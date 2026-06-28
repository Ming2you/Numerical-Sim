# [throwaway] 분해손실 진단 프로브 — rollout정확도 / own-TTS vs global-TTT / 좌표깊이
"""Investigator A 프로브. 기존 파일 미변경. 끝나면 삭제."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "2026-06-27"))

from run_wu_faithful import build_cfg
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.controllers.local_signal_plant import rollout_local_tts
from src.models.demand import DemandProfile
from src.models.state import ControlAction
from src.simulation.baseline import baseline_control
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.coupling import run_coupled_interval


def warm_state(cfg, scenario, warm_steps):
    """no_control 폐루프로 혼잡 상태를 데운 뒤 (sim.state, profile) 반환."""
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    for step in range(warm_steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        control = baseline_control("no_control", cfg, sim.state, forecast[0])
        sim.step(control, forecast[0], step)
    return sim, profile


def total_urban_queue_signal(state, follower, signal):
    model = follower._local_models[signal]
    return sum(max(0.0, state.urban_movement_queue.get(m, 0.0)) for m in model.movements)


def main():
    cfg, scenario = build_cfg("sweet_128", 3600.0)
    warm_steps = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    probe_signal = sys.argv[2] if len(sys.argv) > 2 else "D"
    total = cfg.network.effective_green_total
    net = cfg.network

    sim, profile = warm_state(cfg, scenario, warm_steps)
    state0 = sim.state.copy()
    t = warm_steps * cfg.simulation.control_interval
    forecast = profile.horizon(t, cfg.mpc.horizon_steps)
    demand0 = forecast[0]
    horizon = max(1, min(len(forecast), cfg.mpc.horizon_steps))

    print(f"=== warmed state after {warm_steps} steps (t={t}s) ===", flush=True)
    print(f"total urban veh={state0.total_urban_vehicles(net):.1f} "
          f"freeway veh={state0.total_freeway_vehicles(net):.1f}", flush=True)
    for s in net.signals:
        pass

    follower = WuFaithfulFollower(cfg)
    # follower가 iteration1에서 보는 입력을 재현: previous=uncontrolled, snapshot=uncontrolled greens.
    previous = ControlAction.uncontrolled(cfg)
    snapshot = ControlAction.uncontrolled(cfg)
    snapshot.green_times = dict(previous.green_times)
    snapshot.inflow_outflow_allocation = {}

    coupling = follower._wu._coupling(state0, snapshot, demand0)
    s_eff_frozen = follower._frozen_s_eff(state0)
    arr_movement = follower._per_movement_arrivals(probe_signal, state0, snapshot, demand0)
    model = follower._local_models[probe_signal]

    # 국소 rollout 입력(=_solve_urban_agent_local 내부 재현)
    sim_cfg = cfg.simulation
    substeps = horizon * max(1, sim_cfg.K_cu)
    dt_h = sim_cfg.T_u_h
    q0 = {m: max(0.0, state0.urban_movement_queue.get(m, 0.0)) for m in model.movements}
    arr_phase = {pid: float(coupling.get(f"arr_{probe_signal}_{pid}", 0.0)) for pid in ("p1", "p2")}
    arr_mv = {}
    for pid in ("p1", "p2"):
        pmoves = [m for m in model.movements if model.phase_of[m] == pid]
        raw_sum = sum(max(0.0, float(arr_movement.get(m, 0.0))) for m in pmoves)
        target = arr_phase[pid]
        if raw_sum > 1e-12:
            scale = target / raw_sum
            for m in pmoves:
                arr_mv[m] = max(0.0, float(arr_movement.get(m, 0.0))) * scale
        else:
            for m in pmoves:
                arr_mv[m] = 0.0
    s_eff0 = {
        model.receiving_of[m]: float(s_eff_frozen.get(model.receiving_of[m], 0.0))
        for m in model.movements if model.receiving_of[m]
    }

    candidates = [float(v) for v in np.linspace(net.green_min, net.green_max, 13)]

    print(f"\n=== PROBE signal {probe_signal}: candidate green p1 sweep (horizon={horizon}) ===", flush=True)
    print(f"q0 sum signal {probe_signal} = {sum(q0.values()):.2f}, "
          f"arr_phase p1={arr_phase['p1']:.1f} p2={arr_phase['p2']:.1f}", flush=True)
    header = f"{'p1':>6} {'local_ownTTS':>13} {'real_ownTTS':>12} {'real_globalTTT':>15} {'real_urbTTT':>12} {'real_fwTTT':>11}"
    print(header, flush=True)

    rows = []
    for p1 in candidates:
        p2 = total - p1
        # (a) 국소 own-TTS (follower 목적)
        local_cost = rollout_local_tts(model, q0, arr_mv, s_eff0, p1, p2, substeps, dt_h)

        # (b) 실제 coupled plant — 이 신호만 green 바꾸고 이웃 동결(uncontrolled greens), 전체망 전진
        ctrl = ControlAction.uncontrolled(cfg)
        ctrl.inflow_outflow_allocation = {}
        ctrl.green_times = dict(snapshot.green_times)
        ctrl.green_times[f"{probe_signal}_p1"] = p1
        ctrl.green_times[f"{probe_signal}_p2"] = p2
        s = state0.copy()
        urb = 0.0
        fw = 0.0
        for d in forecast[:horizon]:
            r = run_coupled_interval(s, ctrl, d, cfg)
            urb += float(r.urban_ttt)
            fw += float(r.freeway_ttt)
            s.time_sec += cfg.simulation.control_interval
        global_ttt = urb + fw
        real_own = total_urban_queue_signal(s, follower, probe_signal)  # 종단 자기큐(참고)
        rows.append((p1, local_cost, real_own, global_ttt, urb, fw))
        print(f"{p1:6.1f} {local_cost:13.2f} {real_own:12.2f} {global_ttt:15.4f} {urb:12.4f} {fw:11.4f}", flush=True)

    rows = np.array(rows)
    p1s = rows[:, 0]
    local_pick = p1s[int(np.argmin(rows[:, 1]))]
    real_global_pick = p1s[int(np.argmin(rows[:, 3]))]
    real_urb_pick = p1s[int(np.argmin(rows[:, 4]))]

    # 랭킹 상관(스피어만 근사: 순위 상관)
    def rank(a):
        return np.argsort(np.argsort(a))
    r_local = rank(rows[:, 1])
    r_globttt = rank(rows[:, 3])
    r_urbttt = rank(rows[:, 4])
    corr_local_glob = np.corrcoef(r_local, r_globttt)[0, 1]
    corr_local_urb = np.corrcoef(r_local, r_urbttt)[0, 1]

    print(f"\n--- verdict for {probe_signal} ---", flush=True)
    print(f"local own-TTS picks p1 = {local_pick:.1f}", flush=True)
    print(f"real GLOBAL-TTT picks p1 = {real_global_pick:.1f}", flush=True)
    print(f"real URBAN-TTT picks p1 = {real_urb_pick:.1f}", flush=True)
    print(f"rank-corr(local_ownTTS, real_globalTTT) = {corr_local_glob:.3f}", flush=True)
    print(f"rank-corr(local_ownTTS, real_urbanTTT)  = {corr_local_urb:.3f}", flush=True)
    # global-TTT 손실: local pick vs global-best pick
    glob_at_local = rows[np.argmin(np.abs(p1s - local_pick)), 3]
    glob_best = rows[:, 3].min()
    glob_at_56 = rows[np.argmin(np.abs(p1s - total / 2.0)), 3]
    print(f"global-TTT at local-pick({local_pick:.0f})={glob_at_local:.4f}, "
          f"global-best({real_global_pick:.0f})={glob_best:.4f}, "
          f"balanced(56)={glob_at_56:.4f}", flush=True)
    print(f"global-TTT regret of local-pick vs global-best = {glob_at_local - glob_best:+.4f} "
          f"({100*(glob_at_local-glob_best)/max(glob_best,1e-9):+.2f}%)", flush=True)


if __name__ == "__main__":
    main()
