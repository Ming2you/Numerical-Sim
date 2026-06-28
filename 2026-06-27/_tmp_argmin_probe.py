# [THROWAWAY] 주장#2 spot-check: D/F의 LOCAL self-TTS argmin vs GLOBAL plant argmin 비교
import sys
from pathlib import Path
import numpy as np
ROOT = Path("C:/Users/alsrj/Desktop/Numerical-Sim")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"2026-06-27"))
from run_wu_faithful import build_cfg
from _tmp_global_ttt_follower import GlobalTTTFollower
from src.controllers.local_signal_plant import rollout_local_tts
from src.models.demand import DemandProfile
from src.models.state import ControlAction
from src.simulation.simulator import MixedTrafficSimulator

cfg, scenario = build_cfg("sweet_128", 3600.0)
profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
follower = GlobalTTTFollower(cfg)

# 몇 step 진행해 큐가 쌓인 상태(B의 "step 4"에 해당)를 만든다.
prev = None
TARGET_STEP = 4
for step in range(TARGET_STEP):
    t = step * cfg.simulation.control_interval
    forecast = profile.horizon(t, cfg.mpc.horizon_steps)
    nash = follower.solve(sim.state.copy(), None, forecast, prev)
    sim.step(nash.control, forecast[0], step)
    prev = nash.control.copy()
print(f"=== probing at step {TARGET_STEP} (cum_ttt so far {sim.total_ttt:.1f}) ===", flush=True)

t = TARGET_STEP * cfg.simulation.control_interval
forecast = profile.horizon(t, cfg.mpc.horizon_steps)
follower._forecast = forecast
state = sim.state.copy()
demand = forecast[0]
# 부모 _solve_followers 초기화 복제: snapshot/coupling/s_eff.
follower._wu._repair_diagnostics = {}
snapshot = ControlAction.uncontrolled(cfg)
snapshot.green_times = dict(prev.green_times)
snapshot.vsl = dict(prev.vsl)
snapshot.inflow_outflow_allocation = {}
coupling = follower._wu._coupling(state, snapshot, demand)
s_eff_frozen = follower._frozen_s_eff(state)

sim_cfg = cfg.simulation
net = cfg.network
horizon = max(1, cfg.mpc.horizon_steps)
substeps = horizon * max(1, sim_cfg.K_cu)
dt_h = sim_cfg.T_u_h

for signal in ("D", "F"):
    model = follower._local_models[signal]
    arr_movement = follower._per_movement_arrivals(signal, state, snapshot, demand)
    # local arr 재정규화 복제(부모 _solve_urban_agent_local과 동일).
    arr_phase = {pid: float(coupling.get(f"arr_{signal}_{pid}", 0.0)) for pid in ("p1","p2")}
    arr_mv = {}
    for pid in ("p1","p2"):
        pm = [m for m in model.movements if model.phase_of[m]==pid]
        raw_sum = sum(max(0.0,float(arr_movement.get(m,0.0))) for m in pm)
        tgt = arr_phase[pid]
        for m in pm:
            arr_mv[m] = (max(0.0,float(arr_movement.get(m,0.0)))*tgt/raw_sum) if raw_sum>1e-12 else 0.0
    q0 = {m: max(0.0, state.urban_movement_queue.get(m,0.0)) for m in model.movements}
    s_eff0 = {model.receiving_of[m]: float(s_eff_frozen.get(model.receiving_of[m],0.0))
              for m in model.movements if model.receiving_of[m]}

    grid = np.linspace(net.green_min, net.green_max, 13)
    local_costs, global_costs = [], []
    for p1 in grid:
        p2 = net.effective_green_total - p1
        lc = rollout_local_tts(model, q0, arr_mv, s_eff0, p1, p2, substeps, dt_h)
        gc = follower._global_ttt_for_p1(signal, state, snapshot, p1)
        local_costs.append(lc); global_costs.append(gc)
    li = int(np.argmin(local_costs)); gi = int(np.argmin(global_costs))
    print(f"\nsignal {signal}:")
    print(f"  grid p1      = {[f'{g:.0f}' for g in grid]}")
    print(f"  LOCAL  self-TTS argmin p1 = {grid[li]:.1f}  (cost {local_costs[li]:.2f})")
    print(f"  GLOBAL plant TTT argmin p1 = {grid[gi]:.1f}  (ttt {global_costs[gi]:.3f})")
    print(f"  GLOBAL ttt at p1=20 = {global_costs[0]:.3f}  at p1=86/92 = {global_costs[-1]:.3f}")
