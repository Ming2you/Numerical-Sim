from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping

import numpy as np

from src.controllers.leader import LeaderAction
from src.models.state import ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    movement_storage_capacity,
    movement_specs,
    safe_balance_index,
    urban_accumulation_feedback_flow,
)


INFLOW_KINDS = {"boundary_in", "off_ramp"}
OUTFLOW_KINDS = {"boundary_out", "on_ramp"}


@dataclass
class AllocationResult:
    movement_flows: Dict[str, float]
    movement_green_sec: Dict[str, float]
    target_net_inflow_veh_h: float
    projected_net_inflow_veh_h: float
    residual_veh_h: float
    diagnostics: Dict[str, float] = field(default_factory=dict)


class InflowOutflowAllocationModule:
    """논문 §3.2 density-balancing inflow/outflow allocation module.

    이 모듈은 leader의 `N_P_star`를 받아 perimeter 전체 movement의 기준 service flow와
    green setpoint를 한 번 산출한다. Urban agent는 이 결과를 `±eps_g` 범위에서만
    fine-tune한다.
    """

    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg
        self.solve_count = 0

    def solve(self, state: TrafficState, leader: LeaderAction) -> AllocationResult:
        self.solve_count += 1
        specs = movement_specs(self.cfg)
        movements = [
            movement
            for movement, spec in specs.items()
            if spec.get("kind") in INFLOW_KINDS | OUTFLOW_KINDS
        ]
        if not movements:
            return AllocationResult({}, {}, 0.0, 0.0, 0.0, {"allocation_module_active": 1.0})

        target = urban_accumulation_feedback_flow(state, self.cfg, leader.N_P_star)
        lower, upper = self._bounds(movements)
        kinds = [str(specs[m].get("kind", "")) for m in movements]
        target = self._clip_target(target, lower, upper, kinds)
        # 같은 state/leader에서는 호출 순서와 무관하게 같은 allocation plan을 재현한다.
        time_index = int(round(state.time_sec / max(self.cfg.simulation.control_interval, 1.0e-9)))
        seed = int(self.cfg.simulation.random_seed + time_index)
        best = self._run_pso(state, movements, kinds, lower, upper, target, seed)
        best = self._project_net_flow(best, lower, upper, kinds, target)
        flows = {movement: float(best[idx]) for idx, movement in enumerate(movements)}
        green = {
            movement: self._flow_to_green_sec(flows[movement])
            for movement in movements
        }
        in_values = self._densities_after_service(state, movements, kinds, best, INFLOW_KINDS)
        out_values = self._densities_after_service(state, movements, kinds, best, OUTFLOW_KINDS)
        net = self._net_flow(best, kinds)
        residual = abs(net - target)
        diagnostics = {
            "allocation_module_active": 1.0,
            "allocation_pso_calls": float(self.solve_count),
            "allocation_pso_particles": float(self.cfg.urban_follower.allocation_pso_particles),
            "allocation_pso_iterations": float(self.cfg.urban_follower.allocation_pso_iterations),
            "allocation_target_net_inflow_veh_h": float(target),
            "allocation_projected_net_inflow_veh_h": float(net),
            "allocation_net_inflow_residual_veh_h": float(residual),
            "allocation_B_in": safe_balance_index(in_values),
            "allocation_B_out": safe_balance_index(out_values),
            "allocation_inflow_dim": float(len(in_values)),
            "allocation_outflow_dim": float(len(out_values)),
        }
        return AllocationResult(flows, green, float(target), float(net), float(residual), diagnostics)

    def _bounds(self, movements: Iterable[str]) -> tuple[np.ndarray, np.ndarray]:
        net = self.cfg.network
        g_min = float(net.green_min)
        g_max = float(net.green_max)
        saturation = float(net.movement_capacity_veh_h)
        lower = []
        upper = []
        for _movement in movements:
            lower.append(g_min / max(net.cycle_length, 1.0e-9) * saturation)
            upper.append(g_max / max(net.cycle_length, 1.0e-9) * saturation)
        return np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)

    def _clip_target(
        self,
        target: float,
        lower: np.ndarray,
        upper: np.ndarray,
        kinds: list[str],
    ) -> float:
        inflow = np.asarray([kind in INFLOW_KINDS for kind in kinds], dtype=bool)
        outflow = np.asarray([kind in OUTFLOW_KINDS for kind in kinds], dtype=bool)
        min_net = float(np.sum(lower[inflow]) - np.sum(upper[outflow]))
        max_net = float(np.sum(upper[inflow]) - np.sum(lower[outflow]))
        return float(np.clip(target, min_net, max_net))

    def _run_pso(
        self,
        state: TrafficState,
        movements: list[str],
        kinds: list[str],
        lower: np.ndarray,
        upper: np.ndarray,
        target: float,
        seed: int,
    ) -> np.ndarray:
        particles = max(4, int(self.cfg.urban_follower.allocation_pso_particles))
        iterations = max(1, int(self.cfg.urban_follower.allocation_pso_iterations))
        rng = np.random.default_rng(seed)
        span = np.maximum(upper - lower, 1.0e-9)
        pos = lower + rng.random((particles, len(movements))) * span
        vel = rng.normal(0.0, 0.10, size=pos.shape) * span
        personal = pos.copy()
        personal_score = np.asarray([
            self._objective(state, movements, kinds, row, target)
            for row in pos
        ])
        best_idx = int(np.argmin(personal_score))
        global_best = personal[best_idx].copy()
        global_score = float(personal_score[best_idx])

        for _ in range(iterations):
            r1 = rng.random(pos.shape)
            r2 = rng.random(pos.shape)
            vel = 0.55 * vel + 1.45 * r1 * (personal - pos) + 1.45 * r2 * (global_best - pos)
            pos = np.clip(pos + vel, lower, upper)
            scores = np.asarray([
                self._objective(state, movements, kinds, row, target)
                for row in pos
            ])
            improved = scores < personal_score
            personal[improved] = pos[improved]
            personal_score[improved] = scores[improved]
            best_idx = int(np.argmin(personal_score))
            if float(personal_score[best_idx]) < global_score:
                global_score = float(personal_score[best_idx])
                global_best = personal[best_idx].copy()
        return global_best

    def _objective(
        self,
        state: TrafficState,
        movements: list[str],
        kinds: list[str],
        flows: np.ndarray,
        target: float,
    ) -> float:
        inflow_density = self._densities_after_service(state, movements, kinds, flows, INFLOW_KINDS)
        outflow_density = self._densities_after_service(state, movements, kinds, flows, OUTFLOW_KINDS)
        balance = safe_balance_index(inflow_density) ** 2 + safe_balance_index(outflow_density) ** 2
        residual = self._net_flow(flows, kinds) - target
        return float(balance + 10.0 * (residual / max(self.cfg.network.movement_capacity_veh_h, 1.0)) ** 2)

    def _densities_after_service(
        self,
        state: TrafficState,
        movements: list[str],
        kinds: list[str],
        flows: np.ndarray,
        accepted_kinds: set[str],
    ) -> list[float]:
        out: list[float] = []
        dt_h = self.cfg.simulation.T_c_h
        for idx, movement in enumerate(movements):
            if kinds[idx] not in accepted_kinds:
                continue
            queue = max(0.0, state.urban_movement_queue.get(movement, 0.0))
            remaining = max(0.0, queue - max(0.0, flows[idx]) * dt_h)
            out.append(remaining / max(self._movement_storage_capacity(movement), 1.0e-9))
        return out

    def _movement_storage_capacity(self, movement: str) -> float:
        return movement_storage_capacity(self.cfg, movement)

    @staticmethod
    def _net_flow(flows: np.ndarray, kinds: list[str]) -> float:
        net = 0.0
        for idx, kind in enumerate(kinds):
            if kind in INFLOW_KINDS:
                net += float(flows[idx])
            elif kind in OUTFLOW_KINDS:
                net -= float(flows[idx])
        return float(net)

    def _project_net_flow(
        self,
        flows: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        kinds: list[str],
        target: float,
    ) -> np.ndarray:
        out = np.clip(flows.astype(float), lower, upper)
        for _ in range(2 * len(out) + 1):
            residual = target - self._net_flow(out, kinds)
            if abs(residual) <= max(self.cfg.urban_follower.eps_U, 1.0e-9):
                break
            if residual > 0.0:
                candidates = [i for i, kind in enumerate(kinds) if kind in INFLOW_KINDS and out[i] < upper[i] - 1.0e-9]
                candidates += [i for i, kind in enumerate(kinds) if kind in OUTFLOW_KINDS and out[i] > lower[i] + 1.0e-9]
                sign = 1.0
            else:
                candidates = [i for i, kind in enumerate(kinds) if kind in INFLOW_KINDS and out[i] > lower[i] + 1.0e-9]
                candidates += [i for i, kind in enumerate(kinds) if kind in OUTFLOW_KINDS and out[i] < upper[i] - 1.0e-9]
                sign = -1.0
            if not candidates:
                break
            share = abs(residual) / len(candidates)
            for idx in candidates:
                if kinds[idx] in INFLOW_KINDS:
                    delta = sign * min(share, upper[idx] - out[idx] if sign > 0.0 else out[idx] - lower[idx])
                    out[idx] += delta
                else:
                    delta = -sign * min(share, out[idx] - lower[idx] if sign > 0.0 else upper[idx] - out[idx])
                    out[idx] += delta
        return np.clip(out, lower, upper)

    def _flow_to_green_sec(self, flow: float) -> float:
        net = self.cfg.network
        raw = max(0.0, flow) / max(net.movement_capacity_veh_h, 1.0e-9) * net.cycle_length
        return float(np.clip(raw, net.green_min, net.green_max))
