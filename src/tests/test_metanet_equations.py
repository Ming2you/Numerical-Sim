import math
import unittest

from src.models.demand import DemandStep
from src.models.metanet import (
    desired_speed_kmh,
    effective_desired_speed_kmh,
    freeway_step,
    metanet_speed_update_kmh,
    segment_flow_veh_h,
)
from src.models.state import ControlAction, ExperimentConfig, TrafficState


class MetanetEquationTests(unittest.TestCase):
    def test_segment_flow_matches_spec_equation(self):
        self.assertAlmostEqual(segment_flow_veh_h(20.0, 80.0, 2.0), 3200.0)

    def test_desired_speed_matches_spec_equation(self):
        rho = 30.0
        v_free = 100.0
        rho_crit = 33.5
        a = 1.867
        expected = v_free * math.exp(-(1.0 / a) * ((rho / rho_crit) ** a))
        self.assertAlmostEqual(desired_speed_kmh(rho, v_free, rho_crit, a), expected)

    def test_vsl_effect_uses_alpha_compliance(self):
        rho = 10.0
        no_vsl = desired_speed_kmh(rho, 100.0, 33.5, 1.867)
        self.assertGreater(no_vsl, 90.0)
        self.assertAlmostEqual(
            effective_desired_speed_kmh(rho, 100.0, 33.5, 90.0, alpha_vsl=0.1),
            min(no_vsl, 99.0),
        )
        self.assertAlmostEqual(
            effective_desired_speed_kmh(rho, 100.0, 33.5, 90.0, vsl_active=False),
            no_vsl,
        )

    def test_speed_update_matches_relaxation_convection_anticipation_sum(self):
        speed = 80.0
        upstream_speed = 90.0
        rho = 25.0
        downstream_rho = 30.0
        v_eff = 85.0
        dt_h = 10.0 / 3600.0
        length_km = 0.5
        tau_h = 0.005
        nu = 65.0
        kappa = 40.0
        v_min = 5.0
        expected = (
            speed
            + dt_h / tau_h * (v_eff - speed)
            + dt_h / length_km * speed * (upstream_speed - speed)
            - nu * dt_h / (tau_h * length_km) * (downstream_rho - rho) / (rho + kappa)
        )
        self.assertAlmostEqual(
            metanet_speed_update_kmh(
                speed,
                upstream_speed,
                rho,
                downstream_rho,
                v_eff,
                dt_h,
                length_km,
                tau_h,
                nu,
                kappa,
                v_min,
            ),
            max(v_min, expected),
        )

    def test_config_exposes_time_ratios_and_units(self):
        cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.assertAlmostEqual(cfg.simulation.T_f_h, cfg.simulation.T_f / 3600.0)
        self.assertAlmostEqual(cfg.simulation.T_u_h, cfg.simulation.T_u / 3600.0)
        self.assertAlmostEqual(cfg.simulation.T_c_h, cfg.simulation.control_interval / 3600.0)
        self.assertEqual(cfg.simulation.K_fu, 2)
        self.assertEqual(cfg.simulation.K_cf, 18)
        self.assertEqual(cfg.simulation.K_cu, 36)
        self.assertEqual(cfg.leader.N_P_star_unit, "veh")
        self.assertEqual(cfg.leader.N_UF_star_unit, "veh_per_hour")
        self.assertGreaterEqual(cfg.freeway_follower.horizon_beam_width, 1)
        self.assertGreaterEqual(cfg.freeway_follower.horizon_ramp_candidate_limit, 1)
        self.assertGreaterEqual(cfg.freeway_follower.horizon_vsl_candidate_limit_per_link, 1)
        self.assertIn("R1", cfg.network.on_ramp_to_movement)
        self.assertIn("OR_W", cfg.network.off_ramps)
        self.assertIn("OR_W_D", cfg.network.urban_link_storage_veh)

    def test_config_rejects_non_integer_time_ratios(self):
        with self.assertRaises(ValueError):
            ExperimentConfig.from_file("src/config/default.yaml", {"simulation": {"T_f": 7.0}})

    def test_config_rejects_unknown_nuf_unit(self):
        with self.assertRaises(ValueError):
            ExperimentConfig.from_file("src/config/default.yaml", {"leader": {"N_UF_star_unit": "vehicles"}})

    def test_config_rejects_unknown_np_unit(self):
        with self.assertRaises(ValueError):
            ExperimentConfig.from_file("src/config/default.yaml", {"leader": {"N_P_star_unit": "veh_per_hour"}})

    def test_traffic_state_stores_freeway_flow(self):
        cfg = ExperimentConfig.from_file("src/config/default.yaml")
        state = TrafficState.initial(cfg)
        for link in cfg.network.freeway_links:
            for rho, speed, flow in zip(
                state.freeway_density[link],
                state.freeway_speed[link],
                state.freeway_flow[link],
            ):
                self.assertAlmostEqual(
                    flow,
                    segment_flow_veh_h(rho, speed, cfg.network.freeway_lanes),
                )

    def test_freeway_step_density_uses_metanet_conservation(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "simulation": {"T_total": 10.0, "T_f": 10.0, "T_u": 5.0, "control_interval": 10.0},
                "network": {"freeway_segments_per_link": 1},
            },
        )
        state = TrafficState.initial(cfg)
        for link in cfg.network.freeway_links:
            state.freeway_density[link] = [20.0]
            state.freeway_speed[link] = [50.0]
        demand = DemandStep(
            freeway_mainline={link: 1000.0 for link in cfg.network.freeway_links},
            urban_boundary={link: 0.0 for link in cfg.network.movement_links},
            ramp_arrival={ramp: 0.0 for ramp in cfg.network.ramps},
        )
        control = ControlAction.fixed(cfg)
        control.ramp_metering = {ramp: 0.0 for ramp in cfg.network.ramps}
        freeway_step(state, control, demand, cfg)
        expected = 20.0 + cfg.simulation.T_f_h / (
            cfg.network.freeway_segment_length_km * cfg.network.freeway_lanes
        ) * (1000.0 - segment_flow_veh_h(20.0, 50.0, cfg.network.freeway_lanes))
        self.assertAlmostEqual(state.freeway_density["FW_W"][0], expected)
        self.assertAlmostEqual(
            state.freeway_flow["FW_W"][0],
            segment_flow_veh_h(
                state.freeway_density["FW_W"][0],
                state.freeway_speed["FW_W"][0],
                cfg.network.freeway_lanes,
            ),
        )

    def test_freeway_step_adds_full_ramp_flow_to_merge_segment(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {"simulation": {"T_total": 10.0, "T_f": 10.0, "T_u": 5.0, "control_interval": 10.0}},
        )
        state = TrafficState.initial(cfg)
        for link in cfg.network.freeway_links:
            state.freeway_density[link] = [10.0, 10.0, 10.0]
            state.freeway_speed[link] = [0.0, 0.0, 0.0]
        demand = DemandStep(
            freeway_mainline={link: 0.0 for link in cfg.network.freeway_links},
            urban_boundary={link: 0.0 for link in cfg.network.movement_links},
            ramp_arrival={ramp: (900.0 if ramp == "R1" else 0.0) for ramp in cfg.network.ramps},
        )
        control = ControlAction.fixed(cfg)
        control.ramp_metering = {ramp: (900.0 if ramp == "R1" else 0.0) for ramp in cfg.network.ramps}
        control.N_UF_star = 900.0
        freeway_step(state, control, demand, cfg)
        expected_merge_density = 10.0 + cfg.simulation.T_f_h / (
            cfg.network.freeway_segment_length_km * cfg.network.freeway_lanes
        ) * 900.0
        self.assertAlmostEqual(state.freeway_density["FW_W"][1], expected_merge_density)
        self.assertAlmostEqual(state.freeway_density["FW_W"][0], 10.0)
        self.assertAlmostEqual(state.freeway_density["FW_W"][2], 10.0)


if __name__ == "__main__":
    unittest.main()
