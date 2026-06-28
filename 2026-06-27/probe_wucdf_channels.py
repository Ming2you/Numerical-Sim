# [throwaway] WU-CD-F의 이득이 green vs VSL 중 어디서 오나(폐루프 채널분리)
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "2026-06-27"))
from run_wu_faithful import build_cfg
from src.controllers.distributed_coordinator import DistributedCoordinator
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
        for k in list(out.vsl.keys()):
            out.vsl[k] = float(nc.vsl.get(k, 100.0)) if "__seg" not in k else 100.0
    return out


def run(cfg, scenario, mode):
    profile = DemandProfile(cfg, scenario); sim = MixedTrafficSimulator(cfg)
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    if mode == "no_control":
        for step in range(steps):
            t = step*cfg.simulation.control_interval; fc=profile.horizon(t,cfg.mpc.horizon_steps)
            sim.step(baseline_control("no_control",cfg,sim.state,fc[0]),fc[0],step)
        return sim.total_ttt
    coord = DistributedCoordinator(cfg, ablation="WU_GREEN_VSL_ONLY_TTT")
    prev=None
    for step in range(steps):
        t=step*cfg.simulation.control_interval; fc=profile.horizon(t,cfg.mpc.horizon_steps)
        nash=coord.solve(sim.state.copy(),None,fc,prev); c=nash.control
        if mode=="full": applied=c
        elif mode=="green_only": applied=neutralize(c,cfg,kill_green=False,kill_vsl=True)
        elif mode=="vsl_only": applied=neutralize(c,cfg,kill_green=True,kill_vsl=False)
        sim.step(applied,fc[0],step); prev=c.copy()
    return sim.total_ttt


def main():
    cfg, scenario = build_cfg("sweet_128", 3600.0)
    cfg.mpc.grid_parallel_backend = "thread"
    base = run(cfg, scenario, "no_control")
    print(f"no_control TTT={base:.3f}", flush=True)
    for mode in ("full","green_only","vsl_only"):
        ttt = run(cfg, scenario, mode)
        print(f"  WU-CD-F {mode:10s} TTT={ttt:.3f} impr={100*(base-ttt)/base:+.2f}%", flush=True)


if __name__ == "__main__":
    main()
