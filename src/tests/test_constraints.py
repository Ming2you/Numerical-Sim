import unittest
from unittest.mock import patch

from src.controllers.freeway_follower import FreewayFollower, FreewayFollowerResult
from src.controllers.leader import LeaderAction
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.controllers.urban_follower import UrbanFollower
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
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
            if spec.get("kind") != "on_ramp"
        ]
        self.assertTrue(all(movement in control.inflow_outflow_allocation for movement in movement_keys))

    def test_offset_range(self):
        cfg = short_config()
        demand = DemandProfile(cfg, ScenarioConfig("test")).horizon(0.0, 2)
        control = StackelbergMPCController(cfg).decide(TrafficState.initial(cfg), demand)
        for value in control.offsets.values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLess(value, cfg.network.cycle_length)

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
        self.assertTrue(error <= cfg.freeway_follower.eps_F or result.infeasibility["metering_residual"] > 0.0)

    def test_ramp_metering_respects_downstream_receiving_capacity(self):
        cfg = short_config()
        state = TrafficState.initial(cfg)
        for link in cfg.network.freeway_links:
            merge_idx = len(state.freeway_density[link]) // 2
            state.freeway_density[link][merge_idx] = cfg.network.rho_max
        demand = DemandProfile(cfg, ScenarioConfig("test", ramp_scale=3.0)).at(0.0)
        result = FreewayFollower(cfg).solve(state, LeaderAction(0.0, 3000.0), demand)
        self.assertTrue(all(value <= 1.0e-9 for value in result.ramp_metering.values()))
        self.assertGreater(result.infeasibility["metering_target_infeasible"], 0.0)
        self.assertGreater(result.infeasibility["metering_tracking_residual"], cfg.freeway_follower.eps_F)

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

    def test_boundary_queue_balance_safe_division(self):
        from src.models.urban_queue_model import safe_balance_index

        self.assertEqual(safe_balance_index([0.0, 0.0]), 0.0)

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
        state.ramp_queue["R1"] = 30.0
        state.urban_movement_queue["R1_onramp"] = 70.0
        sync_onramp_queues_from_freeway(state, cfg)
        self.assertAlmostEqual(state.ramp_queue["R1"], 30.0)
        self.assertAlmostEqual(state.urban_movement_queue["R1_onramp"], 70.0)
        sync_onramp_queues_to_freeway(state, cfg)
        self.assertAlmostEqual(state.ramp_queue["R1"], 30.0)
        self.assertAlmostEqual(state.urban_movement_queue["R1_onramp"], 70.0)

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
            for movement in cfg.network.on_ramp_to_movement.values():
                state.urban_movement_queue[movement] = 40.0

        low_control = ControlAction.fixed(cfg)
        high_control = ControlAction.fixed(cfg)
        low_control.green_times["A_p2"] = cfg.network.green_min
        high_control.green_times["A_p2"] = cfg.network.green_max
        low_control.inflow_outflow_allocation["R1_onramp"] = cfg.network.movement_capacity_veh_h
        high_control.inflow_outflow_allocation["R1_onramp"] = cfg.network.movement_capacity_veh_h
        ramp_release = {ramp: 0.0 for ramp in cfg.network.ramps}

        _, low_diag = urban_substep(low, low_control, demand, cfg, urban_step_index=0, ramp_release_veh_h=ramp_release)
        _, high_diag = urban_substep(high, high_control, demand, cfg, urban_step_index=0, ramp_release_veh_h=ramp_release)

        self.assertGreater(high.ramp_queue["R1"], low.ramp_queue["R1"])
        self.assertGreater(high_diag["onramp_green_releases_veh"], low_diag["onramp_green_releases_veh"])

    def test_coupling_passes_actual_ramp_release_to_freeway_step(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {"simulation": {"T_total": 10.0, "T_f": 10.0, "T_u": 5.0, "control_interval": 10.0}},
        )
        state = TrafficState.initial(cfg)
        for ramp in cfg.network.ramps:
            state.ramp_queue[ramp] = 0.0
            state.urban_movement_queue[cfg.network.on_ramp_to_movement[ramp]] = 0.0
        control = ControlAction.fixed(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test", ramp_scale=0.0)).at(0.0)
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
                        "A_out_D": 220.0,
                        "C_out_F": 220.0,
                        "A_R1": 180.0,
                        "C_R2": 180.0,
                        "D_R3": 180.0,
                        "F_R4": 180.0,
                        "OR_W_D": 0.0,
                        "OR_E_F": 0.0,
                        "D_out_D": 220.0,
                        "F_out_F": 220.0,
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
        no_out = sum(no_response.inflow_outflow_allocation.get(movement, 0.0) for movement in outbound)
        yes_out = sum(with_response.inflow_outflow_allocation.get(movement, 0.0) for movement in outbound)
        self.assertEqual(with_response.metrics["freeway_response_used"], 1.0)
        self.assertGreater(with_response.metrics["freeway_total_pressure"], 0.0)
        self.assertGreaterEqual(yes_out, no_out)


if __name__ == "__main__":
    unittest.main()
