from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional

import numpy as np

from src.controllers.relaxed_quantization import (
    accumulate_repair_diagnostics,
    queue_pressure_green_target,
    repair_green_pair,
)
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
    movement_balance_summary,
    movement_specs,
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
        self._repair_diagnostics: Dict[str, float] = {}

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
            if self.cfg.mpc.relaxed_quantized_controls:
                # Spec 17.5 proposed follower relaxed: allocation/pressure로 얻은 연속 green도
                # plant 적용 전 동일한 quantized repair를 거친다.
                repaired = repair_green_pair(p1, self.cfg)
                accumulate_repair_diagnostics(self._repair_diagnostics, green=repaired)
                p1, p2 = repaired.p1, repaired.p2
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

    def _search_green_times(
        self,
        state: TrafficState,
        previous: Optional[ControlAction],
        pressure: Mapping[str, float],
    ) -> tuple[Dict[str, float], float]:
        """P-FO(spec 16.7, 2026-06-13 재정의) green 자유 탐색 — allocation 기준점 없음.

        신호별 후보 p1 ∈ linspace(green_min, green_max, 7)를 경량 큐 모델
        (서비스율 = green/cycle × Σ포화유율 — plant의 cycle 평균과 동일 회계)로
        horizon 동안 굴려 잔여 큐 + green 변화 패널티가 최소인 split을 고른다.
        coupling 정보는 freeway 압력으로만 들어온다(off-ramp 방출 phase 큐 가중)."""
        net = self.cfg.network
        specs = movement_specs(self.cfg)
        horizon = max(1, self.cfg.mpc.horizon_steps)
        dt_h = self.cfg.simulation.T_c_h
        total = net.effective_green_total
        smooth_w = self.cfg.urban_follower.green_smoothness_weight
        green: Dict[str, float] = {}
        objective = 0.0
        for signal in net.signals:
            phase_movements = {
                pid: [m for m, spec in specs.items() if spec.get("phase") == f"{signal}_{pid}"]
                for pid in ("p1", "p2")
            }
            q0 = {
                pid: sum(
                    max(0.0, state.urban_movement_queue.get(m, 0.0))
                    for m in phase_movements[pid]
                )
                for pid in ("p1", "p2")
            }
            for pid in ("p1", "p2"):
                # freeway 압력이 높으면 off-ramp storage를 비우는 phase를 우선한다
                # (full follower의 _green_times와 같은 coupling 경로).
                if any(specs[m].get("kind") == "off_ramp" for m in phase_movements[pid]):
                    q0[pid] += float(pressure.get("total_pressure", 0.0)) * net.ramp_queue_max_veh
            sat = {
                pid: max(len(phase_movements[pid]) * net.movement_capacity_veh_h, 1.0e-9)
                for pid in ("p1", "p2")
            }
            prev_p1 = (
                float(previous.green_times.get(f"{signal}_p1", total / 2.0))
                if previous else total / 2.0
            )
            if self.cfg.mpc.relaxed_quantized_controls:
                # Spec 17.5 P-FO relaxed: grid search를 pressure split 하나로 대체하고
                # 공통 repair가 cycle sum과 green bound를 보장한다.
                repaired = repair_green_pair(
                    queue_pressure_green_target(q0["p1"], q0["p2"], self.cfg),
                    self.cfg,
                )
                accumulate_repair_diagnostics(self._repair_diagnostics, green=repaired)
                q = dict(q0)
                cost = 0.0
                for _ in range(horizon):
                    for pid, g in (("p1", repaired.p1), ("p2", repaired.p2)):
                        service = (g / max(net.cycle_length, 1.0e-9)) * sat[pid] * dt_h
                        q[pid] = max(0.0, q[pid] - service)
                    cost += (q["p1"] + q["p2"]) * dt_h
                cost += smooth_w * abs(repaired.p1 - prev_p1)
                green[f"{signal}_p1"] = repaired.p1
                green[f"{signal}_p2"] = repaired.p2
                objective += cost
                continue
            best_p1, best_cost = prev_p1, float("inf")
            for p1 in np.linspace(net.green_min, net.green_max, 7):
                p2 = total - p1
                if p2 < net.green_min - 1.0e-9 or p2 > net.green_max + 1.0e-9:
                    continue
                q = dict(q0)
                cost = 0.0
                for _ in range(horizon):
                    for pid, g in (("p1", p1), ("p2", p2)):
                        service = (g / max(net.cycle_length, 1.0e-9)) * sat[pid] * dt_h
                        q[pid] = max(0.0, q[pid] - service)
                    cost += (q["p1"] + q["p2"]) * dt_h
                cost += smooth_w * abs(p1 - prev_p1)
                if cost < best_cost:
                    best_cost, best_p1 = cost, float(p1)
            green[f"{signal}_p1"] = float(best_p1)
            green[f"{signal}_p2"] = float(total - best_p1)
            objective += best_cost
        return green, float(objective)

    def _offsets(
        self,
        state: TrafficState,
        previous: Optional[ControlAction],
        green_times: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """corridor 진행(green wave) offset — urban 속도·실제 leg 인접 기반.

        plant가 cycle 위상을 모델링하므로(`_phase_green_fraction`), 인접 신호의
        해당 축 phase 시작이 링크 통과시간(t_link = storage×차길이/urban 속도 ≈95s)
        만큼 어긋나게 offset을 정한다. 진행 방향은 회랑별 양방향 부하(링크 점유 +
        하류 접근 대기열)로 매 interval 선택 — 상태에 따라 신호별·시간별로 움직인다.
        회랑: 상단 A–B–C(EW, p2 정렬), 수직 A–D(NS, p1 정렬), 하단 D–(E)–F(EW,
        p2 정렬, E는 비통제라 2링크 통과시간). 앵커는 A(이전 offset 유지)."""
        net = self.cfg.network
        uc = self.cfg.urban_follower
        cycle = max(net.cycle_length, 1.0e-9)
        prev = previous.offsets if previous else {}
        green = green_times or {}
        default_green = net.effective_green_total / 2.0
        link_len_km = float(net.grid_link_storage_veh) * net.urban_avg_vehicle_length_m / 1000.0
        t_link = link_len_km / max(net.urban_avg_speed_km_h, 1.0e-9) * 3600.0

        def p2_start(signal: str) -> float:
            return float(green.get(f"{signal}_p1", default_green)) + net.lost_time / 2.0

        def occ(link: str) -> float:
            cap = net.urban_link_storage_veh.get(link, 0.0)
            return max(0.0, cap - state.urban_link_storage.get(link, cap))

        def queue_mass(signal: str, approach: str) -> float:
            return sum(
                max(0.0, state.urban_movement_queue.get(movement, 0.0))
                for movement, spec in net.urban_movements.items()
                if spec.get("intersection") == signal and spec.get("approach") == approach
            )

        # 방향 선택: 회랑별 양방향 부하 비교(링크 in-transit 점유 + 하류 접근 대기열).
        east_top = occ("A_to_B") + occ("B_to_C") + queue_mass("B", "W") + queue_mass("C", "W")
        west_top = occ("B_to_A") + occ("C_to_B") + queue_mass("B", "E") + queue_mass("A", "E")
        south_ad = occ("A_to_D") + queue_mass("D", "N")
        north_ad = occ("D_to_A") + queue_mass("A", "S")
        east_bot = occ("D_to_E") + occ("E_to_F") + queue_mass("F", "W")
        west_bot = occ("F_to_E") + occ("E_to_D") + queue_mass("D", "E")

        desired: Dict[str, float] = {"A": float(prev.get("A", 0.0))}
        # 상단 EW: 같은 축 phase(p2) 시작이 진행 방향으로 t_link씩 늦게 오게.
        top_sign = 1.0 if east_top >= west_top else -1.0
        desired["B"] = desired["A"] + top_sign * t_link + p2_start("A") - p2_start("B")
        desired["C"] = desired["B"] + top_sign * t_link + p2_start("B") - p2_start("C")
        # 수직 A–D: NS축 phase(p1)는 cycle 시작이라 보정항 없음.
        ad_sign = 1.0 if south_ad >= north_ad else -1.0
        desired["D"] = desired["A"] + ad_sign * t_link
        # 하단 D–F: E 비통제 통과라 2링크 통과시간.
        bot_sign = 1.0 if east_bot >= west_bot else -1.0
        desired["F"] = desired["D"] + bot_sign * 2.0 * t_link + p2_start("D") - p2_start("F")

        offsets: Dict[str, float] = {}
        for signal in net.signals:
            target = float(desired.get(signal, prev.get(signal, 0.0))) % cycle
            anchor = float(prev.get(signal, 0.0))
            # cycle 래핑을 고려한 최단 이동을 max_offset_step으로 제한한다.
            delta = (target - anchor + 0.5 * cycle) % cycle - 0.5 * cycle
            delta = float(np.clip(delta, -uc.max_offset_step, uc.max_offset_step))
            offsets[signal] = float((anchor + delta) % cycle)
        return offsets

    def _allocation(
        self,
        state: TrafficState,
        leader: Optional[LeaderAction],
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
        leader: Optional[LeaderAction],
        demand: DemandStep,
        freeway_response: object | None = None,
        previous_control: Optional[ControlAction] = None,
        allocation_plan: Optional[AllocationResult] = None,
    ) -> UrbanFollowerResult:
        ensure_urban_state(state, self.cfg)
        self._repair_diagnostics = {}
        pressure = self._freeway_pressure(freeway_response)
        if leader is None:
            # P-FO(spec 16.7, 2026-06-13 재정의): allocation module을 호출하지 않는다 —
            # green 자유탐색 + offset만 결정하고 movement service는 plant 포화유율
            # fallback(빈 allocation)에 맡긴다. 숨은 전역 target 없음.
            return self._solve_leaderless(state, pressure, previous_control)
        plan = allocation_plan or self.allocation_module.solve(state, leader)
        green = self._green_times(state, previous_control, freeway_response, plan)
        offsets = self._offsets(state, previous_control, green)
        allocation, residual, target_net_inflow, allocation_metrics = self._allocation(
            state,
            leader,
            freeway_response,
            green,
            plan,
        )
        balance = movement_balance_summary(
            state,
            self.cfg,
            saturation_fraction=self.cfg.evaluation.boundary_degenerate_saturation_fraction,
            degenerate_ratio=self.cfg.evaluation.boundary_degenerate_ratio,
            eps=self.cfg.evaluation.eps,
        )
        b_in = balance["B_in"]
        b_out = balance["B_out"]
        metrics = {
            "B_in": b_in,
            "B_out": b_out,
            "freeway_response_used": pressure["used"],
            "freeway_metering_pressure": pressure["metering_pressure"],
            "freeway_queue_pressure": pressure["queue_pressure"],
            "freeway_density_pressure": pressure["density_pressure"],
            "freeway_receiving_pressure": pressure["receiving_pressure"],
            "freeway_total_pressure": pressure["total_pressure"],
            "urban_accumulation_veh": float(state.protected_accumulation_veh(self.cfg.network)),
            "urban_accumulation_target_veh": float(leader.N_P_star) if leader is not None else 0.0,
            "urban_accumulation_error_veh": (
                float(state.protected_accumulation_veh(self.cfg.network) - leader.N_P_star)
                if leader is not None else 0.0
            ),
            "urban_net_inflow_target_veh_h": float(target_net_inflow),
        }
        metrics.update(allocation_metrics)
        metrics.update(balance)
        metrics.update(self._repair_diagnostics)
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

    def _solve_leaderless(
        self,
        state: TrafficState,
        pressure: Mapping[str, float],
        previous_control: Optional[ControlAction],
    ) -> UrbanFollowerResult:
        """PROPOSED-FOLLOWERS-ONLY — green 자유탐색 + offset, allocation 비제어."""
        green, search_cost = self._search_green_times(state, previous_control, pressure)
        offsets = self._offsets(state, previous_control, green)
        balance = movement_balance_summary(
            state,
            self.cfg,
            saturation_fraction=self.cfg.evaluation.boundary_degenerate_saturation_fraction,
            degenerate_ratio=self.cfg.evaluation.boundary_degenerate_ratio,
            eps=self.cfg.evaluation.eps,
        )
        metrics = {
            "B_in": balance["B_in"],
            "B_out": balance["B_out"],
            "allocation_module_active": 0.0,
            "freeway_response_used": pressure["used"],
            "freeway_total_pressure": pressure["total_pressure"],
            "urban_accumulation_veh": float(state.protected_accumulation_veh(self.cfg.network)),
            "urban_accumulation_target_veh": 0.0,
            "urban_accumulation_error_veh": 0.0,
            "urban_net_inflow_target_veh_h": 0.0,
        }
        metrics.update(balance)
        metrics.update(self._repair_diagnostics)
        metrics.update(boundary_indices(state.boundary_queue.values(), self.cfg.network.boundary_queue_max_veh))
        return UrbanFollowerResult(
            green_times=green,
            offsets=offsets,
            inflow_outflow_allocation={},
            objective_value=float(search_cost),
            infeasibility={"net_inflow_residual": 0.0},
            metrics=metrics,
        )
