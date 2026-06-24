from __future__ import annotations

import json
import os
import csv
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
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

    def _append_progress_event(
        self,
        *,
        event: str,
        stage: str,
        completed: int,
        total: int,
        evaluation: Optional[_LeaderCandidateEvaluation] = None,
        best_objective: Optional[float] = None,
    ) -> None:
        path_text = os.environ.get("NUMSIM_STACKELBERG_PROGRESS_FILE", "")
        if not path_text:
            return
        row: Dict[str, object] = {
            "event": event,
            "step": os.environ.get("NUMSIM_STACKELBERG_PROGRESS_STEP", ""),
            "stage": stage,
            "completed": int(completed),
            "total": int(total),
        }
        if best_objective is not None:
            row["best_objective_so_far"] = float(best_objective)
        if evaluation is not None:
            row.update({
                "candidate_index": int(evaluation.index),
                "N_P_star": float(evaluation.action.N_P_star),
                "N_UF_star": float(evaluation.action.N_UF_star),
                "objective": float(evaluation.objective),
                "follower_ttt": float(evaluation.objective_terms.get("leader_follower_ttt_base", 0.0)),
                "mfd_storage_penalty": float(evaluation.objective_terms.get("leader_mfd_storage_penalty", 0.0)),
                "mfd_storage_excess_veh": float(
                    evaluation.objective_terms.get("leader_mfd_storage_excess_veh", 0.0)
                ),
            })
        try:
            path = Path(path_text)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            csv_path = path.with_suffix(".csv")
            fields = [
                "step",
                "event",
                "stage",
                "completed",
                "total",
                "candidate_index",
                "N_P_star",
                "N_UF_star",
                "objective",
                "best_objective_so_far",
                "follower_ttt",
                "mfd_storage_penalty",
                "mfd_storage_excess_veh",
            ]
            write_header = not csv_path.exists()
            with csv_path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
                if write_header:
                    writer.writeheader()
                writer.writerow(row)
        except OSError:
            return

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
        search_mode = str(self.cfg.mpc.leader_search_mode)
        fallback_start_index = 1000000
        fallback_enabled = bool(self.cfg.mpc.stackelberg_enable_fallback)
        pfo_objective_floor = bool(getattr(self.cfg.mpc, "leader_pfo_objective_floor", False))
        # fix 2: objective floor가 켜지면 비대칭 가드가 꺼져 있어도 PFO/no-control 후보를 평가해
        # 순수 objective 비교에 포함시킨다(P-Stack <= PFO 보장).
        fallback_evaluations = (
            self._evaluate_fallback_candidates(
                state,
                forecast,
                previous,
                start_index=fallback_start_index,
            )
            if (fallback_enabled or pfo_objective_floor)
            else []
        )
        fallback_incumbent_obj = min(
            (item.objective for item in fallback_evaluations),
            default=float("inf"),
        )
        if search_mode == "continuous":
            (
                full_evaluations,
                base_metadata,
                proxy_metadata,
                refined_proxy_metadata,
            ) = self._continuous_leader_search(
                state,
                forecast,
                previous,
                global_refresh,
                fallback_incumbent_obj,
            )
        else:
            (
                full_evaluations,
                base_metadata,
                proxy_metadata,
                refined_proxy_metadata,
            ) = self._grid_leader_search(
                state,
                forecast,
                previous,
                global_refresh,
                fallback_incumbent_obj,
            )
        base_metadata.update({
            "leader_search_mode_grid": float(search_mode == "grid"),
            "leader_search_mode_continuous": float(search_mode == "continuous"),
            "leader_fallback_enabled": float(fallback_enabled),
            "leader_fallback_incumbent_seed_active": float(fallback_incumbent_obj < float("inf")),
            "leader_fallback_incumbent_objective": float(
                fallback_incumbent_obj if fallback_incumbent_obj < float("inf") else 0.0
            ),
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
        if pfo_objective_floor:
            best_eval, fallback_metadata = self._select_pfo_objective_floor(
                full_evaluations,
                fallback_evaluations,
            )
        else:
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
            "leader_follower_response_objective_used": float(
                self.cfg.leader.objective_mode == "follower_ttt"
            ),
            "leader_rollout_objective_base_used": float(
                self.cfg.leader.objective_mode == "state_accumulation"
            ),
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

    def _grid_leader_search(
        self,
        state: TrafficState,
        forecast: list[DemandStep],
        previous: ControlAction,
        global_refresh: bool,
        fallback_incumbent_obj: float,
    ) -> tuple[list[_LeaderCandidateEvaluation], Dict[str, float], Dict[str, float], Dict[str, float]]:
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
        base_metadata.update(self._leader_search_common_metadata(
            full_evaluations,
            global_refresh,
            coarse_stage,
            len(coarse_candidates),
            len(coarse_evaluations),
            len(refined_candidates),
            len(refined_evaluations),
            bool(refined_candidates),
        ))
        return full_evaluations, base_metadata, proxy_metadata, refined_proxy_metadata

    def _leader_search_common_metadata(
        self,
        full_evaluations: list[_LeaderCandidateEvaluation],
        global_refresh: bool,
        coarse_stage: str,
        coarse_count: int,
        coarse_evaluated_count: int,
        refined_count: int,
        refined_evaluated_count: int,
        refinement_active: bool,
    ) -> Dict[str, float]:
        def candidate_meta_any(key: str) -> float:
            return float(max((item.metadata.get(key, 0.0) for item in full_evaluations), default=0.0))

        return {
            "leader_candidate_coarse_count": float(coarse_count),
            "leader_candidate_coarse_evaluated_count": float(coarse_evaluated_count),
            "leader_candidate_refined_count": float(refined_count),
            "leader_candidate_refined_evaluated_count": float(refined_evaluated_count),
            "leader_candidate_refinement_active": float(refinement_active),
            "leader_candidate_global_refresh": float(global_refresh),
            "leader_candidate_coarse_global": float(coarse_stage in {"coarse_global", "continuous_global"}),
            "leader_candidate_coarse_local": float(coarse_stage in {"coarse_local", "continuous_local"}),
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
        }

    def _continuous_leader_search(
        self,
        state: TrafficState,
        forecast: list[DemandStep],
        previous: ControlAction,
        global_refresh: bool,
        fallback_incumbent_obj: float,
    ) -> tuple[list[_LeaderCandidateEvaluation], Dict[str, float], Dict[str, float], Dict[str, float]]:
        bounds = self.leader._candidate_bounds(state, previous, forecast[0], forecast)
        np_lower, np_upper = float(bounds.np_lower), float(bounds.np_upper)
        nuf_lower, nuf_upper = float(bounds.nuf_lower), float(bounds.nuf_upper)
        if not global_refresh:
            np_lower = max(np_lower, float(previous.N_P_star) - float(self.cfg.mpc.leader_local_np_radius_veh))
            np_upper = min(np_upper, float(previous.N_P_star) + float(self.cfg.mpc.leader_local_np_radius_veh))
            nuf_lower = max(nuf_lower, float(previous.N_UF_star) - float(self.cfg.mpc.leader_local_nuf_radius_veh_h))
            nuf_upper = min(nuf_upper, float(previous.N_UF_star) + float(self.cfg.mpc.leader_local_nuf_radius_veh_h))
        if np_lower > np_upper:
            np_lower = np_upper = float(previous.N_P_star)
        if nuf_lower > nuf_upper:
            nuf_lower = nuf_upper = float(previous.N_UF_star)

        def clipped(np_value: float, nuf_value: float) -> LeaderAction:
            return LeaderAction(
                float(min(max(float(np_value), np_lower), np_upper)),
                float(min(max(float(nuf_value), nuf_lower), nuf_upper)),
            )

        # full 탐색은 global refresh 스텝에서만, local 스텝은 축소 예산으로 previous 인근만 본다.
        if global_refresh:
            eff_max_evals = int(self.cfg.mpc.leader_continuous_max_evals)
            eff_seed_count = int(self.cfg.mpc.leader_continuous_seed_count)
            eff_prefilter_samples = int(self.cfg.mpc.leader_continuous_prefilter_samples)
            eff_prefilter_top_k = int(self.cfg.mpc.leader_continuous_prefilter_top_k)
        else:
            eff_max_evals = int(self.cfg.mpc.leader_continuous_local_max_evals)
            eff_seed_count = int(self.cfg.mpc.leader_continuous_local_seed_count)
            eff_prefilter_samples = int(self.cfg.mpc.leader_continuous_local_prefilter_samples)
            eff_prefilter_top_k = int(self.cfg.mpc.leader_continuous_local_prefilter_top_k)
        max_evals = max(1, eff_max_evals)
        raw_seed_actions = self._continuous_seed_actions(
            previous,
            bounds,
            np_lower,
            np_upper,
            nuf_lower,
            nuf_upper,
            clipped,
        )
        # Continuous search도 grid prefilter와 같은 구조를 쓴다. 먼저 넓은
        # deterministic low-discrepancy sample을 cheap proxy로 정렬하고, full
        # follower evaluation은 top-K seed에만 쓴다.
        seed_actions, prefilter_metadata = self._continuous_prefilter_actions(
            raw_seed_actions,
            state,
            forecast,
            previous,
            np_lower,
            np_upper,
            nuf_lower,
            nuf_upper,
            prefilter_samples=eff_prefilter_samples,
            prefilter_top_k=eff_prefilter_top_k,
        )
        seed_actions = seed_actions[: max(1, eff_seed_count)]
        coarse_stage = "continuous_global" if global_refresh else "continuous_local"
        evaluated, incumbent_obj = self._evaluate_continuous_action_set(
            seed_actions[:max_evals],
            state,
            forecast,
            previous,
            stage=coarse_stage,
            index_start=0,
            incumbent_obj=fallback_incumbent_obj,
        )
        if not evaluated:
            raise ValueError("Continuous leader search produced no evaluated candidates.")
        seen = {
            (round(float(item.action.N_P_star), 6), round(float(item.action.N_UF_star), 6))
            for item in evaluated
        }
        best = min(evaluated, key=lambda item: item.objective)
        np_span = max(np_upper - np_lower, 1.0e-9)
        nuf_span = max(nuf_upper - nuf_lower, 1.0e-9)
        np_step = max(
            float(self.cfg.mpc.leader_continuous_min_np_step_veh),
            np_span * float(self.cfg.mpc.leader_continuous_initial_step_fraction),
        )
        nuf_step = max(
            float(self.cfg.mpc.leader_continuous_min_nuf_step_veh_h),
            nuf_span * float(self.cfg.mpc.leader_continuous_initial_step_fraction),
        )
        local_evaluations: list[_LeaderCandidateEvaluation] = []
        iterations_completed = 0
        next_index = len(evaluated)
        shrink = float(self.cfg.mpc.leader_continuous_shrink_factor)
        min_np_step = float(self.cfg.mpc.leader_continuous_min_np_step_veh)
        min_nuf_step = float(self.cfg.mpc.leader_continuous_min_nuf_step_veh_h)
        base_directions = [
            (-1.0, 0.0),
            (1.0, 0.0),
            (0.0, -1.0),
            (0.0, 1.0),
            (-1.0, -1.0),
            (-1.0, 1.0),
            (1.0, -1.0),
            (1.0, 1.0),
        ]
        for iteration in range(max(0, int(self.cfg.mpc.leader_continuous_local_iterations))):
            remaining = max_evals - len(evaluated) - len(local_evaluations)
            if remaining <= 0:
                break
            candidates: list[LeaderAction] = []
            directions = self._continuous_ranked_directions(
                best.action,
                state,
                forecast,
                previous,
                np_step,
                nuf_step,
                clipped,
                base_directions,
            )
            for dx, dy in directions:
                action = clipped(
                    best.action.N_P_star + dx * np_step,
                    best.action.N_UF_star + dy * nuf_step,
                )
                key = (round(float(action.N_P_star), 6), round(float(action.N_UF_star), 6))
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(action)
                if len(candidates) >= remaining:
                    break
            if not candidates:
                np_step *= shrink
                nuf_step *= shrink
                if np_step < min_np_step and nuf_step < min_nuf_step:
                    break
                continue
            stage = f"continuous_refined_{iteration}"
            new_evaluations, incumbent_obj = self._evaluate_continuous_action_set(
                candidates,
                state,
                forecast,
                previous,
                stage=stage,
                index_start=next_index,
                incumbent_obj=incumbent_obj,
            )
            next_index += len(new_evaluations)
            local_evaluations.extend(new_evaluations)
            if new_evaluations:
                new_best = min(new_evaluations + [best], key=lambda item: item.objective)
                if new_best.objective < best.objective - 1.0e-12:
                    best = new_best
                else:
                    np_step *= shrink
                    nuf_step *= shrink
            iterations_completed += 1
            if np_step < min_np_step and nuf_step < min_nuf_step:
                break

        full_evaluations = evaluated + local_evaluations
        actions = [item.action for item in full_evaluations]
        base_metadata = leader_metadata(actions)
        base_metadata.update(self.leader.candidate_bound_metadata(state, previous, forecast[0], forecast=forecast))
        base_metadata.update(self._forecast_demand_metadata(forecast))
        base_metadata.update(self._leader_search_common_metadata(
            full_evaluations,
            global_refresh,
            coarse_stage,
            len(seed_actions),
            len(evaluated),
            len(local_evaluations),
            len(local_evaluations),
            bool(local_evaluations),
        ))
        base_metadata.update({
            "leader_continuous_search_bound_np_lower": float(np_lower),
            "leader_continuous_search_bound_np_upper": float(np_upper),
            "leader_continuous_search_bound_nuf_lower": float(nuf_lower),
            "leader_continuous_search_bound_nuf_upper": float(nuf_upper),
            "leader_continuous_max_evals": float(max_evals),
            "leader_continuous_seed_count": float(len(seed_actions)),
            "leader_continuous_iterations_completed": float(iterations_completed),
            "leader_continuous_final_np_step_veh": float(np_step),
            "leader_continuous_final_nuf_step_veh_h": float(nuf_step),
        })
        base_metadata.update(prefilter_metadata)
        return full_evaluations, base_metadata, {}, {}

    def _continuous_seed_actions(
        self,
        previous: ControlAction,
        bounds,
        np_lower: float,
        np_upper: float,
        nuf_lower: float,
        nuf_upper: float,
        clipped,
    ) -> list[LeaderAction]:
        np_mid = 0.5 * (np_lower + np_upper)
        nuf_mid = 0.5 * (nuf_lower + nuf_upper)
        heuristic_nuf = float(min(max(float(bounds.heuristic_nuf), nuf_lower), nuf_upper))
        return [
            clipped(previous.N_P_star, previous.N_UF_star),
            clipped(np_mid, nuf_mid),
            clipped(0.0, heuristic_nuf),
            clipped(np_lower, nuf_lower),
            clipped(np_lower, nuf_upper),
            clipped(np_upper, nuf_lower),
            clipped(np_upper, nuf_upper),
            clipped(np_lower, nuf_mid),
            clipped(np_upper, nuf_mid),
            clipped(np_mid, nuf_lower),
            clipped(np_mid, nuf_upper),
        ]

    def _continuous_prefilter_actions(
        self,
        seed_actions: list[LeaderAction],
        state: TrafficState,
        forecast: list[DemandStep],
        previous: ControlAction,
        np_lower: float,
        np_upper: float,
        nuf_lower: float,
        nuf_upper: float,
        prefilter_samples: Optional[int] = None,
        prefilter_top_k: Optional[int] = None,
    ) -> tuple[list[LeaderAction], Dict[str, float]]:
        if prefilter_samples is None:
            prefilter_samples = int(self.cfg.mpc.leader_continuous_prefilter_samples)
        if prefilter_top_k is None:
            prefilter_top_k = int(self.cfg.mpc.leader_continuous_prefilter_top_k)
        samples = self._unique_leader_actions(
            seed_actions
            + self._continuous_low_discrepancy_samples(
                int(prefilter_samples),
                np_lower,
                np_upper,
                nuf_lower,
                nuf_upper,
            )
        )
        rows: list[Dict[str, float]] = []
        filtered = 0
        spillback_filtered = 0
        for idx, action in enumerate(samples):
            if not self._continuous_candidate_bounds_ok(action, np_lower, np_upper, nuf_lower, nuf_upper):
                filtered += 1
                continue
            row = self._proxy_score_candidate(idx, action, state, forecast, previous)
            if bool(self.cfg.mpc.leader_continuous_hard_precheck):
                tolerance = float(self.cfg.mpc.leader_continuous_precheck_spillback_tolerance_veh)
                if row["spillback_violation"] > tolerance:
                    filtered += 1
                    spillback_filtered += 1
                    continue
            rows.append(row)
        if not rows:
            # Hard pre-check가 지나치게 강하면 기존 seed를 보존한다. feasibility
            # 진단은 남기되 controller가 후보 0개로 죽지 않게 한다.
            rows = [
                self._proxy_score_candidate(idx, action, state, forecast, previous)
                for idx, action in enumerate(self._unique_leader_actions(seed_actions))
            ]
        rows = sorted(rows, key=lambda row: (row["objective"], row["spillback_violation"], row["index"]))
        top_k = max(1, int(prefilter_top_k))
        selected_indices = [int(row["index"]) for row in rows[:top_k]]
        selected_actions = [samples[idx] for idx in selected_indices if 0 <= idx < len(samples)]
        # 기본/직전 seed가 cheap proxy에서 살짝 밀려도 한 개는 남겨 guard 역할을 하게 한다.
        if seed_actions:
            selected_actions.insert(0, seed_actions[0])
        selected_actions = self._unique_leader_actions(selected_actions)
        objectives = [float(row["objective"]) for row in rows] or [0.0]
        best = rows[0] if rows else {"index": 0.0, "objective": 0.0}
        second = rows[1] if len(rows) > 1 else best
        return selected_actions, {
            "leader_continuous_prefilter_active": 1.0,
            "leader_continuous_prefilter_samples": float(len(samples)),
            "leader_continuous_prefilter_proxy_evaluated_count": float(len(rows)),
            "leader_continuous_prefilter_selected_count": float(len(selected_actions)),
            "leader_continuous_prefilter_top_k": float(top_k),
            "leader_continuous_precheck_filtered_count": float(filtered),
            "leader_continuous_precheck_spillback_filtered_count": float(spillback_filtered),
            "leader_continuous_proxy_best_index": float(best["index"]),
            "leader_continuous_proxy_second_index": float(second["index"]),
            "leader_continuous_proxy_best_objective": float(best["objective"]),
            "leader_continuous_proxy_second_objective": float(second["objective"]),
            "leader_continuous_proxy_objective_gap": float(second["objective"] - best["objective"]),
            "leader_continuous_proxy_objective_spread": float(max(objectives) - min(objectives)),
        }

    def _continuous_low_discrepancy_samples(
        self,
        count: int,
        np_lower: float,
        np_upper: float,
        nuf_lower: float,
        nuf_upper: float,
    ) -> list[LeaderAction]:
        count = max(0, int(count))
        np_span = max(np_upper - np_lower, 0.0)
        nuf_span = max(nuf_upper - nuf_lower, 0.0)

        def vdc(index: int, base: int) -> float:
            value = 0.0
            denom = 1.0
            n = max(0, int(index))
            while n:
                n, rem = divmod(n, base)
                denom *= base
                value += rem / denom
            return value

        actions: list[LeaderAction] = []
        for i in range(1, count + 1):
            np_frac = vdc(i, 2)
            nuf_frac = vdc(i, 3)
            actions.append(LeaderAction(
                float(np_lower + np_frac * np_span),
                float(nuf_lower + nuf_frac * nuf_span),
            ))
        return actions

    def _continuous_candidate_bounds_ok(
        self,
        action: LeaderAction,
        np_lower: float,
        np_upper: float,
        nuf_lower: float,
        nuf_upper: float,
    ) -> bool:
        values = [action.N_P_star, action.N_UF_star, np_lower, np_upper, nuf_lower, nuf_upper]
        if any(value != value for value in values):
            return False
        eps = 1.0e-6
        return (
            np_lower - eps <= action.N_P_star <= np_upper + eps
            and nuf_lower - eps <= action.N_UF_star <= nuf_upper + eps
        )

    def _continuous_ranked_directions(
        self,
        center: LeaderAction,
        state: TrafficState,
        forecast: list[DemandStep],
        previous: ControlAction,
        np_step: float,
        nuf_step: float,
        clipped,
        base_directions: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        if not bool(self.cfg.mpc.leader_continuous_use_sensitivity_directions):
            return base_directions
        scored: list[tuple[float, float, float]] = []
        for dx, dy in base_directions:
            action = clipped(
                center.N_P_star + dx * np_step,
                center.N_UF_star + dy * nuf_step,
            )
            row = self._proxy_score_candidate(0, action, state, forecast, previous)
            scored.append((float(row["objective"]), dx, dy))
        scored.sort(key=lambda item: item[0])
        ranked = [(dx, dy) for _objective, dx, dy in scored]
        if len(ranked) >= 2:
            best_dx, best_dy = ranked[0]
            second_dx, second_dy = ranked[1]
            sensitivity = (
                float(max(-1.0, min(1.0, best_dx + 0.5 * second_dx))),
                float(max(-1.0, min(1.0, best_dy + 0.5 * second_dy))),
            )
            if abs(sensitivity[0]) > 1.0e-9 or abs(sensitivity[1]) > 1.0e-9:
                ranked.insert(0, sensitivity)
        return self._unique_directions(ranked)

    def _unique_directions(self, directions: list[tuple[float, float]]) -> list[tuple[float, float]]:
        seen: set[tuple[float, float]] = set()
        out: list[tuple[float, float]] = []
        for dx, dy in directions:
            key = (round(float(dx), 6), round(float(dy), 6))
            if key in seen:
                continue
            seen.add(key)
            out.append((float(dx), float(dy)))
        return out

    def _evaluate_continuous_action_set(
        self,
        actions: list[LeaderAction],
        state: TrafficState,
        forecast: list[DemandStep],
        previous: ControlAction,
        stage: str,
        index_start: int,
        incumbent_obj: float,
    ) -> tuple[list[_LeaderCandidateEvaluation], float]:
        actions = self._unique_leader_actions(actions)
        if not actions:
            return [], float(incumbent_obj)
        if not bool(self.cfg.mpc.leader_continuous_parallel_multistart):
            eval_cfg = self.cfg.with_updates({"mpc": {"stackelberg_leader_parallel_backend": "serial"}})
            controller = StackelbergMPCController(eval_cfg)
            try:
                results = controller._evaluate_candidate_set(
                    actions,
                    list(range(len(actions))),
                    state,
                    forecast,
                    previous,
                    stage=stage,
                    index_offset=index_start,
                    incumbent_obj=incumbent_obj,
                )
            finally:
                controller.close()
        else:
            # Grid path의 parallel evaluator를 재사용한다. 첫 후보는 serial로
            # incumbent를 만든 뒤 나머지 multi-start 후보를 thread/process로 평가한다.
            results = self._evaluate_candidate_set(
                actions,
                list(range(len(actions))),
                state,
                forecast,
                previous,
                stage=stage,
                index_offset=index_start,
                incumbent_obj=incumbent_obj,
            )
        stage_incumbent = min((float(result.objective) for result in results), default=float(incumbent_obj))
        return results, min(float(incumbent_obj), stage_incumbent)

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

    def _select_pfo_objective_floor(
        self,
        leader_evaluations: list[_LeaderCandidateEvaluation],
        fallback_evaluations: list[_LeaderCandidateEvaluation],
    ) -> tuple[_LeaderCandidateEvaluation, Dict[str, float]]:
        """fix 2: PFO/no-control을 순수 objective 후보로 포함해 min objective를 고른다.

        비대칭 가드(terminal_severe 등) 없이 objective만 비교하므로, leader가 PFO를 못 이기면
        PFO가 선택된다 → P-Stack objective <= PFO objective를 탐색 단계에서 보장한다.
        """
        if not leader_evaluations:
            raise ValueError("Stackelberg leader produced no evaluated candidates.")
        leader_best = min(leader_evaluations, key=lambda item: item.objective)
        candidates = list(leader_evaluations) + list(fallback_evaluations)
        best = min(candidates, key=lambda item: item.objective)
        chose_fallback = best is not leader_best and str(best.stage).startswith("fallback")
        metadata: Dict[str, float] = {
            "leader_pfo_objective_floor_active": 1.0,
            "leader_pfo_objective_floor_selected_fallback": float(chose_fallback),
            "leader_pfo_objective_floor_selected_pfo": float(best.stage == "fallback_pfo"),
            "leader_pfo_objective_floor_selected_no_control": float(best.stage == "fallback_no_control"),
            "leader_pfo_objective_floor_leader_objective": float(leader_best.objective),
            "leader_pfo_objective_floor_selected_objective": float(best.objective),
            "leader_fallback_candidate_count": float(len(fallback_evaluations)),
        }
        for fallback in fallback_evaluations:
            metadata[f"leader_{fallback.stage}_objective"] = float(fallback.objective)
        return best, metadata

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
        no_eval = self._make_fallback_evaluation(
            start_index,
            "fallback_no_control",
            no_nash,
            previous,
            state,
            forecast,
        )
        evaluations.append(no_eval)
        self._append_progress_event(
            event="candidate_evaluated",
            stage="fallback_no_control",
            completed=1,
            total=2,
            evaluation=no_eval,
            best_objective=no_eval.objective,
        )

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
        pfo_eval = self._make_fallback_evaluation(
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
        )
        evaluations.append(pfo_eval)
        self._append_progress_event(
            event="candidate_evaluated",
            stage="fallback_pfo",
            completed=2,
            total=2,
            evaluation=pfo_eval,
            best_objective=min(item.objective for item in evaluations),
        )
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
                "leader_mfd_storage_excess_veh": float(
                    objective_terms.get("leader_mfd_storage_excess_veh", 0.0)
                ),
                "leader_mfd_movement_excess_veh": float(
                    objective_terms.get("leader_mfd_movement_excess_veh", 0.0)
                ),
                "leader_mfd_link_excess_veh": float(objective_terms.get("leader_mfd_link_excess_veh", 0.0)),
                "leader_mfd_storage_penalty": float(objective_terms.get("leader_mfd_storage_penalty", 0.0)),
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
        total_candidates = len(selected_indices)
        self._append_progress_event(
            event="stage_started",
            stage=stage,
            completed=0,
            total=total_candidates,
            best_objective=stage_incumbent if stage_incumbent < float("inf") else None,
        )
        if payloads:
            seed_payload = dict(payloads[0])
            seed_payload["incumbent_obj"] = stage_incumbent
            seed_result = _stackelberg_candidate_worker(seed_payload)
            results.append(seed_result)
            stage_incumbent = min(stage_incumbent, float(seed_result.objective))
            seed_used = True
            self._append_progress_event(
                event="candidate_evaluated",
                stage=stage,
                completed=len(results),
                total=total_candidates,
                evaluation=seed_result,
                best_objective=stage_incumbent,
            )
            payloads = payloads[1:]
            for payload in payloads:
                payload["incumbent_obj"] = stage_incumbent
        if backend == "serial" or workers <= 1:
            for payload in payloads:
                payload["incumbent_obj"] = stage_incumbent
                result = _stackelberg_candidate_worker(payload)
                results.append(result)
                stage_incumbent = min(stage_incumbent, float(result.objective))
                self._append_progress_event(
                    event="candidate_evaluated",
                    stage=stage,
                    completed=len(results),
                    total=total_candidates,
                    evaluation=result,
                    best_objective=stage_incumbent,
                )
            backend_used = "serial"
            chunks = 1
        elif backend == "thread":
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(_stackelberg_candidate_worker, payload) for payload in payloads]
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    stage_incumbent = min(stage_incumbent, float(result.objective))
                    self._append_progress_event(
                        event="candidate_evaluated",
                        stage=stage,
                        completed=len(results),
                        total=total_candidates,
                        evaluation=result,
                        best_objective=stage_incumbent,
                    )
            backend_used = "thread"
            chunks = max(1, len(payloads))
        else:
            if self.cfg.mpc.stackelberg_reuse_process_pool:
                executor, process_pool_reused_existing = self._leader_process_executor(workers)
                futures = [executor.submit(_stackelberg_candidate_worker, payload) for payload in payloads]
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    stage_incumbent = min(stage_incumbent, float(result.objective))
                    self._append_progress_event(
                        event="candidate_evaluated",
                        stage=stage,
                        completed=len(results),
                        total=total_candidates,
                        evaluation=result,
                        best_objective=stage_incumbent,
                    )
            else:
                with ProcessPoolExecutor(max_workers=workers) as executor:
                    futures = [executor.submit(_stackelberg_candidate_worker, payload) for payload in payloads]
                    for future in as_completed(futures):
                        result = future.result()
                        results.append(result)
                        stage_incumbent = min(stage_incumbent, float(result.objective))
                        self._append_progress_event(
                            event="candidate_evaluated",
                            stage=stage,
                            completed=len(results),
                            total=total_candidates,
                            evaluation=result,
                            best_objective=stage_incumbent,
                        )
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
        # In follower_ttt mode, keep the follower response as the base objective
        # but evaluate leader penalties on future MPC rollout states.
        states, rollout_ttt = self._predict(state, nash.control, forecast)
        if self.cfg.leader.objective_mode == "state_accumulation":
            return states, rollout_ttt, True
        return states, float(nash.objective_value), True

        # target/density penalty는 현재 response-state proxy 위에서 평가한다. follower objective
        # 자체가 후보별 response 비용을 담고, full system rollout 비용은 의도적으로 배제한다.

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
