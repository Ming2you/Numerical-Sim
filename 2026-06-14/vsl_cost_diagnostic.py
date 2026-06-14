# capacity_drop 최혼잡 interval에서 VSL 후보별 cost(TTS 이득 vs smoothness 페널티)를 정량화하는 진단
from __future__ import annotations

from src.controllers.wu_distributed import WuDistributedController, _wu_fixed_control
from src.models.demand import (
    DemandProfile,
    ScenarioConfig,
    apply_scenario_network_overrides,
    load_scenarios,
)
from src.models.metanet import compute_ramp_release_flows, freeway_substep
from src.models.state import ControlAction, ExperimentConfig
from src.models.urban_queue_model import off_ramp_capacity_by_freeway_link
from src.simulation.simulator import MixedTrafficSimulator


def candidate_costs(ctl, link, state, coupling, demand, previous, leader=None):
    """_solve_freeway_agent의 후보 루프를 그대로 복제하되 후보별 (TTS항, smoothness항)을 분리 기록한다."""
    net = ctl.cfg.network
    sim = ctl.cfg.simulation
    horizon = max(1, ctl.cfg.mpc.horizon_steps)
    dt_h = sim.T_f_h
    prev_vsl = float(previous.vsl.get(link, max(ctl.cfg.freeway_follower.vsl_set)))
    smooth_w = ctl.cfg.freeway_follower.vsl_smoothness_weight
    vsl_set = sorted(float(v) for v in ctl.cfg.freeway_follower.vsl_set)
    max_step = ctl.cfg.freeway_follower.max_vsl_step
    candidates = [v for v in vsl_set if abs(v - prev_vsl) <= max_step + 1e-9] or vsl_set

    rows = []
    for vsl in candidates:
        probe = state.copy()
        candidate_control = ControlAction(
            ramp_metering=dict(previous.ramp_metering),
            vsl=dict(previous.vsl),
            green_times=dict(previous.green_times),
            offsets=dict(previous.offsets),
            inflow_outflow_allocation={},
        )
        candidate_control.vsl[link] = float(vsl)
        tts = 0.0
        for _ in range(horizon):
            for _ in range(sim.K_cf):
                for ramp in net.ramps:
                    approach_flow = max(0.0, float(coupling.get(f"u_on_{ramp}", 0.0)))
                    probe.ramp_queue[ramp] = min(
                        net.ramp_queue_max_veh,
                        max(0.0, probe.ramp_queue.get(ramp, 0.0)) + approach_flow * dt_h,
                    )
                ramp_release, ramp_diag = compute_ramp_release_flows(
                    probe, candidate_control, demand, ctl.cfg, include_current_arrivals=False
                )
                for ramp, release in ramp_release.items():
                    probe.ramp_queue[ramp] = max(
                        0.0, probe.ramp_queue.get(ramp, 0.0) - max(0.0, release) * dt_h
                    )
                offramp_capacity = off_ramp_capacity_by_freeway_link(probe.copy(), ctl.cfg, interval_h=dt_h)
                _, fw_diag = freeway_substep(
                    probe, candidate_control, demand, ctl.cfg,
                    offramp_capacity_veh_h=offramp_capacity,
                    ramp_release_veh_h=ramp_release, ramp_release_diagnostics=ramp_diag,
                    update_ramp_queues=False, include_ramp_queue_ttt=False,
                )
                ctl._update_probe_offramp_storage(probe, fw_diag, candidate_control, dt_h)
                link_vehicles = sum(probe.freeway_vehicle_count_by_link(net).get(link, []))
                link_ramp_queue = sum(
                    max(0.0, probe.ramp_queue.get(ramp, 0.0))
                    for ramp in net.ramps if net.ramp_to_freeway.get(ramp) == link
                )
                tts += (link_vehicles + link_ramp_queue) * dt_h
        smooth = smooth_w * abs(vsl - prev_vsl)
        rows.append((vsl, tts, smooth, tts + smooth))
    return rows


def main():
    cfg = ExperimentConfig.from_file("src/config/default.yaml", {"simulation": {"T_total": 1800.0}})
    scenario = load_scenarios("src/config/scenarios.yaml")["capacity_drop"]
    cfg = apply_scenario_network_overrides(cfg, scenario)
    prof = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    ctl = WuDistributedController(cfg, leader_enabled=False)
    prev = None
    cap = 120.0

    # 최혼잡(off-ramp 점유 최대) interval을 닫힌루프로 찾는다.
    states = []
    steps = int(round(cfg.simulation.T_total / cfg.simulation.control_interval))
    for step in range(steps):
        t = step * cfg.simulation.control_interval
        fc = prof.horizon(t, cfg.mpc.horizon_steps)
        info = ctl.decide_with_info(sim.state.copy(), fc, prev)
        ctrl = info.control
        occ = max(
            (cap - sim.state.urban_link_storage.get(f"OR_{o}_storage", cap)) / cap
            for o in ["D_E", "D_W", "F_E", "F_W"]
        )
        states.append((step, occ, sim.state.copy(), prev, fc[0]))
        sim.step(ctrl, fc[0], step)
        prev = ctrl

    step, occ, state, previous, demand = max(states, key=lambda x: x[1])
    if previous is None:
        previous = _wu_fixed_control(cfg)
    # prev_vsl=max(=100)에서 시작(정직한 출발점).
    for lk in cfg.network.freeway_links:
        previous.vsl[lk] = max(cfg.freeway_follower.vsl_set)
    print(f"most congested step={step} off-ramp occ={occ * 100:.1f}%")
    coupling = ctl._coupling(state, previous, demand)
    smooth_w = cfg.freeway_follower.vsl_smoothness_weight
    print(f"vsl_smoothness_weight={smooth_w}")
    for link in cfg.network.freeway_links:
        rows = candidate_costs(ctl, link, state, coupling, demand, previous)
        base = next(r for r in rows if r[0] == 100.0)
        print(f"\n[{link}] candidate cost breakdown (prev_vsl=100):")
        print("  vsl   TTS_term   smooth   total      dTTS_vs100   dSmooth_vs100")
        for vsl, tts, smooth, total in rows:
            d_tts = tts - base[1]
            d_smooth = smooth - base[2]
            print(f"  {vsl:5.0f} {tts:10.4f} {smooth:8.4f} {total:10.4f}  {d_tts:+11.5f}  {d_smooth:+11.5f}")
        # VSL↓(가장 낮은 후보)의 TTS 이득 vs smoothness 페널티 배율.
        low = min(rows, key=lambda r: r[0])
        tts_gain = base[1] - low[1]  # 양수면 VSL↓가 TTS를 줄임(이득).
        smooth_pen = low[2] - base[2]  # VSL↓의 추가 smoothness 페널티.
        ratio = (smooth_pen / tts_gain) if abs(tts_gain) > 1e-12 else float("inf")
        print(f"  -> VSL {low[0]:.0f} vs 100: TTS_gain={tts_gain:+.5f} veh*h, "
              f"smooth_penalty={smooth_pen:+.5f}, penalty/gain={ratio:.2f}")


if __name__ == "__main__":
    main()
