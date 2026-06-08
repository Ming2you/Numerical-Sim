import unittest

from src.controllers.freeway_follower import FreewayFollower
from src.controllers.leader import LeaderAction
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState
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


if __name__ == "__main__":
    unittest.main()
