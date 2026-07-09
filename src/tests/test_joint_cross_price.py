# JOINT bilinear cross 가격: 휴면=OFF 상태 기본값, 새 probe 일관성, vsl_override 고정,
# 컨트롤러 refresh가 non-ramp 신호·ramp에 cross 가격을 하달하는지 검증
import unittest

from src.controllers.f1_wu_faithful_follower import F1WuFaithfulFollower
from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState


def _build_cfg():
    return ExperimentConfig.from_file(
        "src/config/default.yaml",
        {
            "simulation": {"T_total": 360.0},
            "mpc": {
                "horizon_steps": 1,
                "relaxed_quantized_controls": True,
                "grid_parallel_backend": "serial",
                "leader_global_refresh_sec": 1.0e9,
            },
            "freeway_follower": {
                "freeway_prediction_horizon_steps": 1,
                "vsl_sequence_search": False,
            },
        },
    )


def _demand(cfg):
    return DemandProfile(
        cfg,
        ScenarioConfig("probe", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0),
    ).horizon(0.0, 1)


class TestJointCrossPrice(unittest.TestCase):
    def test_defaults_dormant(self):
        cfg = _build_cfg()
        f = WuFaithfulFollower(cfg)
        self.assertIsNone(f.green_offset_cross_price)
        self.assertIsNone(f.vsl_meter_cross_price)
        self.assertFalse(f.joint_green_offset_enabled)

    def test_green_offset_probe_matches_offset_probe(self):
        # (p1=control green, offset) 쌍의 own_TTS는 같은 green에서의 offset probe와 동일 경로.
        cfg = _build_cfg()
        f = WuFaithfulFollower(cfg)
        state = TrafficState.initial(cfg)
        ctrl = ControlAction.fixed(cfg)
        dem = _demand(cfg)[0]
        net = cfg.network
        sig = [s for s in net.signals if not f._local_models[s].has_ramps][0]
        p1 = float(ctrl.green_times.get(f"{sig}_p1", net.effective_green_total / 2.0))
        offs = [0.0, net.cycle_length / 8.0]
        via_offset = f.local_offset_costs({sig: offs}, state, ctrl, dem)[sig]
        via_pairs = f.local_green_offset_costs(
            {sig: [(p1, o) for o in offs]}, state, ctrl, dem,
        )[sig]
        for a, b in zip(via_offset, via_pairs):
            self.assertAlmostEqual(a, b, places=6)

    def test_vsl_override_returns_finite_costs(self):
        # vsl_override 경로(고정 (meter,vsl) own-TTS)가 유한값을 낸다(F1 계열, ALLPRICE base).
        cfg = _build_cfg()
        f = F1WuFaithfulFollower(cfg)
        state = TrafficState.initial(cfg)
        ctrl = ControlAction.fixed(cfg)
        dem = _demand(cfg)[0]
        net = cfg.network
        ramp = net.ramps[0]
        cap = float(net.ramp_capacity_veh_h[ramp])
        vlo = min(cfg.freeway_follower.vsl_set)
        vhi = max(cfg.freeway_follower.vsl_set)
        costs = f.local_vsl_meter_costs(
            {ramp: [(cap, vhi), (0.5 * cap, vlo)]}, state, ctrl, dem,
        )[ramp]
        self.assertEqual(len(costs), 2)
        for c in costs:
            self.assertTrue(c == c and c not in (float("inf"), -float("inf")))
            self.assertGreaterEqual(c, 0.0)

    def test_controller_refresh_hands_cross_prices(self):
        cfg = _build_cfg()
        controller = StackelbergWuMeteredController(cfg)
        controller.signal_price_enabled = False
        controller.green_offset_cross_price_enabled = True
        controller.vsl_meter_cross_price_enabled = True
        state = TrafficState.initial(cfg)
        state.time_sec = float(cfg.simulation.control_interval)
        controller._maybe_refresh_signal_prices(
            state, _demand(cfg), ControlAction.fixed(cfg),
        )
        f = controller.nash_solver
        net = cfg.network
        non_ramp = {s for s in net.signals if not f._local_models[s].has_ramps}
        self.assertIsNotNone(f.green_offset_cross_price)
        self.assertEqual(set(f.green_offset_cross_price), non_ramp)
        self.assertIsNotNone(f.vsl_meter_cross_price)
        self.assertEqual(set(f.vsl_meter_cross_price), set(net.ramps))
        for v in list(f.green_offset_cross_price.values()) + list(f.vsl_meter_cross_price.values()):
            self.assertTrue(v == v and v not in (float("inf"), -float("inf")))


if __name__ == "__main__":
    unittest.main()
