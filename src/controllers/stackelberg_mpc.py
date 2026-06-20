from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.leader import Leader, LeaderAction, leader_metadata
from src.controllers.nash_solver import NashResult, NashSolver
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState


@dataclass
class DecisionResult:
    control: ControlAction
    leader_objective: float
    nash: NashResult
    metadata: Dict[str, float]


@dataclass
class _LeaderCandidateEvaluation:
    index: int
    action: LeaderAction
    nash: NashResult
    objective: float
    objective_terms: Dict[str, float]
    metadata: Dict[str, float]
    rollout_used: bool
    stage: str = "coarse"


def _stackelberg_candidate_worker(payload: dict) -> _LeaderCandidateEvaluation:
    controller = StackelbergMPCController(payload["cfg"])
    return controller._evaluate_full_candidate(
        payload["index"],
        payload["action"],
        payload["state"],
        payload["forecast"],
        payload["previous"],
        payload.get("stage", "coarse"),
        payload.get("incumbent_obj", float("inf")),
    )


class StackelbergMPCController:
    """Spec-first Stackelberg MPC controller.

    This implementation is intentionally self-contained under `src/` and does
    not import any root-level historical controller modules. Leader actions are
    enumerated, follower responses are solved by deterministic projection and
    queue-balancing heuristics, and the default leader base uses the follower
    response objective rather than an additional full-system rollout.
    """

    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg
        self.leader = Leader(cfg)
        self.nash_solver = self._make_follower_solver(cfg)
        self.previous_control: Optional[ControlAction] = None
        self.last_decision: Optional[DecisionResult] = None
        self._pfo_fallback_previous_control: Optional[ControlAction] = None
        self._leader_process_pool: Optional[ProcessPoolExecutor] = None
        self._leader_process_pool_workers: int = 0

    def close(self) -> None:
        if self._leader_process_pool is not None:
            self._leader_process_pool.shutdown(wait=False, cancel_futures=True)
            self._leader_process_pool = None
            self._leader_process_pool_workers = 0

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _make_follower_solver(self, cfg: ExperimentConfig):
        if cfg.mpc.follower_solver_mode == "distributed":
            return DistributedCoordinator(cfg)
        return NashSolver(cfg)

    def decide(
        self,
        state: TrafficState,
        demand_forecast: Iterable[DemandStep],
        previous_control: Optional[ControlAction] = None,
        config: Optional[ExperimentConfig] = None,
    ) -> ControlAction:
        result = self.decide_with_info(state, demand_forecast, previous_control, config)
        return result.control

    def decide_with_info(
        self,
        state: TrafficState,
        demand_forecast: Iterable[DemandStep],
        previous_control: Optional[ControlAction] = None,
        config: Optional[ExperimentConfig] = None,
    ) -> DecisionResult:
        if config is not None and config is not self.cfg:
            self.close()
            self.cfg = config
            self.leader = Leader(config)
            self.nash_solver = self._make_follower_solver(config)
            self._pfo_fallback_previous_control = None
        forecast = list(demand_forecast)
        if not forecast:
            raise ValueError("StackelbergMPCController requires a non-empty demand forecast.")
        previous = (
            previous_control.copy()
            if previous_control is not None
            else self.previous_control.copy()
            if self.previous_control is not None
            else ControlAction.fixed(self.cfg)
        )
        previous = self._normalize_previous_leader_reference(previous)
        global_refresh = self._leader_global_refresh_active(state)
        if global_refresh:
            coarse_candidates = self.leader.candidates(state, previous, forecast[0], forecast=forecast)
            coarse_stage = "coarse_global"
        else:
            previous_leader = LeaderAction(previous.N_P_star, previous.N_UF_star)
            coarse_candidates = self.leader.refined_candidates(
                state,
                previous_leader,
                previous,
                forecast[0],
                forecast=forecast,
                count=self.cfg.mpc.leader_candidate_count,
            )
            coarse_stage = "coarse_local"
        fallback_start_index = len(coarse_candidates) + max(0, int(self.cfg.mpc.leader_refinement_candidate_count))
        fallback_evaluations = self._evaluate_fallback_candidates(
            state,
            forecast,
            previous,
            start_index=fallback_start_index,
        )
        fallback_incumbent_obj = min(
            (item.objective for item in fallback_evaluations),
            default=float("inf"),
        )
        selected_indices, proxy_metadata = self._prefilter_leader_candidates(
            coarse_candidates,
            state,
            forecast,
            previous,
            global_scope=global_refresh,
        )
        coarse_evaluations = self._evaluate_candidate_set(
            coarse_candidates,
            selected_indices,
            state,
            forecast,
            previous,
            stage=coarse_stage,
            incumbent_obj=fallback_incumbent_obj,
        )
        coarse_best = min(coarse_evaluations, key=lambda item: item.objective)
        refined_candidates = self._unique_leader_actions(
            self.leader.refined_candidates(
                state,
                coarse_best.action,
                previous,
                forecast[0],
                forecast=forecast,
            )
        )
        refined_indices: list[int] = []
        refined_proxy_metadata: Dict[str, float] = {}
        if refined_candidates:
            refined_indices, raw_refined_proxy_metadata = self._prefilter_leader_candidates(
                refined_candidates,
                state,
                forecast,
                previous,
                global_scope=False,
            )
            refined_proxy_metadata = self._stage_prefilter_metadata(
                raw_refined_proxy_metadata,
                "refined",
            )
        refined_evaluations = self._evaluate_candidate_set(
            refined_candidates,
            refined_indices,
            state,
            forecast,
            previous,
            stage="refined",
            index_offset=len(coarse_candidates),
            incumbent_obj=min(coarse_best.objective, fallback_incumbent_obj),
        ) if refined_candidates else []
        full_evaluations = coarse_evaluations + refined_evaluations
        base_metadata = leader_metadata(coarse_candidates + refined_candidates)
        base_metadata.update(self.leader.candidate_bound_metadata(state, previous, forecast[0], forecast=forecast))
        base_metadata.update(self._forecast_demand_metadata(forecast))
        def candidate_meta_any(key: str) -> float:
            return float(max((item.metadata.get(key, 0.0) for item in full_evaluations), default=0.0))

        base_metadata.update({
            "leader_candidate_coarse_count": float(len(coarse_candidates)),
            "leader_candidate_coarse_evaluated_count": float(len(coarse_evaluations)),
            "leader_candidate_refined_count": float(len(refined_candidates)),
            "leader_candidate_refined_evaluated_count": float(len(refined_evaluations)),
            "leader_candidate_refinement_active": float(bool(refined_candidates)),
            "leader_candidate_global_refresh": float(global_refresh),
            "leader_candidate_coarse_global": float(coarse_stage == "coarse_global"),
            "leader_candidate_coarse_local": float(coarse_stage == "coarse_local"),
            "leader_fallback_incumbent_seed_active": float(fallback_incumbent_obj < float("inf")),
            "leader_fallback_incumbent_objective": float(
                fallback_incumbent_obj if fallback_incumbent_obj < float("inf") else 0.0
            ),
            "leader_candidate_parallel_backend_serial": candidate_meta_any(
                "leader_candidate_parallel_backend_serial"
            ),
            "leader_candidate_parallel_backend_thread": candidate_meta_any(
                "leader_candidate_parallel_backend_thread"
            ),
            "leader_candidate_parallel_backend_process": candidate_meta_any(
                "leader_candidate_parallel_backend_process"
            ),
            "leader_candidate_process_pool_reuse_enabled": candidate_meta_any(
                "leader_candidate_process_pool_reuse_enabled"
            ),
            "leader_candidate_process_pool_reused_existing": candidate_meta_any(
                "leader_candidate_process_pool_reused_existing"
            ),
            "leader_candidate_incumbent_any_active": float(any(
                item.metadata.get("leader_candidate_incumbent_active", 0.0) > 0.5
                for item in full_evaluations
            )),
            "leader_candidate_follower_early_terminated_candidates_total": float(sum(
                item.metadata.get("leader_candidate_follower_early_terminated_candidates", 0.0)
                for item in full_evaluations
            )),
        })
        all_evaluations = full_evaluations + fallback_evaluations
        evaluations: list[dict[str, object]] = [
            {
                "index": float(item.index),
                "N_P_star": float(item.action.N_P_star),
                "N_UF_star": float(item.action.N_UF_star),
                "objective": float(item.objective),
                "base": float(item.objective_terms["leader_objective_base"]),
                "follower_ttt": float(item.objective_terms["leader_follower_ttt_base"]),
                "stage": item.stage,
            }
            for item in all_evaluations
        ]
        best_eval, fallback_metadata = self._select_with_fallback_guard(
            full_evaluations,
            fallback_evaluations,
        )
        metadata = dict(base_metadata)
        metadata.update(proxy_metadata)
        metadata.update(refined_proxy_metadata)
        metadata.update(fallback_metadata)
        metadata.update({
            "N_P_crit": float(self.cfg.leader.N_P_crit_veh),
            "nash_iterations": float(best_eval.nash.iterations),
            "nash_converged": 1.0 if best_eval.nash.converged else 0.0,
            "nash_residual_control": best_eval.nash.residual_control,
            "nash_residual_objective": best_eval.nash.residual_objective,
            "leader_rollout_prediction_used": 1.0 if best_eval.rollout_used else 0.0,
            "leader_follower_response_objective_used": 0.0 if best_eval.rollout_used else 1.0,
            "leader_response_proxy_state_count": float(best_eval.metadata.get("leader_response_proxy_state_count", 0.0)),
            "leader_candidate_full_evaluated_count": float(len(full_evaluations)),
            "leader_fallback_evaluated_count": float(len(fallback_evaluations)),
        })
        metadata.update(best_eval.metadata)
        metadata.update(best_eval.objective_terms)
        best = DecisionResult(best_eval.nash.control, best_eval.objective, best_eval.nash, metadata)
        assert best is not None
        best.metadata.update(self._candidate_evaluation_metadata(evaluations, best.control, best_eval))
        best.control.diagnostics.update(best.metadata)
        best.control.diagnostics["leader_objective"] = best.leader_objective
        self.previous_control = best.control.copy()
        self.last_decision = best
        return best

    def _normalize_previous_leader_reference(self, previous: ControlAction) -> ControlAction:
        out = previous.copy()
        if out.N_UF_star > 1.0e-9:
            return out
        net = self.cfg.network
        release = sum(float(out.ramp_metering.get(ramp, 0.0)) for ramp in net.ramps)
        if release >= 0.95 * float(net.total_ramp_capacity):
            out.N_UF_star = float(net.total_ramp_capacity)
        return out

    def _leader_global_refresh_active(self, state: TrafficState) -> bool:
        interval = max(float(self.cfg.simulation.control_interval), 1.0e-9)
        step_index = int(round(float(state.time_sec) / interval))
        refresh_steps = max(1, int(round(float(self.cfg.mpc.leader_global_refresh_sec) / interval)))
        return step_index == 0 or step_index % refresh_steps == 0

    def _fallback_full_refresh_active(self, state: TrafficState) -> bool:
        interval = max(float(self.cfg.simulation.control_interval), 1.0e-9)
        step_index = int(round(float(state.time_sec) / interval))
        refresh_steps = max(1, int(round(float(self.cfg.mpc.stackelberg_fallback_full_refresh_sec) / interval)))
        return step_index == 0 or step_index % refresh_steps == 0

    def _unique_leader_actions(self, actions: list[LeaderAction]) -> list[LeaderAction]:
        seen: set[tuple[float, float]] = set()
        out: list[LeaderAction] = []
        for action in actions:
            key = (round(float(action.N_P_star), 6), round(float(action.N_UF_star), 6))
            if key in seen:
                continue
            seen.add(key)
            out.append(action)
        return out

    def _stage_prefilter_metadata(self, metadata: Dict[str, float], stage: str) -> Dict[str, float]:
        prefix = f"leader_candidate_{stage}_"
        out: Dict[str, float] = {}
        for key, value in metadata.items():
            if key.startswith("leader_candidate_"):
                out[prefix + key[len("leader_candidate_"):]] = float(value)
            else:
                out[f"{prefix}{key}"] = float(value)
        return out

    def _candidate_eval_config(self) -> ExperimentConfig:
        if (
            self.cfg.mpc.stackelberg_leader_parallel_backend == "process"
            and self.cfg.mpc.grid_parallel_backend == "process"
        ):
            return self.cfg.with_updates({
                "mpc": {
                    "grid_parallel_backend": self.cfg.mpc.stackelberg_inner_backend_when_outer_process,
                    "stackelberg_leader_parallel_backend": "serial",
                }
            })
        return self.cfg

    def _leader_process_executor(self, workers: int) -> tuple[ProcessPoolExecutor, bool]:
        if self._leader_process_pool is not None and self._leader_process_pool_workers == workers:
            return self._leader_process_pool, True
        self.close()
        self._leader_process_pool = ProcessPoolExecutor(max_workers=workers)
        self._leader_process_pool_workers = workers
        return self._leader_process_pool, False

    def _evaluate_full_candidate(
        self,
        index: int,
        action: LeaderAction,
        state: TrafficState,
        forecast: list[DemandStep],
        previous: ControlAction,
        stage: str = "coarse",
        incumbent_obj: float = float("inf"),
    ) -> _LeaderCandidateEvaluation:
        if isinstance(self.nash_solver, DistributedCoordinator):
            nash = self.nash_solver.solve(
                state.copy(),
                action,
                forecast,
                previous,
                leader_incumbent_obj=incumbent_obj,
            )
        else:
            nash = self.nash_solver.solve(state.copy(), action, forecast, previous)
        predicted_states, follower_ttt, rollout_used = self._leader_evaluation_base(
            state,
            nash,
            forecast,
        )
        objective_terms = self.leader.objective_terms(
            predicted_states,
            nash.control,
            previous,
            follower_ttt,
            nash.converged,
            nash.residual_objective,
            nash.residual_control,
        )
        metadata = {
            "leader_response_proxy_state_count": float(len(predicted_states)),
            "leader_candidate_incumbent_active": float(incumbent_obj < float("inf")),
            "leader_candidate_incumbent_objective": float(incumbent_obj if incumbent_obj < float("inf") else 0.0),
            "leader_candidate_follower_early_terminated_candidates": float(
                nash.diagnostics.get(
                    "distributed_grid_early_terminated_candidates",
                    nash.control.diagnostics.get("distributed_grid_early_terminated_candidates", 0.0),
                )
            ),
        }
        return _LeaderCandidateEvaluation(
            index=index,
            action=action,
            nash=nash,
            objective=float(objective_terms["leader_total_objective"]),
            objective_terms=objective_terms,
            metadata=metadata,
            rollout_used=rollout_used,
            stage=stage,
        )

    def _evaluation_terminal_proxy(self, evaluation: _LeaderCandidateEvaluation) -> float:
        diag = dict(evaluation.nash.diagnostics)
        diag.update(evaluation.nash.control.diagnostics)
        return float(diag.get("distributed_response_terminal_proxy_vehicles", 0.0))

    def _evaluation_completed_proxy(self, evaluation: _LeaderCandidateEvaluation) -> float:
        diag = dict(evaluation.nash.diagnostics)
        diag.update(evaluation.nash.control.diagnostics)
        return float(diag.get("distributed_response_mainline_exit_veh", 0.0)) + float(
            diag.get("distributed_response_boundary_out_sink_veh", 0.0)
        )

    def _fallback_guard_rejects(
        self,
        leader_best: _LeaderCandidateEvaluation,
        fallback_best: _LeaderCandidateEvaluation,
    ) -> tuple[bool, Dict[str, float]]:
        leader_terminal = self._evaluation_terminal_proxy(leader_best)
        fallback_terminal = self._evaluation_terminal_proxy(fallback_best)
        leader_completed = self._evaluation_completed_proxy(leader_best)
        fallback_completed = self._evaluation_completed_proxy(fallback_best)
        leader_obj = float(leader_best.objective)
        fallback_obj = float(fallback_best.objective)
        terminal_margin = max(20.0, 0.05 * max(fallback_terminal, 1.0))
        completed_margin = max(1.0, 0.05 * max(fallback_completed, 1.0))
        terminal_worse = leader_terminal > fallback_terminal + terminal_margin
        terminal_severe = leader_terminal > fallback_terminal + max(100.0, 0.25 * max(fallback_terminal, 1.0))
        completed_worse = leader_completed + completed_margin < fallback_completed
        completed_severe = leader_completed + max(2.0, 0.10 * max(fallback_completed, 1.0)) < fallback_completed
        objective_worse = leader_obj >= fallback_obj - 1.0e-12
        objective_gain = max(0.0, fallback_obj - leader_obj)
        required_gain = 0.05 * max(abs(fallback_obj), 1.0)
        insufficient_gain = objective_gain < required_gain
        reject = bool(
            objective_worse
            or terminal_severe
            or completed_severe
            or ((terminal_worse or completed_worse) and insufficient_gain)
        )
        return reject, {
            "leader_fallback_guard_rejected_leader": float(reject),
            "leader_fallback_guard_terminal_worse": float(terminal_worse),
            "leader_fallback_guard_terminal_severe": float(terminal_severe),
            "leader_fallback_guard_completed_worse": float(completed_worse),
            "leader_fallback_guard_completed_severe": float(completed_severe),
            "leader_fallback_guard_objective_worse": float(objective_worse),
            "leader_fallback_guard_insufficient_gain": float(insufficient_gain),
            "leader_fallback_guard_leader_objective": leader_obj,
            "leader_fallback_guard_fallback_objective": fallback_obj,
            "leader_fallback_guard_objective_gain": float(objective_gain),
            "leader_fallback_guard_required_gain": float(required_gain),
            "leader_fallback_guard_leader_terminal_proxy_veh": leader_terminal,
            "leader_fallback_guard_fallback_terminal_proxy_veh": fallback_terminal,
            "leader_fallback_guard_leader_completed_proxy_veh": leader_completed,
            "leader_fallback_guard_fallback_completed_proxy_veh": fallback_completed,
        }

    def _select_with_fallback_guard(
        self,
        leader_evaluations: list[_LeaderCandidateEvaluation],
        fallback_evaluations: list[_LeaderCandidateEvaluation],
    ) -> tuple[_LeaderCandidateEvaluation, Dict[str, float]]:
        if not leader_evaluations:
            raise ValueError("Stackelberg leader produced no evaluated candidates.")
        leader_best = min(leader_evaluations, key=lambda item: item.objective)
        metadata: Dict[str, float] = {
            "leader_fallback_guard_active": 1.0,
            "leader_fallback_guard_selected": 0.0,
            "leader_fallback_guard_selected_pfo": 0.0,
            "leader_fallback_guard_selected_no_control": 0.0,
            "leader_fallback_candidate_count": float(len(fallback_evaluations)),
        }
        if not fallback_evaluations:
            metadata["leader_fallback_guard_rejected_leader"] = 0.0
            return leader_best, metadata
        fallback_best = min(fallback_evaluations, key=lambda item: item.objective)
        reject, guard_meta = self._fallback_guard_rejects(leader_best, fallback_best)
        metadata.update(guard_meta)
        metadata.update({
            "leader_fallback_best_stage_pfo": float(fallback_best.stage == "fallback_pfo"),
            "leader_fallback_best_stage_no_control": float(fallback_best.stage == "fallback_no_control"),
            "leader_fallback_best_objective": float(fallback_best.objective),
            "leader_fallback_best_terminal_proxy_veh": self._evaluation_terminal_proxy(fallback_best),
            "leader_fallback_best_completed_proxy_veh": self._evaluation_completed_proxy(fallback_best),
        })
        for fallback in fallback_evaluations:
            prefix = f"leader_{fallback.stage}"
            metadata[f"{prefix}_objective"] = float(fallback.objective)
            metadata[f"{prefix}_terminal_proxy_veh"] = self._evaluation_terminal_proxy(fallback)
            metadata[f"{prefix}_completed_proxy_veh"] = self._evaluation_completed_proxy(fallback)
        if reject:
            metadata["leader_fallback_guard_selected"] = 1.0
            metadata["leader_fallback_guard_selected_pfo"] = float(fallback_best.stage == "fallback_pfo")
            metadata["leader_fallback_guard_selected_no_control"] = float(
                fallback_best.stage == "fallback_no_control"
            )
            return fallback_best, metadata
        return leader_best, metadata

    def _evaluate_fallback_candidates(
        self,
        state: TrafficState,
        forecast: list[DemandStep],
        previous: ControlAction,
        start_index: int,
    ) -> list[_LeaderCandidateEvaluation]:
        if not isinstance(self.nash_solver, DistributedCoordinator):
            return []
        evaluations: list[_LeaderCandidateEvaluation] = []

        no_control = ControlAction.uncontrolled(self.cfg)
        no_obj, no_diag = self.nash_solver._response_tts_objective(
            state,
            no_control,
            forecast,
            residual=0.0,
            proxy_objective=0.0,
        )
        no_control.diagnostics.update(no_diag)
        no_nash = NashResult(
            control=no_control,
            objective_value=float(no_obj),
            iterations=0,
            converged=True,
            residual_objective=0.0,
            residual_control=0.0,
            diagnostics=dict(no_diag),
        )
        evaluations.append(self._make_fallback_evaluation(
            start_index,
            "fallback_no_control",
            no_nash,
            previous,
            state,
            forecast,
        ))

        fallback_refresh = self._fallback_full_refresh_active(state)
        cached_previous_used = (
            bool(self.cfg.mpc.stackelberg_fallback_use_cached_pfo)
            and not fallback_refresh
            and self._pfo_fallback_previous_control is not None
        )
        pfo_previous = (
            self._pfo_fallback_previous_control.copy()
            if cached_previous_used and self._pfo_fallback_previous_control is not None
            else previous.copy()
        )
        pfo_previous.N_P_star = 0.0
        pfo_previous.N_UF_star = 0.0
        pfo_previous.inflow_outflow_allocation = {}
        pfo_nash = self.nash_solver.solve(
            state.copy(),
            None,
            forecast,
            pfo_previous,
        )
        self._pfo_fallback_previous_control = pfo_nash.control.copy()
        evaluations.append(self._make_fallback_evaluation(
            start_index + 1,
            "fallback_pfo",
            pfo_nash,
            previous,
            state,
            forecast,
            extra_metadata={
                "leader_fallback_pfo_global_refresh": float(fallback_refresh),
                "leader_fallback_pfo_local_search": float(not fallback_refresh),
                "leader_fallback_pfo_cached_previous_used": float(cached_previous_used),
                "leader_fallback_pfo_refresh_interval_sec": float(
                    self.cfg.mpc.stackelberg_fallback_full_refresh_sec
                ),
            },
        ))
        return evaluations

    def _make_fallback_evaluation(
        self,
        index: int,
        stage: str,
        nash: NashResult,
        previous: ControlAction,
        state: TrafficState,
        forecast: list[DemandStep],
        extra_metadata: Optional[Dict[str, float]] = None,
    ) -> _LeaderCandidateEvaluation:
        action = LeaderAction(float(nash.control.N_P_star), float(nash.control.N_UF_star))
        horizon = max(1, len(forecast[: self.cfg.mpc.horizon_steps]))
        objective_terms = self.leader.objective_terms(
            [state.copy() for _ in range(horizon)],
            nash.control,
            previous,
            float(nash.objective_value),
            nash.converged,
            nash.residual_objective,
            nash.residual_control,
        )
        return _LeaderCandidateEvaluation(
            index=index,
            action=action,
            nash=nash,
            objective=float(objective_terms.get("leader_total_objective", nash.objective_value)),
            objective_terms={
                "leader_base_accumulation": float(objective_terms.get("leader_base_accumulation", 0.0)),
                "leader_objective_base": float(objective_terms.get("leader_objective_base", nash.objective_value)),
                "leader_state_accumulation_base": float(objective_terms.get("leader_state_accumulation_base", 0.0)),
                "leader_follower_ttt_base": float(objective_terms.get("leader_follower_ttt_base", nash.objective_value)),
                "leader_boundary_leg_excluded_veh": float(objective_terms.get("leader_boundary_leg_excluded_veh", 0.0)),
                "leader_target_penalty": float(objective_terms.get("leader_target_penalty", 0.0)),
                "leader_boundary_in_queue_penalty": float(objective_terms.get("leader_boundary_in_queue_penalty", 0.0)),
                "leader_density_excess": float(objective_terms.get("leader_density_excess", 0.0)),
                "leader_density_penalty": float(objective_terms.get("leader_density_penalty", 0.0)),
                "leader_density_effective_lane_weight_count": float(
                    objective_terms.get("leader_density_effective_lane_weight_count", 0.0)
                ),
                "leader_smoothness_penalty": float(objective_terms.get("leader_smoothness_penalty", 0.0)),
                "leader_nonconvergence_penalty": float(objective_terms.get("leader_nonconvergence_penalty", 0.0)),
                "leader_nonconvergence_obj_residual_component": float(
                    objective_terms.get("leader_nonconvergence_obj_residual_component", 0.0)
                ),
                "leader_nonconvergence_control_residual_component": float(
                    objective_terms.get("leader_nonconvergence_control_residual_component", 0.0)
                ),
                "leader_total_objective": float(objective_terms.get("leader_total_objective", nash.objective_value)),
            },
            metadata={
                "leader_response_proxy_state_count": float(horizon),
                "leader_fallback_candidate": 1.0,
                **(extra_metadata or {}),
            },
            rollout_used=False,
            stage=stage,
        )

    def _proxy_score_candidate(
        self,
        index: int,
        action: LeaderAction,
        state: TrafficState,
        forecast: list[DemandStep],
        previous: ControlAction,
    ) -> Dict[str, float]:
        control = previous.copy()
        control.N_P_star = float(action.N_P_star)
        control.N_UF_star = float(action.N_UF_star)
        if isinstance(self.nash_solver, DistributedCoordinator):
            weights = {
                ramp: float(self.cfg.network.ramp_capacity_veh_h[ramp])
                for ramp in self.cfg.network.ramps
            }
            control.ramp_metering = self.nash_solver._leader_metering_projection(action, weights)
            follower_obj, proxy_diag = self.nash_solver._response_tts_objective(
                state,
                control,
                forecast,
                residual=0.0,
                proxy_objective=0.0,
            )
        else:
            horizon_h = self.cfg.simulation.T_c_h * max(1, min(len(forecast), self.cfg.mpc.horizon_steps))
            follower_obj = (
                state.total_urban_vehicles(self.cfg.network)
                + state.total_freeway_vehicles(self.cfg.network)
            ) * horizon_h
            proxy_diag = {}
        horizon = max(1, len(forecast[: self.cfg.mpc.horizon_steps]))
        terms = self.leader.objective_terms(
            [state.copy() for _ in range(horizon)],
            control,
            previous,
            float(follower_obj),
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
            "spillback_violation": float(proxy_diag.get("distributed_response_total_spillback_violation_veh", 0.0)),
        }

    def _prefilter_leader_candidates(
        self,
        candidates: list[LeaderAction],
        state: TrafficState,
        forecast: list[DemandStep],
        previous: ControlAction,
        global_scope: bool = False,
    ) -> tuple[list[int], Dict[str, float]]:
        rows = [
            self._proxy_score_candidate(idx, action, state, forecast, previous)
            for idx, action in enumerate(candidates)
        ]
        ranked = sorted(rows, key=lambda row: (row["objective"], row["spillback_violation"], row["index"]))
        objectives = [row["objective"] for row in rows] or [0.0]
        top_k = int(
            self.cfg.mpc.stackelberg_prefilter_top_k
            if global_scope
            else self.cfg.mpc.stackelberg_prefilter_local_top_k
        )
        if top_k <= 0 or top_k >= len(candidates):
            selected = list(range(len(candidates)))
            active = False
        else:
            selected = []
            seen = set()

            def add_index(idx: int) -> None:
                if idx in seen:
                    return
                seen.add(idx)
                selected.append(idx)

            for row in ranked[:top_k]:
                add_index(int(row["index"]))
            add_index(0)
            nearest_previous = min(
                range(len(candidates)),
                key=lambda idx: (
                    abs(candidates[idx].N_P_star - previous.N_P_star)
                    + abs(candidates[idx].N_UF_star - previous.N_UF_star)
                ),
            )
            add_index(int(nearest_previous))
            active = True
        best = ranked[0] if ranked else {"index": 0.0, "objective": 0.0}
        second = ranked[1] if len(ranked) > 1 else best
        return selected, {
            "leader_candidate_prefilter_active": float(active),
            "leader_candidate_prefilter_top_k": float(top_k),
            "leader_candidate_prefilter_scope_global": float(global_scope),
            "leader_candidate_prefilter_scope_local": float(not global_scope),
            "leader_candidate_proxy_evaluated_count": float(len(rows)),
            "leader_candidate_prefilter_selected_count": float(len(selected)),
            "leader_candidate_proxy_best_index": float(best["index"]),
            "leader_candidate_proxy_second_index": float(second["index"]),
            "leader_candidate_proxy_best_objective": float(best["objective"]),
            "leader_candidate_proxy_second_objective": float(second["objective"]),
            "leader_candidate_proxy_objective_gap": float(second["objective"] - best["objective"]),
            "leader_candidate_proxy_objective_spread": float(max(objectives) - min(objectives)),
        }

    def _evaluate_candidate_set(
        self,
        candidates: list[LeaderAction],
        selected_indices: list[int],
        state: TrafficState,
        forecast: list[DemandStep],
        previous: ControlAction,
        stage: str = "coarse",
        index_offset: int = 0,
        incumbent_obj: float = float("inf"),
    ) -> list[_LeaderCandidateEvaluation]:
        if not selected_indices:
            raise ValueError("Stackelberg leader prefilter removed every candidate.")
        backend = self.cfg.mpc.stackelberg_leader_parallel_backend
        workers = max(1, min(int(self.cfg.mpc.stackelberg_leader_parallel_max_workers), len(selected_indices)))
        eval_cfg = self._candidate_eval_config()
        inner_backend = eval_cfg.mpc.grid_parallel_backend
        payloads = [
            {
                "cfg": eval_cfg,
                "index": idx + index_offset,
                "action": candidates[idx],
                "state": state,
                "forecast": forecast,
                "previous": previous,
                "stage": stage,
                "incumbent_obj": incumbent_obj,
            }
            for idx in selected_indices
        ]
        results: list[_LeaderCandidateEvaluation] = []
        stage_incumbent = float(incumbent_obj)
        seed_used = False
        process_pool_reused_existing = False
        if payloads:
            seed_payload = dict(payloads[0])
            seed_payload["incumbent_obj"] = stage_incumbent
            seed_result = _stackelberg_candidate_worker(seed_payload)
            results.append(seed_result)
            stage_incumbent = min(stage_incumbent, float(seed_result.objective))
            seed_used = True
            payloads = payloads[1:]
            for payload in payloads:
                payload["incumbent_obj"] = stage_incumbent
        if backend == "serial" or workers <= 1:
            for payload in payloads:
                payload["incumbent_obj"] = stage_incumbent
                result = _stackelberg_candidate_worker(payload)
                results.append(result)
                stage_incumbent = min(stage_incumbent, float(result.objective))
            backend_used = "serial"
            chunks = 1
        elif backend == "thread":
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results.extend(executor.map(_stackelberg_candidate_worker, payloads))
            backend_used = "thread"
            chunks = max(1, len(payloads))
        else:
            if self.cfg.mpc.stackelberg_reuse_process_pool:
                executor, process_pool_reused_existing = self._leader_process_executor(workers)
                results.extend(executor.map(_stackelberg_candidate_worker, payloads))
            else:
                with ProcessPoolExecutor(max_workers=workers) as executor:
                    results.extend(executor.map(_stackelberg_candidate_worker, payloads))
            backend_used = "process"
            chunks = max(1, len(payloads))
        diag = {
            "leader_candidate_parallel_backend_serial": float(backend_used == "serial"),
            "leader_candidate_parallel_backend_thread": float(backend_used == "thread"),
            "leader_candidate_parallel_backend_process": float(backend_used == "process"),
            "leader_candidate_parallel_workers": float(workers if backend_used != "serial" else 1),
            "leader_candidate_parallel_chunks": float(chunks),
            "leader_candidate_process_pool_reuse_enabled": float(
                bool(self.cfg.mpc.stackelberg_reuse_process_pool)
            ),
            "leader_candidate_process_pool_reused_existing": float(process_pool_reused_existing),
            "leader_candidate_inner_grid_backend_serial": float(inner_backend == "serial"),
            "leader_candidate_inner_grid_backend_thread": float(inner_backend == "thread"),
            "leader_candidate_inner_grid_backend_process": float(inner_backend == "process"),
            "leader_candidate_nested_process_avoided": float(
                backend_used == "process" and self.cfg.mpc.grid_parallel_backend == "process" and inner_backend != "process"
            ),
            "leader_candidate_incumbent_seed_used": float(seed_used),
            "leader_candidate_incumbent_initial_objective": float(
                incumbent_obj if incumbent_obj < float("inf") else 0.0
            ),
            "leader_candidate_incumbent_final_objective": float(
                min((result.objective for result in results), default=stage_incumbent)
            ),
            "leader_candidate_incumbent_early_termination_active": float(
                any(result.metadata.get("leader_candidate_incumbent_active", 0.0) > 0.5 for result in results)
            ),
            "leader_candidate_follower_early_terminated_candidates": float(sum(
                result.metadata.get("leader_candidate_follower_early_terminated_candidates", 0.0)
                for result in results
            )),
        }
        for result in results:
            result.metadata.update(diag)
        return results

    def _forecast_demand_metadata(self, forecast: list[DemandStep]) -> Dict[str, float]:
        """forecast 요약 진단을 compact하게 남긴다.

        후보 집합은 같아도 평가 입력 수요가 달라졌는지 test/진단에서 확인할 수 있도록,
        horizon 내부의 첫 스텝/미래 평균/peak 유량[veh/h]만 기록한다.
        """
        horizon = forecast[: max(1, self.cfg.mpc.horizon_steps)]

        def total(step: DemandStep, attr: str) -> float:
            values = getattr(step, attr)
            return float(sum(float(v) for v in values.values()))

        def mean(values: list[float]) -> float:
            return float(sum(values) / len(values)) if values else 0.0

        by_group = {
            "mainline": [total(step, "freeway_mainline") for step in horizon],
            "boundary": [total(step, "urban_boundary") for step in horizon],
            "ramp": [total(step, "ramp_arrival") for step in horizon],
        }
        metadata: Dict[str, float] = {"leader_forecast_steps": float(len(horizon))}
        total_by_step = [
            by_group["mainline"][idx] + by_group["boundary"][idx] + by_group["ramp"][idx]
            for idx in range(len(horizon))
        ]
        future_total = total_by_step[1:]
        metadata.update({
            "leader_forecast_total_first_veh_h": float(total_by_step[0]),
            "leader_forecast_total_future_mean_veh_h": mean(future_total),
            "leader_forecast_total_peak_veh_h": float(max(total_by_step, default=0.0)),
        })
        for name, values in by_group.items():
            future = values[1:]
            metadata.update({
                f"leader_forecast_{name}_first_veh_h": float(values[0]),
                f"leader_forecast_{name}_future_mean_veh_h": mean(future),
                f"leader_forecast_{name}_peak_veh_h": float(max(values, default=0.0)),
            })
        return metadata

    def _candidate_evaluation_metadata(
        self,
        evaluations: list[dict[str, object]],
        selected: ControlAction,
        selected_eval: Optional[_LeaderCandidateEvaluation] = None,
    ) -> Dict[str, float]:
        """candidate 평가/랭킹 요약만 diagnostics에 보존한다.

        전체 후보 로그는 커질 수 있으므로 best/second, objective spread, 선택 action만 남긴다.
        """
        if not evaluations:
            return {}
        ranked = sorted(evaluations, key=lambda row: row["objective"])
        best = ranked[0]
        second = ranked[1] if len(ranked) > 1 else ranked[0]
        objectives = [row["objective"] for row in evaluations]
        selected_stage = selected_eval.stage if selected_eval is not None else str(best.get("stage", ""))
        selected_objective = float(selected_eval.objective) if selected_eval is not None else float(best["objective"])
        return {
            "leader_selected_N_P_star": float(selected.N_P_star),
            "leader_selected_N_UF_star": float(selected.N_UF_star),
            "leader_selected_objective": selected_objective,
            "leader_selected_stage_coarse": float(str(selected_stage).startswith("coarse")),
            "leader_selected_stage_refined": float(selected_stage == "refined"),
            "leader_selected_stage_fallback": float(str(selected_stage).startswith("fallback")),
            "leader_selected_stage_fallback_pfo": float(selected_stage == "fallback_pfo"),
            "leader_selected_stage_fallback_no_control": float(selected_stage == "fallback_no_control"),
            "leader_candidate_best_index": float(best["index"]),
            "leader_candidate_second_index": float(second["index"]),
            "leader_candidate_best_stage_coarse": float(str(best.get("stage", "")).startswith("coarse")),
            "leader_candidate_best_stage_refined": float(best.get("stage") == "refined"),
            "leader_candidate_best_stage_fallback": float(str(best.get("stage", "")).startswith("fallback")),
            "leader_candidate_second_stage_coarse": float(str(second.get("stage", "")).startswith("coarse")),
            "leader_candidate_second_stage_refined": float(second.get("stage") == "refined"),
            "leader_candidate_second_stage_fallback": float(str(second.get("stage", "")).startswith("fallback")),
            "leader_candidate_best_N_P_star": float(best["N_P_star"]),
            "leader_candidate_best_N_UF_star": float(best["N_UF_star"]),
            "leader_candidate_second_N_P_star": float(second["N_P_star"]),
            "leader_candidate_second_N_UF_star": float(second["N_UF_star"]),
            "leader_candidate_best_objective": float(best["objective"]),
            "leader_candidate_second_objective": float(second["objective"]),
            "leader_candidate_objective_gap": float(second["objective"] - best["objective"]),
            "leader_candidate_objective_spread": float(max(objectives) - min(objectives)),
        }

    def _leader_evaluation_base(
        self,
        state: TrafficState,
        nash: NashResult,
        forecast: list[DemandStep],
    ) -> tuple[list[TrafficState], float, bool]:
        """Leader 기본 평가는 follower response objective를 그대로 사용한다.

        사용자가 제시한 Stackelberg 구조에서는 follower equilibrium/response가 산출한
        objective가 leader의 follower-TTT 항이다. 따라서 기본 `follower_ttt` 모드에서는
        후보 control을 다시 full coupled plant로 rollout하지 않는다. Legacy
        `state_accumulation` 모드는 state trajectory 자체가 base이므로 기존 rollout을 유지한다.
        """
        if self.cfg.leader.objective_mode == "state_accumulation":
            states, rollout_ttt = self._predict(state, nash.control, forecast)
            return states, rollout_ttt, True
        horizon = max(1, len(forecast[: self.cfg.mpc.horizon_steps]))
        # target/density penalty는 현재 response-state proxy 위에서 평가한다. follower objective
        # 자체가 후보별 response 비용을 담고, full system rollout 비용은 의도적으로 배제한다.
        return [state.copy() for _ in range(horizon)], float(nash.objective_value), False

    def _predict(
        self,
        state: TrafficState,
        control: ControlAction,
        forecast: list[DemandStep],
    ) -> tuple[list[TrafficState], float]:
        from src.simulation.coupling import run_coupled_interval

        s = state.copy()
        states: list[TrafficState] = []
        total_ttt = 0.0
        for demand in forecast[: self.cfg.mpc.horizon_steps]:
            result = run_coupled_interval(s, control, demand, self.cfg)
            s.time_sec += self.cfg.simulation.control_interval
            total_ttt += result.freeway_ttt + result.urban_ttt
            states.append(s.copy())
        return states, float(total_ttt)
