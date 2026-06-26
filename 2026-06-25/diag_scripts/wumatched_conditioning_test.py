# WU-MATCHED 0% 원인 격리: leader conditioning(w_P,w_F) on/off로 follower가 망가지는지 확인.
import argparse
from src.controllers.wu_distributed import WuDistributedController
from src.controllers.distributed_coordinator import DistributedCoordinator
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ExperimentConfig, ControlAction
from src.simulation.simulator import MixedTrafficSimulator

ap = argparse.ArgumentParser()
ap.add_argument("--steps", type=int, default=8)
args = ap.parse_args()


def run(label, w_p, w_f, leader_enabled):
    cfg = ExperimentConfig.from_file("src/config/default.yaml",
        {"simulation": {"T_total": 180.0 * args.steps},
         "mpc": {"grid_parallel_backend": "serial"},
         "leader": {"w_P": w_p, "w_F": w_f}})
    sc = load_scenarios("src/config/scenarios.yaml")["sweet_128"]
    cfg = apply_scenario_network_overrides(cfg, sc)
    demand = DemandProfile(cfg, sc)
    sim = MixedTrafficSimulator(cfg)
    ctrl = WuDistributedController(cfg, leader_enabled=leader_enabled)
    prev = None
    sel = []
    for step in range(args.steps):
        cd = demand.at(sim.state.time_sec)
        fc = demand.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
        info = ctrl.decide_with_info(sim.state.copy(), fc, prev)
        c = info.control
        if info.leader_selected is not None:
            sel.append((round(info.leader_selected.n_p_star,0), round(info.leader_selected.n_f_star,0)))
        sim.step(c, cd, step)
        prev = c
    print(f"{label:32s} total_ttt={sim.total_ttt:8.2f}  selected(N_P,N_F)={sel[:3]}")
    return sim.total_ttt


# no-control baseline
cfg0 = apply_scenario_network_overrides(
    ExperimentConfig.from_file("src/config/default.yaml", {"simulation": {"T_total": 180.0*args.steps}}),
    load_scenarios("src/config/scenarios.yaml")["sweet_128"])
sim0 = MixedTrafficSimulator(cfg0); d0 = DemandProfile(cfg0, load_scenarios("src/config/scenarios.yaml")["sweet_128"])
from src.simulation.baseline import baseline_control
prev = None
for step in range(args.steps):
    cd = d0.at(sim0.state.time_sec)
    c = baseline_control("no_control", cfg0, sim0.state.copy(), cd, prev)
    sim0.step(c, cd, step); prev = c
nc = sim0.total_ttt
print(f"{'NO-CONTROL':32s} total_ttt={nc:8.2f}")
print()
a = run("WU-MATCHED conditioning ON (w=1)", 1.0, 1.0, True)
b = run("WU-MATCHED conditioning OFF (w=0)", 0.0, 0.0, True)
c = run("WU-CD-F (leader disabled)", 1.0, 1.0, False)
print()
print(f"개선율: ON={100*(nc-a)/nc:.1f}%  OFF={100*(nc-b)/nc:.1f}%  WU-CD-F={100*(nc-c)/nc:.1f}%")
