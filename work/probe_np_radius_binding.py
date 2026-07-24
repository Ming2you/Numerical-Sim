# N_P 국소반경(leader_local_np_radius_veh=40)이 span 기반 floor에 덮이는지 라이브 폐루프에서 계측 — 프로덕션 미변경(몽키패치).
import sys, io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
import numpy as np
from src.controllers import leader as LD
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control

runner = importlib.import_module('run_claude_style_five_controller')

SC = sys.argv[1] if len(sys.argv) > 1 else 'sweet_170_incident_w'
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 30
WARM = 20

rows = []
_ref = LD.Leader.refined_candidates


def spy(self, state, center, previous=None, demand=None, forecast=None, count=None):
    cfg = self.cfg
    budget = max(5, int(count if count is not None else cfg.mpc.leader_refinement_candidate_count))
    b = self._candidate_bounds(state, previous, demand, forecast)
    n_np = max(3, int(round(np.sqrt(budget))))
    R = float(cfg.mpc.leader_local_np_radius_veh)
    span = b.np_upper - b.np_lower
    floor = span / max(2.0 * (n_np - 1), 1.0)
    eff = max(R, floor)
    out = _ref(self, state, center, previous, demand, forecast, count)
    nps = [a.N_P_star for a in out]
    # 최종 selected가 설정반경 40 밖으로 나가는가
    outside = sorted({v for v in nps
                      if v < center.N_P_star - R - 1e-6 or v > center.N_P_star + R + 1e-6})
    rows.append(dict(budget=budget, n_np=n_np, span=span, floor=floor, eff=eff,
                     cfg_wins=(R >= floor), center_np=float(center.N_P_star),
                     np_lo=b.np_lower, np_hi=b.np_upper,
                     sel_lo=min(nps), sel_hi=max(nps), n_outside=len(outside)))
    return out


LD.Leader.refined_candidates = spy

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

print("search_mode=%s  leader_candidate_count=%s  leader_refinement_candidate_count=%s"
      % (cfg.mpc.leader_search_mode, cfg.mpc.leader_candidate_count,
         cfg.mpc.leader_refinement_candidate_count))
print("leader_local_np_radius_veh=%s  skip_local_refinement=%s  global_refresh_sec=%s"
      % (cfg.mpc.leader_local_np_radius_veh,
         getattr(cfg.mpc, 'leader_skip_local_refinement', None),
         cfg.mpc.leader_global_refresh_sec))
print("N_P_star_range=%s" % (cfg.leader.N_P_star_range,))
print()

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
for step in range(STEPS):
    forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, forecast[0])
    else:
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, forecast, prev, cfg, step)
    sim.step(ctrl, forecast[0], step)
    prev = ctrl

print("refined_candidates 총 호출 = %d" % len(rows))
if not rows:
    print("!! 호출 0 — 라이브 경로 아님")
    sys.exit(0)

print()
print("%7s %5s %10s %10s %10s %8s %10s %8s" %
      ('budget', 'n_np', 'np_span', 'floor', 'eff_radius', 'cfg승?', 'center_NP', '40밖수'))
print('-' * 76)
for r in rows[:25]:
    print("%7d %5d %10.1f %10.1f %10.1f %8s %10.1f %8d" %
          (r['budget'], r['n_np'], r['span'], r['floor'], r['eff'],
           'YES' if r['cfg_wins'] else 'no', r['center_np'], r['n_outside']))

wins = sum(1 for r in rows if r['cfg_wins'])
print()
print("=== 요약 (n=%d 호출) ===" % len(rows))
print("설정값 40이 max()를 이긴 횟수 : %d / %d" % (wins, len(rows)))
print("floor 최소값                  : %.2f  (40보다 작으려면 span < %.0f)" %
      (min(r['floor'] for r in rows), 40 * 2 * (min(r['n_np'] for r in rows) - 1)))
print("floor 최대값                  : %.2f" % max(r['floor'] for r in rows))
print("np_span  min/max              : %.1f / %.1f" %
      (min(r['span'] for r in rows), max(r['span'] for r in rows)))
print("유효반경 eff min/max          : %.1f / %.1f" %
      (min(r['eff'] for r in rows), max(r['eff'] for r in rows)))
print("budget 값 집합                : %s" % sorted({r['budget'] for r in rows}))
print("최종 selected가 반경40 밖 후보를 포함한 호출: %d / %d" %
      (sum(1 for r in rows if r['n_outside'] > 0), len(rows)))
