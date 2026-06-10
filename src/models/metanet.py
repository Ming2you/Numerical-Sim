from __future__ import annotations

import math
from typing import Dict, List, Tuple

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


def offramp_spillback_lambda_eff(
    occupancy_veh: float,
    capacity_veh: float,
    nominal_lanes: float,
    lane_reduction: float,
    gamma: float,
    b: float,
) -> float:
    """Wu Eq.(22) 계열 spill-back lane reduction을 분수 차로 감소까지 일반화한다."""
    if capacity_veh <= 0.0 or lane_reduction <= 0.0:
        return float(nominal_lanes)
    occupancy = _clip(float(occupancy_veh), 0.0, float(capacity_veh))
    if occupancy <= 1.0e-9:
        return float(nominal_lanes)
    if occupancy >= capacity_veh - 1.0e-9:
        return float(max(1.0e-9, nominal_lanes - lane_reduction))
    scale = occupancy / max(gamma * capacity_veh, 1.0e-9)
    decay = math.exp(-(1.0 / max(b, 1.0e-9)) * (scale ** b))
    return float(max(1.0e-9, nominal_lanes - lane_reduction * (1.0 - decay)))


def effective_lane_profile(
    state: TrafficState,
    cfg: ExperimentConfig,
) -> Tuple[Dict[str, List[float]], Dict[str, float]]:
    """현재 off-ramp storage 점유율에서 freeway segment별 effective lane profile을 계산한다."""
    net = cfg.network
    drop = cfg.freeway_offramp_capacity_drop
    state.ensure_freeway_lane_profile(net)
    profile = {
        link: [float(net.freeway_lanes) for _ in state.freeway_density.get(link, [])]
        for link in net.freeway_links
    }
    diagnostics: Dict[str, float] = {"capacity_drop_active": 0.0}
    if not drop.enabled:
        for link, lanes in profile.items():
            if lanes:
                diagnostics[f"lambda_eff_{link}_last"] = float(lanes[-1])
                diagnostics[f"capacity_drop_lane_loss_{link}_last"] = 0.0
        return profile, diagnostics

    for off_ramp in net.off_ramps:
        link = net.off_ramp_from_freeway.get(off_ramp)
        if link not in profile or not profile[link]:
            continue
        storage_link = net.off_ramp_storage_link.get(off_ramp)
        capacity = float(net.urban_link_storage_veh.get(storage_link, 0.0))
        available = float(state.urban_link_storage.get(storage_link, capacity))
        occupancy = _clip(capacity - available, 0.0, capacity)
        ratio = occupancy / max(capacity, 1.0e-9)
        lambda_eff = offramp_spillback_lambda_eff(
            occupancy,
            capacity,
            float(net.freeway_lanes),
            float(drop.lane_reduction),
            float(drop.gamma),
            float(drop.b),
        )
        last_idx = len(profile[link]) - 1
        profile[link][last_idx] = min(profile[link][last_idx], lambda_eff)
        diagnostics[f"offramp_occupancy_ratio_{off_ramp}"] = float(ratio)
        diagnostics[f"lambda_eff_{link}_last"] = float(profile[link][last_idx])
        diagnostics[f"capacity_drop_lane_loss_{link}_last"] = float(
            max(0.0, net.freeway_lanes - profile[link][last_idx])
        )

    for link, lanes in profile.items():
        if not lanes:
            continue
        diagnostics.setdefault(f"lambda_eff_{link}_last", float(lanes[-1]))
        diagnostics.setdefault(f"capacity_drop_lane_loss_{link}_last", 0.0)
        if lanes[-1] < net.freeway_lanes - 1.0e-9:
            diagnostics["capacity_drop_active"] = 1.0
    return profile, diagnostics


def compute_ramp_release_flows(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
    include_current_arrivals: bool = True,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Spec 3.2 ramp outflow 제약을 한 `T_f` 경계에서 계산한다."""
    net = cfg.network
    dt_h = cfg.simulation.T_f_h
    cap_factor = getattr(demand, "incident_capacity_factor", 1.0)
    q_cap = net.freeway_capacity_veh_h * cap_factor
    ramp_release: Dict[str, float] = {}
    receiving_factor_acc = 0.0
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

        cap = net.ramp_capacity_veh_h[ramp]
        arrival = demand.ramp_arrival.get(ramp, 0.0) if include_current_arrivals else 0.0
        requested = _clip(control.ramp_metering.get(ramp, cap), 0.0, cap)
        available = max(0.0, arrival + state.ramp_queue.get(ramp, 0.0) / max(dt_h, 1.0e-9))
        no_meter = min(available, cap, q_cap * receiving_factor)
        release = min(no_meter, requested)
        ramp_release[ramp] = release
        no_meter_total += no_meter

    diagnostics = {
        "total_metering_flow": float(sum(ramp_release.values())),
        "total_no_meter_flow": float(no_meter_total),
        "mean_ramp_receiving_factor": (
            receiving_factor_acc / max(len(net.ramps), 1)
        ),
    }
    return ramp_release, diagnostics


def freeway_substep(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
    offramp_capacity_veh_h: Dict[str, float] | None = None,
    ramp_release_veh_h: Dict[str, float] | None = None,
    ramp_release_diagnostics: Dict[str, float] | None = None,
    update_ramp_queues: bool = True,
    include_ramp_queue_ttt: bool = True,
) -> Tuple[float, Dict[str, float]]:
    """Spec 3.1/3.2 METANET plant를 정확히 한 `T_f` step만 전진한다."""
    net = cfg.network
    sim = cfg.simulation
    dt_h = sim.T_f_h

    state.ensure_freeway_lane_profile(net)
    freeway_ttt = 0.0
    density_projection_count = 0
    speed_projection_count = 0
    flow_acc = 0.0
    flow_count = 0
    offramp_flow_acc: Dict[str, float] = {link: 0.0 for link in net.freeway_links}
    offramp_blocked_acc: Dict[str, float] = {link: 0.0 for link in net.freeway_links}
    cap_factor = getattr(demand, "incident_capacity_factor", 1.0)
    q_cap = net.freeway_capacity_veh_h * cap_factor
    target_flow = _nuf_target_flow_veh_h(control, cfg)

    if ramp_release_veh_h is None:
        ramp_release, ramp_diag = compute_ramp_release_flows(state, control, demand, cfg)
    else:
        ramp_release = dict(ramp_release_veh_h)
        ramp_diag = (
            dict(ramp_release_diagnostics)
            if ramp_release_diagnostics is not None
            else compute_ramp_release_flows(state, control, demand, cfg)[1]
        )

    ramp_in_by_link = {
        link: [0.0 for _ in state.freeway_density[link]]
        for link in net.freeway_links
    }
    for ramp, release in ramp_release.items():
        link = net.ramp_to_freeway[ramp]
        merge_idx = _ramp_merge_index(cfg, ramp, len(state.freeway_density[link]))
        ramp_in_by_link[link][merge_idx] += max(0.0, release)
        if update_ramp_queues:
            # standalone freeway_step에서는 ramp demand와 release를 여기서 보존식으로 갱신한다.
            arrival = demand.ramp_arrival.get(ramp, 0.0)
            next_queue = state.ramp_queue.get(ramp, 0.0) + dt_h * (arrival - release)
            state.ramp_queue[ramp] = max(0.0, next_queue)

    lane_now_by_link, lane_diag_start = effective_lane_profile(state, cfg)
    for link in net.freeway_links:
        rhos = list(state.freeway_density[link])
        speeds = list(state.freeway_speed[link])
        previous_lanes = list(state.freeway_effective_lanes.get(link, []))
        lanes_now = lane_now_by_link[link]
        vehicles = [
            max(0.0, rho) * net.freeway_segment_length_km * max(lane, 1.0e-9)
            for rho, lane in zip(rhos, previous_lanes)
        ]
        rho_for_flow = [
            n / max(net.freeway_segment_length_km * max(lane, 1.0e-9), 1.0e-9)
            for n, lane in zip(vehicles, lanes_now)
        ]
        vsl = control.vsl.get(link, max(cfg.freeway_follower.vsl_set))
        vsl_active = vsl < max(cfg.freeway_follower.vsl_set) - 0.5
        q_values = [
            segment_flow_veh_h(rho, speed, lane)
            for rho, speed, lane in zip(rho_for_flow, speeds, lanes_now)
        ]
        flow_acc += sum(q_values)
        flow_count += len(q_values)

        next_rhos = []
        next_speeds = []
        next_flows = []
        next_lanes = []
        next_vehicle_count = []
        for i, rho in enumerate(rho_for_flow):
            # Spec 3.1.2 밀도 갱신: q_in/q_out은 veh/h, dt는 hour 단위로 계산한다.
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
                    boundary_speed_cap = q_out / max(rho * lanes_now[i], 1.0e-9)
            vehicle_raw = vehicles[i] + dt_h * (q_in - q_out)
            vehicle_new = max(0.0, vehicle_raw)
            if abs(vehicle_new - vehicle_raw) > 1.0e-9:
                density_projection_count += 1
            rho_new = vehicle_new / max(net.freeway_segment_length_km * max(lanes_now[i], 1.0e-9), 1.0e-9)

            upstream_speed = net.v_free if i == 0 else speeds[i - 1]
            downstream_rho = rho_for_flow[i + 1] if i + 1 < len(rhos) else rho_for_flow[i]
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
            next_lanes.append(float(lanes_now[i]))
            next_vehicle_count.append(float(vehicle_new))
            next_flows.append(segment_flow_veh_h(rho_new, v_new, lanes_now[i]))

        state.freeway_density[link] = next_rhos
        state.freeway_speed[link] = next_speeds
        state.freeway_flow[link] = next_flows
        state.freeway_effective_lanes[link] = next_lanes
        freeway_ttt += sum(next_vehicle_count) * dt_h

    if include_ramp_queue_ttt:
        freeway_ttt += sum(state.ramp_queue.values()) * dt_h

    diagnostics: Dict[str, float] = {}
    avg_metering = float(sum(ramp_release.values()))
    avg_no_meter = ramp_diag["total_no_meter_flow"]
    diagnostics["total_metering_flow"] = avg_metering
    diagnostics["total_metering_error"] = abs(avg_metering - target_flow)
    diagnostics["metering_target_infeasible"] = float(target_flow > avg_no_meter + cfg.freeway_follower.eps_F)
    diagnostics["ramp_queue_overflow_count"] = float(sum(
        1 for q in state.ramp_queue.values() if q > net.ramp_queue_max_veh
    ))
    diagnostics["mean_ramp_receiving_factor"] = ramp_diag["mean_ramp_receiving_factor"]
    diagnostics["mean_segment_flow"] = flow_acc / flow_count if flow_count else 0.0
    diagnostics.update(lane_diag_start)
    diagnostics["offramp_storage_binding"] = float(any(v > 1.0e-9 for v in offramp_blocked_acc.values()))
    diagnostics["offramp_flow_total"] = float(sum(offramp_flow_acc.values()))
    diagnostics["offramp_blocked_flow_total"] = float(sum(offramp_blocked_acc.values()))
    for link in net.freeway_links:
        diagnostics[f"offramp_flow_{link}"] = float(offramp_flow_acc.get(link, 0.0))
        diagnostics[f"offramp_blocked_flow_{link}"] = float(offramp_blocked_acc.get(link, 0.0))
    diagnostics["density_projection_count"] = float(density_projection_count)
    diagnostics["speed_projection_count"] = float(speed_projection_count)
    diagnostics["density_exceedance_count"] = float(sum(
        1
        for values in state.freeway_density.values()
        for rho in values
        if rho > net.rho_crit
    ))
    return float(freeway_ttt), diagnostics


def _aggregate_freeway_diagnostics(rows: list[Dict[str, float]]) -> Dict[str, float]:
    if not rows:
        return {}
    avg_keys = {
        "total_metering_flow",
        "total_metering_error",
        "mean_ramp_receiving_factor",
        "mean_segment_flow",
        "offramp_flow_total",
        "offramp_blocked_flow_total",
    }
    out: Dict[str, float] = {}
    keys = set().union(*(row.keys() for row in rows))
    for key in keys:
        values = [row.get(key, 0.0) for row in rows]
        if (
            key in avg_keys
            or key.startswith("offramp_flow_")
            or key.startswith("offramp_blocked_flow_")
            or key.startswith("lambda_eff_")
            or key.startswith("capacity_drop_lane_loss_")
            or key.startswith("offramp_occupancy_ratio_")
        ):
            out[key] = float(sum(values) / max(len(values), 1))
        elif key in {"metering_target_infeasible", "offramp_storage_binding", "capacity_drop_active"}:
            out[key] = float(max(values))
        else:
            out[key] = float(sum(values))
    return out


def freeway_step(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
    offramp_capacity_veh_h: Dict[str, float] | None = None,
) -> Tuple[float, Dict[str, float]]:
    """기존 API 호환용 wrapper: 한 control interval 동안 `K_cf`개 freeway substep을 실행한다."""
    total_ttt = 0.0
    diagnostics: list[Dict[str, float]] = []
    for _ in range(cfg.simulation.K_cf):
        fw_ttt, fw_diag = freeway_substep(
            state,
            control,
            demand,
            cfg,
            offramp_capacity_veh_h=offramp_capacity_veh_h,
        )
        total_ttt += fw_ttt
        diagnostics.append(fw_diag)
    return float(total_ttt), _aggregate_freeway_diagnostics(diagnostics)
