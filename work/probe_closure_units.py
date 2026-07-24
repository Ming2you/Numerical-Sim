# 폐쇄(_apply_output_closure)가 run_log N_UF*를 intent에서 realized로 바꾸는지 실측 — 프로덕션 미변경.
# 검증 대상: "run_log N_UF*는 intent가 아니라 realized" 지적이 사실인지.
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
from src.controllers import stackelberg_mpc as SM
from src.controllers import leader as LD
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control

runner = importlib.import_module('run_claude_style_five_controller')

SC = sys.argv[1] if len(sys.argv) > 1 else 'sweet_170_incident_w'
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 23
WARM = int(sys.argv[3]) if len(sys.argv) > 3 else 20

# --- 계측 1: 폐쇄 진입 시점의 N_UF_star(=intent, 폐쇄 전)와 종료 후 값(realized)을 포착 ---
closure_trace = []
_closure = SM.StackelbergMPCController._apply_output_closure


def spy_closure(self, best, state, forecast):
    before = float(best.control.N_UF_star)
    _closure(self, best, state, forecast)
    after = float(best.control.N_UF_star)
    d = best.control.diagnostics
    closure_trace.append({
        'before_nuf': before,
        'after_nuf': after,
        'intent_diag': float(d.get('leader_intent_N_UF_star', float('nan'))),
        'realized_diag': float(d.get('leader_realized_N_UF_star', float('nan'))),
        'applied': float(d.get('leader_output_closure_applied', -1.0)),
        'ramp_sum': sum(float(v) for v in best.control.ramp_metering.values()),
    })


SM.StackelbergMPCController._apply_output_closure = spy_closure

# --- 계측 2: refined_candidates의 center와 후보 N_UF 범위(반경 준수 여부) ---
cand_trace = []
_ref = LD.Leader.refined_candidates


def spy_ref(self, state, center, previous=None, demand=None, forecast=None, count=None):
    out = _ref(self, state, center, previous, demand, forecast, count)
    vals = [a.N_UF_star for a in out]
    cand_trace.append((float(center.N_UF_star), min(vals), max(vals)))
    return out


LD.Leader.refined_candidates = spy_ref

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

RAD = float(cfg.mpc.leader_local_nuf_radius_veh_h)
print("반경 설정: leader_local_nuf_radius_veh_h = %s" % RAD)
print("skip_local_refinement = %s" % getattr(cfg.mpc, 'leader_skip_local_refinement', None))
print()

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
prev_nuf = None
prev_intent = None

hdr = "%5s %11s %11s %9s %9s %11s %11s" % (
    'step', 'intent', 'realized', '폐쇄적용', '동일?', 'Δrealized', 'Δintent')
print(hdr)
print('-' * len(hdr))

for step in range(STEPS):
    forecast = profile.horizon(sim.state.time_sec,
                              cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    closure_trace.clear()
    cand_trace.clear()
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, forecast[0])
    else:
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim,
                             forecast, prev, cfg, step)
        logged = float(ctrl.N_UF_star)          # run_log가 기록하는 바로 그 값
        ct = closure_trace[-1] if closure_trace else None
        if ct is None:
            print("%5d  폐쇄 미호출(!) logged=%.0f" % (step, logged))
        else:
            same = 'YES' if abs(ct['before_nuf'] - ct['after_nuf']) < 1e-6 else 'NO'
            dr = ('%+11.0f' % (logged - prev_nuf)) if prev_nuf is not None else '%11s' % '-'
            di = ('%+11.0f' % (ct['before_nuf'] - prev_intent)) if prev_intent is not None else '%11s' % '-'
            print("%5d %11.0f %11.0f %9.0f %9s %s %s" % (
                step, ct['before_nuf'], ct['after_nuf'], ct['applied'], same, dr, di))
            # 후보집합 반경 준수(intent 공간) — 독립 증거
            for (c, lo, hi) in cand_trace:
                viol = '  ★반경위반' if (lo < c - RAD - 1 or hi > c + RAD + 1) else ''
                print("        후보: center=%.0f 범위=[%.0f, %.0f] 반경대로면=[%.0f, %.0f]%s" % (
                    c, lo, hi, c - RAD, c + RAD, viol))
            prev_nuf = logged
            prev_intent = ct['before_nuf']
    sim.step(ctrl, forecast[0], step)
    prev = ctrl
