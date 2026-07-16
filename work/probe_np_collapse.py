# N_P 축 붕괴 계측 — 리뷰어(렌즈2) 지적: budget 절단이 N_P 축을 붕괴시켜
# 격자가 최저 N_P 2개만 훑고 상한부를 한 번도 안 본다.
# 라이브 경로는 stackelberg_mpc.py:771 coarse_local (count=leader_candidate_count=49).
# OPT12가 skip_local_refinement=True라 :804 refined(budget 25)는 안 돈다.
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
import numpy as np
from src.controllers.leader import Leader, LeaderAction
from src.models.demand import DemandProfile
from src.models.state import TrafficState
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control

runner = importlib.import_module('run_claude_style_five_controller')

SC = sys.argv[1] if len(sys.argv) > 1 else 'sweet_170_incident_w'
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 26
WARM = 20

cfg, scenario = runner.build_cfg(SC, STEPS * 180.0)
print("count(coarse_local) = leader_candidate_count = %s" % cfg.mpc.leader_candidate_count)
print("leader_local_np_radius_veh = %s" % cfg.mpc.leader_local_np_radius_veh)
print()

# 실제 폐루프 상태에서 재기 위해 웜업까지 전진시킨 뒤 계측
profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
for step in range(WARM):
    fc = profile.horizon(sim.state.time_sec, 1)
    sim.step(baseline_control('no_control', cfg, sim.state, fc[0]), fc[0], step)

ld = Leader(cfg)
st = sim.state
fc = profile.horizon(st.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
b = ld._candidate_bounds(st, None, None, fc)

print("=== bounds (웜업 20스텝 후 실상태) ===")
print("  N_P  : [%.1f, %.1f]  (span %.1f)" % (b.np_lower, b.np_upper, b.np_upper - b.np_lower))
print("  N_UF : [%.1f, %.1f]" % (b.nuf_lower, b.nuf_upper))
print()

# 반경 유도: refined_candidates 내부 식을 그대로 재현
budget = cfg.mpc.leader_candidate_count
n_np = max(3, int(round(np.sqrt(budget))))
n_nuf = max(3, int(np.ceil(budget / n_np)))
span_floor_np = (b.np_upper - b.np_lower) / max(2.0 * (n_np - 1), 1.0)
np_radius = max(float(cfg.mpc.leader_local_np_radius_veh), span_floor_np)
print("=== N_P 반경이 구속력이 있나 ===")
print("  budget=%d → n_np=%d, n_nuf=%d" % (budget, n_np, n_nuf))
print("  설정 반경        = %.1f" % cfg.mpc.leader_local_np_radius_veh)
print("  span floor       = span/(2·(n_np−1)) = %.1f" % span_floor_np)
print("  실효 반경 max(·) = %.1f  → %s" %
      (np_radius, "★span floor가 이김 — 설정값 40은 무의미" if span_floor_np > cfg.mpc.leader_local_np_radius_veh
       else "설정값이 구속"))
print()

# 실제 후보 집합의 N_P 분포
for center_np in (b.np_lower + 0.1 * (b.np_upper - b.np_lower),
                  (b.np_lower + b.np_upper) / 2,
                  b.np_lower + 0.9 * (b.np_upper - b.np_lower)):
    out = ld.refined_candidates(st, LeaderAction(center_np, 5000.0), None, None, fc, budget)
    nps = sorted(set(round(a.N_P_star, 2) for a in out))
    cover = (max(nps) - min(nps)) / max(b.np_upper - b.np_lower, 1e-9) * 100
    print("center N_P=%7.1f → 후보 %2d개, 고유 N_P %d개: %s" % (center_np, len(out), len(nps),
                                                             [round(x) for x in nps[:8]]))
    print("            N_P 범위 [%.1f, %.1f] = bounds의 %.1f%%  %s" %
          (min(nps), max(nps), cover, "★상한부 미탐색" if max(nps) < b.np_upper - 1 else ""))
