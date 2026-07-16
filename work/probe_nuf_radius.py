# N_UF 이동이 국소 반경(leader_local_nuf_radius_veh_h)을 넘는지 계측 — 프로덕션 미변경(몽키패치).
# 관측: 170_incident_w에서 step25→26에 N_UF가 6000→4231(−1769). 반경 1500이면 불가능.
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
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 30
WARM = 20

trace = []          # (kind, center, lo, hi)
_ref = LD.Leader.refined_candidates
_glob = LD.Leader.candidates


def spy_ref(self, state, center, previous=None, demand=None, forecast=None, count=None):
    out = _ref(self, state, center, previous, demand, forecast, count)
    vals = [a.N_UF_star for a in out]
    trace.append(('local', float(center.N_UF_star), min(vals), max(vals)))
    return out


def spy_glob(self, state, previous=None, demand=None, forecast=None):
    out = _glob(self, state, previous, demand, forecast)
    vals = [a.N_UF_star for a in out]
    trace.append(('GLOBAL', float('nan'), min(vals), max(vals)))
    return out


LD.Leader.refined_candidates = spy_ref
LD.Leader.candidates = spy_glob

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

print("반경 설정: leader_local_nuf_radius_veh_h = %s" % cfg.mpc.leader_local_nuf_radius_veh_h)
print("전역 주기: leader_global_refresh_sec = %s (= %d스텝마다)" %
      (cfg.mpc.leader_global_refresh_sec, round(cfg.mpc.leader_global_refresh_sec / 180)))
print()

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
prev_nuf = None
print("%5s %8s %10s %12s %12s %10s" % ('step', '종류', 'center', '후보최소', '후보최대', 'Δ실제'))
print('-' * 62)
for step in range(STEPS):
    forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    trace.clear()
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, forecast[0])
    else:
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, forecast, prev, cfg, step)
        nuf = float(ctrl.N_UF_star)
        kinds = {t[0] for t in trace}
        kind = 'GLOBAL' if 'GLOBAL' in kinds else 'local'
        centers = [t[1] for t in trace if t[0] == 'local']
        lo = min((t[2] for t in trace), default=float('nan'))
        hi = max((t[3] for t in trace), default=float('nan'))
        d = ('%+10.0f' % (nuf - prev_nuf)) if prev_nuf is not None else '%10s' % '-'
        c = ('%10.0f' % centers[0]) if centers else '%10s' % '-'
        viol = ''
        if centers and abs(nuf - centers[0]) > float(cfg.mpc.leader_local_nuf_radius_veh_h) + 1:
            viol = '  ★반경위반'
        print("%5d %8s %s %12.0f %12.0f %s%s" % (step, kind, c, lo, hi, d, viol))
        prev_nuf = nuf
    sim.step(ctrl, forecast[0], step)
    prev = ctrl
