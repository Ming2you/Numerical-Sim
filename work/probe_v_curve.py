"""리더 목적함수 V(N_UF) 곡선 직접 측정 — 평탄/다봉/단봉 판정.

'왜 리더가 매 스텝 전 범위를 왔다갔다 하는가'의 직접 답. 리뷰어 렌즈4가 측정 실패한 항목.
후보 격자를 쓰지 않고 N_UF를 등간격으로 훑어 _leader_evaluation_base를 직접 호출한다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
import numpy as np
from src.controllers.leader import LeaderAction
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control

runner = importlib.import_module('run_claude_style_five_controller')

SC = sys.argv[1] if len(sys.argv) > 1 else 'sweet_170_w'
AT = int(sys.argv[2]) if len(sys.argv) > 2 else 25      # 이 스텝에서 곡선을 뜬다
NPTS = int(sys.argv[3]) if len(sys.argv) > 3 else 13
WARM = 20

cfg, scenario = runner.build_cfg(SC, (AT + 2) * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
for step in range(AT):
    fc = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, fc[0])
    else:
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, fc, prev, cfg, step)
    sim.step(ctrl, fc[0], step)
    prev = ctrl

st = sim.state
fc = profile.horizon(st.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
ld = controller.leader if hasattr(controller, 'leader') else None
b = ld._candidate_bounds(st, prev, None, fc)
prev_norm = controller._normalize_previous_leader_reference(prev)

print("### V(N_UF) 곡선 — %s, step %d" % (SC, AT))
print("bounds N_UF = [%.0f, %.0f]   N_P = [%.0f, %.0f]" % (b.nuf_lower, b.nuf_upper, b.np_lower, b.np_upper))
print("previous N_UF* = %.0f  N_P* = %.0f" % (prev_norm.N_UF_star, prev_norm.N_P_star))
print()

np_fixed = float(np.clip(prev_norm.N_P_star, b.np_lower, b.np_upper))
grid = np.linspace(b.nuf_lower, b.nuf_upper, NPTS)
rows = []
for nuf in grid:
    action = LeaderAction(np_fixed, float(nuf))
    try:
        # 리더가 후보를 채점하는 바로 그 경로. objective가 곧 V = near + far(+hinge).
        ev = controller._evaluate_full_candidate(
            0, action, st.copy(), fc, prev_norm, "probe", float('inf'), float('inf'))
        rows.append((float(nuf), float(ev.objective), float(ev.action.N_UF_star)))
    except Exception as e:
        rows.append((float(nuf), None, None))
        err = e

vals = [v for _, v, _ in rows if v is not None]
if not vals:
    print("★ 측정 실패 — _solve_follower_for_leader/_leader_evaluation_base 시그니처 확인 필요")
    sys.exit(1)

lo, hi = min(vals), max(vals)
print("%10s %14s %10s" % ('N_UF', 'V(목적함수)', '막대'))
print('-' * 46)
for nuf, v, proj in rows:
    if v is None:
        print("%10.0f %14s" % (nuf, '(실패)'))
        continue
    bar = '#' * int(round((v - lo) / max(hi - lo, 1e-9) * 28))
    star = ' ←최소' if abs(v - lo) < 1e-9 else ''
    pj = '' if proj is None or abs(proj - nuf) < 1 else '  (사영→%.0f)' % proj
    print("%10.0f %14.3f %s%s%s" % (nuf, v, bar, star, pj))
print()
span = hi - lo
print("  V 범위 = %.3f (min %.3f @ N_UF=%.0f)" % (span, lo, rows[[v for _, v, _ in rows].index(lo)][0]))
print("  상대 변동 = %.2f%%  → %s" % (span / max(abs(lo), 1e-9) * 100,
      "★거의 평탄 — argmin이 잡음 따라 튄다" if span / max(abs(lo), 1e-9) < 0.02 else "구조 있음"))
# 국소최소 개수
mins = [i for i in range(1, len(rows) - 1)
        if rows[i][1] is not None and rows[i-1][1] is not None and rows[i+1][1] is not None
        and rows[i][1] < rows[i-1][1] and rows[i][1] < rows[i+1][1]]
print("  내부 국소최소 %d개 → %s" % (len(mins), "★다봉 — 봉우리 사이를 오간다" if len(mins) > 1 else "단봉"))
