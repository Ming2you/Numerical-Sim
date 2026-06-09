from __future__ import annotations

import math
from typing import Dict, Tuple

from .demand import DemandStep
from .state import ControlAction, ExperimentConfig, TrafficState


def segment_flow_veh_h(rho_veh_km_lane: float, speed_km_h: float, lanes: float) -> float:
    """METANET segment flow q = rho * v * lanes in veh/h."""
    return float(max(rho_veh_km_lane, 0.0) * max(speed_km_h, 0.0) * max(lanes, 0.0))


def desired_speed_kmh(rho: float, v_free: float, rho_crit: float, a: float = 1.867) -> float:
    ratio = max(rho, 0.0) / max(rho_crit, 1.0e-9)
    return float(v_free * math.exp(-(1.0 / a) * (ratio ** a)))


def effective_desired_speed_kmh(
    rho: float,
    v_free: float,
    rho_crit: float,
    vsl: float,
    alpha_vsl: float = 0.0,
    vsl_active: bool = True,
    a: float = 1.867,
) -> float:
    """Compute V_eff from the split spec's VSL desired-speed rule."""
    no_vsl = desired_speed_kmh(rho, v_free, rho_crit, a)
    if not vsl_active:
        return no_vsl
    return float(min(no_vsl, (1.0 + alpha_vsl) * vsl))


def metanet_speed_update_kmh(
    speed: float,
    upstream_speed: float,
    rho: float,
    downstream_rho: float,
    v_eff: float,
    dt_h: float,
    length_km: float,
    tau_h: float,
    nu_km2_h: float,
    kappa_veh_km_lane: float,
    v_min: float,
) -> float:
    """METANET relaxation + convection + anticipation speed update."""
    relaxation = dt_h / max(tau_h, 1.0e-9) * (v_eff - speed)
    convection = dt_h / max(length_km, 1.0e-9) * speed * (upstream_speed - speed)
    anticipation = (
        -nu_km2_h
        * dt_h
        / (max(tau_h, 1.0e-9) * max(length_km, 1.0e-9))
        * (downstream_rho - rho)
        / max(rho + kappa_veh_km_lane, 1.0e-9)
    )
    return float(max(v_min, speed + relaxation + convection + anticipation))


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _nuf_target_flow_veh_h(control: ControlAction, cfg: ExperimentConfig) -> float:
    if cfg.leader.N_UF_star_unit == "veh_per_control_interval":
        return float(control.N_UF_star / max(cfg.simulation.T_c_h, 1.0e-9))
    return float(control.N_UF_star)


def _ramp_merge_index(cfg: ExperimentConfig, ramp: str, n_segments: int) -> int:
    configured = getattr(cfg.network, "ramp_merge_segment_index", {})
    if isinstance(configured, dict) and ramp in configured:
        return int(_clip(float(configured[ramp]), 0.0, float(n_segments - 1)))
    return n_segments // 2


def freeway_step(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
    offramp_capacity_veh_h: Dict[str, float] | None = None,
) -> Tuple[float, Dict[str, float]]:
    """Advance the freeway model over one controller interval.

    The controller action is held constant over `K_cf` METANET substeps.
    Returns freeway TTT contribution and diagnostics. Units are veh*h.
    """
    net = cfg.network
    sim = cfg.simulation
    dt_h = sim.T_f_h
    substeps = sim.K_cf
    diagnostics: Dict[str, float] = {}

    state.refresh_freeway_flow(net)
    freeway_ttt = 0.0
    total_metering_flow_acc = 0.0
    total_no_meter_flow_acc = 0.0
    receiving_factor_acc = 0.0
    receiving_factor_count = 0
    ramp_overflow_max = 0.0
    density_projection_count = 0
    speed_projection_count = 0
    flow_acc = 0.0
    flow_count = 0
    offramp_flow_acc: Dict[str, float] = {link: 0.0 for link in net.freeway_links}
    offramp_blocked_acc: Dict[str, float] = {link: 0.0 for link in net.freeway_links}
    cap_factor = getattr(demand, "incident_capacity_factor", 1.0)
    q_cap = net.freeway_capacity_veh_h * cap_factor
    target_flow = _nuf_target_flow_veh_h(control, cfg)

    for _ in range(substeps):
        ramp_release: Dict[str, float] = {}
        ramp_in_by_link = {
            link: [0.0 for _ in state.freeway_density[link]]
            for link in net.freeway_links
        }
        no_meter_total = 0.0

        for ramp in net.ramps:
            link = net.ramp_to_freeway[ramp]
            merge_idx = _ramp_merge_index(cfg, ramp, len(state.freeway_density[link]))
            rho_merge = state.freeway_density[link][merge_idx]
            receiving_factor = _clip(
                (net.rho_max - rho_merge) / max(net.rho_max - net.rho_crit, 1.0e-9),
                0.0,
                1.0,
            )
            receiving_factor_acc += receiving_factor
            receiving_factor_count += 1

            cap = net.ramp_capacity_veh_h[ramp]
            arrival = demand.ramp_arrival.get(ramp, 0.0)
            requested = _clip(control.ramp_metering.get(ramp, cap), 0.0, cap)
            available = max(0.0, arrival + state.ramp_queue.get(ramp, 0.0) / max(dt_h, 1.0e-9))
            no_meter = min(available, cap, q_cap * receiving_factor)
            release = min(no_meter, requested)
            ramp_release[ramp] = release
            ramp_in_by_link[link][merge_idx] += release
            no_meter_total += no_meter

            next_queue = state.ramp_queue.get(ramp, 0.0) + dt_h * (arrival - release)
            state.ramp_queue[ramp] = max(0.0, next_queue)

        total_metering = sum(ramp_release.values())
        total_metering_flow_acc += total_metering
        total_no_meter_flow_acc += no_meter_total

        for link in net.freeway_links:
            rhos = list(state.freeway_density[link])
            speeds = list(state.freeway_speed[link])
            vsl = control.vsl.get(link, max(cfg.freeway_follower.vsl_set))
            vsl_active = vsl < max(cfg.freeway_follower.vsl_set) - 0.5
            q_values = list(state.freeway_flow.get(link, []))
            if len(q_values) != len(rhos):
                q_values = [
                    segment_flow_veh_h(rho, speed, net.freeway_lanes)
                    for rho, speed in zip(rhos, speeds)
                ]
            flow_acc += sum(q_values)
            flow_count += len(q_values)

            next_rhos = []
            next_speeds = []
            next_flows = []
            for i, rho in enumerate(rhos):
                q_in = min(q_cap, demand.freeway_mainline.get(link, 0.0)) if i == 0 else q_values[i - 1]
                q_in += ramp_in_by_link[link][i]
                q_out = q_values[i]
                boundary_speed_cap = None
                if i == len(rhos) - 1:
                    normal_out = q_values[i]
                    off_ratio = sum(
                        ratio
                        for off_ramp, ratio in net.off_ramp_split_ratio.items()
                        if net.off_ramp_from_freeway.get(off_ramp) == link
                    )
                    off_ratio = _clip(off_ratio, 0.0, 1.0)
                    normal_off = off_ratio * normal_out
                    cap = None if offramp_capacity_veh_h is None else offramp_capacity_veh_h.get(link)
                    effective_off = normal_off if cap is None else min(normal_off, max(0.0, cap))
                    q_out = (1.0 - off_ratio) * normal_out + effective_off
                    offramp_flow_acc[link] += effective_off
                    offramp_blocked_acc[link] += max(0.0, normal_off - effective_off)
                    if normal_off > effective_off + 1.0e-9:
                        boundary_speed_cap = q_out / max(rho * net.freeway_lanes, 1.0e-9)
                rho_raw = rho + dt_h / (net.freeway_segment_length_km * net.freeway_lanes) * (q_in - q_out)
                rho_new = _clip(rho_raw, 0.0, net.rho_max)
                if abs(rho_new - rho_raw) > 1.0e-9:
                    density_projection_count += 1

                upstream_speed = net.v_free if i == 0 else speeds[i - 1]
                downstream_rho = rhos[i + 1] if i + 1 < len(rhos) else rhos[i]
                v_eff = effective_desired_speed_kmh(
                    rho,
                    net.v_free,
                    net.rho_crit,
                    vsl,
                    net.alpha_vsl,
                    vsl_active,
                    net.metanet_a_m,
                )
                v_new = metanet_speed_update_kmh(
                    speeds[i],
                    upstream_speed,
                    rho,
                    downstream_rho,
                    v_eff,
                    dt_h,
                    net.freeway_segment_length_km,
                    net.metanet_tau_h,
                    net.metanet_nu_km2_h,
                    net.metanet_kappa_veh_km_lane,
                    net.v_min,
                )
                if v_new <= net.v_min + 1.0e-9:
                    speed_projection_count += 1
                if boundary_speed_cap is not None and v_new > boundary_speed_cap:
                    v_new = max(net.v_min, boundary_speed_cap)
                    speed_projection_count += 1
                next_rhos.append(rho_new)
                next_speeds.append(v_new)
                next_flows.append(segment_flow_veh_h(rho_new, v_new, net.freeway_lanes))

            state.freeway_density[link] = next_rhos
            state.freeway_speed[link] = next_speeds
            state.freeway_flow[link] = next_flows
            freeway_ttt += sum(next_rhos) * net.freeway_segment_length_km * net.freeway_lanes * dt_h

        freeway_ttt += sum(state.ramp_queue.values()) * dt_h
        ramp_overflow_max = max(ramp_overflow_max, float(sum(
            1 for q in state.ramp_queue.values() if q > net.ramp_queue_max_veh
        )))

    avg_metering = total_metering_flow_acc / max(substeps, 1)
    avg_no_meter = total_no_meter_flow_acc / max(substeps, 1)
    diagnostics["total_metering_flow"] = float(avg_metering)
    diagnostics["total_metering_error"] = abs(avg_metering - target_flow)
    diagnostics["metering_target_infeasible"] = float(target_flow > avg_no_meter + cfg.freeway_follower.eps_F)
    diagnostics["ramp_queue_overflow_count"] = ramp_overflow_max
    diagnostics["mean_ramp_receiving_factor"] = (
        receiving_factor_acc / receiving_factor_count if receiving_factor_count else 1.0
    )
    diagnostics["mean_segment_flow"] = flow_acc / flow_count if flow_count else 0.0
    diagnostics["offramp_storage_binding"] = float(any(v > 1.0e-9 for v in offramp_blocked_acc.values()))
    diagnostics["offramp_flow_total"] = float(sum(offramp_flow_acc.values()) / max(substeps, 1))
    diagnostics["offramp_blocked_flow_total"] = float(sum(offramp_blocked_acc.values()) / max(substeps, 1))
    for link in net.freeway_links:
        diagnostics[f"offramp_flow_{link}"] = float(offramp_flow_acc.get(link, 0.0) / max(substeps, 1))
        diagnostics[f"offramp_blocked_flow_{link}"] = float(offramp_blocked_acc.get(link, 0.0) / max(substeps, 1))
    diagnostics["density_projection_count"] = float(density_projection_count)
    diagnostics["speed_projection_count"] = float(speed_projection_count)
    diagnostics["density_exceedance_count"] = float(sum(
        1
        for values in state.freeway_density.values()
        for rho in values
        if rho > net.rho_crit
    ))
    return float(freeway_ttt), diagnostics
