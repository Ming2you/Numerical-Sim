# PFO vs P-Stack(fallback on) vs P-Stack(fallback off)의 실제 closed-loop TTT 비교.
# fallback guard가 leader의 진짜 개선을 막는지(과보호) vs 더 나쁜 걸 올바로 막는지 가른다.
import argparse

from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator

ap = argparse.ArgumentParser()
ap.add_argument("--scenario", default="sweet_128")
ap.add_argument("--steps", type=int, default=8)
args = ap.parse_args()


def base_cfg(fallback: bool):
    cfg = ExperimentConfig.from_file(
        "src/config/default.yaml",
        {"simulation": {"T_total": 180.0 * args.steps}, "mpc": {
            "relaxed_quantized_controls": True,
            "grid_parallel_backend": "serial",
            "stackelberg_leader_parallel_backend": "serial",
            "stackelberg_enable_fallback": fallback,
        }},
    )
    sc = load_scenarios("src/config/scenarios.yaml")[args.scenario]
    cfg = apply_scenario_network_overrides(cfg, sc)
    cfg.mpc.follower_solver_mode = "distributed"
    return cfg, sc


def run_pfo():
    cfg, sc = base_cfg(False)
    demand = DemandProfile(cfg, sc)
    sim = MixedTrafficSimulator(cfg)
    coord = DistributedCoordinator(cfg)
    prev = None
    for step in range(args.steps):
        cd = demand.at(sim.state.time_sec)
        fc = demand.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
        nash = coord.solve(sim.state.copy(), None, fc, prev or ControlAction.uncontrolled(cfg))
        sim.step(nash.control, cd, step)
        prev = nash.control
    return sim.total_ttt


def run_pstack(fallback: bool):
    cfg, sc = base_cfg(fallback)
    demand = DemandProfile(cfg, sc)
    sim = MixedTrafficSimulator(cfg)
    ctrl = StackelbergMPCController(cfg)
    prev = None
    max_np = 0.0
    for step in range(args.steps):
        cd = demand.at(sim.state.time_sec)
        fc = demand.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
        c = ctrl.decide(sim.state.copy(), fc, prev, cfg)
        max_np = max(max_np, abs(float(c.diagnostics.get("leader_intent_N_P_star", 0.0))))
        sim.step(c, cd, step)
        prev = c
    return sim.total_ttt, max_np


print(f"scenario={args.scenario} steps={args.steps}")
pfo = run_pfo()
print(f"PFO                total_ttt = {pfo:.3f}")
ttt_on, np_on = run_pstack(True)
print(f"P-Stack fb-ON      total_ttt = {ttt_on:.3f}   (maxN_P={np_on:.0f}, vs PFO {pfo - ttt_on:+.3f})")
ttt_off, np_off = run_pstack(False)
print(f"P-Stack fb-OFF     total_ttt = {ttt_off:.3f}   (maxN_P={np_off:.0f}, vs PFO {pfo - ttt_off:+.3f})")
print()
print(f"fb-OFF leader가 PFO보다 좋은가? {ttt_off < pfo - 1e-6}  (gain={pfo - ttt_off:+.3f})")
print(f"fallback guard가 막은 게 정당? {ttt_off >= ttt_on - 1e-6}  (fb-on {ttt_on:.3f} vs fb-off {ttt_off:.3f})")
