# 후보 범위를 전체 bounds로 벌리는 앵커 소스를 개별 귀속 — 소스별 기여를 실측(프로덕션 미변경).
import sys, io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
import numpy as np
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control
from src.controllers.leader import LeaderAction

runner = importlib.import_module('run_claude_style_five_controller')
cfg, scenario = runner.build_cfg('sweet_170_incident_w', 30 * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
leader = controller.leader
R = float(cfg.mpc.leader_local_nuf_radius_veh_h)

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
state = sim.state
prev = baseline_control('no_control', cfg, state, forecast[0])
bounds = leader._candidate_bounds(state, prev, forecast[0], forecast)

center_v = 6000.0
center = LeaderAction(float(prev.N_P_star), center_v)

# refined_candidates 내부 각 소스를 그대로 재현해 개별 기여를 본다.
budget = max(5, int(cfg.mpc.leader_refinement_candidate_count))
n_np = max(3, int(round(np.sqrt(budget))))
n_nuf = max(3, int(np.ceil(budget / n_np)))
nuf_radius = max(R, (bounds.nuf_upper - bounds.nuf_lower) / max(2.0 * (n_nuf - 1), 1.0))
nuf_low = max(bounds.nuf_lower, center.N_UF_star - nuf_radius)
nuf_high = min(bounds.nuf_upper, center.N_UF_star + nuf_radius)

print("center=%.0f  설정반경=%.0f  실효 nuf_radius=%.0f" % (center_v, R, nuf_radius))
print("반경격자 linspace(%.0f, %.0f, %d) = %s" %
      (nuf_low, nuf_high, n_nuf, [round(v) for v in np.linspace(nuf_low, nuf_high, n_nuf)]))
print()

src = {}
src['①반경격자'] = set(float(v) for v in np.linspace(nuf_low, nuf_high, n_nuf))
src['②center'] = {float(np.clip(center.N_UF_star, bounds.nuf_lower, bounds.nuf_upper))}
src['③heuristic_nuf'] = {float(np.clip(bounds.heuristic_nuf, bounds.nuf_lower, bounds.nuf_upper))}
src['④_nuf_anchor_values'] = set(leader._nuf_anchor_values(bounds, prev))
src['⑤previous_nuf_target'] = {float(np.clip(leader._previous_nuf_target(prev), bounds.nuf_lower, bounds.nuf_upper))}

print("%-22s %-42s %s" % ('소스', '기여 N_UF 값', '반경밖?'))
print('-' * 86)
for k, v in src.items():
    outside = sorted(x for x in v if x < nuf_low - 1 or x > nuf_high + 1)
    print("%-22s %-42s %s" % (k, sorted(round(x) for x in v),
                             ('예 → ' + str([round(x) for x in outside])) if outside else '아니오'))

print()
# ④를 뺐을 때 범위가 반경을 지키는가?
without4 = set().union(src['①반경격자'], src['②center'], src['③heuristic_nuf'], src['⑤previous_nuf_target'])
allsrc = set().union(*src.values())
print("④ 포함 전체 nuf_values 범위 = [%.0f, %.0f]" % (min(allsrc), max(allsrc)))
print("④ 제외 시        범위 = [%.0f, %.0f]" % (min(without4), max(without4)))
print("bounds 전체            = [%.0f, %.0f]" % (bounds.nuf_lower, bounds.nuf_upper))
print()
print("④의 lower/upper 멤버가 bounds 끝점과 일치하는가: lower=%.0f→%s  upper=%.0f→%s" %
      (bounds.nuf_lower, bounds.nuf_lower in src['④_nuf_anchor_values'],
       bounds.nuf_upper, bounds.nuf_upper in src['④_nuf_anchor_values']))
