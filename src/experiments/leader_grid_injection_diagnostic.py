from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np

from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.leader import LeaderAction
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _clip_action(action: LeaderAction, bounds: Any) -> LeaderAction:
    return LeaderAction(
        float(np.clip(action.N_P_star, bounds.np_lower, bounds.np_upper)),
        float(np.clip(action.N_UF_star, bounds.nuf_lower, bounds.nuf_upper)),
    )


def _unique_actions(rows: Iterable[Tuple[str, LeaderAction]], bounds: Any) -> List[Tuple[str, LeaderAction]]:
    seen: set[tuple[float, float]] = set()
    out: List[Tuple[str, LeaderAction]] = []
    for label, action in rows:
        clipped = _clip_action(action, bounds)
        key = (round(float(clipped.N_P_star), 6), round(float(clipped.N_UF_star), 6))
        if key in seen:
            continue
        seen.add(key)
        out.append((label, clipped))
    return out


def _reverse_leader_action(
    coordinator: DistributedCoordinator,
    state: Any,
    forecast: list[Any],
    control: ControlAction,
) -> tuple[LeaderAction, Dict[str, float]]:
    rm_sum = float(sum(control.ramp_metering.get(ramp, 0.0) for ramp in coordinator.cfg.network.ramps))
    dummy = LeaderAction(0.0, rm_sum)
    diag = coordinator._leader_direct_feasible_set_diagnostics(
        state.copy(),
        control.copy(),
        forecast,
        dummy,
    )
    action = LeaderAction(
        float(diag.get("distributed_grid_leader_projected_net_inflow_veh", 0.0)),
        rm_sum,
    )
    return action, diag


def _plant_one_step(cfg: ExperimentConfig, control: ControlAction, current_demand: Any) -> Dict[str, float]:
    sim = MixedTrafficSimulator(cfg)
    log = sim.step(control.copy(), current_demand, 0)
    net = cfg.network
    return {
        "total_ttt": float(log.freeway_ttt + log.urban_ttt),
        "urban_ttt": float(log.urban_ttt),
        "freeway_ttt": float(log.freeway_ttt),
        "terminal_urban_vehicles": float(sim.state.total_urban_vehicles(net)),
        "terminal_freeway_vehicles": float(sim.state.total_freeway_vehicles(net)),
        "terminal_total_vehicles": float(sim.state.total_urban_vehicles(net) + sim.state.total_freeway_vehicles(net)),
    }


def _candidate_rows(evaluations: list[Any], labels: Dict[int, str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in sorted(evaluations, key=lambda value: float(value.objective)):
        diag = dict(item.nash.diagnostics)
        diag.update(item.nash.control.diagnostics)
        rows.append({
            "rank": len(rows) + 1,
            "index": int(item.index),
            "label": labels.get(int(item.index), ""),
            "stage": item.stage,
            "N_P_star": float(item.action.N_P_star),
            "N_UF_star": float(item.action.N_UF_star),
            "leader_objective": float(item.objective),
            "leader_base": float(item.objective_terms.get("leader_objective_base", 0.0)),
            "leader_target_penalty": float(item.objective_terms.get("leader_target_penalty", 0.0)),
            "leader_boundary_penalty": float(item.objective_terms.get("leader_boundary_in_queue_penalty", 0.0)),
            "leader_density_penalty": float(item.objective_terms.get("leader_density_penalty", 0.0)),
            "leader_smoothness_penalty": float(item.objective_terms.get("leader_smoothness_penalty", 0.0)),
            "rollout_ttt": float(diag.get("distributed_response_rollout_ttt", 0.0)),
            "rollout_urban_ttt": float(diag.get("distributed_response_rollout_urban_ttt", 0.0)),
            "rollout_freeway_ttt": float(diag.get("distributed_response_rollout_freeway_ttt", 0.0)),
            "rollout_terminal_vehicles": float(diag.get("distributed_response_terminal_rollout_vehicles", 0.0)),
            "projected_net_inflow_veh": float(
                diag.get("distributed_grid_leader_projected_net_inflow_veh", 0.0)
            ),
            "net_inflow_residual_veh": float(
                diag.get("distributed_grid_leader_net_inflow_residual_veh", 0.0)
            ),
            "metering_sum_veh_h": float(
                diag.get("distributed_grid_leader_selected_metering_sum_veh_h", 0.0)
                or sum(item.nash.control.ramp_metering.get(ramp, 0.0) for ramp in item.nash.control.ramp_metering)
            ),
            "early_terminated": float(diag.get("distributed_grid_early_terminated", 0.0)),
        })
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="src/config/default.yaml")
    parser.add_argument("--scenarios-config", default="src/config/scenarios.yaml")
    parser.add_argument("--scenario", default="medium_demand")
    parser.add_argument("--output", required=True)
    parser.add_argument("--T-total", type=float, default=180.0)
    parser.add_argument("--max-nash-iter", type=int, default=1)
    parser.add_argument("--np-step", type=float, default=40.0)
    parser.add_argument("--nuf-step", type=float, default=500.0)
    args = parser.parse_args(argv)

    overrides = {
        "simulation": {"T_total": float(args.T_total)},
        "mpc": {
            "relaxed_quantized_controls": True,
            "max_nash_iter": int(args.max_nash_iter),
            "stackelberg_enable_fallback": False,
            "stackelberg_prefilter_top_k": 0,
            "stackelberg_prefilter_local_top_k": 0,
            "stackelberg_leader_parallel_backend": "thread",
            "stackelberg_leader_parallel_max_workers": 4,
            "grid_parallel_backend": "thread",
            "grid_parallel_max_workers": 4,
            "grid_parallel_chunk_size": 8,
        },
        "freeway_follower": {"freeway_prediction_horizon_steps": 3},
    }
    base_cfg = ExperimentConfig.from_file(args.config, overrides)
    scenarios = load_scenarios(args.scenarios_config)
    if args.scenario not in scenarios:
        raise SystemExit(f"Unknown scenario: {args.scenario}")
    cfg = apply_scenario_network_overrides(base_cfg.with_updates({}), scenarios[args.scenario])
    # Match the production PROPOSED-STACKELBERG adapter: the leader must
    # evaluate distributed follower responses, not the legacy two-block solver.
    cfg.mpc.follower_solver_mode = "distributed"
    demand = DemandProfile(cfg, scenarios[args.scenario])
    current_demand = demand.at(0.0)
    forecast = demand.horizon(0.0, cfg.mpc.horizon_steps)
    state = MixedTrafficSimulator(cfg).state.copy()

    coordinator = DistributedCoordinator(cfg)
    previous = StackelbergMPCController(cfg)._normalize_previous_leader_reference(ControlAction.fixed(cfg))

    no_control = ControlAction.uncontrolled(cfg)
    no_action, no_diag = _reverse_leader_action(coordinator, state, forecast, no_control)

    pfo_nash = coordinator.solve(state.copy(), None, forecast, ControlAction.uncontrolled(cfg))
    pfo_control = pfo_nash.control.copy()
    pfo_action, pfo_diag = _reverse_leader_action(coordinator, state, forecast, pfo_control)

    controller = StackelbergMPCController(cfg)
    bounds = controller.leader._candidate_bounds(state, previous, current_demand, forecast)

    raw_candidates: List[Tuple[str, LeaderAction]] = [
        ("reverse_no_control_exact", no_action),
        ("reverse_pfo_exact", pfo_action),
        ("previous_default_exact", LeaderAction(previous.N_P_star, previous.N_UF_star)),
        ("old_high_release_anchor", LeaderAction(0.0, cfg.network.total_ramp_capacity)),
    ]
    for center_label, center in (("no_control", no_action), ("pfo", pfo_action)):
        for delta_np in (-2.0 * args.np_step, -args.np_step, args.np_step, 2.0 * args.np_step):
            raw_candidates.append((
                f"{center_label}_np_{delta_np:+.0f}",
                LeaderAction(center.N_P_star + delta_np, center.N_UF_star),
            ))
        for delta_nuf in (-2.0 * args.nuf_step, -args.nuf_step, args.nuf_step, 2.0 * args.nuf_step):
            raw_candidates.append((
                f"{center_label}_nuf_{delta_nuf:+.0f}",
                LeaderAction(center.N_P_star, center.N_UF_star + delta_nuf),
            ))

    candidates_with_labels = _unique_actions(raw_candidates, bounds)
    candidates = [action for _label, action in candidates_with_labels]
    labels = {idx: label for idx, (label, _action) in enumerate(candidates_with_labels)}

    print(
        "LEADER_GRID_INJECTION_START "
        f"scenario={args.scenario} "
        f"follower_solver={cfg.mpc.follower_solver_mode} "
        f"candidates={len(candidates)} "
        f"no_control_N_P={no_action.N_P_star:.3f} "
        f"no_control_N_UF={no_action.N_UF_star:.3f} "
        f"pfo_N_P={pfo_action.N_P_star:.3f} "
        f"pfo_N_UF={pfo_action.N_UF_star:.3f}",
        flush=True,
    )
    start = time.perf_counter()
    evaluations = controller._evaluate_candidate_set(
        candidates,
        list(range(len(candidates))),
        state.copy(),
        forecast,
        previous,
        stage="tight_injected",
        incumbent_obj=float("inf"),
    )
    elapsed = time.perf_counter() - start
    rows = _candidate_rows(evaluations, labels)
    best_eval = min(evaluations, key=lambda item: item.objective)
    selected_control = best_eval.nash.control.copy()
    selected_metrics = _plant_one_step(cfg, selected_control, current_demand)
    no_metrics = _plant_one_step(cfg, no_control, current_demand)
    pfo_metrics = _plant_one_step(cfg, pfo_control, current_demand)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(out / "candidate_table.csv", rows)
    summary = {
        "scenario": args.scenario,
        "T_total": float(args.T_total),
        "candidate_count": len(candidates),
        "evaluation_wall_time_sec": round(elapsed, 3),
        "bounds": {
            "np_lower": float(bounds.np_lower),
            "np_upper": float(bounds.np_upper),
            "nuf_lower": float(bounds.nuf_lower),
            "nuf_upper": float(bounds.nuf_upper),
        },
        "reverse_no_control": {
            "N_P_star": float(no_action.N_P_star),
            "N_UF_star": float(no_action.N_UF_star),
            "projected_inflow_veh": float(no_diag.get("distributed_grid_leader_projected_inflow_veh", 0.0)),
            "projected_outflow_veh": float(no_diag.get("distributed_grid_leader_projected_outflow_veh", 0.0)),
            "plant": no_metrics,
        },
        "reverse_pfo": {
            "N_P_star": float(pfo_action.N_P_star),
            "N_UF_star": float(pfo_action.N_UF_star),
            "projected_inflow_veh": float(pfo_diag.get("distributed_grid_leader_projected_inflow_veh", 0.0)),
            "projected_outflow_veh": float(pfo_diag.get("distributed_grid_leader_projected_outflow_veh", 0.0)),
            "plant": pfo_metrics,
            "pfo_response_objective": float(pfo_nash.objective_value),
        },
        "selected": {
            "label": labels.get(int(best_eval.index), ""),
            "index": int(best_eval.index),
            "N_P_star": float(best_eval.action.N_P_star),
            "N_UF_star": float(best_eval.action.N_UF_star),
            "leader_objective": float(best_eval.objective),
            "plant": selected_metrics,
        },
        "selected_reverse_no_control": labels.get(int(best_eval.index), "") == "reverse_no_control_exact",
        "selected_reverse_pfo": labels.get(int(best_eval.index), "") == "reverse_pfo_exact",
        "top_rows": rows[: min(8, len(rows))],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        "LEADER_GRID_INJECTION "
        f"scenario={args.scenario} candidates={len(candidates)} "
        f"follower_solver={cfg.mpc.follower_solver_mode} "
        f"selected={summary['selected']['label']} "
        f"N_P={summary['selected']['N_P_star']:.3f} "
        f"N_UF={summary['selected']['N_UF_star']:.3f} "
        f"leader_obj={summary['selected']['leader_objective']:.3f} "
        f"plant_ttt={summary['selected']['plant']['total_ttt']:.3f} "
        f"output={out}"
    )


if __name__ == "__main__":
    main()
