# coarse_local(stackelberg_mpc.py:771) 후보집합이 previous 주변 trust-region인지 폐루프 실측 — 프로덕션 미변경(몽키패치)
import sys, io, os
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
STEPS = 28
WARM = 20

rec = []
_ref = LD.Leader.refined_candidates


def spy(self, state, center, previous=None, demand=None, forecast=None, count=None):
    out = _ref(self, state, center, previous, demand, forecast, count)
    b = self._candidate_bounds(state, previous, demand, forecast)
    vals = [a.N_UF_star for a in out]
    # count is not None  <=> coarse_local call site (stackelberg_mpc.py:771..778)
    rec.append(dict(
        stage='coarse_local' if count is not None else 'refined',
        center=float(center.N_UF_star),
        lo=min(vals), hi=max(vals), n=len(out),
        bl=float(b.nuf_lower), bu=float(b.nuf_upper),
        prev_nuf=(float(previous.N_UF_star) if previous is not None else float('nan')),
    ))
    return out


LD.Leader.refined_candidates = spy

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True
R = float(cfg.mpc.leader_local_nuf_radius_veh_h)
print("radius R = %.0f | search_mode=%s | cand_count=%d | refresh=%.0fs"
      % (R, cfg.mpc.leader_search_mode, cfg.mpc.leader_candidate_count,
         cfg.mpc.leader_global_refresh_sec))
print()

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
print("%4s %12s %8s %8s %11s %11s %13s %s"
      % ('step', 'stage', 'center', 'prevNUF', 'cand_lo', 'cand_hi', 'bounds', 'TR?'))
print('-' * 92)
for step in range(STEPS):
    forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    rec.clear()
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, forecast[0])
    else:
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, forecast, prev, cfg, step)
        for r in rec:
            if r['stage'] != 'coarse_local':
                continue
            # trust region around center would be [center-R, center+R] ∩ bounds
            tr_lo = max(r['bl'], r['center'] - R)
            tr_hi = min(r['bu'], r['center'] + R)
            inside = (r['lo'] >= tr_lo - 1) and (r['hi'] <= tr_hi + 1)
            full = (abs(r['lo'] - r['bl']) < 1) and (abs(r['hi'] - r['bu']) < 1)
            tag = 'TR-OK' if inside else ('FULL-BOUNDS' if full else 'WIDER-THAN-TR')
            print("%4d %12s %8.0f %8.0f %11.0f %11.0f  [%5.0f,%5.0f] %s  (TR would be [%.0f,%.0f], n=%d)"
                  % (step, r['stage'], r['center'], r['prev_nuf'], r['lo'], r['hi'],
                     r['bl'], r['bu'], tag, tr_lo, tr_hi, r['n']))
    sim.step(ctrl, forecast[0], step)
    prev = ctrl
