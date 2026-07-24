# refined_candidates의 반경 준수 여부를 직접 계측 — 시뮬 없이 후보 생성만 호출(프로덕션 미변경).
import sys, io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.controllers.leader import LeaderAction

runner = importlib.import_module('run_claude_style_five_controller')

SC = sys.argv[1] if len(sys.argv) > 1 else 'sweet_170_incident_w'
cfg, scenario = runner.build_cfg(SC, 30 * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

R = float(cfg.mpc.leader_local_nuf_radius_veh_h)
print("search_mode              =", cfg.mpc.leader_search_mode)
print("skip_local_refinement    =", getattr(cfg.mpc, 'leader_skip_local_refinement', None))
print("leader_local_nuf_radius  =", R)
print("global_refresh_sec       =", cfg.mpc.leader_global_refresh_sec)
print()

leader = controller.leader
profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
state = sim.state

# previous ControlAction 하나 만들기(baseline)
from src.simulation.baseline import baseline_control
prev = baseline_control('no_control', cfg, state, forecast[0])

bounds = leader._candidate_bounds(state, prev, forecast[0], forecast)
print("bounds.nuf_lower=%.0f  bounds.nuf_upper=%.0f  heuristic_nuf=%.0f"
      % (bounds.nuf_lower, bounds.nuf_upper, bounds.heuristic_nuf))
print("_nuf_anchor_values =", sorted(round(v) for v in leader._nuf_anchor_values(bounds, prev)))
print()

print("%10s | %10s %10s | %10s %10s | %s" %
      ('center', '반경下', '반경上', '후보min', '후보max', '판정'))
print('-' * 78)
for c in (6000.0, 4231.0, 3000.0, 1500.0):
    center = LeaderAction(float(prev.N_P_star), c)
    out = leader.refined_candidates(state, center, prev, forecast[0], forecast=forecast)
    vals = [a.N_UF_star for a in out]
    lo_exp = max(bounds.nuf_lower, c - R)
    hi_exp = min(bounds.nuf_upper, c + R)
    viol = (min(vals) < lo_exp - 1) or (max(vals) > hi_exp + 1)
    print("%10.0f | %10.0f %10.0f | %10.0f %10.0f | %s (n=%d)"
          % (c, lo_exp, hi_exp, min(vals), max(vals),
             '★반경위반' if viol else 'OK', len(out)))

# lens#4: candidates()(전역) vs refined_candidates()(국소) 범위 비교
g = leader.candidates(state, prev, forecast[0], forecast=forecast)
gv = [a.N_UF_star for a in g]
center = LeaderAction(float(prev.N_P_star), 6000.0)
r = leader.refined_candidates(state, center, prev, forecast[0], forecast=forecast)
rv = [a.N_UF_star for a in r]
print()
print("전역 candidates()      N_UF 범위 = [%.0f, %.0f]  n=%d" % (min(gv), max(gv), len(g)))
print("국소 refined(center=6000) 범위 = [%.0f, %.0f]  n=%d" % (min(rv), max(rv), len(r)))
