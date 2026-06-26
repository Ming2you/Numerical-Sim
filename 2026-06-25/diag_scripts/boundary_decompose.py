# sweet_190 등에서 PFO vs fb-OFF leader의 TTT를 freeway/urban/boundary 큐/보호영역 누적으로 분해.
# leader가 interior는 줄이는데 boundary에 막혀 가려지는지(accounting) vs 그냥 과admit인지 가른다.
import argparse

from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator

ap = argparse.ArgumentParser()
ap.add_argument("--scenario", default="sweet_190")
ap.add_argument("--steps", type=int, default=8)
args = ap.parse_args()


def make_cfg():
    cfg = ExperimentConfig.from_file(
        "src/config/default.yaml",
        {"simulation": {"T_total": 180.0 * args.steps}, "mpc": {
            "relaxed_quantized_controls": True,
            "grid_parallel_backend": "serial",
            "stackelberg_leader_parallel_backend": "serial",
            "stackelberg_enable_fallback": False,
        }},
    )
    sc = load_scenarios("src/config/scenarios.yaml")[args.scenario]
    cfg = apply_scenario_network_overrides(cfg, sc)
    cfg.mpc.follower_solver_mode = "distributed"
    return cfg, sc


def run(mode):
    cfg, sc = make_cfg()
    net = cfg.network
    demand = DemandProfile(cfg, sc)
    sim = MixedTrafficSimulator(cfg)
    coord = DistributedCoordinator(cfg) if mode == "pfo" else None
    ctrl = StackelbergMPCController(cfg) if mode == "leader" else None
    prev = None
    max_bnd = 0.0
    max_np_acc = 0.0
    max_intent_np = 0.0
    for step in range(args.steps):
        cd = demand.at(sim.state.time_sec)
        fc = demand.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
        max_bnd = max(max_bnd, sim.state.boundary_in_queue_vehicles(net))
        max_np_acc = max(max_np_acc, sim.state.protected_accumulation_veh(net))
        if mode == "pfo":
            c = coord.solve(sim.state.copy(), None, fc, prev or ControlAction.uncontrolled(cfg)).control
        else:
            c = ctrl.decide(sim.state.copy(), fc, prev, cfg)
            max_intent_np = max(max_intent_np, abs(float(c.diagnostics.get("leader_intent_N_P_star", 0.0))))
        sim.step(c, cd, step)
        prev = c
    final_bnd = sim.state.boundary_in_queue_vehicles(net)
    return {
        "freeway_ttt": sim.freeway_ttt, "urban_ttt": sim.urban_ttt, "total_ttt": sim.total_ttt,
        "max_boundary_in_q": max_bnd, "final_boundary_in_q": final_bnd,
        "max_protected_acc": max_np_acc, "max_intent_np": max_intent_np,
    }


cfg, _ = make_cfg()
print(f"scenario={args.scenario} steps={args.steps}  N_P_crit={cfg.leader.N_P_crit_veh:.0f}\n")
pfo = run("pfo")
ld = run("leader")
print(f"{'metric':>22} {'PFO':>10} {'leader(fbOFF)':>14} {'Δ(ld-PFO)':>11}")
for k in ["freeway_ttt", "urban_ttt", "total_ttt", "max_boundary_in_q", "final_boundary_in_q", "max_protected_acc"]:
    print(f"{k:>22} {pfo[k]:10.2f} {ld[k]:14.2f} {ld[k]-pfo[k]:+11.2f}")
print(f"{'leader maxIntent N_P':>22} {'-':>10} {ld['max_intent_np']:14.1f}")
