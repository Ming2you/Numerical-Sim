# [throwaway] 좌표깊이 프로브 — Jacobi 반복수가 균형 green을 바꾸는가 + 장기 horizon green-sweep
"""1) follower.solve를 호출해 수렴 green과 iteration 보고(기본 s_max=5).
2) max_nash_iter를 5/10/20으로 바꿔 균형 green이 변하는지.
3) 한 신호 green-sweep을 horizon=3 대신 더 긴 12스텝(=2160s) 누적 plant로 평가해
   per-step 평탄성이 누적되면 깨지는지 검사.
끝나면 삭제."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "2026-06-27"))

from run_wu_faithful import build_cfg
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandProfile
from src.models.state import ControlAction
from src.simulation.baseline import baseline_control
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.coupling import run_coupled_interval


def warm(cfg, scenario, warm_steps):
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    for step in range(warm_steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        control = baseline_control("no_control", cfg, sim.state, forecast[0])
        sim.step(control, forecast[0], step)
    return sim, profile


def greens_of(control, cfg):
    return {s: round(control.green_times.get(f"{s}_p1", 56.0), 1) for s in cfg.network.signals}


def main():
    warm_steps = 10
    cfg, scenario = build_cfg("sweet_128", 3600.0)
    sim, profile = warm(cfg, scenario, warm_steps)
    state0 = sim.state.copy()
    t = warm_steps * cfg.simulation.control_interval
    forecast = profile.horizon(t, cfg.mpc.horizon_steps)

    print("=== coordination-depth: equilibrium greens vs max_nash_iter ===", flush=True)
    for s_max in (5, 10, 20, 40):
        cfg.mpc.max_nash_iter = s_max
        follower = WuFaithfulFollower(cfg)
        nash = follower.solve(state0.copy(), None, forecast, ControlAction.uncontrolled(cfg))
        print(f"  max_nash_iter={s_max:3d} -> iters_used={nash.iterations} "
              f"converged={nash.converged} residual={nash.residual_control:.4g} "
              f"greens={greens_of(nash.control, cfg)}", flush=True)

    # 장기 누적 green-sweep: 신호 D, horizon 길이 늘려가며 global-TTT가 split에 민감해지나
    cfg.mpc.max_nash_iter = 5
    follower = WuFaithfulFollower(cfg)
    total = cfg.network.effective_green_total
    probe_signal = "D"
    snapshot = ControlAction.uncontrolled(cfg)
    snapshot.inflow_outflow_allocation = {}
    print(f"\n=== long-horizon cumulative green sweep, signal {probe_signal} ===", flush=True)
    long_forecast = profile.horizon(t, 12)
    for nstep in (3, 6, 12):
        rows = []
        for p1 in (20.0, 38.0, 56.0, 62.0, 92.0):
            ctrl = ControlAction.uncontrolled(cfg)
            ctrl.inflow_outflow_allocation = {}
            ctrl.green_times[f"{probe_signal}_p1"] = p1
            ctrl.green_times[f"{probe_signal}_p2"] = total - p1
            s = state0.copy()
            tot = 0.0
            for d in long_forecast[:nstep]:
                r = run_coupled_interval(s, ctrl, d, cfg)
                tot += float(r.urban_ttt + r.freeway_ttt)
                s.time_sec += cfg.simulation.control_interval
            rows.append((p1, tot))
        arr = np.array(rows)
        best_p1 = arr[np.argmin(arr[:, 1]), 0]
        spread = arr[:, 1].max() - arr[:, 1].min()
        print(f"  nstep={nstep:2d}: " + " ".join(f"p1={p:.0f}:{v:.2f}" for p, v in rows)
              + f"  | best={best_p1:.0f} spread={spread:.3f} "
              f"({100*spread/arr[:,1].min():.2f}% of min)", flush=True)


if __name__ == "__main__":
    main()
