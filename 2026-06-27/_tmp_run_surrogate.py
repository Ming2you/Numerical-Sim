# [THROWAWAY] cheap off-ramp bias surrogate closed-loop sweep (T=3600 sweet_128)
import sys, time
from pathlib import Path
import numpy as np
ROOT = Path("C:/Users/alsrj/Desktop/Numerical-Sim")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"2026-06-27"))
from run_wu_faithful import build_cfg
from _tmp_surrogate_follower import OffRampBiasFollower
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator

BASE = 3089.532

def run(w_off):
    cfg, scenario = build_cfg("sweet_128", 3600.0)
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    follower = OffRampBiasFollower(cfg, w_off=w_off)
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    prev = None
    gp1 = {s: [] for s in cfg.network.signals}
    t0 = time.perf_counter()
    for step in range(steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        nash = follower.solve(sim.state.copy(), None, forecast, prev)
        control = nash.control
        sim.step(control, forecast[0], step)
        for s in cfg.network.signals:
            gp1[s].append(float(control.green_times.get(f"{s}_p1", 56.0)))
        prev = control.copy()
    impr = 100.0*(BASE - sim.total_ttt)/BASE
    dmean = np.mean(gp1["D"]); fmean = np.mean(gp1["F"])
    wall = time.perf_counter()-t0
    print(f"w_off={w_off:<8.4g} ttt={sim.total_ttt:8.3f} impr={impr:+6.2f}% "
          f"D_p1_mean={dmean:5.1f} F_p1_mean={fmean:5.1f} wall={wall:.1f}s", flush=True)
    return impr

print(f"baseline no_control = {BASE:.3f}")
for w in [0.0, 0.001, 0.01, 0.05, 0.1, 0.5]:
    run(w)
