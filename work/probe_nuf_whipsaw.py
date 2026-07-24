# N_UF* whipsaw 원인 규명 — 반경 미강제 vs V(N_UF) 평탄/다봉. 프로덕션 미변경(몽키패치).
# RADIUS_ENFORCE=1이면 refined_candidates 반환을 [center±radius]로 필터(앵커 포함 강제).
# 스텝별로 후보 (N_P,N_UF,objective,stage) 전체와 step TTT를 JSON으로 덤프한다.
import sys
import os
import json
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
from src.controllers import stackelberg_mpc as SM
from src.controllers import leader as LD
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control

runner = importlib.import_module('run_claude_style_five_controller')

SC = os.environ.get('SC', 'sweet_170_incident_w')
STEPS = int(os.environ.get('STEPS', '40'))
WARM = int(os.environ.get('WARMUP_NC_STEPS', '20'))
ENFORCE = os.environ.get('RADIUS_ENFORCE', '0') == '1'
OUT = os.environ.get('OUT', str(ROOT / 'work' / 'out_whipsaw.json'))
CTRL = 'P-STACK-WU-FAITHFUL-ALLPRICE-JOINT'

calls = {'refined': 0, 'global': 0, 'grid_search': 0, 'filtered_out': 0}
step_rec = {}
cur = {}

_ref = LD.Leader.refined_candidates
_glob = LD.Leader.candidates
_grid = SM.StackelbergMPCController._grid_leader_search


def spy_ref(self, state, center, previous=None, demand=None, forecast=None, count=None):
    out = _ref(self, state, center, previous, demand, forecast, count)
    calls['refined'] += 1
    R = float(self.cfg.mpc.leader_local_nuf_radius_veh_h)
    c = float(center.N_UF_star)
    raw = [float(a.N_UF_star) for a in out]
    if ENFORCE:
        keep = [a for a in out if abs(float(a.N_UF_star) - c) <= R + 1e-6]
        if not keep:
            keep = [out[0]]
        calls['filtered_out'] += len(out) - len(keep)
        out = keep
    cur.setdefault('ref_calls', []).append({
        'center_nuf': c, 'radius': R,
        'raw_lo': min(raw), 'raw_hi': max(raw), 'raw_n': len(raw),
        'kept_n': len(out),
        'kept_lo': min([float(a.N_UF_star) for a in out]),
        'kept_hi': max([float(a.N_UF_star) for a in out]),
        'n_outside_radius': sum(1 for v in raw if abs(v - c) > R + 1e-6),
    })
    return out


def spy_glob(self, state, previous=None, demand=None, forecast=None):
    out = _glob(self, state, previous, demand, forecast)
    calls['global'] += 1
    vals = [float(a.N_UF_star) for a in out]
    cur.setdefault('global_calls', []).append({'lo': min(vals), 'hi': max(vals), 'n': len(vals)})
    return out


def spy_grid(self, state, forecast, previous, global_refresh, fallback_incumbent_obj):
    evals, base_md, pmd, rpmd = _grid(self, state, forecast, previous, global_refresh, fallback_incumbent_obj)
    calls['grid_search'] += 1
    cur.setdefault('evals', []).extend([
        {'np': float(e.action.N_P_star), 'nuf': float(e.action.N_UF_star),
         'obj': float(e.objective), 'stage': str(e.stage)}
        for e in evals
    ])
    cur['global_refresh'] = bool(global_refresh)
    return evals, base_md, pmd, rpmd


LD.Leader.refined_candidates = spy_ref
LD.Leader.candidates = spy_glob
SM.StackelbergMPCController._grid_leader_search = spy_grid

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller(CTRL, cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

print('SC=%s STEPS=%d WARM=%d RADIUS_ENFORCE=%s' % (SC, STEPS, WARM, ENFORCE))
print('radius=%s  refresh=%ss(=%d steps)  skip_local_refine=%s' % (
    cfg.mpc.leader_local_nuf_radius_veh_h, cfg.mpc.leader_global_refresh_sec,
    round(cfg.mpc.leader_global_refresh_sec / 180),
    getattr(cfg.mpc, 'leader_skip_local_refinement', None)))
sys.stdout.flush()

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
prev_ttt = 0.0
rows = []
for step in range(STEPS):
    forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    cur.clear()
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, forecast[0])
    else:
        ctrl = runner.decide(CTRL, controller, sim, forecast, prev, cfg, step)
    sim.step(ctrl, forecast[0], step)
    ttt = float(sim.total_ttt)
    row = {
        'step': step, 'warm': step < WARM,
        'nuf': float(ctrl.N_UF_star), 'np': float(ctrl.N_P_star),
        'step_ttt': ttt - prev_ttt, 'cum_ttt': ttt,
    }
    if step >= WARM:
        row.update({k: v for k, v in cur.items()})
    rows.append(row)
    prev_ttt = ttt
    prev = ctrl
    if step >= WARM:
        rc = cur.get('ref_calls', [])
        gr = cur.get('global_refresh', None)
        print('step %2d %-6s nuf=%8.1f np=%7.1f stepTTT=%8.2f  ref_calls=%d %s' % (
            step, 'GLOBAL' if gr else 'local', row['nuf'], row['np'], row['step_ttt'], len(rc),
            ('cand[%.0f,%.0f] center=%.0f outside=%d' % (
                rc[0]['kept_lo'], rc[0]['kept_hi'], rc[0]['center_nuf'], rc[0]['n_outside_radius'])) if rc else ''))
        sys.stdout.flush()

json.dump({'meta': {'sc': SC, 'steps': STEPS, 'warm': WARM, 'enforce': ENFORCE,
                    'radius': float(cfg.mpc.leader_local_nuf_radius_veh_h), 'calls': calls},
           'rows': rows}, open(OUT, 'w', encoding='utf-8'))
win = [r for r in rows if not r['warm']]
print('\n== calls: %s' % calls)
print('== wTTT(window %d..%d) = %.2f' % (WARM, STEPS - 1, sum(r['step_ttt'] for r in win)))
print('== OUT=%s' % OUT)
