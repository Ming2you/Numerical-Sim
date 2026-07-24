# budget 절단이 반경밖 앵커를 남기는지 / N_P 축이 잘려나가는지 계측 — 읽기 전용.
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
from src.controllers.leader import Leader, LeaderAction

runner = importlib.import_module('run_claude_style_five_controller')
cfg, scenario = runner.build_cfg('sweet_170_incident_w', 30 * 180.0)
print("leader_candidate_count(coarse_local budget) = %s" % cfg.mpc.leader_candidate_count)
print("leader_refinement_candidate_count(refined budget) = %s" % cfg.mpc.leader_refinement_candidate_count)
print("leader_skip_local_refinement = %s" % getattr(cfg.mpc, "leader_skip_local_refinement", "<미선언>"))

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
for step in range(21):
    fc = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    prev = baseline_control('no_control', cfg, sim.state, fc[0])
    sim.step(prev, fc[0], step)

state = sim.state
fc = profile.horizon(state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
leader = Leader(cfg)
bounds = leader._candidate_bounds(state, prev, fc[0], fc)

for budget in (int(cfg.mpc.leader_candidate_count), int(cfg.mpc.leader_refinement_candidate_count)):
    center = LeaderAction(float(np.clip(50.0, bounds.np_lower, bounds.np_upper)), 6000.0)
    out = leader.refined_candidates(state, center, prev, fc[0], fc, count=budget)
    nufs = sorted({a.N_UF_star for a in out})
    nps = sorted({a.N_P_star for a in out})
    # 내부 집합 크기 재현
    n_np = max(3, int(round(np.sqrt(max(5, budget)))))
    n_nuf = max(3, int(np.ceil(max(5, budget) / n_np)))
    print("\n=== budget=%d (n_np=%d, n_nuf=%d) ===" % (budget, n_np, n_nuf))
    print("  selected 개수=%d" % len(out))
    print("  고유 N_UF %d개: %s" % (len(nufs), [round(v) for v in nufs]))
    print("  고유 N_P  %d개: %s" % (len(nps), [round(v) for v in nps]))
    print("  N_P bounds=[%.0f, %.0f] → selected N_P 상한 도달률: %.1f%% 지점"
          % (bounds.np_lower, bounds.np_upper,
             100.0 * (max(nps) - bounds.np_lower) / max(bounds.np_upper - bounds.np_lower, 1e-9)))
    print("  선택 순서 앞 8개: %s" % [(round(a.N_P_star), round(a.N_UF_star)) for a in out[:8]])
