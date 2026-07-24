# ④_nuf_anchor_values만 제거해도 후보 범위가 그대로인지(과결정)를 실제 실행경로에서 검증 — 프로덕션 미변경.
import sys, io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
from src.controllers import leader as LD
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control

runner = importlib.import_module('run_claude_style_five_controller')

SC = 'sweet_170_incident_w'
STEPS = 27
WARM = 20

_ref = LD.Leader.refined_candidates
_anchor = LD.Leader._nuf_anchor_values
rows = []
_depth = {'n': 0}


def spy_ref(self, state, center, previous=None, demand=None, forecast=None, count=None):
    out = _ref(self, state, center, previous, demand, forecast, count)
    if _depth['n'] > 0:            # 재귀(대조군 호출) 중이면 기록하지 않음
        return out
    b = self._candidate_bounds(state, previous, demand, forecast)
    full = [a.N_UF_star for a in out]

    # 대조군: ④만 제거한 채 진짜 refined_candidates를 다시 호출
    _depth['n'] += 1
    LD.Leader._nuf_anchor_values = lambda s, bo, pr=None: set()
    try:
        out4 = _ref(self, state, center, previous, demand, forecast, count)
    finally:
        LD.Leader._nuf_anchor_values = _anchor
        _depth['n'] -= 1
    no4 = [a.N_UF_star for a in out4]

    rows.append(dict(
        center=float(center.N_UF_star),
        lo=b.nuf_lower, hi=b.nuf_upper, heur=b.heuristic_nuf,
        full=(min(full), max(full)), no4=(min(no4), max(no4)),
    ))
    return out


LD.Leader.refined_candidates = spy_ref

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

R = float(cfg.mpc.leader_local_nuf_radius_veh_h)
print("반경=%.0f  total_ramp_capacity=%.0f" % (R, cfg.network.total_ramp_capacity), flush=True)

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
for step in range(STEPS):
    forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    rows.clear()
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, forecast[0])
    else:
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, forecast, prev, cfg, step)
        if rows:
            r = rows[0]
            rlo, rhi = max(r['lo'], r['center'] - R), min(r['hi'], r['center'] + R)
            print("step%-3d center=%-7.0f bounds=[%.0f,%.0f] heuristic=%-7.1f 반경대로=[%.0f,%.0f]"
                  % (step, r['center'], r['lo'], r['hi'], r['heur'], rlo, rhi), flush=True)
            print("        전체후보=[%.0f,%.0f]   ④제외후보=[%.0f,%.0f]   heur<lower? %s   ④제외로복원? %s"
                  % (r['full'][0], r['full'][1], r['no4'][0], r['no4'][1],
                     r['heur'] < r['lo'],
                     abs(r['no4'][0] - rlo) < 1 and abs(r['no4'][1] - rhi) < 1), flush=True)
        else:
            print("step%-3d refined_candidates 호출 없음(GLOBAL 스텝)" % step, flush=True)
    sim.step(ctrl, forecast[0], step)
    prev = ctrl
