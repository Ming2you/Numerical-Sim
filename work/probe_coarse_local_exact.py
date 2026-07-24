# 실행경로 그대로(coarse_local 시그니처) 반경 위반 + normalize의 intent/realized 시딩을 실측.
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
cfg, scenario = runner.build_cfg('sweet_170_incident_w', 30 * 180.0)
controller = runner.make_controller('P-STACK-WU-FAITHFUL-ALLPRICE-JOINT', cfg)
leader = controller.leader
R = float(cfg.mpc.leader_local_nuf_radius_veh_h)

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
state = sim.state
prev = baseline_control('no_control', cfg, state, forecast[0])

print("=== A. coarse_local 정확한 시그니처(stackelberg_mpc.py:771) ===")
print("leader_candidate_count=%d  leader_refinement_candidate_count=%d"
      % (cfg.mpc.leader_candidate_count, cfg.mpc.leader_refinement_candidate_count))
for c in (6000.0, 4231.0, 3000.0):
    center = LeaderAction(float(prev.N_P_star), c)
    out = leader.refined_candidates(state, center, prev, forecast[0], forecast=forecast,
                                    count=cfg.mpc.leader_candidate_count)
    vals = sorted(set(round(a.N_UF_star) for a in out))
    outside = [v for v in vals if abs(v - c) > R + 1]
    print("center=%6.0f  후보 N_UF값=%s" % (c, vals))
    print("            반경밖 값 =%s  (%d/%d개)" % (outside, len(outside), len(vals)))

print()
print("=== B. _normalize_previous_leader_reference: docstring은 'seed=intent' ===")
# 출력폐쇄가 적용된 previous 재현: _apply_output_closure는 N_UF_star에 realized를 써둔다.
p2 = prev.copy()
p2.N_UF_star = 4231.0          # realized(폐쇄가 덮어쓴 값)
p2.N_P_star = 100.0
p2.diagnostics = dict(getattr(p2, 'diagnostics', None) or {})
p2.diagnostics.update({
    "leader_output_closure_applied": 1.0,
    "leader_intent_N_UF_star": 6000.0,      # raw intent
    "leader_realized_N_UF_star": 4231.0,    # realized
    "leader_intent_N_P_star": 250.0,
    "leader_realized_N_P_star": 100.0,
})
norm = controller._normalize_previous_leader_reference(p2)
print("입력 previous.N_UF_star (=realized) = %.0f" % p2.N_UF_star)
print("diagnostics intent  N_UF = %.0f" % p2.diagnostics["leader_intent_N_UF_star"])
print("diagnostics realized N_UF = %.0f" % p2.diagnostics["leader_realized_N_UF_star"])
print("normalize 반환 N_UF_star  = %.0f" % norm.N_UF_star)
print("→ intent(6000)를 시딩했는가? %s" % (abs(norm.N_UF_star - 6000.0) < 1e-6))
print("→ realized(4231)를 시딩했는가? %s" % (abs(norm.N_UF_star - 4231.0) < 1e-6))
print("→ 입력과 동일(=무변화 no-op)인가? %s" % (abs(norm.N_UF_star - p2.N_UF_star) < 1e-6))
print("   N_P: 입력=%.0f intent=%.0f 반환=%.0f" % (p2.N_P_star, 250.0, norm.N_P_star))
