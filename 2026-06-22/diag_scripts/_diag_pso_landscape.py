# pso 모드 N_P 후보별 leader objective vs 실제 rollout — 상한-핀(objective 오정렬) 진단(일회용).
from src.models.state import ExperimentConfig, ControlAction
from src.models.demand import DemandProfile, load_scenarios, apply_scenario_network_overrides
from src.simulation.simulator import MixedTrafficSimulator
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.controllers.leader import LeaderAction

SCEN = "peak_demand"
SC = load_scenarios("src/config/scenarios.yaml")[SCEN]


def build_cfg():
    return apply_scenario_network_overrides(
        ExperimentConfig.from_file("src/config/default.yaml", {"mpc": {
            "follower_solver_mode": "distributed", "stackelberg_enable_fallback": False,
            "stackelberg_allocation_mode": "pso", "max_nash_iter": 1,
            "grid_parallel_backend": "serial"}}), SC)


def congested(cfg):
    prof = DemandProfile(cfg, SC)
    sim = MixedTrafficSimulator(cfg)
    nc = ControlAction.uncontrolled(cfg)
    for k in range(2):
        sim.step(nc, prof.at(sim.state.time_sec), k)
    return prof, sim.state.copy()


def rollout(cfg, control, n=3):
    prof = DemandProfile(cfg, SC); sim = MixedTrafficSimulator(cfg)
    nc = ControlAction.uncontrolled(cfg)
    for k in range(2):
        sim.step(nc, prof.at(sim.state.time_sec), k)
    tot = 0.0
    for k in range(n):
        log = sim.step(control, prof.at(sim.state.time_sec), 100 + k)
        tot += float(log.freeway_ttt + log.urban_ttt)
    return tot


cfg = build_cfg()
prof, state = congested(cfg)
ctl = StackelbergMPCController(cfg)
prev = ctl._normalize_previous_leader_reference(ControlAction.fixed(cfg))
fc = prof.horizon(state.time_sec, cfg.mpc.horizon_steps)
b = ctl.leader._candidate_bounds(state, prev, prof.at(state.time_sec), fc)
print(f"bounds N_P=[{b.np_lower:.0f},{b.np_upper:.0f}]", flush=True)

import numpy as np
NP = [float(x) for x in np.linspace(max(0.0, b.np_lower), b.np_upper, 6)]
cands = [LeaderAction(np_, 4000.0) for np_ in NP]
evals = ctl._evaluate_candidate_set(cands, list(range(len(cands))), state.copy(), fc, prev, stage="diag", incumbent_obj=float("inf"))
print(f"{'N_P':>7} {'leader_obj':>11} {'REAL_3step':>11}", flush=True)
for e in evals:
    rt = rollout(cfg, e.nash.control)
    print(f"{e.action.N_P_star:>7.0f} {e.objective:>11.3f} {rt:>11.3f}", flush=True)
