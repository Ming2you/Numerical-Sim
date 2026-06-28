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

from src.controllers.local_signal_plant import (
    build_local_model,
    rollout_local_tts,
    rollout_local_tts_ramp_aware,
)
from src.controllers.nash_solver import NashResult
from src.controllers.relaxed_quantization import (
    queue_pressure_green_target,
    repair_green_pair,
)
from src.controllers.wu_distributed import WuDistributedController, _split_link_offramp_flow
from src.models.demand import DemandStep
from src.models.metanet import compute_ramp_release_flows
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
        # de facto ramp metering 패널티 계수: 0으로 비활성화한다(SPEC 갱신). 이전엔 urban
        # agent의 on_ramp green을 freeway 혼잡으로 가중 처벌해 metering을 '근사'했으나, 이는
        # 튜닝된 hack(이중 metering)이었다. 이제 freeway agent가 진짜 ramp_metering 액추에이터를
        # 자기 own-TTS로 직접 탐색하므로(아래 `_solve_freeway_agent_metered`), urban agent는
        # 순수 demand-responsive로 남기고 metering은 freeway가 단독 수행한다.
        self.ramp_metering_weight: float = 0.0
        # freeway agent가 탐색할 ramp metering 후보 분율(×capacity). +41.8% 검증 최적(≈0.5)을
        # 중심으로 0.25~1.0을 덮는다. cap=100%(=metering off)부터 강한 metering 25%까지.
        self.ramp_metering_fractions: tuple[float, ...] = (1.0, 0.7, 0.5, 0.35, 0.25)
        # 직전 step 수렴 결합값(warm-start).
        self._prev_coupling: Optional[Dict[str, float]] = None
        # 어댑터가 n_agents를 셀 때 쓰는 속성(six_controller 어댑터 호환).
        self.urban_agents = list(cfg.network.signals)
        self.freeway_agents = list(cfg.network.freeway_links)

    # ---------- per-movement 도착 (결합변수 movement 분해) ----------

    def _per_movement_arrivals(
        self,
        signal: str,
        state: TrafficState,
        control: ControlAction,
        demand: DemandStep,
    ) -> Dict[str, float]:
        """신호 i의 각 movement m에 대한 고정 도착유량 arr_m[veh/h]을 **소스에서 직접** 계산.

        `_coupling`의 `arr_{signal}_{pid}` phase 집계를 β로 재분배(re-smear)하지 않는다.
        `_coupling`이 합산한 것과 동일한 항을 movement 단위로 그대로 구한다. _coupling은
        movement마다 (a) kind-specific 외생 항과 (b) origin 링크가 상류 신호에서 받는 유입의
        β 몫을 **둘 다 더한다**(예: on_ramp movement D_N_to_onW는 origin이 internal 링크
        A_to_D라 ramp_arrival·β + A_to_D 유입·β를 모두 받는다). 따라서 두 항을 합산한다:
          (a) kind-specific:
              boundary_in → β_m × demand.urban_boundary[origin_m]
              on_ramp     → β_m × demand.ramp_arrival[ramp_m]
              off_ramp    → β_m × off_inflow(off_ramp_m)  (freeway 후보 VSL 동결값 재사용)
          (b) upstream:
              origin 링크 L이 상류 신호 leaving을 받으면 + β_m × inflow(L).
              inflow(L) = Σ_{producer dest==L} leaving_rate(producer)  (_coupling과 동일).
        보존: Σ_{m∈phase} arr_m == arr_{signal}_{phase}(_coupling)."""
        net = self.cfg.network
        wu = self._wu
        arr_m: Dict[str, float] = {}
        # 상류 신호가 먹이는 origin 링크별 총 유입유량[veh/h]을 한 번만 계산해 캐시.
        # _coupling과 동일하게 producer movement의 leaving rate를 합산한다.
        upstream_inflow_by_link: Dict[str, float] = {}
        for phase_id in ("p1", "p2"):
            key = f"{signal}_{phase_id}"
            for up_signal, up_movement, _up_beta in wu._upstream_leaving_map.get(key, []):
                origin_link = str(wu._specs[up_movement].get("destination", ""))
                if not origin_link:
                    continue
                if origin_link not in upstream_inflow_by_link:
                    upstream_inflow_by_link[origin_link] = 0.0
                upstream_inflow_by_link[origin_link] += wu._signal_leaving_rate(
                    up_signal, up_movement, control, state, demand,
                )

        for phase_id in ("p1", "p2"):
            for movement in self._phase_movements[signal][phase_id]:
                spec = self._specs[movement]
                kind = str(spec.get("kind", ""))
                beta = float(spec.get("beta", 0.0))
                origin = str(spec.get("origin", ""))
                arrival = 0.0
                # (a) kind-specific 외생 항.
                if kind == "boundary_in":
                    arrival += beta * max(0.0, demand.urban_boundary.get(origin, 0.0))
                elif kind == "on_ramp":
                    ramp = str(spec.get("ramp", ""))
                    arrival += beta * max(0.0, demand.ramp_arrival.get(ramp, 0.0))
                elif kind == "off_ramp":
                    off_ramp = str(spec.get("off_ramp", ""))
                    link = net.off_ramp_from_freeway.get(off_ramp, "")
                    if wu._has_last_offramp_flow:
                        off_inflow = float(wu._last_offramp_flow.get(off_ramp, 0.0))
                    else:
                        base = (
                            state.freeway_flow.get(link, [0.0])[-1]
                            if state.freeway_flow.get(link) else 0.0
                        )
                        off_inflow = _split_link_offramp_flow(self.cfg, link, off_ramp, base)
                    arrival += beta * max(0.0, off_inflow)
                # (b) origin 링크가 상류 신호 leaving을 받으면 그 β 몫도 더한다(_coupling과 동일).
                arrival += beta * max(0.0, upstream_inflow_by_link.get(origin, 0.0))
                arr_m[movement] = arrival
        return arr_m

    def _frozen_offramp_inflow(self, off_ramp: str, state: TrafficState) -> float:
        """off_ramp별 frozen freeway→off-ramp 유출[veh/h].

        `_coupling`의 freeway→urban 결합과 동일 소스: freeway agent 후보 VSL의 off-ramp
        유출 캐시(`_last_offramp_flow`), 없으면 현재 본선 유량 폴백(`_split_link_offramp_flow`).
        `_per_movement_arrivals`가 β로 분배하기 전 per-off_ramp 원값이다."""
        net = self.cfg.network
        wu = self._wu
        link = net.off_ramp_from_freeway.get(off_ramp, "")
        if wu._has_last_offramp_flow:
            return max(0.0, float(wu._last_offramp_flow.get(off_ramp, 0.0)))
        base = (
            state.freeway_flow.get(link, [0.0])[-1]
            if state.freeway_flow.get(link) else 0.0
        )
        return max(0.0, _split_link_offramp_flow(self.cfg, link, off_ramp, base))

    def _frozen_freeway_congestion(self, state: TrafficState) -> Dict[str, float]:
        """ramp별 frozen freeway 혼잡 가중 w_fw ∈ [0,1] — de facto ramp metering(SPEC line 28).

        merge 지점 ρ로 `compute_ramp_release_flows`의 receiving_factor를 복제해
        w_fw = 1 − receiving_factor. freeway가 막히면(ρ_merge↑) w_fw→1, free-flow면 →0.
        on-ramp reservoir 적재(→freeway 유입)에 이 가중을 곱해 비용에 넣으면, 막힌 freeway로
        차를 더 보내는 p1(on_ramp 위주) green이 비용으로 잡혀 p2-heavy로 기운다. freeway가
        자유흐름이면 w_fw≈0이라 순수 국소 거동을 회복(무해)."""
        from src.models.metanet import _ramp_merge_index, _clip
        net = self.cfg.network
        w: Dict[str, float] = {}
        for ramp in net.ramps:
            link = net.ramp_to_freeway.get(ramp, "")
            densities = state.freeway_density.get(link, [])
            if not densities:
                w[ramp] = 0.0
                continue
            merge_idx = _ramp_merge_index(self.cfg, ramp, len(densities))
            rho_merge = densities[merge_idx]
            receiving_factor = _clip(
                (net.rho_max - rho_merge) / max(net.rho_max - net.rho_crit, 1.0e-9),
                0.0, 1.0,
            )
            w[ramp] = float(max(0.0, 1.0 - receiving_factor))
        return w

    def _frozen_reservoir_drain(
        self, state: TrafficState, control: ControlAction, demand: DemandStep,
    ) -> Dict[str, float]:
        """ramp별 frozen reservoir→freeway 방출률[veh/h](freeway가 reservoir를 비우는 속도).

        실제 plant는 매 T_f 경계에서 `compute_ramp_release_flows`(ρ_merge 기반 수용)로
        reservoir(w_r)를 freeway로 비운다. 국소 rollout이 reservoir 유출을 0으로 동결하면
        w_r이 ramp_queue_max에 고정돼 on_ramp green이 무력해진다(잘못된 flat 비용). 따라서
        freeway 본선 ρ로 결정되는 이 방출률을 동결 결합값으로 받아 substep마다 reservoir를
        비운다(green→reservoir 적재 vs freeway→reservoir 배출의 상충이 보이게)."""
        release, _ = compute_ramp_release_flows(state, control, demand, self.cfg)
        return {ramp: max(0.0, float(v)) for ramp, v in release.items()}

    def _offramp_occupancy(self, off_ramp: str, state: TrafficState) -> float:
        """off-ramp storage 초기 점유[veh] = cap − available(plant `_drain_offramp_storage` 정의)."""
        net = self.cfg.network
        storage = net.off_ramp_storage_link.get(off_ramp, "")
        if not storage:
            return 0.0
        cap = float(net.urban_link_storage_veh.get(storage, 0.0))
        return max(0.0, cap - float(state.urban_link_storage.get(storage, cap)))

    # ---------- per-signal 국소 agent solve (핵심 신규) ----------

    def _solve_urban_agent_local(
        self,
        signal: str,
        state: TrafficState,
        coupling: Mapping[str, float],
        arr_movement: Mapping[str, float],
        s_eff_frozen: Mapping[str, float],
        reservoir_drain: Mapping[str, float],
        freeway_congestion: Mapping[str, float],
        previous: ControlAction,
    ) -> tuple[float, float, int]:
        """green p1 후보 탐색 — 반환 (p1*, 자기 TTS objective, evaluations).

        후보 채점은 `rollout_local_tts`로 **신호 i movement만** 전진(전체망 plant 호출 없음).
        arr_movement: `_per_movement_arrivals`가 소스에서 직접 구한 movement별 도착유량.
        결합변수는 frozen이므로 phase 합이 frozen arr_{signal}_{pid}와 일치하도록 재정규화한다
        (phase 내 재귀속만, phase 총량 보존)."""
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
        # phase 단위 고정 도착(결합변수, frozen).
        arr_phase = {pid: float(coupling.get(f"arr_{signal}_{pid}", 0.0)) for pid in ("p1", "p2")}
        # ramp-aware 신호(D/F): off-ramp 유입을 phase 큐에서 분리해 storage로 보낸다. frozen
        # arr_phase는 `_coupling`에서 off-ramp inflow·β를 포함하므로, queue 도착에는 그 몫을
        # 빼고(phase별 off-ramp 기여), off-ramp inflow는 storage 유입으로 따로 넘긴다.
        offramp_inflow: Dict[str, float] = {}
        offramp_contrib_phase = {"p1": 0.0, "p2": 0.0}
        if model.has_ramps:
            for off_ramp, movements in model.offramp_movements.items():
                inflow = self._frozen_offramp_inflow(off_ramp, state)
                offramp_inflow[off_ramp] = inflow
                # off_ramp movement는 모두 같은 phase(Σβ=1.0); 그 phase 큐 기여 = inflow.
                for m in movements:
                    offramp_contrib_phase[model.phase_of[m]] += model.beta_of[m] * inflow
        # movement별 도착을 frozen phase 총량(off-ramp 몫 제외)에 맞춰 재정규화.
        arr_mv: Dict[str, float] = {}
        for pid in ("p1", "p2"):
            # off_ramp movement는 큐 도착 대상이 아님(storage로 유입).
            phase_movements = [
                m for m in model.movements
                if model.phase_of[m] == pid and model.kind_of[m] != "off_ramp"
            ]
            raw_sum = sum(max(0.0, float(arr_movement.get(m, 0.0))) for m in phase_movements)
            target = max(0.0, arr_phase[pid] - offramp_contrib_phase[pid])
            if raw_sum > 1.0e-12:
                scale = target / raw_sum
                for m in phase_movements:
                    arr_mv[m] = max(0.0, float(arr_movement.get(m, 0.0))) * scale
            else:
                for m in phase_movements:
                    arr_mv[m] = 0.0
        # off-ramp storage 초기 점유·on-ramp reservoir 초기 큐 스냅샷(자기 권역).
        offramp_occ0 = {
            off_ramp: self._offramp_occupancy(off_ramp, state)
            for off_ramp in model.offramp_movements
        }
        ramp_queue0 = {
            ramp: max(0.0, float(state.ramp_queue.get(ramp, 0.0)))
            for ramp in model.onramp_movements
        }
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
            if model.has_ramps:
                cost = rollout_local_tts_ramp_aware(
                    model, q0, arr_mv, s_eff0,
                    offramp_inflow, offramp_occ0, ramp_queue0, reservoir_drain,
                    freeway_congestion, self.ramp_metering_weight,
                    p1, p2, substeps, dt_h,
                )
            else:
                cost = rollout_local_tts(
                    model, q0, arr_mv, s_eff0, p1, p2, substeps, dt_h,
                )
            cost += smooth_w * abs(p1 - prev_p1)
            evals += 1
            if cost < best_obj:
                best_obj, best_p1 = cost, float(p1)
        return best_p1, best_obj, evals

    # ---------- freeway agent: 진짜 ramp metering 탐색 (핵심 신규) ----------

    def _solve_freeway_agent_metered(
        self,
        link: str,
        state: TrafficState,
        coupling: Mapping[str, float],
        demand: DemandStep,
        snapshot: ControlAction,
    ) -> tuple[Dict[str, float], Dict[str, float], int]:
        """freeway agent의 VSL + ramp_metering 결합 탐색 — 반환 (vsl_dict, metering_dict, evals).

        SPEC: freeway agent가 자기 partition의 on-ramp를 소유하므로(`ramp_to_freeway[ramp]==link`),
        de-facto metering이 freeway agent의 OWN-TTS 최소화에서 **창발(emerge)**해야 한다.

        구현은 기존 `_solve_freeway_agent`의 probe-rollout을 그대로 재사용한다(미변경 파일이지만
        callable). 그 메서드는 `previous.ramp_metering`을 candidate_control에 복사해
        `compute_ramp_release_flows`로 흘리고(metanet.py:230 액추에이터), own-TTS(=freeway link
        차량 + on-ramp ramp_queue + off-ramp storage)로 채점한다. 따라서 후보 metering 분율을
        snapshot.ramp_metering에 주입해 `_solve_freeway_agent`를 호출하면, 그 분율 하의
        (best-VSL) own-TTS 비용을 그대로 돌려받는다. metering의 상충(본선 보호 vs on-ramp 큐
        성장)이 probe 동역학과 own-TTS에 내생화된다 — 인위적 패널티/튜닝 없음.

        탐색은 cheap하게 ramp별 좌표하강(coordinate scan): 이 link 소유 ramp 각각에 대해
        5개 분율을 훑고 나머지 ramp는 현재 best에 고정. 호출 횟수 = Σ_ramp(분율 수) ≈ 2×5 = 10
        freeway solve/link (조합 25개 대신). 각 solve는 기존 VSL 후보 sweep과 동일.
        """
        net = self.cfg.network
        owned_ramps = [r for r in net.ramps if net.ramp_to_freeway.get(r) == link]
        caps = {r: float(net.ramp_capacity_veh_h[r]) for r in owned_ramps}
        # 현재 best metering(절대 veh/h). 초기값 = capacity(=metering off, snapshot 기본).
        best_meter = {
            r: float(snapshot.ramp_metering.get(r, caps[r])) for r in owned_ramps
        }
        evals_total = 0

        def _solve_with(meter: Mapping[str, float]) -> tuple[Dict[str, float], float, int]:
            probe_prev = ControlAction(
                ramp_metering=dict(snapshot.ramp_metering),
                vsl=dict(snapshot.vsl),
                green_times=dict(snapshot.green_times),
                offsets=dict(snapshot.offsets),
                inflow_outflow_allocation={},
            )
            probe_prev.ramp_metering.update({r: float(v) for r, v in meter.items()})
            return self._wu._solve_freeway_agent(
                link, state, coupling, demand, probe_prev, None,
            )

        # 초기 best 비용·VSL(현재 metering에서).
        best_vsl, best_cost, e0 = _solve_with(best_meter)
        evals_total += e0

        # ramp별 좌표하강: 각 ramp의 5개 분율을 훑어 own-TTS 최저 분율로 갱신.
        for ramp in owned_ramps:
            local_best_meter = best_meter[ramp]
            for frac in self.ramp_metering_fractions:
                cand_val = frac * caps[ramp]
                if abs(cand_val - best_meter[ramp]) <= 1.0e-9:
                    continue  # 이미 평가된 현재값.
                trial = dict(best_meter)
                trial[ramp] = cand_val
                vsl_dict, cost, e = _solve_with(trial)
                evals_total += e
                if cost < best_cost:
                    best_cost, best_vsl, local_best_meter = cost, vsl_dict, cand_val
            best_meter[ramp] = local_best_meter

        return best_vsl, best_meter, evals_total

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
        # freeway가 reservoir(w_r)를 비우는 frozen 방출률(ρ_merge 기반) — 한 step 내 고정.
        reservoir_drain = self._frozen_reservoir_drain(state, control, demand)
        # ramp별 frozen freeway 혼잡 가중(de facto ramp metering) — 한 step 내 고정.
        freeway_congestion = self._frozen_freeway_congestion(state)

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
                arr_movement = self._per_movement_arrivals(signal, state, snapshot, demand)
                p1, _, e = self._solve_urban_agent_local(
                    signal, state, coupling, arr_movement, s_eff_frozen,
                    reservoir_drain, freeway_congestion, snapshot,
                )
                new_green[f"{signal}_p1"] = p1
                new_green[f"{signal}_p2"] = net.effective_green_total - p1
                evals += e
            # freeway agent(Jacobi 내부): VSL solve만 cheap하게 — VSL은 여기서 inert이고
            # metering 좌표하강은 비싸므로 합의 루프 밖에서 1회만 돈다(아래 post-loop).
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
        # ---- freeway agent ramp_metering 좌표하강(step당 1회, 수렴된 결합값 기준) ----
        # metering 탐색은 비싸므로(VSL probe sweep ×5분율) Jacobi 루프 밖에서 1회만 돈다.
        # 입력 snapshot = 합의 종료 control(최신 urban green·VSL). coupling['u_on_ramp']은
        # 수렴값이라 reservoir 적재가 안정적이고, metering이 own-TTS에서 창발한다.
        meter_snapshot = ControlAction(
            ramp_metering=dict(control.ramp_metering),
            vsl=dict(control.vsl),
            green_times=dict(control.green_times),
            offsets=dict(control.offsets),
            inflow_outflow_allocation={},
        )
        for link in net.freeway_links:
            vsl_dict, meter_dict, e = self._solve_freeway_agent_metered(
                link, state, coupling, demand, meter_snapshot,
            )
            control.vsl.update(vsl_dict)
            control.ramp_metering.update(meter_dict)
            evals += e
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
