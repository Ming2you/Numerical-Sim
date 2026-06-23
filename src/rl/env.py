from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

import numpy as np

from src.models.demand import (
    DemandProfile,
    ScenarioConfig,
    apply_scenario_network_overrides,
)
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.rl.action_space import (
    LeaderDiscreteActionSpace,
    build_follower_action_spaces,
    centralized_action_space_metadata,
    compose_control_action,
)
from src.rl.agents import RLAgentSpec, build_rl_agent_specs
from src.rl.observations import (
    RLObservation,
    build_follower_observations,
    build_leader_observation,
)
from src.rl.rewards import RewardBreakdown, follower_rewards, leader_reward
from src.simulation.simulator import MixedTrafficSimulator


@dataclass
class RLEnvironmentObservation:
    """leader observation과 현재 leader target 조건의 follower observations."""

    leader: RLObservation
    followers: Dict[str, RLObservation]


@dataclass
class RLStepRecord:
    """학습 없이도 leader target -> follower response -> plant outcome을 복원하는 in-memory log."""

    step_index: int
    time_sec_before: float
    time_sec_after: float
    leader_action_index: int
    leader_action: Dict[str, float]
    follower_action_indices: Dict[str, int]
    physical_follower_actions: Dict[str, Dict[str, Any]]
    control: ControlAction
    leader_observation: RLObservation
    follower_observations: Dict[str, RLObservation]
    leader_reward: float
    follower_rewards: Dict[str, float]
    leader_reward_terms: Dict[str, float]
    follower_reward_terms: Dict[str, Dict[str, float]]
    global_step_ttt: float
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RLEnvStep:
    observation: RLEnvironmentObservation
    leader_reward: float
    follower_rewards: Dict[str, float]
    done: bool
    truncated: bool
    info: Dict[str, Any]
    record: RLStepRecord


class StackelbergRLEnvironment:
    """MixedTrafficSimulator를 Stackelberg-RL decision order로 감싸는 경량 env."""

    def __init__(
        self,
        cfg: ExperimentConfig,
        scenario: ScenarioConfig,
        initial_state: TrafficState | None = None,
        seed: int | None = None,
        leader_n_p_bins: int = 5,
        leader_n_uf_bins: int = 5,
    ):
        self.cfg = apply_scenario_network_overrides(cfg, scenario)
        self.scenario = scenario
        self.initial_state = initial_state.copy() if initial_state is not None else None
        self.seed = int(seed if seed is not None else self.cfg.simulation.random_seed)
        self.rng = np.random.default_rng(self.seed)
        self.demand_profile = DemandProfile(self.cfg, scenario)
        self.sim = MixedTrafficSimulator(self.cfg, self.initial_state)
        self.agents: Dict[str, RLAgentSpec] = build_rl_agent_specs(self.cfg)
        self.leader_action_space = LeaderDiscreteActionSpace(
            self.cfg,
            n_p_bins=leader_n_p_bins,
            n_uf_bins=leader_n_uf_bins,
        )
        self.follower_action_spaces = build_follower_action_spaces(self.cfg, self.agents)
        self.centralized_action_space = centralized_action_space_metadata(
            self.agents,
            self.follower_action_spaces,
        )
        self.previous_control: ControlAction | None = None
        self.step_index = 0
        self.records: list[RLStepRecord] = []

    def reset(self, initial_state: TrafficState | None = None) -> RLEnvironmentObservation:
        self.initial_state = initial_state.copy() if initial_state is not None else self.initial_state
        self.sim = MixedTrafficSimulator(self.cfg, self.initial_state)
        self.previous_control = None
        self.step_index = 0
        self.records = []
        return self.observe()

    def observe(self) -> RLEnvironmentObservation:
        """다음 leader decision 전에 볼 수 있는 compact observation을 반환한다."""

        demand = self.demand_profile.at(self.sim.state.time_sec)
        leader_observation = build_leader_observation(
            self.sim.state,
            self.cfg,
            demand,
            self.previous_control,
        )
        neutral_leader = self.leader_action_space.map_index(self.leader_action_space.neutral_index())
        follower_observations = build_follower_observations(
            self.sim.state,
            self.cfg,
            self.agents,
            neutral_leader,
            self.previous_control,
            demand,
        )
        return RLEnvironmentObservation(leader=leader_observation, followers=follower_observations)

    def follower_observations_for_leader(self, leader_action_index: int) -> Dict[str, RLObservation]:
        """선택된 leader target을 조건으로 follower actor 입력을 만든다."""

        leader_action = self.leader_action_space.map_index(leader_action_index)
        demand = self.demand_profile.at(self.sim.state.time_sec)
        return build_follower_observations(
            self.sim.state,
            self.cfg,
            self.agents,
            leader_action,
            self.previous_control,
            demand,
        )

    def step(
        self,
        leader_action_index: int,
        follower_action_indices: Mapping[str, int] | None = None,
    ) -> RLEnvStep:
        if self.step_index >= self.cfg.simulation.n_control_steps:
            raise RuntimeError("episode is already done; call reset() before stepping again.")

        time_before = float(self.sim.state.time_sec)
        demand = self.demand_profile.at(time_before)
        leader_action = self.leader_action_space.map_index(leader_action_index)
        leader_observation = build_leader_observation(
            self.sim.state,
            self.cfg,
            demand,
            self.previous_control,
        )
        # Stackelberg 순서 보존: leader target이 먼저 정해진 뒤 follower local obs/action이 계산된다.
        follower_observations = build_follower_observations(
            self.sim.state,
            self.cfg,
            self.agents,
            leader_action,
            self.previous_control,
            demand,
        )
        safe_indices = self._complete_follower_indices(follower_action_indices or {})
        control, physical_actions = compose_control_action(
            self.cfg,
            leader_action,
            safe_indices,
            self.agents,
            self.follower_action_spaces,
            self.previous_control,
        )
        log = self.sim.step(control, demand, self.step_index)
        global_step_ttt = float(log.freeway_ttt + log.urban_ttt)
        leader_breakdown = leader_reward(self.sim.state, self.cfg, global_step_ttt)
        follower_breakdowns = follower_rewards(self.sim.state, self.cfg, self.agents)
        self.previous_control = control.copy()

        record = self._build_record(
            time_before=time_before,
            leader_action_index=int(leader_action_index),
            leader_action=leader_action.as_dict(),
            follower_action_indices=safe_indices,
            physical_actions=physical_actions,
            control=control,
            leader_observation=leader_observation,
            follower_observations=follower_observations,
            leader_breakdown=leader_breakdown,
            follower_breakdowns=follower_breakdowns,
            global_step_ttt=global_step_ttt,
            diagnostics=log.diagnostics,
        )
        self.records.append(record)
        self.step_index += 1
        done = self.step_index >= self.cfg.simulation.n_control_steps
        observation = self.observe()
        info = {
            "leader_reward_terms": dict(leader_breakdown.terms),
            "follower_reward_terms": {
                agent_id: dict(breakdown.terms)
                for agent_id, breakdown in follower_breakdowns.items()
            },
            "physical_follower_actions": physical_actions,
            "control_diagnostics": dict(control.diagnostics),
            "sim_diagnostics": dict(log.diagnostics),
            "centralized_action_space": dict(self.centralized_action_space),
        }
        return RLEnvStep(
            observation=observation,
            leader_reward=float(leader_breakdown.reward),
            follower_rewards={
                agent_id: float(breakdown.reward)
                for agent_id, breakdown in follower_breakdowns.items()
            },
            done=done,
            truncated=False,
            info=info,
            record=record,
        )

    def random_follower_action_indices(self) -> Dict[str, int]:
        return {
            agent_id: int(self.rng.integers(0, action_space.size))
            for agent_id, action_space in self.follower_action_spaces.items()
        }

    def random_leader_action_index(self) -> int:
        return int(self.rng.integers(0, self.leader_action_space.size))

    def scripted_safe_action_indices(self) -> tuple[int, Dict[str, int]]:
        """학습 전 smoke용 neutral action set."""

        return (
            self.leader_action_space.neutral_index(),
            {
                agent_id: action_space.neutral_index()
                for agent_id, action_space in self.follower_action_spaces.items()
            },
        )

    def _complete_follower_indices(self, given: Mapping[str, int]) -> Dict[str, int]:
        return {
            agent_id: int(given.get(agent_id, action_space.neutral_index()))
            for agent_id, action_space in self.follower_action_spaces.items()
        }

    def _build_record(
        self,
        time_before: float,
        leader_action_index: int,
        leader_action: Dict[str, float],
        follower_action_indices: Dict[str, int],
        physical_actions: Dict[str, Dict[str, Any]],
        control: ControlAction,
        leader_observation: RLObservation,
        follower_observations: Dict[str, RLObservation],
        leader_breakdown: RewardBreakdown,
        follower_breakdowns: Mapping[str, RewardBreakdown],
        global_step_ttt: float,
        diagnostics: Dict[str, Any],
    ) -> RLStepRecord:
        return RLStepRecord(
            step_index=self.step_index,
            time_sec_before=float(time_before),
            time_sec_after=float(self.sim.state.time_sec),
            leader_action_index=int(leader_action_index),
            leader_action=dict(leader_action),
            follower_action_indices=dict(follower_action_indices),
            physical_follower_actions={
                agent_id: dict(action)
                for agent_id, action in physical_actions.items()
            },
            control=control.copy(),
            leader_observation=leader_observation,
            follower_observations=dict(follower_observations),
            leader_reward=float(leader_breakdown.reward),
            follower_rewards={
                agent_id: float(breakdown.reward)
                for agent_id, breakdown in follower_breakdowns.items()
            },
            leader_reward_terms=dict(leader_breakdown.terms),
            follower_reward_terms={
                agent_id: dict(breakdown.terms)
                for agent_id, breakdown in follower_breakdowns.items()
            },
            global_step_ttt=float(global_step_ttt),
            diagnostics=dict(diagnostics),
        )


def random_safe_rollout(
    cfg: ExperimentConfig,
    scenario: ScenarioConfig,
    max_steps: int = 3,
    seed: int | None = None,
    policy: str = "random",
) -> list[RLStepRecord]:
    """training 없이 random 또는 neutral scripted action으로 짧은 smoke rollout을 수행한다."""

    env = StackelbergRLEnvironment(cfg, scenario, seed=seed)
    env.reset()
    for _ in range(max(0, int(max_steps))):
        if policy == "scripted":
            leader_index, follower_indices = env.scripted_safe_action_indices()
        elif policy == "random":
            leader_index = env.random_leader_action_index()
            follower_indices = env.random_follower_action_indices()
        else:
            raise ValueError("policy must be 'random' or 'scripted'.")
        step = env.step(leader_index, follower_indices)
        if step.done or step.truncated:
            break
    return list(env.records)
