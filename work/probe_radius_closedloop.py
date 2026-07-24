# 폐루프에서 refined_candidates 호출만 분리 계측(candidates()와 섞지 않음) — 읽기 전용 몽키패치.
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
STEPS = int(sys.argv[1]) if len(sys.argv) > 1 else 23
WARM = 20

calls = []
_ref = LD.Leader.refined_candidates
_glob = LD.Leader.candidates

def spy_ref(self, state, center, previous=None, demand=None, forecast=None, count=None):
    out = _ref(self, state, center, previous, demand, forecast, count)
    v = [a.N_UF_star for a in out]
    calls.append(('refined', float(center.N_UF_star), min(v), max(v), len(out)))
    return out

def spy_glob(self, state, previous=None, demand=None, forecast=None):
    out = _glob(self, state, previous, demand, forecast)
    v = [a.N_UF_star for a in out]
    calls.append(('candidates(GLOBAL)', float('nan'), min(v), max(v), len(out)))
    return out

LD.Leader.refined_candidates = spy_ref
LD.Leader.candidates = spy_glob

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True
R = float(cfg.mpc.leader_local_nuf_radius_veh_h)
print("radius=%s, global_refresh_sec=%s" % (R, cfg.mpc.leader_global_refresh_sec))

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
for step in range(STEPS):
    fc = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    if step < WARM:
        ctrl = baseline_control('no_control', cfg, sim.state, fc[0])
    else:
        calls.clear()
        ctrl = runner.decide('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', controller, sim, fc, prev, cfg, step)
        print("\n--- step %d : 선택된 N_UF*=%.0f ---" % (step, ctrl.N_UF_star))
        for kind, c, lo, hi, n in calls:
            if kind == 'refined':
                viol = "  ★반경밖 포함" if (lo < c - R - 1 or hi > c + R + 1) else ""
                print("   %-20s center=%7.0f  후보=[%6.0f, %6.0f] n=%d%s" % (kind, c, lo, hi, n, viol))
            else:
                print("   %-20s center=%7s  후보=[%6.0f, %6.0f] n=%d" % (kind, '-', lo, hi, n))
        sys.stdout.flush()
    sim.step(ctrl, fc[0], step)
    prev = ctrl
