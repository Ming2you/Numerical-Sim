from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from src.controllers.leader import LeaderAction
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import boundary_indices, safe_balance_index


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

    def _green_times(self, state: TrafficState, previous: Optional[ControlAction]) -> Dict[str, float]:
        net = self.cfg.network
        green: Dict[str, float] = {}
        total = net.effective_green_total
        for signal in net.signals:
            if signal in ("A", "C"):
                p1_queue = sum(state.boundary_queue.get(k, 0.0) for k in net.boundary_in_links)
                p2_queue = sum(state.boundary_queue.get(k, 0.0) for k in net.boundary_out_links)
            else:
                p1_queue = sum(state.boundary_queue.get(k, 0.0) for k in net.boundary_out_links)
                p2_queue = sum(state.boundary_queue.get(k, 0.0) for k in net.boundary_in_links)
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

    def _allocation(self, state: TrafficState, leader: LeaderAction) -> tuple[Dict[str, float], float]:
        net = self.cfg.network
        caps = {link: net.movement_capacity_veh_h for link in net.movement_links}
        in_cap = sum(caps[l] for l in net.boundary_in_links)
        out_cap = sum(caps[l] for l in net.boundary_out_links)
        total_service = 0.62 * (in_cap + out_cap)
        desired_in = np.clip((total_service + leader.N_P_star) / 2.0, 0.0, in_cap)
        desired_out = np.clip(desired_in - leader.N_P_star, 0.0, out_cap)
        if abs((desired_in - desired_out) - leader.N_P_star) > self.cfg.urban_follower.eps_U:
            desired_out = np.clip(desired_in - leader.N_P_star, 0.0, out_cap)
            desired_in = np.clip(desired_out + leader.N_P_star, 0.0, in_cap)

        alloc: Dict[str, float] = {}
        for group, total in ((net.boundary_in_links, desired_in), (net.boundary_out_links, desired_out)):
            q = np.asarray([state.boundary_queue.get(link, 0.0) + 1.0 for link in group], dtype=float)
            w = q / max(float(np.sum(q)), 1.0e-9)
            for idx, link in enumerate(group):
                alloc[link] = float(min(caps[link], total * w[idx]))
        residual = abs(sum(alloc[l] for l in net.boundary_in_links) - sum(alloc[l] for l in net.boundary_out_links) - leader.N_P_star)
        return alloc, float(residual)

    def solve(
        self,
        state: TrafficState,
        leader: LeaderAction,
        demand: DemandStep,
        freeway_response: object | None = None,
        previous_control: Optional[ControlAction] = None,
    ) -> UrbanFollowerResult:
        green = self._green_times(state, previous_control)
        offsets = self._offsets(state, previous_control)
        allocation, residual = self._allocation(state, leader)
        b_in = safe_balance_index(state.boundary_queue.get(l, 0.0) for l in self.cfg.network.boundary_in_links)
        b_out = safe_balance_index(state.boundary_queue.get(l, 0.0) for l in self.cfg.network.boundary_out_links)
        metrics = {"B_in": b_in, "B_out": b_out}
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
