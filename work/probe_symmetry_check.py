# continuous vs grid 두 경로의 반경 강제 여부를 동일 조건에서 대조 계측 — 프로덕션 미변경.
import sys, io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control
from src.controllers.leader import LeaderAction

runner = importlib.import_module('run_claude_style_five_controller')

SC = 'sweet_170_incident_w'
cfg, scenario = runner.build_cfg(SC, 30 * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
if hasattr(controller, 'nash_solver'):
    controller.nash_solver.segment_agents = True

R = float(cfg.mpc.leader_local_nuf_radius_veh_h)
leader = controller.leader
profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
state = sim.state
prev = baseline_control('no_control', cfg, state, forecast[0])

# previous.N_UF_star 를 4000으로 세팅해 반경창 [2500,5500] 이 bounds 안쪽에 오도록
prev.N_UF_star = 4000.0
bounds = leader._candidate_bounds(state, prev, forecast[0], forecast)
print("radius=%.0f  bounds=[%.0f, %.0f]  previous.N_UF*=%.0f" %
      (R, bounds.nuf_lower, bounds.nuf_upper, prev.N_UF_star))
print("반경창(기대) = [%.0f, %.0f]" % (max(bounds.nuf_lower, 4000 - R), min(bounds.nuf_upper, 4000 + R)))
print("anchors =", sorted(round(v) for v in leader._nuf_anchor_values(bounds, prev)))
print()

# --- 경로 A: grid local 스텝의 coarse = refined_candidates(center=previous) ---
center = LeaderAction(float(prev.N_P_star), float(prev.N_UF_star))
grid_out = leader.refined_candidates(state, center, prev, forecast[0], forecast=forecast,
                                     count=cfg.mpc.leader_candidate_count)
g = [a.N_UF_star for a in grid_out]
print("[A] grid  local coarse  N_UF 범위 = [%.0f, %.0f]  n=%d" % (min(g), max(g), len(g)))

# --- 경로 B: continuous local 스텝의 seed actions ---
np_lower, np_upper = float(bounds.np_lower), float(bounds.np_upper)
nuf_lower, nuf_upper = float(bounds.nuf_lower), float(bounds.nuf_upper)
# _continuous_leader_search 의 911-915 재현 (global_refresh=False)
np_lower_l = max(np_lower, float(prev.N_P_star) - float(cfg.mpc.leader_local_np_radius_veh))
np_upper_l = min(np_upper, float(prev.N_P_star) + float(cfg.mpc.leader_local_np_radius_veh))
nuf_lower_l = max(nuf_lower, float(prev.N_UF_star) - R)
nuf_upper_l = min(nuf_upper, float(prev.N_UF_star) + R)


def clipped(np_value, nuf_value):
    return LeaderAction(
        float(min(max(float(np_value), np_lower_l), np_upper_l)),
        float(min(max(float(nuf_value), nuf_lower_l), nuf_upper_l)),
    )


seeds = controller._continuous_seed_actions(
    prev, bounds, np_lower_l, np_upper_l, nuf_lower_l, nuf_upper_l, clipped,
)
c = [a.N_UF_star for a in seeds]
print("[B] continuous local seeds N_UF 범위 = [%.0f, %.0f]  n=%d" % (min(c), max(c), len(c)))
print()

a_viol = min(g) < max(bounds.nuf_lower, 4000 - R) - 1 or max(g) > min(bounds.nuf_upper, 4000 + R) + 1
b_viol = min(c) < nuf_lower_l - 1 or max(c) > nuf_upper_l + 1
print("A(grid)       반경위반 =", a_viol)
print("B(continuous) 반경위반 =", b_viol)
