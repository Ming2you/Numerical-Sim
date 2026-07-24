# 실제 closed-loop refined_candidates 호출 지점에서 N_UF 후보 소스별 반경밖 기여를 귀속 — 프로덕션 미변경(몽키패치).
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

SC = 'sweet_170_incident_w'
STEPS = 30
WARM = 20

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

R = float(cfg.mpc.leader_local_nuf_radius_veh_h)
_ref = LD.Leader.refined_candidates
CUR = {'step': -1}
rows = []


def spy(self, state, center, previous=None, demand=None, forecast=None, count=None):
    out = _ref(self, state, center, previous, demand, forecast, count)
    # 내부 로직을 실제 인자로 재현
    d = self._forecast_demand_summary(list(forecast)) if forecast else demand
    budget = max(5, int(count if count is not None else self.cfg.mpc.leader_refinement_candidate_count))
    n_np = max(3, int(round(np.sqrt(budget))))
    n_nuf = max(3, int(np.ceil(budget / n_np)))
    b = self._candidate_bounds(state, previous, d, forecast)
    nuf_radius = max(R, (b.nuf_upper - b.nuf_lower) / max(2.0 * (n_nuf - 1), 1.0))
    lo = max(b.nuf_lower, center.N_UF_star - nuf_radius)
    hi = min(b.nuf_upper, center.N_UF_star + nuf_radius)

    src = {}
    src['grid'] = set(float(v) for v in np.linspace(lo, hi, n_nuf))
    src['center'] = {float(np.clip(center.N_UF_star, b.nuf_lower, b.nuf_upper))}
    src['heur'] = {float(np.clip(b.heuristic_nuf, b.nuf_lower, b.nuf_upper))}
    src['anchors'] = set(float(x) for x in self._nuf_anchor_values(b, previous))
    if previous is not None:
        src['prevtgt'] = {float(np.clip(self._previous_nuf_target(previous), b.nuf_lower, b.nuf_upper))}

    def outside(vals):
        return sorted(x for x in vals if x < lo - 1e-6 or x > hi + 1e-6)

    rows.append({
        'step': CUR['step'], 'center': float(center.N_UF_star),
        'win': (lo, hi), 'bounds': (b.nuf_lower, b.nuf_upper),
        'heur': b.heuristic_nuf, 'radius': nuf_radius,
        'out': {k: outside(v) for k, v in src.items()},
        'src': {k: sorted(v) for k, v in src.items()},
        'cand': (min(a.N_UF_star for a in out), max(a.N_UF_star for a in out)),
    })
    return out


LD.Leader.refined_candidates = spy

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
for step in range(STEPS):
    CUR['step'] = step
    forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, forecast[0])
    else:
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, forecast, prev, cfg, step)
    sim.step(ctrl, forecast[0], step)
    prev = ctrl

print("설정 반경 R = %.0f" % R)
print()
for r in rows:
    if r['step'] not in (21, 26):
        continue
    print("=== step %d  center=%.0f  실효반경=%.0f  반경창=[%.0f, %.0f]  bounds=[%.0f, %.0f]" % (
        r['step'], r['center'], r['radius'], r['win'][0], r['win'][1], r['bounds'][0], r['bounds'][1]))
    print("    후보 N_UF 실제 범위 = [%.0f, %.0f]" % (r['cand'][0], r['cand'][1]))
    print("    heuristic_nuf = %.1f" % r['heur'])
    for k in r['src']:
        o = r['out'][k]
        print("    %-9s vals=%-46s 반경밖=%s" % (
            k, [round(x) for x in r['src'][k]], [round(x) for x in o] if o else '없음'))
    # anchors 제거 시 범위
    keep = set()
    for k, v in r['src'].items():
        if k != 'anchors':
            keep.update(v)
    print("    anchors 제외 시 nuf_values 범위 = [%.0f, %.0f]" % (min(keep), max(keep)))
    print()

# 전 스텝 요약: 반경밖 값을 만드는 소스별 카운트
from collections import Counter
cnt = Counter()
for r in rows:
    for k, o in r['out'].items():
        if o:
            cnt[k] += 1
print("전체 %d개 refined_candidates 호출 중 반경밖 값을 기여한 호출 수:" % len(rows))
for k, v in cnt.most_common():
    print("   %-9s %d" % (k, v))
# anchors 없이도 반경밖이 생기는 호출
solo = [r['step'] for r in rows if any(o for k, o in r['out'].items() if k != 'anchors')]
print("anchors 이외 소스가 반경밖을 만든 호출 step =", sorted(set(solo)) if solo else '없음')
