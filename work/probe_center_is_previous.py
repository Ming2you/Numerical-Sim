# trust-region 앵커가 previous인지 PFO incumbent center인지 폐루프 실측 — 프로덕션 미변경(몽키패치).
import sys, io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
from src.controllers import leader as LD
from src.controllers import stackelberg_wu_metered as WM
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control

runner = importlib.import_module('run_claude_style_five_controller')

SC = sys.argv[1] if len(sys.argv) > 1 else 'sweet_170_incident_w'
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 28
WARM = 20

rec = {}

_grid = WM.StackelbergWuMeteredController._grid_leader_search
_centered = WM.StackelbergWuMeteredController._pfo_centered_previous
_ref = LD.Leader.refined_candidates


def spy_grid(self, state, forecast, previous, global_refresh, fallback_incumbent_obj):
    rec['prev_in'] = float(previous.N_UF_star)          # decide()가 받은 진짜 직전 행동
    rec['global_refresh'] = bool(global_refresh)
    c = getattr(self, '_pfo_incumbent_center', None)
    rec['pfo_center'] = float(c.N_UF_star) if c is not None else None
    return _grid(self, state, forecast, previous, global_refresh, fallback_incumbent_obj)


def spy_centered(self, previous):
    out = _centered(self, previous)
    rec['centered_out'] = float(out.N_UF_star)
    return out


def spy_ref(self, state, center, previous=None, demand=None, forecast=None, count=None):
    rec.setdefault('ref_centers', []).append(float(center.N_UF_star))
    return _ref(self, state, center, previous, demand, forecast, count)


WM.StackelbergWuMeteredController._grid_leader_search = spy_grid
WM.StackelbergWuMeteredController._pfo_centered_previous = spy_centered
LD.Leader.refined_candidates = spy_ref

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

print("pfo_incumbent enabled = %s" % controller._pfo_incumbent_fallback_enabled())
print("search_mode = %s" % cfg.mpc.leader_search_mode)
print("radius = %s" % cfg.mpc.leader_local_nuf_radius_veh_h)
print()
print("%5s %9s %12s %12s %12s %12s %s" %
      ('step', 'refresh', 'prev(진짜)', 'PFO center', 'centered→', 'coarse중심', '판정'))
print('-' * 88)

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
for step in range(STEPS):
    forecast = profile.horizon(sim.state.time_sec,
                               cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    rec.clear()
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, forecast[0])
    else:
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, forecast, prev, cfg, step)
        p = rec.get('prev_in')
        pc = rec.get('pfo_center')
        co = rec.get('centered_out')
        rc = rec.get('ref_centers', [])
        first_rc = rc[0] if rc else None
        if p is None:
            verdict = 'grid 미호출'
        elif co is None:
            verdict = 'centered 미호출'
        elif abs(co - p) < 1e-6:
            verdict = 'center==previous (지적 반증)'
        elif pc is not None and abs(co - pc) < 1e-6:
            verdict = '★center==PFO≠previous (지적 성립)'
        else:
            verdict = '기타'
        fmt = lambda v: ('%12.0f' % v) if v is not None else '%12s' % '-'
        print("%5d %9s %s %s %s %s  %s" %
              (step, rec.get('global_refresh'), fmt(p), fmt(pc), fmt(co), fmt(first_rc), verdict))
    sim.step(ctrl, forecast[0], step)
    prev = ctrl
