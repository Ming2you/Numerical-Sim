"""리더 목적함수 2-D 지도 V(N_P, N_UF) — 진짜 최적이 어디인가.

1-D 절단면(N_P 고정)은 단조감소였으나(min @ N_UF=6000), 실제 리더는 경계를 안 고른다.
=> N_P와 결합해서 봐야 한다. 후보 격자를 안 쓰고 두 축을 등간격으로 훑는다.
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
AT = int(sys.argv[2]) if len(sys.argv) > 2 else 25
N = int(sys.argv[3]) if len(sys.argv) > 3 else 7
WARM = 20

cfg, scenario = runner.build_cfg(SC, (AT + 2) * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
chosen = None
for step in range(AT):
    fc = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, fc[0])
    else:
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, fc, prev, cfg, step)
        d = ctrl.diagnostics or {}
        chosen = (d.get('leader_intent_N_P_star'), d.get('leader_intent_N_UF_star'))
    sim.step(ctrl, fc[0], step)
    prev = ctrl

st = sim.state
fc = profile.horizon(st.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
ld = controller.leader
b = ld._candidate_bounds(st, prev, None, fc)
pn = controller._normalize_previous_leader_reference(prev)

print("### V(N_P, N_UF) 2-D 지도 — %s, step %d" % (SC, AT))
print("bounds  N_P [%.0f, %.0f]   N_UF [%.0f, %.0f]" % (b.np_lower, b.np_upper, b.nuf_lower, b.nuf_upper))
print("직전 스텝 리더 intent: N_P=%s  N_UF=%s" % (
    ('%.0f' % chosen[0]) if chosen and chosen[0] is not None else '?',
    ('%.0f' % chosen[1]) if chosen and chosen[1] is not None else '?'))
print()

nps = np.linspace(b.np_lower, b.np_upper, N)
nufs = np.linspace(b.nuf_lower, b.nuf_upper, N)
V = {}
for i, p in enumerate(nps):
    for j, u in enumerate(nufs):
        try:
            ev = controller._evaluate_full_candidate(
                0, LeaderAction(float(p), float(u)), st.copy(), fc, pn,
                "probe", float('inf'), float('inf'))
            V[(i, j)] = float(ev.objective)
        except Exception:
            V[(i, j)] = None

vals = [v for v in V.values() if v is not None]
lo, hi = min(vals), max(vals)
best = min((v, k) for k, v in V.items() if v is not None)[1]

print("행=N_P(위가 큰 값)  열=N_UF(오른쪽이 큼).  숫자 = (V−min)/(max−min)×99, 00=최적")
print("%9s | %s" % ('N_P \\ N_UF', ' '.join('%5.0f' % u for u in nufs)))
print('-' * (12 + 6 * N))
for i in range(N - 1, -1, -1):
    cells = []
    for j in range(N):
        v = V[(i, j)]
        if v is None:
            cells.append('   --')
            continue
        z = int(round((v - lo) / max(hi - lo, 1e-9) * 99))
        cells.append(('  %02d*' % z) if (i, j) == best else ('  %02d ' % z))
    print("%9.0f | %s" % (nps[i], ' '.join(cells)))
print()
print("  V 범위 = [%.2f, %.2f]  (변동 %.1f%%)" % (lo, hi, (hi - lo) / max(abs(lo), 1e-9) * 100))
print("  ★최적 = N_P=%.0f, N_UF=%.0f  (V=%.2f)" % (nps[best[0]], nufs[best[1]], lo))
edge_p = best[0] in (0, N - 1)
edge_u = best[1] in (0, N - 1)
print("  최적 위치: N_P %s / N_UF %s" % ('경계' if edge_p else '내부', '경계' if edge_u else '내부'))
# 2-D 국소최소 개수
loc = 0
for i in range(1, N - 1):
    for j in range(1, N - 1):
        v = V[(i, j)]
        if v is None:
            continue
        nb = [V.get((i + di, j + dj)) for di in (-1, 0, 1) for dj in (-1, 0, 1) if (di, dj) != (0, 0)]
        nb = [x for x in nb if x is not None]
        if nb and all(v < x for x in nb):
            loc += 1
print("  내부 국소최소 %d개 → %s" % (loc, "★다봉" if loc > 1 else "단봉"))
