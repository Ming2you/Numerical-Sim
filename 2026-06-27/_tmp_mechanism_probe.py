# [THROWAWAY] p1=20 vs p1=56 for D/F: 어디서 TTT 이득이 나는지 (urban vs freeway, off-ramp storage)
import sys
from pathlib import Path
import numpy as np
ROOT = Path("C:/Users/alsrj/Desktop/Numerical-Sim")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"2026-06-27"))
from run_wu_faithful import build_cfg
from _tmp_global_ttt_follower import GlobalTTTFollower
from src.models.demand import DemandProfile
from src.models.state import ControlAction
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.coupling import run_coupled_interval

cfg, scenario = build_cfg("sweet_128", 3600.0)
profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
follower = GlobalTTTFollower(cfg)

# global follower로 6 step 진행해 D/F가 p1=20으로 간 뒤의 상태.
prev = None
for step in range(6):
    t = step*cfg.simulation.control_interval
    forecast = profile.horizon(t, cfg.mpc.horizon_steps)
    nash = follower.solve(sim.state.copy(), None, forecast, prev)
    sim.step(nash.control, forecast[0], step)
    prev = nash.control.copy()

t = 6*cfg.simulation.control_interval
forecast = profile.horizon(t, cfg.mpc.horizon_steps)
state = sim.state.copy()

def horizon_breakdown(p1_DF):
    ctrl = ControlAction.uncontrolled(cfg)
    ctrl.green_times = dict(prev.green_times)
    ctrl.vsl = dict(prev.vsl)
    ctrl.inflow_outflow_allocation = {}
    for s in ("D","F"):
        ctrl.green_times[f"{s}_p1"] = float(p1_DF)
        ctrl.green_times[f"{s}_p2"] = cfg.network.effective_green_total - float(p1_DF)
    s = state.copy()
    u=f=0.0; occ_end={}
    for demand in forecast[:cfg.mpc.horizon_steps]:
        res = run_coupled_interval(s, ctrl, demand, cfg)
        u += res.urban_ttt; f += res.freeway_ttt
        s.time_sec += cfg.simulation.control_interval
    for sl in set(cfg.network.off_ramp_storage_link.values()):
        cap = cfg.network.urban_link_storage_veh.get(sl,0.0)
        occ_end[sl] = cap - s.urban_link_storage.get(sl,cap)
    return u,f,occ_end

for p1 in (20.0, 56.0, 92.0):
    u,f,occ = horizon_breakdown(p1)
    print(f"D/F p1={p1:.0f}: urban_ttt={u:7.3f} freeway_ttt={f:7.3f} total={u+f:7.3f} "
          f"offramp_occ_end={ {k.replace('_storage',''):round(v,1) for k,v in occ.items()} }", flush=True)
