# Wu(2022) §IV-D 충실 분산 follower — 진짜 per-signal 국소 rollout + Jacobi 합의 (새 코드)
"""SPEC_wu_faithful_follower.md 구현물.

이전 실패는 후보 채점을 전체망 plant(`urban_step`/`run_coupled_interval`)로 해서 진짜 local이
아니었고 목적이 global TTT였다. 이번엔:
1. agent i(=신호 1개)의 movement 큐만 `LocalSignalModel.rollout_local_tts`로 전진(이웃 동결).
2. 목적 = 자기 차량수 합(자기 TTS) + R_i·|Δg|.
3. Jacobi: S_max=5 반복, 결합변수 z̃ 동결·동시갱신, warm-start.

기존 파일 미변경 원칙: 결합변수 계산(`_coupling`), 토폴로지 맵(`_phase_movements`, `_specs`),
freeway agent VSL solve(`_solve_freeway_agent`)는 기존 `WuDistributedController` 인스턴스를
**조합(composition)**으로 재사용한다. urban agent solve만 진짜 국소 rollout으로 교체한다.

`solve(state, leader, demand, previous) -> NashResult`로 `DistributedCoordinator`와 동일 인터페이스.
leader는 None(PFO 모드)부터 구현한다.
"""
from __future__ import annotations

import time
from typing import Dict, Iterable, List, Mapping, Optional

import numpy as np

from src.controllers.local_signal_plant import build_local_model, rollout_local_tts
from src.controllers.nash_solver import NashResult
from src.controllers.relaxed_quantization import (
    queue_pressure_green_target,
    repair_green_pair,
)
from src.controllers.wu_distributed import WuDistributedController
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import _effective_available_space


class WuFaithfulFollower:
    """Wu §IV-D 충실 분산 follower(PFO 모드 우선)."""

    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg
        # 결합·freeway·토폴로지 재사용용 내부 인스턴스(기존 파일 미변경, 조합만).
        self._wu = WuDistributedController(cfg, leader_enabled=False)
        self._specs = self._wu._specs
        self._phase_movements = self._wu._phase_movements
        # 신호별 국소 모델(정적 데이터) 구성 — 매 step 재사용.
        self._local_models = {
            signal: build_local_model(cfg, signal, self._specs, self._phase_movements)
            for signal in cfg.network.signals
        }
        # 직전 step 수렴 결합값(warm-start).
        self._prev_coupling: Optional[Dict[str, float]] = None
        # 어댑터가 n_agents를 셀 때 쓰는 속성(six_controller 어댑터 호환).
        self.urban_agents = list(cfg.network.signals)
        self.freeway_agents = list(cfg.network.freeway_links)

    # ---------- per-signal 국소 agent solve (핵심 신규) ----------

    def _solve_urban_agent_local(
        self,
        signal: str,
        state: TrafficState,
        coupling: Mapping[str, float],
        s_eff_frozen: Mapping[str, float],
        previous: ControlAction,
    ) -> tuple[float, float, int]:
        """green p1 후보 탐색 — 반환 (p1*, 자기 TTS objective, evaluations).

        후보 채점은 `rollout_local_tts`로 **신호 i movement만** 전진(전체망 plant 호출 없음)."""
        net = self.cfg.network
        sim = self.cfg.simulation
        model = self._local_models[signal]
        total = net.effective_green_total
        horizon = max(1, self.cfg.mpc.horizon_steps)
        substeps = horizon * max(1, sim.K_cu)
        dt_h = sim.T_u_h
        smooth_w = self.cfg.urban_follower.green_smoothness_weight

        # 자기 movement 초기 큐.
        q0 = {m: max(0.0, state.urban_movement_queue.get(m, 0.0)) for m in model.movements}
        # phase 단위 고정 도착(결합변수).
        arr_phase = {pid: float(coupling.get(f"arr_{signal}_{pid}", 0.0)) for pid in ("p1", "p2")}
        # 이 신호 movement들의 receiving 링크 S_eff(동결 스냅샷).
        s_eff0 = {
            model.receiving_of[m]: float(s_eff_frozen.get(model.receiving_of[m], 0.0))
            for m in model.movements
            if model.receiving_of[m]
        }

        prev_p1 = float(previous.green_times.get(f"{signal}_p1", total / 2.0))
        # pressure 중심 + 주변 후보(완화 양자화). 기존 _solve_urban_agent와 같은 후보 구성 철학.
        p1_pressure = q0_sum(q0, model, "p1") + arr_phase["p1"] * dt_h * substeps
        p2_pressure = q0_sum(q0, model, "p2") + arr_phase["p2"] * dt_h * substeps
        pressure_center = queue_pressure_green_target(p1_pressure, p2_pressure, self.cfg)
        raw_candidates = [total / 2.0, prev_p1, pressure_center]
        if self.cfg.mpc.relaxed_quantized_controls:
            raw_candidates.extend([
                pressure_center - 1.0, pressure_center + 1.0,
                pressure_center - 2.0, pressure_center + 2.0,
                pressure_center - 5.0, pressure_center + 5.0,
            ])
        # 진짜 국소 rollout은 신호 1개만 돌아 싸므로 전 green 범위를 굵게 훑어 실제 국소
        # 최적을 찾는다(pressure-center 밴드는 옛 집계모델용이라 좁아 56을 못 벗어났다 —
        # 의도적 deviation, SPEC §2의 "argmin J_i,local" 충실). 후보 폭발 없음(13점/신호).
        raw_candidates.extend(float(v) for v in np.linspace(net.green_min, net.green_max, 13))

        candidates: List[float] = []
        for raw in raw_candidates:
            if self.cfg.mpc.relaxed_quantized_controls:
                p1_value = repair_green_pair(float(raw), self.cfg).p1
            else:
                p1_value = float(np.clip(raw, net.green_min, net.green_max))
                p2_value = total - p1_value
                if p2_value < net.green_min:
                    p1_value = total - net.green_min
                if p2_value > net.green_max:
                    p1_value = total - net.green_max
            if not any(abs(p1_value - existing) <= 1.0e-9 for existing in candidates):
                candidates.append(float(p1_value))

        best_p1, best_obj = prev_p1, float("inf")
        evals = 0
        for p1 in candidates:
            p2 = total - p1
            if p2 < net.green_min - 1.0e-9 or p2 > net.green_max + 1.0e-9:
                continue
            cost = rollout_local_tts(
                model, q0, arr_phase, s_eff0, p1, p2, substeps, dt_h,
            )
            cost += smooth_w * abs(p1 - prev_p1)
            evals += 1
            if cost < best_obj:
                best_obj, best_p1 = cost, float(p1)
        return best_p1, best_obj, evals

    # ---------- Jacobi 합의 루프 (Wu §IV-D) ----------

    def _frozen_s_eff(self, state: TrafficState) -> Dict[str, float]:
        """모든 urban 링크의 S_eff 스냅샷(이웃 downstream 동결값)."""
        s_eff: Dict[str, float] = {}
        for link in self.cfg.network.urban_link_storage_veh:
            s_eff[link] = float(_effective_available_space(state, self.cfg, link))
        return s_eff

    def _solve_followers(
        self,
        state: TrafficState,
        demand: DemandStep,
        previous: ControlAction,
    ) -> tuple[ControlAction, int, bool, float, int]:
        net = self.cfg.network
        self._wu._repair_diagnostics = {}
        control = ControlAction.uncontrolled(self.cfg)
        control.green_times = dict(previous.green_times)
        control.vsl = dict(previous.vsl)
        control.inflow_outflow_allocation = {}
        # warm-start 결합변수(직전 step 수렴값) 우선, 없으면 현재 control 기준 계산.
        coupling = self._wu._coupling(state, control, demand)
        if self._prev_coupling is not None:
            for k in coupling:
                if k in self._prev_coupling:
                    coupling[k] = float(self._prev_coupling[k])
        # 이웃 downstream S_eff 동결 스냅샷(한 step 내 고정).
        s_eff_frozen = self._frozen_s_eff(state)

        s_max = max(1, min(self.cfg.mpc.max_nash_iter, 5))
        alpha = 0.5
        evals = 0
        residual = float("inf")
        converged = False
        iteration = 0
        for iteration in range(1, s_max + 1):
            # Jacobi: iteration 시작 control 스냅샷 고정 → 모든 agent 동일 z̃/previous 입력.
            snapshot = ControlAction(
                ramp_metering=dict(control.ramp_metering),
                vsl=dict(control.vsl),
                green_times=dict(control.green_times),
                offsets=dict(control.offsets),
                inflow_outflow_allocation={},
            )
            new_green: Dict[str, float] = {}
            new_vsl: Dict[str, float] = {}
            for signal in net.signals:
                p1, _, e = self._solve_urban_agent_local(
                    signal, state, coupling, s_eff_frozen, snapshot,
                )
                new_green[f"{signal}_p1"] = p1
                new_green[f"{signal}_p2"] = net.effective_green_total - p1
                evals += e
            # freeway agent는 기존 VSL solve 재사용(spec §3: 1차 구현 차용 허용, 결합 동일 규약).
            for link in net.freeway_links:
                vsl_dict, _, e = self._wu._solve_freeway_agent(
                    link, state, coupling, demand, snapshot, None,
                )
                new_vsl.update(vsl_dict)
                evals += e
            control.green_times.update(new_green)
            control.vsl.update(new_vsl)
            # outgoing 결합변수 갱신 후 under-relaxation 합성.
            predicted = self._wu._coupling(state, control, demand)
            relaxed = {
                k: (1.0 - alpha) * coupling.get(k, 0.0) + alpha * predicted[k]
                for k in predicted
            }
            residual = max(
                (
                    abs(relaxed[k] - coupling.get(k, 0.0)) / max(1.0, abs(coupling.get(k, 0.0)))
                    for k in relaxed
                ),
                default=0.0,
            )
            coupling = relaxed
            if residual < self.cfg.mpc.distributed_coupling_tol:
                converged = True
                break
        # 다음 step warm-start용 수렴 결합값 저장.
        self._prev_coupling = dict(coupling)
        control.diagnostics.update(self._wu._repair_diagnostics)
        return control, iteration, converged, float(residual), evals

    # ---------- 외부 인터페이스 (DistributedCoordinator.solve와 동일) ----------

    def solve(
        self,
        state: TrafficState,
        leader: Optional[object],
        demand: DemandStep | Iterable[DemandStep],
        previous_control: Optional[ControlAction] = None,
        leader_incumbent_obj: float = np.inf,
    ) -> NashResult:
        if leader is not None:
            raise NotImplementedError("WuFaithfulFollower는 현재 leader=None(PFO 모드)만 구현한다.")
        forecast = [demand] if isinstance(demand, DemandStep) else list(demand)
        if not forecast:
            raise ValueError("WuFaithfulFollower requires at least one demand step.")
        first_demand = forecast[0]
        start = time.perf_counter()
        previous = (
            previous_control.copy()
            if previous_control is not None
            else ControlAction.uncontrolled(self.cfg)
        )
        control, iteration, converged, residual, evals = self._solve_followers(
            state, first_demand, previous,
        )
        control.N_P_star = 0.0
        control.N_UF_star = 0.0
        control.inflow_outflow_allocation = {}
        control.diagnostics["wu_faithful_follower_active"] = 1.0
        control.diagnostics["wu_faithful_local_evals"] = float(evals)
        control.diagnostics["wu_faithful_solve_time_sec"] = float(time.perf_counter() - start)
        return NashResult(
            control=control,
            objective_value=0.0,
            iterations=iteration,
            converged=converged,
            residual_objective=0.0,
            residual_control=float(residual),
            diagnostics=dict(control.diagnostics),
        )


def q0_sum(q0: Mapping[str, float], model, phase_id: str) -> float:
    """phase별 초기 큐 합(pressure 중심 계산용)."""
    return float(sum(
        max(0.0, q0.get(m, 0.0))
        for m in model.movements
        if model.phase_of[m] == phase_id
    ))
