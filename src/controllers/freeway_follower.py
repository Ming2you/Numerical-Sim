from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from src.controllers.leader import LeaderAction
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState


@dataclass
class FreewayFollowerResult:
    ramp_metering: Dict[str, float]
    vsl: Dict[str, float]
    objective_value: float
    infeasibility: Dict[str, float]


class FreewayFollower:
    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg

    def solve(
        self,
        state: TrafficState,
        leader: LeaderAction,
        demand: DemandStep,
        previous_control: Optional[ControlAction] = None,
    ) -> FreewayFollowerResult:
        net = self.cfg.network
        fc = self.cfg.freeway_follower
        caps = np.asarray([net.ramp_capacity_veh_h[r] for r in net.ramps], dtype=float)
        queues = np.asarray([
            state.ramp_queue.get(r, 0.0) + demand.ramp_arrival.get(r, 0.0) * self.cfg.simulation.control_interval_h
            for r in net.ramps
        ], dtype=float)
        weights = queues + 1.0
        weights = weights / max(float(np.sum(weights)), 1.0e-9)
        target = float(np.clip(leader.N_UF_star, 0.0, float(np.sum(caps))))
        raw = weights * target
        release = np.minimum(raw, caps)
        shortfall = target - float(np.sum(release))
        if shortfall > 0.0:
            spare = np.maximum(0.0, caps - release)
            if float(np.sum(spare)) > 1.0e-9:
                release += spare / float(np.sum(spare)) * min(shortfall, float(np.sum(spare)))
        ramp_metering = {r: float(release[i]) for i, r in enumerate(net.ramps)}

        vsl: Dict[str, float] = {}
        prev_vsl = previous_control.vsl if previous_control else {}
        vsl_set = sorted(float(v) for v in fc.vsl_set)
        for link in net.freeway_links:
            rho_mean = float(np.mean(state.freeway_density[link]))
            if rho_mean > 0.98 * net.rho_max:
                desired = 80.0
            else:
                desired = max(vsl_set)
            prev = prev_vsl.get(link, max(vsl_set))
            desired = float(np.clip(desired, prev - fc.max_vsl_step, prev + fc.max_vsl_step))
            feasible = [x for x in vsl_set if abs(x - prev) <= fc.max_vsl_step + 1.0e-9]
            vsl[link] = min(feasible or vsl_set, key=lambda x: abs(x - desired))

        metering_error = abs(sum(ramp_metering.values()) - leader.N_UF_star)
        queue_overflow = sum(max(0.0, q - net.ramp_queue_max_veh) for q in state.ramp_queue.values())
        density_excess = sum(
            max(0.0, rho - net.rho_crit)
            for values in state.freeway_density.values()
            for rho in values
        )
        smooth = 0.0
        if previous_control:
            smooth += sum(abs(ramp_metering[r] - previous_control.ramp_metering.get(r, ramp_metering[r])) for r in net.ramps)
            smooth += sum(abs(vsl[l] - previous_control.vsl.get(l, vsl[l])) for l in net.freeway_links)
        objective = (
            fc.ramp_queue_penalty * queue_overflow
            + fc.density_penalty * density_excess
            + fc.metering_smoothness_weight * smooth
            + 0.01 * metering_error
        )
        return FreewayFollowerResult(
            ramp_metering=ramp_metering,
            vsl=vsl,
            objective_value=float(objective),
            infeasibility={
                "metering_residual": float(max(0.0, metering_error - fc.eps_F)),
                "ramp_queue_overflow": float(queue_overflow),
            },
        )
