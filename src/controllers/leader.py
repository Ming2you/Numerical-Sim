from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from src.models.demand import DemandStep, merge_freeway_lane_loss
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    estimate_onramp_green_release_flows,
    movement_forecast_arrivals_veh,
    movement_storage_capacity,
)


@dataclass(frozen=True)
class LeaderAction:
    N_P_star: float
    N_UF_star: float


@dataclass(frozen=True)
class LeaderCandidateBounds:
    np_lower: float
    np_upper: float
    nuf_lower: float
    nuf_upper: float
    heuristic_nuf: float
    movement_min_net_flow_veh_h: float
    movement_max_net_flow_veh_h: float
    movement_np_lower: float
    movement_np_upper: float
    movement_np_lower_active: bool
    movement_np_upper_active: bool


class Leader:
    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg

    def _forecast_demand_summary(self, forecast: list[DemandStep]) -> DemandStep:
        """horizon 수요 요약 DemandStep — 후보 생성이 첫 스텝이 아닌 예측 수요압을 보게 한다.

        진단 문서 §"Recommended fix" 4: 예측 ramp/boundary/off-ramp 수요를 후보 생성에
        반영한다. 각 키별로 horizon peak(최대 수요)를 취해, 곧 닥칠 수요 파동에 맞춘
        N_UF feasible/heuristic 후보를 만든다(첫 스텝이 낮아도 후보 영역을 충분히 덮음)."""
        steps = forecast[: max(1, self.cfg.mpc.horizon_steps)]
        if len(steps) <= 1:
            return steps[0]

        def peak(getter) -> Dict[str, float]:
            keys: set[str] = set()
            for s in steps:
                keys |= set(getter(s).keys())
            return {k: max(float(getter(s).get(k, 0.0)) for s in steps) for k in keys}

        return DemandStep(
            freeway_mainline=peak(lambda s: s.freeway_mainline),
            urban_boundary=peak(lambda s: s.urban_boundary),
            ramp_arrival=peak(lambda s: s.ramp_arrival),
            incident_capacity_factor=min(
                float(getattr(s, "incident_capacity_factor", 1.0)) for s in steps
            ),
            freeway_lane_loss=merge_freeway_lane_loss(steps),
        )

    def candidates(
        self,
        state: TrafficState,
        previous: Optional[ControlAction] = None,
        demand: Optional[DemandStep] = None,
        forecast: Optional[list[DemandStep]] = None,
    ) -> List[LeaderAction]:
        leader = self.cfg.leader
        # forecast가 주어지면 horizon 수요 요약으로 후보를 생성한다(진단 문서 §4). None이면
        # 기존 first-demand 동작(하위 호환). boundary 비용은 건드리지 않는다 — 후보 생성만.
        if forecast:
            demand = self._forecast_demand_summary(list(forecast))
        count = max(3, self.cfg.mpc.leader_candidate_count)
        n_np = max(2, int(round(np.sqrt(count))))
        n_nuf = max(2, int(np.ceil(count / n_np)))
        bounds = self._candidate_bounds(state, previous, demand, forecast)
        np_lower, np_upper = bounds.np_lower, bounds.np_upper
        np_values = set(float(v) for v in np.linspace(np_lower, np_upper, n_np))
        np_values.add(float(np.clip(0.0, np_lower, np_upper)))
        np_values.add(float(np.clip(bounds.movement_np_lower, np_lower, np_upper)))
        np_values.add(float(np.clip(bounds.movement_np_upper, np_lower, np_upper)))
        density_ratio = self._density_ratio(state)
        feasible_nuf = self._feasible_nuf_capacity(state, previous, demand)
        # 자유류(평균밀도 ≤ metering 활성화 임계)에서는 T_f 단위 feasible 추정이
        # metering을 강제하지 않도록 후보 상한을 ramp 총용량까지 열어둔다.
        # (feasible은 다음 T_f에 추적가능한 유량 추정이라 지속 수요를 과소평가 —
        # 이를 ceiling으로 쓰면 본선이 한가해도 w_r에 순수 대기손실이 쌓인다.)
        if density_ratio <= leader.metering_activation_density_ratio:
            feasible_nuf = max(feasible_nuf, self.cfg.network.total_ramp_capacity)
        nuf_physical_lower = self._minimum_nuf_target()
        nuf_lower = max(float(leader.N_UF_star_range[0]), nuf_physical_lower)
        nuf_upper = min(leader.N_UF_star_range[1], feasible_nuf)
        nuf_upper = max(nuf_lower, nuf_upper)
        heuristic_nuf = min(self._heuristic_nuf_target(state, previous, demand), nuf_upper)
        if density_ratio <= leader.metering_activation_density_ratio:
            # 자유류에서는 N_UF=0 corner가 사실상 ramp 완전 폐쇄라 병적이다.
            # 격자는 넓게 유지하되, 0 유입 corner 대신 feasible release 근처를 하한으로 둔다.
            nuf_lower = min(nuf_upper, max(nuf_lower, 0.75 * heuristic_nuf))
        nuf_values = set(float(v) for v in np.linspace(bounds.nuf_lower, bounds.nuf_upper, n_nuf))
        # coarse grid가 성기더라도 혼잡 인식 target 주변 metering 후보를 반드시 포함한다.
        for scale in (0.75, 1.0, 1.25):
            nuf_values.add(float(np.clip(
                bounds.heuristic_nuf * scale,
                bounds.nuf_lower,
                bounds.nuf_upper,
            )))
        nuf_values = sorted(nuf_values)
        np_values = sorted(np_values)
        grid = [LeaderAction(float(np_), float(nuf)) for np_ in np_values for nuf in nuf_values]
        required = [
            LeaderAction(np_values[0], nuf_values[0]),
            LeaderAction(np_values[0], nuf_values[-1]),
            LeaderAction(np_values[-1], nuf_values[0]),
            LeaderAction(np_values[-1], nuf_values[-1]),
            LeaderAction(
                float(np.clip(0.0, np_lower, np_upper)),
                float(min(nuf_values, key=lambda value: abs(value - bounds.heuristic_nuf))),
            ),
        ]
        if previous is not None:
            previous_nuf = self._previous_nuf_target(previous)
            required.append(LeaderAction(
                float(np.clip(previous.N_P_star, np_lower, np_upper)),
                float(np.clip(previous_nuf, nuf_values[0], nuf_values[-1])),
            ))
        # 단순 Cartesian 앞부분 절단은 낮은 N_P 후보만 남긴다. 필수 corner/직전
        # action을 먼저 보존하고, 남은 budget은 정규화된 (N_P,N_UF) 공간의
        # farthest-point 순서로 채워 전체 후보 영역을 균형 있게 덮는다.
        budget = min(len(grid), count + 1)
        selected: List[LeaderAction] = []

        def add_unique(action: LeaderAction) -> None:
            if action not in selected and len(selected) < budget:
                selected.append(action)

        for action in required:
            add_unique(action)

        np_span = max(np_values[-1] - np_values[0], 1.0e-9)
        nuf_span = max(nuf_values[-1] - nuf_values[0], 1.0e-9)
        while len(selected) < budget:
            remaining = [action for action in grid if action not in selected]
            if not remaining:
                break

            def coverage_distance(action: LeaderAction) -> tuple[float, float, float]:
                if not selected:
                    return (float("inf"), action.N_P_star, action.N_UF_star)
                min_distance = min(
                    ((action.N_P_star - other.N_P_star) / np_span) ** 2
                    + ((action.N_UF_star - other.N_UF_star) / nuf_span) ** 2
                    for other in selected
                )
                return (float(min_distance), action.N_P_star, action.N_UF_star)

            add_unique(max(remaining, key=coverage_distance))
        return selected

    def refined_candidates(
        self,
        state: TrafficState,
        center: LeaderAction,
        previous: Optional[ControlAction] = None,
        demand: Optional[DemandStep] = None,
        forecast: Optional[list[DemandStep]] = None,
        count: Optional[int] = None,
    ) -> List[LeaderAction]:
        if forecast:
            demand = self._forecast_demand_summary(list(forecast))
        budget = max(5, int(count if count is not None else self.cfg.mpc.leader_refinement_candidate_count))
        bounds = self._candidate_bounds(state, previous, demand, forecast)
        n_np = max(3, int(round(np.sqrt(budget))))
        n_nuf = max(3, int(np.ceil(budget / n_np)))
        np_radius = max(
            float(self.cfg.mpc.leader_local_np_radius_veh),
            (bounds.np_upper - bounds.np_lower) / max(2.0 * (n_np - 1), 1.0),
        )
        nuf_radius = max(
            float(self.cfg.mpc.leader_local_nuf_radius_veh_h),
            (bounds.nuf_upper - bounds.nuf_lower) / max(2.0 * (n_nuf - 1), 1.0),
        )
        np_low = max(bounds.np_lower, center.N_P_star - np_radius)
        np_high = min(bounds.np_upper, center.N_P_star + np_radius)
        nuf_low = max(bounds.nuf_lower, center.N_UF_star - nuf_radius)
        nuf_high = min(bounds.nuf_upper, center.N_UF_star + nuf_radius)
        np_values = set(float(v) for v in np.linspace(np_low, np_high, n_np))
        nuf_values = set(float(v) for v in np.linspace(nuf_low, nuf_high, n_nuf))
        np_values.add(float(np.clip(center.N_P_star, bounds.np_lower, bounds.np_upper)))
        np_values.add(float(np.clip(0.0, bounds.np_lower, bounds.np_upper)))
        np_values.add(float(np.clip(bounds.movement_np_lower, bounds.np_lower, bounds.np_upper)))
        np_values.add(float(np.clip(bounds.movement_np_upper, bounds.np_lower, bounds.np_upper)))
        nuf_values.add(float(np.clip(center.N_UF_star, bounds.nuf_lower, bounds.nuf_upper)))
        nuf_values.add(float(np.clip(bounds.heuristic_nuf, bounds.nuf_lower, bounds.nuf_upper)))
        if previous is not None:
            np_values.add(float(np.clip(previous.N_P_star, bounds.np_lower, bounds.np_upper)))
            nuf_values.add(float(np.clip(self._previous_nuf_target(previous), bounds.nuf_lower, bounds.nuf_upper)))
        grid = [
            LeaderAction(float(np_), float(nuf))
            for np_ in sorted(np_values)
            for nuf in sorted(nuf_values)
        ]
        selected: List[LeaderAction] = []
        seen: set[LeaderAction] = set()

        def add(action: LeaderAction) -> None:
            if action in seen or len(selected) >= budget:
                return
            seen.add(action)
            selected.append(action)

        add(LeaderAction(
            float(np.clip(center.N_P_star, bounds.np_lower, bounds.np_upper)),
            float(np.clip(center.N_UF_star, bounds.nuf_lower, bounds.nuf_upper)),
        ))
        if previous is not None:
            add(LeaderAction(
                float(np.clip(previous.N_P_star, bounds.np_lower, bounds.np_upper)),
                float(np.clip(self._previous_nuf_target(previous), bounds.nuf_lower, bounds.nuf_upper)),
            ))
        for action in grid:
            add(action)
        return selected

    def candidate_bound_metadata(
        self,
        state: TrafficState,
        previous: Optional[ControlAction] = None,
        demand: Optional[DemandStep] = None,
        forecast: Optional[list[DemandStep]] = None,
    ) -> Dict[str, float]:
        bounds = self._candidate_bounds(state, previous, demand, forecast)
        return {
            "leader_np_bound_lower": bounds.np_lower,
            "leader_np_bound_upper": bounds.np_upper,
            "leader_nuf_bound_lower": bounds.nuf_lower,
            "leader_nuf_bound_upper": bounds.nuf_upper,
            "leader_nuf_heuristic_target": bounds.heuristic_nuf,
            "leader_np_movement_min_net_flow_veh_h": bounds.movement_min_net_flow_veh_h,
            "leader_np_movement_max_net_flow_veh_h": bounds.movement_max_net_flow_veh_h,
            "leader_np_movement_lower": bounds.movement_np_lower,
            "leader_np_movement_upper": bounds.movement_np_upper,
            "leader_np_movement_lower_active": float(bounds.movement_np_lower_active),
            "leader_np_movement_upper_active": float(bounds.movement_np_upper_active),
        }

    def _candidate_bounds(
        self,
        state: TrafficState,
        previous: Optional[ControlAction] = None,
        demand: Optional[DemandStep] = None,
        forecast: Optional[list[DemandStep]] = None,
    ) -> LeaderCandidateBounds:
        leader = self.cfg.leader
        forecast_steps = list(forecast) if forecast else []
        density_ratio = self._density_ratio(state)
        feasible_nuf = self._feasible_nuf_capacity(state, previous, demand)
        if density_ratio <= leader.metering_activation_density_ratio:
            feasible_nuf = max(feasible_nuf, self.cfg.network.total_ramp_capacity)
        nuf_lower = max(float(leader.N_UF_star_range[0]), self._minimum_nuf_target())
        nuf_upper = min(leader.N_UF_star_range[1], feasible_nuf)
        nuf_upper = max(nuf_lower, nuf_upper)
        heuristic_nuf = min(self._heuristic_nuf_target(state, previous, demand), nuf_upper)
        # fix 1: 저혼잡에서 N_UF* 하한을 heuristic의 일정비율로 강제하던 clamp. 기본 0.0(강제 없음)이라
        # leader가 낮은 자연 방출(PFO 동등 운전점)도 고를 수 있다. low_demand에서 강제 과방출 → urban
        # 침수 회귀를 막는다. (구버전 재현: uncongested_nuf_floor_frac=0.75)
        floor_frac = float(getattr(leader, "uncongested_nuf_floor_frac", 0.0))
        if floor_frac > 0.0 and density_ratio <= leader.metering_activation_density_ratio:
            nuf_lower = min(nuf_upper, max(nuf_lower, floor_frac * heuristic_nuf))

        base_np_lower, base_np_upper = self._np_candidate_bounds(state)
        movement_np_lower, movement_np_upper, min_net, max_net = self._movement_np_bounds(
            state,
            forecast_steps,
            nuf_upper,
        )
        # N_P_star는 보호영역 누적의 setpoint이지 한 step에서 반드시 도달 가능한 상태가 아니다.
        # movement reachability는 진단/anchor로만 쓰고, PFO식 낮은 누적 운전점도 탐색한다.
        # Proposed Stackelberg N_P_star is a direct net-inflow target [veh] over
        # the follower evaluation horizon. Bound it by movement-level
        # inflow-minus-outflow reachability, not by N_P_crit.
        np_lower = max(base_np_lower, movement_np_lower)
        np_upper = min(base_np_upper, movement_np_upper)
        if np_lower > np_upper:
            if base_np_upper < movement_np_lower:
                np_lower = np_upper = movement_np_lower
            elif base_np_lower > movement_np_upper:
                np_lower = np_upper = movement_np_upper
            else:
                midpoint = 0.5 * (movement_np_lower + movement_np_upper)
                np_lower = np_upper = float(np.clip(midpoint, base_np_lower, base_np_upper))
        return LeaderCandidateBounds(
            np_lower=float(np_lower),
            np_upper=float(np_upper),
            nuf_lower=float(nuf_lower),
            nuf_upper=float(nuf_upper),
            heuristic_nuf=float(heuristic_nuf),
            movement_min_net_flow_veh_h=float(min_net),
            movement_max_net_flow_veh_h=float(max_net),
            movement_np_lower=float(movement_np_lower),
            movement_np_upper=float(movement_np_upper),
            movement_np_lower_active=float(np_lower) > float(base_np_lower) + 1.0e-9,
            movement_np_upper_active=float(np_upper) < float(base_np_upper) - 1.0e-9,
        )

    def _np_target_horizon_h(self, forecast: list[DemandStep]) -> float:
        steps = forecast[: max(1, self.cfg.mpc.horizon_steps)] if forecast else []
        count = len(steps) if steps else max(1, int(self.cfg.mpc.horizon_steps))
        return float(max(self.cfg.simulation.T_c_h * count, 1.0e-9))

    def _movement_np_bounds(
        self,
        state: TrafficState,
        forecast: list[DemandStep],
        nuf_upper: float,
    ) -> tuple[float, float, float, float]:
        min_net, max_net = self._movement_net_flow_bounds(state, forecast, nuf_upper)
        flow_lower = min_net
        flow_upper = max_net
        horizon_h = self._np_target_horizon_h(forecast)
        np_lower = flow_lower * horizon_h
        np_upper = flow_upper * horizon_h
        return float(np_lower), float(np_upper), float(min_net), float(max_net)

    def _movement_net_flow_bounds(
        self,
        state: TrafficState,
        forecast: list[DemandStep],
        nuf_upper: float,
    ) -> tuple[float, float]:
        # 도달 가능 net-inflow는 movement 용량이 아니라 실제 서비스 가능량(큐+도착)으로
        # 제한된다. 종전 capacity envelope(flow_max 합)는 수천 veh로 과대해 N_P_star
        # 탐색이 도달 불가 영역의 saturation 평원으로 퇴화했다(2026-06-22 진단).
        net = self.cfg.network
        flow_max = float(net.green_max) / max(float(net.cycle_length), 1.0e-9) * float(net.movement_capacity_veh_h)
        horizon_h = self._np_target_horizon_h(forecast)
        # 후보 범위(feasible set)는 현재 state+첫-스텝 수요로 정해 forecast-미래에 무관하게 둔다
        # (forecast 민감도는 후보 평가에서 다룬다 — leader 후보 설계 계약). 첫-스텝 도착률을
        # np 목표 horizon으로 스케일해 큐와 합산한다.
        dt_h = max(float(self.cfg.simulation.T_c_h), 1.0e-9)
        first_step = list(forecast)[:1]
        step_arrivals = movement_forecast_arrivals_veh(self.cfg, first_step)
        horizon_scale = horizon_h / dt_h
        arrivals = {movement: value * horizon_scale for movement, value in step_arrivals.items()}
        total_ramp_cap = max(float(net.total_ramp_capacity), 1.0e-9)
        ramp_counts: Dict[str, int] = {}
        for spec in net.urban_movements.values():
            if str(spec.get("kind", "")) != "on_ramp":
                continue
            ramp = str(spec.get("ramp", ""))
            if ramp:
                ramp_counts[ramp] = ramp_counts.get(ramp, 0) + 1
        inflow_servable = 0.0
        outflow_servable = 0.0
        for movement, spec in net.urban_movements.items():
            kind = str(spec.get("kind", ""))
            if kind not in {"boundary_in", "off_ramp", "boundary_out", "on_ramp"}:
                continue
            cap_flow = flow_max
            if kind == "on_ramp":
                ramp = str(spec.get("ramp", ""))
                share = float(net.ramp_capacity_veh_h.get(ramp, 0.0)) / total_ramp_cap
                cap_flow = float(np.clip(
                    nuf_upper * share / max(ramp_counts.get(ramp, 1), 1),
                    0.0,
                    flow_max,
                ))
            available_veh = max(0.0, state.urban_movement_queue.get(movement, 0.0)) + max(
                0.0, arrivals.get(movement, 0.0)
            )
            servable_flow = min(available_veh / horizon_h, cap_flow)
            if kind in {"boundary_in", "off_ramp"}:
                inflow_servable += servable_flow
            else:
                outflow_servable += servable_flow
        # 디커플 over-approx: 달성 net-inflow ∈ [−Σoutflow_servable, +Σinflow_servable].
        # 달성집합을 배제하지 않으면서 capacity envelope보다 압도적으로 타이트하다.
        return float(-outflow_servable), float(inflow_servable)

    def _previous_nuf_target(self, previous: ControlAction) -> float:
        """Interpret no-control ramp metering as full N_UF release for leader grids."""
        net = self.cfg.network
        previous_target = float(previous.N_UF_star)
        if previous_target > 1.0e-9:
            return previous_target
        release = sum(
            float(previous.ramp_metering.get(ramp, 0.0))
            for ramp in net.ramps
        )
        if release >= 0.95 * float(net.total_ramp_capacity):
            return float(net.total_ramp_capacity)
        return previous_target

    def _minimum_nuf_target(self) -> float:
        net = self.cfg.network
        min_ratio = float(self.cfg.freeway_follower.ramp_metering_rate_min)
        return float(sum(
            max(0.0, min_ratio * float(net.ramp_capacity_veh_h[ramp]))
            for ramp in net.ramps
        ))

    def _np_candidate_bounds(self, state: TrafficState) -> tuple[float, float]:
        """Calibration된 n_P_crit 주변으로 leader의 도시 누적 목표 후보를 제한한다."""
        leader = self.cfg.leader
        range_lower, range_upper = sorted(float(v) for v in leader.N_P_star_range[:2])
        return float(range_lower), float(range_upper)

    def _ramp_merge_index(self, ramp: str, n_segments: int) -> int:
        configured = getattr(self.cfg.network, "ramp_merge_segment_index", {})
        if isinstance(configured, dict) and ramp in configured:
            return int(np.clip(float(configured[ramp]), 0.0, float(n_segments - 1)))
        return n_segments // 2

    def _feasible_nuf_capacity(
        self,
        state: TrafficState,
        previous: Optional[ControlAction] = None,
        demand: Optional[DemandStep] = None,
    ) -> float:
        """현재 경계 상태에서 첫 T_f 동안 추적 가능한 ramp 유입 상한(veh/h)을 계산한다."""
        net = self.cfg.network
        sim = self.cfg.simulation
        control = previous or ControlAction.fixed(self.cfg)
        if demand is not None:
            green_inflow = estimate_onramp_green_release_flows(
                state.copy(),
                control,
                demand,
                self.cfg,
                interval_h=sim.T_f_h,
            )
            cap_factor = getattr(demand, "incident_capacity_factor", 1.0)
        else:
            green_inflow = {ramp: 0.0 for ramp in net.ramps}
            cap_factor = 1.0
        q_cap = net.freeway_capacity_veh_h * cap_factor
        feasible = 0.0
        for ramp in net.ramps:
            link = net.ramp_to_freeway[ramp]
            merge_idx = self._ramp_merge_index(ramp, len(state.freeway_density[link]))
            rho_merge = state.freeway_density[link][merge_idx]
            receiving_factor = float(np.clip(
                (net.rho_max - rho_merge) / max(net.rho_max - net.rho_crit, 1.0e-9),
                0.0,
                1.0,
            ))
            density_headroom = max(0.0, net.rho_crit - rho_merge)
            headroom_flow = (
                density_headroom
                * net.freeway_segment_length_km
                * net.freeway_lanes
                / max(sim.T_f_h, 1.0e-9)
            )
            available = (
                state.ramp_queue.get(ramp, 0.0) / max(sim.T_f_h, 1.0e-9)
                + green_inflow.get(ramp, 0.0)
            )
            feasible += min(
                net.ramp_capacity_veh_h[ramp],
                max(0.0, available),
                q_cap * receiving_factor,
                max(0.0, headroom_flow),
            )
        return float(max(0.0, feasible * self.cfg.leader.N_UF_feasible_margin))

    def _heuristic_nuf_target(
        self,
        state: TrafficState,
        previous: Optional[ControlAction] = None,
        demand: Optional[DemandStep] = None,
    ) -> float:
        net = self.cfg.network
        lc = self.cfg.leader
        density_ratio = self._density_ratio(state)
        queue_pressure = self._ramp_queue_pressure(state)
        feasible = self._feasible_nuf_capacity(state, previous, demand)
        if density_ratio <= lc.metering_activation_density_ratio:
            frac = 1.0
        else:
            congestion = min(1.0, max(0.0, density_ratio - lc.metering_activation_density_ratio))
            frac = 1.0 - 0.18 * congestion + 0.25 * queue_pressure
        frac = float(np.clip(frac, 0.82, 1.0))
        return min(frac * net.total_ramp_capacity, feasible)

    def _density_ratio(self, state: TrafficState) -> float:
        values = [
            rho / max(self.cfg.network.rho_crit, 1.0e-9)
            for rhos in state.freeway_density.values()
            for rho in rhos
        ]
        return float(np.mean(values)) if values else 0.0

    def _ramp_queue_pressure(self, state: TrafficState) -> float:
        if not state.ramp_queue:
            return 0.0
        return float(np.mean([
            min(1.0, q / max(self.cfg.network.ramp_queue_max_veh, 1.0e-9))
            for q in state.ramp_queue.values()
        ]))

    def _state_accumulation_base(self, states: Iterable[TrafficState]) -> tuple[float, float]:
        net = self.cfg.network
        exclude_boundary = self.cfg.leader.state_accumulation_exclude_boundary_legs
        base = 0.0
        excluded = 0.0
        for state in states:
            base += state.total_freeway_vehicles(net)
            # off-ramp 램프 storage 재귀속(design 2026-06-17): urban total에서 빠진 램프
            # storage를 freeway 쪽 base에 더한다(전체 base 보존 + freeway 귀속 일관).
            base += state.off_ramp_storage_occupancy_veh(net)
            base += state.objective_urban_vehicles(net, exclude_boundary)
            if exclude_boundary:
                excluded += state.boundary_leg_vehicles(net)
        return float(base), float(excluded)

    def _density_penalty(self, states: Iterable[TrafficState]) -> tuple[float, float]:
        """Spec 4.2 freeway density 초과 penalty.

        기본은 nominal lane 수를 쓰되, lane-drop으로 lambda_eff가 실제로 nominal과
        달라진 segment에서만 effective lane weight를 사용한다.
        """
        net = self.cfg.network
        use_effective = self.cfg.leader.use_effective_lanes_for_density_penalty
        penalty = 0.0
        effective_weight_count = 0.0
        for state in states:
            state.ensure_freeway_lane_profile(net)
            for link, values in state.freeway_density.items():
                effective_lanes = state.freeway_effective_lanes.get(link, [])
                for idx, rho in enumerate(values):
                    lane_weight = net.freeway_lanes
                    if use_effective and idx < len(effective_lanes):
                        candidate = float(effective_lanes[idx])
                        if abs(candidate - net.freeway_lanes) > 1.0e-9:
                            lane_weight = candidate
                            effective_weight_count += 1.0
                    penalty += (
                        net.freeway_segment_length_km
                        * lane_weight
                        * max(0.0, rho - net.rho_crit)
                    )
        return float(penalty), float(effective_weight_count)

    def _non_convergence_penalty(
        self,
        nash_converged: bool,
        nash_residual_objective: float = 0.0,
        nash_residual_control: float = 0.0,
    ) -> tuple[float, float, float]:
        if nash_converged:
            return 0.0, 0.0, 0.0
        lc = self.cfg.leader
        obj_component = max(0.0, float(nash_residual_objective)) / max(
            lc.non_convergence_objective_residual_scale,
            1.0e-9,
        )
        control_component = max(0.0, float(nash_residual_control)) / max(
            lc.non_convergence_control_residual_scale,
            1.0e-9,
        )
        penalty = lc.non_convergence_penalty * (obj_component + control_component)
        return float(penalty), float(obj_component), float(control_component)

    def _urban_halfcap_excess(self, states: Iterable[TrafficState]) -> tuple[float, float, float]:
        net = self.cfg.network
        threshold = float(self.cfg.leader.mfd_storage_threshold_ratio)
        movement_excess = 0.0
        link_excess = 0.0
        off_ramp_storage_links = set(net.off_ramp_storage_link.values())
        for state in states:
            for movement, spec in net.urban_movements.items():
                kind = str(spec.get("kind", ""))
                # 2026-06-30 실험: internal-only 0.5-cap. 경계 movement(boundary_in/out)는 제외한다 —
                # gating이 차를 경계에 잡아두는 건 *의도된* 비용이라 base TTS가 보면 충분하고, 0.5-cap은
                # *내부* oversaturation만 막아야 gating이 페널티를 줄이는 방향이 된다(저수요 admit은 TTS가 담당).
                if kind in {"boundary_in", "boundary_out"}:
                    continue
                capacity = movement_storage_capacity(self.cfg, movement, spec)
                capacity = max(float(capacity), 1.0e-9)
                queue = max(0.0, state.urban_movement_queue.get(movement, 0.0))
                movement_excess += max(0.0, queue - threshold * capacity)
            for link, capacity_value in net.urban_link_storage_veh.items():
                if link in off_ramp_storage_links:
                    continue
                capacity = max(float(capacity_value), 1.0e-9)
                occupancy = max(0.0, capacity - state.urban_link_storage.get(link, capacity))
                link_excess += max(0.0, occupancy - threshold * capacity)
        return float(movement_excess + link_excess), float(movement_excess), float(link_excess)

    def objective_terms(
        self,
        predicted_states: Iterable[TrafficState],
        action: ControlAction,
        previous: Optional[ControlAction],
        follower_objective: float,
        nash_converged: bool,
        nash_residual_objective: float = 0.0,
        nash_residual_control: float = 0.0,
    ) -> Dict[str, float]:
        net = self.cfg.network
        lc = self.cfg.leader
        states = list(predicted_states)
        state_base, boundary_excluded = self._state_accumulation_base(states)
        if lc.objective_mode == "follower_ttt":
            base = float(follower_objective)
            accumulation_penalty_scale = self.cfg.simulation.T_c_h
        else:
            base = state_base
            accumulation_penalty_scale = 1.0
        target_penalty = 0.0
        mfd_storage_excess_veh = 0.0
        mfd_movement_excess_veh = 0.0
        mfd_link_excess_veh = 0.0
        mfd_mode = lc.mfd_penalty_mode
        use_protected_exceed = mfd_mode in {"protected_exceed", "combined"}
        use_all_urban_halfcap = mfd_mode in {"all_urban_halfcap", "combined"}
        boundary_in_queue_veh = 0.0
        for s in states:
            n_p = s.protected_accumulation_veh(net)
            # follower_ttt 모드의 base는 veh*h이므로 accumulation 초과 항도 T_c_h로 맞춘다.
            if use_protected_exceed:
                target_penalty += lc.w_P * max(0.0, n_p - lc.N_P_crit_veh) * accumulation_penalty_scale
            # boundary_in 큐는 최종 Total TTT에 포함되므로 leader TTS 목적함수에도 반영한다.
            boundary_in_queue_veh += s.boundary_in_queue_vehicles(net)
        if use_all_urban_halfcap:
            (
                mfd_storage_excess_veh,
                mfd_movement_excess_veh,
                mfd_link_excess_veh,
            ) = self._urban_halfcap_excess(states)
        mfd_storage_penalty = (
            lc.mfd_storage_weight * mfd_storage_excess_veh * accumulation_penalty_scale
        )
        boundary_in_queue_penalty = (
            lc.w_boundary_in * boundary_in_queue_veh * accumulation_penalty_scale
        )
        density_excess, density_effective_count = self._density_penalty(states)
        density_penalty = lc.w_F * density_excess * accumulation_penalty_scale
        # Leader action smoothness is diagnostic-disabled. Medium-demand
        # injection diagnostics showed it can dominate lower rollout TTT
        # candidates and keep the leader pinned to the previous target.
        smooth = 0.0
        conv, obj_component, control_component = self._non_convergence_penalty(
            nash_converged,
            nash_residual_objective,
            nash_residual_control,
        )
        # Boundary-in queues are priced because final Total TTT counts them.
        # Non-convergence remains diagnostic-only per Spec 4.6.
        total = (
            base
            + target_penalty
            + mfd_storage_penalty
            + boundary_in_queue_penalty
            + density_penalty
        )
        return {
            "leader_base_accumulation": float(state_base),
            "leader_objective_base": float(base),
            "leader_state_accumulation_base": float(state_base),
            "leader_follower_ttt_base": float(follower_objective),
            "leader_boundary_leg_excluded_veh": float(boundary_excluded),
            "leader_target_penalty": float(target_penalty),
            "leader_mfd_penalty_mode_protected_exceed": float(use_protected_exceed),
            "leader_mfd_penalty_mode_all_urban_halfcap": float(use_all_urban_halfcap),
            "leader_mfd_storage_threshold_ratio": float(lc.mfd_storage_threshold_ratio),
            "leader_mfd_boundary_queue_capacity_veh": float(lc.mfd_boundary_queue_capacity_veh),
            "leader_mfd_storage_excess_veh": float(mfd_storage_excess_veh),
            "leader_mfd_movement_excess_veh": float(mfd_movement_excess_veh),
            "leader_mfd_link_excess_veh": float(mfd_link_excess_veh),
            "leader_mfd_storage_penalty": float(mfd_storage_penalty),
            "leader_boundary_in_queue_veh": float(boundary_in_queue_veh),
            "leader_boundary_in_queue_penalty": float(boundary_in_queue_penalty),
            "leader_density_excess": float(density_excess),
            "leader_density_penalty": float(density_penalty),
            "leader_density_effective_lane_weight_count": float(density_effective_count),
            "leader_smoothness_penalty": float(smooth),
            "leader_nonconvergence_penalty": float(conv),
            "leader_nonconvergence_obj_residual_component": float(obj_component),
            "leader_nonconvergence_control_residual_component": float(control_component),
            "leader_total_objective": float(total),
        }

    def objective(
        self,
        predicted_states: Iterable[TrafficState],
        action: ControlAction,
        previous: Optional[ControlAction],
        follower_objective: float,
        nash_converged: bool,
        nash_residual_objective: float = 0.0,
        nash_residual_control: float = 0.0,
    ) -> float:
        terms = self.objective_terms(
            predicted_states,
            action,
            previous,
            follower_objective,
            nash_converged,
            nash_residual_objective,
            nash_residual_control,
        )
        return float(terms["leader_total_objective"])


def leader_metadata(actions: Iterable[LeaderAction]) -> Dict[str, float]:
    actions = list(actions)
    return {
        "leader_candidate_count": float(len(actions)),
        "N_P_min": min((a.N_P_star for a in actions), default=0.0),
        "N_P_max": max((a.N_P_star for a in actions), default=0.0),
        "N_UF_min": min((a.N_UF_star for a in actions), default=0.0),
        "N_UF_max": max((a.N_UF_star for a in actions), default=0.0),
    }
