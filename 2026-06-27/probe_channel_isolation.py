# [throwaway] 채널 분리 프로브 — follower의 green vs VSL 중 무엇이 손실을 만드나(폐루프)
"""follower 제어를 폐루프로 돌리되 green/VSL을 선택적으로 중립화해 손실 귀속.
- full follower
- green만(VSL 중립=no VSL)
- VSL만(green 균형 56/56)
- 전부 중립(=no_control 등가, sanity)
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


def neutralize(control, cfg, *, kill_green, kill_vsl):
    out = control.copy()
    if kill_green:
        total = cfg.network.effective_green_total
        for s in cfg.network.signals:
            out.green_times[f"{s}_p1"] = total / 2.0
            out.green_times[f"{s}_p2"] = total / 2.0
    if kill_vsl:
        nc = ControlAction.uncontrolled(cfg)
        out.vsl = dict(nc.vsl)
    out.inflow_outflow_allocation = {}
    return out


def run_mode(cfg, scenario, mode):
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    if mode == "no_control":
        for step in range(steps):
            t = step * cfg.simulation.control_interval
            forecast = profile.horizon(t, cfg.mpc.horizon_steps)
            control = baseline_control("no_control", cfg, sim.state, forecast[0])
            sim.step(control, forecast[0], step)
        return sim.total_ttt
    follower = WuFaithfulFollower(cfg)
    prev = None
    for step in range(steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        nash = follower.solve(sim.state.copy(), None, forecast, prev)
        control = nash.control
        if mode == "full":
            applied = control
        elif mode == "green_only":
            applied = neutralize(control, cfg, kill_green=False, kill_vsl=True)
        elif mode == "vsl_only":
            applied = neutralize(control, cfg, kill_green=True, kill_vsl=False)
        elif mode == "both_neutral":
            applied = neutralize(control, cfg, kill_green=True, kill_vsl=True)
        else:
            raise ValueError(mode)
        sim.step(applied, forecast[0], step)
        prev = control.copy()
    return sim.total_ttt


def main():
    t_total = float(sys.argv[1]) if len(sys.argv) > 1 else 3600.0
    cfg, scenario = build_cfg("sweet_128", t_total)
    base = run_mode(cfg, scenario, "no_control")
    print(f"T_total={t_total:.0f}  no_control TTT = {base:.3f}", flush=True)
    for mode in ("both_neutral", "green_only", "vsl_only", "full"):
        ttt = run_mode(cfg, scenario, mode)
        impr = 100.0 * (base - ttt) / max(base, 1e-9)
        print(f"  {mode:13s} TTT={ttt:.3f}  impr={impr:+.2f}%", flush=True)


if __name__ == "__main__":
    main()
