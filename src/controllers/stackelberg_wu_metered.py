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
    StackelbergMPCController,
    _LeaderCandidateEvaluation,
)
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.controllers.leader import LeaderAction


class StackelbergWuMeteredController(StackelbergMPCController):
    """follower=WuFaithfulFollower(metering-PFO)로 고정한 Stackelberg 컨트롤러."""

    def _make_follower_solver(self, cfg: ExperimentConfig):
        return WuFaithfulFollower(cfg)

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
