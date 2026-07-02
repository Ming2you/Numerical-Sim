from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.baseline import baseline_control
from src.simulation.simulator import MixedTrafficSimulator


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _float(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, "")
        if value == "" or value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def control_from_row(row: dict[str, str], cfg: ExperimentConfig) -> ControlAction:
    control = ControlAction.uncontrolled(cfg)
    control.N_P_star = _float(row, "N_P_star")
    control.N_UF_star = _float(row, "N_UF_star")
    for ramp in cfg.network.ramps:
        control.ramp_metering[ramp] = _float(
            row, f"ramp_metering_{ramp}", control.ramp_metering.get(ramp, 0.0)
        )
    for link in cfg.network.freeway_links:
        control.vsl[link] = _float(row, f"vsl_{link}", control.vsl.get(link, 100.0))
        for i in range(cfg.network.freeway_segments_per_link):
            key = f"{link}__seg{i}"
            control.vsl[key] = _float(row, f"vsl_{link}_seg{i}", control.vsl[link])
    for signal in cfg.network.signals:
        control.green_times[f"{signal}_p1"] = _float(
            row, f"green_{signal}_p1", control.green_times.get(f"{signal}_p1", 0.0)
        )
        control.green_times[f"{signal}_p2"] = _float(
            row, f"green_{signal}_p2", control.green_times.get(f"{signal}_p2", 0.0)
        )
        control.offsets[signal] = _float(
            row, f"offset_{signal}", control.offsets.get(signal, 0.0)
        )
    return control


def random_control(cfg: ExperimentConfig, rng: random.Random) -> ControlAction:
    control = ControlAction.uncontrolled(cfg)
    net = cfg.network
    vsl_set = list(cfg.freeway_follower.vsl_set)
    for signal in net.signals:
        p1 = rng.uniform(net.green_min, net.green_max)
        p2 = net.effective_green_total - p1
        if p2 < net.green_min:
            p2 = net.green_min
            p1 = net.effective_green_total - p2
        if p2 > net.green_max:
            p2 = net.green_max
            p1 = net.effective_green_total - p2
        control.green_times[f"{signal}_p1"] = float(p1)
        control.green_times[f"{signal}_p2"] = float(p2)
        control.offsets[signal] = float(rng.choice([0.0, 20.0, 40.0, 60.0, 80.0, 100.0]))
    for link in net.freeway_links:
        vsl = float(rng.choice(vsl_set))
        control.vsl[link] = vsl
        for i in range(net.freeway_segments_per_link):
            control.vsl[f"{link}__seg{i}"] = vsl
    return control


def control_distance(
    candidate: ControlAction,
    legacy: ControlAction,
    cfg: ExperimentConfig,
) -> dict[str, float]:
    net = cfg.network
    ramp_diff = sum(
        abs(candidate.ramp_metering.get(r, 0.0) - legacy.ramp_metering.get(r, 0.0))
        for r in net.ramps
    )
    vsl_diff = sum(
        abs(candidate.vsl.get(link, 100.0) - legacy.vsl.get(link, 100.0))
        for link in net.freeway_links
    )
    green_diff = sum(
        abs(candidate.green_times.get(f"{s}_p1", 0.0) - legacy.green_times.get(f"{s}_p1", 0.0))
        for s in net.signals
    )
    offset_diff = sum(
        abs(candidate.offsets.get(s, 0.0) - legacy.offsets.get(s, 0.0))
        for s in net.signals
    )
    return {
        "distance_ramp_sum": float(ramp_diff),
        "distance_vsl_link_sum": float(vsl_diff),
        "distance_green_p1_sum": float(green_diff),
        "distance_offset_sum": float(offset_diff),
        "distance_composite": float(ramp_diff + 10.0 * vsl_diff + 20.0 * green_diff + 5.0 * offset_diff),
    }


def build_cfg(scenario_name: str, t_total: float) -> tuple[ExperimentConfig, Any]:
    overrides = {
        "mpc": {
            "relaxed_quantized_controls": True,
            "grid_parallel_backend": "serial",
            "leader_search_mode": "grid",
            "stackelberg_leader_parallel_backend": "serial",
        },
        "simulation": {"T_total": float(t_total)},
    }
    cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), overrides)
    scenario = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))[scenario_name]
    cfg = apply_scenario_network_overrides(cfg, scenario)
    return cfg, scenario


def run_pfo_until_targets(
    cfg: ExperimentConfig,
    scenario: Any,
    target_steps: set[int],
) -> dict[int, tuple[MixedTrafficSimulator, list[Any], Optional[ControlAction]]]:
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    follower = WuFaithfulFollower(cfg)
    previous: Optional[ControlAction] = None
    snapshots: dict[int, tuple[MixedTrafficSimulator, list[Any], Optional[ControlAction]]] = {}
    max_step = max(target_steps)
    for step in range(max_step + 1):
        forecast = profile.horizon(step * cfg.simulation.control_interval, cfg.mpc.horizon_steps)
        if step in target_steps:
            snapshots[step] = (sim.copy(), list(forecast), previous.copy() if previous else None)
        result = follower.solve(sim.state.copy(), None, forecast, previous)
        control = result.control
        sim.step(control, forecast[0], step)
        previous = control.copy()
    return snapshots


def evaluate_one_step_ttt(
    sim_snapshot: MixedTrafficSimulator,
    control: ControlAction,
    demand: Any,
    step: int,
) -> float:
    sim = sim_snapshot.copy()
    log = sim.step(control, demand, step)
    return float(log.freeway_ttt + log.urban_ttt)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="sweet_190")
    parser.add_argument("--T-total", type=float, default=7200.0)
    parser.add_argument("--steps", default="0,10,20,21,26,35,39")
    parser.add_argument("--random-starts", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", default="outputs/pfo_legacy_multistart_sweet190_20260702")
    args = parser.parse_args()

    cfg, scenario = build_cfg(args.scenario, args.T_total)
    pfo_rows = _read_csv(
        ROOT / "outputs/sweet190_all_boundary_halfcap_7200_20260701/runs/sweet_190/PROPOSED-FOLLOWERS-ONLY/control_timeseries.csv"
    )
    legacy_rows = _read_csv(
        ROOT / "outputs/legacy_pstack_sweet190_7200_20260702/runs/sweet_190/LEGACY-STACKELBERG/control_timeseries.csv"
    )
    target_steps = {int(s.strip()) for s in args.steps.split(",") if s.strip()}
    snapshots = run_pfo_until_targets(cfg, scenario, target_steps)
    rng = random.Random(args.seed)
    rows: list[dict[str, Any]] = []

    for step in sorted(target_steps):
        sim_snapshot, forecast, pfo_previous = snapshots[step]
        legacy_current = control_from_row(legacy_rows[step], cfg)
        legacy_previous = (
            control_from_row(legacy_rows[step - 1], cfg)
            if step > 0
            else ControlAction.uncontrolled(cfg)
        )
        saved_pfo_current = control_from_row(pfo_rows[step], cfg)
        saved_pfo_previous = (
            control_from_row(pfo_rows[step - 1], cfg)
            if step > 0
            else ControlAction.uncontrolled(cfg)
        )
        seeds: list[tuple[str, ControlAction]] = [
            ("pfo_runtime_previous", pfo_previous.copy() if pfo_previous else ControlAction.uncontrolled(cfg)),
            ("saved_pfo_previous", saved_pfo_previous),
            ("default_uncontrolled", ControlAction.uncontrolled(cfg)),
            ("legacy_previous", legacy_previous),
            ("legacy_current_as_seed", legacy_current),
        ]
        for i in range(args.random_starts):
            seeds.append((f"random_{i:02d}", random_control(cfg, rng)))

        for seed_name, previous in seeds:
            solver = WuFaithfulFollower(cfg)
            t0 = time.perf_counter()
            result = solver.solve(sim_snapshot.state.copy(), None, forecast, previous)
            solve_time = time.perf_counter() - t0
            control = result.control
            distance = control_distance(control, legacy_current, cfg)
            one_step_ttt = evaluate_one_step_ttt(sim_snapshot, control, forecast[0], step)
            pfo_distance = control_distance(saved_pfo_current, legacy_current, cfg)
            rows.append({
                "step": step,
                "time_sec": step * cfg.simulation.control_interval,
                "seed_name": seed_name,
                "one_step_ttt": one_step_ttt,
                "solve_time_sec": solve_time,
                "legacy_one_step_ttt": evaluate_one_step_ttt(sim_snapshot, legacy_current, forecast[0], step),
                "saved_pfo_one_step_ttt": evaluate_one_step_ttt(sim_snapshot, saved_pfo_current, forecast[0], step),
                "saved_pfo_distance_composite": pfo_distance["distance_composite"],
                "candidate_N_P_star": control.N_P_star,
                "candidate_N_UF_star": control.N_UF_star,
                "candidate_ramp_sum": sum(control.ramp_metering.get(r, 0.0) for r in cfg.network.ramps),
                "legacy_ramp_sum": sum(legacy_current.ramp_metering.get(r, 0.0) for r in cfg.network.ramps),
                "saved_pfo_ramp_sum": sum(saved_pfo_current.ramp_metering.get(r, 0.0) for r in cfg.network.ramps),
                "candidate_vsl_mean": mean(control.vsl.get(link, 100.0) for link in cfg.network.freeway_links),
                "legacy_vsl_mean": mean(legacy_current.vsl.get(link, 100.0) for link in cfg.network.freeway_links),
                "saved_pfo_vsl_mean": mean(saved_pfo_current.vsl.get(link, 100.0) for link in cfg.network.freeway_links),
                "candidate_green_spread": max(control.green_times.get(f"{s}_p1", 0.0) for s in cfg.network.signals)
                - min(control.green_times.get(f"{s}_p1", 0.0) for s in cfg.network.signals),
                "legacy_green_spread": max(legacy_current.green_times.get(f"{s}_p1", 0.0) for s in cfg.network.signals)
                - min(legacy_current.green_times.get(f"{s}_p1", 0.0) for s in cfg.network.signals),
                "offset_active_count": sum(1 for s in cfg.network.signals if abs(control.offsets.get(s, 0.0)) > 1.0e-6),
                **distance,
            })

    out = ROOT / args.output
    _write_csv(out / "multistart_results.csv", rows)
    summary_rows: list[dict[str, Any]] = []
    for step in sorted(target_steps):
        step_rows = [row for row in rows if int(row["step"]) == step]
        best_ttt = min(step_rows, key=lambda row: float(row["one_step_ttt"]))
        best_dist = min(step_rows, key=lambda row: float(row["distance_composite"]))
        runtime = next(row for row in step_rows if row["seed_name"] == "pfo_runtime_previous")
        summary_rows.append({
            "step": step,
            "best_ttt_seed": best_ttt["seed_name"],
            "best_ttt": best_ttt["one_step_ttt"],
            "runtime_ttt": runtime["one_step_ttt"],
            "legacy_action_ttt": runtime["legacy_one_step_ttt"],
            "saved_pfo_action_ttt": runtime["saved_pfo_one_step_ttt"],
            "best_dist_seed": best_dist["seed_name"],
            "best_distance": best_dist["distance_composite"],
            "runtime_distance": runtime["distance_composite"],
            "saved_pfo_distance": runtime["saved_pfo_distance_composite"],
            "legacy_ramp_sum": runtime["legacy_ramp_sum"],
            "runtime_ramp_sum": runtime["candidate_ramp_sum"],
            "saved_pfo_ramp_sum": runtime["saved_pfo_ramp_sum"],
        })
    _write_csv(out / "multistart_summary.csv", summary_rows)
    (out / "summary.json").write_text(json.dumps(summary_rows, indent=2), encoding="utf-8")
    print(json.dumps(summary_rows, indent=2), flush=True)


if __name__ == "__main__":
    main()
