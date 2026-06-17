from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional

import numpy as np

from src.controllers.freeway_follower import FreewayFollowerResult
from src.controllers.inflow_outflow_allocation import AllocationResult
from src.controllers.leader import LeaderAction
from src.controllers.nash_solver import NashResult, _relax_map
from src.controllers.relaxed_quantization import (
    accumulate_repair_diagnostics,
    merge_repair_diagnostics,
    repair_vsl_value,
)
from src.controllers.urban_follower import UrbanFollower
from src.models.demand import DemandStep
from src.models.metanet import effective_lane_profile
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    _movement_capacity_flow,
    _phase_green_fraction,
    ensure_urban_state,
    estimate_onramp_reservoir_inflow,
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


ABLATION_MODES = (
    "FULL_COUPLING",
    "NO_U_TO_F_INFO",
    "NO_F_TO_U_INFO",
    "NO_CROSS_NETWORK_INFO",
    "LOCAL_ONLY_COUPLING_PLAYERS",
    "FIXED_URBAN_COUPLING_PLAYERS",
    "FIXED_FREEWAY_COUPLING_PLAYERS",
    "FIXED_ALL_COUPLING_PLAYERS",
)


class DistributedCoordinator:
    """Wu §IV-D 형태의 agent별 follower coordinator.

    이 1차 구현은 기존 follower 휴리스틱을 재사용하되, 적용 변수는 agent 소유 변수로
    제한하고 coupling variable 변화량으로 반복 종료를 판단한다.

    Stage 3 ablation(plan §10~§11): physical 결합·차량 이동은 plant에 그대로 두고,
    여기서 strategic 정보 교환(u→f 예측 방출, f→u 압력)만 차단하거나 coupling player
    (U_D/U_F, merge·off-ramp freeway agent)의 결정을 고정 정책으로 대체한다.
    잔여 player와 leader는 변경된 game 기준으로 매 호출 재최적화된다."""

    def __init__(self, cfg: ExperimentConfig, ablation: str = "FULL_COUPLING"):
        if ablation not in ABLATION_MODES:
            raise ValueError(f"Unknown ablation mode: {ablation}")
        self.cfg = cfg
        self.ablation = ablation
        self.urban_agents, self.freeway_agents = build_agent_specs(cfg)
        self.urban_follower = UrbanFollower(cfg)
        self._repair_diagnostics: Dict[str, float] = {}
        self._specs = movement_specs(cfg)
        self._phase_movements: Dict[str, Dict[str, list[str]]] = {}
        for signal in cfg.network.signals:
            self._phase_movements[signal] = {
                phase_id: [
                    movement
                    for movement, spec in self._specs.items()
                    if spec.get("phase") == f"{signal}_{phase_id}"
                ]
                for phase_id in ("p1", "p2")
            }
        self._upstream_leaving_map = self._build_upstream_leaving_map()
        # coupling player 식별(plan §9.2): ramp/off-ramp 결합을 가진 agent — topology에서 자동.
        self.coupling_urban_ids = {a.id for a in self.urban_agents if a.ramps or a.off_ramps}
        self.coupling_freeway_ids = {a.id for a in self.freeway_agents if a.ramps or a.off_ramps}

    def _build_upstream_leaving_map(self) -> Dict[str, list[tuple[str, str, float]]]:
        """Wu `_upstream_leaving_map`와 같은 urban-to-urban phase coupling 지도.

        하류 phase pressure는 특정 internal movement 하나가 아니라 같은 incoming
        approach에서 같은 phase에 서는 모든 turn split의 합을 본다. 그래야 상류 green
        release가 downstream approach 전체 도착압으로 전달된다.
        """
        net = self.cfg.network
        signal_set = set(net.signals)
        producers_by_link: Dict[str, list[tuple[str, str]]] = {}
        for up_movement, up_spec in self._specs.items():
            dest = str(up_spec.get("destination", ""))
            up_signal = str(up_spec.get("signal", ""))
            if dest and up_signal in signal_set:
                producers_by_link.setdefault(dest, []).append((up_signal, up_movement))

        upstream_map: Dict[str, list[tuple[str, str, float]]] = {}
        for signal in net.signals:
            for phase_id, movements in self._phase_movements[signal].items():
                entries: list[tuple[str, str, float]] = []
                beta_by_origin: Dict[str, float] = {}
                for movement in movements:
                    spec = self._specs[movement]
                    origin = str(spec.get("origin", ""))
                    if not origin:
                        continue
                    beta_by_origin[origin] = beta_by_origin.get(origin, 0.0) + float(spec.get("beta", 0.0))
                for origin, beta in beta_by_origin.items():
                    for up_signal, up_movement in producers_by_link.get(origin, []):
                        entries.append((up_signal, up_movement, beta))
                upstream_map[f"{signal}_{phase_id}"] = entries
        return upstream_map

    def _signal_leaving_rate(self, movement: str, control: ControlAction) -> float:
        """상류 movement green release rate[veh/h]를 downstream phase pressure로 보낸다."""
        spec = self._specs[movement]
        green_fraction = _phase_green_fraction(control, self.cfg, spec)
        cap_flow = _movement_capacity_flow(control, self.cfg, movement, spec)
        return float(green_fraction * cap_flow)

    def _block_u_to_f(self, agent: AgentSpec) -> bool:
        """이 freeway agent가 urban 예측 정보(u_on 등)를 보면 안 되는가."""
        if self.ablation in {"NO_U_TO_F_INFO", "NO_CROSS_NETWORK_INFO"}:
            return True
        return self.ablation == "LOCAL_ONLY_COUPLING_PLAYERS" and agent.id in self.coupling_freeway_ids

    def _block_f_to_u(self, agent: AgentSpec) -> bool:
        """이 urban agent가 freeway 예측 압력/예측 off-ramp 정보를 보면 안 되는가."""
        if self.ablation in {"NO_F_TO_U_INFO", "NO_CROSS_NETWORK_INFO"}:
            return True
        return self.ablation == "LOCAL_ONLY_COUPLING_PLAYERS" and agent.id in self.coupling_urban_ids

    def _urban_player_fixed(self, agent: AgentSpec) -> bool:
        return (
            self.ablation in {"FIXED_URBAN_COUPLING_PLAYERS", "FIXED_ALL_COUPLING_PLAYERS"}
            and agent.id in self.coupling_urban_ids
        )

    def _freeway_player_fixed(self, agent: AgentSpec) -> bool:
        return (
            self.ablation in {"FIXED_FREEWAY_COUPLING_PLAYERS", "FIXED_ALL_COUPLING_PLAYERS"}
            and agent.id in self.coupling_freeway_ids
        )

    def _forecast_offramp_arrivals(
        self,
        state: TrafficState,
        forecast: list[DemandStep],
        link: str,
    ) -> float:
        """이 freeway link에서 갈라지는 off-ramp의 horizon 누적 예측 도착량[veh].

        off-ramp 도착 = diverge segment 도달 유량 × split. 현재 link 끝 유량을 기준으로
        forecast 본선 수요 비율만큼 horizon에 걸쳐 누적한다(boundary forecast가 본선
        수요를 바꾸면 off-ramp 예측 유입도 같이 변하게 — myopic이 아님)."""
        net = self.cfg.network
        dt_h = self.cfg.simulation.T_c_h
        horizon = max(1, self.cfg.mpc.horizon_steps)
        steps = forecast[: horizon]
        flows = state.freeway_flow.get(link, [])
        base_flow = float(flows[-1]) if flows else 0.0
        base_mainline = max(1.0e-9, float(forecast[0].freeway_mainline.get(link, 0.0)))
        total = 0.0
        for off_ramp in net.off_ramps:
            if net.off_ramp_from_freeway.get(off_ramp) != link:
                continue
            split = net.off_ramp_split_ratio.get(off_ramp, 0.0)
            for step in steps:
                # 본선 수요 비율로 도달 유량을 스케일 — forecast가 커지면 off-ramp 예측↑.
                scale = max(0.0, float(step.freeway_mainline.get(link, 0.0))) / base_mainline
                total += max(0.0, base_flow * scale * split) * dt_h
        return float(total)

    def _forecast_offramp_arrivals_by_ramp(
        self,
        state: TrafficState,
        forecast: list[DemandStep],
        link: str,
    ) -> Dict[str, float]:
        """link 집계와 같은 회계로 off-ramp별 horizon arrival[veh]을 만든다."""
        net = self.cfg.network
        dt_h = self.cfg.simulation.T_c_h
        horizon = max(1, self.cfg.mpc.horizon_steps)
        steps = forecast[: horizon]
        flows = state.freeway_flow.get(link, [])
        base_flow = float(flows[-1]) if flows else 0.0
        base_mainline = max(1.0e-9, float(forecast[0].freeway_mainline.get(link, 0.0)))
        out: Dict[str, float] = {}
        for off_ramp in net.off_ramps:
            if net.off_ramp_from_freeway.get(off_ramp) != link:
                continue
            split = net.off_ramp_split_ratio.get(off_ramp, 0.0)
            total = 0.0
            for step in steps:
                scale = max(0.0, float(step.freeway_mainline.get(link, 0.0))) / base_mainline
                total += max(0.0, base_flow * scale * split) * dt_h
            out[off_ramp] = float(total)
        return out

    def _freeway_neighbor_pressure(
        self,
        agent: AgentSpec,
        state: TrafficState,
        coupling: Mapping[str, float],
        lane_profile: Mapping[str, list[float]],
    ) -> float:
        """인접 segment 상태를 VSL/metring 판단에 넣는 freeway-to-freeway coupling pressure."""
        net = self.cfg.network
        rhos = state.freeway_density.get(agent.link, [])
        speeds = state.freeway_speed.get(agent.link, [])
        flows = state.freeway_flow.get(agent.link, [])
        lanes = lane_profile.get(agent.link, [net.freeway_lanes for _ in rhos])
        if agent.segment_index < 0 or not rhos:
            return 0.0
        pressure = 0.0
        for idx in (agent.segment_index - 1, agent.segment_index + 1):
            if idx < 0 or idx >= len(rhos):
                continue
            rho = float(coupling.get(f"rho_{agent.link}_seg{idx}", rhos[idx]))
            speed = float(coupling.get(
                f"speed_{agent.link}_seg{idx}",
                speeds[idx] if idx < len(speeds) else net.v_free,
            ))
            flow = float(coupling.get(
                f"flow_{agent.link}_seg{idx}",
                flows[idx] if idx < len(flows) else 0.0,
            ))
            lane_loss = max(
                0.0,
                float(coupling.get(
                    f"lane_loss_{agent.link}_seg{idx}",
                    net.freeway_lanes - float(lanes[idx] if idx < len(lanes) else net.freeway_lanes),
                )),
            )
            density_pressure = max(0.0, rho - net.rho_crit)
            speed_pressure = max(0.0, (net.v_free - speed) / max(net.v_free, 1.0e-9))
            flow_pressure = max(0.0, flow / max(net.freeway_capacity_veh_h, 1.0e-9) - 1.0)
            pressure += density_pressure + 0.25 * net.rho_crit * speed_pressure + 0.25 * net.rho_crit * flow_pressure
            pressure += 0.5 * lane_loss
        return float(max(0.0, pressure))

    def solve(
        self,
        state: TrafficState,
        leader: Optional[LeaderAction],
        demand: DemandStep | Iterable[DemandStep],
        previous_control: Optional[ControlAction] = None,
    ) -> NashResult:
        """leader=None이면 PROPOSED-FOLLOWERS-ONLY(spec 16.7, 2026-06-13 재정의) —
        allocation module 미사용, urban agent는 green 자유탐색 + offset, freeway agent는
        local objective로 metering/VSL을 결정한다. 숨은 전역 목표 없음."""
        forecast = [demand] if isinstance(demand, DemandStep) else list(demand)
        if not forecast:
            raise ValueError("DistributedCoordinator requires at least one demand step.")
        self._repair_diagnostics = {}
        first_demand = forecast[0]
        if previous_control is not None:
            reference_control = previous_control
        else:
            # leaderless 초기 기준은 물리적 no-control(allocation 비움) — fixed()의
            # 0.5cap allocation이 숨은 게이팅으로 남지 않게 한다.
            reference_control = (
                ControlAction.uncontrolled(self.cfg) if leader is None else ControlAction.fixed(self.cfg)
            )
        current = reference_control
        current.N_P_star = leader.N_P_star if leader is not None else 0.0
        current.N_UF_star = leader.N_UF_star if leader is not None else 0.0
        allocation_plan = (
            None if leader is None
            else self.urban_follower.allocation_module.solve(state, leader, forecast)
        )
        coupling = self._extract_coupling(state, current, first_demand)
        best_control = current
        best_obj = np.inf
        best_diag: Dict[str, float] = {}
        residual = np.inf
        converged = False
        iteration = 0

        for iteration in range(1, self.cfg.mpc.max_nash_iter + 1):
            # FIXED_* ablation: coupling player의 strategic 결정을 고정 정책으로 대체.
            # physical subsystem은 그대로 — strategic controller role만 제거(plan §11).
            freeway_solves = [
                self._fixed_freeway_solve(agent) if self._freeway_player_fixed(agent)
                else self._solve_freeway_agent(agent, state, leader, forecast, current, coupling)
                for agent in self.freeway_agents
            ]
            freeway_response = self._freeway_response(freeway_solves)
            urban_solves = [
                self._fixed_urban_solve(agent) if self._urban_player_fixed(agent)
                else self._solve_urban_agent(
                    agent,
                    state,
                    leader,
                    forecast,
                    freeway_response,
                    current,
                    allocation_plan,
                    coupling,
                )
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
        forecast: list[DemandStep],
        current: ControlAction,
        coupling: Mapping[str, float],
    ) -> AgentSolve:
        net = self.cfg.network
        dt_h = self.cfg.simulation.T_f_h
        demand = forecast[0]
        lane_profile, lane_diag = effective_lane_profile(state, self.cfg)
        neighbor_pressure = self._freeway_neighbor_pressure(agent, state, coupling, lane_profile)
        neighbor_metering_factor = 1.0 - 0.15 * float(np.clip(
            neighbor_pressure / max(2.0 * net.rho_crit, 1.0e-9),
            0.0,
            1.0,
        ))
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
            # NO_U_TO_F/LOCAL_ONLY ablation: urban 예측 방출 정보 차단 — 측정된 현재
            # w_r만 사용(zero-order hold). 물리 차량 이동은 plant에서 그대로 일어난다.
            urban_release = 0.0 if self._block_u_to_f(agent) else max(0.0, coupling.get(f"u_on_{ramp}", 0.0))
            available = state.ramp_queue.get(ramp, 0.0) / max(dt_h, 1.0e-9) + urban_release
            upper[ramp] = min(
                net.ramp_capacity_veh_h[ramp],
                available,
                net.freeway_capacity_veh_h * receiving * neighbor_metering_factor,
            )
            weights[ramp] = state.ramp_queue.get(ramp, 0.0) + urban_release * self.cfg.simulation.T_c_h + 1.0
        if leader is not None:
            target = max(0.0, leader.N_UF_star) * link_capacity / total_capacity
        else:
            # leaderless(spec 16.7): 전역 N_UF 목표 없이 agent가 local objective로 방출
            # 수준을 고른다 — 후보 분율을 1-구획 merge 밀도 예측으로 평가해 최소 비용 선택.
            target = self._leaderless_metering_target(agent, state, upper, demand)
        ramp_metering = _project_to_target(target, upper, weights)
        all_rhos = state.freeway_density.get(agent.link, [])
        rhos = [all_rhos[agent.segment_index]] if 0 <= agent.segment_index < len(all_rhos) else all_rhos
        max_density = max(rhos) if rhos else 0.0
        density_ratio = max_density / max(net.rho_crit, 1.0e-9)
        lanes_for_link = lane_profile.get(agent.link, [net.freeway_lanes])
        lane_idx = agent.segment_index if 0 <= agent.segment_index < len(lanes_for_link) else len(lanes_for_link) - 1
        lane_loss = max(0.0, net.freeway_lanes - lanes_for_link[lane_idx])
        # off-ramp 램프 storage 재귀속(design 2026-06-17): 이 freeway link에서 갈라지는
        # off-ramp storage 점유[veh]를 계산해 freeway agent 자기 비용(objective)에 가산한다.
        offramp_storage_veh = 0.0
        offramp_capacity_veh = 0.0
        offramp_storage_pressure: Dict[str, float] = {}
        for off_ramp in net.off_ramps:
            if net.off_ramp_from_freeway.get(off_ramp) != agent.link:
                continue
            storage_link = net.off_ramp_storage_link.get(off_ramp, "")
            capacity = float(net.urban_link_storage_veh.get(storage_link, 0.0))
            if capacity <= 0.0:
                continue
            avail = float(state.urban_link_storage.get(storage_link, capacity))
            occupied = max(0.0, capacity - avail)
            offramp_storage_veh += occupied
            offramp_capacity_veh += capacity
            offramp_storage_pressure[off_ramp] = float(occupied / max(capacity, 1.0e-9))
        # forecast horizon에 걸친 off-ramp 예측 유입[veh] — VSL이 낮을수록 diverge
        # 도달량이 줄어 off-ramp storage 유입이 줄어드는 emergence를 후보 평가에 반영한다.
        offramp_forecast_by_ramp = self._forecast_offramp_arrivals_by_ramp(state, forecast, agent.link)
        offramp_forecast_veh = sum(offramp_forecast_by_ramp.values())
        prev_vsl = current.vsl.get(agent.link, max(self.cfg.freeway_follower.vsl_set))
        desired, vsl_eval_count = self._search_agent_vsl(
            agent,
            rhos,
            lane_loss + 0.05 * neighbor_pressure,
            prev_vsl,
            offramp_storage_veh,
            offramp_forecast_veh,
            offramp_capacity_veh,
            ramp_metering,
        )
        density_excess = sum(max(0.0, rho - net.rho_crit) for rho in rhos)
        # 잔차는 달성가능 목표(min(target, Σ물리상한)) 기준 — 수요 부족으로 덜 방출한 것을
        # "추적 실패"로 만들어 urban 쪽에 가짜 freeway 압력을 보내지 않게 한다.
        metering_error = abs(sum(ramp_metering.values()) - min(target, sum(upper.values())))
        objective = self._freeway_agent_objective(
            rhos,
            density_excess,
            metering_error,
            ramp_metering,
            desired,
            prev_vsl,
            offramp_forecast_veh,
            offramp_storage_veh,
            offramp_capacity_veh,
        )
        vsl_fraction = self._offramp_release_fraction(desired)
        selected_offramp_arrival = {
            off_ramp: float(vehicles * vsl_fraction)
            for off_ramp, vehicles in offramp_forecast_by_ramp.items()
        }
        horizon_h = self.cfg.simulation.T_c_h * max(1, len(forecast[: max(1, self.cfg.mpc.horizon_steps)]))
        diagnostics = {
            f"agent_{agent.id}_density_excess": float(density_excess),
            f"agent_{agent.id}_metering_error": float(metering_error),
            f"agent_{agent.id}_min_receiving_factor": float(min_receiving),
            f"agent_{agent.id}_lane_loss": float(lane_loss),
            f"agent_{agent.id}_freeway_neighbor_pressure": float(neighbor_pressure),
            f"agent_{agent.id}_freeway_neighbor_metering_factor": float(neighbor_metering_factor),
            f"agent_{agent.id}_offramp_storage_veh": float(offramp_storage_veh),
            f"agent_{agent.id}_offramp_forecast_veh": float(offramp_forecast_veh),
            f"agent_{agent.id}_vsl_candidates": float(vsl_eval_count),
            f"agent_{agent.id}_vsl_selected": float(desired),
        }
        for off_ramp, vehicles in selected_offramp_arrival.items():
            diagnostics[f"agent_{agent.id}_offramp_selected_arrival_{off_ramp}_veh"] = float(vehicles)
            diagnostics[f"agent_{agent.id}_offramp_selected_flow_{off_ramp}"] = float(
                vehicles / max(horizon_h, 1.0e-9)
            )
            diagnostics[f"agent_{agent.id}_offramp_storage_pressure_{off_ramp}"] = float(
                offramp_storage_pressure.get(off_ramp, 0.0)
            )
        diagnostics.update({f"agent_{agent.id}_{key}": value for key, value in lane_diag.items()})
        infeasibility = {
            "metering_tracking_residual": float(metering_error),
            "density_excess": float(density_excess),
            "min_ramp_receiving_factor": float(min_receiving),
            "ramp_projection_first_step_capacity": float(sum(upper.values())),
        }
        for off_ramp, vehicles in selected_offramp_arrival.items():
            infeasibility[f"offramp_predicted_arrival_{off_ramp}_veh"] = float(vehicles)
            infeasibility[f"offramp_predicted_flow_{off_ramp}"] = float(vehicles / max(horizon_h, 1.0e-9))
            infeasibility[f"offramp_storage_pressure_{off_ramp}"] = float(
                offramp_storage_pressure.get(off_ramp, 0.0)
            )
        return AgentSolve(
            agent_id=agent.id,
            objective=float(objective),
            ramp_metering=ramp_metering,
            vsl={agent.link: desired},
            infeasibility=infeasibility,
            diagnostics=diagnostics,
        )

    def _leaderless_metering_target(
        self,
        agent: AgentSpec,
        state: TrafficState,
        upper: Mapping[str, float],
        demand: DemandStep,
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
        if merge_idx > 0:
            q_upstream = max(0.0, state.freeway_flow[agent.link][merge_idx - 1])
        else:
            q_upstream = max(0.0, demand.freeway_mainline.get(agent.link, 0.0))
        # ramp/on-ramp 큐 비용을 제대로 가격화한다(진단 문서 §"Relation To Wu"): 이미 큐가
        # 쌓인 ramp에 metering을 더 하면 큐 대기손실이 비선형으로 커진다. no-metering(=용량
        # 방출, fraction=1.0)을 보호 baseline 후보로 명시 — 국소 density만으로 과도하게
        # metering해 TTT가 악화되지 않게 한다.
        existing_ramp_queue = sum(max(0.0, state.ramp_queue.get(r, 0.0)) for r in agent.ramps)
        ramp_queue_max = max(net.ramp_queue_max_veh * max(len(agent.ramps), 1), 1.0e-9)
        queue_saturation = min(1.0, existing_ramp_queue / ramp_queue_max)
        best_target, best_cost = total_upper, float("inf")  # baseline = no-metering(용량 방출).
        for fraction in (1.0, 0.85, 0.7, 0.5):
            release = fraction * total_upper
            # Spec 3.1.2 conservation: merge 유입은 본선 상류 유량과 ramp release의 합이다.
            rho_pred = max(
                0.0,
                rho_merge + (q_upstream + release - q_out) * dt_h / max(seg_cap_veh, 1.0e-9),
            )
            held = (total_upper - release) * dt_h  # 잡아둔 차량수[veh] — 대기비용으로 환산.
            # 기존 ramp 큐가 포화에 가까울수록 추가로 잡아두는 비용을 가중(spillback 위험).
            held_cost = held * (1.0 + queue_saturation)
            cost = (
                self.cfg.freeway_follower.density_penalty * max(0.0, rho_pred - net.rho_crit)
                + held_cost
            )
            # 동률(자유류 ρ_pred<ρ_crit, 모든 cost 동일)이면 no-metering을 보호: strict 비교라
            # fraction=1.0이 먼저 best로 잡혀 유지된다.
            if cost < best_cost - 1.0e-12:
                best_cost, best_target = cost, release
        return float(best_target)

    def _vsl_candidates(self, previous_vsl: float) -> list[float]:
        """이 control interval에 freeway agent가 고를 수 있는 VSL 후보 집합[km/h].

        full 모드: vsl_set 중 직전 VSL ±max_vsl_step 안에 드는 discrete 값(보통 3~5개,
        Cartesian 폭증 없이 per-link 1차원). relaxed-quantized 모드: 연속 target(=max,
        한 단계 낮춤, 두 단계 낮춤)을 공통 repair로 양자화해 소수 생성. 어느 모드든
        후보 수가 vsl_set 크기를 넘지 않는다(Nash 루프 비용 bound)."""
        fc = self.cfg.freeway_follower
        vsl_set = sorted(float(v) for v in fc.vsl_set)
        if not self.cfg.mpc.relaxed_quantized_controls:
            feasible = [
                v for v in vsl_set
                if previous_vsl - fc.max_vsl_step - 1.0e-9 <= v <= previous_vsl + fc.max_vsl_step + 1.0e-9
            ]
            return feasible or vsl_set
        max_vsl = max(vsl_set)
        step = max(1.0e-9, fc.max_vsl_step)
        out: list[float] = []
        for raw in (max_vsl, previous_vsl, previous_vsl - step, previous_vsl - 2.0 * step):
            repaired = repair_vsl_value(float(raw), float(previous_vsl), self.cfg)
            if not any(abs(repaired.value - v) <= 1.0e-9 for v in out):
                accumulate_repair_diagnostics(self._repair_diagnostics, vsl=repaired)
                out.append(repaired.value)
        return out

    def _offramp_release_fraction(self, vsl: float) -> float:
        """VSL[km/h] → diverge segment 도달(=off-ramp 유입) 비율 근사 [0,1].

        VSL이 낮을수록 상류 유출(=diverge 도달)이 줄어 off-ramp 유입이 준다는 단조
        관계를 1차로 근사한다. 정밀 plant 예측이 아니라 후보 순위용 경량 surrogate."""
        max_vsl = max(float(v) for v in self.cfg.freeway_follower.vsl_set)
        return float(np.clip(vsl / max(max_vsl, 1.0e-9), 0.0, 1.0))

    def _freeway_agent_objective(
        self,
        rhos: list[float],
        density_excess: float,
        metering_error: float,
        ramp_metering: Mapping[str, float],
        vsl: float,
        previous_vsl: float,
        offramp_forecast_veh: float,
        offramp_storage_veh: float,
        offramp_capacity_veh: float = 0.0,
    ) -> float:
        """freeway agent 자기 비용(horizon emergence). 본선 차량·density penalty·
        off-ramp 큐(현재 점유 + VSL이 통과시키는 예측 유입의 spillback 가중분)·본선 hold·
        Δvsl smooth의 합. off-ramp가 포화에 가까우면 추가 유입의 spillback 비용이 비선형으로
        커져, VSL을 낮춰(예측 유입↓) 비용을 줄이는 게 emergent하게 유리해진다. off-ramp가
        비어 있으면 spillback 가중≈1이라 VSL을 낮출 유인이 없어 max VSL이 선택된다."""
        net = self.cfg.network
        fc = self.cfg.freeway_follower
        fraction = self._offramp_release_fraction(vsl)
        admitted = offramp_forecast_veh * fraction
        # off-ramp 포화도[0~1+]: 점유가 용량에 가까울수록 추가 유입의 spillback 비용이 커진다.
        occupancy_ratio = offramp_storage_veh / max(offramp_capacity_veh, 1.0e-9)
        spillback_weight = 1.0 + max(0.0, occupancy_ratio)
        offramp_cost = offramp_storage_veh + admitted * spillback_weight
        # VSL을 낮춰 통과시키지 못한 차량은 본선에 잡힘(hold) — 본선 대기 비용(가중 1)으로 가산.
        held_mainline = offramp_forecast_veh * (1.0 - fraction)
        # Δvsl smooth: 작은 off-ramp 압력에 과민하게 VSL을 흔들지 않도록 [km/h] 단위 그대로
        # 가격화한다. off-ramp 압력 이득이 smooth 비용을 넘어설 때만 VSL을 낮춘다(단조 emergence).
        return float(
            sum(max(0.0, rho) * net.freeway_segment_length_km * net.freeway_lanes for rho in rhos)
            + fc.density_penalty * density_excess
            + 0.01 * metering_error
            + offramp_cost
            + held_mainline
            + fc.vsl_smoothness_weight * abs(vsl - previous_vsl)
        )

    def _search_agent_vsl(
        self,
        agent: AgentSpec,
        rhos: list[float],
        lane_loss: float,
        previous_vsl: float,
        offramp_storage_veh: float,
        offramp_forecast_veh: float,
        offramp_capacity_veh: float,
        ramp_metering: Mapping[str, float],
    ) -> tuple[float, int]:
        """VSL 후보를 horizon objective로 평가해 최소 비용 후보를 고른다(emergence, option 2).

        트리거 없음 — off-ramp storage backup·예측 유입이 objective에 들어 있어 후보 평가
        과정에서 VSL이 자연히 낮아진다. lane-drop은 물리 제약이라 후보 평가와 별개로
        density_excess를 통해 반영된다."""
        net = self.cfg.network
        # lane-drop은 통과 용량을 줄이는 물리 제약 — density_excess에 가산해 후보 평가가
        # 차선 손실 segment에서 더 낮은 VSL을 선호하게 한다(트리거 아님, 비용 가중).
        density_excess = sum(max(0.0, rho - net.rho_crit) for rho in rhos) + lane_loss
        metering_error = 0.0  # VSL 선택은 metering_error와 독립 — 순위에 영향 없는 상수.
        candidates = self._vsl_candidates(previous_vsl)
        best_vsl, best_cost = previous_vsl, float("inf")
        for vsl in candidates:
            cost = self._freeway_agent_objective(
                rhos,
                density_excess,
                metering_error,
                ramp_metering,
                vsl,
                previous_vsl,
                offramp_forecast_veh,
                offramp_storage_veh,
                offramp_capacity_veh,
            )
            if cost < best_cost - 1.0e-12:
                best_cost, best_vsl = cost, float(vsl)
        return float(best_vsl), len(candidates)

    def _phase_arrival_coupling(
        self,
        agent: AgentSpec,
        coupling: Mapping[str, float],
    ) -> Dict[str, float]:
        """Wu식 arr_* flow[veh/h]를 UrbanFollower의 horizon arrival[veh]로 변환한다."""
        dt_h = self.cfg.simulation.T_c_h
        horizon = max(1, self.cfg.mpc.horizon_steps)
        out: Dict[str, float] = {}
        for phase_id in ("p1", "p2"):
            phase = f"{agent.signal}_{phase_id}"
            flow = max(0.0, float(coupling.get(f"arr_{phase}", 0.0)))
            if flow > 0.0:
                out[phase] = flow * dt_h * horizon
        return out

    def _coupling_active_flags(self) -> Dict[str, float]:
        """ablation 설정을 반영한 direction별 strategic coupling 활성 플래그."""
        u_to_f = 0.0 if self.ablation in {
            "NO_U_TO_F_INFO",
            "NO_CROSS_NETWORK_INFO",
            "LOCAL_ONLY_COUPLING_PLAYERS",
        } else 1.0
        f_to_u = 0.0 if self.ablation in {
            "NO_F_TO_U_INFO",
            "NO_CROSS_NETWORK_INFO",
            "LOCAL_ONLY_COUPLING_PLAYERS",
        } else 1.0
        return {
            "distributed_u_to_f_coupling_active": u_to_f,
            "distributed_f_to_u_coupling_active": f_to_u,
            "distributed_u_to_u_coupling_active": 1.0,
            "distributed_f_to_f_coupling_active": 1.0,
        }

    def _solve_urban_agent(
        self,
        agent: AgentSpec,
        state: TrafficState,
        leader: Optional[LeaderAction],
        forecast: list[DemandStep],
        freeway_response: FreewayFollowerResult,
        current: ControlAction,
        allocation_plan: Optional[AllocationResult],
        coupling: Mapping[str, float],
    ) -> AgentSolve:
        demand = forecast[0]
        # NO_F_TO_U/LOCAL_ONLY ablation: freeway 예측 압력 정보 차단 — urban은 측정된
        # 현재 off-ramp 도착(plant 경유)만 disturbance로 받는다.
        if self._block_f_to_u(agent):
            freeway_response = None
        phase_arrival_coupling = self._phase_arrival_coupling(agent, coupling)
        result = self.urban_follower.solve(
            state.copy(),
            leader,
            demand,
            freeway_response,
            current,
            allocation_plan,
            forecast=forecast,
            phase_arrival_coupling=phase_arrival_coupling,
        )
        specs = movement_specs(self.cfg)
        green = {
            key: value
            for key, value in result.green_times.items()
            if key.startswith(f"{agent.signal}_")
        }
        offsets = {agent.signal: result.offsets.get(agent.signal, current.offsets.get(agent.signal, 0.0))}
        # follower allocation에 없는 movement(internal 등)는 0이 아니라 "비제어"다 —
        # 0으로 머지하면 내부 그리드 이동이 동결돼 출구 보급이 끊긴다(그리드 라우팅 후 치명적).
        # leaderless(P-FO)는 allocation 자체가 비어 있으므로 아래 합산도 자연히 건너뛴다.
        allocation = {
            movement: result.inflow_outflow_allocation[movement]
            for movement in agent.movements
            if movement in result.inflow_outflow_allocation
        }
        for movement in agent.movements:
            if movement not in allocation:
                continue
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
        merge_repair_diagnostics(diagnostics, result.metrics)
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
        vsl = self._aggregate_link_vsl(solves)
        objective = 0.0
        density_excess = 0.0
        metering_residual = 0.0
        step_capacity = 0.0
        min_receiving = 1.0
        coupling_payload: Dict[str, float] = {}
        for solve in solves:
            ramp_metering.update(solve.ramp_metering)
            objective += solve.objective
            density_excess += solve.infeasibility.get("density_excess", 0.0)
            metering_residual += solve.infeasibility.get("metering_tracking_residual", 0.0)
            step_capacity += solve.infeasibility.get("ramp_projection_first_step_capacity", 0.0)
            min_receiving = min(min_receiving, solve.infeasibility.get("min_ramp_receiving_factor", 1.0))
            for key, value in solve.infeasibility.items():
                if key.startswith(("offramp_predicted_arrival_", "offramp_predicted_flow_")):
                    coupling_payload[key] = coupling_payload.get(key, 0.0) + float(value)
                elif key.startswith("offramp_storage_pressure_"):
                    coupling_payload[key] = max(coupling_payload.get(key, 0.0), float(value))
        infeasibility = {
            "density_excess": float(density_excess),
            "metering_tracking_residual": float(metering_residual),
            "ramp_projection_first_step_capacity": float(step_capacity),
            "min_ramp_receiving_factor": float(min_receiving),
            "freeway_follower_coupled_prediction": 0.0,
            "freeway_follower_lightweight_prediction": 1.0,
        }
        infeasibility.update(coupling_payload)
        return FreewayFollowerResult(
            ramp_metering=ramp_metering,
            vsl=vsl,
            objective_value=float(objective),
            infeasibility=infeasibility,
        )

    def _aggregate_link_vsl(self, solves: list[AgentSolve]) -> Dict[str, float]:
        """segment agent의 제안을 하나의 link-level VSL actuator로 합의한다.

        동일 link를 여러 agent가 소유한 것처럼 순서대로 덮어쓰지 않고, local
        congestion constraint 중 가장 제한적인 제안을 consensus projection으로 쓴다.
        """
        by_link: Dict[str, list[float]] = {link: [] for link in self.cfg.network.freeway_links}
        for solve in solves:
            for link, value in solve.vsl.items():
                by_link.setdefault(link, []).append(float(value))
        maximum = max(self.cfg.freeway_follower.vsl_set)
        return {
            link: float(min(values)) if values else float(maximum)
            for link, values in by_link.items()
        }

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
            infeasibility.update(solve.infeasibility)
            merge_repair_diagnostics(diagnostics, solve.diagnostics)
            diagnostics.update({
                k: v for k, v in solve.diagnostics.items()
                if k not in diagnostics or "quantization" not in k and "repair_count" not in k
            })
        vsl.update(self._aggregate_link_vsl(freeway_solves))
        for solve in urban_solves:
            green_times.update(solve.green_times)
            offsets.update(solve.offsets)
            allocation.update(solve.allocation)
            infeasibility.update(solve.infeasibility)
            merge_repair_diagnostics(diagnostics, solve.diagnostics)
            diagnostics.update({
                k: v for k, v in solve.diagnostics.items()
                if k not in diagnostics or "quantization" not in k and "repair_count" not in k
            })
        merge_repair_diagnostics(diagnostics, self._repair_diagnostics)
        if leader is None:
            # P-FO(spec 16.7 재정의): allocation 비제어 — plant 포화유율 fallback.
            allocation = {}
        else:
            allocation.update(self._legacy_boundary_allocations(allocation))
        return ControlAction(
            N_P_star=leader.N_P_star if leader is not None else 0.0,
            N_UF_star=leader.N_UF_star if leader is not None else 0.0,
            ramp_metering=_relax_map(current.ramp_metering, ramp_metering, alpha),
            vsl=vsl,
            green_times=_relax_map(current.green_times, green_times, alpha),
            offsets=_relax_map(current.offsets, offsets, alpha),
            inflow_outflow_allocation=(
                {} if leader is None
                else _relax_map(current.inflow_outflow_allocation, allocation, alpha)
            ),
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

    def _fixed_urban_solve(self, agent: AgentSpec) -> AgentSolve:
        """FIXED_URBAN_COUPLING_PLAYERS: green 50:50·offset 0·allocation 0.5cap 고정 정책."""
        net = self.cfg.network
        fixed = ControlAction.fixed(self.cfg)
        return AgentSolve(
            agent_id=agent.id,
            objective=0.0,
            green_times={
                f"{agent.signal}_p1": fixed.green_times[f"{agent.signal}_p1"],
                f"{agent.signal}_p2": fixed.green_times[f"{agent.signal}_p2"],
            },
            offsets={agent.signal: 0.0},
            allocation={m: fixed.inflow_outflow_allocation.get(m, 0.5 * net.movement_capacity_veh_h)
                        for m in agent.movements},
            diagnostics={f"agent_{agent.id}_fixed_policy": 1.0},
        )

    def _fixed_freeway_solve(self, agent: AgentSpec) -> AgentSolve:
        """FIXED_FREEWAY_COUPLING_PLAYERS: VSL=max·metering=용량(neutral) 고정 정책."""
        net = self.cfg.network
        return AgentSolve(
            agent_id=agent.id,
            objective=0.0,
            ramp_metering={r: net.ramp_capacity_veh_h[r] for r in agent.ramps},
            vsl={agent.link: max(self.cfg.freeway_follower.vsl_set)},
            infeasibility={
                "metering_tracking_residual": 0.0,
                "density_excess": 0.0,
                "min_ramp_receiving_factor": 1.0,
                "ramp_projection_first_step_capacity": sum(net.ramp_capacity_veh_h[r] for r in agent.ramps),
            },
            diagnostics={f"agent_{agent.id}_fixed_policy": 1.0},
        )

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
            if self.cfg.mpc.relaxed_quantized_controls:
                repaired = repair_vsl_value(value, prev, self.cfg)
                accumulate_repair_diagnostics(self._repair_diagnostics, vsl=repaired)
                out[link] = repaired.value
            else:
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
        # Spec 3.4/Wu coupling: ramp queue 공간 cap을 빼고 green 후보가 만든 접근부
        # reservoir inflow[veh/h]를 freeway agent에 전달한다.
        onramp = estimate_onramp_reservoir_inflow(
            state.copy(),
            control,
            demand,
            self.cfg,
            interval_h=self.cfg.simulation.T_c_h,
        )
        values: Dict[str, float] = {}
        for ramp, value in onramp.items():
            values[f"u_on_{ramp}"] = float(value)
            values[f"w_ramp_{ramp}"] = float(state.ramp_queue.get(ramp, 0.0))
        # urban→urban coupling: 상류 green release rate를 하류 phase arrival pressure로 보낸다.
        for signal in net.signals:
            for phase_id in ("p1", "p2"):
                phase = f"{signal}_{phase_id}"
                arrival_flow = 0.0
                for _up_signal, up_movement, beta in self._upstream_leaving_map.get(phase, []):
                    arrival_flow += beta * self._signal_leaving_rate(up_movement, control)
                values[f"arr_{phase}"] = float(max(0.0, arrival_flow))
        for off_ramp in net.off_ramps:
            link = net.off_ramp_from_freeway[off_ramp]
            split = net.off_ramp_split_ratio.get(off_ramp, 0.0)
            flow = state.freeway_flow.get(link, [0.0])[-1] if state.freeway_flow.get(link) else 0.0
            values[f"q_off_{off_ramp}"] = float(max(0.0, flow * split))
        for link in net.freeway_links:
            rhos = state.freeway_density.get(link, [])
            speeds = state.freeway_speed.get(link, [])
            flows = state.freeway_flow.get(link, [])
            lanes = state.freeway_effective_lanes.get(link, [net.freeway_lanes for _ in rhos])
            values[f"rho_boundary_{link}"] = float(rhos[-1] if rhos else 0.0)
            values[f"speed_boundary_{link}"] = float(speeds[-1] if speeds else 0.0)
            for idx, rho in enumerate(rhos):
                values[f"rho_{link}_seg{idx}"] = float(rho)
                values[f"speed_{link}_seg{idx}"] = float(speeds[idx] if idx < len(speeds) else net.v_free)
                values[f"flow_{link}_seg{idx}"] = float(flows[idx] if idx < len(flows) else 0.0)
                lane_eff = float(lanes[idx] if idx < len(lanes) else net.freeway_lanes)
                values[f"lane_loss_{link}_seg{idx}"] = float(max(0.0, net.freeway_lanes - lane_eff))
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
        }
        coupling_flags = self._coupling_active_flags()
        out.update(coupling_flags)
        out["nash_freeway_used_coupled_prediction"] = coupling_flags["distributed_u_to_f_coupling_active"]
        out["nash_urban_used_freeway_response"] = coupling_flags["distributed_f_to_u_coupling_active"]
        out["distributed_neighbor_coupling_active"] = float(max(coupling_flags.values()))
        for agent in self.urban_agents + self.freeway_agents:
            out[f"distributed_agent_{agent.id}_active"] = 1.0
        for solve in freeway_solves + urban_solves:
            out[f"agent_{solve.agent_id}_objective"] = float(solve.objective)
            merge_repair_diagnostics(out, solve.diagnostics)
            out.update({
                k: v for k, v in solve.diagnostics.items()
                if k not in out or "quantization" not in k and "repair_count" not in k
            })
        merge_repair_diagnostics(out, self._repair_diagnostics)
        return out
