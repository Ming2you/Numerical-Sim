# 혼잡 state에서 N_P 후보별 leader objective 분해 — -3315가 진짜 objective 최소인지(구조적) vs 탐색버그 판별(일회용).
from src.models.state import ExperimentConfig, ControlAction
from src.models.demand import DemandProfile, load_scenarios, apply_scenario_network_overrides
from src.simulation.simulator import MixedTrafficSimulator
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.controllers.leader import LeaderAction

SCEN = "peak_demand"
SC = load_scenarios("src/config/scenarios.yaml")[SCEN]
cfg = apply_scenario_network_overrides(
    ExperimentConfig.from_file("src/config/default.yaml",
        {"mpc": {"follower_solver_mode": "distributed", "stackelberg_enable_fallback": False}}), SC)
prof = DemandProfile(cfg, SC)
sim = MixedTrafficSimulator(cfg)

# 1) no-control로 2 인터벌(360s) 굴려 혼잡 누적
nc = ControlAction.uncontrolled(cfg)
for k in range(2):
    t = sim.state.time_sec
    sim.step(nc, prof.at(t), k)
state = sim.state.copy()
print(f"congested state @ t={state.time_sec:.0f}s  protected_N_P={state.protected_accumulation_veh(cfg.network):.1f} veh", flush=True)

# 2) 그 state에서 N_P 후보별 objective 평가
ctl = StackelbergMPCController(cfg)
prev = ctl._normalize_previous_leader_reference(ControlAction.fixed(cfg))
t = state.time_sec
forecast = prof.horizon(t, cfg.mpc.horizon_steps)

NP = [-3315.0, -1500.0, 0.0, 1400.0, 2287.0, 3220.0]
cands = [LeaderAction(np_, 6000.0) for np_ in NP]
evals = ctl._evaluate_candidate_set(cands, list(range(len(cands))), state.copy(),
                                    forecast, prev, stage="diag", incumbent_obj=float("inf"))

# 3) 후보별 follower 응답을 실제 plant에서 3-스텝 굴려 realized TTT 측정 (counterfactual rollout)
def congested_sim():
    s = MixedTrafficSimulator(cfg)
    for kk in range(2):
        s.step(nc, prof.at(s.state.time_sec), kk)
    return s

def rollout_ttt(control, n_steps=3):
    s = congested_sim()
    tot = 0.0
    for kk in range(n_steps):
        tt = s.state.time_sec
        log = s.step(control, prof.at(tt), 100 + kk)
        tot += float(log.freeway_ttt + log.urban_ttt)
    return tot

results = []
for e in evals:
    rttt = rollout_ttt(e.nash.control)
    results.append((e.action.N_P_star, e.objective, e.objective_terms.get('leader_objective_base', 0), rttt))

obj_best = min(results, key=lambda r: r[1])
roll_best = min(results, key=lambda r: r[3])
print(f"\n{'N_P':>7} | {'obj_TOTAL':>10} | {'obj_base':>9} | {'REAL_3step_TTT':>14}", flush=True)
print("-" * 52, flush=True)
for np_, obj, base, rttt in results:
    m = []
    if (np_, obj, base, rttt) == obj_best: m.append("obj-MIN")
    if (np_, obj, base, rttt) == roll_best: m.append("roll-MIN")
    print(f"{np_:7.0f} | {obj:10.3f} | {base:9.3f} | {rttt:14.4f}  {' '.join(m)}", flush=True)
print(f"\nobjective argmin N_P = {obj_best[0]:.0f}   |   actual-rollout argmin N_P = {roll_best[0]:.0f}", flush=True)
print("RANKING " + ("AGREE (finite-horizon/objective-design issue)" if obj_best[0]==roll_best[0]
                    else "DISAGREE (candidate eval/translation/rollout bug)"), flush=True)
