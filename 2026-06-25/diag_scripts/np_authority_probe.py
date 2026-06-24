# N_P* 제어권한(authority) probe: 혼잡 state에서 N_UF* 고정·N_P* 스윕 시 realized rollout TTT가 움직이는지 측정.
"""leader의 urban 채널(N_P*)이 실제 제어권한을 갖는지 가르는 결정적 실험.

설계:
1. PFO(leader=None)로 K control-step warm-up → 혼잡 운전점 state 확보(cold free-flow가
   아니라 leader가 실제로 마주하는 상태).
2. 그 state에서 leader 후보를 N_UF* 고정값마다 N_P*만 도달박스 [np_lower, np_upper] 전체로
   스윕해 생성.
3. controller._evaluate_candidate_set로 각 후보의 *realized* rollout TTT(특히 urban)를 평가.
4. 각 고정 N_UF*에서 N_P* 스윕에 따른 rollout_urban_ttt/total 변동폭(spread)을 본다.
   - 변동 → N_P*에 권한 있음(box 타이트닝/사영 수정 가치 있음).
   - 평탄 → urban 채널 권한 거의 없음(soft/hard/projection 무의미 → 채널 재설계).
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.leader import LeaderAction
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig


def _warmup_state(cfg: ExperimentConfig, scenario: Any, k_steps: int):
    """PFO closed-loop을 k_steps 돌려 혼잡 state/previous/forecast/demand를 스냅샷한다."""
    from src.simulation.simulator import MixedTrafficSimulator

    demand = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    coordinator = DistributedCoordinator(cfg)
    previous: ControlAction | None = None
    for step in range(k_steps):
        current_demand = demand.at(sim.state.time_sec)
        forecast = demand.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
        nash = coordinator.solve(
            sim.state.copy(), None, forecast, previous or ControlAction.uncontrolled(cfg)
        )
        control = nash.control
        sim.step(control, current_demand, step)
        previous = control
    current_demand = demand.at(sim.state.time_sec)
    forecast = demand.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
    return sim.state.copy(), previous, current_demand, forecast


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="src/config/default.yaml")
    ap.add_argument("--scenarios-config", default="src/config/scenarios.yaml")
    ap.add_argument("--scenario", default="sweet_128")
    ap.add_argument("--warmup-steps", type=int, default=6)
    ap.add_argument("--np-count", type=int, default=13)
    ap.add_argument("--nuf-count", type=int, default=3)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)

    overrides = {
        "mpc": {
            "relaxed_quantized_controls": True,
            "stackelberg_enable_fallback": False,
            "stackelberg_leader_parallel_backend": "serial",
            "stackelberg_leader_parallel_max_workers": 1,
            "grid_parallel_backend": "serial",
            "stackelberg_allocation_mode": "direct",
        },
    }
    base_cfg = ExperimentConfig.from_file(args.config, overrides)
    scenarios = load_scenarios(args.scenarios_config)
    if args.scenario not in scenarios:
        raise SystemExit(f"Unknown scenario: {args.scenario}")
    scenario = scenarios[args.scenario]
    cfg = apply_scenario_network_overrides(base_cfg.with_updates({}), scenario)
    cfg.mpc.follower_solver_mode = "distributed"

    state, previous_warm, current_demand, forecast = _warmup_state(cfg, scenario, args.warmup_steps)

    controller = StackelbergMPCController(cfg)
    previous = controller._normalize_previous_leader_reference(
        previous_warm if previous_warm is not None else ControlAction.fixed(cfg)
    )
    bounds = controller.leader._candidate_bounds(state, previous, current_demand, forecast)

    np_lo, np_hi = float(bounds.np_lower), float(bounds.np_upper)
    nuf_lo, nuf_hi = float(bounds.nuf_lower), float(bounds.nuf_upper)
    np_values = list(np.linspace(np_lo, np_hi, max(2, args.np_count)))
    if args.nuf_count <= 1:
        nuf_values = [0.5 * (nuf_lo + nuf_hi)]
    else:
        nuf_values = list(np.linspace(nuf_lo, nuf_hi, args.nuf_count))

    candidates: List[LeaderAction] = []
    for nuf in nuf_values:
        for npv in np_values:
            candidates.append(LeaderAction(float(npv), float(nuf)))

    print(
        f"AUTHORITY_PROBE_START scenario={args.scenario} warmup={args.warmup_steps} "
        f"np_box=[{np_lo:.1f},{np_hi:.1f}] nuf_box=[{nuf_lo:.1f},{nuf_hi:.1f}] "
        f"candidates={len(candidates)} state_urban={state.total_urban_vehicles(cfg.network):.1f} "
        f"state_freeway={state.total_freeway_vehicles(cfg.network):.1f}",
        flush=True,
    )

    evals = controller._evaluate_candidate_set(
        candidates, list(range(len(candidates))), state, forecast, previous,
        stage="authority_probe", incumbent_obj=float("inf"),
    )

    rows: List[Dict[str, Any]] = []
    for ev in evals:
        diag = dict(ev.nash.diagnostics)
        diag.update(ev.nash.control.diagnostics)
        rows.append({
            "N_P_star": round(float(ev.action.N_P_star), 2),
            "N_UF_star": round(float(ev.action.N_UF_star), 2),
            "leader_objective": round(float(ev.objective), 4),
            "rollout_ttt": round(float(diag.get("distributed_response_rollout_ttt", 0.0)), 4),
            "rollout_urban_ttt": round(float(diag.get("distributed_response_rollout_urban_ttt", 0.0)), 4),
            "rollout_freeway_ttt": round(float(diag.get("distributed_response_rollout_freeway_ttt", 0.0)), 4),
            "projected_net_inflow_veh": round(float(diag.get("distributed_grid_leader_projected_net_inflow_veh", 0.0)), 2),
            "net_inflow_residual_veh": round(float(diag.get("distributed_grid_leader_net_inflow_residual_veh", 0.0)), 2),
        })

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "authority_probe_table.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # 각 고정 N_UF*에서 N_P* 스윕에 따른 rollout 변동폭(authority 지표).
    print("\n=== authority by fixed N_UF* (spread over N_P* sweep) ===")
    print(f"{'N_UF*':>9s} {'urban_min':>10s} {'urban_max':>10s} {'urban_spread':>12s} "
          f"{'tot_min':>9s} {'tot_max':>9s} {'tot_spread':>10s} {'projNP_min':>10s} {'projNP_max':>10s}")
    summary_by_nuf = []
    for nuf in nuf_values:
        sub = [r for r in rows if abs(r["N_UF_star"] - float(nuf)) < 1e-6]
        if not sub:
            continue
        u = [r["rollout_urban_ttt"] for r in sub]
        t = [r["rollout_ttt"] for r in sub]
        pn = [r["projected_net_inflow_veh"] for r in sub]
        rec = {
            "N_UF_star": round(float(nuf), 2),
            "urban_min": round(min(u), 3), "urban_max": round(max(u), 3),
            "urban_spread": round(max(u) - min(u), 3),
            "tot_min": round(min(t), 3), "tot_max": round(max(t), 3),
            "tot_spread": round(max(t) - min(t), 3),
            "projNP_min": round(min(pn), 1), "projNP_max": round(max(pn), 1),
        }
        summary_by_nuf.append(rec)
        print(f"{rec['N_UF_star']:9.1f} {rec['urban_min']:10.3f} {rec['urban_max']:10.3f} "
              f"{rec['urban_spread']:12.3f} {rec['tot_min']:9.3f} {rec['tot_max']:9.3f} "
              f"{rec['tot_spread']:10.3f} {rec['projNP_min']:10.1f} {rec['projNP_max']:10.1f}")

    (out / "authority_summary.json").write_text(
        json.dumps({
            "scenario": args.scenario,
            "warmup_steps": args.warmup_steps,
            "np_box": [np_lo, np_hi],
            "nuf_box": [nuf_lo, nuf_hi],
            "state_urban_veh": float(state.total_urban_vehicles(cfg.network)),
            "state_freeway_veh": float(state.total_freeway_vehicles(cfg.network)),
            "by_nuf": summary_by_nuf,
        }, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
