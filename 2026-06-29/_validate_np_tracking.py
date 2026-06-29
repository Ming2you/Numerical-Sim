# N_P 추적 검증: 이분법 λ*가 leader N_P_star target을 따라가는지 단일-step 스윕 (임시)
"""warm된 sweet_128 혼잡 상태에서 N_P_star를 feasible 범위(1385→바닥)로 스윕하며
realized Σnin(diag wu_faithful_sum_nin)이 target을 따라 내려가다 바닥에서 clamp되는지 본다.
이전엔 λ가 0에 갇혀 Σnin이 1385에 평탄했다(추적 실패). 이제 따라가야 한다."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path('C:/Users/alsrj/Desktop/Numerical-Sim'); sys.path.insert(0, str(ROOT))

from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.controllers.leader import LeaderAction
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ExperimentConfig, ControlAction
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control

ov = {'mpc': {'relaxed_quantized_controls': True, 'grid_parallel_backend': 'serial'},
      'simulation': {'T_total': 3600.0}}
cfg = ExperimentConfig.from_file(str(ROOT / 'src/config/default.yaml'), ov)
scen = load_scenarios(str(ROOT / 'src/config/scenarios.yaml'))['sweet_128']
cfg = apply_scenario_network_overrides(cfg, scen)

# warm a congested state with no_control for 30 steps
profile = DemandProfile(cfg, scen); sim = MixedTrafficSimulator(cfg)
for step in range(30):
    t = step * cfg.simulation.control_interval
    fc = profile.horizon(t, cfg.mpc.horizon_steps)
    c = baseline_control('no_control', cfg, sim.state, fc[0]); sim.step(c, fc[0], step)
state = sim.state.copy()
t = 30 * cfg.simulation.control_interval
forecast = profile.horizon(t, cfg.mpc.horizon_steps)
prev = ControlAction.uncontrolled(cfg)

# Sigma_nin(lambda) is monotone non-increasing & piecewise-constant. Achievable levels at the
# converged coupling are ~{1550(slack), 1235, 1168, 1105, 1055(floor)}; target is matched to the
# nearest achievable level <= target (or the floor). 'tracks down' = realized follows target down.
targets = [1600.0, 1385.0, 1300.0, 1200.0, 1108.0, 1050.0, 900.0]
print(f"{'N_P_star':>10} {'realized_Sigma_nin':>18} {'lambda*':>12} {'evals':>8}  note")
prev_realized = None
for tgt in targets:
    f = WuFaithfulFollower(cfg)  # fresh -> no warm-start carryover; isolates each target
    leader = LeaderAction(N_P_star=tgt, N_UF_star=0.0)
    control, it, conv, resid, evals = f._solve_followers(state, forecast[0], prev, leader, forecast)
    realized = control.diagnostics['wu_faithful_sum_nin']
    lam = control.diagnostics['wu_faithful_lambda_P']
    if prev_realized is None:
        note = 'baseline (slack region)'
    elif realized <= prev_realized + 1e-6:
        note = 'follows target down' if realized > 1056 else 'clamped @ floor (~1055)'
    else:
        note = '!! went UP (bug)'
    prev_realized = realized
    print(f"{tgt:>10.1f} {realized:>18.1f} {lam:>12.4f} {evals:>8}  {note}")
