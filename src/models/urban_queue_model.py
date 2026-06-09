from __future__ import annotations

import math
from typing import Dict, Iterable, Mapping, Tuple

import numpy as np

from .demand import DemandStep
from .state import ControlAction, ExperimentConfig, TrafficState


def safe_balance_index(values: Iterable[float], eps: float = 1.0e-9) -> float:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0 or float(np.sum(np.abs(arr))) <= eps:
        return 0.0
    l1 = float(np.sum(np.abs(arr)))
    l2_sq = float(np.sum(arr * arr))
    return max(0.0, l2_sq / max(l1 * l1, eps) - 1.0 / arr.size)


def boundary_indices(values: Iterable[float], queue_max: float, eps: float = 1.0e-9) -> Dict[str, float]:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return {"CV_boundary": 0.0, "MaxMin_boundary": 0.0, "OverflowRatio_boundary": 0.0}
    mean = float(np.mean(arr))
    return {
        "CV_boundary": float(np.std(arr) / max(mean, eps)) if mean > eps else 0.0,
        "MaxMin_boundary": float(np.max(arr) - np.min(arr)),
        "OverflowRatio_boundary": float(np.mean(arr > queue_max)),
    }


def movement_specs(cfg: ExperimentConfig) -> Dict[str, Dict[str, object]]:
    return {key: dict(value) for key, value in cfg.network.urban_movements.items()}


def ensure_urban_state(state: TrafficState, cfg: ExperimentConfig) -> None:
    net = cfg.network
    if not state.urban_movement_queue:
        state.urban_movement_queue = {
            movement: (0.0 if spec.get("kind") == "on_ramp" else 20.0)
            for movement, spec in movement_specs(cfg).items()
        }
    for movement, spec in movement_specs(cfg).items():
        state.urban_movement_queue.setdefault(
            movement,
            0.0 if spec.get("kind") == "on_ramp" else 20.0,
        )
        state.urban_arrival_buffer.setdefault(movement, {})
    for link, capacity in net.urban_link_storage_veh.items():
        state.urban_link_storage.setdefault(link, capacity)
        state.urban_storage_release_buffer.setdefault(link, {})
    _sync_legacy_queues(state, cfg)


def sync_onramp_queues_from_freeway(state: TrafficState, cfg: ExperimentConfig) -> None:
    ensure_urban_state(state, cfg)
    for ramp, movement in cfg.network.on_ramp_to_movement.items():
        if movement in state.urban_movement_queue:
            state.urban_movement_queue[movement] = max(0.0, state.ramp_queue.get(ramp, 0.0))
    _sync_legacy_queues(state, cfg)


def sync_onramp_queues_to_freeway(state: TrafficState, cfg: ExperimentConfig) -> None:
    ensure_urban_state(state, cfg)
    for ramp, movement in cfg.network.on_ramp_to_movement.items():
        if movement in state.urban_movement_queue:
            state.ramp_queue[ramp] = max(0.0, state.urban_movement_queue.get(movement, 0.0))
    _sync_legacy_queues(state, cfg)


def schedule_offramp_arrivals(
    state: TrafficState,
    cfg: ExperimentConfig,
    off_ramp: str,
    vehicles: float,
    urban_step_index: int,
) -> tuple[float, float]:
    """Insert freeway-to-off-ramp vehicles into directed urban storage.

    Returns `(accepted, rejected)` in vehicles.
    """
    ensure_urban_state(state, cfg)
    if vehicles <= 0.0:
        return 0.0, 0.0
    net = cfg.network
    storage_link = net.off_ramp_storage_link[off_ramp]
    movement = net.off_ramp_to_movement[off_ramp]
    available = max(0.0, state.urban_link_storage.get(storage_link, 0.0))
    accepted = min(float(vehicles), available)
    rejected = max(0.0, float(vehicles) - accepted)
    if accepted <= 0.0:
        return 0.0, rejected
    state.urban_link_storage[storage_link] = max(0.0, available - accepted)
    delay_steps = _link_delay_steps(state, cfg, storage_link)
    arrival_step = urban_step_index + delay_steps
    _schedule(state.urban_arrival_buffer, movement, arrival_step, accepted)
    _schedule(state.urban_storage_release_buffer, storage_link, arrival_step, accepted)
    return accepted, rejected


def off_ramp_capacity_by_freeway_link(
    state: TrafficState,
    cfg: ExperimentConfig,
    interval_h: float | None = None,
) -> Dict[str, float]:
    ensure_urban_state(state, cfg)
    horizon_h = cfg.simulation.T_c_h if interval_h is None else interval_h
    cap: Dict[str, float] = {}
    for off_ramp in cfg.network.off_ramps:
        link = cfg.network.off_ramp_from_freeway[off_ramp]
        storage_link = cfg.network.off_ramp_storage_link[off_ramp]
        available = max(0.0, state.urban_link_storage.get(storage_link, 0.0))
        cap[link] = cap.get(link, 0.0) + available / max(horizon_h, 1.0e-9)
    return cap


def _urban_step_index(state: TrafficState, cfg: ExperimentConfig) -> int:
    return int(round(state.time_sec / max(cfg.simulation.T_u_sec, 1.0e-9)))


def _schedule(buffer: Dict[str, Dict[int, float]], key: str, step: int, vehicles: float) -> None:
    if vehicles <= 0.0:
        return
    buffer.setdefault(key, {})
    buffer[key][step] = buffer[key].get(step, 0.0) + float(vehicles)


def _pop_buffer(buffer: Dict[str, Dict[int, float]], key: str, step: int) -> float:
    values = buffer.setdefault(key, {})
    return float(values.pop(step, 0.0))


def _link_delay_steps(state: TrafficState, cfg: ExperimentConfig, storage_link: str) -> int:
    net = cfg.network
    capacity = net.urban_link_storage_veh.get(storage_link, net.boundary_queue_max_veh)
    available = max(0.0, state.urban_link_storage.get(storage_link, capacity))
    occupied = max(0.0, capacity - available)
    distance_km = occupied * net.urban_avg_vehicle_length_m / 1000.0
    travel_time_h = distance_km / max(net.urban_avg_speed_km_h, 1.0e-9)
    return max(1, int(math.ceil(travel_time_h / max(cfg.simulation.T_u_h, 1.0e-9))))


def _queue_max(cfg: ExperimentConfig, movement: str, spec: Mapping[str, object]) -> float:
    if spec.get("kind") == "on_ramp":
        ramp = str(spec.get("ramp", ""))
        return cfg.network.ramp_queue_max_veh if ramp else cfg.network.boundary_queue_max_veh
    return cfg.network.boundary_queue_max_veh


def _phase_green_fraction(control: ControlAction, cfg: ExperimentConfig, spec: Mapping[str, object]) -> float:
    phase = str(spec.get("phase", ""))
    if not phase:
        return 1.0
    default_green = cfg.network.effective_green_total / 2.0
    green_sec = control.green_times.get(phase, default_green)
    return float(np.clip(green_sec / max(cfg.network.cycle_length, 1.0e-9), 0.0, 1.0))


def _movement_capacity_flow(
    control: ControlAction,
    cfg: ExperimentConfig,
    movement: str,
    spec: Mapping[str, object],
) -> float:
    net = cfg.network
    origin = str(spec.get("origin", ""))
    destination = str(spec.get("destination", ""))
    return float(min(
        control.inflow_outflow_allocation.get(
            movement,
            control.inflow_outflow_allocation.get(
                origin,
                control.inflow_outflow_allocation.get(destination, net.movement_capacity_veh_h),
            ),
        ),
        net.movement_capacity_veh_h,
    ))


def _allocate_receiving_counts(rule: str, intended: Dict[str, float], total_space: float) -> Dict[str, float]:
    total = sum(max(v, 0.0) for v in intended.values())
    if total <= total_space or total <= 1.0e-9:
        return {k: max(v, 0.0) for k, v in intended.items()}
    if rule == "equal_split":
        share = total_space / max(len(intended), 1)
        return {k: min(max(v, 0.0), share) for k, v in intended.items()}
    if rule == "main_priority":
        out: Dict[str, float] = {}
        remaining = total_space
        for key in sorted(intended, key=lambda item: 0 if item.startswith("in_") else 1):
            val = min(max(intended[key], 0.0), remaining)
            out[key] = val
            remaining -= val
        return out
    return {k: max(v, 0.0) * total_space / total for k, v in intended.items()}


def _sync_legacy_queues(state: TrafficState, cfg: ExperimentConfig) -> None:
    specs = movement_specs(cfg)
    for link in cfg.network.movement_links:
        related = 0.0
        for movement, spec in specs.items():
            if spec.get("origin") == link or spec.get("destination") == link:
                related += state.urban_movement_queue.get(movement, 0.0)
        state.boundary_queue[link] = max(0.0, related)
        state.urban_queue[link] = max(0.0, related)


def _storage_occupancy(state: TrafficState, cfg: ExperimentConfig) -> float:
    total = 0.0
    for link, capacity in cfg.network.urban_link_storage_veh.items():
        total += max(0.0, capacity - state.urban_link_storage.get(link, capacity))
    return float(total)


def urban_substep(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
    urban_step_index: int | None = None,
    ramp_release_veh_h: Mapping[str, float] | None = None,
) -> Tuple[float, Dict[str, float]]:
    """movement-level horizontal queue를 `T_u` 한 스텝만 전진한다."""
    ensure_urban_state(state, cfg)
    net = cfg.network
    sim = cfg.simulation
    specs = movement_specs(cfg)
    diagnostics: Dict[str, float] = {
        "movement_queue_model_active": 1.0,
        "urban_storage_active": 1.0,
        "urban_substep_active": 1.0,
    }
    overflow_count = 0.0
    projection_count = 0.0
    inbound_service_veh = 0.0
    outbound_service_veh = 0.0
    onramp_arrivals_veh = 0.0
    onramp_release_request_veh = 0.0
    onramp_releases_veh = 0.0
    onramp_release_shortfall_veh = 0.0
    off_ramp_departures: Dict[str, float] = {r: 0.0 for r in net.off_ramps}
    step_idx = _urban_step_index(state, cfg) if urban_step_index is None else urban_step_index

    for link in net.urban_link_storage_veh:
        released = _pop_buffer(state.urban_storage_release_buffer, link, step_idx)
        if released > 0.0:
            cap = net.urban_link_storage_veh[link]
            state.urban_link_storage[link] = min(cap, state.urban_link_storage.get(link, cap) + released)

    for movement in specs:
        arrived = _pop_buffer(state.urban_arrival_buffer, movement, step_idx)
        if arrived > 0.0:
            state.urban_movement_queue[movement] += arrived

    by_origin: Dict[str, list[str]] = {}
    for movement, spec in specs.items():
        if spec.get("kind") == "boundary_in":
            by_origin.setdefault(str(spec.get("origin")), []).append(movement)
    for origin, movements in by_origin.items():
        arrival = demand.urban_boundary.get(origin, 0.0) * sim.T_u_h
        if arrival <= 0.0 or not movements:
            continue
        share = arrival / len(movements)
        for movement in movements:
            state.urban_movement_queue[movement] += share

    # on-ramp 수요는 urban movement queue로 들어오고, ramp metering release만큼 같은 queue에서 빠져나간다.
    for ramp, movement in net.on_ramp_to_movement.items():
        arrival = max(0.0, demand.ramp_arrival.get(ramp, 0.0)) * sim.T_u_h
        state.urban_movement_queue[movement] = state.urban_movement_queue.get(movement, 0.0) + arrival
        onramp_arrivals_veh += arrival

    if ramp_release_veh_h is not None:
        for ramp, release_flow in ramp_release_veh_h.items():
            movement = net.on_ramp_to_movement.get(ramp)
            if movement is None:
                continue
            requested = max(0.0, release_flow) * sim.T_u_h
            before = max(0.0, state.urban_movement_queue.get(movement, 0.0))
            actual = min(before, requested)
            state.urban_movement_queue[movement] = max(0.0, before - actual)
            onramp_release_request_veh += requested
            onramp_releases_veh += actual
            onramp_release_shortfall_veh += max(0.0, requested - actual)

    intended_by_storage: Dict[str, Dict[str, float]] = {}
    no_storage_intended: Dict[str, float] = {}
    for movement, spec in specs.items():
        if spec.get("kind") == "on_ramp":
            continue
        available = max(0.0, state.urban_movement_queue.get(movement, 0.0))
        cap_flow = _movement_capacity_flow(control, cfg, movement, spec)
        green_fraction = _phase_green_fraction(control, cfg, spec)
        intended = min(available, sim.T_u_h * green_fraction * cap_flow)
        receiving_link = str(spec.get("receiving_link", ""))
        if receiving_link and receiving_link in state.urban_link_storage:
            intended_by_storage.setdefault(receiving_link, {})[movement] = intended
        else:
            no_storage_intended[movement] = intended

    actual_departure: Dict[str, float] = dict(no_storage_intended)
    for storage_link, intended in intended_by_storage.items():
        available_space = max(0.0, state.urban_link_storage.get(storage_link, 0.0))
        actual_departure.update(_allocate_receiving_counts(
            cfg.urban_follower.receiving_space_rule,
            intended,
            available_space,
        ))

    for movement, departed in actual_departure.items():
        if departed <= 0.0:
            continue
        spec = specs[movement]
        before = state.urban_movement_queue.get(movement, 0.0)
        actual = min(before, departed)
        state.urban_movement_queue[movement] = max(0.0, before - actual)
        receiving_link = str(spec.get("receiving_link", ""))
        if receiving_link in state.urban_link_storage:
            state.urban_link_storage[receiving_link] = max(
                0.0,
                state.urban_link_storage.get(receiving_link, 0.0) - actual,
            )
            delay_steps = _link_delay_steps(state, cfg, receiving_link)
            arrival_step = step_idx + delay_steps
            next_movement = str(spec.get("next_movement", ""))
            if next_movement:
                _schedule(state.urban_arrival_buffer, next_movement, arrival_step, actual)
            _schedule(state.urban_storage_release_buffer, receiving_link, arrival_step, actual)
        if spec.get("kind") == "off_ramp":
            off_ramp = str(spec.get("off_ramp", ""))
            off_ramp_departures[off_ramp] = off_ramp_departures.get(off_ramp, 0.0) + actual
            outbound_service_veh += actual
        elif spec.get("kind") == "boundary_in":
            inbound_service_veh += actual

    for movement, spec in specs.items():
        qmax = _queue_max(cfg, movement, spec)
        q = state.urban_movement_queue.get(movement, 0.0)
        if q > qmax:
            overflow_count += 1.0
            projection_count += q - qmax
            state.urban_movement_queue[movement] = qmax

    urban_ttt = (sum(state.urban_movement_queue.values()) + _storage_occupancy(state, cfg)) * sim.T_u_h

    _sync_legacy_queues(state, cfg)
    inbound = inbound_service_veh / max(sim.T_u_h, 1.0e-9)
    outbound = outbound_service_veh / max(sim.T_u_h, 1.0e-9)
    net_inflow = inbound - outbound
    diagnostics["inbound_service_veh"] = float(inbound_service_veh)
    diagnostics["outbound_service_veh"] = float(outbound_service_veh)
    diagnostics["net_inflow"] = float(net_inflow)
    diagnostics["net_inflow_tracking_error"] = abs(net_inflow - control.N_P_star)
    diagnostics["B_in"] = safe_balance_index(state.boundary_queue[l] for l in net.boundary_in_links)
    diagnostics["B_out"] = safe_balance_index(state.boundary_queue[l] for l in net.boundary_out_links)
    diagnostics.update(boundary_indices(state.boundary_queue.values(), net.boundary_queue_max_veh))
    diagnostics["queue_overflow_count"] = float(overflow_count)
    diagnostics["movement_queue_projection_veh"] = float(projection_count)
    diagnostics["urban_storage_occupancy"] = _storage_occupancy(state, cfg)
    diagnostics["onramp_arrivals_veh"] = float(onramp_arrivals_veh)
    diagnostics["onramp_release_request_veh"] = float(onramp_release_request_veh)
    diagnostics["onramp_releases_veh"] = float(onramp_releases_veh)
    diagnostics["onramp_release_shortfall_veh"] = float(onramp_release_shortfall_veh)
    diagnostics["offramp_departures_veh"] = float(sum(off_ramp_departures.values()))
    for off_ramp, value in off_ramp_departures.items():
        diagnostics[f"offramp_departures_{off_ramp}_veh"] = float(value)
    return float(urban_ttt), diagnostics


def aggregate_urban_diagnostics(
    rows: Iterable[Mapping[str, float]],
    cfg: ExperimentConfig,
    control: ControlAction,
    interval_h: float | None = None,
) -> Dict[str, float]:
    """여러 `urban_substep` diagnostics를 하나의 control/freeway interval 값으로 묶는다."""
    diagnostics_rows = [dict(row) for row in rows]
    if not diagnostics_rows:
        return {
            "movement_queue_model_active": 1.0,
            "urban_storage_active": 1.0,
            "urban_substep_active": 1.0,
            "net_inflow": 0.0,
            "net_inflow_tracking_error": abs(control.N_P_star),
        }

    out = dict(diagnostics_rows[-1])
    sum_keys = {
        "inbound_service_veh",
        "outbound_service_veh",
        "queue_overflow_count",
        "movement_queue_projection_veh",
        "onramp_arrivals_veh",
        "onramp_release_request_veh",
        "onramp_releases_veh",
        "onramp_release_shortfall_veh",
        "offramp_departures_veh",
    }
    for key in set().union(*(row.keys() for row in diagnostics_rows)):
        if key in sum_keys or (key.startswith("offramp_departures_") and key.endswith("_veh")):
            out[key] = float(sum(row.get(key, 0.0) for row in diagnostics_rows))
        elif key in {"movement_queue_model_active", "urban_storage_active", "urban_substep_active"}:
            out[key] = float(max(row.get(key, 0.0) for row in diagnostics_rows))

    horizon_h = cfg.simulation.T_c_h if interval_h is None else interval_h
    inbound = out.get("inbound_service_veh", 0.0) / max(horizon_h, 1.0e-9)
    outbound = out.get("outbound_service_veh", 0.0) / max(horizon_h, 1.0e-9)
    net_inflow = inbound - outbound
    out["net_inflow"] = float(net_inflow)
    out["net_inflow_tracking_error"] = abs(net_inflow - control.N_P_star)
    return out


def urban_step(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
) -> Tuple[float, Dict[str, float]]:
    """기존 API 호환 wrapper: 한 control interval 동안 `urban_substep`을 반복한다."""
    ensure_urban_state(state, cfg)
    total_ttt = 0.0
    diagnostics: list[Dict[str, float]] = []
    start_step = _urban_step_index(state, cfg)
    for substep in range(cfg.simulation.K_cu):
        ur_ttt, ur_diag = urban_substep(
            state,
            control,
            demand,
            cfg,
            urban_step_index=start_step + substep,
        )
        total_ttt += ur_ttt
        diagnostics.append(ur_diag)
    return float(total_ttt), aggregate_urban_diagnostics(diagnostics, cfg, control)
