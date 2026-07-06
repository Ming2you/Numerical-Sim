from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.controllers.leader import LeaderAction
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig, segment_vsl

BASE_PATH = ROOT / "work" / "forced_leader_response_probe.py"
base_spec = importlib.util.spec_from_file_location("forced_leader_response_probe_base", BASE_PATH)
if base_spec is None or base_spec.loader is None:
    raise RuntimeError(f"Cannot load base probe helpers from {BASE_PATH}")
base = importlib.util.module_from_spec(base_spec)
base_spec.loader.exec_module(base)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_cfg(scenario_name: str, t_total: float, np_mode: str) -> tuple[ExperimentConfig, Any]:
    overrides = {
        "mpc": {
            "relaxed_quantized_controls": True,
            "grid_parallel_backend": "serial",
            "leader_search_mode": "grid",
            "stackelberg_leader_parallel_backend": "serial",
            "wu_faithful_np_coordination_mode": np_mode,
            "wu_faithful_joint_freeway_rm_vsl": True,
            "wu_faithful_joint_urban_green_offset": True,
            "wu_faithful_metering_to_urban_ramp_space": True,
            "wu_faithful_joint_marginal_price": False,
        },
        "simulation": {"T_total": float(t_total)},
    }
    cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), overrides)
    scenario = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))[scenario_name]
    return apply_scenario_network_overrides(cfg, scenario), scenario


def copy_green(candidate: ControlAction, legacy: ControlAction, cfg: ExperimentConfig, signal: str | None = None) -> None:
    signals = [signal] if signal is not None else list(cfg.network.signals)
    for s in signals:
        candidate.green_times[f"{s}_p1"] = float(legacy.green_times.get(f"{s}_p1", 0.0))
        candidate.green_times[f"{s}_p2"] = float(legacy.green_times.get(f"{s}_p2", 0.0))


def copy_offset(candidate: ControlAction, legacy: ControlAction, cfg: ExperimentConfig, signal: str | None = None) -> None:
    signals = [signal] if signal is not None else list(cfg.network.signals)
    for s in signals:
        candidate.offsets[s] = float(legacy.offsets.get(s, 0.0))


def copy_ramp(candidate: ControlAction, legacy: ControlAction, cfg: ExperimentConfig, ramp: str | None = None) -> None:
    ramps = [ramp] if ramp is not None else list(cfg.network.ramps)
    for r in ramps:
        candidate.ramp_metering[r] = float(legacy.ramp_metering.get(r, candidate.ramp_metering.get(r, 0.0)))


def copy_vsl(candidate: ControlAction, legacy: ControlAction, cfg: ExperimentConfig, link: str | None = None) -> None:
    links = [link] if link is not None else list(cfg.network.freeway_links)
    for freeway_link in links:
        candidate.vsl[freeway_link] = float(legacy.vsl.get(freeway_link, candidate.vsl.get(freeway_link, 100.0)))
        for i in range(cfg.network.freeway_segments_per_link):
            key = f"{freeway_link}__seg{i}"
            candidate.vsl[key] = float(legacy.vsl.get(key, segment_vsl(legacy, freeway_link, i, cfg)))


def summarize_delta(candidate: ControlAction, base_control: ControlAction, legacy: ControlAction, cfg: ExperimentConfig) -> dict[str, float]:
    net = cfg.network
    return {
        "ramp_sum": float(sum(candidate.ramp_metering.get(r, 0.0) for r in net.ramps)),
        "ramp_delta_vs_base": float(
            sum(candidate.ramp_metering.get(r, 0.0) - base_control.ramp_metering.get(r, 0.0) for r in net.ramps)
        ),
        "ramp_l1_to_legacy": float(
            sum(abs(candidate.ramp_metering.get(r, 0.0) - legacy.ramp_metering.get(r, 0.0)) for r in net.ramps)
        ),
        "vsl_segment_mean": float(
            sum(
                segment_vsl(candidate, link, i, cfg)
                for link in net.freeway_links
                for i in range(net.freeway_segments_per_link)
            )
            / max(len(net.freeway_links) * net.freeway_segments_per_link, 1)
        ),
        "vsl_segment_l1_to_legacy": float(
            sum(
                abs(segment_vsl(candidate, link, i, cfg) - segment_vsl(legacy, link, i, cfg))
                for link in net.freeway_links
                for i in range(net.freeway_segments_per_link)
            )
        ),
        "green_p1_sum": float(sum(candidate.green_times.get(f"{s}_p1", 0.0) for s in net.signals)),
        "green_l1_to_legacy": float(
            sum(abs(candidate.green_times.get(f"{s}_p1", 0.0) - legacy.green_times.get(f"{s}_p1", 0.0)) for s in net.signals)
        ),
        "offset_l1_to_legacy": float(
            sum(abs(candidate.offsets.get(s, 0.0) - legacy.offsets.get(s, 0.0)) for s in net.signals)
        ),
    }


def run_variant(
    cfg: ExperimentConfig,
    sim: Any,
    forecast: list[Any],
    step: int,
    state_source: str,
    base_control: ControlAction,
    legacy_control: ControlAction,
    label: str,
    mutate: Callable[[ControlAction], None],
    base_ttt: float,
    legacy_ttt: float,
    pfo_ttt: float,
) -> dict[str, Any]:
    candidate = base_control.copy()
    mutate(candidate)
    ttt = base.rollout_ttt(cfg, sim, candidate, forecast)
    return {
        "step": step,
        "time_sec": step * cfg.simulation.control_interval,
        "state_source": state_source,
        "variant": label,
        "rollout_ttt": float(ttt),
        "delta_vs_current_response": float(ttt - base_ttt),
        "delta_vs_legacy": float(ttt - legacy_ttt),
        "delta_vs_saved_pfo": float(ttt - pfo_ttt),
        **summarize_delta(candidate, base_control, legacy_control, cfg),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="sweet_190")
    parser.add_argument("--T-total", type=float, default=7200.0)
    parser.add_argument("--steps", default="20,35")
    parser.add_argument("--np-mode", choices=["cap", "equality"], default="cap")
    parser.add_argument(
        "--data-root",
        default=r"C:\Users\alsrj\Documents\Numerical Simulation",
        help="Root containing historical outputs.",
    )
    parser.add_argument("--current-run", default="outputs/joint_wu_faithful_sweet190_7200_20260706")
    parser.add_argument("--legacy-run", default="outputs/legacy_pstack_sweet190_7200_20260702")
    parser.add_argument("--output", default="outputs/legacy_direction_ablation_probe_sweet190_step20_35_20260706")
    parser.add_argument("--state-source", choices=["legacy", "pfo", "both"], default="legacy")
    args = parser.parse_args()

    cfg, scenario = build_cfg(args.scenario, args.T_total, args.np_mode)
    data_root = Path(args.data_root)
    legacy_rows = base.read_csv(
        data_root / args.legacy_run / "runs" / args.scenario / "LEGACY-STACKELBERG" / "control_timeseries.csv"
    )
    pfo_rows = base.read_csv(
        data_root / args.current_run / "runs" / args.scenario / "PROPOSED-FOLLOWERS-ONLY" / "control_timeseries.csv"
    )
    steps = [int(value.strip()) for value in args.steps.split(",") if value.strip()]
    rows: list[dict[str, Any]] = []
    response_rows: list[dict[str, Any]] = []

    for step in steps:
        pfo_sim, pfo_forecast, _ = base.replay_to_step(cfg, scenario, pfo_rows, step)
        legacy_sim, legacy_forecast, _ = base.replay_to_step(cfg, scenario, legacy_rows, step)
        sources = []
        if args.state_source in ("legacy", "both"):
            sources.append(("legacy_replayed_state", legacy_sim, legacy_forecast))
        if args.state_source in ("pfo", "both"):
            sources.append(("pfo_replayed_state", pfo_sim, pfo_forecast))
        for state_source, sim, forecast in sources:
            legacy_current = base.control_from_row(legacy_rows[step], cfg)
            saved_pfo_current = base.control_from_row(pfo_rows[step], cfg)
            leader = LeaderAction(float(legacy_current.N_P_star), float(legacy_current.N_UF_star))
            solver = WuFaithfulFollower(cfg)
            start = time.perf_counter()
            result = solver.solve(sim.state.copy(), leader, forecast, legacy_current)
            solve_time = time.perf_counter() - start
            response = result.control
            response_ttt = base.rollout_ttt(cfg, sim, response, forecast)
            legacy_ttt = base.rollout_ttt(cfg, sim, legacy_current, forecast)
            pfo_ttt = base.rollout_ttt(cfg, sim, saved_pfo_current, forecast)
            response_rows.append({
                "step": step,
                "time_sec": step * cfg.simulation.control_interval,
                "state_source": state_source,
                "response_ttt": float(response_ttt),
                "legacy_ttt": float(legacy_ttt),
                "saved_pfo_ttt": float(pfo_ttt),
                "response_minus_legacy": float(response_ttt - legacy_ttt),
                "response_minus_pfo": float(response_ttt - pfo_ttt),
                "solve_time_sec": float(solve_time),
                "iterations": float(result.iterations),
                "converged": float(result.converged),
                **summarize_delta(response, response, legacy_current, cfg),
            })

            variants: list[tuple[str, Callable[[ControlAction], None]]] = [
                ("legacy_green_all", lambda c: copy_green(c, legacy_current, cfg)),
                ("legacy_offset_all", lambda c: copy_offset(c, legacy_current, cfg)),
                ("legacy_green_offset_all", lambda c: (copy_green(c, legacy_current, cfg), copy_offset(c, legacy_current, cfg))),
                ("legacy_ramp_all", lambda c: copy_ramp(c, legacy_current, cfg)),
                ("legacy_vsl_all", lambda c: copy_vsl(c, legacy_current, cfg)),
                ("legacy_ramp_vsl_all", lambda c: (copy_ramp(c, legacy_current, cfg), copy_vsl(c, legacy_current, cfg))),
                ("legacy_all_controls", lambda c: (
                    copy_green(c, legacy_current, cfg),
                    copy_offset(c, legacy_current, cfg),
                    copy_ramp(c, legacy_current, cfg),
                    copy_vsl(c, legacy_current, cfg),
                )),
            ]
            for signal in cfg.network.signals:
                variants.append((f"legacy_green_{signal}", lambda c, s=signal: copy_green(c, legacy_current, cfg, s)))
                variants.append((f"legacy_offset_{signal}", lambda c, s=signal: copy_offset(c, legacy_current, cfg, s)))
                variants.append((f"legacy_green_offset_{signal}", lambda c, s=signal: (
                    copy_green(c, legacy_current, cfg, s),
                    copy_offset(c, legacy_current, cfg, s),
                )))
            for ramp in cfg.network.ramps:
                variants.append((f"legacy_ramp_{ramp}", lambda c, r=ramp: copy_ramp(c, legacy_current, cfg, r)))
            for link in cfg.network.freeway_links:
                variants.append((f"legacy_vsl_{link}", lambda c, l=link: copy_vsl(c, legacy_current, cfg, l)))

            for label, mutate in variants:
                rows.append(
                    run_variant(
                        cfg,
                        sim,
                        forecast,
                        step,
                        state_source,
                        response,
                        legacy_current,
                        label,
                        mutate,
                        response_ttt,
                        legacy_ttt,
                        pfo_ttt,
                    )
                )

    out = data_root / args.output
    write_csv(out / "response_summary.csv", response_rows)
    write_csv(out / "ablation_variants.csv", rows)
    (out / "response_summary.json").write_text(json.dumps(response_rows, indent=2), encoding="utf-8")
    print(json.dumps({"response": response_rows, "variant_count": len(rows)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
