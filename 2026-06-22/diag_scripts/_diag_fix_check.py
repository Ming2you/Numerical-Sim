# 수정 후 leader N_P 후보범위가 좁아졌는지 + 범위 내 N_P sweep이 distinct 응답을 내는지 검증(일회용).
from src.models.state import ExperimentConfig, ControlAction
from src.models.demand import DemandProfile, load_scenarios, apply_scenario_network_overrides
from src.simulation.simulator import MixedTrafficSimulator
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.controllers.leader import LeaderAction

SCEN = "peak_demand"
SC = load_scenarios("src/config/scenarios.yaml")[SCEN]
cfg = apply_scenario_network_overrides(
    ExperimentConfig.from_file("src/config/default.yaml",
        {"mpc": {"follower_solver_mode": "distributed", "stackelberg_enable_fallback": False,
                 "grid_parallel_backend": "serial"}}), SC)  # 스크립트는 main-guard 없어 serial
prof = DemandProfile(cfg, SC)
sim = MixedTrafficSimulator(cfg)
nc = ControlAction.uncontrolled(cfg)
for k in range(2):
    sim.step(nc, prof.at(sim.state.time_sec), k)
state = sim.state.copy()
ctl = StackelbergMPCController(cfg)
prev = ctl._normalize_previous_leader_reference(ControlAction.fixed(cfg))
demand0 = prof.at(state.time_sec)
forecast = prof.horizon(state.time_sec, cfg.mpc.horizon_steps)

b = ctl.leader._candidate_bounds(state, prev, demand0, forecast)
print(f"[NEW bounds] N_P=[{b.np_lower:.1f}, {b.np_upper:.1f}]  (config range {cfg.leader.N_P_star_range})", flush=True)
print(f"            movement_np=[{b.movement_np_lower:.1f}, {b.movement_np_upper:.1f}]  N_UF=[{b.nuf_lower:.0f}, {b.nuf_upper:.0f}]", flush=True)

# 범위 내 5점 sweep (N_UF=6000 고정) → distinct base 확인
import numpy as np
lo, hi = b.np_lower, b.np_upper
NP = [float(x) for x in np.linspace(lo, hi, 5)]
cands = [LeaderAction(np_, 6000.0) for np_ in NP]
evals = ctl._evaluate_candidate_set(cands, list(range(len(cands))), state.copy(),
                                    forecast, prev, stage="diag", incumbent_obj=float("inf"))
print(f"\n{'N_P':>8} | {'base':>10}", flush=True)
bases = set()
for e in evals:
    bbase = round(float(e.objective_terms.get('leader_objective_base', 0)), 3)
    bases.add(bbase)
    print(f"{e.action.N_P_star:8.1f} | {bbase:10.3f}", flush=True)
print(f"\n범위 내 distinct base = {len(bases)} / {len(evals)}  (수정 전엔 saturation으로 사실상 1~2)", flush=True)
