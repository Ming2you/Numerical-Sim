# N_UF(및 N_P) 후보별 follower 응답이 몇 개의 distinct로 붕괴하는지 측정 — dedup 폭 확인(일회용).
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
nc = ControlAction.uncontrolled(cfg)
for k in range(2):
    sim.step(nc, prof.at(sim.state.time_sec), k)
state = sim.state.copy()
ctl = StackelbergMPCController(cfg)
prev = ctl._normalize_previous_leader_reference(ControlAction.fixed(cfg))
forecast = prof.horizon(state.time_sec, cfg.mpc.horizon_steps)

def ctrl_sig(c):
    def rd(d): return tuple(sorted((k, round(float(v), 3)) for k, v in d.items()))
    return (rd(getattr(c, "green_splits", {}) or {}),
            rd(getattr(c, "vsl", {}) or {}),
            rd(getattr(c, "ramp_metering", {}) or {}),
            rd(getattr(c, "offsets", {}) or {}))

def sweep(label, np_val, nuf_list):
    cands = [LeaderAction(np_val, nuf) for nuf in nuf_list]
    evals = ctl._evaluate_candidate_set(cands, list(range(len(cands))), state.copy(),
                                        forecast, prev, stage="diag", incumbent_obj=float("inf"))
    print(f"\n[{label}] N_P={np_val}", flush=True)
    bases, sigs = set(), set()
    for e in evals:
        b = round(float(e.objective_terms.get('leader_objective_base', 0)), 3)
        s = ctrl_sig(e.nash.control)
        bases.add(b); sigs.add(s)
        print(f"  N_UF={e.action.N_UF_star:6.0f}  base={b:9.3f}", flush=True)
    print(f"  -> distinct base={len(bases)} / {len(evals)} ,  distinct control={len(sigs)} / {len(evals)}", flush=True)

sweep("N_UF sweep @ admit-regime", 1400.0, [0.0, 1500.0, 3000.0, 4500.0, 6000.0])
sweep("N_UF sweep @ drain-regime", -3315.0, [0.0, 3000.0, 6000.0])
