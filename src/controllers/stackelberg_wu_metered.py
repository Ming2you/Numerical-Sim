# Wu충실 metering-PFO follower를 nash_solver로 주입하는 StackelbergMPCController 서브클래스(새 코드)
"""기존 `StackelbergMPCController`를 미변경으로 두고, follower만 `WuFaithfulFollower`로
교체하는 thin 서브클래스/팩토리.

근거(미변경 원칙): `StackelbergMPCController._make_follower_solver`는 cfg.mpc.follower_solver_mode가
"distributed"면 DistributedCoordinator, 아니면 NashSolver를 반환한다. 이 파일을 건드리지 않고
follower를 바꾸려면 `_make_follower_solver`만 오버라이드하면 된다. `decide_with_info` 등 나머지
경로는 `isinstance(self.nash_solver, DistributedCoordinator)` 분기에서 우리 follower가 모두 else
경로를 타므로(라인 ~301/991/1173/1338) 그대로 동작한다:
  - `_evaluate_full_candidate`: else 분기에서 `solve(state, action, forecast, previous)` 호출 —
    `WuFaithfulFollower.solve` 시그니처와 일치, `nash.control`/`nash.objective_value` 사용.
  - `_realized_net_inflow_veh` / `_evaluate_fallback_candidates`: DistributedCoordinator가 아니면
    각각 None / [] 반환 → output closure는 intent 유지, fallback 후보(no_control/pfo) 비활성.
    즉 우리 경우 fallback guard는 leader 후보만 보고 선택한다(leader vs PFO 비교는 러너가 한다).
  - `_proxy_score_candidate`: 베이스 else 분기는 action-blind(모든 후보 동점)라 이 파일에서
    action-aware 버전으로 오버라이드한다(용량비례 metering 근사 + plant rollout 채점).

따라서 서브클래스는 follower 주입만 한다. cfg는 호출처에서 follower_solver_mode를 임의값(예:
"wu_metered")으로 두거나 기본값 그대로 둬도 무방하다(우리는 mode와 무관하게 항상 주입).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from src.controllers.stackelberg_mpc import (
    DecisionResult,
    StackelbergMPCController,
    _LeaderCandidateEvaluation,
)
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState, segment_vsl
from src.controllers.leader import Leader, LeaderAction


class StackelbergWuMeteredController(StackelbergMPCController):
    """follower=WuFaithfulFollower(metering-PFO)로 고정한 Stackelberg 컨트롤러."""

    def __init__(self, cfg: ExperimentConfig):
        super().__init__(cfg)
        # ---------- B2: per-signal externality 가격(marginal price) 하달 ----------
        # Step B1(2026-07-03)이 검증한 가격 채널의 구현판. leader가 refresh마다 유한차분
        # 전역 rollout으로 g_ext_i = d(전역TTT)/dp1 − d(own-TTS)/dp1을 계산해 follower의
        # signal_marginal_price에 설정하고(사이엔 hold), follower는 green 후보 비용에
        # + w·g_ext_i·(p1 − p1_ref_i)를 더한다. w=1이 1차 정확값(B1 sweet spot, w=2는
        # overshoot). 이 가격은 전역 rollout이 필요해 leader 전용 — 순수 PFO 러너에는
        # 존재하지 않는다(P-Stack에서만 활성).
        # ── 기본 False(STOP 관례, 2026-07-04 교차검증): sweet_190에서 −1.84%(3600s)/−3.40%
        # (7200s)로 강한 이득이나 sweet_155 +1.66%(>1% 악화 기준 위반)·sweet_128 +0.36%.
        # 중부하 해악의 판별자(가격 크기·refresh 빈도로는 분리 안 됨)를 찾기 전까지 opt-in
        # (러너 P-STACK-WU-FAITHFUL-B2). P1.5와 동일 처분.
        self.signal_price_enabled: bool = False
        self.signal_price_delta_sec: float = 6.0  # 유한차분 스텝(B1 probe와 동일)
        self.signal_price_weight: float = 1.0
        # event-trigger 재선형화: 운영점(commit green)이 기준점에서 이만큼 이동하면
        # 재계산한다(B1 step35류 non-monotone은 재선형화 iteration으로 흡수). 그 외엔
        # 기존 leader_global_refresh cadence에 편승.
        self.signal_price_refresh_threshold_sec: float = 3.0
        # ---------- B3(Codex f18e920 포팅) + B4: metering/VSL 가격 채널 ----------
        # green과 동일 흐름으로 통일: refresh(최초/cadence/event-trigger) 시 **동일 동결
        # 운영점**에서 g_i(전역 rollout)와 d_local(follower 국소 채점)을 모두 계산해
        # g_ext를 완성·하달, 사이엔 hold. 1차 TTT 가격 단독의 metering/VSL 가격은 음성
        # (절벽 lever가 과방류 → freeway breakdown, 2026-07-04 §3) → 기본 OFF.
        self.metering_price_enabled: bool = False
        self.metering_price_delta_veh_h: float = 60.0  # Codex f18e920과 동일 δ
        self.metering_price_refresh_threshold_veh_h: float = 30.0
        self.vsl_price_enabled: bool = False
        self.vsl_price_delta_kmh: float = 10.0
        self.vsl_price_refresh_threshold_kmh: float = 5.0
        # B4(사용자 제안): metering 가격에 freeway rho_crit barrier 항의 marginal price를
        # 합산. barrier = w_f·Σ (excess_veh)²·T_c_h per interval — gradient가 절벽
        # (capacity drop)을 1차로 예고해, 정상 방류는 TTT 가격이 유도하고 과방류만
        # 차단한다(soft state constraint의 가격 실현; TTT 밖 별도 항이라 동어반복 아님).
        # barrier는 leader 전용 목적항이라 d_local 차감이 없다(follower own-TTS에 부재).
        self.barrier_price_enabled: bool = False
        self.barrier_weight: float = 1.0e-2  # excess_veh²·h → veh·h 급 환산 스케일(스윕 대상)
        self._signal_price_refresh_count: int = 0
        self._signal_price_meta: Dict[str, float] = {}

    def _make_follower_solver(self, cfg: ExperimentConfig):
        return WuFaithfulFollower(cfg)

    # ---------- B2: per-signal externality 가격 계산/refresh ----------

    def decide_with_info(
        self,
        state: TrafficState,
        demand_forecast,
        previous_control: Optional[ControlAction] = None,
        config: Optional[ExperimentConfig] = None,
    ) -> DecisionResult:
        # config 교체는 base와 동일 로직을 먼저 수행한다 — 가격이 새 cfg의 follower에
        # 걸리도록(base가 나중에 nash_solver를 갈아치우면 하달한 가격이 유실된다).
        if config is not None and config is not self.cfg:
            self.close()
            self.cfg = config
            self.leader = Leader(config)
            self.nash_solver = self._make_follower_solver(config)
            self._pfo_fallback_previous_control = None
        forecast = list(demand_forecast)
        previous = (
            previous_control.copy()
            if previous_control is not None
            else self.previous_control.copy()
            if self.previous_control is not None
            else ControlAction.fixed(self.cfg)
        )
        self._maybe_refresh_signal_prices(state, forecast, previous)
        result = super().decide_with_info(state, forecast, previous_control, config)
        if self._signal_price_meta:
            result.metadata.update(self._signal_price_meta)
            result.control.diagnostics.update(self._signal_price_meta)
        return result

    def _signal_price_p1_bounds(self) -> tuple[float, float]:
        # p1 pair-feasible 범위: p1∈[green_min, green_max] ∧ p2=total−p1∈[green_min, green_max].
        net = self.cfg.network
        total = float(net.effective_green_total)
        lo = max(float(net.green_min), total - float(net.green_max))
        hi = min(float(net.green_max), total - float(net.green_min))
        return lo, hi

    def _global_rollout_ttt_with_green(
        self,
        state: TrafficState,
        previous: ControlAction,
        forecast: List[DemandStep],
        signal: str,
        p1: float,
    ) -> float:
        """ego 신호만 green을 p1로 바꾸고 나머지는 previous 유지, horizon 전역 rollout TTT.

        B1 probe의 truth_horizon_ttt와 같은 구조지만, 미래 legacy trace 대신 현재
        committed control을 horizon 동안 hold한다(closed-loop에서 미래 제어는 미지)."""
        total = float(self.cfg.network.effective_green_total)
        control = previous.copy()
        control.green_times[f"{signal}_p1"] = float(p1)
        control.green_times[f"{signal}_p2"] = float(total - p1)
        _, ttt = self._predict(state, control, forecast)
        return float(ttt)

    def _predict_ttt_and_barrier(
        self,
        state: TrafficState,
        control: ControlAction,
        forecast: List[DemandStep],
    ) -> tuple[float, float]:
        """전역 rollout의 (TTT, barrier). barrier는 B4 활성 시에만 계산(아니면 0).

        barrier = Σ_states Σ_link Σ_seg w_f·(max(0, ρ−ρ_crit)·L_seg·lanes)²·T_c_h —
        rho_crit 초과분을 세그먼트 초과 차량수로 환산해 제곱(interior-point식 soft
        state constraint). TTT를 뽑는 같은 rollout의 상태에서 계산하므로 추가 rollout
        0회 — B4의 metering 가격 유한차분이 TTT와 barrier gradient를 동시에 얻는다."""
        states, ttt = self._predict(state, control, forecast)
        barrier = 0.0
        if self.barrier_price_enabled:
            net = self.cfg.network
            t_c_h = float(self.cfg.simulation.T_c_h)
            seg_veh = float(net.freeway_segment_length_km) * float(net.freeway_lanes)
            rho_crit = float(net.rho_crit)
            for s in states:
                for link in net.freeway_links:
                    for rho in s.freeway_density.get(link, []):
                        excess = max(0.0, float(rho) - rho_crit) * seg_veh
                        barrier += self.barrier_weight * excess * excess * t_c_h
        return float(ttt), float(barrier)

    def _global_rollout_metrics_with_metering(
        self,
        state: TrafficState,
        previous: ControlAction,
        forecast: List[DemandStep],
        ramp: str,
        value: float,
    ) -> tuple[float, float]:
        """해당 ramp만 metering을 value로 바꾸고 나머지는 previous hold, (TTT, barrier)."""
        control = previous.copy()
        control.ramp_metering = dict(previous.ramp_metering)
        control.ramp_metering[ramp] = float(value)
        return self._predict_ttt_and_barrier(state, control, forecast)

    def _global_rollout_ttt_with_vsl(
        self,
        state: TrafficState,
        previous: ControlAction,
        forecast: List[DemandStep],
        link: str,
        seg_key: str,
        value: float,
        vsl_upper: float,
    ) -> float:
        """해당 segment만 VSL을 value로 바꾸고(link fallback 키 동기화) horizon TTT."""
        control = previous.copy()
        control.vsl = dict(previous.vsl)
        control.vsl[seg_key] = float(value)
        control.vsl[link] = min(float(control.vsl.get(link, vsl_upper)), float(value))
        _, ttt = self._predict(state, control, forecast)
        return float(ttt)

    def _maybe_refresh_signal_prices(
        self,
        state: TrafficState,
        forecast: List[DemandStep],
        previous: ControlAction,
    ) -> None:
        follower = self.nash_solver
        if not isinstance(follower, WuFaithfulFollower):
            return
        # 채널별 게이트: 꺼진 채널의 잔존 가격은 항상 제거(A/B 격리).
        if not self.signal_price_enabled:
            follower.signal_marginal_price = None
        if not self.metering_price_enabled:
            follower.metering_marginal_price = None
        if not self.vsl_price_enabled:
            follower.vsl_marginal_price = None
        if not (
            self.signal_price_enabled
            or self.metering_price_enabled
            or self.vsl_price_enabled
        ):
            self._signal_price_meta = {
                "wu_b2_price_enabled": 0.0,
                "wu_b2_price_refreshed": 0.0,
            }
            return
        net = self.cfg.network
        total = float(net.effective_green_total)
        lo, hi = self._signal_price_p1_bounds()

        def clamp(v: float) -> float:
            return max(lo, min(hi, float(v)))

        # ---- 운영점 스냅샷: 모든 채널이 같은 previous(동결 운영점)를 본다 ----
        op_green: Dict[str, float] = (
            {
                signal: clamp(previous.green_times.get(f"{signal}_p1", total / 2.0))
                for signal in net.signals
            }
            if self.signal_price_enabled else {}
        )
        ramp_caps = {r: float(net.ramp_capacity_veh_h[r]) for r in net.ramps}
        op_meter: Dict[str, float] = (
            {
                r: min(max(float(previous.ramp_metering.get(r, ramp_caps[r])), 0.0), ramp_caps[r])
                for r in net.ramps
            }
            if self.metering_price_enabled else {}
        )
        ff = self.cfg.freeway_follower
        vsl_values = [float(v) for v in ff.vsl_set]
        vsl_lower = min(vsl_values) if vsl_values else 0.0
        vsl_upper = max(vsl_values) if vsl_values else 0.0
        op_vsl: Dict[str, float] = {}
        if self.vsl_price_enabled and vsl_values:
            for link in net.freeway_links:
                for index in range(int(net.freeway_segments_per_link)):
                    key = f"{link}__seg{index}"
                    op_vsl[key] = float(segment_vsl(previous, link, index, self.cfg))

        # ---- refresh 판정: 가격 부재 ∨ cadence ∨ event-trigger(운영점 이동) ----
        refresh = (
            (self.signal_price_enabled and follower.signal_marginal_price is None)
            or (self.metering_price_enabled and follower.metering_marginal_price is None)
            or (self.vsl_price_enabled and follower.vsl_marginal_price is None)
        )
        if not refresh and self._leader_global_refresh_active(state):
            refresh = True
        if not refresh:
            # event-trigger: 운영점이 선형화 기준점에서 threshold 이상 이동한 레버가 있으면
            # 재선형화(dual ascent/SQP식 iteration — B1 step35 non-monotone 처방).
            for signal, p1_now in op_green.items():
                ref = float(follower.signal_marginal_price_ref.get(signal, p1_now))
                if abs(p1_now - ref) >= float(self.signal_price_refresh_threshold_sec):
                    refresh = True
                    break
        if not refresh:
            for ramp, x_now in op_meter.items():
                ref = float(follower.metering_marginal_price_ref.get(ramp, x_now))
                if abs(x_now - ref) >= float(self.metering_price_refresh_threshold_veh_h):
                    refresh = True
                    break
        if not refresh:
            for key, v_now in op_vsl.items():
                ref = float(follower.vsl_marginal_price_ref.get(key, v_now))
                if abs(v_now - ref) >= float(self.vsl_price_refresh_threshold_kmh):
                    refresh = True
                    break
        if not refresh:
            self._signal_price_meta = dict(self._signal_price_meta)
            self._signal_price_meta["wu_b2_price_refreshed"] = 0.0
            return

        meta: Dict[str, float] = {"wu_b2_price_enabled": float(self.signal_price_enabled)}

        # ---- green 채널(B2) ----
        if self.signal_price_enabled:
            delta = float(self.signal_price_delta_sec)
            pts: Dict[str, tuple[float, float, float]] = {}
            requests: Dict[str, List[float]] = {}
            for signal, p1_0 in op_green.items():
                p_hi = clamp(p1_0 + delta)
                p_lo = clamp(p1_0 - delta)
                pts[signal] = (p1_0, p_lo, p_hi)
                requests[signal] = [p_lo, p_hi]
            local_costs = follower.local_green_costs(requests, state, previous, forecast[0])
            prices: Dict[str, float] = {}
            refs: Dict[str, float] = {}
            for signal, (p1_0, p_lo, p_hi) in pts.items():
                two_delta = p_hi - p_lo
                if two_delta <= 1.0e-9:
                    g_ext = 0.0
                else:
                    ttt_hi = self._global_rollout_ttt_with_green(
                        state, previous, forecast, signal, p_hi,
                    )
                    ttt_lo = self._global_rollout_ttt_with_green(
                        state, previous, forecast, signal, p_lo,
                    )
                    g_i = (ttt_hi - ttt_lo) / two_delta
                    cost_lo, cost_hi = local_costs[signal]
                    g_ext = g_i - (cost_hi - cost_lo) / two_delta
                prices[signal] = float(g_ext)
                refs[signal] = float(p1_0)
                meta[f"wu_b2_price_{signal}"] = float(g_ext)
                meta[f"wu_b2_price_ref_{signal}"] = float(p1_0)
            follower.signal_marginal_price = prices
            follower.signal_marginal_price_ref = refs
            follower.signal_marginal_price_weight = float(self.signal_price_weight)
            meta["wu_b2_price_delta_sec"] = delta

        # ---- metering 채널(B3, B4 barrier 합산 가능) ----
        # g_ext = d(전역TTT)/dx − d(own-TTS)/dx (+ d(barrier)/dx). 세 미분 모두 같은
        # 동결 운영점에서 — Codex 원안의 "g_i는 commit점·d_local은 snapshot점" 혼합을 제거.
        if self.metering_price_enabled:
            meta["wu_b3_meter_price_enabled"] = 1.0
            meta["wu_b4_barrier_enabled"] = float(self.barrier_price_enabled)
            delta_m = float(self.metering_price_delta_veh_h)
            m_pts: Dict[str, tuple[float, float, float]] = {}
            m_requests: Dict[str, List[float]] = {}
            for ramp, x0 in op_meter.items():
                cap = ramp_caps[ramp]
                m_hi = min(cap, x0 + delta_m)
                m_lo = max(0.0, x0 - delta_m)
                m_pts[ramp] = (x0, m_lo, m_hi)
                m_requests[ramp] = [m_lo, m_hi]
            local_m = follower.local_metering_costs(m_requests, state, previous, forecast[0])
            m_prices: Dict[str, float] = {}
            m_refs: Dict[str, float] = {}
            for ramp, (x0, m_lo, m_hi) in m_pts.items():
                span = m_hi - m_lo
                if span <= 1.0e-9:
                    g_ext = 0.0
                else:
                    ttt_hi, bar_hi = self._global_rollout_metrics_with_metering(
                        state, previous, forecast, ramp, m_hi,
                    )
                    ttt_lo, bar_lo = self._global_rollout_metrics_with_metering(
                        state, previous, forecast, ramp, m_lo,
                    )
                    g_i = (ttt_hi - ttt_lo) / span
                    cost_lo, cost_hi = local_m[ramp]
                    g_ext = g_i - (cost_hi - cost_lo) / span
                    if self.barrier_price_enabled:
                        # barrier는 leader 전용 목적항 — follower own-TTS에 없으므로
                        # d_local 차감 없이 그대로 합산(B4).
                        g_ext += (bar_hi - bar_lo) / span
                m_prices[ramp] = float(g_ext)
                m_refs[ramp] = float(x0)
                meta[f"wu_b3_meter_price_{ramp}"] = float(g_ext)
                meta[f"wu_b3_meter_price_ref_{ramp}"] = float(x0)
            follower.metering_marginal_price = m_prices
            follower.metering_marginal_price_ref = m_refs

        # ---- VSL 채널(B3, raw g_i — d_local 미차감 주의, 기본 OFF) ----
        if self.vsl_price_enabled and op_vsl:
            meta["wu_b3_vsl_price_enabled"] = 1.0
            delta_v = float(self.vsl_price_delta_kmh)
            v_prices: Dict[str, float] = {}
            v_refs: Dict[str, float] = {}
            for key, x0 in op_vsl.items():
                link = key.split("__seg")[0]
                v_hi = min(vsl_upper, x0 + delta_v)
                v_lo = max(vsl_lower, x0 - delta_v)
                span = v_hi - v_lo
                if span <= 1.0e-9:
                    g_i = 0.0
                else:
                    ttt_hi = self._global_rollout_ttt_with_vsl(
                        state, previous, forecast, link, key, v_hi, vsl_upper,
                    )
                    ttt_lo = self._global_rollout_ttt_with_vsl(
                        state, previous, forecast, link, key, v_lo, vsl_upper,
                    )
                    g_i = (ttt_hi - ttt_lo) / span
                v_prices[key] = float(g_i)
                v_refs[key] = float(x0)
            follower.vsl_marginal_price = v_prices
            follower.vsl_marginal_price_ref = v_refs

        self._signal_price_refresh_count += 1
        meta["wu_b2_price_refreshed"] = 1.0
        meta["wu_b2_price_refresh_count"] = float(self._signal_price_refresh_count)
        self._signal_price_meta = meta

    def _pfo_incumbent_fallback_enabled(self) -> bool:
        return bool(getattr(self.cfg.mpc, "stackelberg_enable_pfo_incumbent", True))

    @staticmethod
    def _finite(value: float) -> bool:
        return value == value and value not in (float("inf"), -float("inf"))

    def _pfo_equivalent_action(
        self,
        control: ControlAction,
        state: TrafficState,
        forecast: List[DemandStep],
        previous: ControlAction,
    ) -> tuple[LeaderAction, Dict[str, float]]:
        # PFO response를 leader local search의 target 좌표계로 변환한다.
        diagnostics = dict(control.diagnostics)
        raw_np = float(diagnostics.get("wu_faithful_sum_nin", control.N_P_star))
        if not self._finite(raw_np):
            raw_np = float(control.N_P_star)
        raw_nuf = float(sum(float(v) for v in control.ramp_metering.values()))
        if raw_nuf <= 1.0e-9 and self._finite(float(control.N_UF_star)):
            raw_nuf = float(control.N_UF_star)
        bounds = self.leader._candidate_bounds(state, previous, forecast[0], forecast)
        clipped_np = float(min(max(raw_np, bounds.np_lower), bounds.np_upper))
        clipped_nuf = float(min(max(raw_nuf, bounds.nuf_lower), bounds.nuf_upper))
        return LeaderAction(clipped_np, clipped_nuf), {
            "leader_pfo_incumbent_N_P_star": clipped_np,
            "leader_pfo_incumbent_N_UF_star": clipped_nuf,
            "leader_pfo_incumbent_raw_N_P_star": raw_np,
            "leader_pfo_incumbent_raw_N_UF_star": raw_nuf,
            "leader_pfo_incumbent_N_P_clipped": float(abs(clipped_np - raw_np) > 1.0e-9),
            "leader_pfo_incumbent_N_UF_clipped": float(abs(clipped_nuf - raw_nuf) > 1.0e-9),
        }

    def _evaluate_fallback_candidates(
        self,
        state: TrafficState,
        forecast: List[DemandStep],
        previous: ControlAction,
        start_index: int,
    ) -> List[_LeaderCandidateEvaluation]:
        self._pfo_incumbent_center: Optional[LeaderAction] = None
        self._pfo_incumbent_eval: Optional[_LeaderCandidateEvaluation] = None
        if not self._pfo_incumbent_fallback_enabled():
            return []
        pfo_previous = previous.copy()
        pfo_previous.N_P_star = 0.0
        pfo_previous.N_UF_star = 0.0
        pfo_previous.inflow_outflow_allocation = {}
        pfo_nash = self.nash_solver.solve(state.copy(), None, forecast, pfo_previous)
        action, action_meta = self._pfo_equivalent_action(pfo_nash.control, state, forecast, previous)
        pfo_nash.control.N_P_star = float(action.N_P_star)
        pfo_nash.control.N_UF_star = float(action.N_UF_star)
        pfo_nash.control.diagnostics.update(action_meta)
        predicted_states, follower_ttt, rollout_used = self._leader_evaluation_base(
            state,
            pfo_nash,
            forecast,
        )
        objective_terms = self.leader.objective_terms(
            predicted_states,
            pfo_nash.control,
            previous,
            follower_ttt,
            pfo_nash.converged,
            pfo_nash.residual_objective,
            pfo_nash.residual_control,
        )
        metadata = {
            "leader_response_proxy_state_count": float(len(predicted_states)),
            "leader_pfo_incumbent_active": 1.0,
            "leader_pfo_incumbent_candidate": 1.0,
            "leader_pfo_incumbent_objective": float(objective_terms["leader_total_objective"]),
            **action_meta,
        }
        pfo_eval = _LeaderCandidateEvaluation(
            index=start_index,
            action=action,
            nash=pfo_nash,
            objective=float(objective_terms["leader_total_objective"]),
            objective_terms=objective_terms,
            metadata=metadata,
            rollout_used=rollout_used,
            stage="fallback_pfo",
        )
        self._pfo_incumbent_center = action
        self._pfo_incumbent_eval = pfo_eval
        self._append_progress_event(
            event="candidate_evaluated",
            stage="fallback_pfo",
            completed=1,
            total=1,
            evaluation=pfo_eval,
            best_objective=pfo_eval.objective,
        )
        return [pfo_eval]

    def _pfo_centered_previous(self, previous: ControlAction) -> ControlAction:
        center = getattr(self, "_pfo_incumbent_center", None)
        if center is None:
            return previous
        seeded = previous.copy()
        seeded.N_P_star = float(center.N_P_star)
        seeded.N_UF_star = float(center.N_UF_star)
        return seeded

    def _grid_leader_search(
        self,
        state: TrafficState,
        forecast: List[DemandStep],
        previous: ControlAction,
        global_refresh: bool,
        fallback_incumbent_obj: float,
    ):
        return super()._grid_leader_search(
            state,
            forecast,
            self._pfo_centered_previous(previous),
            global_refresh,
            fallback_incumbent_obj,
        )

    @staticmethod
    def _leader_action_key(action: LeaderAction) -> tuple[float, float]:
        return (round(float(action.N_P_star), 6), round(float(action.N_UF_star), 6))

    def _pfo_global_scout_evaluations(
        self,
        state: TrafficState,
        forecast: List[DemandStep],
        previous: ControlAction,
        local_evaluations: List[_LeaderCandidateEvaluation],
        fallback_incumbent_obj: float,
    ) -> tuple[List[_LeaderCandidateEvaluation], Dict[str, float]]:
        bounds = self.leader._candidate_bounds(state, previous, forecast[0], forecast)
        np_lower, np_upper = float(bounds.np_lower), float(bounds.np_upper)
        nuf_lower, nuf_upper = float(bounds.nuf_lower), float(bounds.nuf_upper)

        def clipped(np_value: float, nuf_value: float) -> LeaderAction:
            return LeaderAction(
                float(min(max(float(np_value), np_lower), np_upper)),
                float(min(max(float(nuf_value), nuf_lower), nuf_upper)),
            )

        seed_actions = self._unique_leader_actions(
            [LeaderAction(previous.N_P_star, previous.N_UF_star)]
            + self._continuous_seed_actions(
                previous,
                bounds,
                np_lower,
                np_upper,
                nuf_lower,
                nuf_upper,
                clipped,
            )
        )
        scout_top_k = max(1, min(2, int(self.cfg.mpc.leader_continuous_prefilter_top_k)))
        scout_actions, scout_meta = self._continuous_prefilter_actions(
            seed_actions,
            state,
            forecast,
            previous,
            np_lower,
            np_upper,
            nuf_lower,
            nuf_upper,
            prefilter_samples=int(self.cfg.mpc.leader_continuous_prefilter_samples),
            prefilter_top_k=scout_top_k,
        )
        seen = {self._leader_action_key(item.action) for item in local_evaluations}
        scout_actions = [
            action for action in scout_actions
            if self._leader_action_key(action) not in seen
        ]
        full_budget = max(
            0,
            min(2, int(self.cfg.mpc.leader_continuous_max_evals) - len(local_evaluations)),
        )
        if full_budget <= 0 or not scout_actions:
            return [], {
                "leader_pfo_anchor_scout_full_budget": float(full_budget),
                "leader_pfo_anchor_scout_candidate_count": float(len(scout_actions)),
                "leader_pfo_anchor_scout_full_evaluated_count": 0.0,
                "leader_pfo_anchor_scout_top_k": float(scout_top_k),
            }
        incumbent = min(
            [float(fallback_incumbent_obj)]
            + [float(item.objective) for item in local_evaluations],
        )
        scout_evals, _ = self._evaluate_continuous_action_set(
            scout_actions[:full_budget],
            state,
            forecast,
            previous,
            stage="continuous_global_scout",
            index_start=len(local_evaluations),
            incumbent_obj=incumbent,
        )
        prefixed = {
            f"leader_pfo_anchor_scout_{key}": float(value)
            for key, value in scout_meta.items()
            if isinstance(value, (int, float, bool))
        }
        prefixed.update({
            "leader_pfo_anchor_scout_full_budget": float(full_budget),
            "leader_pfo_anchor_scout_candidate_count": float(len(scout_actions)),
            "leader_pfo_anchor_scout_full_evaluated_count": float(len(scout_evals)),
            "leader_pfo_anchor_scout_top_k": float(scout_top_k),
        })
        return scout_evals, prefixed

    def _continuous_leader_search(
        self,
        state: TrafficState,
        forecast: List[DemandStep],
        previous: ControlAction,
        global_refresh: bool,
        fallback_incumbent_obj: float,
    ):
        centered_previous = self._pfo_centered_previous(previous)
        if global_refresh and getattr(self, "_pfo_incumbent_center", None) is not None:
            local_evals, base_meta, proxy_meta, refined_meta = super()._continuous_leader_search(
                state,
                forecast,
                centered_previous,
                False,
                fallback_incumbent_obj,
            )
            scout_evals, scout_meta = self._pfo_global_scout_evaluations(
                state,
                forecast,
                centered_previous,
                local_evals,
                fallback_incumbent_obj,
            )
            full_evals = local_evals + scout_evals
            base_meta.update(scout_meta)
            base_meta.update({
                "leader_pfo_anchor_global_hybrid_active": 1.0,
                "leader_pfo_anchor_local_full_evaluated_count": float(len(local_evals)),
                "leader_pfo_anchor_total_full_evaluated_count": float(len(full_evals)),
                "leader_candidate_global_refresh": 1.0,
                "leader_candidate_coarse_global": 1.0,
                "leader_candidate_coarse_local": 0.0,
            })
            return full_evals, base_meta, proxy_meta, refined_meta
        return super()._continuous_leader_search(
            state,
            forecast,
            centered_previous,
            global_refresh,
            fallback_incumbent_obj,
        )

    def _select_with_fallback_guard(
        self,
        leader_evaluations: List[_LeaderCandidateEvaluation],
        fallback_evaluations: List[_LeaderCandidateEvaluation],
    ):
        best, metadata = super()._select_with_fallback_guard(leader_evaluations, fallback_evaluations)
        pfo_eval = getattr(self, "_pfo_incumbent_eval", None)
        pfo_tie_break_selected = False
        if pfo_eval is not None and best.stage != "fallback_pfo":
            eps = 1.0e-9
            if float(best.objective) >= float(pfo_eval.objective) - eps:
                best = pfo_eval
                pfo_tie_break_selected = True
                metadata["leader_fallback_guard_selected"] = 1.0
                metadata["leader_fallback_guard_selected_pfo"] = 1.0
                metadata["leader_fallback_guard_rejected_leader"] = 1.0
        metadata.update({
            "leader_pfo_incumbent_active": float(pfo_eval is not None),
            "leader_pfo_incumbent_selected": float(best.stage == "fallback_pfo"),
            "leader_pfo_incumbent_tie_break_selected": float(pfo_tie_break_selected),
            "leader_pfo_incumbent_N_P_star": float(pfo_eval.action.N_P_star) if pfo_eval else 0.0,
            "leader_pfo_incumbent_N_UF_star": float(pfo_eval.action.N_UF_star) if pfo_eval else 0.0,
            "leader_pfo_incumbent_objective": float(pfo_eval.objective) if pfo_eval else 0.0,
            "leader_pfo_incumbent_local_center_used": float(
                pfo_eval is not None and getattr(self, "_pfo_incumbent_center", None) is not None
            ),
        })
        # λ step 간 적분 갱신(A1+A2): **선택된 후보**의 λ_next만 follower 영속 가격에 commit한다
        # (후보별 solve는 diagnostics로만 λ_next를 내놓고 self._lambda_P를 건드리지 않는다).
        # PFO incumbent 선택 시(stage=="fallback_pfo", leader=None이라 lambda_next 없음) λ는 갱신
        # 하지 않고 유지한다 — 커밋된 제어가 PFO면 λ는 plant에 영향이 없으므로 새 정보가 없다.
        lam_next = best.nash.control.diagnostics.get("wu_faithful_lambda_next")
        if lam_next is not None:
            self.nash_solver._lambda_P = float(lam_next)
        metadata["leader_lambda_np_committed"] = float(lam_next is not None)
        return best, metadata

    def _proxy_score_candidate(
        self,
        index: int,
        action: LeaderAction,
        state: TrafficState,
        forecast: List[DemandStep],
        previous: ControlAction,
    ) -> Dict[str, float]:
        """action-aware prefilter proxy(베이스의 action-blind else 분기 대체).

        베이스 `_proxy_score_candidate`의 else 분기는 현재 state만 읽어 모든 후보의 점수가
        동일했다(prefilter가 index 순서로 무작위 통과). 여기서는 후보-의존으로 만든다:
        (1) follower의 hard-budget 분기(N_UF_star>0)를 simplex 탐색 없이 용량비례 배분으로
        근사해 candidate metering을 구성하고, (2) leader full 평가와 동일한 plant rollout
        (`self._predict`)으로 예측 상태를 만들어 `objective_terms`로 채점한다(leader는
        centralized이므로 정보 철학 위반 아님).

        한계: green의 λ(N_P) 응답은 근사하지 않는다 — N_P 차원은 predicted states의
        protected accumulation 항을 통해서만 간접 반영되며, 주된 후보-분별력은
        N_UF(metering) 차원에서 나온다."""
        # base full 평가(_evaluate_full_candidate)는 follower-feasible로 투영된 좌표를
        # 채점하므로, prefilter proxy도 동일 좌표계에서 채점해야 랭킹이 어긋나지 않는다
        # (base _proxy_score_candidate 1537-1539행과 동일한 pre-projection).
        action, _projection_meta = self._project_action_to_follower_feasible_np(
            action, state, forecast, previous
        )
        control = previous.copy()
        control.N_P_star = float(action.N_P_star)
        control.N_UF_star = float(action.N_UF_star)
        net = self.cfg.network
        if float(action.N_UF_star) > 0.0:
            # follower hard-budget 분기 근사: link budget = ω_F[link]·N_UF_star를
            # 소유 ramp들에 용량비례로 배분(각 ramp은 capacity로 clamp).
            follower = self.nash_solver
            for link in net.freeway_links:
                model = follower._local_freeway_models[link]
                owned = list(model.owned_ramps)
                if not owned:
                    continue
                caps = {r: float(net.ramp_capacity_veh_h[r]) for r in owned}
                cap_sum = sum(caps.values())
                if cap_sum <= 0.0:
                    continue
                omega = float(follower._wu._omega_f.get(link, 0.0))
                budget = min(max(omega * float(action.N_UF_star), 0.0), cap_sum)
                for ramp in owned:
                    share = budget * (caps[ramp] / cap_sum)
                    control.ramp_metering[ramp] = float(min(max(share, 0.0), caps[ramp]))
        # N_UF_star<=0이면 follower autonomous 분기에 대응 — previous.ramp_metering 유지.
        states, rollout_ttt = self._predict(state, control, forecast)
        terms = self.leader.objective_terms(
            states,
            control,
            previous,
            float(rollout_ttt),
            True,
            0.0,
            0.0,
        )
        return {
            "index": float(index),
            "N_P_star": float(action.N_P_star),
            "N_UF_star": float(action.N_UF_star),
            "objective": float(terms["leader_total_objective"]),
            "base": float(terms["leader_objective_base"]),
            "follower_ttt": float(terms["leader_follower_ttt_base"]),
            "spillback_violation": 0.0,
        }

    def _evaluate_candidate_set(
        self,
        candidates: List[LeaderAction],
        selected_indices: List[int],
        state: TrafficState,
        forecast: List[DemandStep],
        previous: ControlAction,
        stage: str = "coarse",
        index_offset: int = 0,
        incumbent_obj: float = float("inf"),
    ) -> List[_LeaderCandidateEvaluation]:
        """후보 평가를 serial in-process로 강제한다(미변경 베이스의 worker 우회).

        베이스 `_evaluate_candidate_set`는 module-level `_stackelberg_candidate_worker`로
        후보를 평가하는데, 그 worker는 항상 베이스 `StackelbergMPCController`를 생성해
        nash_solver가 NashSolver가 된다(우리 follower 주입이 무시됨). 그래서 worker를 쓰지
        않고 self의 `_evaluate_full_candidate`(=self.nash_solver=WuFaithfulFollower)를 직접
        serial로 호출한다. metering 좌표하강이 무거우므로 process 풀 없이도 충분하다."""
        if not selected_indices:
            raise ValueError("Stackelberg leader prefilter removed every candidate.")
        results: List[_LeaderCandidateEvaluation] = []
        stage_incumbent = float(incumbent_obj)
        for idx in selected_indices:
            result = self._evaluate_full_candidate(
                idx + index_offset,
                candidates[idx],
                state,
                forecast,
                previous,
                stage=stage,
                incumbent_obj=stage_incumbent,
            )
            results.append(result)
            stage_incumbent = min(stage_incumbent, float(result.objective))
        diag: Dict[str, float] = {
            "leader_candidate_parallel_backend_serial": 1.0,
            "leader_candidate_parallel_backend_thread": 0.0,
            "leader_candidate_parallel_backend_process": 0.0,
            "leader_candidate_parallel_workers": 1.0,
            "leader_candidate_wu_metered_serial_override": 1.0,
        }
        for result in results:
            result.metadata.update(diag)
        return results
