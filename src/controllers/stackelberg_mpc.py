from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

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
        self.nash_solver = NashSolver(cfg)
        self.previous_control: Optional[ControlAction] = None
        self.last_decision: Optional[DecisionResult] = None

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
            self.nash_solver = NashSolver(config)
        forecast = list(demand_forecast)
        first_demand = forecast[0]
        previous = previous_control or self.previous_control or ControlAction.fixed(self.cfg)
        candidates = self.leader.candidates(state, previous)
        best: Optional[DecisionResult] = None
        for action in candidates:
            nash = self.nash_solver.solve(state.copy(), action, first_demand, previous)
            predicted_states, follower_ttt = self._predict(state, nash.control, forecast)
            obj = self.leader.objective(
                predicted_states,
                nash.control,
                previous,
                follower_ttt + nash.objective_value,
                nash.converged,
            )
            metadata = leader_metadata(candidates)
            metadata.update({
                "nash_iterations": float(nash.iterations),
                "nash_converged": 1.0 if nash.converged else 0.0,
                "nash_residual_control": nash.residual_control,
                "nash_residual_objective": nash.residual_objective,
            })
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
        from src.models.metanet import freeway_step
        from src.models.urban_queue_model import urban_step

        s = state.copy()
        states: list[TrafficState] = []
        total_ttt = 0.0
        for demand in forecast[: self.cfg.mpc.horizon_steps]:
            fw_ttt, _ = freeway_step(s, control, demand, self.cfg)
            ur_ttt, _ = urban_step(s, control, demand, self.cfg)
            s.time_sec += self.cfg.simulation.control_interval
            total_ttt += fw_ttt + ur_ttt
            states.append(s.copy())
        return states, float(total_ttt)
