# H3 probe (throwaway): per-iteration S_eff refresh vs frozen — Jacobi green evolution + closed-loop TTT
"""Investigator A H3 test. DELETE before finishing.

Reproduces the WuFaithfulFollower Jacobi loop with two S_eff modes:
  A) FROZEN  : s_eff snapshot once per control step (current code behavior).
  B) REFRESH : recompute s_eff each Jacobi iteration from a state rolled forward
               one control interval under the current iteration's full control.
Logs green evolution per iteration at a warmed congested state, and runs a short
closed-loop with mode B to compare TTT vs no_control.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandProfile
from src.models.state import ControlAction
from src.models.urban_queue_model import _effective_available_space
from src.simulation.baseline import baseline_control
from src.simulation.coupling import run_coupled_interval
from src.simulation.simulator import MixedTrafficSimulator

sys.argv_backup = sys.argv
# reuse build_cfg from the existing runner
import importlib.util
spec = importlib.util.spec_from_file_location("rwf", str(ROOT / "2026-06-27" / "run_wu_faithful.py"))
rwf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rwf)
build_cfg = rwf.build_cfg


def s_eff_from_state(cfg, state) -> Dict[str, float]:
    return {link: float(_effective_available_space(state, cfg, link))
            for link in cfg.network.urban_link_storage_veh}


def jacobi(follower: WuFaithfulFollower, cfg, state, demand, previous, refresh: bool, s_max=5):
    """Run Jacobi loop, return (control, green_history[list of dict per iter])."""
    wu = follower._wu
    net = cfg.network
    wu._repair_diagnostics = {}
    control = ControlAction.uncontrolled(cfg)
    control.green_times = dict(previous.green_times)
    control.vsl = dict(previous.vsl)
    control.inflow_outflow_allocation = {}
    coupling = wu._coupling(state, control, demand)
    if follower._prev_coupling is not None:
        for k in coupling:
            if k in follower._prev_coupling:
                coupling[k] = float(follower._prev_coupling[k])
    s_eff_frozen = follower._frozen_s_eff(state)
    alpha = 0.5
    green_hist = []
    for iteration in range(1, s_max + 1):
        # mode B: refresh s_eff from a forward-rolled state copy under current control
        if refresh and iteration > 1:
            roll_state = state.copy()
            roll_ctrl = ControlAction.uncontrolled(cfg)
            roll_ctrl.green_times = dict(control.green_times)
            roll_ctrl.vsl = dict(control.vsl)
            roll_ctrl.inflow_outflow_allocation = {}
            run_coupled_interval(roll_state, roll_ctrl, demand, cfg)
            s_eff_use = s_eff_from_state(cfg, roll_state)
        else:
            s_eff_use = s_eff_frozen
        snapshot = ControlAction(
            ramp_metering=dict(control.ramp_metering),
            vsl=dict(control.vsl),
            green_times=dict(control.green_times),
            offsets=dict(control.offsets),
            inflow_outflow_allocation={},
        )
        new_green: Dict[str, float] = {}
        new_vsl: Dict[str, float] = {}
        for signal in net.signals:
            arr_movement = follower._per_movement_arrivals(signal, state, snapshot, demand)
            p1, _, _ = follower._solve_urban_agent_local(
                signal, state, coupling, arr_movement, s_eff_use, snapshot,
            )
            new_green[f"{signal}_p1"] = p1
            new_green[f"{signal}_p2"] = net.effective_green_total - p1
        for link in net.freeway_links:
            vsl_dict, _, _ = wu._solve_freeway_agent(link, state, coupling, demand, snapshot, None)
            new_vsl.update(vsl_dict)
        control.green_times.update(new_green)
        control.vsl.update(new_vsl)
        green_hist.append({s: float(control.green_times[f"{s}_p1"]) for s in net.signals})
        predicted = wu._coupling(state, control, demand)
        relaxed = {k: (1.0 - alpha) * coupling.get(k, 0.0) + alpha * predicted[k] for k in predicted}
        coupling = relaxed
    follower._prev_coupling = dict(coupling)  # warm-start next step (matches real _solve_followers)
    return control, green_hist


def warm_state(cfg, scenario, n_steps):
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    for step in range(min(n_steps, steps)):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        control = baseline_control("no_control", cfg, sim.state, forecast[0])
        sim.step(control, forecast[0], step)
    t = min(n_steps, steps) * cfg.simulation.control_interval
    forecast = profile.horizon(t, cfg.mpc.horizon_steps)
    return sim.state.copy(), forecast, profile


def main():
    scenario_name = "sweet_128"
    cfg, scenario = build_cfg(scenario_name, 3600.0)
    # warm to a congested state (step 14 of 20 -> heavily loaded per no_control trace)
    n_warm = 14
    state, forecast, profile = warm_state(cfg, scenario, n_warm)
    demand = forecast[0]
    previous = ControlAction.uncontrolled(cfg)

    print(f"=== H3 Jacobi green evolution @ warm step {n_warm}, scenario {scenario_name} ===")
    for refresh in (False, True):
        follower = WuFaithfulFollower(cfg)
        follower._prev_coupling = None
        _, hist = jacobi(follower, cfg, state.copy(), demand, previous, refresh=refresh, s_max=5)
        tag = "REFRESH" if refresh else "FROZEN "
        sigs = cfg.network.signals
        print(f"\n-- mode {tag} --")
        header = "iter " + " ".join(f"{s:>6}" for s in sigs)
        print(header)
        for i, g in enumerate(hist, 1):
            print(f"  {i}  " + " ".join(f"{g[s]:6.1f}" for s in sigs))

    # --- closed-loop short run with mode B (refresh) vs no_control ---
    print("\n=== closed-loop TTT: FROZEN vs REFRESH vs no_control (full T=3600) ===")
    for refresh in (False, True):
        cfg2, scen2 = build_cfg(scenario_name, 3600.0)
        profile2 = DemandProfile(cfg2, scen2)
        sim = MixedTrafficSimulator(cfg2)
        follower = WuFaithfulFollower(cfg2)
        steps = max(1, int(round(cfg2.simulation.T_total / cfg2.simulation.control_interval)))
        prev = ControlAction.uncontrolled(cfg2)
        for step in range(steps):
            t = step * cfg2.simulation.control_interval
            fc = profile2.horizon(t, cfg2.mpc.horizon_steps)
            ctrl, _ = jacobi(follower, cfg2, sim.state.copy(), fc[0], prev, refresh=refresh, s_max=5)
            ctrl.N_P_star = 0.0
            ctrl.N_UF_star = 0.0
            ctrl.inflow_outflow_allocation = {}
            sim.step(ctrl, fc[0], step)
            prev = ctrl.copy()
        tag = "REFRESH" if refresh else "FROZEN "
        print(f"  {tag} total_ttt = {sim.total_ttt:.3f}  (urban {sim.urban_ttt:.3f} / fw {sim.freeway_ttt:.3f})")
    print("  no_control total_ttt = 3089.532 (established)")


if __name__ == "__main__":
    main()
