from __future__ import annotations

import math
from typing import Dict, Tuple

from .demand import DemandStep
from .state import ControlAction, ExperimentConfig, TrafficState


def desired_speed_kmh(rho: float, v_free: float, rho_crit: float, a: float = 1.867) -> float:
    ratio = max(rho, 0.0) / max(rho_crit, 1.0e-9)
    return float(v_free * math.exp(-(1.0 / a) * (ratio ** a)))


def freeway_step(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
) -> Tuple[float, Dict[str, float]]:
    """Advance freeway state one control interval.

    Returns freeway TTT contribution and diagnostics. Units are veh*h.
    """
    net = cfg.network
    dt_h = cfg.simulation.control_interval_h
    diagnostics: Dict[str, float] = {}

    ramp_release: Dict[str, float] = {}
    for ramp in net.ramps:
        cap = net.ramp_capacity_veh_h[ramp]
        arrival = demand.ramp_arrival.get(ramp, 0.0)
        requested = control.ramp_metering.get(ramp, cap)
        available = arrival + state.ramp_queue.get(ramp, 0.0) / max(dt_h, 1.0e-9)
        release = min(max(requested, 0.0), cap, max(available, 0.0))
        ramp_release[ramp] = release
        next_queue = state.ramp_queue.get(ramp, 0.0) + dt_h * (arrival - release)
        state.ramp_queue[ramp] = max(0.0, next_queue)

    total_metering = sum(ramp_release.values())
    diagnostics["total_metering_flow"] = float(total_metering)
    diagnostics["total_metering_error"] = abs(total_metering - control.N_UF_star)
    diagnostics["ramp_queue_overflow_count"] = float(sum(
        1 for q in state.ramp_queue.values() if q > net.ramp_queue_max_veh
    ))

    freeway_ttt = 0.0
    for link in net.freeway_links:
        rhos = state.freeway_density[link]
        speeds = state.freeway_speed[link]
        vsl = control.vsl.get(link, max(cfg.freeway_follower.vsl_set))
        cap_factor = getattr(demand, "incident_capacity_factor", 1.0)
        q_cap = net.freeway_capacity_veh_h * cap_factor
        link_ramps = [r for r in net.ramps if net.ramp_to_freeway[r] == link]
        ramp_in = sum(ramp_release[r] for r in link_ramps)
        main_in = demand.freeway_mainline.get(link, 0.0)
        prev_out = min(q_cap, main_in)
        next_rhos = []
        next_speeds = []
        for i, rho in enumerate(rhos):
            veh = rho * net.freeway_segment_length_km * net.freeway_lanes
            flow = min(
                q_cap,
                max(0.0, rho * max(speeds[i], 1.0) * net.freeway_lanes),
                veh / max(dt_h, 1.0e-9) + prev_out,
            )
            seg_in = prev_out + (ramp_in / len(rhos) if i == len(rhos) // 2 else 0.0)
            next_veh = max(0.0, veh + dt_h * (seg_in - flow))
            rho_new = min(net.rho_max, next_veh / (net.freeway_segment_length_km * net.freeway_lanes))
            v_des = min(desired_speed_kmh(rho_new, net.v_free, net.rho_crit), vsl)
            v_new = max(5.0, 0.65 * speeds[i] + 0.35 * v_des)
            next_rhos.append(rho_new)
            next_speeds.append(v_new)
            prev_out = flow
        state.freeway_density[link] = next_rhos
        state.freeway_speed[link] = next_speeds
        freeway_ttt += sum(next_rhos) * net.freeway_segment_length_km * net.freeway_lanes * dt_h

    freeway_ttt += sum(state.ramp_queue.values()) * dt_h
    diagnostics["density_exceedance_count"] = float(sum(
        1
        for values in state.freeway_density.values()
        for rho in values
        if rho > net.rho_crit
    ))
    return float(freeway_ttt), diagnostics
