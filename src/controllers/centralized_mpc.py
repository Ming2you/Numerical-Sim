# budgeted centralized MPC — WU-CC-F(green+VSL)와 PROPOSED-CENTRALIZED(full authority) 공용 (spec 16.6/16.9)
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import numpy as np

from src.controllers.relaxed_quantization import (
    accumulate_repair_diagnostics,
    repair_green_pair,
    repair_vsl_value,
)
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import movement_specs


@dataclass
class CentralizedDecisionInfo:
    control: ControlAction
    objective: float
    solver_evaluations: int
    converged: bool
    computation_time_sec: float


def _wu_fixed_base(cfg: ExperimentConfig) -> ControlAction:
    from src.controllers.wu_distributed import _wu_fixed_control

    return _wu_fixed_control(cfg)


class CentralizedMPC:
    """단일 system objective를 coupled plant 예측으로 직접 최적화하는 수치 참조 controller.

    spec 16.9: leader/agent/Nash 없음. solver는 외부 의존성 없는 seeded random
    perturbation search(warm start + 탐색 반경 감쇠) — 보장된 전역 최적이 아니라
    "동일 budget의 centralized numerical reference"로 보고한다(spec 16.13 비교 규칙).
    authority:
      - mode='wu':       green p1(신호 5) + VSL(링크 2). offset 고정, metering=용량,
                         allocation 미사용 — Wu authority(spec 16.6).
      - mode='proposed': green p1 + VSL + offset + ramp metering + 게이트 서비스 분율.
                         allocation은 게이트 단위 service level로 매개변수화(β 비례 배분,
                         fidelity matrix에 차원 축소 근사로 기록).
    """

    def __init__(self, cfg: ExperimentConfig, mode: str):
        if mode not in {"wu", "proposed"}:
            raise ValueError(f"Unknown centralized mode: {mode}")
        self.cfg = cfg
        self.mode = mode
        self.previous_control: Optional[ControlAction] = None
        self._specs = movement_specs(cfg)
        net = cfg.network
        self._gates = list(net.boundary_in_links)
        # 게이트별 boundary_in movement 목록(β 비례 allocation 전개용).
        self._gate_movements = {
            gate: [m for m, s in self._specs.items() if s.get("kind") == "boundary_in" and s.get("origin") == gate]
            for gate in self._gates
        }
        self._flow_max = float(net.green_max) / max(net.cycle_length, 1e-9) * float(net.movement_capacity_veh_h)

    # ---------- 제어벡터 <-> ControlAction ----------

    def _vector_bounds(self, previous: ControlAction) -> tuple[np.ndarray, np.ndarray, list[str]]:
        net = self.cfg.network
        names: list[str] = []
        lower: list[float] = []
        upper: list[float] = []
        for signal in net.signals:
            names.append(f"g_{signal}")
            lower.append(net.green_min)
            upper.append(net.green_max)
        for link in net.freeway_links:
            prev = float(previous.vsl.get(link, max(self.cfg.freeway_follower.vsl_set)))
            names.append(f"v_{link}")
            lower.append(max(min(self.cfg.freeway_follower.vsl_set), prev - self.cfg.freeway_follower.max_vsl_step))
            upper.append(min(max(self.cfg.freeway_follower.vsl_set), prev + self.cfg.freeway_follower.max_vsl_step))
        if self.mode == "proposed":
            for signal in net.signals:
                prev = float(previous.offsets.get(signal, 0.0))
                names.append(f"o_{signal}")
                # offset은 이전값 ±max_offset_step(랩어라운드는 적용 시 mod 처리).
                lower.append(prev - self.cfg.urban_follower.max_offset_step)
                upper.append(prev + self.cfg.urban_follower.max_offset_step)
            for ramp in net.ramps:
                names.append(f"m_{ramp}")
                lower.append(0.0)
                upper.append(net.ramp_capacity_veh_h[ramp])
            for gate in self._gates:
                names.append(f"a_{gate}")
                lower.append(0.0)
                upper.append(1.0)
        return np.asarray(lower, dtype=float), np.asarray(upper, dtype=float), names

    def _vector_from_control(self, control: ControlAction, names: list[str]) -> np.ndarray:
        net = self.cfg.network
        values = []
        for name in names:
            kind, _, key = name.partition("_")
            if kind == "g":
                values.append(float(control.green_times.get(f"{key}_p1", net.effective_green_total / 2.0)))
            elif kind == "v":
                values.append(float(control.vsl.get(key, max(self.cfg.freeway_follower.vsl_set))))
            elif kind == "o":
                values.append(float(control.offsets.get(key, 0.0)))
            elif kind == "m":
                values.append(float(control.ramp_metering.get(key, net.ramp_capacity_veh_h[key])))
            else:  # a_<gate>: 게이트 서비스 분율 — allocation에서 역산(없으면 1.0).
                movements = self._gate_movements.get(key, [])
                if movements and control.inflow_outflow_allocation:
                    mean_alloc = float(np.mean([
                        control.inflow_outflow_allocation.get(m, self._flow_max) for m in movements
                    ]))
                    values.append(float(np.clip(mean_alloc / max(self._flow_max, 1e-9), 0.0, 1.0)))
                else:
                    values.append(1.0)
        return np.asarray(values, dtype=float)

    def _control_from_vector(
        self,
        vec: np.ndarray,
        names: list[str],
        previous: Optional[ControlAction] = None,
    ) -> ControlAction:
        net = self.cfg.network
        base = _wu_fixed_base(self.cfg)
        control = ControlAction(
            ramp_metering=dict(base.ramp_metering),
            vsl=dict(base.vsl),
            green_times=dict(base.green_times),
            offsets=dict(base.offsets),
            inflow_outflow_allocation={},
        )
        vsl_set = sorted(float(v) for v in self.cfg.freeway_follower.vsl_set)
        for value, name in zip(vec, names):
            kind, _, key = name.partition("_")
            if kind == "g":
                p1 = float(np.clip(value, net.green_min, net.green_max))
                p2 = net.effective_green_total - p1
                # cycle 합 제약: p2도 [min,max] 안으로 사영.
                if p2 < net.green_min:
                    p2 = net.green_min
                    p1 = net.effective_green_total - p2
                if p2 > net.green_max:
                    p2 = net.green_max
                    p1 = net.effective_green_total - p2
                if self.cfg.mpc.relaxed_quantized_controls:
                    # Spec 17.5 centralized relaxed: decoded continuous green을 공통 repair로 재투영한다.
                    repaired = repair_green_pair(float(value), self.cfg)
                    accumulate_repair_diagnostics(control.diagnostics, green=repaired)
                    p1, p2 = repaired.p1, repaired.p2
                control.green_times[f"{key}_p1"] = p1
                control.green_times[f"{key}_p2"] = p2
            elif kind == "v":
                # 이산 VSL 집합으로 스냅(plant 검증 게이트와 동일 제약).
                if self.cfg.mpc.relaxed_quantized_controls:
                    prev = previous.vsl.get(key, max(vsl_set)) if previous else max(vsl_set)
                    repaired = repair_vsl_value(float(value), float(prev), self.cfg)
                    accumulate_repair_diagnostics(control.diagnostics, vsl=repaired)
                    control.vsl[key] = repaired.value
                else:
                    control.vsl[key] = float(min(vsl_set, key=lambda v: abs(v - value)))
            elif kind == "o":
                control.offsets[key] = float(value % net.cycle_length)
            elif kind == "m":
                control.ramp_metering[key] = float(np.clip(value, 0.0, net.ramp_capacity_veh_h[key]))
            else:  # a_<gate>
                fraction = float(np.clip(value, 0.0, 1.0))
                for movement in self._gate_movements.get(key, []):
                    control.inflow_outflow_allocation[movement] = fraction * self._flow_max
        if self.mode == "proposed":
            # 게이트 외 perimeter movement: follower 정책과 동일하게 boundary_out/off_ramp는
            # 최대 서비스(자유 sink/우선 방출), on_ramp는 metering과 정합(중복 제어 방지).
            for movement, spec in self._specs.items():
                kind = str(spec.get("kind", ""))
                if kind == "boundary_out" or kind == "off_ramp":
                    control.inflow_outflow_allocation[movement] = self._flow_max
                elif kind == "on_ramp":
                    ramp = str(spec.get("ramp", ""))
                    count = max(1, sum(1 for s in self._specs.values()
                                       if s.get("kind") == "on_ramp" and s.get("ramp") == ramp))
                    control.inflow_outflow_allocation[movement] = (
                        control.ramp_metering.get(ramp, net.ramp_capacity_veh_h.get(ramp, 0.0)) / count
                    )
        return control

    # ---------- objective ----------

    def _objective(
        self,
        states: List[TrafficState],
        control: ControlAction,
        previous: ControlAction,
        trajectory_ttt: float | None = None,
    ) -> float:
        """J_WU_global(16.6)/J_PROPOSED_SYSTEM(16.9) 공통 형태 — TTS + 초과 패널티 + Δu."""
        net = self.cfg.network
        lc = self.cfg.leader
        if self.mode == "wu":
            # Spec 16.6: Wu centralized objective는 coupled plant의 urban/freeway TTS와
            # green/VSL variation이다. Proposed leader threshold penalty를 섞지 않는다.
            if trajectory_ttt is None:
                # off-ramp 램프 storage 재귀속(design 2026-06-17): WU도 plant 공통이라
                # 램프 storage를 freeway로 느낀다(total objective 보존 + freeway 귀속).
                total = self.cfg.simulation.T_c_h * sum(
                    s.total_urban_vehicles(net)
                    + s.total_freeway_vehicles(net)
                    + s.off_ramp_storage_occupancy_veh(net)
                    for s in states
                )
            else:
                total = float(trajectory_ttt)
        else:
            total = 0.0
            for s in states:
                total += s.total_urban_vehicles(net) + s.total_freeway_vehicles(net)
                # off-ramp 램프 storage 재귀속(design 2026-06-17): urban에서 빠진 램프
                # storage를 freeway TTS로 계상(total objective 보존 + freeway 귀속).
                total += s.off_ramp_storage_occupancy_veh(net)
                total += lc.w_P * max(0.0, s.protected_accumulation_veh(net) - lc.N_P_crit_veh)
                total += lc.w_F * sum(
                    net.freeway_segment_length_km * net.freeway_lanes * max(0.0, rho - net.rho_crit)
                    for values in s.freeway_density.values()
                    for rho in values
                )
        # 제어 변화 패널티(green/VSL — Wu 식24의 Δu항과 동형; proposed는 offset/metering 포함).
        green_variation = 0.0
        for signal in net.signals:
            green_variation += abs(
                control.green_times.get(f"{signal}_p1", 0.0)
                - previous.green_times.get(f"{signal}_p1", 0.0)
            )
        vsl_variation = 0.0
        for link in net.freeway_links:
            vsl_variation += abs(control.vsl.get(link, 0.0) - previous.vsl.get(link, 0.0))
        if self.mode == "wu":
            # seconds와 km/h를 직접 더하지 않고 각 action range로 정규화한다.
            smooth = (
                self.cfg.urban_follower.green_smoothness_weight
                * green_variation
                / max(net.effective_green_total, 1.0e-9)
                + self.cfg.freeway_follower.vsl_smoothness_weight
                * vsl_variation
                / max(self.cfg.freeway_follower.max_vsl_step, 1.0e-9)
            )
            return float(total + smooth)

        smooth = green_variation + vsl_variation
        if self.mode == "proposed":
            for signal in net.signals:
                delta = abs(control.offsets.get(signal, 0.0) - previous.offsets.get(signal, 0.0))
                smooth += min(delta, net.cycle_length - delta)
            for ramp in net.ramps:
                smooth += abs(control.ramp_metering.get(ramp, 0.0) - previous.ramp_metering.get(ramp, 0.0)) / 100.0
        return float(total + 0.1 * smooth)

    def _predict(self, state: TrafficState, control: ControlAction, forecast: List[DemandStep]) -> List[TrafficState]:
        return self._predict_with_ttt(state, control, forecast)[0]

    def _predict_with_ttt(
        self,
        state: TrafficState,
        control: ControlAction,
        forecast: List[DemandStep],
    ) -> tuple[List[TrafficState], float]:
        from src.simulation.coupling import run_coupled_interval

        s = state.copy()
        states: List[TrafficState] = []
        total_ttt = 0.0
        for demand in forecast[: self.cfg.mpc.horizon_steps]:
            result = run_coupled_interval(s, control, demand, self.cfg)
            total_ttt += result.urban_ttt + result.freeway_ttt
            s.time_sec += self.cfg.simulation.control_interval
            states.append(s.copy())
        return states, float(total_ttt)

    # ---------- decide ----------

    def decide_with_info(
        self,
        state: TrafficState,
        demand_forecast: Iterable[DemandStep],
        previous_control: Optional[ControlAction] = None,
    ) -> CentralizedDecisionInfo:
        start = time.perf_counter()
        forecast = list(demand_forecast)
        previous = previous_control or self.previous_control or _wu_fixed_base(self.cfg)
        lower, upper, names = self._vector_bounds(previous)
        span = np.maximum(upper - lower, 1e-9)
        budget = max(8, int(self.cfg.mpc.optimizer_maxiter) * max(1, int(self.cfg.mpc.optimizer_n_starts)))
        time_index = int(round(state.time_sec / max(self.cfg.simulation.control_interval, 1e-9)))
        rng = np.random.default_rng(int(self.cfg.simulation.random_seed) + 7919 * time_index)

        def evaluate(vec: np.ndarray) -> tuple[float, ControlAction]:
            control = self._control_from_vector(np.clip(vec, lower, upper), names, previous)
            states, trajectory_ttt = self._predict_with_ttt(state, control, forecast)
            return self._objective(states, control, previous, trajectory_ttt), control

        # warm start = 직전 적용 제어, 비교 기준 = 고정 baseline.
        best_vec = np.clip(self._vector_from_control(previous, names), lower, upper)
        best_obj, best_control = evaluate(best_vec)
        evals = 1

        # Sparse control improvement를 놓치지 않도록 각 차원의 bound를 먼저 평가한다.
        # 모든 변수를 동시에 흔드는 random search만 사용하면 불필요한 variation penalty가
        # 유효한 단일 green/VSL 변경을 가릴 수 있다.
        coordinate_origin = best_vec.copy()
        for index in range(len(best_vec)):
            for value in (lower[index], upper[index]):
                if evals >= budget or abs(value - coordinate_origin[index]) <= 1.0e-9:
                    continue
                cand = coordinate_origin.copy()
                cand[index] = value
                obj, control = evaluate(cand)
                evals += 1
                if obj < best_obj - 1.0e-9:
                    best_obj, best_control = obj, control
                    best_vec = np.clip(self._vector_from_control(control, names), lower, upper)

        stall = 0
        sigma = 0.35
        while evals < budget:
            cand = best_vec + rng.normal(0.0, sigma, size=best_vec.shape) * span
            obj, control = evaluate(cand)
            evals += 1
            if obj < best_obj - 1e-9:
                best_obj, best_control = obj, control
                best_vec = np.clip(self._vector_from_control(control, names), lower, upper)
                stall = 0
            else:
                stall += 1
                if stall % 8 == 0:
                    sigma = max(0.08, sigma * 0.6)  # 탐색 반경 감쇠(국소 정밀화).
        converged = stall >= 8  # 마지막 구간에서 개선 정체 → 수렴으로 보고.
        self.previous_control = best_control
        return CentralizedDecisionInfo(
            control=best_control,
            objective=float(best_obj),
            solver_evaluations=evals,
            converged=bool(converged),
            computation_time_sec=time.perf_counter() - start,
        )
