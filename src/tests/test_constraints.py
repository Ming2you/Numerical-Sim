import unittest
from unittest.mock import patch

from src.controllers.distributed_coordinator import AgentSolve, DistributedCoordinator, build_agent_specs
from src.controllers.freeway_follower import FreewayFollower, FreewayFollowerResult
from src.controllers.leader import Leader, LeaderAction
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.controllers.urban_follower import UrbanFollower
from src.evaluation.metrics import validate_controls
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.metanet import effective_lane_profile
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    movement_storage_capacity,
    sync_onramp_queues_from_freeway,
    sync_onramp_queues_to_freeway,
    urban_substep,
)
from src.simulation.coupling import CoupledStepResult, run_coupled_interval
from src.simulation.simulator import MixedTrafficSimulator


def short_config():
    return ExperimentConfig.from_file(
        "src/config/default.yaml",
        {"simulation": {"T_total": 360.0}, "mpc": {"leader_candidate_count": 5, "max_nash_iter": 3}},
    )


class ConstraintTests(unittest.TestCase):
    def test_vsl_values_are_discrete(self):
        cfg = short_config()
        demand = DemandProfile(cfg, ScenarioConfig("test")).horizon(0.0, 2)
        control = StackelbergMPCController(cfg).decide(TrafficState.initial(cfg), demand)
        self.assertTrue(all(v in cfg.freeway_follower.vsl_set for v in control.vsl.values()))

    def test_distributed_agent_partition_matches_topology(self):
        cfg = short_config()
        urban_agents, freeway_agents = build_agent_specs(cfg)
        self.assertEqual(len(urban_agents), 5)
        self.assertEqual(len(freeway_agents), 6)
        self.assertEqual({agent.id for agent in urban_agents}, {"U_A", "U_B", "U_C", "U_D", "U_F"})
        self.assertEqual({agent.id for agent in freeway_agents}, {"F_W0", "F_W1", "F_W2", "F_E0", "F_E1", "F_E2"})
        d_agent = next(agent for agent in urban_agents if agent.id == "U_D")
        self.assertIn("D_N_to_onW", d_agent.movements)
        self.assertIn("D_offW_to_N", d_agent.movements)
        fw_merge_agent = next(agent for agent in freeway_agents if agent.id == "F_W1")
        self.assertIn("R_D_W", fw_merge_agent.ramps)
        self.assertIn("R_F_W", fw_merge_agent.ramps)
        freeway_ids = {agent.id for agent in freeway_agents}
        for agent in urban_agents:
            self.assertTrue(set(agent.neighbors).issubset(freeway_ids))
        self.assertEqual(
            set(d_agent.neighbors),
            {"F_W1", "F_W2", "F_E1", "F_E2"},
        )

    def test_distributed_coordinator_returns_per_agent_diagnostics(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "simulation": {"T_total": 360.0},
                "mpc": {
                    "follower_solver_mode": "distributed",
                    "max_nash_iter": 2,
                    "leader_candidate_count": 2,
                },
            },
        )
        state = TrafficState.initial(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).horizon(0.0, 1)
        result = DistributedCoordinator(cfg).solve(
            state,
            LeaderAction(cfg.leader.N_P_crit_veh, 1200.0),
            demand,
            ControlAction.fixed(cfg),
        )
        self.assertEqual(result.control.diagnostics["distributed_player_active"], 1.0)
        self.assertEqual(result.control.diagnostics["distributed_urban_agent_count"], 5.0)
        self.assertEqual(result.control.diagnostics["distributed_freeway_agent_count"], 6.0)
        self.assertIn("agent_U_A_objective", result.control.diagnostics)
        self.assertIn("agent_F_W1_objective", result.control.diagnostics)
        self.assertEqual(set(result.control.vsl), set(cfg.network.freeway_links))
        boundary_out_total = sum(
            result.control.inflow_outflow_allocation[movement]
            for movement, spec in cfg.network.urban_movements.items()
            if spec.get("destination") == "out_A_left" and spec.get("kind") == "boundary_out"
        )
        self.assertAlmostEqual(
            result.control.inflow_outflow_allocation["out_A_left"],
            boundary_out_total,
        )

    def test_distributed_link_vsl_consensus_is_order_independent(self):
        cfg = short_config()
        coordinator = DistributedCoordinator(cfg)
        solves = [
            AgentSolve(agent_id="F_W0", objective=0.0, vsl={"FW_W": 100.0}),
            AgentSolve(agent_id="F_W1", objective=0.0, vsl={"FW_W": 80.0}),
            AgentSolve(agent_id="F_W2", objective=0.0, vsl={"FW_W": 60.0}),
        ]
        self.assertEqual(coordinator._aggregate_link_vsl(solves)["FW_W"], 60.0)
        self.assertEqual(coordinator._aggregate_link_vsl(list(reversed(solves)))["FW_W"], 60.0)

    def test_leaderless_metering_prediction_includes_upstream_mainline_flow(self):
        cfg = short_config()
        coordinator = DistributedCoordinator(cfg)
        state = TrafficState.initial(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).at(0.0)
        agent = next(item for item in coordinator.freeway_agents if item.id == "F_W1")
        upper = {ramp: cfg.network.ramp_capacity_veh_h[ramp] for ramp in agent.ramps}

        state.freeway_flow["FW_W"][0] = 0.0
        low_inflow_target = coordinator._leaderless_metering_target(agent, state, upper, demand)
        state.freeway_flow["FW_W"][0] = 8000.0
        high_inflow_target = coordinator._leaderless_metering_target(agent, state, upper, demand)

        self.assertLess(high_inflow_target, low_inflow_target)

    def test_leader_candidate_budget_covers_extremes_and_previous_action(self):
        cfg = short_config()
        state = TrafficState.initial(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).at(0.0)
        previous = ControlAction.fixed(cfg)
        # previous N_P_star는 후보 범위(n_crit×[0.9,1.05]) 안이어야 clip 없이 보존된다.
        previous.N_P_star = 750.0
        previous.N_UF_star = 3333.0
        candidates = Leader(cfg).candidates(state, previous, demand)

        pairs = {(round(c.N_P_star, 6), round(c.N_UF_star, 6)) for c in candidates}
        np_values = [c.N_P_star for c in candidates]
        nuf_values = [c.N_UF_star for c in candidates]
        self.assertIn((round(min(np_values), 6), round(min(nuf_values), 6)), pairs)
        self.assertIn((round(max(np_values), 6), round(max(nuf_values), 6)), pairs)
        self.assertIn((750.0, 3333.0), pairs)

    def test_stackelberg_can_use_distributed_follower_solver(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "simulation": {"T_total": 360.0},
                "mpc": {
                    "follower_solver_mode": "distributed",
                    "max_nash_iter": 2,
                    "leader_candidate_count": 2,
                },
            },
        )
        demand = DemandProfile(cfg, ScenarioConfig("test")).horizon(0.0, 1)
        control = StackelbergMPCController(cfg).decide(TrafficState.initial(cfg), demand)
        self.assertEqual(control.diagnostics["distributed_player_active"], 1.0)
        self.assertEqual(control.diagnostics["nash_per_agent_active"], 1.0)

    def test_green_times_sum_to_cycle_length(self):
        cfg = short_config()
        control = ControlAction.fixed(cfg)
        for signal in cfg.network.signals:
            total = control.green_times[f"{signal}_p1"] + control.green_times[f"{signal}_p2"] + cfg.network.lost_time
            self.assertAlmostEqual(total, cfg.network.cycle_length)

    def test_green_time_bounds(self):
        cfg = short_config()
        demand = DemandProfile(cfg, ScenarioConfig("test")).horizon(0.0, 2)
        control = StackelbergMPCController(cfg).decide(TrafficState.initial(cfg), demand)
        for value in control.green_times.values():
            self.assertGreaterEqual(value, cfg.network.green_min)
            self.assertLessEqual(value, cfg.network.green_max)

    def test_urban_follower_returns_movement_level_allocations(self):
        cfg = short_config()
        demand = DemandProfile(cfg, ScenarioConfig("test")).horizon(0.0, 2)
        control = StackelbergMPCController(cfg).decide(TrafficState.initial(cfg), demand)
        movement_keys = [
            movement for movement, spec in cfg.network.urban_movements.items()
            if spec.get("kind") in {"boundary_in", "off_ramp", "on_ramp"}
        ]
        self.assertTrue(all(movement in control.inflow_outflow_allocation for movement in movement_keys))

    def test_offset_range(self):
        cfg = short_config()
        demand = DemandProfile(cfg, ScenarioConfig("test")).horizon(0.0, 2)
        control = StackelbergMPCController(cfg).decide(TrafficState.initial(cfg), demand)
        for value in control.offsets.values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLess(value, cfg.network.cycle_length)

    def test_leader_np_candidates_use_calibrated_crit_band(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "mpc": {"leader_candidate_count": 6},
                "leader": {
                    "N_P_crit_veh": 172.0,
                    "N_P_candidate_lower_factor": 0.9,
                    "N_P_candidate_upper_factor": 1.05,
                },
            },
        )
        state = TrafficState.initial(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).at(0.0)
        previous = ControlAction.fixed(cfg)
        previous.N_P_star = 333.0

        actions = Leader(cfg).candidates(state, previous, demand)
        nps = [action.N_P_star for action in actions]
        self.assertTrue(all(0.9 * 172.0 <= value <= 1.05 * 172.0 for value in nps))
        self.assertTrue(any(abs(value - 172.0) <= 1.0e-9 for value in nps))

        congested = state.copy()
        for movement in congested.urban_movement_queue:
            congested.urban_movement_queue[movement] = 0.0
        # internal movement 큐는 보호영역 누적 N_P에 포함된다(그리드 라우팅 이후 정의).
        congested.urban_movement_queue["A_S_to_E"] = 220.0
        congested_actions = Leader(cfg).candidates(congested, previous, demand)
        self.assertTrue(all(action.N_P_star <= 172.0 + 1.0e-9 for action in congested_actions))

    def test_leader_objective_matches_spec_accumulation_form(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "leader": {
                    "objective_mode": "state_accumulation",
                    "w_P": 2.0,
                    "w_F": 3.0,
                    "w_L": 0.5,
                    "N_P_crit_veh": 100.0,
                    "non_convergence_penalty": 0.0,
                }
            },
        )
        state = TrafficState.initial(cfg)
        for movement in state.urban_movement_queue:
            state.urban_movement_queue[movement] = 0.0
        state.urban_movement_queue["A_N_to_S"] = 120.0
        # 보호영역 누적(내부 link storage 점유)을 perimeter penalty 경로가 동작하도록 설정한다.
        grid_cap = cfg.network.urban_link_storage_veh["A_to_D"]
        state.urban_link_storage["A_to_D"] = grid_cap - 150.0
        for link in cfg.network.freeway_links:
            state.freeway_density[link] = [cfg.network.rho_crit + 2.0 for _ in state.freeway_density[link]]
            state.freeway_speed[link] = [cfg.network.v_free for _ in state.freeway_speed[link]]
        state.refresh_freeway_flow(cfg.network)

        action = ControlAction.fixed(cfg)
        action.N_P_star = 170.0
        action.N_UF_star = 300.0
        previous = ControlAction.fixed(cfg)
        previous.N_P_star = 160.0
        previous.N_UF_star = 250.0

        n_p = state.total_urban_vehicles(cfg.network)
        n_p_protected = state.protected_accumulation_veh(cfg.network)
        n_f = state.total_freeway_vehicles(cfg.network)
        density_excess = sum(
            cfg.network.freeway_segment_length_km
            * cfg.network.freeway_lanes
            * max(0.0, rho - cfg.network.rho_crit)
            for values in state.freeway_density.values()
            for rho in values
        )
        expected = (
            n_p
            + n_f
            + 2.0 * max(0.0, n_p_protected - 100.0)
            + 3.0 * density_excess
            + 0.5 * (abs(170.0 - 160.0) + abs(300.0 - 250.0))
        )
        actual = Leader(cfg).objective([state], action, previous, follower_objective=9999.0, nash_converged=True)
        self.assertAlmostEqual(actual, expected)

    def test_ramp_metering_bounds(self):
        cfg = short_config()
        state = TrafficState.initial(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).at(0.0)
        result = FreewayFollower(cfg).solve(state, LeaderAction(0.0, 5000.0), demand)
        for ramp, value in result.ramp_metering.items():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, cfg.network.ramp_capacity_veh_h[ramp])

    def test_total_metering_tracking_or_infeasibility_flag(self):
        cfg = short_config()
        state = TrafficState.initial(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).at(0.0)
        result = FreewayFollower(cfg).solve(state, LeaderAction(0.0, 10000.0), demand)
        error = abs(sum(result.ramp_metering.values()) - 10000.0)
        # N_UF는 ceiling 목표: 원목표(10000)를 못 채우면 추적잔차 대신
        # metering_target_infeasible로 명시 로깅된다(acceptance 기준 문서 참조).
        self.assertTrue(
            error <= cfg.freeway_follower.eps_F
            or result.infeasibility["metering_residual"] > 0.0
            or result.infeasibility["metering_target_infeasible"] > 0.0
        )

    def test_ramp_metering_respects_downstream_receiving_capacity(self):
        cfg = short_config()
        state = TrafficState.initial(cfg)
        for link in cfg.network.freeway_links:
            merge_idx = len(state.freeway_density[link]) // 2
            state.freeway_density[link][merge_idx] = cfg.network.rho_max
        demand = DemandProfile(cfg, ScenarioConfig("test", ramp_scale=3.0)).at(0.0)
        result = FreewayFollower(cfg).solve(state, LeaderAction(0.0, 3000.0), demand)
        self.assertTrue(all(value <= 1.0e-9 for value in result.ramp_metering.values()))
        # receiving 붕괴로 목표(3000)를 풀 수 없는 상황 — 명시적 infeasible 플래그가
        # 핵심 검증이다. (큐-증가 기반 잔차는 경량 예측 경로에선 큐를 안 키워 0일 수 있음.)
        self.assertGreater(result.infeasibility["metering_target_infeasible"], 0.0)

    def test_freeway_follower_scores_over_forecast_horizon(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "simulation": {"T_total": 360.0},
                "mpc": {"horizon_steps": 3},
                "freeway_follower": {"vsl_set": [100], "max_vsl_step": 0.0},
            },
        )
        state = TrafficState.initial(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).horizon(0.0, 3)
        used_demand_ids = []

        def fake_lightweight_transition(*args):
            state_arg = args[-3]
            demand_step = args[-1]
            used_demand_ids.append(id(demand_step))
            return (
                state_arg.copy(),
                1.0,
                {"total_metering_error": 0.0, "mean_ramp_receiving_factor": 1.0},
            )

        with patch(
            "src.controllers.freeway_follower.FreewayFollower._lightweight_transition",
            side_effect=fake_lightweight_transition,
        ):
            result = FreewayFollower(cfg).solve(
                state,
                LeaderAction(0.0, 1200.0),
                demand,
                ControlAction.fixed(cfg),
            )

        self.assertIn(id(demand[2]), used_demand_ids)
        self.assertEqual(result.infeasibility["freeway_follower_horizon_steps"], 3.0)
        self.assertEqual(result.infeasibility["freeway_follower_sequence_optimized"], 1.0)

    def test_freeway_follower_expands_time_varying_vsl_sequence(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "simulation": {"T_total": 360.0},
                "mpc": {"horizon_steps": 2},
                "freeway_follower": {
                    "vsl_set": [60, 80, 100],
                    "max_vsl_step": 20.0,
                    "horizon_beam_width": 1,
                    "horizon_ramp_candidate_limit": 1,
                    "horizon_vsl_candidate_limit_per_link": 3,
                },
            },
        )
        state = TrafficState.initial(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).horizon(0.0, 2)
        second_step_vsl_values = []

        def fake_lightweight_transition(*args):
            state_arg = args[-3]
            control = args[-2]
            demand_step = args[-1]
            if demand_step is demand[1]:
                second_step_vsl_values.extend(control.vsl.values())
            if demand_step is demand[0] and min(control.vsl.values()) < 100.0:
                return (
                    state_arg.copy(),
                    1.0,
                    {"total_metering_error": 0.0, "mean_ramp_receiving_factor": 1.0},
                )
            return (
                state_arg.copy(),
                10.0,
                {"total_metering_error": 0.0, "mean_ramp_receiving_factor": 1.0},
            )

        with patch(
            "src.controllers.freeway_follower.FreewayFollower._lightweight_transition",
            side_effect=fake_lightweight_transition,
        ):
            FreewayFollower(cfg).solve(
                state,
                LeaderAction(0.0, 1200.0),
                demand,
                ControlAction.fixed(cfg),
            )

        self.assertIn(60.0, second_step_vsl_values)

    def test_freeway_follower_activates_vsl_under_capacity_drop(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "simulation": {"T_total": 180.0},
                "mpc": {"horizon_steps": 3},
                "network": {
                    "off_ramp_split_ratio": {
                        "OR_D_W": 0.25,
                        "OR_F_W": 0.25,
                        "OR_D_E": 0.25,
                        "OR_F_E": 0.25,
                    }
                },
                "freeway_offramp_capacity_drop": {
                    "enabled": True,
                    "lane_reduction": 0.75,
                    "gamma": 0.2,
                    "b": 2.0,
                },
                "freeway_follower": {
                    "vsl_smoothness_weight": 0.0,
                    "horizon_beam_width": 4,
                    "horizon_vsl_candidate_limit_per_link": 3,
                },
            },
        )
        state = TrafficState.initial(cfg)
        for link in cfg.network.freeway_links:
            state.freeway_density[link] = [28.0, 34.0, 45.0]
            state.freeway_speed[link] = [90.0, 75.0, 45.0]
            state.freeway_effective_lanes[link] = [2.0, 2.0, 2.0]
        for storage_link in cfg.network.off_ramp_storage_link.values():
            state.urban_link_storage[storage_link] = 0.0

        _, lane_diag = effective_lane_profile(state, cfg)
        self.assertEqual(lane_diag["capacity_drop_active"], 1.0)
        self.assertLess(lane_diag["lambda_eff_FW_W_last"], cfg.network.freeway_lanes)

        demand = DemandProfile(
            cfg,
            ScenarioConfig(
                "forced_capacity_drop",
                urban_scale=0.0,
                freeway_scale=1.4,
                ramp_scale=0.8,
                incident_capacity_factor=1.0,
            ),
        ).horizon(0.0, cfg.mpc.horizon_steps)
        result = FreewayFollower(cfg).solve(
            state,
            LeaderAction(0.0, 0.0),
            demand,
            ControlAction.fixed(cfg),
        )

        self.assertTrue(any(
            value < max(cfg.freeway_follower.vsl_set) - 0.5
            for value in result.vsl.values()
        ))

    def test_boundary_queue_balance_safe_division(self):
        from src.models.urban_queue_model import safe_balance_index

        self.assertEqual(safe_balance_index([0.0, 0.0]), 0.0)

    def test_boundary_balance_gate_uses_movement_level_b_not_cv(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {"evaluation": {"eps_balance": 0.03}, "urban_follower": {"eps_U": 100.0}},
        )
        baseline_state = TrafficState.initial(cfg)
        proposed_state = TrafficState.initial(cfg)
        for idx, link in enumerate(cfg.network.movement_links):
            proposed_state.boundary_queue[link] = 120.0 if idx == 0 else 10.0
        for movement, spec in cfg.network.urban_movements.items():
            if spec.get("kind") in {"boundary_in", "off_ramp", "boundary_out", "on_ramp"}:
                proposed_state.urban_movement_queue[movement] = 0.5 * movement_storage_capacity(cfg, movement, spec)
        validation = validate_controls(
            {"final_state": baseline_state, "run_rows": [], "control_rows": []},
            {"final_state": proposed_state, "run_rows": [], "control_rows": []},
            cfg,
        )
        self.assertGreater(validation["boundary_balance"]["CV_boundary"], 0.0)
        self.assertEqual(validation["boundary_balance"]["boundary_balance_degenerate"], 0.0)
        self.assertTrue(validation["boundary_balance"]["pass"])

    def test_degenerate_boundary_balance_does_not_trivially_pass(self):
        cfg = ExperimentConfig.from_file("src/config/default.yaml", {"evaluation": {"eps_balance": 0.03}})
        baseline_state = TrafficState.initial(cfg)
        proposed_state = TrafficState.initial(cfg)
        for movement in proposed_state.urban_movement_queue:
            proposed_state.urban_movement_queue[movement] = 0.0
        validation = validate_controls(
            {"final_state": baseline_state, "run_rows": [], "control_rows": []},
            {"final_state": proposed_state, "run_rows": [], "control_rows": []},
            cfg,
        )
        self.assertEqual(validation["boundary_balance"]["B_in"], 0.0)
        self.assertEqual(validation["boundary_balance"]["B_out"], 0.0)
        self.assertEqual(validation["boundary_balance"]["boundary_balance_degenerate"], 1.0)
        self.assertFalse(validation["boundary_balance"]["pass"])

    def test_no_negative_density_speed_queue(self):
        cfg = short_config()
        sim = MixedTrafficSimulator(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).at(0.0)
        sim.step(ControlAction.fixed(cfg), demand, 0)
        for values in sim.state.freeway_density.values():
            self.assertTrue(all(v >= 0.0 for v in values))
        for values in sim.state.freeway_speed.values():
            self.assertTrue(all(v >= 0.0 for v in values))
        self.assertTrue(all(v >= 0.0 for v in sim.state.ramp_queue.values()))
        self.assertTrue(all(v >= 0.0 for v in sim.state.boundary_queue.values()))
        self.assertTrue(all(v >= 0.0 for v in sim.state.urban_movement_queue.values()))
        self.assertTrue(all(v >= 0.0 for v in sim.state.urban_link_storage.values()))

    def test_simulator_uses_coupling_module_diagnostics(self):
        cfg = short_config()
        sim = MixedTrafficSimulator(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).at(0.0)
        log = sim.step(ControlAction.fixed(cfg), demand, 0)
        self.assertEqual(log.diagnostics["coupling_freeway_substeps"], float(cfg.simulation.K_cf))
        self.assertEqual(log.diagnostics["coupling_urban_substeps"], float(cfg.simulation.K_cu))
        self.assertEqual(log.diagnostics["coupling_nested_order_active"], 1.0)
        self.assertEqual(log.diagnostics["coupling_aggregate_urban_model"], 0.0)
        self.assertEqual(log.diagnostics["coupling_movement_urban_model"], 1.0)
        self.assertEqual(log.diagnostics["coupling_onramp_sync_active"], 1.0)
        self.assertEqual(log.diagnostics["coupling_onramp_two_reservoir_active"], 1.0)
        self.assertEqual(log.diagnostics["coupling_offramp_storage_active"], 1.0)

    def test_onramp_uses_two_reservoirs_instead_of_syncing_queues(self):
        cfg = short_config()
        state = TrafficState.initial(cfg)
        state.ramp_queue["R_D_W"] = 30.0
        state.urban_movement_queue["D_N_to_onW"] = 70.0
        sync_onramp_queues_from_freeway(state, cfg)
        self.assertAlmostEqual(state.ramp_queue["R_D_W"], 30.0)
        self.assertAlmostEqual(state.urban_movement_queue["D_N_to_onW"], 70.0)
        sync_onramp_queues_to_freeway(state, cfg)
        self.assertAlmostEqual(state.ramp_queue["R_D_W"], 30.0)
        self.assertAlmostEqual(state.urban_movement_queue["D_N_to_onW"], 70.0)

    def test_onramp_demand_enters_urban_movement_queue_when_metering_closed(self):
        cfg = short_config()
        sim = MixedTrafficSimulator(cfg)
        control = ControlAction.fixed(cfg)
        control.ramp_metering = {ramp: 0.0 for ramp in cfg.network.ramps}
        demand = DemandProfile(cfg, ScenarioConfig("test", ramp_scale=2.0)).at(0.0)
        log = sim.step(control, demand, 0)
        self.assertGreater(log.diagnostics["onramp_arrivals_veh"], 0.0)
        self.assertAlmostEqual(log.diagnostics["ramp_metering_releases_veh"], 0.0)
        self.assertGreater(log.diagnostics["onramp_green_releases_veh"], 0.0)
        self.assertGreater(
            log.diagnostics["onramp_approach_queue_veh"] + log.diagnostics["ramp_queue_veh"],
            0.0,
        )

    def test_onramp_green_controls_approach_release_to_ramp_queue(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {"simulation": {"T_total": 10.0, "T_f": 10.0, "T_u": 5.0, "control_interval": 10.0}},
        )
        demand = DemandProfile(cfg, ScenarioConfig("test", ramp_scale=0.0)).at(0.0)
        low = TrafficState.initial(cfg)
        high = TrafficState.initial(cfg)
        for state in (low, high):
            for ramp in cfg.network.ramps:
                state.ramp_queue[ramp] = 0.0
            for movements in cfg.network.on_ramp_to_movement.values():
                for movement in movements:
                    state.urban_movement_queue[movement] = 40.0

        low_control = ControlAction.fixed(cfg)
        high_control = ControlAction.fixed(cfg)
        # on_ramp 행 movement는 incoming approach 축으로 phase가 갈린다 — 양 phase 모두 조인다.
        for phase in ("D_p1", "D_p2"):
            low_control.green_times[phase] = cfg.network.green_min
            high_control.green_times[phase] = cfg.network.green_max
        for movement in cfg.network.on_ramp_to_movement["R_D_W"]:
            low_control.inflow_outflow_allocation[movement] = cfg.network.movement_capacity_veh_h
            high_control.inflow_outflow_allocation[movement] = cfg.network.movement_capacity_veh_h
        ramp_release = {ramp: 0.0 for ramp in cfg.network.ramps}

        # cycle 위상 plant에서는 substep별 green이 이진(window)이므로 한 cycle을
        # 누적해 비교한다(green이 길수록 cycle당 방출이 커야 한다).
        cycle_steps = int(cfg.network.cycle_length / cfg.simulation.T_u_sec)
        low_release = 0.0
        high_release = 0.0
        for step in range(cycle_steps):
            _, low_diag = urban_substep(low, low_control, demand, cfg, urban_step_index=step, ramp_release_veh_h=ramp_release)
            _, high_diag = urban_substep(high, high_control, demand, cfg, urban_step_index=step, ramp_release_veh_h=ramp_release)
            low_release += low_diag["onramp_green_releases_veh"]
            high_release += high_diag["onramp_green_releases_veh"]

        self.assertGreater(high.ramp_queue["R_D_W"], low.ramp_queue["R_D_W"])
        self.assertGreater(high_release, low_release)

    def test_coupling_passes_actual_ramp_release_to_freeway_step(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {"simulation": {"T_total": 10.0, "T_f": 10.0, "T_u": 5.0, "control_interval": 10.0}},
        )
        state = TrafficState.initial(cfg)
        for ramp in cfg.network.ramps:
            state.ramp_queue[ramp] = 0.0
        # 게이트→ramp 직결 movement(β 자연 분산)도 w_r를 채우므로 ramp행 큐를 전부 비운다.
        for movement, spec in cfg.network.urban_movements.items():
            if spec.get("ramp"):
                state.urban_movement_queue[movement] = 0.0
        control = ControlAction.fixed(cfg)
        # urban 게이트 수요가 같은 interval 안에서 ramp로 넘어가지 않게 urban_scale=0.
        demand = DemandProfile(cfg, ScenarioConfig("test", urban_scale=0.0, ramp_scale=0.0)).at(0.0)
        requested_release = {ramp: 1000.0 for ramp in cfg.network.ramps}
        seen_release = []

        def fake_compute_release(*_args, **_kwargs):
            return requested_release, {
                "total_metering_flow": sum(requested_release.values()),
                "total_no_meter_flow": sum(requested_release.values()),
                "mean_ramp_receiving_factor": 1.0,
            }

        def fake_freeway_substep(*_args, **kwargs):
            actual = dict(kwargs["ramp_release_veh_h"])
            seen_release.append(actual)
            return 0.0, {
                "total_metering_flow": sum(actual.values()),
                "total_metering_error": 0.0,
                "mean_ramp_receiving_factor": 1.0,
                "offramp_flow_total": 0.0,
                "offramp_blocked_flow_total": 0.0,
            }

        with patch("src.simulation.coupling.compute_ramp_release_flows", side_effect=fake_compute_release):
            with patch("src.simulation.coupling.freeway_substep", side_effect=fake_freeway_substep):
                result = run_coupled_interval(state, control, demand, cfg)

        self.assertTrue(seen_release)
        self.assertTrue(all(value == 0.0 for value in seen_release[0].values()))
        self.assertGreater(result.diagnostics["ramp_metering_release_shortfall_veh"], 0.0)

    def test_offramp_storage_limits_freeway_boundary_flow(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "simulation": {"T_total": 360.0},
                "network": {
                    "urban_link_storage_veh": {
                        "OR_D_W_storage": 0.0,
                        "OR_F_W_storage": 0.0,
                        "OR_D_E_storage": 0.0,
                        "OR_F_E_storage": 0.0,
                    }
                },
            },
        )
        sim = MixedTrafficSimulator(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).at(0.0)
        log = sim.step(ControlAction.fixed(cfg), demand, 0)
        self.assertGreater(log.diagnostics["offramp_storage_binding"], 0.0)
        self.assertGreater(log.diagnostics["offramp_blocked_flow_total"], 0.0)

    def test_stackelberg_prediction_uses_coupling_module(self):
        cfg = short_config()
        controller = StackelbergMPCController(cfg)
        state = TrafficState.initial(cfg)
        control = ControlAction.fixed(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).horizon(0.0, 1)
        calls = []

        def fake_coupled_step(*args):
            calls.append(args)
            return CoupledStepResult(freeway_ttt=1.25, urban_ttt=2.75)

        with patch("src.simulation.coupling.run_coupled_interval", side_effect=fake_coupled_step):
            states, total_ttt = controller._predict(state, control, demand)

        self.assertEqual(len(calls), 1)
        self.assertAlmostEqual(total_ttt, 4.0)
        self.assertAlmostEqual(states[0].time_sec, cfg.simulation.control_interval)

    def test_freeway_follower_prediction_preserves_urban_control_context(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "simulation": {"T_total": 360.0},
                "mpc": {"horizon_steps": 1},
                "freeway_follower": {"vsl_set": [100], "max_vsl_step": 0.0},
            },
        )
        state = TrafficState.initial(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).horizon(0.0, 1)
        previous = ControlAction.fixed(cfg)
        previous.green_times["A_p1"] = cfg.network.green_min
        previous.green_times["A_p2"] = cfg.network.effective_green_total - cfg.network.green_min
        seen_green = []

        def fake_lightweight_transition(*args):
            state_arg = args[-3]
            control = args[-2]
            seen_green.append(dict(control.green_times))
            return (
                state_arg.copy(),
                1.0,
                {"total_metering_error": 0.0, "mean_ramp_receiving_factor": 1.0},
            )

        with patch(
            "src.controllers.freeway_follower.FreewayFollower._lightweight_transition",
            side_effect=fake_lightweight_transition,
        ):
            result = FreewayFollower(cfg).solve(state, LeaderAction(0.0, 1200.0), demand, previous)

        self.assertEqual(result.infeasibility["freeway_follower_coupled_prediction"], 0.0)
        self.assertEqual(result.infeasibility["freeway_follower_lightweight_prediction"], 1.0)
        self.assertTrue(seen_green)
        self.assertEqual(seen_green[0]["A_p1"], previous.green_times["A_p1"])

    def test_urban_follower_uses_freeway_response_pressure(self):
        cfg = short_config()
        demand = DemandProfile(cfg, ScenarioConfig("test")).at(0.0)
        state = TrafficState.initial(cfg)
        follower = UrbanFollower(cfg)
        leader = LeaderAction(0.0, 1200.0)
        previous = ControlAction.fixed(cfg)
        no_response = follower.solve(state.copy(), leader, demand, None, previous)
        freeway_response = FreewayFollowerResult(
            ramp_metering={},
            vsl={},
            objective_value=0.0,
            infeasibility={
                "metering_tracking_residual": 1500.0,
                "ramp_projection_first_step_capacity": 1500.0,
                "ramp_queue_overflow": cfg.network.ramp_queue_max_veh,
                "density_excess": cfg.network.rho_crit,
                "min_ramp_receiving_factor": 0.2,
            },
        )
        with_response = follower.solve(state.copy(), leader, demand, freeway_response, previous)
        outbound = [
            movement for movement, spec in cfg.network.urban_movements.items()
            if spec.get("kind") == "off_ramp"
        ]
        no_out = sum(
            min(no_response.inflow_outflow_allocation.get(movement, 0.0), cfg.network.movement_capacity_veh_h)
            * no_response.green_times[cfg.network.urban_movements[movement]["phase"]]
            / cfg.network.cycle_length
            for movement in outbound
        )
        yes_out = sum(
            min(with_response.inflow_outflow_allocation.get(movement, 0.0), cfg.network.movement_capacity_veh_h)
            * with_response.green_times[cfg.network.urban_movements[movement]["phase"]]
            / cfg.network.cycle_length
            for movement in outbound
        )
        self.assertEqual(with_response.metrics["freeway_response_used"], 1.0)
        self.assertGreater(with_response.metrics["freeway_total_pressure"], 0.0)
        self.assertGreaterEqual(yes_out, no_out)


if __name__ == "__main__":
    unittest.main()
