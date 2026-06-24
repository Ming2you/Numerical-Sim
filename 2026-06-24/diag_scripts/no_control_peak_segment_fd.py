from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Iterable, List

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.demand import DemandProfile, DemandStep, apply_scenario_network_overrides, load_scenarios
from src.models.metanet import compute_ramp_release_flows, freeway_substep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    off_ramp_capacity_by_freeway_link,
    schedule_offramp_arrivals,
    sync_onramp_queues_from_freeway,
    sync_onramp_queues_to_freeway,
    urban_substep,
)
from src.simulation.coupling import (
    _actual_ramp_release_flows,
    _offramp_flow_from_diagnostics,
    _with_actual_ramp_diagnostics,
)


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _surge_scale(
    time_sec: float,
    start_sec: float | None,
    peak_sec: float | None,
    end_sec: float | None,
    peak_scale: float,
    recovery_scale: float,
) -> float:
    if start_sec is None or peak_sec is None or end_sec is None:
        return 1.0
    if not start_sec < peak_sec < end_sec:
        raise ValueError("surge timing must satisfy start < peak < end")
    if time_sec <= start_sec:
        return 1.0
    if time_sec <= peak_sec:
        fraction = (time_sec - start_sec) / max(peak_sec - start_sec, 1.0e-9)
        return 1.0 + fraction * (peak_scale - 1.0)
    if time_sec <= end_sec:
        fraction = (time_sec - peak_sec) / max(end_sec - peak_sec, 1.0e-9)
        return peak_scale + fraction * (recovery_scale - peak_scale)
    return recovery_scale


def _scaled_demand(demand: DemandStep, scale: float) -> DemandStep:
    return DemandStep(
        freeway_mainline={key: max(0.0, value * scale) for key, value in demand.freeway_mainline.items()},
        urban_boundary={key: max(0.0, value * scale) for key, value in demand.urban_boundary.items()},
        ramp_arrival={key: max(0.0, value * scale) for key, value in demand.ramp_arrival.items()},
        incident_capacity_factor=demand.incident_capacity_factor,
        freeway_lane_loss={
            link: dict(segment_losses)
            for link, segment_losses in demand.freeway_lane_loss.items()
        },
    )


def _trace_no_control_peak(
    cfg: ExperimentConfig,
    scenario_name: str,
    surge_start_sec: float | None = None,
    surge_peak_sec: float | None = None,
    surge_end_sec: float | None = None,
    surge_peak_scale: float = 1.0,
    recovery_scale: float = 1.0,
    urban_scale: float | None = None,
    freeway_scale: float | None = None,
    ramp_scale: float | None = None,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    scenario = load_scenarios("src/config/scenarios.yaml")[scenario_name]
    scenario = replace(
        scenario,
        urban_scale=scenario.urban_scale if urban_scale is None else urban_scale,
        freeway_scale=scenario.freeway_scale if freeway_scale is None else freeway_scale,
        ramp_scale=scenario.ramp_scale if ramp_scale is None else ramp_scale,
    )
    cfg = apply_scenario_network_overrides(cfg, scenario)
    demand_profile = DemandProfile(cfg, scenario)
    state = TrafficState.initial(cfg)
    control = ControlAction.uncontrolled(cfg)
    sim = cfg.simulation
    net = cfg.network
    rows: List[Dict[str, Any]] = []
    interval_rows: List[Dict[str, Any]] = []

    sync_onramp_queues_from_freeway(state, cfg)
    freeway_ttt_total = 0.0
    urban_ttt_total = 0.0
    accepted_offramp_total = 0.0
    rejected_offramp_total = 0.0

    for control_step in range(sim.n_control_steps):
        demand_scale = _surge_scale(
            state.time_sec,
            surge_start_sec,
            surge_peak_sec,
            surge_end_sec,
            surge_peak_scale,
            recovery_scale,
        )
        demand = _scaled_demand(demand_profile.at(state.time_sec), demand_scale)
        start_urban_step = int(round(state.time_sec / max(sim.T_u_sec, 1.0e-9)))
        control_interval_freeway_ttt = 0.0
        control_interval_urban_ttt = 0.0

        for freeway_substep_index in range(sim.K_cf):
            sync_onramp_queues_to_freeway(state, cfg)
            ramp_release, ramp_diag = compute_ramp_release_flows(
                state,
                control,
                demand,
                cfg,
                include_current_arrivals=False,
            )

            urban_rows_in_freeway_step: list[Dict[str, float]] = []
            for urban_offset in range(sim.K_fu):
                step_idx = start_urban_step + freeway_substep_index * sim.K_fu + urban_offset
                ur_ttt, ur_diag = urban_substep(
                    state,
                    control,
                    demand,
                    cfg,
                    urban_step_index=step_idx,
                    ramp_release_veh_h=ramp_release,
                )
                urban_ttt_total += ur_ttt
                control_interval_urban_ttt += ur_ttt
                urban_rows_in_freeway_step.append(ur_diag)

            sync_onramp_queues_to_freeway(state, cfg)
            actual_ramp_release = _actual_ramp_release_flows(urban_rows_in_freeway_step, cfg)
            actual_ramp_diag = _with_actual_ramp_diagnostics(ramp_diag, actual_ramp_release)
            offramp_capacity = off_ramp_capacity_by_freeway_link(
                state,
                cfg,
                interval_h=sim.T_f_h,
            )
            fw_ttt, fw_diag = freeway_substep(
                state,
                control,
                demand,
                cfg,
                offramp_capacity_veh_h=offramp_capacity,
                ramp_release_veh_h=actual_ramp_release,
                ramp_release_diagnostics=actual_ramp_diag,
                update_ramp_queues=False,
                include_ramp_queue_ttt=True,
            )
            freeway_ttt_total += fw_ttt
            control_interval_freeway_ttt += fw_ttt

            next_urban_step = start_urban_step + (freeway_substep_index + 1) * sim.K_fu
            accepted_step = 0.0
            rejected_step = 0.0
            for off_ramp in net.off_ramps:
                flow = _offramp_flow_from_diagnostics(fw_diag, cfg, off_ramp)
                vehicles = flow * sim.T_f_h
                accepted, rejected = schedule_offramp_arrivals(state, cfg, off_ramp, vehicles, next_urban_step)
                accepted_step += accepted
                rejected_step += rejected
            accepted_offramp_total += accepted_step
            rejected_offramp_total += rejected_step

            elapsed = control_step * sim.T_c_sec + (freeway_substep_index + 1) * sim.T_f_sec
            state.ensure_freeway_lane_profile(net)
            for link in net.freeway_links:
                for segment, (rho, speed, flow, lanes) in enumerate(
                    zip(
                        state.freeway_density[link],
                        state.freeway_speed[link],
                        state.freeway_flow[link],
                        state.freeway_effective_lanes[link],
                    )
                ):
                    rows.append(
                        {
                            "scenario": scenario_name,
                            "controller": "NO-CONTROL",
                            "plant": "coupled_metanet_storage_cap",
                            "control_step": control_step,
                            "freeway_substep": control_step * sim.K_cf + freeway_substep_index,
                            "time_sec": float(elapsed),
                            "branch": (
                                "loading"
                                if surge_peak_sec is None or elapsed <= surge_peak_sec
                                else "unloading"
                            ),
                            "link": link,
                            "segment": segment,
                            "rho_veh_km_lane": float(rho),
                            "speed_km_h": float(speed),
                            "flow_veh_h": float(flow),
                            "lambda_eff": float(lanes),
                            "mainline_demand_veh_h": float(demand.freeway_mainline.get(link, 0.0)),
                            "ramp_arrival_total_veh_h": float(sum(demand.ramp_arrival.values())),
                            "demand_scale": float(demand_scale),
                            "mainline_origin_queue_total_veh": float(sum(max(0.0, q) for q in state.mainline_origin_queue.values())),
                            "ramp_queue_total_veh": float(sum(max(0.0, q) for q in state.ramp_queue.values())),
                            "offramp_accepted_step_veh": float(accepted_step),
                            "offramp_rejected_step_veh": float(rejected_step),
                            "freeway_ttt_cum": float(freeway_ttt_total),
                            "urban_ttt_cum": float(urban_ttt_total),
                        }
                    )

        state.time_sec += sim.T_c_sec
        interval_rows.append(
            {
                "scenario": scenario_name,
                "controller": "NO-CONTROL",
                "control_step": control_step,
                "time_sec": float(state.time_sec),
                "demand_scale": float(demand_scale),
                "control_interval_freeway_ttt": float(control_interval_freeway_ttt),
                "control_interval_urban_ttt": float(control_interval_urban_ttt),
                "cumulative_freeway_ttt": float(freeway_ttt_total),
                "cumulative_urban_ttt": float(urban_ttt_total),
                "cumulative_total_ttt": float(freeway_ttt_total + urban_ttt_total),
                "mainline_origin_queue_total_veh": float(sum(max(0.0, q) for q in state.mainline_origin_queue.values())),
                "ramp_queue_total_veh": float(sum(max(0.0, q) for q in state.ramp_queue.values())),
                "accepted_offramp_total_veh": float(accepted_offramp_total),
                "rejected_offramp_total_veh": float(rejected_offramp_total),
            }
        )
    return rows, interval_rows


def _aggregate_fd(rows: Iterable[Dict[str, Any]], window_sec: float) -> List[Dict[str, Any]]:
    rows = list(rows)
    groups: Dict[tuple[str, int, int], list[Dict[str, Any]]] = {}
    for row in rows:
        key = (
            str(row["link"]),
            int(row["segment"]),
            int((float(row["time_sec"]) - 1.0e-9) // window_sec),
        )
        groups.setdefault(key, []).append(row)
    out = []
    for (link, segment, window), group in sorted(groups.items()):
        time_sec = sum(float(row["time_sec"]) for row in group) / len(group)
        out.append(
            {
                "link": link,
                "segment": segment,
                "window": window,
                "time_sec": time_sec,
                "branch": "loading",
                "rho_veh_km_lane": sum(float(row["rho_veh_km_lane"]) for row in group) / len(group),
                "flow_veh_h": sum(float(row["flow_veh_h"]) for row in group) / len(group),
                "speed_km_h": sum(float(row["speed_km_h"]) for row in group) / len(group),
            }
        )
    peak_time_by_panel: Dict[tuple[str, int], float] = {}
    for row in out:
        key = (str(row["link"]), int(row["segment"]))
        current_time = peak_time_by_panel.get(key)
        if current_time is None:
            peak_time_by_panel[key] = float(row["time_sec"])
            continue
        current_peak = next(
            candidate
            for candidate in out
            if str(candidate["link"]) == key[0]
            and int(candidate["segment"]) == key[1]
            and float(candidate["time_sec"]) == current_time
        )
        if float(row["rho_veh_km_lane"]) > float(current_peak["rho_veh_km_lane"]):
            peak_time_by_panel[key] = float(row["time_sec"])
    for row in out:
        key = (str(row["link"]), int(row["segment"]))
        row["branch"] = (
            "loading"
            if float(row["time_sec"]) <= peak_time_by_panel[key]
            else "unloading"
        )
    return out


def _summary(rows: List[Dict[str, Any]], cfg: ExperimentConfig) -> List[Dict[str, Any]]:
    out = []
    for link in cfg.network.freeway_links:
        for segment in range(cfg.network.freeway_segments_per_link):
            subset = [
                row
                for row in rows
                if row["link"] == link and int(row["segment"]) == segment
            ]
            if not subset:
                continue
            out.append(
                {
                    "link": link,
                    "segment": segment,
                    "max_rho_veh_km_lane": max(float(row["rho_veh_km_lane"]) for row in subset),
                    "mean_rho_veh_km_lane": sum(float(row["rho_veh_km_lane"]) for row in subset) / len(subset),
                    "final_rho_veh_km_lane": float(subset[-1]["rho_veh_km_lane"]),
                    "max_flow_veh_h": max(float(row["flow_veh_h"]) for row in subset),
                    "mean_flow_veh_h": sum(float(row["flow_veh_h"]) for row in subset) / len(subset),
                    "min_speed_km_h": min(float(row["speed_km_h"]) for row in subset),
                    "congested_samples": sum(
                        1 for row in subset if float(row["rho_veh_km_lane"]) > cfg.network.rho_crit
                    ),
                    "samples": len(subset),
                }
            )
    return out


def _plot_segment_fd(
    rows: List[Dict[str, Any]],
    agg_rows: List[Dict[str, Any]],
    summary_rows: List[Dict[str, Any]],
    cfg: ExperimentConfig,
    scenario_name: str,
    aggregate_window_sec: float,
    out_path: Path,
) -> None:
    links = cfg.network.freeway_links
    n_segments = cfg.network.freeway_segments_per_link
    by_panel = {
        (str(row["link"]), int(row["segment"])): []
        for row in rows
    }
    for row in rows:
        by_panel[(str(row["link"]), int(row["segment"]))].append(row)
    agg_by_panel: Dict[tuple[str, int], list[Dict[str, Any]]] = {}
    for row in agg_rows:
        agg_by_panel.setdefault((str(row["link"]), int(row["segment"])), []).append(row)
    summary = {(row["link"], int(row["segment"])): row for row in summary_rows}

    all_rho = [float(row["rho_veh_km_lane"]) for row in rows]
    all_flow = [float(row["flow_veh_h"]) for row in rows]
    x_min = max(0.0, min(all_rho) - 3.0)
    x_max = max(max(all_rho) + 5.0, cfg.network.rho_crit + 8.0)
    y_min = max(0.0, min(all_flow) - 250.0)
    y_max = max(all_flow) + 400.0

    panel_w = 330
    panel_h = 245
    margin_l = 80
    margin_t = 115
    gap_x = 35
    gap_y = 70
    width = margin_l + n_segments * panel_w + (n_segments - 1) * gap_x + 45
    height = margin_t + len(links) * panel_h + (len(links) - 1) * gap_y + 115
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    try:
        title_font = ImageFont.truetype("arial.ttf", 24)
        font = ImageFont.truetype("arial.ttf", 17)
        small = ImageFont.truetype("arial.ttf", 12)
        tiny = ImageFont.truetype("arial.ttf", 10)
    except OSError:
        title_font = font = small = tiny = ImageFont.load_default()

    draw.text((36, 24), f"No-control {scenario_name} freeway segment FD", fill=(20, 20, 20), font=title_font)
    draw.text(
        (36, 56),
        f"Coupled METANET plant with storage receiving cap; 10 s samples, {aggregate_window_sec:g} s aggregate path",
        fill=(70, 70, 70),
        font=small,
    )
    draw.text(
        (36, 75),
        f"T={cfg.simulation.T_total:.0f}s, rho_crit={cfg.network.rho_crit:.1f}, rho_max={cfg.network.rho_max:.1f}, capacity={cfg.network.freeway_capacity_veh_h:.0f} veh/h",
        fill=(70, 70, 70),
        font=small,
    )

    colors = {"loading": (43, 108, 176), "unloading": (213, 94, 0)}
    for r, link in enumerate(links):
        for segment in range(n_segments):
            left = margin_l + segment * (panel_w + gap_x)
            top = margin_t + r * (panel_h + gap_y)
            right = left + panel_w
            bottom = top + panel_h
            draw.rectangle((left, top, right, bottom), outline=(35, 35, 35), width=1)
            for frac in (0.25, 0.5, 0.75):
                x = left + frac * panel_w
                y = top + frac * panel_h
                draw.line((x, top, x, bottom), fill=(225, 225, 225))
                draw.line((left, y, right, y), fill=(225, 225, 225))

            def xy(rho: float, flow: float) -> tuple[float, float]:
                x = left + (rho - x_min) / max(x_max - x_min, 1.0e-9) * panel_w
                y = bottom - (flow - y_min) / max(y_max - y_min, 1.0e-9) * panel_h
                return x, y

            xcrit, _ = xy(cfg.network.rho_crit, y_min)
            draw.line((xcrit, top, xcrit, bottom), fill=(130, 130, 130), width=1)

            panel_rows = by_panel.get((link, segment), [])
            for row in panel_rows[::2]:
                x, y = xy(float(row["rho_veh_km_lane"]), float(row["flow_veh_h"]))
                draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(175, 175, 175))

            panel_agg = agg_by_panel.get((link, segment), [])
            pts = [
                xy(float(row["rho_veh_km_lane"]), float(row["flow_veh_h"]))
                for row in panel_agg
            ]
            if len(pts) > 1:
                draw.line(pts, fill=(20, 20, 20), width=2)
            for row, (x, y) in zip(panel_agg, pts):
                color = colors.get(str(row["branch"]), (20, 20, 20))
                draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color, outline="white")

            title = f"{link} seg{segment}"
            draw.text((left + 6, top - 22), title, fill=(20, 20, 20), font=font)
            s = summary.get((link, segment), {})
            info = (
                f"max rho {float(s.get('max_rho_veh_km_lane', 0.0)):.1f}\n"
                f"mean q {float(s.get('mean_flow_veh_h', 0.0)):.0f}\n"
                f"cong {int(float(s.get('congested_samples', 0.0)))}"
            )
            draw.multiline_text((left + 8, top + 8), info, fill=(30, 30, 30), font=tiny, spacing=2)

            for frac in (0.0, 0.5, 1.0):
                xv = x_min + frac * (x_max - x_min)
                x = left + frac * panel_w
                draw.line((x, bottom, x, bottom + 4), fill=(40, 40, 40))
                draw.text((x - 10, bottom + 6), f"{xv:.0f}", fill=(60, 60, 60), font=tiny)
                yv = y_min + frac * (y_max - y_min)
                y = bottom - frac * panel_h
                draw.line((left - 4, y, left, y), fill=(40, 40, 40))
                draw.text((left - 54, y - 6), f"{yv:.0f}", fill=(60, 60, 60), font=tiny)
            if r == len(links) - 1:
                draw.text((left + 75, bottom + 28), "rho (veh/km/lane)", fill=(50, 50, 50), font=small)
            if segment == 0:
                draw.text((left - 64, top - 18), "flow (veh/h)", fill=(50, 50, 50), font=small)

    legend_y = height - 48
    draw.ellipse((margin_l, legend_y, margin_l + 12, legend_y + 12), fill=colors["loading"])
    draw.text((margin_l + 18, legend_y - 2), f"{aggregate_window_sec:g} s aggregate: loading", fill=(50, 50, 50), font=small)
    draw.ellipse((margin_l + 250, legend_y, margin_l + 262, legend_y + 12), fill=colors["unloading"])
    draw.text((margin_l + 268, legend_y - 2), f"{aggregate_window_sec:g} s aggregate: unloading", fill=(50, 50, 50), font=small)
    draw.text((margin_l + 548, legend_y - 2), "gray dots: 10 s states", fill=(90, 90, 90), font=small)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="src/config/default.yaml")
    parser.add_argument("--scenario", default="peak_demand")
    parser.add_argument("--out-dir", default="outputs/no_control_peak_segment_fd_storage_cap")
    parser.add_argument("--figure", default="reports/figures/fig_no_control_peak_segment_fd_storage_cap.png")
    parser.add_argument("--aggregate-window-sec", type=float, default=600.0)
    parser.add_argument("--total-sec", type=float, default=None)
    parser.add_argument("--rho-max", type=float, default=None)
    parser.add_argument("--surge-start-sec", type=float, default=None)
    parser.add_argument("--surge-peak-sec", type=float, default=None)
    parser.add_argument("--surge-end-sec", type=float, default=None)
    parser.add_argument("--surge-peak-scale", type=float, default=1.0)
    parser.add_argument("--recovery-scale", type=float, default=1.0)
    parser.add_argument("--urban-scale", type=float, default=None)
    parser.add_argument("--freeway-scale", type=float, default=None)
    parser.add_argument("--ramp-scale", type=float, default=None)
    args = parser.parse_args()

    cfg = ExperimentConfig.from_file(args.config)
    if args.total_sec is not None:
        cfg = cfg.with_updates({"simulation": {"T_total": float(args.total_sec)}})
    if args.rho_max is not None:
        cfg = cfg.with_updates({"network": {"rho_max": float(args.rho_max)}})
    rows, interval_rows = _trace_no_control_peak(
        cfg,
        args.scenario,
        args.surge_start_sec,
        args.surge_peak_sec,
        args.surge_end_sec,
        args.surge_peak_scale,
        args.recovery_scale,
        args.urban_scale,
        args.freeway_scale,
        args.ramp_scale,
    )
    summary_rows = _summary(rows, cfg)
    agg_rows = _aggregate_fd(rows, args.aggregate_window_sec)

    out_dir = Path(args.out_dir)
    _write_csv(out_dir / "segment_fd_timeseries.csv", rows)
    _write_csv(out_dir / "segment_fd_aggregate.csv", agg_rows)
    _write_csv(out_dir / "segment_fd_summary.csv", summary_rows)
    _write_csv(out_dir / "control_interval_summary.csv", interval_rows)
    plot_scenario = args.scenario + (" surge" if args.surge_start_sec is not None else "")
    _plot_segment_fd(
        rows,
        agg_rows,
        summary_rows,
        cfg,
        plot_scenario,
        args.aggregate_window_sec,
        Path(args.figure),
    )

    metadata = {
        "scenario": args.scenario,
        "controller": "NO-CONTROL",
        "plant": "coupled_metanet_storage_cap",
        "timeseries_rows": len(rows),
        "aggregate_rows": len(agg_rows),
        "summary_rows": len(summary_rows),
        "rho_max": float(cfg.network.rho_max),
        "total_sec": float(cfg.simulation.T_total),
        "surge_start_sec": args.surge_start_sec,
        "surge_peak_sec": args.surge_peak_sec,
        "surge_end_sec": args.surge_end_sec,
        "surge_peak_scale": args.surge_peak_scale,
        "recovery_scale": args.recovery_scale,
        "urban_scale": args.urban_scale,
        "freeway_scale": args.freeway_scale,
        "ramp_scale": args.ramp_scale,
        "final_total_ttt": (
            interval_rows[-1]["cumulative_total_ttt"] if interval_rows else 0.0
        ),
        "figure": args.figure,
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
