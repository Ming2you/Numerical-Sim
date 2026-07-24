# PFO 귀속 주장 검증 — 동일 state에서 _nuf_anchor_values 유무 A/B로 후보범위 변화를 실측(프로덕션 미변경).
# 물음: refined_candidates의 '반경 파괴'가 9581fcd(_nuf_anchor_values, PFO)의 부수효과인가?
import sys, io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
import numpy as np
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control
from src.controllers import leader as LD
from src.controllers.leader import LeaderAction

runner = importlib.import_module('run_claude_style_five_controller')

SC = 'sweet_170_incident_w'
STEPS = 30
WARM = 20

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True
leader = controller.leader
R = float(cfg.mpc.leader_local_nuf_radius_veh_h)

_orig_anchor = LD.Leader._nuf_anchor_values
rows = []

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None

print("반경 R = %.0f" % R)
print()
print("%4s %9s %9s %9s %9s | %-17s %-17s | %s" %
      ('step', 'center', 'lower', 'upper', 'heur', 'ON(④포함)', 'OFF(④제거)', '동일?'))
print('-' * 104)

for step in range(STEPS):
    forecast = profile.horizon(sim.state.time_sec,
                              cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    state = sim.state
    prev_ctrl = prev if prev is not None else baseline_control('no_control', cfg, state, forecast[0])

    if step >= WARM:
        bounds = leader._candidate_bounds(state, prev_ctrl, forecast[0], forecast)
        center = LeaderAction(float(prev_ctrl.N_P_star),
                              float(np.clip(prev_ctrl.N_UF_star, bounds.nuf_lower, bounds.nuf_upper)))

        # A: 프로덕션 그대로
        LD.Leader._nuf_anchor_values = _orig_anchor
        on = [a.N_UF_star for a in leader.refined_candidates(state, center, prev_ctrl, forecast[0], forecast)]

        # B: _nuf_anchor_values를 완전히 무력화(빈 집합) — PFO 기여만 제거
        LD.Leader._nuf_anchor_values = lambda self, b, p=None: set()
        off = [a.N_UF_star for a in leader.refined_candidates(state, center, prev_ctrl, forecast[0], forecast)]
        LD.Leader._nuf_anchor_values = _orig_anchor

        same = (abs(min(on) - min(off)) < 1.0) and (abs(max(on) - max(off)) < 1.0)
        # 반경 밖으로 벗어난 폭(OFF 기준) — ④ 없이도 반경이 깨지는가
        off_escape = max(0.0, (center.N_UF_star - min(off)) - R, (max(off) - center.N_UF_star) - R)
        rows.append((step, center.N_UF_star, bounds.nuf_lower, bounds.nuf_upper,
                     bounds.heuristic_nuf, min(on), max(on), min(off), max(off), same, off_escape))
        print("%4d %9.0f %9.0f %9.0f %9.0f | [%6.0f,%6.0f] [%6.0f,%6.0f] | %s%s" %
              (step, center.N_UF_star, bounds.nuf_lower, bounds.nuf_upper, bounds.heuristic_nuf,
               min(on), max(on), min(off), max(off),
               '동일' if same else '다름',
               ('  (④없이 반경초과 %+.0f)' % off_escape) if off_escape > 1 else ''))

    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, forecast[0])
    else:
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, forecast, prev, cfg, step)
    sim.step(ctrl, forecast[0], step)
    prev = ctrl

print()
n = len(rows)
same_n = sum(1 for r in rows if r[9])
esc_n = sum(1 for r in rows if r[10] > 1)
heur_at_lower = sum(1 for r in rows if abs(r[4] - r[2]) < 1.0)
print("측정 스텝 수: %d" % n)
print("④(PFO) 제거해도 후보범위 동일: %d/%d" % (same_n, n))
print("④ 없이도 반경 초과(파괴 잔존):  %d/%d" % (esc_n, n))
print("heuristic_nuf == bounds.nuf_lower(끝점): %d/%d" % (heur_at_lower, n))
if n:
    print("④ 없이 반경초과 폭 최대 = %+.0f (반경 R=%.0f)" % (max(r[10] for r in rows), R))
