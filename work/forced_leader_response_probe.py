from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.controllers.leader import LeaderAction
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.coupling import run_coupled_interval


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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


def f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, "")
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def control_from_row(row: dict[str, str], cfg: ExperimentConfig) -> ControlAction:
    control = ControlAction.uncontrolled(cfg)
    control.N_P_star = f(row, "N_P_star")
    control.N_UF_star = f(row, "N_UF_star")
    for ramp in cfg.network.ramps:
        control.ramp_metering[ramp] = f(row, f"ramp_metering_{ramp}", control.ramp_metering[ramp])
    for link in cfg.network.freeway_links:
        control.vsl[link] = f(row, f"vsl_{link}", control.vsl[link])
        for i in range(cfg.network.freeway_segments_per_link):
            control.vsl[f"{link}__seg{i}"] = f(row, f"vsl_{link}_seg{i}", control.vsl[link])
    for signal in cfg.network.signals:
        control.green_times[f"{signal}_p1"] = f(row, f"green_{signal}_p1", control.green_times[f"{signal}_p1"])
        control.green_times[f"{signal}_p2"] = f(row, f"green_{signal}_p2", control.green_times[f"{signal}_p2"])
        control.offsets[signal] = f(row, f"offset_{signal}", control.offsets[signal])
    return control


def build_cfg(scenario_name: str, t_total: float, np_mode: str) -> tuple[ExperimentConfig, Any]:
    overrides = {
        "mpc": {
            "relaxed_quantized_controls": True,
            "grid_parallel_backend": "serial",
            "leader_search_mode": "grid",
            "stackelberg_leader_parallel_backend": "serial",
            "wu_faithful_np_coordination_mode": np_mode,
        },
        "simulation": {"T_total": float(t_total)},
    }
    cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), overrides)
    scenario = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))[scenario_name]
    return apply_scenario_network_overrides(cfg, scenario), scenario


def replay_to_step(
    cfg: ExperimentConfig,
    scenario: Any,
    controls: list[dict[str, str]],
    target_step: int,
) -> tuple[MixedTrafficSimulator, list[Any], Optional[ControlAction]]:
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    previous: Optional[ControlAction] = None
    for step in range(target_step):
        demand = profile.at(step * cfg.simulation.control_interval)
        control = control_from_row(controls[step], cfg)
        sim.step(control, demand, step)
        previous = control.copy()
    forecast = profile.horizon(target_step * cfg.simulation.control_interval, cfg.mpc.horizon_steps)
    return sim, list(forecast), previous


def rollout_ttt(cfg: ExperimentConfig, sim: MixedTrafficSimulator, control: ControlAction, forecast: list[Any]) -> float:
    state = sim.state.copy()
    freeway_ttt = 0.0
    urban_ttt = 0.0
    for demand in forecast[: max(1, cfg.mpc.horizon_steps)]:
        result = run_coupled_interval(state, control, demand, cfg)
        state.time_sec += cfg.simulation.control_interval
        freeway_ttt += float(result.freeway_ttt)
        urban_ttt += float(result.urban_ttt)
    return float(freeway_ttt + urban_ttt)


def one_step_ttt(sim: MixedTrafficSimulator, control: ControlAction, demand: Any, step: int) -> float:
    probe = sim.copy()
    log = probe.step(control, demand, step)
    return float(log.freeway_ttt + log.urban_ttt)


def distances(candidate: ControlAction, legacy: ControlAction, cfg: ExperimentConfig) -> dict[str, float]:
    net = cfg.network
    ramp = sum(abs(candidate.ramp_metering.get(r, 0.0) - legacy.ramp_metering.get(r, 0.0)) for r in net.ramps)
    vsl = sum(abs(candidate.vsl.get(link, 100.0) - legacy.vsl.get(link, 100.0)) for link in net.freeway_links)
    green = sum(abs(candidate.green_times.get(f"{s}_p1", 0.0) - legacy.green_times.get(f"{s}_p1", 0.0)) for s in net.signals)
    offset = sum(abs(candidate.offsets.get(s, 0.0) - legacy.offsets.get(s, 0.0)) for s in net.signals)
    return {
        "distance_ramp_sum": ramp,
        "distance_vsl_link_sum": vsl,
        "distance_green_p1_sum": green,
        "distance_offset_sum": offset,
        "distance_composite": ramp + 10.0 * vsl + 20.0 * green + 5.0 * offset,
    }


def summarize_control(prefix: str, control: ControlAction, cfg: ExperimentConfig) -> dict[str, float]:
    net = cfg.network
    return {
        f"{prefix}_ramp_sum": sum(control.ramp_metering.get(r, 0.0) for r in net.ramps),
        f"{prefix}_vsl_mean": mean(control.vsl.get(link, 100.0) for link in net.freeway_links),
        f"{prefix}_green_spread": (
            max(control.green_times.get(f"{s}_p1", 0.0) for s in net.signals)
            - min(control.green_times.get(f"{s}_p1", 0.0) for s in net.signals)
        ),
        f"{prefix}_offset_active_count": sum(1 for s in net.signals if abs(control.offsets.get(s, 0.0)) > 1.0e-6),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="sweet_190")
    parser.add_argument("--T-total", type=float, default=7200.0)
    parser.add_argument("--steps", default="20,21,26,35,39")
    parser.add_argument("--np-mode", choices=["cap", "equality"], default="cap")
    parser.add_argument("--output", default="outputs/forced_leader_response_probe_sweet190_20260702")
    args = parser.parse_args()

    cfg, scenario = build_cfg(args.scenario, args.T_total, args.np_mode)
    pfo_rows = read_csv(ROOT / "outputs/sweet190_all_boundary_halfcap_7200_20260701/runs/sweet_190/PROPOSED-FOLLOWERS-ONLY/control_timeseries.csv")
    legacy_rows = read_csv(ROOT / "outputs/legacy_pstack_sweet190_7200_20260702/runs/sweet_190/LEGACY-STACKELBERG/control_timeseries.csv")
    steps = [int(s.strip()) for s in args.steps.split(",") if s.strip()]
    output_rows: list[dict[str, Any]] = []

    for step in steps:
        pfo_sim, pfo_forecast, pfo_previous_replayed = replay_to_step(cfg, scenario, pfo_rows, step)
        legacy_sim, legacy_forecast, legacy_previous_replayed = replay_to_step(cfg, scenario, legacy_rows, step)
        for state_source, sim, forecast in (
            ("pfo_replayed_state", pfo_sim, pfo_forecast),
            ("legacy_replayed_state", legacy_sim, legacy_forecast),
        ):
            legacy_current = control_from_row(legacy_rows[step], cfg)
            saved_pfo_current = control_from_row(pfo_rows[step], cfg)
            seeds: list[tuple[str, Optional[ControlAction]]] = [
                ("default_uncontrolled", ControlAction.uncontrolled(cfg)),
                ("pfo_previous", control_from_row(pfo_rows[step - 1], cfg) if step > 0 else ControlAction.uncontrolled(cfg)),
                ("legacy_previous", control_from_row(legacy_rows[step - 1], cfg) if step > 0 else ControlAction.uncontrolled(cfg)),
                ("legacy_current", legacy_current),
            ]
            targets = [
                ("legacy_target", legacy_current.N_P_star, legacy_current.N_UF_star),
                ("high_release_6000", legacy_current.N_P_star, 6000.0),
                ("pfo_zero_target", saved_pfo_current.N_P_star, saved_pfo_current.N_UF_star),
            ]
            legacy_horizon = rollout_ttt(cfg, sim, legacy_current, forecast)
            pfo_horizon = rollout_ttt(cfg, sim, saved_pfo_current, forecast)
            legacy_step = one_step_ttt(sim, legacy_current, forecast[0], step)
            pfo_step = one_step_ttt(sim, saved_pfo_current, forecast[0], step)

            for target_name, n_p_star, n_uf_star in targets:
                leader = LeaderAction(float(n_p_star), float(n_uf_star))
                for seed_name, previous in seeds:
                    solver = WuFaithfulFollower(cfg)
                    start = time.perf_counter()
                    result = solver.solve(sim.state.copy(), leader, forecast, previous)
                    solve_time = time.perf_counter() - start
                    control = result.control
                    diag = result.diagnostics
                    ramp_sum = sum(control.ramp_metering.get(r, 0.0) for r in cfg.network.ramps)
                    row: dict[str, Any] = {
                        "step": step,
                        "time_sec": step * cfg.simulation.control_interval,
                        "np_mode": args.np_mode,
                        "state_source": state_source,
                        "target_name": target_name,
                        "seed_name": seed_name,
                        "target_N_P_star": float(n_p_star),
                        "target_N_UF_star": float(n_uf_star),
                        "response_objective_horizon_ttt": result.objective_value,
                        "response_one_step_ttt": one_step_ttt(sim, control, forecast[0], step),
                        "response_rollout_ttt_recomputed": rollout_ttt(cfg, sim, control, forecast),
                        "legacy_action_horizon_ttt": legacy_horizon,
                        "saved_pfo_action_horizon_ttt": pfo_horizon,
                        "legacy_action_one_step_ttt": legacy_step,
                        "saved_pfo_action_one_step_ttt": pfo_step,
                        "solve_time_sec": solve_time,
                        "response_ramp_sum": ramp_sum,
                        "response_N_UF_residual": float(n_uf_star - ramp_sum),
                        "response_N_P_realized": float(diag.get("wu_faithful_sum_nin", 0.0)),
                        "response_N_P_target_error": float(diag.get("wu_faithful_np_target_error_veh", 0.0)),
                        "response_lambda_P": float(diag.get("wu_faithful_lambda_P", 0.0)),
                        "response_local_evals": float(diag.get("wu_faithful_local_evals", 0.0)),
                        "response_converged": float(result.converged),
                        "response_iterations": float(result.iterations),
                        **summarize_control("response", control, cfg),
                        **summarize_control("legacy", legacy_current, cfg),
                        **summarize_control("saved_pfo", saved_pfo_current, cfg),
                        **distances(control, legacy_current, cfg),
                    }
                    output_rows.append(row)

    out = ROOT / args.output
    write_csv(out / f"forced_response_{args.np_mode}.csv", output_rows)
    summary_rows: list[dict[str, Any]] = []
    keys = sorted({(int(r["step"]), str(r["state_source"]), str(r["target_name"])) for r in output_rows})
    for step, state_source, target_name in keys:
        rows = [
            r for r in output_rows
            if int(r["step"]) == step and r["state_source"] == state_source and r["target_name"] == target_name
        ]
        best_obj = min(rows, key=lambda r: float(r["response_objective_horizon_ttt"]))
        best_step = min(rows, key=lambda r: float(r["response_one_step_ttt"]))
        best_dist = min(rows, key=lambda r: float(r["distance_composite"]))
        summary_rows.append({
            "step": step,
            "state_source": state_source,
            "target_name": target_name,
            "best_obj_seed": best_obj["seed_name"],
            "best_obj_response_horizon_ttt": best_obj["response_objective_horizon_ttt"],
            "best_step_seed": best_step["seed_name"],
            "best_step_response_one_step_ttt": best_step["response_one_step_ttt"],
            "best_dist_seed": best_dist["seed_name"],
            "best_distance": best_dist["distance_composite"],
            "best_dist_ramp_sum": best_dist["response_ramp_sum"],
            "legacy_ramp_sum": best_dist["legacy_ramp_sum"],
            "saved_pfo_ramp_sum": best_dist["saved_pfo_ramp_sum"],
            "legacy_horizon_ttt": best_dist["legacy_action_horizon_ttt"],
            "saved_pfo_horizon_ttt": best_dist["saved_pfo_action_horizon_ttt"],
        })
    write_csv(out / f"forced_response_summary_{args.np_mode}.csv", summary_rows)
    (out / f"summary_{args.np_mode}.json").write_text(json.dumps(summary_rows, indent=2), encoding="utf-8")
    print(json.dumps(summary_rows, indent=2), flush=True)


if __name__ == "__main__":
    main()
