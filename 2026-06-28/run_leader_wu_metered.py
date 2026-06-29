# Leader+metering-PFO vs metering-PFO-alone vs no_control closed-loop 가치검증 러너(새 코드)
"""StackelbergWuMeteredController(leader+WuFaithfulFollower) 닫힌루프 가치검증.

세 가지를 같은 cfg/scenario로 닫힌루프 비교한다:
  1. no_control baseline (sweet_128 T=3600 = 3089.532 기대).
  2. metering-PFO alone (WuFaithfulFollower.solve(leader=None)) — +56.63% 기대.
  3. leader + metering-PFO (StackelbergWuMeteredController.decide) — leader 한계가치 측정.

보고: 세 total_ttt, leader vs PFO 한계개선%, N_P/N_UF/green/metering 궤적, solve time.
미변경 원칙이라 새 스크립트로 닫힌루프를 직접 돈다(grid 탐색·serial backend로 우리 follower 주입 보장).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import (
    DemandProfile,
    apply_scenario_network_overrides,
    load_scenarios,
)
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.baseline import baseline_control
from src.simulation.simulator import MixedTrafficSimulator


def build_cfg(scenario_name: str, t_total: float):
    overrides = {
        "mpc": {
            "relaxed_quantized_controls": True,
            "grid_parallel_backend": "serial",
            # 우리 follower 주입을 보장하려면 grid 탐색 + serial leader backend.
            "leader_search_mode": "grid",
            "stackelberg_leader_parallel_backend": "serial",
        },
        "simulation": {"T_total": float(t_total)},
    }
    cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), overrides)
    scenarios = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))
    scenario = scenarios[scenario_name]
    cfg = apply_scenario_network_overrides(cfg, scenario)
    return cfg, scenario


def run_no_control(cfg, scenario):
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    for step in range(steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        control = baseline_control("no_control", cfg, sim.state, forecast[0])
        sim.step(control, forecast[0], step)
    return {"total_ttt": sim.total_ttt, "urban_ttt": sim.urban_ttt, "freeway_ttt": sim.freeway_ttt}


def run_pfo(cfg, scenario):
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    follower = WuFaithfulFollower(cfg)
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    prev = None
    solve_times = []
    for step in range(steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        t0 = time.perf_counter()
        nash = follower.solve(sim.state.copy(), None, forecast, prev)
        solve_times.append(time.perf_counter() - t0)
        control = nash.control
        sim.step(control, forecast[0], step)
        prev = control.copy()
    return {
        "total_ttt": sim.total_ttt,
        "urban_ttt": sim.urban_ttt,
        "freeway_ttt": sim.freeway_ttt,
        "solve_times": solve_times,
    }


def run_leader(cfg, scenario):
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    controller = StackelbergWuMeteredController(cfg)
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    prev = None
    np_hist, nuf_hist = [], []
    meter_hist = []
    green_hist = {s: [] for s in cfg.network.signals}
    solve_times = []
    for step in range(steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        t0 = time.perf_counter()
        control = controller.decide(sim.state.copy(), forecast, prev, cfg)
        solve_times.append(time.perf_counter() - t0)
        sim.step(control, forecast[0], step)
        prev = control.copy()
        np_hist.append(float(control.diagnostics.get("leader_intent_N_P_star", control.N_P_star)))
        nuf_hist.append(float(control.diagnostics.get("leader_intent_N_UF_star", control.N_UF_star)))
        meter_hist.append(sum(float(v) for v in control.ramp_metering.values()))
        for s in cfg.network.signals:
            green_hist[s].append(float(control.green_times.get(f"{s}_p1", 56.0)))
        print(
            f"step {step+1}/{steps} cum_ttt={sim.total_ttt:.3f} "
            f"N_P={np_hist[-1]:.0f} N_UF={nuf_hist[-1]:.0f} meter={meter_hist[-1]:.0f} "
            f"solve={solve_times[-1]*1000:.0f}ms",
            flush=True,
        )
    controller.close()
    return {
        "total_ttt": sim.total_ttt,
        "urban_ttt": sim.urban_ttt,
        "freeway_ttt": sim.freeway_ttt,
        "np_hist": np_hist,
        "nuf_hist": nuf_hist,
        "meter_hist": meter_hist,
        "green_hist": green_hist,
        "solve_times": solve_times,
    }


def main():
    scenario_name = sys.argv[1] if len(sys.argv) > 1 else "sweet_128"
    t_total = float(sys.argv[2]) if len(sys.argv) > 2 else 3600.0
    skip_nc = "--skip-nc" in sys.argv
    cfg, scenario = build_cfg(scenario_name, t_total)
    print(f"scenario={scenario_name} T_total={t_total:.0f}", flush=True)

    base = None
    if not skip_nc:
        print("=== no_control ===", flush=True)
        base = run_no_control(cfg, scenario)
    print("=== metering-PFO alone ===", flush=True)
    pfo = run_pfo(cfg, scenario)
    print("=== leader + metering-PFO ===", flush=True)
    led = run_leader(cfg, scenario)

    print("\n========== SUMMARY ==========")
    nc_ttt = base["total_ttt"] if base else (3089.532 if scenario_name == "sweet_128" else None)
    if nc_ttt:
        print(f"no_control total_ttt = {nc_ttt:.3f}")
        pfo_impr = 100.0 * (nc_ttt - pfo["total_ttt"]) / nc_ttt
        led_impr = 100.0 * (nc_ttt - led["total_ttt"]) / nc_ttt
        print(f"PFO    total_ttt = {pfo['total_ttt']:.3f}  impr vs no_control = {pfo_impr:+.2f}%")
        print(f"leader total_ttt = {led['total_ttt']:.3f}  impr vs no_control = {led_impr:+.2f}%")
        print(f"leader MARGINAL vs PFO = {led_impr - pfo_impr:+.2f}pp  "
              f"(ttt delta = {pfo['total_ttt'] - led['total_ttt']:+.3f})")
    else:
        print(f"PFO    total_ttt = {pfo['total_ttt']:.3f}")
        print(f"leader total_ttt = {led['total_ttt']:.3f}")
        print(f"leader vs PFO ttt delta = {pfo['total_ttt'] - led['total_ttt']:+.3f}")

    nph = np.array(led["np_hist"]); nufh = np.array(led["nuf_hist"]); mh = np.array(led["meter_hist"])
    print(f"\nN_P*:  min={nph.min():.0f} max={nph.max():.0f} mean={nph.mean():.0f}")
    print(f"N_UF*: min={nufh.min():.0f} max={nufh.max():.0f} mean={nufh.mean():.0f}")
    print(f"metering sum[veh/h]: min={mh.min():.0f} max={mh.max():.0f} mean={mh.mean():.0f}")
    print("\n-- green p1 (leader), balanced=56 --")
    for s in cfg.network.signals:
        h = np.array(led["green_hist"][s])
        print(f"  {s}: min={h.min():.1f} max={h.max():.1f} mean={h.mean():.2f}")
    lst = np.array(led["solve_times"]) * 1000.0
    pst = np.array(pfo["solve_times"]) * 1000.0
    print(f"\nleader solve/step (ms): mean={lst.mean():.0f} max={lst.max():.0f}")
    print(f"PFO    solve/step (ms): mean={pst.mean():.0f} max={pst.max():.0f}")


if __name__ == "__main__":
    main()
