# PFO 실효 N_P/N_UF를 역산 → leader box 안에 있는지 + 그 점에서 최적화하면 PFO보다 개선되는지 확인.
"""혼잡 state에서:
1. PFO(leader=None) 풀어 control_pfo → 실효 (N_P_pfo, N_UF_pfo) 역산.
2. leader 후보 박스 [np_lo,np_hi]×[nuf_lo,nuf_hi] 안에 PFO 점이 있는지.
   - 밖이면 → leader가 PFO 운전점을 후보로 못 만든다(box가 문제, 위치/폭).
   - 안이면 → box는 담는다(문제는 objective/search).
3. PFO 점 + 그 주변을 leader objective로 평가 → PFO를 이기는 점이 box 안에 있는지(개선 여지).
"""
import argparse

import numpy as np

from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.leader import LeaderAction
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator

ap = argparse.ArgumentParser()
ap.add_argument("--scenario", default="sweet_128")
ap.add_argument("--warmup-steps", type=int, default=6)
args = ap.parse_args()

cfg = ExperimentConfig.from_file(
    "src/config/default.yaml",
    {"mpc": {
        "relaxed_quantized_controls": True,
        "stackelberg_enable_fallback": False,
        "grid_parallel_backend": "serial",
        "stackelberg_leader_parallel_backend": "serial",
    }},
)
sc = load_scenarios("src/config/scenarios.yaml")[args.scenario]
cfg = apply_scenario_network_overrides(cfg, sc)
cfg.mpc.follower_solver_mode = "distributed"

# --- warm-up: PFO closed-loop으로 혼잡 state ---
demand = DemandProfile(cfg, sc)
sim = MixedTrafficSimulator(cfg)
coord = DistributedCoordinator(cfg)
prev = None
for step in range(args.warmup_steps):
    cd = demand.at(sim.state.time_sec)
    fc = demand.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
    nash = coord.solve(sim.state.copy(), None, fc, prev or ControlAction.uncontrolled(cfg))
    sim.step(nash.control, cd, step)
    prev = nash.control
state = sim.state.copy()
fc = demand.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
demand_now = demand.at(sim.state.time_sec)

ctrl = StackelbergMPCController(cfg)
previous = ctrl._normalize_previous_leader_reference(prev)

# --- PFO 풀고 실효 N_P/N_UF 역산 ---
pfo_nash = coord.solve(state.copy(), None, list(fc), previous)
pfo_ctrl = pfo_nash.control
n_p_pfo = ctrl._realized_net_inflow_veh(pfo_ctrl, state, fc)
n_uf_pfo = sum(float(v) for v in pfo_ctrl.ramp_metering.values())
pfo_obj = float(pfo_nash.objective_value)

# --- leader box ---
bounds = ctrl.leader._candidate_bounds(state, previous, demand_now, fc)
np_lo, np_hi = float(bounds.np_lower), float(bounds.np_upper)
nuf_lo, nuf_hi = float(bounds.nuf_lower), float(bounds.nuf_upper)
np_in = np_lo - 1e-6 <= n_p_pfo <= np_hi + 1e-6
nuf_in = nuf_lo - 1e-6 <= n_uf_pfo <= nuf_hi + 1e-6

print(f"scenario={args.scenario} warmup={args.warmup_steps}")
print(f"state urban={state.total_urban_vehicles(cfg.network):.1f} freeway={state.total_freeway_vehicles(cfg.network):.1f}")
print(f"PFO realized:  N_P={n_p_pfo:.1f}  N_UF={n_uf_pfo:.1f}  leader_obj(PFO response)={pfo_obj:.3f}")
print(f"leader box:    N_P[{np_lo:.1f}, {np_hi:.1f}]  N_UF[{nuf_lo:.1f}, {nuf_hi:.1f}]")
print(f"PFO point in box?  N_P_in={np_in}  N_UF_in={nuf_in}")

# --- PFO 점 + 주변을 leader objective로 평가(개선 여지) ---
np_c = float(np.clip(n_p_pfo, np_lo, np_hi))
nuf_c = float(np.clip(n_uf_pfo, nuf_lo, nuf_hi))
np_grid = sorted({float(np.clip(np_c + d, np_lo, np_hi)) for d in (-150, -75, 0, 75, 150)})
nuf_grid = sorted({float(np.clip(nuf_c + d, nuf_lo, nuf_hi)) for d in (-1000, -500, 0, 500, 1000)})
cands = [LeaderAction(p, u) for p in np_grid for u in nuf_grid]
evals = ctrl._evaluate_candidate_set(cands, list(range(len(cands))), state, list(fc), previous,
                                     stage="reverse_pfo_probe", incumbent_obj=float("inf"))
evals_sorted = sorted(evals, key=lambda e: e.objective)
print(f"\nPFO leader_obj baseline = {pfo_obj:.3f}")
print(f"{'rank':>4} {'N_P':>8} {'N_UF':>8} {'leader_obj':>11} {'vs_PFO':>9} {'rollout_ttt':>11}")
for i, e in enumerate(evals_sorted[:8]):
    diag = dict(e.nash.diagnostics); diag.update(e.nash.control.diagnostics)
    print(f"{i+1:>4} {e.action.N_P_star:8.1f} {e.action.N_UF_star:8.1f} {e.objective:11.3f} "
          f"{e.objective - pfo_obj:9.3f} {float(diag.get('distributed_response_rollout_ttt',0)):11.3f}")
best = evals_sorted[0]
print(f"\nbest leader candidate beats PFO? {best.objective < pfo_obj - 1e-9} "
      f"(best={best.objective:.3f} vs PFO={pfo_obj:.3f}, gain={pfo_obj - best.objective:.3f})")
