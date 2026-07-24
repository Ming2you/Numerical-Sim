# normalize의 출력폐쇄 분기가 실제 실행경로에서 no-op인지 실측 — 프로덕션 미변경(몽키패치).
import sys, io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
from src.controllers import stackelberg_mpc as SM
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control

runner = importlib.import_module('run_claude_style_five_controller')

SC = sys.argv[1] if len(sys.argv) > 1 else 'sweet_170_incident_w'
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 24
WARM = int(sys.argv[3]) if len(sys.argv) > 3 else 20

calls = []
_norm = SM.StackelbergMPCController._normalize_previous_leader_reference


def spy_norm(self, previous):
    diag = dict(getattr(previous, 'diagnostics', None) or {})
    in_nuf, in_np = float(previous.N_UF_star), float(previous.N_P_star)
    applied = float(diag.get('leader_output_closure_applied', 0.0))
    has_real = 'leader_realized_N_UF_star' in diag
    real_nuf = diag.get('leader_realized_N_UF_star', None)
    real_np = diag.get('leader_realized_N_P_star', None)
    int_nuf = diag.get('leader_intent_N_UF_star', None)
    out = _norm(self, previous)
    calls.append(dict(
        in_nuf=in_nuf, in_np=in_np, applied=applied, has_real=has_real,
        real_nuf=real_nuf, real_np=real_np, int_nuf=int_nuf,
        out_nuf=float(out.N_UF_star), out_np=float(out.N_P_star),
    ))
    return out


SM.StackelbergMPCController._normalize_previous_leader_reference = spy_norm

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

print("controller=%s  follower=%s" % (type(controller).__name__, type(controller.nash_solver).__name__))
print("price_iter_max=%s (>1이면 relax 경로 활성)" % getattr(controller, 'price_iter_max', None))
print("leader_value_depth=%s" % cfg.mpc.leader_value_depth)
print()

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
for step in range(STEPS):
    forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, forecast[0])
    else:
        n0 = len(calls)
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, forecast, prev, cfg, step)
        for c in calls[n0:]:
            c['step'] = step
        print("step %d: normalize 호출 %d회 / commit N_UF*=%.1f N_P*=%.1f"
              % (step, len(calls) - n0, ctrl.N_UF_star, ctrl.N_P_star))
    sim.step(ctrl, forecast[0], step)
    prev = ctrl

print()
print("=== normalize 호출 전수 ===")
def _f(v):
    return ('%.1f' % v) if v is not None else 'None'


print("%5s %8s | %9s %9s %9s | %9s %9s %9s | %6s" %
      ('step', 'applied', 'in_NUF', 'real_NUF', 'out_NUF', 'in_NP', 'real_NP', 'out_NP', 'noop?'))
print('-' * 96)
n_fire = n_change = 0
n_fire_change = 0
for c in calls:
    fired = c['applied'] >= 0.5
    n_fire += fired
    changed = abs(c['out_nuf'] - c['in_nuf']) > 1e-9 or abs(c['out_np'] - c['in_np']) > 1e-9
    n_change += changed
    if fired and changed:
        n_fire_change += 1
    print("%5s %8.1f | %9.1f %9s %9.1f | %9.1f %9s %9.1f | %6s" % (
        c.get('step', '-'), c['applied'], c['in_nuf'], _f(c['real_nuf']), c['out_nuf'],
        c['in_np'], _f(c['real_np']), c['out_np'],
        'NO' if changed else 'yes'))
print()
print("[핵심] 분기가 발화하면서 값을 바꾼 호출 = %d회" % n_fire_change)

print()
print("총 호출 %d회 / 분기 발화(applied>=0.5) %d회 / 입출력 변화 %d회" % (len(calls), n_fire, n_change))
print("→ 분기가 발화한 적 있는가? %s" % (n_fire > 0))
print("→ 분기가 값을 바꾼 적 있는가(=no-op 아님)? %s" % (n_change > 0))
fired_calls = [c for c in calls if c['applied'] >= 0.5]
if fired_calls:
    same_as_real = all(abs(c['in_nuf'] - (c['real_nuf'] if c['real_nuf'] is not None else c['in_nuf'])) < 1e-9
                       for c in fired_calls)
    print("→ 발화 시 입력 N_UF == realized 였는가(=대입이 같은 값)? %s" % same_as_real)
    print("→ 발화 시 intent != realized 였는가(=intent 시딩이면 달랐을 것)? %s"
          % any(c['int_nuf'] is not None and c['real_nuf'] is not None
                and abs(c['int_nuf'] - c['real_nuf']) > 1e-6 for c in fired_calls))
