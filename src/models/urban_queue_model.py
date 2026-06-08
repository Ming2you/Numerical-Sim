from __future__ import annotations

from typing import Dict, Iterable, Tuple

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


def _receiving_scale(rule: str, intended: Dict[str, float], total_space: float) -> Dict[str, float]:
    total = sum(max(v, 0.0) for v in intended.values())
    if total <= total_space or total <= 1.0e-9:
        return {k: max(v, 0.0) for k, v in intended.items()}
    if rule == "equal_split":
        share = total_space / len(intended)
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


def urban_step(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
) -> Tuple[float, Dict[str, float]]:
    """Advance queue dynamics one control interval."""
    net = cfg.network
    dt_h = cfg.simulation.control_interval_h
    diagnostics: Dict[str, float] = {}

    for link in net.movement_links:
        arrival = demand.urban_boundary.get(link, 0.0)
        state.boundary_queue[link] = max(0.0, state.boundary_queue.get(link, 0.0) + arrival * dt_h)
        state.urban_queue[link] = max(0.0, state.urban_queue.get(link, 0.0) + 0.35 * arrival * dt_h)

    default_green = net.effective_green_total / 2.0
    movement_phase = {
        "in_A": "A_p1",
        "in_C": "C_p1",
        "out_D": "D_p1",
        "out_F": "F_p1",
    }
    movement_cap_by_link = {}
    for link in net.movement_links:
        phase = movement_phase.get(link)
        green_sec = control.green_times.get(phase, default_green) if phase else default_green
        movement_cap_by_link[link] = net.movement_capacity_veh_h * max(
            0.15,
            green_sec / max(net.cycle_length, 1.0e-9),
        )
    intended = {
        link: min(
            control.inflow_outflow_allocation.get(link, movement_cap_by_link[link]),
            movement_cap_by_link[link],
            (state.boundary_queue.get(link, 0.0) + state.urban_queue.get(link, 0.0)) / max(dt_h, 1.0e-9),
        )
        for link in net.movement_links
    }
    total_storage = len(net.movement_links) * net.boundary_queue_max_veh
    used_storage = sum(state.boundary_queue.values()) + 0.35 * sum(state.urban_queue.values())
    available_space_flow = max(0.0, total_storage - used_storage) / max(dt_h, 1.0e-9)
    effective = _receiving_scale(cfg.urban_follower.receiving_space_rule, intended, available_space_flow)

    for link, dep_flow in effective.items():
        dep_veh = dep_flow * dt_h
        from_boundary = min(state.boundary_queue.get(link, 0.0), 0.65 * dep_veh)
        state.boundary_queue[link] = max(0.0, state.boundary_queue.get(link, 0.0) - from_boundary)
        remaining = dep_veh - from_boundary
        state.urban_queue[link] = max(0.0, state.urban_queue.get(link, 0.0) - remaining)

    inbound = sum(effective.get(link, 0.0) for link in net.boundary_in_links)
    outbound = sum(effective.get(link, 0.0) for link in net.boundary_out_links)
    net_inflow = inbound - outbound
    diagnostics["net_inflow"] = float(net_inflow)
    diagnostics["net_inflow_tracking_error"] = abs(net_inflow - control.N_P_star)
    diagnostics["B_in"] = safe_balance_index(state.boundary_queue[l] for l in net.boundary_in_links)
    diagnostics["B_out"] = safe_balance_index(state.boundary_queue[l] for l in net.boundary_out_links)
    diagnostics.update(boundary_indices(state.boundary_queue.values(), net.boundary_queue_max_veh))
    diagnostics["queue_overflow_count"] = float(sum(
        1 for q in list(state.boundary_queue.values()) + list(state.urban_queue.values())
        if q > net.boundary_queue_max_veh
    ))
    urban_ttt = (sum(state.boundary_queue.values()) + sum(state.urban_queue.values())) * dt_h
    return float(urban_ttt), diagnostics
