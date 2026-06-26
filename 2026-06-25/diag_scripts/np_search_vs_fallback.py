# leader 탐색이 fallback 이전에 N_P를 원했는지 확인: candidate_best_N_P_star vs committed(post-fallback).
import argparse

from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ExperimentConfig

ap = argparse.ArgumentParser()
ap.add_argument("--scenario", default="sweet_190")
ap.add_argument("--steps", type=int, default=6)
ap.add_argument("--fallback", choices=["on", "off"], default="off")
args = ap.parse_args()

from src.simulation.simulator import MixedTrafficSimulator

cfg = ExperimentConfig.from_file(
    "src/config/default.yaml",
    {"simulation": {"T_total": 180.0 * args.steps}, "mpc": {
        "relaxed_quantized_controls": True,
        "grid_parallel_backend": "serial",
        "stackelberg_leader_parallel_backend": "serial",
        "stackelberg_enable_fallback": args.fallback == "on",
    }},
)
sc = load_scenarios("src/config/scenarios.yaml")[args.scenario]
cfg = apply_scenario_network_overrides(cfg, sc)
cfg.mpc.follower_solver_mode = "distributed"
demand = DemandProfile(cfg, sc)
sim = MixedTrafficSimulator(cfg)
ctrl = StackelbergMPCController(cfg)
prev = None
print(f"scenario={args.scenario}")
print(f"{'step':>4} {'searchBestNP':>12} {'searchBestNUF':>13} {'searchBestObj':>13} {'committedNP':>11} {'committedNUF':>12} {'fallbackPFO':>11}")
for step in range(args.steps):
    cd = demand.at(sim.state.time_sec)
    fc = demand.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
    c = ctrl.decide(sim.state.copy(), fc, prev, cfg)
    d = c.diagnostics
    print(f"{step:>4} {d.get('leader_candidate_best_N_P_star',0):12.1f} {d.get('leader_candidate_best_N_UF_star',0):13.1f} "
          f"{d.get('leader_candidate_best_objective',0):13.3f} {d.get('leader_intent_N_P_star',0):11.1f} "
          f"{d.get('leader_intent_N_UF_star',0):12.1f} {d.get('leader_selected_stage_fallback_pfo',0):11.0f}")
    sim.step(c, cd, step)
    prev = c
