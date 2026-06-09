from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from src.controllers.leader import LeaderAction
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import boundary_indices, ensure_urban_state, movement_specs, safe_balance_index


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
    ) -> Dict[str, float]:
        net = self.cfg.network
        specs = movement_specs(self.cfg)
        pressure = self._freeway_pressure(freeway_response)
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
            has_onramp_phase = any(
                spec.get("phase") == f"{signal}_p2" and spec.get("kind") == "on_ramp"
                for spec in specs.values()
            )
            if has_onramp_phase:
                # ramp 병목 압력이 높으면 on-ramp 대기열을 green split 산정에서 더 크게 본다.
                p2_queue += pressure["total_pressure"] * net.ramp_queue_max_veh
            ratio = p1_queue / max(p1_queue + p2_queue, 1.0e-9) if p1_queue + p2_queue > 0 else 0.5
            p1 = float(np.clip(total * ratio, net.green_min, net.green_max))
            p2 = total - p1
            if p2 < net.green_min:
                p2 = net.green_min
                p1 = total - p2
            if p2 > net.green_max:
                p2 = net.green_max
                p1 = total - p2
            green[f"{signal}_p1"] = float(p1)
            green[f"{signal}_p2"] = float(p2)
        return green

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
    ) -> tuple[Dict[str, float], float]:
        net = self.cfg.network
        specs = movement_specs(self.cfg)
        pressure = self._freeway_pressure(freeway_response)
        inbound_movements = [
            movement for movement, spec in specs.items()
            if spec.get("kind") == "boundary_in"
        ]
        outbound_movements = [
            movement for movement, spec in specs.items()
            if spec.get("kind") == "off_ramp"
        ]
        in_cap = len(inbound_movements) * net.movement_capacity_veh_h
        out_cap = len(outbound_movements) * net.movement_capacity_veh_h
        total_service = 0.62 * (in_cap + out_cap)
        desired_in = np.clip((total_service + leader.N_P_star) / 2.0, 0.0, in_cap)
        desired_out = np.clip(desired_in - leader.N_P_star, 0.0, out_cap)
        if pressure["used"] > 0.0 and outbound_movements:
            # freeway가 막히면 off-ramp storage를 더 빨리 비우도록 outbound service 목표를 살짝 올린다.
            desired_out = np.clip(
                desired_out + pressure["total_pressure"] * 0.08 * out_cap,
                0.0,
                out_cap,
            )
            desired_in = np.clip(desired_out + leader.N_P_star, 0.0, in_cap)
        if abs((desired_in - desired_out) - leader.N_P_star) > self.cfg.urban_follower.eps_U:
            desired_out = np.clip(desired_in - leader.N_P_star, 0.0, out_cap)
            desired_in = np.clip(desired_out + leader.N_P_star, 0.0, in_cap)

        alloc: Dict[str, float] = {}
        for group, total in ((inbound_movements, desired_in), (outbound_movements, desired_out)):
            if not group:
                continue
            q = np.asarray([state.urban_movement_queue.get(movement, 0.0) + 1.0 for movement in group], dtype=float)
            if group is outbound_movements:
                q = q * (1.0 + pressure["total_pressure"])
            w = q / max(float(np.sum(q)), 1.0e-9)
            for idx, movement in enumerate(group):
                alloc[movement] = float(min(net.movement_capacity_veh_h, total * w[idx]))

        for link in net.boundary_in_links:
            related = [
                movement for movement, spec in specs.items()
                if spec.get("origin") == link and spec.get("kind") == "boundary_in"
            ]
            alloc[link] = float(sum(alloc.get(movement, 0.0) for movement in related))
        for link in net.boundary_out_links:
            related = [
                movement for movement, spec in specs.items()
                if spec.get("destination") == link and spec.get("kind") == "off_ramp"
            ]
            alloc[link] = float(sum(alloc.get(movement, 0.0) for movement in related))

        residual = abs(
            sum(alloc.get(m, 0.0) for m in inbound_movements)
            - sum(alloc.get(m, 0.0) for m in outbound_movements)
            - leader.N_P_star
        )
        return alloc, float(residual)

    def solve(
        self,
        state: TrafficState,
        leader: LeaderAction,
        demand: DemandStep,
        freeway_response: object | None = None,
        previous_control: Optional[ControlAction] = None,
    ) -> UrbanFollowerResult:
        ensure_urban_state(state, self.cfg)
        pressure = self._freeway_pressure(freeway_response)
        green = self._green_times(state, previous_control, freeway_response)
        offsets = self._offsets(state, previous_control)
        allocation, residual = self._allocation(state, leader, freeway_response)
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
        }
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
