"""사영이 N_P를 한 점으로 뭉개는지 — V 지도의 N_P 축이 평평한 진짜 이유.

지도 실측: N_P를 -1730~2861(폭 4591)로 훑어도 V가 한 자리도 안 변함.
가설 A(설계): N_P는 원래 무력한 레버다.
가설 B(버그): _project_action_to_follower_feasible_np가 전부 한 점으로 사영한다.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'work'))
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import importlib, numpy as np
from src.controllers.leader import LeaderAction
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control

runner = importlib.import_module('run_claude_style_five_controller')
SC = sys.argv[1] if len(sys.argv) > 1 else 'sweet_170_w'
AT = int(sys.argv[2]) if len(sys.argv) > 2 else 25

cfg, scen = runner.build_cfg(SC, (AT + 1) * 180.0)
c = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
c.nash_solver.segment_agents = True
prof = DemandProfile(cfg, scen); sim = MixedTrafficSimulator(cfg)
prev = None
for s in range(AT):
    fc = prof.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    ctrl = (baseline_control('no_control', cfg, sim.state, fc[0]) if s < 20
            else runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', c, sim, fc, prev, cfg, s))
    sim.step(ctrl, fc[0], s); prev = ctrl
st = sim.state
fc = prof.horizon(st.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
pn = c._normalize_previous_leader_reference(prev)
b = c.leader._candidate_bounds(st, prev, None, fc)

print("### %s step %d — 사영이 N_P를 어디로 보내나" % (SC, AT))
print("leader bounds N_P = [%.0f, %.0f]  (폭 %.0f)" % (b.np_lower, b.np_upper, b.np_upper - b.np_lower))
print()
fn = getattr(c.nash_solver, 'leader_np_feasible_range', None)
if fn is None:
    print("  ★leader_np_feasible_range 없음 → 사영 자체가 no-op(action 그대로 반환)")
else:
    smin, smax, diag = fn(st.copy(), list(fc), pn.copy())
    lo, hi = min(smin, smax), max(smin, smax)
    print("  follower feasible range = [%.1f, %.1f]  (폭 %.1f)" % (lo, hi, hi - lo))
    print("  → leader bounds 폭의 %.2f%%" % ((hi - lo) / max(b.np_upper - b.np_lower, 1e-9) * 100))
    print()
print("%12s %12s %12s" % ('입력 N_P', '사영 N_P', '변화'))
print('-' * 38)
out = []
for p in np.linspace(b.np_lower, b.np_upper, 9):
    ap, meta = c._project_action_to_follower_feasible_np(LeaderAction(float(p), 5000.0), st.copy(), fc, pn)
    out.append(round(float(ap.N_P_star), 3))
    print("%12.1f %12.1f %12.1f" % (p, ap.N_P_star, ap.N_P_star - p))
uniq = sorted(set(out))
print()
print("  고유 사영값 = %d개 / 9  %s" % (len(uniq), [round(x, 1) for x in uniq[:9]]))
print("  판정: %s" % ('★사영이 전부 한 점으로 뭉갬 — N_P 축이 존재하지 않음'
                    if len(uniq) == 1 else
                    '사영이 %d개로 분리 — N_P 축은 살아있고 V가 진짜로 N_P에 무감' % len(uniq)))
