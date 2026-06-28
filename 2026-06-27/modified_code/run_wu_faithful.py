# WuFaithfulFollower 검증용 standalone closed-loop 러너 (six_controller run_controller 복제)
"""SPEC §4 검증 러너 — 기존 하네스 미변경 원칙이라 새 스크립트로 closed-loop을 돈다.

- cfg: default.yaml + 하네스 동일 override(relaxed_quantized_controls=True, serial backend, T_total=720).
- scenario: sweet_128.
- follower.solve(state.copy(), None, forecast, prev)을 매 step 호출, sim.step(control, forecast[0], step) 적용.
- no_control baseline로 improvement% 산출.
- 보고: green min/max/mean per signal, impr%, eval/step, per-step wall time.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import (
    DemandProfile,
    apply_scenario_network_overrides,
    load_scenarios,
)
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.baseline import baseline_control
from src.simulation.simulator import MixedTrafficSimulator


OVERRIDES = {
    "mpc": {"relaxed_quantized_controls": True, "grid_parallel_backend": "serial"},
    "simulation": {"T_total": 720.0},
}


def build_cfg(scenario_name: str = "sweet_128") -> ExperimentConfig:
    cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), OVERRIDES)
    scenarios = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))
    scenario = scenarios[scenario_name]
    cfg = apply_scenario_network_overrides(cfg, scenario)
    return cfg, scenario


def run_follower(cfg, scenario):
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    follower = WuFaithfulFollower(cfg)
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    prev = None
    green_p1_history = {s: [] for s in cfg.network.signals}
    eval_counts = []
    solve_times = []
    step_wall_times = []
    for step in range(steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        step_start = time.perf_counter()
        nash = follower.solve(sim.state.copy(), None, forecast, prev)
        solve_dt = time.perf_counter() - step_start
        control = nash.control
        log = sim.step(control, forecast[0], step)
        step_wall_times.append(time.perf_counter() - step_start)
        solve_times.append(solve_dt)
        eval_counts.append(float(control.diagnostics.get("wu_faithful_local_evals", 0.0)))
        for s in cfg.network.signals:
            green_p1_history[s].append(float(control.green_times.get(f"{s}_p1", 56.0)))
        prev = control.copy()
        print(
            f"step {step+1}/{steps} cum_ttt={sim.total_ttt:.3f} "
            f"step_ttt={log.freeway_ttt+log.urban_ttt:.3f} evals={eval_counts[-1]:.0f} "
            f"solve={solve_dt*1000:.1f}ms",
            flush=True,
        )
    return {
        "total_ttt": sim.total_ttt,
        "urban_ttt": sim.urban_ttt,
        "freeway_ttt": sim.freeway_ttt,
        "green_p1_history": green_p1_history,
        "eval_counts": eval_counts,
        "solve_times": solve_times,
        "step_wall_times": step_wall_times,
        "steps": steps,
    }


def run_no_control(cfg, scenario):
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    for step in range(steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        control = baseline_control("no_control", cfg, sim.state, forecast[0])
        sim.step(control, forecast[0], step)
    return {
        "total_ttt": sim.total_ttt,
        "urban_ttt": sim.urban_ttt,
        "freeway_ttt": sim.freeway_ttt,
    }


def main():
    scenario_name = sys.argv[1] if len(sys.argv) > 1 else "sweet_128"
    cfg, scenario = build_cfg(scenario_name)
    print(f"scenario = {scenario_name}", flush=True)
    print("=== no_control baseline ===", flush=True)
    base = run_no_control(cfg, scenario)
    print("=== WuFaithfulFollower ===", flush=True)
    res = run_follower(cfg, scenario)

    impr = 100.0 * (base["total_ttt"] - res["total_ttt"]) / max(base["total_ttt"], 1e-9)
    print("\n========== SUMMARY ==========")
    print(f"no_control  total_ttt = {base['total_ttt']:.3f} (urban {base['urban_ttt']:.3f} / fw {base['freeway_ttt']:.3f})")
    print(f"follower    total_ttt = {res['total_ttt']:.3f} (urban {res['urban_ttt']:.3f} / fw {res['freeway_ttt']:.3f})")
    print(f"improvement vs no_control = {impr:+.2f}%")
    print("\n-- green p1 per signal (min / max / mean), balanced = 56.0 --")
    for s in cfg.network.signals:
        h = np.array(res["green_p1_history"][s])
        print(f"  {s}: min={h.min():.1f} max={h.max():.1f} mean={h.mean():.2f} "
              f"off56={'YES' if (np.abs(h-56.0)>0.5).any() else 'no'}")
    ev = np.array(res["eval_counts"])
    st = np.array(res["solve_times"]) * 1000.0
    wt = np.array(res["step_wall_times"]) * 1000.0
    print(f"\nevals/step: min={ev.min():.0f} max={ev.max():.0f} mean={ev.mean():.1f}")
    print(f"solve time/step (ms): min={st.min():.1f} max={st.max():.1f} mean={st.mean():.1f}")
    print(f"wall time/step incl plant (ms): mean={wt.mean():.1f}")


if __name__ == "__main__":
    main()
