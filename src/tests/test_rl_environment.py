import unittest

from src.models.demand import ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, segment_vsl
from src.rl import StackelbergRLEnvironment, random_safe_rollout


def short_config():
    return ExperimentConfig.from_file(
        "src/config/default.yaml",
        {"simulation": {"T_total": 360.0}},
    )


class StackelbergRLEnvironmentTest(unittest.TestCase):
    def test_no_e_control_actor(self):
        env = StackelbergRLEnvironment(short_config(), ScenarioConfig("test"), seed=7)

        self.assertNotIn("urban_E", env.agents)
        self.assertFalse(any(agent.signal == "E" for agent in env.agents.values()))
        self.assertFalse(env.centralized_action_space["emits_e_control"])

    def test_follower_observations_are_local(self):
        cfg = short_config()
        env = StackelbergRLEnvironment(cfg, ScenarioConfig("test"), seed=7)
        observations = env.follower_observations_for_leader(
            env.leader_action_space.neutral_index()
        )

        self.assertTrue(observations)
        for obs in observations.values():
            names = " ".join(obs.feature_names)
            self.assertNotIn("global", names)
            self.assertNotIn("all_freeway", names)
            self.assertNotIn("all_urban", names)
            if obs.family == "freeway_segment":
                self.assertLessEqual(len(obs.owned_links), 1)
                self.assertLess(len(obs.features), len(cfg.network.freeway_links) * cfg.network.freeway_segments_per_link * 3)
            if obs.family == "urban_intersection":
                self.assertEqual(len(obs.owned_signals), 1)
                self.assertLess(len(obs.owned_movements), len(cfg.network.urban_movements))

    def test_action_mappings_respect_physical_bounds(self):
        cfg = short_config()
        env = StackelbergRLEnvironment(cfg, ScenarioConfig("test"), seed=7)
        n_p_low, n_p_high = cfg.leader.N_P_star_range
        n_uf_low, n_uf_high = cfg.leader.N_UF_star_range

        for action in env.leader_action_space.actions:
            self.assertGreaterEqual(action.N_P_star, n_p_low)
            self.assertLessEqual(action.N_P_star, n_p_high)
            self.assertGreaterEqual(action.N_UF_star, n_uf_low)
            self.assertLessEqual(action.N_UF_star, n_uf_high)

        for agent_id, action_space in env.follower_action_spaces.items():
            agent = env.agents[agent_id]
            for index in range(action_space.size):
                if agent.is_freeway:
                    action = action_space.map_index(index)
                    self.assertGreaterEqual(action.vsl_km_h, cfg.freeway_follower.vsl_min_km_h)
                    self.assertLessEqual(action.vsl_km_h, cfg.freeway_follower.vsl_max_km_h)
                    for ramp, value in action.ramp_metering.items():
                        cap = cfg.network.ramp_capacity_veh_h[ramp]
                        self.assertGreaterEqual(value, cfg.freeway_follower.ramp_metering_rate_min * cap)
                        self.assertLessEqual(value, cfg.freeway_follower.ramp_metering_rate_max * cap)
                else:
                    action = action_space.map_index(index)
                    self.assertGreaterEqual(action.green_p1_sec, cfg.network.green_min)
                    self.assertGreaterEqual(action.green_p2_sec, cfg.network.green_min)
                    self.assertLessEqual(action.green_p1_sec, cfg.network.green_max)
                    self.assertLessEqual(action.green_p2_sec, cfg.network.green_max)
                    self.assertAlmostEqual(
                        action.green_p1_sec + action.green_p2_sec,
                        cfg.network.effective_green_total,
                    )
                    self.assertTrue(all(0.0 <= value < cfg.network.cycle_length for value in action.offsets.values()))

    def test_extreme_vsl_action_projects_to_dynamic_step_bound(self):
        cfg = short_config()
        env = StackelbergRLEnvironment(cfg, ScenarioConfig("test"), seed=7)
        freeway_agent_id = next(
            agent_id for agent_id, agent in env.agents.items() if agent.is_freeway
        )
        agent = env.agents[freeway_agent_id]
        action_space = env.follower_action_spaces[freeway_agent_id]
        extreme_index = min(
            range(action_space.size),
            key=lambda index: action_space.map_index(index).vsl_km_h,
        )
        leader_index, follower_indices = env.scripted_safe_action_indices()
        follower_indices[freeway_agent_id] = extreme_index
        previous = ControlAction.fixed(cfg)
        previous_vsl = segment_vsl(previous, agent.link, agent.segment_index, cfg)
        requested_vsl = action_space.map_index(extreme_index).vsl_km_h

        step = env.step(leader_index, follower_indices)
        applied_vsl = segment_vsl(
            step.record.control,
            agent.link,
            agent.segment_index,
            cfg,
        )
        action_details = step.record.physical_follower_actions[freeway_agent_id]
        diagnostics = step.record.control.diagnostics

        self.assertGreater(abs(requested_vsl - previous_vsl), cfg.freeway_follower.max_vsl_step)
        self.assertAlmostEqual(
            abs(applied_vsl - previous_vsl),
            cfg.freeway_follower.max_vsl_step,
        )
        self.assertGreaterEqual(applied_vsl, cfg.freeway_follower.vsl_min_km_h)
        self.assertLessEqual(applied_vsl, cfg.freeway_follower.vsl_max_km_h)
        self.assertEqual(diagnostics["rl_action_projection_applied"], 1.0)
        self.assertGreaterEqual(diagnostics["rl_projected_vsl_action_count"], 1.0)
        self.assertGreater(diagnostics["rl_max_requested_vsl_delta"], cfg.freeway_follower.max_vsl_step)
        self.assertLessEqual(diagnostics["rl_max_applied_vsl_delta"], cfg.freeway_follower.max_vsl_step)
        self.assertEqual(diagnostics["rl_action_fallback_used"], 0.0)
        self.assertEqual(action_details["requested_vsl_km_h"], requested_vsl)
        self.assertEqual(action_details["applied_vsl_km_h"], applied_vsl)
        self.assertEqual(action_details["vsl_projected"], 1.0)

    def test_short_safe_rollout_completes(self):
        records = random_safe_rollout(
            short_config(),
            ScenarioConfig("test"),
            max_steps=2,
            seed=7,
            policy="random",
        )

        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.global_step_ttt >= 0.0 for record in records))
        self.assertTrue(all(record.control.diagnostics["rl_emits_e_control"] == 0.0 for record in records))
        self.assertTrue(all("global_step_ttt" in record.leader_reward_terms for record in records))
        for record in records:
            self.assertTrue(record.follower_rewards)
            self.assertTrue(all(value <= 0.0 for value in record.follower_rewards.values()))
            self.assertTrue(all(terms for terms in record.follower_reward_terms.values()))


if __name__ == "__main__":
    unittest.main()
