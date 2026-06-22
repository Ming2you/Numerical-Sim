# closed-loop P-Stack fidelity probe: 매 step 예측 follower_ttt_base vs 실제 plant TTT(증분 CSV, 일회용).
import math, statistics, csv
from pathlib import Path
from src.models.state import ExperimentConfig, ControlAction
from src.models.demand import DemandProfile, load_scenarios, apply_scenario_network_overrides
from src.simulation.simulator import MixedTrafficSimulator
from src.controllers.stackelberg_mpc import StackelbergMPCController

SCEN = "peak_demand"; T = 3600.0
SC = load_scenarios("src/config/scenarios.yaml")[SCEN]
cfg = apply_scenario_network_overrides(
    ExperimentConfig.from_file("src/config/default.yaml",
        {"mpc": {"follower_solver_mode": "distributed", "stackelberg_enable_fallback": False}}), SC)
prof = DemandProfile(cfg, SC); sim = MixedTrafficSimulator(cfg)
ctl = StackelbergMPCController(cfg); prev = ControlAction.fixed(cfg)
n = int(T / cfg.simulation.control_interval)
out = Path("outputs/fidelity_probe"); out.mkdir(parents=True, exist_ok=True)
f = open(out / "steps.csv", "w", newline="", encoding="utf-8")
w = csv.writer(f); w.writerow(["step", "pred_base", "real_ttt", "N_P_star", "N_UF_star", "key"]); f.flush()

def pick_base(diag):
    for key in ("leader_follower_ttt_base", "leader_objective_base", "leader_total_objective"):
        if key in diag:
            return float(diag[key]), key
    cands = [k for k in diag if "follower_ttt" in k or "objective" in k]
    return (float(diag[cands[0]]), cands[0]) if cands else (0.0, "NONE")

pred = []; real = []; key_used = "?"
for k in range(n):
    t = sim.state.time_sec
    forecast = prof.horizon(t, cfg.mpc.horizon_steps)
    res = ctl.decide_with_info(sim.state.copy(), forecast, prev)
    c = res.control
    base, key_used = pick_base(c.diagnostics)
    log = sim.step(c, prof.at(t), k)
    rttt = float(log.freeway_ttt + log.urban_ttt)
    pred.append(base); real.append(rttt); prev = c
    w.writerow([k, round(base, 3), round(rttt, 4), round(c.N_P_star, 1), round(c.N_UF_star, 1), key_used]); f.flush()

def corr(a, b):
    ma = sum(a)/len(a); mb = sum(b)/len(b)
    cov = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    va = sum((x-ma)**2 for x in a); vb = sum((y-mb)**2 for y in b)
    return cov/math.sqrt(va*vb) if va > 0 and vb > 0 else float('nan')

ratios = [p/r for p, r in zip(pred, real) if r > 0]
summary = (f"DONE key={key_used} CORR={corr(pred, real):.3f} "
           f"ratio_mean={statistics.mean(ratios):.1f}x" if ratios else "DONE no-data")
w.writerow([summary]); f.flush(); f.close()
print(summary)
