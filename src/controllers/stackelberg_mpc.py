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
        candidates = self.leader.candidates(state, previous, forecast[0])
        best: Optional[DecisionResult] = None
        for action in candidates:
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
            metadata = leader_metadata(candidates)
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
        best.control.diagnostics.update(best.metadata)
        best.control.diagnostics["leader_objective"] = best.leader_objective
        self.previous_control = best.control
        self.last_decision = best
        return best

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
