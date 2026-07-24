# 라이브 플래그십 런에서 leader 후보집합의 N_P 축 커버리지를 계측 — 프로덕션 미변경(몽키패치).
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
STEPS = 32
WARM = 20

records = []
_ref = LD.Leader.refined_candidates
_glob = LD.Leader.candidates


def spy_ref(self, state, center, previous=None, demand=None, forecast=None, count=None):
    out = _ref(self, state, center, previous, demand, forecast, count)
    b = self._candidate_bounds(state, previous, demand, forecast)
    budget = max(5, int(count if count is not None else self.cfg.mpc.leader_refinement_candidate_count))
    records.append(dict(
        kind='refined(count=%s)' % ('None->%d' % budget if count is None else count),
        center_np=float(center.N_P_star), center_nuf=float(center.N_UF_star),
        nps=sorted({a.N_P_star for a in out}), n=len(out),
        np_lo=b.np_lower, np_hi=b.np_upper,
    ))
    return out


def spy_glob(self, state, previous=None, demand=None, forecast=None):
    out = _glob(self, state, previous, demand, forecast)
    b = self._candidate_bounds(state, previous, demand, forecast)
    records.append(dict(
        kind='GLOBAL candidates()',
        center_np=float('nan'), center_nuf=float('nan'),
        nps=sorted({a.N_P_star for a in out}), n=len(out),
        np_lo=b.np_lower, np_hi=b.np_upper,
    ))
    return out


LD.Leader.refined_candidates = spy_ref
LD.Leader.candidates = spy_glob

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
for step in range(STEPS):
    fc = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    records.clear()
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, fc[0])
    else:
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, fc, prev, cfg, step)
        print("\n===== step %d =====  (chosen N_P*=%.0f, N_UF*=%.0f)" % (step, ctrl.N_P_star, ctrl.N_UF_star))
        for r in records:
            span = max(r['np_hi'] - r['np_lo'], 1e-9)
            reach = 100.0 * (max(r['nps']) - r['np_lo']) / span
            print("  %-22s n=%3d center_np=%8.1f | 고유N_P %2d개 max=%8.1f (bounds[%.0f,%.0f] 도달 %5.1f%%)"
                  % (r['kind'], r['n'], r['center_np'], len(r['nps']), max(r['nps']),
                     r['np_lo'], r['np_hi'], reach))
            print("      N_P set: %s" % [round(v) for v in r['nps']][:12])
    sim.step(ctrl, fc[0], step)
    prev = ctrl
