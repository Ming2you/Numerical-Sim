# H1/H2 probe (throwaway): greedy own-TTS vs global TTT, and local rollout vs real plant ranking
"""Investigator A H1/H2 test. DELETE before finishing.

At a warmed congested state, pick a signal. For a grid of candidate greens (p1):
  H1: score by (a) own-TTS local rollout [follower's _solve_urban_agent_local cost]
              vs (b) GLOBAL TTT via run_coupled_interval(state_copy, control with this
                 signal's green set, neighbors frozen at previous greens).
      If own-TTS's argmin differs from global-TTT's argmin -> greedy objective is a cause.
  H2: compare local rollout's predicted OWN-queue trajectory (sum of this signal's
      movement queues at end of interval) against the REAL plant's own-queue after
      run_coupled_interval. Does local rollout RANK greens the same as real plant ranks
      this signal's own TTS? Spearman-ish: compare argmin & ordering.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.controllers.local_signal_plant import rollout_local_tts
from src.controllers.relaxed_quantization import repair_green_pair
from src.models.demand import DemandProfile
from src.models.state import ControlAction
from src.models.urban_queue_model import _effective_available_space
from src.simulation.baseline import baseline_control
from src.simulation.coupling import run_coupled_interval
from src.simulation.simulator import MixedTrafficSimulator

import importlib.util
spec = importlib.util.spec_from_file_location("rwf", str(ROOT / "2026-06-27" / "run_wu_faithful.py"))
rwf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rwf)
build_cfg = rwf.build_cfg


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
    return sim.state.copy(), forecast[0]


def own_queue_sum(cfg, state, signal, follower):
    model = follower._local_models[signal]
    return float(sum(max(0.0, state.urban_movement_queue.get(m, 0.0)) for m in model.movements))


def main():
    scenario_name = "sweet_128"
    cfg, scenario = build_cfg(scenario_name, 3600.0)
    n_warm = 14
    state, demand = warm_state(cfg, scenario, n_warm)
    follower = WuFaithfulFollower(cfg)
    net = cfg.network

    # baseline control = balanced 56/56 everywhere (neighbors frozen at this)
    base_ctrl = ControlAction.uncontrolled(cfg)
    base_ctrl.inflow_outflow_allocation = {}

    # candidate p1 grid
    total = net.effective_green_total
    raw = list(np.linspace(net.green_min, net.green_max, 13))
    cands = []
    for r in raw:
        p1 = repair_green_pair(float(r), cfg).p1 if cfg.mpc.relaxed_quantized_controls else float(np.clip(r, net.green_min, net.green_max))
        if not any(abs(p1 - c) < 1e-6 for c in cands):
            cands.append(p1)

    # pick the most congested signal by own-queue sum
    sig_load = {s: own_queue_sum(cfg, state, s, follower) for s in net.signals}
    signal = max(sig_load, key=sig_load.get)
    print(f"=== H1/H2 @ warm step {n_warm}, scenario {scenario_name} ===")
    print(f"signal loads (own-queue sum): " + ", ".join(f"{s}={sig_load[s]:.1f}" for s in net.signals))
    print(f"chosen signal = {signal} (most congested)\n")

    # follower internal coupling/arr/s_eff for the local rollout (frozen, current behavior)
    coupling = follower._wu._coupling(state, base_ctrl, demand)
    s_eff_frozen = follower._frozen_s_eff(state)
    model = follower._local_models[signal]
    horizon = max(1, cfg.mpc.horizon_steps)
    substeps = horizon * max(1, cfg.simulation.K_cu)
    dt_h = cfg.simulation.T_u_h
    arr_movement = follower._per_movement_arrivals(signal, state, base_ctrl, demand)
    # reproduce arr_mv renormalization from _solve_urban_agent_local
    arr_phase = {pid: float(coupling.get(f"arr_{signal}_{pid}", 0.0)) for pid in ("p1", "p2")}
    arr_mv = {}
    for pid in ("p1", "p2"):
        pm = [m for m in model.movements if model.phase_of[m] == pid]
        rawsum = sum(max(0.0, float(arr_movement.get(m, 0.0))) for m in pm)
        tgt = arr_phase[pid]
        if rawsum > 1e-12:
            sc = tgt / rawsum
            for m in pm:
                arr_mv[m] = max(0.0, float(arr_movement.get(m, 0.0))) * sc
        else:
            for m in pm:
                arr_mv[m] = 0.0
    s_eff0 = {model.receiving_of[m]: float(s_eff_frozen.get(model.receiving_of[m], 0.0))
              for m in model.movements if model.receiving_of[m]}
    q0 = {m: max(0.0, state.urban_movement_queue.get(m, 0.0)) for m in model.movements}

    print(f"{'p1':>6} {'localTTS':>12} {'globalTTT':>12} {'realOwnTTS':>12}")
    rows = []
    for p1 in cands:
        p2 = total - p1
        if p2 < net.green_min - 1e-9 or p2 > net.green_max + 1e-9:
            continue
        # (a) local own-TTS rollout (what follower uses; no smoothness term so it's pure own-TTS)
        local_tts = rollout_local_tts(model, q0, arr_mv, s_eff0, p1, p2, substeps, dt_h)
        # (b) global TTT via real plant, only THIS signal's green changed, neighbors frozen at 56/56
        gstate = state.copy()
        gctrl = ControlAction.uncontrolled(cfg)
        gctrl.green_times = dict(base_ctrl.green_times)
        gctrl.green_times[f"{signal}_p1"] = p1
        gctrl.green_times[f"{signal}_p2"] = p2
        gctrl.inflow_outflow_allocation = {}
        res = run_coupled_interval(gstate, gctrl, demand, cfg)
        global_ttt = float(res.freeway_ttt + res.urban_ttt)
        # (c) real plant's own-TTS for this signal = own-queue sum AFTER interval (proxy for own TTS)
        real_own = own_queue_sum(cfg, gstate, signal, follower)
        rows.append((p1, local_tts, global_ttt, real_own))
        print(f"{p1:6.1f} {local_tts:12.3f} {global_ttt:12.3f} {real_own:12.3f}")

    arr = np.array(rows)
    p1s = arr[:, 0]
    local = arr[:, 1]
    glob = arr[:, 2]
    realown = arr[:, 3]
    print("\n--- argmin comparison ---")
    print(f"  local-TTS argmin p1   = {p1s[np.argmin(local)]:.1f}")
    print(f"  global-TTT argmin p1  = {p1s[np.argmin(glob)]:.1f}  <- H1: differ from local? "
          f"{'YES (greedy hurts global)' if abs(p1s[np.argmin(local)]-p1s[np.argmin(glob)])>0.6 else 'no'}")
    print(f"  real-ownTTS argmin p1 = {p1s[np.argmin(realown)]:.1f}  <- H2: differ from local? "
          f"{'YES (rollout mis-ranks own)' if abs(p1s[np.argmin(local)]-p1s[np.argmin(realown)])>0.6 else 'no'}")
    # rank correlation local vs realown (H2) and local vs global (H1)
    def spearman(a, b):
        ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
        ra = ra - ra.mean(); rb = rb - rb.mean()
        return float((ra @ rb) / (np.sqrt(ra @ ra) * np.sqrt(rb @ rb) + 1e-12))
    print(f"\n  Spearman(local, real-ownTTS) = {spearman(local, realown):+.3f}  (H2: low/neg => rollout inaccurate)")
    print(f"  Spearman(local, global-TTT)  = {spearman(local, glob):+.3f}  (H1: low/neg => own-TTS != global)")
    print(f"  Spearman(real-ownTTS, global-TTT) = {spearman(realown, glob):+.3f}  (own-goal vs system align?)")


if __name__ == "__main__":
    main()
