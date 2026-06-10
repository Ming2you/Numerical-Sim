from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional

import numpy as np

from src.controllers.inflow_outflow_allocation import (
    AllocationResult,
    INFLOW_KINDS,
    OUTFLOW_KINDS,
    InflowOutflowAllocationModule,
)
from src.controllers.leader import LeaderAction
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    boundary_indices,
    ensure_urban_state,
    movement_specs,
    safe_balance_index,
)


@dataclass
class UrbanFollowerResult:
    green_times: Dict[str, float]
    offsets: Dict[str, float]
    inflow_outflow_allocation: Dict[str, float]
    objective_value: float
    infeasibility: Dict[str, float]
    metrics: Dict[str, float]


class UrbanFollower:
    """Two-stage urban follower.

    Stage 1 allocates inflow/outflow service and green splits to track
    `N_P_star` while balancing boundary queues. Stage 2 computes bounded signal
    offsets from current speed/queue-derived travel-time estimates.
    """

    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg
        self.allocation_module = InflowOutflowAllocationModule(cfg)

    def _freeway_pressure(self, freeway_response: object | None) -> Dict[str, float]:
        """Freeway follower 결과를 urban 신호/배분이 사용할 압력 지표로 바꾼다."""
        if freeway_response is None:
            return {
                "used": 0.0,
                "metering_pressure": 0.0,
                "queue_pressure": 0.0,
                "density_pressure": 0.0,
                "receiving_pressure": 0.0,
                "total_pressure": 0.0,
            }
        infeasibility = getattr(freeway_response, "infeasibility", {}) or {}
        metering_residual = float(infeasibility.get(
            "metering_tracking_residual",
            infeasibility.get("metering_residual", 0.0),
        ))
        step_capacity = float(infeasibility.get("ramp_projection_first_step_capacity", 0.0))
        queue_overflow = float(infeasibility.get("ramp_queue_overflow", 0.0))
        density_excess = float(infeasibility.get("density_excess", 0.0))
        receiving_factor = float(infeasibility.get("min_ramp_receiving_factor", 1.0))
        metering_pressure = metering_residual / max(step_capacity, self.cfg.network.freeway_capacity_veh_h, 1.0e-9)
        queue_pressure = queue_overflow / max(self.cfg.network.ramp_queue_max_veh, 1.0e-9)
        density_pressure = density_excess / max(
            self.cfg.network.rho_crit * len(self.cfg.network.freeway_links),
            1.0e-9,
        )
        receiving_pressure = max(0.0, 1.0 - receiving_factor)
        total_pressure = float(np.clip(
            metering_pressure + queue_pressure + density_pressure + receiving_pressure,
            0.0,
            1.0,
        ))
        return {
            "used": 1.0,
            "metering_pressure": float(metering_pressure),
            "queue_pressure": float(queue_pressure),
            "density_pressure": float(density_pressure),
            "receiving_pressure": float(receiving_pressure),
            "total_pressure": total_pressure,
        }

    def _green_times(
        self,
        state: TrafficState,
        previous: Optional[ControlAction],
        freeway_response: object | None = None,
        allocation_plan: Optional[AllocationResult] = None,
    ) -> Dict[str, float]:
        net = self.cfg.network
        specs = movement_specs(self.cfg)
        pressure = self._freeway_pressure(freeway_response)
        phase_setpoints = self._allocation_phase_setpoints(allocation_plan)
        green: Dict[str, float] = {}
        total = net.effective_green_total
        for signal in net.signals:
            p1_queue = sum(
                state.urban_movement_queue.get(movement, 0.0)
                for movement, spec in specs.items()
                if spec.get("phase") == f"{signal}_p1"
            )
            p2_queue = sum(
                state.urban_movement_queue.get(movement, 0.0)
                for movement, spec in specs.items()
                if spec.get("phase") == f"{signal}_p2"
            )
            has_offramp_discharge_phase = any(
                spec.get("phase") == f"{signal}_p1" and spec.get("kind") == "off_ramp"
                for spec in specs.values()
            )
            if has_offramp_discharge_phase:
                # freeway 압력이 높으면 off-ramp storage를 비우는 도시 유입 phase를 우선한다.
                p1_queue += pressure["total_pressure"] * net.ramp_queue_max_veh
            ratio = p1_queue / max(p1_queue + p2_queue, 1.0e-9) if p1_queue + p2_queue > 0 else 0.5
            p1 = float(np.clip(total * ratio, net.green_min, net.green_max))
            p2 = total - p1
            if has_offramp_discharge_phase:
                # off-ramp 방출 phase가 최소 green에 묶이면 urban net outflow가 구조적으로 부족해진다.
                p1_floor = max(net.green_min, 0.35 * total)
                if p1 < p1_floor:
                    p1 = p1_floor
                    p2 = total - p1
            if p2 < net.green_min:
                p2 = net.green_min
                p1 = total - p2
            if p2 > net.green_max:
                p2 = net.green_max
                p1 = total - p2
            if allocation_plan is not None:
                p1, p2 = self._clamp_green_to_allocation_band(signal, p1, p2, phase_setpoints)
            green[f"{signal}_p1"] = float(p1)
            green[f"{signal}_p2"] = float(p2)
        return green

    def _allocation_phase_setpoints(
        self,
        allocation_plan: Optional[AllocationResult],
    ) -> Dict[str, float]:
        if allocation_plan is None:
            return {}
        specs = movement_specs(self.cfg)
        by_phase: Dict[str, list[float]] = {}
        for movement, green_sec in allocation_plan.movement_green_sec.items():
            phase = str(specs.get(movement, {}).get("phase", ""))
            if phase:
                by_phase.setdefault(phase, []).append(float(green_sec))
        return {
            phase: float(np.mean(values))
            for phase, values in by_phase.items()
            if values
        }

    def _clamp_green_to_allocation_band(
        self,
        signal: str,
        p1: float,
        p2: float,
        phase_setpoints: Mapping[str, float],
    ) -> tuple[float, float]:
        net = self.cfg.network
        total = net.effective_green_total
        band = max(0.0, float(self.cfg.urban_follower.allocation_green_band_sec))
        p1_key = f"{signal}_p1"
        p2_key = f"{signal}_p2"
        p1_target = phase_setpoints.get(p1_key, p1)
        p2_target = phase_setpoints.get(p2_key, p2)
        low = max(net.green_min, p1_target - band, total - (p2_target + band))
        high = min(net.green_max, p1_target + band, total - (p2_target - band))
        if low > high:
            low, high = net.green_min, net.green_max
        p1_new = float(np.clip(p1, low, high))
        p2_new = total - p1_new
        if p2_new < net.green_min:
            p2_new = net.green_min
            p1_new = total - p2_new
        if p2_new > net.green_max:
            p2_new = net.green_max
            p1_new = total - p2_new
        return float(p1_new), float(p2_new)

    def _offsets(self, state: TrafficState, previous: Optional[ControlAction]) -> Dict[str, float]:
        net = self.cfg.network
        uc = self.cfg.urban_follower
        offsets: Dict[str, float] = {}
        avg_speed = np.mean([v for values in state.freeway_speed.values() for v in values])
        travel_time = 1000.0 / max(avg_speed / 3.6, 1.0)
        for idx, signal in enumerate(net.signals):
            desired = (idx * travel_time) % net.cycle_length
            prev = previous.offsets.get(signal, 0.0) if previous else 0.0
            bounded = float(np.clip(desired, prev - uc.max_offset_step, prev + uc.max_offset_step))
            offsets[signal] = bounded % net.cycle_length
        return offsets

    def _allocation(
        self,
        state: TrafficState,
        leader: LeaderAction,
        freeway_response: object | None = None,
        green_times: Optional[Dict[str, float]] = None,
        allocation_plan: Optional[AllocationResult] = None,
    ) -> tuple[Dict[str, float], float, float, Dict[str, float]]:
        net = self.cfg.network
        specs = movement_specs(self.cfg)
        plan = allocation_plan or self.allocation_module.solve(state, leader)
        alloc: Dict[str, float] = {}
        default_green = net.effective_green_total / 2.0
        for movement, target_flow in plan.movement_flows.items():
            spec = specs.get(movement, {})
            phase = str(spec.get("phase", ""))
            green_sec = green_times.get(phase, default_green) if green_times else default_green
            green_fraction = float(np.clip(green_sec / max(net.cycle_length, 1.0e-9), 1.0e-6, 1.0))
            alloc[movement] = float(np.clip(
                max(0.0, target_flow) / green_fraction,
                0.0,
                net.movement_capacity_veh_h,
            ))

        for link in net.boundary_in_links:
            related = [
                movement for movement, spec in specs.items()
                if spec.get("origin") == link and spec.get("kind") == "boundary_in"
            ]
            alloc[link] = float(sum(alloc.get(movement, 0.0) for movement in related))
        for link in net.boundary_out_links:
            related = [
                movement for movement, spec in specs.items()
                if spec.get("destination") == link and spec.get("kind") == "boundary_out"
            ]
            alloc[link] = float(sum(alloc.get(movement, 0.0) for movement in related))

        inflow = sum(
            plan.movement_flows.get(movement, 0.0)
            for movement, spec in specs.items()
            if spec.get("kind") in INFLOW_KINDS
        )
        outflow = sum(
            plan.movement_flows.get(movement, 0.0)
            for movement, spec in specs.items()
            if spec.get("kind") in OUTFLOW_KINDS
        )
        residual = abs(inflow - outflow - plan.target_net_inflow_veh_h)
        return alloc, float(residual), float(plan.target_net_inflow_veh_h), dict(plan.diagnostics)

    def solve(
        self,
        state: TrafficState,
        leader: LeaderAction,
        demand: DemandStep,
        freeway_response: object | None = None,
        previous_control: Optional[ControlAction] = None,
        allocation_plan: Optional[AllocationResult] = None,
    ) -> UrbanFollowerResult:
        ensure_urban_state(state, self.cfg)
        pressure = self._freeway_pressure(freeway_response)
        plan = allocation_plan or self.allocation_module.solve(state, leader)
        green = self._green_times(state, previous_control, freeway_response, plan)
        offsets = self._offsets(state, previous_control)
        allocation, residual, target_net_inflow, allocation_metrics = self._allocation(
            state,
            leader,
            freeway_response,
            green,
            plan,
        )
        b_in = safe_balance_index(state.boundary_queue.get(l, 0.0) for l in self.cfg.network.boundary_in_links)
        b_out = safe_balance_index(state.boundary_queue.get(l, 0.0) for l in self.cfg.network.boundary_out_links)
        metrics = {
            "B_in": b_in,
            "B_out": b_out,
            "freeway_response_used": pressure["used"],
            "freeway_metering_pressure": pressure["metering_pressure"],
            "freeway_queue_pressure": pressure["queue_pressure"],
            "freeway_density_pressure": pressure["density_pressure"],
            "freeway_receiving_pressure": pressure["receiving_pressure"],
            "freeway_total_pressure": pressure["total_pressure"],
            "urban_accumulation_veh": float(state.total_urban_vehicles()),
            "urban_accumulation_target_veh": float(leader.N_P_star),
            "urban_accumulation_error_veh": float(state.total_urban_vehicles() - leader.N_P_star),
            "urban_net_inflow_target_veh_h": float(target_net_inflow),
        }
        metrics.update(allocation_metrics)
        metrics.update(boundary_indices(state.boundary_queue.values(), self.cfg.network.boundary_queue_max_veh))
        smooth = 0.0
        if previous_control:
            smooth += sum(abs(green[k] - previous_control.green_times.get(k, green[k])) for k in green)
            smooth += sum(abs(offsets[k] - previous_control.offsets.get(k, offsets[k])) for k in offsets)
        objective = (
            self.cfg.urban_follower.boundary_balance_weight * (b_in * b_in + b_out * b_out)
            + self.cfg.urban_follower.green_smoothness_weight * smooth
            + residual
        )
        return UrbanFollowerResult(
            green_times=green,
            offsets=offsets,
            inflow_outflow_allocation=allocation,
            objective_value=float(objective),
            infeasibility={"net_inflow_residual": max(0.0, residual - self.cfg.urban_follower.eps_U)},
            metrics=metrics,
        )
