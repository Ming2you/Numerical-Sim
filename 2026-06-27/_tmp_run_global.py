# [THROWAWAY] B의 decisive H1 closed-loop 재현 러너 (T=3600 sweet_128)
import sys, time
from pathlib import Path
import numpy as np
ROOT = Path("C:/Users/alsrj/Desktop/Numerical-Sim")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"2026-06-27"))
from run_wu_faithful import build_cfg
from _tmp_global_ttt_follower import GlobalTTTFollower
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator

cfg, scenario = build_cfg("sweet_128", 3600.0)
profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
follower = GlobalTTTFollower(cfg)
steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
prev = None
gp1 = {s: [] for s in cfg.network.signals}
for step in range(steps):
    t = step * cfg.simulation.control_interval
    forecast = profile.horizon(t, cfg.mpc.horizon_steps)
    t0 = time.perf_counter()
    nash = follower.solve(sim.state.copy(), None, forecast, prev)
    control = nash.control
    log = sim.step(control, forecast[0], step)
    for s in cfg.network.signals:
        gp1[s].append(float(control.green_times.get(f"{s}_p1", 56.0)))
    prev = control.copy()
    print(f"step {step+1}/{steps} cum_ttt={sim.total_ttt:.3f} "
          f"p1=[{','.join(f'{gp1[s][-1]:.0f}' for s in cfg.network.signals)}] "
          f"wall={time.perf_counter()-t0:.1f}s", flush=True)

base = 3089.532
impr = 100.0*(base - sim.total_ttt)/base
print("\n===== SUMMARY =====")
print(f"no_control = {base:.3f}")
print(f"GlobalTTTFollower total_ttt = {sim.total_ttt:.3f} (urban {sim.urban_ttt:.3f} / fw {sim.freeway_ttt:.3f})")
print(f"improvement = {impr:+.2f}%")
for s in cfg.network.signals:
    h = np.array(gp1[s])
    print(f"  {s}: min={h.min():.1f} max={h.max():.1f} mean={h.mean():.2f}")
