# Arora-Kattan capacity-drop Step 2 진단: rise-fall 수요에서 flow-density hysteresis를 확인한다.
#
# 실행:
#   PYTHONPATH=<repo> python -B 2026-06-24/diag_scripts/capacity_drop_hysteresis_probe.py
#
# 이 스크립트는 default.yaml을 수정하지 않고 runtime override만 사용한다. off-ramp lane-drop
# 모델은 꺼 두어 이번 진단을 anticipation ν regime split 효과로만 분리한다.
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    matplotlib = None
    plt = None

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.demand import DemandStep
from src.models.metanet import (
    effective_desired_speed_kmh,
    freeway_substep,
    metanet_speed_update_kmh,
    segment_flow_veh_h,
    select_anticipation_nu,
)
from src.models.state import ControlAction, ExperimentConfig, TrafficState


DEFAULT_NU_VALUES = (65.0, 100.0, 150.0, 250.0)


def _parse_nu_values(raw: str) -> List[float]:
    out = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            out.append(float(item))
    return out or list(DEFAULT_NU_VALUES)


def _parse_segment_indices(raw: str | None) -> set[int] | None:
    if raw is None or raw.strip() == "":
        return None
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            out.update(range(min(start, end), max(start, end) + 1))
        else:
            out.add(int(part))
    return out


def _rise_fall_factor(time_sec: float, total_sec: float) -> float:
    """0->중앙 peak->0 형태의 transient surge 계수."""
    x = min(max(time_sec / max(total_sec, 1.0), 0.0), 1.0)
    return math.sin(math.pi * x)


def _build_cfg(base: ExperimentConfig, total_sec: float, toggle: bool, nu_cong: float) -> ExperimentConfig:
    """기본 config는 보존하고, Step 2 진단에 필요한 네트워크 파라미터만 runtime override한다."""
    off_zero = {off_ramp: 0.0 for off_ramp in base.network.off_ramps}
    return base.with_updates(
        {
            "simulation": {"T_total": float(total_sec)},
            "network": {
                "capacity_drop_anticipation": bool(toggle),
                "metanet_nu_cong_km2_h": float(nu_cong),
                "off_ramp_split_ratio": off_zero,
            },
            "freeway_offramp_capacity_drop": {"enabled": False},
        }
    )


def _demand_at(
    cfg: ExperimentConfig,
    time_sec: float,
    mainline_low: float,
    mainline_peak: float,
    ramp_low: float,
    ramp_peak: float,
) -> DemandStep:
    """rise-fall 본선/램프 수요를 veh/h 단위로 만든다."""
    factor = _rise_fall_factor(time_sec, cfg.simulation.T_total)
    mainline = mainline_low + (mainline_peak - mainline_low) * factor
    ramp = ramp_low + (ramp_peak - ramp_low) * factor
    return DemandStep(
        freeway_mainline={link: mainline for link in cfg.network.freeway_links},
        urban_boundary={},
        ramp_arrival={ramp_name: ramp for ramp_name in cfg.network.ramps},
        incident_capacity_factor=1.0,
    )


def _freeway_substep_paper_eq6(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
    fixed_vsl_kmh: float | None = None,
    fixed_vsl_link: str = "all",
    fixed_vsl_segments: set[int] | None = None,
    eq6_storage_cap: bool = False,
) -> Dict[str, float]:
    """논문 Eq. (6) boundary-flow만 분리 구현한 진단용 freeway substep.

    기존 plant의 CTM storage receiving을 쓰지 않고, 인접 segment 경계 유량을
    Arora-Kattan modified METANET Eq. (6) 형태로 계산한다. 밀도 보존식과 속도식은
    기존 단위계(veh/km/lane, km/h, veh/h)를 유지한다.
    """
    net = cfg.network
    dt_h = cfg.simulation.T_f_h
    lanes = float(net.freeway_lanes)
    q_cap = float(net.freeway_capacity_veh_h) * float(getattr(demand, "incident_capacity_factor", 1.0))
    diagnostics: Dict[str, float] = {}
    state.ensure_freeway_lane_profile(net)

    for link in net.freeway_links:
        rhos = list(state.freeway_density[link])
        speeds = list(state.freeway_speed[link])
        q_values = [segment_flow_veh_h(rho, speed, lanes) for rho, speed in zip(rhos, speeds)]
        receiving = [
            max(
                0.0,
                (net.rho_max - max(0.0, rho)) * net.freeway_segment_length_km * lanes / max(dt_h, 1.0e-9),
            )
            for rho in rhos
        ]
        receiving_for_mainline = list(receiving)

        ramp_in_by_segment = [0.0 for _ in rhos]
        for ramp in net.ramps:
            if net.ramp_to_freeway[ramp] != link:
                continue
            merge_idx = int(max(0, min(len(rhos) - 1, net.ramp_merge_segment_index.get(ramp, 0))))
            available_flow = (
                max(0.0, demand.ramp_arrival.get(ramp, 0.0))
                + state.ramp_queue.get(ramp, 0.0) / max(dt_h, 1.0e-9)
            )
            release = min(
                available_flow,
                control.ramp_metering.get(ramp, net.ramp_capacity_veh_h[ramp]),
                net.ramp_capacity_veh_h[ramp],
            )
            if eq6_storage_cap:
                release = min(release, receiving_for_mainline[merge_idx])
                receiving_for_mainline[merge_idx] = max(0.0, receiving_for_mainline[merge_idx] - release)
            ramp_in_by_segment[merge_idx] += release
            state.ramp_queue[ramp] = max(
                0.0,
                state.ramp_queue.get(ramp, 0.0) + dt_h * (demand.ramp_arrival.get(ramp, 0.0) - release),
            )
            diagnostics[f"ramp_release_{ramp}_veh_h"] = float(release)

        # 논문 Eq. (6): downstream free면 downstream capacity와 upstream sending 중 작은 값,
        # downstream congested면 downstream through-flow와 upstream sending 중 작은 값.
        q_inter: List[float] = []
        for i in range(len(rhos) - 1):
            upstream_sending = q_values[i]
            downstream_flow = q_values[i + 1]
            if rhos[i + 1] <= net.rho_crit:
                boundary_flow = min(q_cap, upstream_sending)
            else:
                boundary_flow = min(downstream_flow, upstream_sending)
            if eq6_storage_cap:
                boundary_flow = min(boundary_flow, receiving_for_mainline[i + 1])
            q_inter.append(max(0.0, boundary_flow))
        for idx, boundary_flow in enumerate(q_inter):
            diagnostics[f"q_inter_{link}_{idx}_veh_h"] = float(boundary_flow)
        for idx, supply in enumerate(receiving_for_mainline):
            diagnostics[f"receiving_mainline_{link}_{idx}_veh_h"] = float(supply)

        mainline_demand = max(0.0, demand.freeway_mainline.get(link, 0.0))
        queued_flow = state.mainline_origin_queue.get(link, 0.0) / max(dt_h, 1.0e-9)
        entry_request = mainline_demand + queued_flow
        entry_realized = min(entry_request, q_cap)
        if eq6_storage_cap:
            entry_realized = min(entry_realized, receiving_for_mainline[0])
        diagnostics[f"entry_{link}_veh_h"] = float(entry_realized)
        state.mainline_origin_queue[link] = max(
            0.0,
            state.mainline_origin_queue.get(link, 0.0) + dt_h * (mainline_demand - entry_realized),
        )

        next_rhos: List[float] = []
        next_speeds: List[float] = []
        next_flows: List[float] = []
        for i, rho in enumerate(rhos):
            q_in = entry_realized if i == 0 else q_inter[i - 1]
            q_in += ramp_in_by_segment[i]
            q_out = min(q_cap, q_values[i]) if i == len(rhos) - 1 else q_inter[i]

            # 차량보존식: rho는 veh/km/lane, q는 veh/h, dt는 hour.
            vehicle_count = max(0.0, rho) * net.freeway_segment_length_km * lanes
            vehicle_next = max(0.0, vehicle_count + dt_h * (q_in - q_out))
            rho_next = vehicle_next / max(net.freeway_segment_length_km * lanes, 1.0e-9)

            upstream_speed = net.v_free if i == 0 else speeds[i - 1]
            downstream_rho = rhos[i + 1] if i + 1 < len(rhos) else rhos[i]
            link_match = fixed_vsl_link in {"all", "*"} or fixed_vsl_link == link
            segment_match = fixed_vsl_segments is None or i in fixed_vsl_segments
            if fixed_vsl_kmh is not None and link_match and segment_match:
                vsl_i = float(fixed_vsl_kmh)
            else:
                vsl_i = float(control.vsl.get(link, max(cfg.freeway_follower.vsl_set)))
            vsl_active_i = vsl_i < max(cfg.freeway_follower.vsl_set) - 0.5
            v_eff = effective_desired_speed_kmh(
                rho,
                net.v_free,
                net.rho_crit,
                vsl_i,
                net.alpha_vsl,
                vsl_active_i,
                net.metanet_a_m,
            )
            v_next = metanet_speed_update_kmh(
                speeds[i],
                upstream_speed,
                rho,
                downstream_rho,
                v_eff,
                dt_h,
                net.freeway_segment_length_km,
                net.metanet_tau_h,
                select_anticipation_nu(rho, net),
                net.metanet_kappa_veh_km_lane,
                net.v_min,
            )
            next_rhos.append(rho_next)
            next_speeds.append(v_next)
            next_flows.append(segment_flow_veh_h(rho_next, v_next, lanes))

        state.freeway_density[link] = next_rhos
        state.freeway_speed[link] = next_speeds
        state.freeway_flow[link] = next_flows
        diagnostics[f"exit_{link}_veh_h"] = float(min(q_cap, q_values[-1]) if q_values else 0.0)

    return diagnostics


def _branch_binned(rows: List[Dict[str, float]], branch: str, bin_width: float) -> Dict[int, List[float]]:
    bins: Dict[int, List[float]] = {}
    for row in rows:
        if row["branch"] != branch:
            continue
        idx = int(math.floor(row["rho"] / bin_width))
        bins.setdefault(idx, []).append(row["flow"])
    return bins


def _percentile(values: Iterable[float], pct: float) -> float:
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * min(max(pct, 0.0), 100.0) / 100.0
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def _metrics(rows: List[Dict[str, float]], rho_crit: float, q_ref_fallback: float) -> Dict[str, float]:
    """loading/unloading branch의 같은 밀도 bin 유량 차이와 capacity-drop 크기를 계산한다."""
    loading = _branch_binned(rows, "loading", bin_width=2.0)
    unloading = _branch_binned(rows, "unloading", bin_width=2.0)
    gaps = []
    for idx in sorted(set(loading).intersection(unloading)):
        if len(loading[idx]) < 3 or len(unloading[idx]) < 3:
            continue
        rho_mid = (idx + 0.5) * 2.0
        if rho_mid < 0.75 * rho_crit:
            continue
        gaps.append(sum(loading[idx]) / len(loading[idx]) - sum(unloading[idx]) / len(unloading[idx]))

    near_critical_loading = [
        row["flow"]
        for row in rows
        if row["branch"] == "loading" and 0.85 * rho_crit <= row["rho"] <= 1.05 * rho_crit
    ]
    q_ref = max(near_critical_loading) if near_critical_loading else q_ref_fallback
    congested_unloading = [
        row["flow"]
        for row in rows
        if row["branch"] == "unloading" and row["rho"] > 1.03 * rho_crit
    ]
    congested_discharge = _percentile(congested_unloading, 90.0) if congested_unloading else math.nan
    drop_pct = (
        100.0 * (q_ref - congested_discharge) / max(q_ref, 1.0e-9)
        if congested_unloading
        else math.nan
    )
    gap_mean = sum(gaps) / len(gaps) if gaps else 0.0
    drop_in_target = (
        1.0
        if congested_unloading and 5.0 <= drop_pct <= 15.0
        else 0.0
    )
    return {
        "free_capacity_ref_veh_h": float(q_ref),
        "congested_discharge_p90_veh_h": float(congested_discharge),
        "drop_pct": float(drop_pct),
        "loop_gap_mean_veh_h": float(gap_mean),
        "loop_overlap_bins": float(len(gaps)),
        "has_loop": float(len(gaps) >= 4 and gap_mean > max(50.0, 0.02 * q_ref)),
        "drop_in_target_5_15pct": drop_in_target,
    }


def _run_case(
    label: str,
    cfg: ExperimentConfig,
    mainline_low: float,
    mainline_peak: float,
    ramp_low: float,
    ramp_peak: float,
    probe_link: str,
    probe_segment: int,
    plant_mode: str,
    fixed_vsl_kmh: float | None,
    fixed_vsl_link: str,
    fixed_vsl_segments: set[int] | None,
    eq6_storage_cap: bool,
) -> Tuple[List[Dict[str, float]], Dict[str, float]]:
    state = TrafficState.initial(cfg)
    control = ControlAction.uncontrolled(cfg)
    if fixed_vsl_kmh is not None:
        control.vsl = {link: float(fixed_vsl_kmh) for link in cfg.network.freeway_links}
    dt = float(cfg.simulation.T_f)
    total = float(cfg.simulation.T_total)
    steps = int(math.ceil(total / max(dt, 1.0e-9)))
    rows: List[Dict[str, float]] = []
    for step in range(steps):
        time_sec = step * dt
        demand = _demand_at(cfg, time_sec, mainline_low, mainline_peak, ramp_low, ramp_peak)
        if plant_mode == "eq6":
            step_diag = _freeway_substep_paper_eq6(
                state,
                control,
                demand,
                cfg,
                fixed_vsl_kmh,
                fixed_vsl_link,
                fixed_vsl_segments,
                eq6_storage_cap,
            )
        else:
            _, step_diag = freeway_substep(state, control, demand, cfg)
        rhos = state.freeway_density[probe_link]
        speeds = state.freeway_speed[probe_link]
        flows = state.freeway_flow[probe_link]
        seg = min(max(probe_segment, 0), len(rhos) - 1)
        probe_inflow = (
            step_diag.get(f"q_inter_{probe_link}_{seg - 1}_veh_h", float("nan"))
            if seg > 0
            else step_diag.get(f"entry_{probe_link}_veh_h", float("nan"))
        )
        branch = "loading" if time_sec <= 0.5 * total else "unloading"
        rows.append(
            {
                "case": label,
                "plant_mode": plant_mode,
                "time_sec": float(time_sec + dt),
                "branch": branch,
                "demand_factor": _rise_fall_factor(time_sec, total),
                "mainline_demand_veh_h": float(demand.freeway_mainline[probe_link]),
                "ramp_arrival_each_veh_h": float(next(iter(demand.ramp_arrival.values()))),
                "fixed_vsl_kmh": float(fixed_vsl_kmh) if fixed_vsl_kmh is not None else float("nan"),
                "fixed_vsl_link": fixed_vsl_link,
                "fixed_vsl_segments": (
                    "all"
                    if fixed_vsl_segments is None
                    else ",".join(str(i) for i in sorted(fixed_vsl_segments))
                ),
                "eq6_storage_cap": float(eq6_storage_cap),
                "rho": float(rhos[seg]),
                "speed": float(speeds[seg]),
                "flow": float(flows[seg]),
                "probe_inflow_veh_h": float(probe_inflow),
                "rho_mean": float(sum(rhos) / len(rhos)),
                "speed_mean": float(sum(speeds) / len(speeds)),
                "flow_mean": float(sum(flows) / len(flows)),
                "origin_queue_veh": float(state.mainline_origin_queue.get(probe_link, 0.0)),
                "ramp_queue_total_veh": float(sum(state.ramp_queue.values())),
            }
        )
    q_ref = cfg.network.freeway_capacity_veh_h * 0.98
    metrics = _metrics(rows, cfg.network.rho_crit, q_ref)
    return rows, metrics


def _write_csv(path: Path, rows: List[Dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _plot(all_rows: Dict[str, List[Dict[str, float]]], metrics_rows: List[Dict[str, float]], out_path: Path, rho_crit: float) -> None:
    if plt is None:
        print("SKIP figure: matplotlib is not installed in this Python runtime.")
        return
    cols = 2
    rows_n = int(math.ceil(len(all_rows) / cols))
    fig, axes = plt.subplots(rows_n, cols, figsize=(11, max(4.0, rows_n * 3.8)), squeeze=False)
    summary = {row["case"]: row for row in metrics_rows}
    for ax, (label, rows) in zip(axes.ravel(), all_rows.items()):
        loading = [row for row in rows if row["branch"] == "loading"]
        unloading = [row for row in rows if row["branch"] == "unloading"]
        ax.scatter([r["rho"] for r in loading], [r["flow"] for r in loading], s=12, alpha=0.65, label="loading")
        ax.scatter([r["rho"] for r in unloading], [r["flow"] for r in unloading], s=12, alpha=0.65, label="unloading")
        ax.axvline(rho_crit, color="k", ls="--", lw=0.9)
        ax.axhline(summary[label]["free_capacity_ref_veh_h"], color="k", ls=":", lw=0.9)
        ax.set_title(
            f"{label}: drop={summary[label]['drop_pct']:.1f}%, "
            f"gap={summary[label]['loop_gap_mean_veh_h']:.0f}"
        )
        ax.set_xlabel(r"$\rho$ (veh/km/lane)")
        ax.set_ylabel("flow (veh/h)")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    for ax in axes.ravel()[len(all_rows):]:
        ax.axis("off")
    fig.suptitle("Capacity-drop hysteresis probe: rise-fall demand, probe segment trajectory")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="src/config/default.yaml")
    parser.add_argument("--out-dir", default="outputs/capacity_drop_hysteresis")
    parser.add_argument("--figure", default="reports/figures/fig_capacity_drop_hysteresis.png")
    parser.add_argument("--nu-values", default=",".join(str(v) for v in DEFAULT_NU_VALUES))
    parser.add_argument("--total-sec", type=float, default=7200.0)
    parser.add_argument("--mainline-low", type=float, default=2500.0)
    parser.add_argument("--mainline-peak", type=float, default=4300.0)
    parser.add_argument("--ramp-low", type=float, default=50.0)
    parser.add_argument("--ramp-peak", type=float, default=1400.0)
    parser.add_argument("--probe-link", default="FW_W")
    parser.add_argument("--probe-segment", type=int, default=2)
    parser.add_argument("--plant-mode", choices=("existing", "eq6"), default="existing")
    parser.add_argument("--fixed-vsl", type=float, default=None)
    parser.add_argument("--fixed-vsl-link", default="all")
    parser.add_argument("--fixed-vsl-segments", default=None)
    parser.add_argument("--eq6-storage-cap", action="store_true")
    args = parser.parse_args()

    base = ExperimentConfig.from_file(args.config)
    nu_values = _parse_nu_values(args.nu_values)
    fixed_vsl_segments = _parse_segment_indices(args.fixed_vsl_segments)
    out_dir = Path(args.out_dir)
    all_rows: Dict[str, List[Dict[str, float]]] = {}
    summary_rows: List[Dict[str, float]] = []

    # toggle-off 대조군: nu_cong 값을 크게 줘도 off면 ν_free 단일값으로 동작해야 한다.
    cases = [("toggle_off", False, max(nu_values))]
    cases.extend((f"nu_cong_{nu:g}", True, nu) for nu in nu_values)

    for label, toggle, nu_cong in cases:
        cfg = _build_cfg(base, args.total_sec, toggle, nu_cong)
        rows, metrics = _run_case(
            label,
            cfg,
            args.mainline_low,
            args.mainline_peak,
            args.ramp_low,
            args.ramp_peak,
            args.probe_link,
            args.probe_segment,
            args.plant_mode,
            args.fixed_vsl,
            args.fixed_vsl_link,
            fixed_vsl_segments,
            args.eq6_storage_cap,
        )
        all_rows[label] = rows
        _write_csv(out_dir / f"trajectory_{label}.csv", rows)
        summary_rows.append(
            {
                "case": label,
                "plant_mode": args.plant_mode,
                "eq6_storage_cap": float(args.eq6_storage_cap),
                "fixed_vsl_kmh": float(args.fixed_vsl) if args.fixed_vsl is not None else float("nan"),
                "fixed_vsl_link": args.fixed_vsl_link,
                "fixed_vsl_segments": (
                    "all"
                    if fixed_vsl_segments is None
                    else ",".join(str(i) for i in sorted(fixed_vsl_segments))
                ),
                "capacity_drop_anticipation": float(toggle),
                "nu_free_km2_h": float(base.network.metanet_nu_km2_h),
                "nu_cong_km2_h": float(nu_cong),
                "rho_crit": float(cfg.network.rho_crit),
                **metrics,
            }
        )

    _write_csv(out_dir / "summary.csv", summary_rows)
    _plot(all_rows, summary_rows, Path(args.figure), base.network.rho_crit)
    print(f"WROTE {out_dir / 'summary.csv'}")
    print(f"WROTE {args.figure}")
    for row in summary_rows:
        print(
            f"{row['case']}: drop={row['drop_pct']:.2f}% "
            f"loop_gap={row['loop_gap_mean_veh_h']:.1f} "
            f"bins={int(row['loop_overlap_bins'])} "
            f"has_loop={int(row['has_loop'])}"
        )


if __name__ == "__main__":
    main()
