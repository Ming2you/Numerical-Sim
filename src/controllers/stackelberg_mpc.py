from __future__ import annotations

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


class StackelbergMPCController:
    """Spec-first Stackelberg MPC controller.

    This implementation is intentionally self-contained under `src/` and does
    not import any root-level historical controller modules. Leader actions are
    enumerated, follower responses are solved by deterministic projection and
    queue-balancing heuristics, and each candidate is evaluated by the same
    closed-loop model used by the experiment runner.
    """

    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg
        self.leader = Leader(cfg)
        self.nash_solver = self._make_follower_solver(cfg)
        self.previous_control: Optional[ControlAction] = None
        self.last_decision: Optional[DecisionResult] = None

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
            self.cfg = config
            self.leader = Leader(config)
            self.nash_solver = self._make_follower_solver(config)
        forecast = list(demand_forecast)
        if not forecast:
            raise ValueError("StackelbergMPCController requires a non-empty demand forecast.")
        previous = previous_control or self.previous_control or ControlAction.fixed(self.cfg)
        candidates = self.leader.candidates(state, previous, forecast[0], forecast=forecast)
        base_metadata = leader_metadata(candidates)
        base_metadata.update(self._forecast_demand_metadata(forecast))
        evaluations: list[Dict[str, float]] = []
        best: Optional[DecisionResult] = None
        for idx, action in enumerate(candidates):
            nash = self.nash_solver.solve(state.copy(), action, forecast, previous)
            predicted_states, follower_ttt = self._predict(state, nash.control, forecast)
            objective_terms = self.leader.objective_terms(
                predicted_states,
                nash.control,
                previous,
                follower_ttt,
                nash.converged,
                nash.residual_objective,
                nash.residual_control,
            )
            obj = objective_terms["leader_total_objective"]
            evaluations.append({
                "index": float(idx),
                "N_P_star": float(action.N_P_star),
                "N_UF_star": float(action.N_UF_star),
                "objective": float(obj),
                "base": float(objective_terms["leader_objective_base"]),
                "follower_ttt": float(objective_terms["leader_follower_ttt_base"]),
            })
            metadata = dict(base_metadata)
            metadata.update({
                "N_P_crit": float(self.cfg.leader.N_P_crit_veh),
                "nash_iterations": float(nash.iterations),
                "nash_converged": 1.0 if nash.converged else 0.0,
                "nash_residual_control": nash.residual_control,
                "nash_residual_objective": nash.residual_objective,
            })
            metadata.update(objective_terms)
            result = DecisionResult(nash.control, obj, nash, metadata)
            if best is None or result.leader_objective < best.leader_objective:
                best = result
        assert best is not None
        best.metadata.update(self._candidate_evaluation_metadata(evaluations, best.control))
        best.control.diagnostics.update(best.metadata)
        best.control.diagnostics["leader_objective"] = best.leader_objective
        self.previous_control = best.control
        self.last_decision = best
        return best

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
        evaluations: list[Dict[str, float]],
        selected: ControlAction,
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
        return {
            "leader_selected_N_P_star": float(selected.N_P_star),
            "leader_selected_N_UF_star": float(selected.N_UF_star),
            "leader_selected_objective": float(best["objective"]),
            "leader_candidate_best_index": float(best["index"]),
            "leader_candidate_second_index": float(second["index"]),
            "leader_candidate_best_N_P_star": float(best["N_P_star"]),
            "leader_candidate_best_N_UF_star": float(best["N_UF_star"]),
            "leader_candidate_second_N_P_star": float(second["N_P_star"]),
            "leader_candidate_second_N_UF_star": float(second["N_UF_star"]),
            "leader_candidate_best_objective": float(best["objective"]),
            "leader_candidate_second_objective": float(second["objective"]),
            "leader_candidate_objective_gap": float(second["objective"] - best["objective"]),
            "leader_candidate_objective_spread": float(max(objectives) - min(objectives)),
        }

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
