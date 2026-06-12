from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional

import numpy as np

from src.controllers.freeway_follower import FreewayFollowerResult
from src.controllers.inflow_outflow_allocation import AllocationResult
from src.controllers.leader import LeaderAction
from src.controllers.nash_solver import NashResult, _relax_map
from src.controllers.urban_follower import UrbanFollower
from src.models.demand import DemandStep
from src.models.metanet import effective_lane_profile
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    ensure_urban_state,
    estimate_onramp_green_release_flows,
    movement_specs,
)


@dataclass(frozen=True)
class AgentSpec:
    id: str
    kind: str
    signal: str = ""
    link: str = ""
    movements: tuple[str, ...] = ()
    ramps: tuple[str, ...] = ()
    off_ramps: tuple[str, ...] = ()
    neighbors: tuple[str, ...] = ()
    segment_index: int = -1


@dataclass
class AgentSolve:
    agent_id: str
    objective: float
    ramp_metering: Dict[str, float] = field(default_factory=dict)
    vsl: Dict[str, float] = field(default_factory=dict)
    green_times: Dict[str, float] = field(default_factory=dict)
    offsets: Dict[str, float] = field(default_factory=dict)
    allocation: Dict[str, float] = field(default_factory=dict)
    infeasibility: Dict[str, float] = field(default_factory=dict)
    diagnostics: Dict[str, float] = field(default_factory=dict)


def _freeway_agent_id(link: str, segment_index: int | None = None) -> str:
    suffix = link.split("_")[-1] if "_" in link else link
    if segment_index is None:
        return f"F_{suffix}"
    return f"F_{suffix}{segment_index}"


def _urban_agent_id(signal: str) -> str:
    return f"U_{signal}"


def _urban_signal_for_movement(spec: Mapping[str, object], signals: Iterable[str]) -> str:
    signal_set = set(signals)
    phase = str(spec.get("phase", ""))
    if "_" in phase:
        owner = phase.split("_", 1)[0]
        if owner in signal_set:
            return owner
    signal = str(spec.get("signal", ""))
    return signal if signal in signal_set else ""


def _configured_segment_index(mapping: object, key: str, fallback: int, n_segments: int) -> int:
    if isinstance(mapping, Mapping) and key in mapping:
        return int(np.clip(float(mapping[key]), 0.0, float(n_segments - 1)))
    return int(np.clip(float(fallback), 0.0, float(n_segments - 1)))


def build_agent_specs(cfg: ExperimentConfig) -> tuple[list[AgentSpec], list[AgentSpec]]:
    """현재 topology에서 Wu식 urban/freeway agent 분할을 자동 유도한다."""
    net = cfg.network
    specs = movement_specs(cfg)
    movement_owner = {
        movement: _urban_signal_for_movement(spec, net.signals)
        for movement, spec in specs.items()
    }
    urban_agents: list[AgentSpec] = []
    for signal in net.signals:
        movements = tuple(
            movement
            for movement, spec in specs.items()
            if movement_owner.get(movement) == signal
        )
        ramps = tuple(
            ramp for ramp, ramp_movements in net.on_ramp_to_movement.items()
            if any(movement in movements for movement in ramp_movements)
        )
        off_ramps = tuple(
            off_ramp for off_ramp, ramp_movements in net.off_ramp_to_movement.items()
            if any(movement in movements for movement in ramp_movements)
        )
        neighbors = sorted({
            _freeway_agent_id(
                net.ramp_to_freeway[ramp],
                _configured_segment_index(
                    getattr(net, "ramp_merge_segment_index", {}),
                    ramp,
                    net.freeway_segments_per_link // 2,
                    net.freeway_segments_per_link,
                ),
            )
            for ramp in ramps
        } | {
            _freeway_agent_id(
                net.off_ramp_from_freeway[off_ramp],
                _configured_segment_index(
                    getattr(net, "off_ramp_segment_index", {}),
                    off_ramp,
                    net.freeway_segments_per_link - 1,
                    net.freeway_segments_per_link,
                ),
            )
            for off_ramp in off_ramps
        })
        urban_agents.append(AgentSpec(
            id=_urban_agent_id(signal),
            kind="urban",
            signal=signal,
            movements=movements,
            ramps=ramps,
            off_ramps=off_ramps,
            neighbors=tuple(neighbors),
        ))

    urban_by_ramp = {
        ramp: _urban_agent_id(movement_owner[ramp_movements[0]])
        for ramp, ramp_movements in net.on_ramp_to_movement.items()
        if ramp_movements and ramp_movements[0] in specs and movement_owner.get(ramp_movements[0])
    }
    urban_by_offramp = {
        off_ramp: _urban_agent_id(movement_owner[ramp_movements[0]])
        for off_ramp, ramp_movements in net.off_ramp_to_movement.items()
        if ramp_movements and ramp_movements[0] in specs and movement_owner.get(ramp_movements[0])
    }
    freeway_agents: list[AgentSpec] = []
    for link in net.freeway_links:
        for segment_index in range(net.freeway_segments_per_link):
            ramps = tuple(
                ramp for ramp in net.ramps
                if net.ramp_to_freeway.get(ramp) == link
                and _configured_segment_index(
                    getattr(net, "ramp_merge_segment_index", {}),
                    ramp,
                    net.freeway_segments_per_link // 2,
                    net.freeway_segments_per_link,
                ) == segment_index
            )
            off_ramps = tuple(
                off_ramp
                for off_ramp in net.off_ramps
                if net.off_ramp_from_freeway.get(off_ramp) == link
                and _configured_segment_index(
                    getattr(net, "off_ramp_segment_index", {}),
                    off_ramp,
                    net.freeway_segments_per_link - 1,
                    net.freeway_segments_per_link,
                ) == segment_index
            )
            neighbors = sorted({
                urban_by_ramp[ramp]
                for ramp in ramps
                if ramp in urban_by_ramp
            } | {
                urban_by_offramp[off_ramp]
                for off_ramp in off_ramps
                if off_ramp in urban_by_offramp
            })
            freeway_agents.append(AgentSpec(
                id=_freeway_agent_id(link, segment_index),
                kind="freeway",
                link=link,
                ramps=ramps,
                off_ramps=off_ramps,
                neighbors=tuple(neighbors),
                segment_index=segment_index,
            ))
    return urban_agents, freeway_agents


def _project_to_target(target: float, upper: Mapping[str, float], weights: Mapping[str, float]) -> Dict[str, float]:
    release = {key: 0.0 for key in upper}
    remaining = float(np.clip(target, 0.0, sum(max(v, 0.0) for v in upper.values())))
    active = {key for key, value in upper.items() if value > 1.0e-9}
    while remaining > 1.0e-9 and active:
        w_sum = sum(max(weights.get(key, 1.0), 1.0e-9) for key in active)
        if w_sum <= 1.0e-9:
            break
        changed = False
        for key in list(active):
            proposed = remaining * max(weights.get(key, 1.0), 1.0e-9) / w_sum
            spare = max(0.0, upper[key] - release[key])
            if proposed >= spare - 1.0e-9:
                release[key] += spare
                remaining -= spare
                active.remove(key)
                changed = True
        if not changed:
            for key in active:
                release[key] += remaining * max(weights.get(key, 1.0), 1.0e-9) / w_sum
            remaining = 0.0
    return {key: float(min(max(value, 0.0), upper[key])) for key, value in release.items()}


class DistributedCoordinator:
    """Wu §IV-D 형태의 agent별 follower coordinator.

    이 1차 구현은 기존 follower 휴리스틱을 재사용하되, 적용 변수는 agent 소유 변수로
    제한하고 coupling variable 변화량으로 반복 종료를 판단한다.
    """

    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg
        self.urban_agents, self.freeway_agents = build_agent_specs(cfg)
        self.urban_follower = UrbanFollower(cfg)

    def solve(
        self,
        state: TrafficState,
        leader: Optional[LeaderAction],
        demand: DemandStep | Iterable[DemandStep],
        previous_control: Optional[ControlAction] = None,
    ) -> NashResult:
        """leader=None이면 PROPOSED-FOLLOWERS-ONLY(spec 16.7) — 숨은 전역 목표 없이
        allocation은 균형/관측 큐로, freeway agent는 local objective로 결정한다."""
        forecast = [demand] if isinstance(demand, DemandStep) else list(demand)
        if not forecast:
            raise ValueError("DistributedCoordinator requires at least one demand step.")
        first_demand = forecast[0]
        reference_control = previous_control or ControlAction.fixed(self.cfg)
        current = reference_control
        current.N_P_star = leader.N_P_star if leader is not None else 0.0
        current.N_UF_star = leader.N_UF_star if leader is not None else 0.0
        allocation_plan = self.urban_follower.allocation_module.solve(state, leader)
        coupling = self._extract_coupling(state, current, first_demand)
        best_control = current
        best_obj = np.inf
        best_diag: Dict[str, float] = {}
        residual = np.inf
        converged = False
        iteration = 0

        for iteration in range(1, self.cfg.mpc.max_nash_iter + 1):
            freeway_solves = [
                self._solve_freeway_agent(agent, state, leader, first_demand, current, coupling)
                for agent in self.freeway_agents
            ]
            freeway_response = self._freeway_response(freeway_solves)
            urban_solves = [
                self._solve_urban_agent(agent, state, leader, first_demand, freeway_response, current, allocation_plan)
                for agent in self.urban_agents
            ]
            candidate = self._merge_agent_controls(
                leader,
                current,
                freeway_solves,
                urban_solves,
            )
            candidate.offsets = self._clamp_offsets_to_reference(candidate.offsets, reference_control)
            candidate.vsl = self._clamp_vsl_to_reference(candidate.vsl, reference_control)
            new_coupling = self._extract_coupling(state, candidate, first_demand)
            residual = self._coupling_residual(coupling, new_coupling)
            obj = sum(s.objective for s in freeway_solves) + sum(s.objective for s in urban_solves)
            diagnostics = self._diagnostics(freeway_solves, urban_solves, residual, iteration)
            if obj < best_obj:
                best_obj = float(obj)
                best_control = candidate
                best_diag = diagnostics
            current = candidate
            coupling = new_coupling
            if residual < self.cfg.mpc.distributed_coupling_tol:
                converged = True
                best_control = candidate
                best_obj = float(obj)
                best_diag = diagnostics
                break

        best_control.diagnostics.update(best_diag)
        best_control.diagnostics["nash_converged"] = converged
        best_control.diagnostics["nash_iterations"] = iteration
        return NashResult(
            control=best_control,
            objective_value=float(best_obj if np.isfinite(best_obj) else 0.0),
            iterations=iteration,
            converged=converged,
            residual_objective=float(residual if np.isfinite(residual) else 0.0),
            residual_control=float(residual if np.isfinite(residual) else 0.0),
            diagnostics=best_diag,
        )

    def _solve_freeway_agent(
        self,
        agent: AgentSpec,
        state: TrafficState,
        leader: Optional[LeaderAction],
        demand: DemandStep,
        current: ControlAction,
        coupling: Mapping[str, float],
    ) -> AgentSolve:
        net = self.cfg.network
        dt_h = self.cfg.simulation.T_f_h
        link_capacity = sum(net.ramp_capacity_veh_h[ramp] for ramp in agent.ramps)
        total_capacity = max(sum(net.ramp_capacity_veh_h.values()), 1.0e-9)
        upper: Dict[str, float] = {}
        weights: Dict[str, float] = {}
        min_receiving = 1.0
        for ramp in agent.ramps:
            merge_idx = agent.segment_index if agent.segment_index >= 0 else len(state.freeway_density[agent.link]) // 2
            rho_merge = state.freeway_density[agent.link][merge_idx]
            receiving = float(np.clip(
                (net.rho_max - rho_merge) / max(net.rho_max - net.rho_crit, 1.0e-9),
                0.0,
                1.0,
            ))
            min_receiving = min(min_receiving, receiving)
            urban_release = max(0.0, coupling.get(f"u_on_{ramp}", 0.0))
            available = state.ramp_queue.get(ramp, 0.0) / max(dt_h, 1.0e-9) + urban_release
            upper[ramp] = min(net.ramp_capacity_veh_h[ramp], available, net.freeway_capacity_veh_h * receiving)
            weights[ramp] = state.ramp_queue.get(ramp, 0.0) + urban_release * self.cfg.simulation.T_c_h + 1.0
        if leader is not None:
            target = max(0.0, leader.N_UF_star) * link_capacity / total_capacity
        else:
            # leaderless(spec 16.7): 전역 N_UF 목표 없이 agent가 local objective로 방출
            # 수준을 고른다 — 후보 분율을 1-구획 merge 밀도 예측으로 평가해 최소 비용 선택.
            target = self._leaderless_metering_target(agent, state, upper)
        ramp_metering = _project_to_target(target, upper, weights)
        lane_profile, lane_diag = effective_lane_profile(state, self.cfg)
        all_rhos = state.freeway_density.get(agent.link, [])
        rhos = [all_rhos[agent.segment_index]] if 0 <= agent.segment_index < len(all_rhos) else all_rhos
        max_density = max(rhos) if rhos else 0.0
        density_ratio = max_density / max(net.rho_crit, 1.0e-9)
        lane_loss = max(0.0, net.freeway_lanes - (lane_profile.get(agent.link, [net.freeway_lanes])[-1]))
        desired = self._agent_vsl(density_ratio, lane_loss, current.vsl.get(agent.link, max(self.cfg.freeway_follower.vsl_set)))
        density_excess = sum(max(0.0, rho - net.rho_crit) for rho in rhos)
        # 잔차는 달성가능 목표(min(target, Σ물리상한)) 기준 — 수요 부족으로 덜 방출한 것을
        # "추적 실패"로 만들어 urban 쪽에 가짜 freeway 압력을 보내지 않게 한다.
        metering_error = abs(sum(ramp_metering.values()) - min(target, sum(upper.values())))
        objective = (
            sum(max(0.0, rho) * net.freeway_segment_length_km * net.freeway_lanes for rho in rhos)
            + self.cfg.freeway_follower.density_penalty * density_excess
            + 0.01 * metering_error
        )
        diagnostics = {
            f"agent_{agent.id}_density_excess": float(density_excess),
            f"agent_{agent.id}_metering_error": float(metering_error),
            f"agent_{agent.id}_min_receiving_factor": float(min_receiving),
            f"agent_{agent.id}_lane_loss": float(lane_loss),
        }
        diagnostics.update({f"agent_{agent.id}_{key}": value for key, value in lane_diag.items()})
        return AgentSolve(
            agent_id=agent.id,
            objective=float(objective),
            ramp_metering=ramp_metering,
            vsl={agent.link: desired},
            infeasibility={
                "metering_tracking_residual": float(metering_error),
                "density_excess": float(density_excess),
                "min_ramp_receiving_factor": float(min_receiving),
                "ramp_projection_first_step_capacity": float(sum(upper.values())),
            },
            diagnostics=diagnostics,
        )

    def _leaderless_metering_target(
        self,
        agent: AgentSpec,
        state: TrafficState,
        upper: Mapping[str, float],
    ) -> float:
        """leaderless freeway agent의 국소 metering 수준 선택.

        후보 = Σupper의 분율 {1.0, 0.85, 0.7, 0.5}. 1-구획 근사로 한 control interval 뒤
        merge 밀도를 예측해 비용 = density_penalty×pos(ρ_pred−ρ_crit) + 잡아둔 차량의
        대기비용(veh·h)으로 평가한다 — 전역 목표 없이 자기 목적만 사용(spec 16.7)."""
        net = self.cfg.network
        dt_h = self.cfg.simulation.T_c_h
        total_upper = sum(max(0.0, v) for v in upper.values())
        if total_upper <= 1.0e-9 or not agent.ramps:
            return total_upper
        merge_idx = agent.segment_index if agent.segment_index >= 0 else len(state.freeway_density[agent.link]) // 2
        rho_merge = state.freeway_density[agent.link][merge_idx]
        speed = max(state.freeway_speed[agent.link][merge_idx], net.v_min)
        seg_cap_veh = net.freeway_segment_length_km * net.freeway_lanes
        q_out = rho_merge * speed * net.freeway_lanes
        best_target, best_cost = total_upper, float("inf")
        for fraction in (1.0, 0.85, 0.7, 0.5):
            release = fraction * total_upper
            rho_pred = max(0.0, rho_merge + (release - q_out) * dt_h / max(seg_cap_veh, 1.0e-9))
            held = (total_upper - release) * dt_h  # 잡아둔 차량수[veh] — 대기비용으로 환산.
            cost = (
                self.cfg.freeway_follower.density_penalty * max(0.0, rho_pred - net.rho_crit)
                + held
            )
            if cost < best_cost:
                best_cost, best_target = cost, release
        return float(best_target)

    def _agent_vsl(self, density_ratio: float, lane_loss: float, previous_vsl: float) -> float:
        vsl_set = sorted(float(v) for v in self.cfg.freeway_follower.vsl_set)
        max_vsl = max(vsl_set)
        if lane_loss > 0.5 or density_ratio > 1.25:
            target = min(vsl_set)
        elif lane_loss > 0.1 or density_ratio > 1.05:
            target = 60.0
        elif density_ratio > 0.95:
            target = 80.0
        else:
            target = max_vsl
        low = previous_vsl - self.cfg.freeway_follower.max_vsl_step
        high = previous_vsl + self.cfg.freeway_follower.max_vsl_step
        feasible = [v for v in vsl_set if low - 1.0e-9 <= v <= high + 1.0e-9]
        feasible = feasible or vsl_set
        return float(min(feasible, key=lambda value: (abs(value - target), value)))

    def _solve_urban_agent(
        self,
        agent: AgentSpec,
        state: TrafficState,
        leader: Optional[LeaderAction],
        demand: DemandStep,
        freeway_response: FreewayFollowerResult,
        current: ControlAction,
        allocation_plan: AllocationResult,
    ) -> AgentSolve:
        result = self.urban_follower.solve(state.copy(), leader, demand, freeway_response, current, allocation_plan)
        specs = movement_specs(self.cfg)
        green = {
            key: value
            for key, value in result.green_times.items()
            if key.startswith(f"{agent.signal}_")
        }
        offsets = {agent.signal: result.offsets.get(agent.signal, current.offsets.get(agent.signal, 0.0))}
        # follower allocation에 없는 movement(internal 등)는 0이 아니라 "비제어"다 —
        # 0으로 머지하면 내부 그리드 이동이 동결돼 출구 보급이 끊긴다(그리드 라우팅 후 치명적).
        allocation = {
            movement: result.inflow_outflow_allocation[movement]
            for movement in agent.movements
            if movement in result.inflow_outflow_allocation
        }
        for movement in agent.movements:
            spec = specs.get(movement, {})
            origin = str(spec.get("origin", ""))
            destination = str(spec.get("destination", ""))
            kind = str(spec.get("kind", ""))
            # _legacy_boundary_allocations와 동일하게 kind까지 맞춰 합산한다
            # (corner boundary_in→out movement가 out 링크 합에 중복 산입되지 않게).
            if origin in self.cfg.network.boundary_in_links and kind == "boundary_in":
                allocation[origin] = allocation.get(origin, 0.0) + allocation[movement]
            if destination in self.cfg.network.boundary_out_links and kind == "boundary_out":
                allocation[destination] = allocation.get(destination, 0.0) + allocation[movement]
        local_queue = sum(state.urban_movement_queue.get(movement, 0.0) for movement in agent.movements)
        local_objective = float(local_queue + result.objective_value / max(len(self.urban_agents), 1))
        diagnostics = {
            f"agent_{agent.id}_local_queue": float(local_queue),
            f"agent_{agent.id}_freeway_pressure_used": float(result.metrics.get("freeway_response_used", 0.0)),
            f"agent_{agent.id}_allocation_module_used": float(result.metrics.get("allocation_module_active", 0.0)),
        }
        return AgentSolve(
            agent_id=agent.id,
            objective=local_objective,
            green_times=green,
            offsets=offsets,
            allocation=allocation,
            infeasibility=dict(result.infeasibility),
            diagnostics=diagnostics,
        )

    def _freeway_response(self, solves: list[AgentSolve]) -> FreewayFollowerResult:
        ramp_metering: Dict[str, float] = {}
        vsl: Dict[str, float] = {}
        objective = 0.0
        density_excess = 0.0
        metering_residual = 0.0
        step_capacity = 0.0
        min_receiving = 1.0
        for solve in solves:
            ramp_metering.update(solve.ramp_metering)
            vsl.update(solve.vsl)
            objective += solve.objective
            density_excess += solve.infeasibility.get("density_excess", 0.0)
            metering_residual += solve.infeasibility.get("metering_tracking_residual", 0.0)
            step_capacity += solve.infeasibility.get("ramp_projection_first_step_capacity", 0.0)
            min_receiving = min(min_receiving, solve.infeasibility.get("min_ramp_receiving_factor", 1.0))
        return FreewayFollowerResult(
            ramp_metering=ramp_metering,
            vsl=vsl,
            objective_value=float(objective),
            infeasibility={
                "density_excess": float(density_excess),
                "metering_tracking_residual": float(metering_residual),
                "ramp_projection_first_step_capacity": float(step_capacity),
                "min_ramp_receiving_factor": float(min_receiving),
                "freeway_follower_coupled_prediction": 0.0,
                "freeway_follower_lightweight_prediction": 1.0,
            },
        )

    def _merge_agent_controls(
        self,
        leader: Optional[LeaderAction],
        current: ControlAction,
        freeway_solves: list[AgentSolve],
        urban_solves: list[AgentSolve],
    ) -> ControlAction:
        alpha = float(np.clip(self.cfg.mpc.nash_relaxation_alpha, 0.0, 1.0))
        ramp_metering = dict(current.ramp_metering)
        vsl = dict(current.vsl)
        green_times = dict(current.green_times)
        offsets = dict(current.offsets)
        allocation = dict(current.inflow_outflow_allocation)
        infeasibility: Dict[str, float] = {}
        diagnostics: Dict[str, float] = {}
        for solve in freeway_solves:
            ramp_metering.update(solve.ramp_metering)
            vsl.update(solve.vsl)
            infeasibility.update(solve.infeasibility)
            diagnostics.update(solve.diagnostics)
        for solve in urban_solves:
            green_times.update(solve.green_times)
            offsets.update(solve.offsets)
            allocation.update(solve.allocation)
            infeasibility.update(solve.infeasibility)
            diagnostics.update(solve.diagnostics)
        allocation.update(self._legacy_boundary_allocations(allocation))
        return ControlAction(
            N_P_star=leader.N_P_star if leader is not None else 0.0,
            N_UF_star=leader.N_UF_star if leader is not None else 0.0,
            ramp_metering=_relax_map(current.ramp_metering, ramp_metering, alpha),
            vsl=vsl,
            green_times=_relax_map(current.green_times, green_times, alpha),
            offsets=_relax_map(current.offsets, offsets, alpha),
            inflow_outflow_allocation=_relax_map(current.inflow_outflow_allocation, allocation, alpha),
            infeasibility=infeasibility,
            diagnostics=diagnostics,
        )

    def _clamp_offsets_to_reference(
        self,
        offsets: Mapping[str, float],
        reference: ControlAction,
    ) -> Dict[str, float]:
        """분산 내부 iteration이 실제 control-interval offset 제약을 누적 위반하지 않게 막는다."""
        cycle = self.cfg.network.cycle_length
        max_step = self.cfg.urban_follower.max_offset_step
        out: Dict[str, float] = {}
        for signal in self.cfg.network.signals:
            prev = reference.offsets.get(signal, 0.0)
            value = offsets.get(signal, prev)
            delta = (value - prev + 0.5 * cycle) % cycle - 0.5 * cycle
            delta = float(np.clip(delta, -max_step, max_step))
            out[signal] = float((prev + delta) % cycle)
        return out

    def _clamp_vsl_to_reference(
        self,
        vsl: Mapping[str, float],
        reference: ControlAction,
    ) -> Dict[str, float]:
        """내부 iteration의 VSL 누적 드리프트가 interval 간 max_vsl_step 제약을
        위반하지 않게, 직전 적용 control 기준 ±step 범위의 discrete 값으로 스냅한다."""
        fc = self.cfg.freeway_follower
        vsl_set = sorted(float(v) for v in fc.vsl_set)
        out: Dict[str, float] = {}
        for link in self.cfg.network.freeway_links:
            prev = float(reference.vsl.get(link, max(vsl_set)))
            value = float(vsl.get(link, prev))
            feasible = [
                v for v in vsl_set
                if prev - fc.max_vsl_step - 1.0e-9 <= v <= prev + fc.max_vsl_step + 1.0e-9
            ] or vsl_set
            out[link] = float(min(feasible, key=lambda v: (abs(v - value), v)))
        return out

    def _legacy_boundary_allocations(self, allocation: Mapping[str, float]) -> Dict[str, float]:
        specs = movement_specs(self.cfg)
        out: Dict[str, float] = {}
        for link in self.cfg.network.boundary_in_links:
            out[link] = float(sum(
                allocation.get(movement, 0.0)
                for movement, spec in specs.items()
                if spec.get("origin") == link and spec.get("kind") == "boundary_in"
            ))
        for link in self.cfg.network.boundary_out_links:
            out[link] = float(sum(
                allocation.get(movement, 0.0)
                for movement, spec in specs.items()
                if spec.get("destination") == link and spec.get("kind") == "boundary_out"
            ))
        return out

    def _extract_coupling(
        self,
        state: TrafficState,
        control: ControlAction,
        demand: DemandStep,
    ) -> Dict[str, float]:
        ensure_urban_state(state, self.cfg)
        net = self.cfg.network
        onramp = estimate_onramp_green_release_flows(
            state.copy(),
            control,
            demand,
            self.cfg,
            interval_h=self.cfg.simulation.T_f_h,
        )
        values: Dict[str, float] = {}
        for ramp, value in onramp.items():
            values[f"u_on_{ramp}"] = float(value)
            values[f"w_ramp_{ramp}"] = float(state.ramp_queue.get(ramp, 0.0))
        for off_ramp in net.off_ramps:
            link = net.off_ramp_from_freeway[off_ramp]
            split = net.off_ramp_split_ratio.get(off_ramp, 0.0)
            flow = state.freeway_flow.get(link, [0.0])[-1] if state.freeway_flow.get(link) else 0.0
            values[f"q_off_{off_ramp}"] = float(max(0.0, flow * split))
        for link in net.freeway_links:
            rhos = state.freeway_density.get(link, [])
            speeds = state.freeway_speed.get(link, [])
            values[f"rho_boundary_{link}"] = float(rhos[-1] if rhos else 0.0)
            values[f"speed_boundary_{link}"] = float(speeds[-1] if speeds else 0.0)
        for agent in self.urban_agents:
            values[f"n_{agent.id}"] = float(sum(
                state.urban_movement_queue.get(movement, 0.0)
                for movement in agent.movements
            ))
        return values

    @staticmethod
    def _coupling_residual(old: Mapping[str, float], new: Mapping[str, float]) -> float:
        residual = 0.0
        for key in set(old) | set(new):
            a = float(old.get(key, 0.0))
            b = float(new.get(key, 0.0))
            residual = max(residual, abs(a - b) / max(1.0, abs(a), abs(b)))
        return float(residual)

    def _diagnostics(
        self,
        freeway_solves: list[AgentSolve],
        urban_solves: list[AgentSolve],
        residual: float,
        iteration: int,
    ) -> Dict[str, float]:
        out: Dict[str, float] = {
            "distributed_player_active": 1.0,
            "nash_per_agent_active": 1.0,
            "distributed_urban_agent_count": float(len(self.urban_agents)),
            "distributed_freeway_agent_count": float(len(self.freeway_agents)),
            "distributed_coupling_residual": float(residual if np.isfinite(residual) else 0.0),
            "distributed_iterations": float(iteration),
            "nash_mutual_response_active": 1.0,
            "nash_urban_used_freeway_response": 1.0,
            "nash_freeway_used_coupled_prediction": 0.0,
        }
        for agent in self.urban_agents + self.freeway_agents:
            out[f"distributed_agent_{agent.id}_active"] = 1.0
        for solve in freeway_solves + urban_solves:
            out[f"agent_{solve.agent_id}_objective"] = float(solve.objective)
            out.update(solve.diagnostics)
        return out
