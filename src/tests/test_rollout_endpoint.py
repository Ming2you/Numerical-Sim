# N7 production rollout endpoint - 순수성/채널 커버리지/우회 호출 0/통합(one-step·H=3) 검증
import unittest

from src.controllers import rollout_endpoint as rep
from src.controllers.rollout_endpoint import (
    LeverMove,
    ObjectiveSpec,
    apply_action_schedule,
    evaluate_price_point,
)
from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState


def _cfg(horizon_steps: int = 1):
    return ExperimentConfig.from_file(
        "src/config/default.yaml",
        {
            "simulation": {"T_total": 360.0},
            "mpc": {
                "horizon_steps": horizon_steps,
                "relaxed_quantized_controls": True,
                "grid_parallel_backend": "serial",
                "leader_global_refresh_sec": 1.0e9,
                "leader_candidate_count": 2,
                "max_nash_iter": 2,
            },
            "freeway_follower": {
                "freeway_prediction_horizon_steps": 1,
                "vsl_sequence_search": False,
                "horizon_beam_width": 1,
                "horizon_ramp_candidate_limit": 1,
                "horizon_vsl_candidate_limit_per_link": 1,
            },
        },
    )


def _fixture(horizon_steps: int = 1):
    cfg = _cfg(horizon_steps)
    controller = StackelbergWuMeteredController(cfg)
    profile = DemandProfile(
        cfg, ScenarioConfig("peak_demand", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0)
    )
    forecast = profile.horizon(0.0, horizon_steps + 2)
    state = TrafficState.initial(cfg)
    previous = ControlAction.fixed(cfg)
    return cfg, controller, state, previous, forecast


class EndpointPurityTests(unittest.TestCase):
    def test_same_inputs_give_same_output_and_do_not_mutate_arguments(self):
        cfg, controller, state, previous, forecast = _fixture()
        spec = controller._rollout_spec(score_mode="price")
        signal = sorted(cfg.network.signals)[0]
        schedule = (LeverMove("green", signal, 40.0),)
        before_green = dict(previous.green_times)
        before_time = float(state.time_sec)
        a = evaluate_price_point(state, previous, forecast, schedule, spec)
        b = evaluate_price_point(state, previous, forecast, schedule, spec)
        controller.close()
        self.assertEqual(a.objective, b.objective)
        self.assertEqual(a.ttt, b.ttt)
        self.assertEqual(before_green, previous.green_times)
        self.assertEqual(before_time, float(state.time_sec))

    def test_empty_schedule_holds_previous_control(self):
        cfg, controller, state, previous, forecast = _fixture()
        spec = controller._rollout_spec(score_mode="raw")
        control = apply_action_schedule(previous, (), spec)
        controller.close()
        self.assertEqual(dict(previous.green_times), dict(control.green_times))
        self.assertEqual(dict(previous.ramp_metering), dict(control.ramp_metering))
        self.assertEqual(dict(previous.vsl), dict(control.vsl))
        self.assertEqual(dict(previous.offsets), dict(control.offsets))


class ChannelCoverageTests(unittest.TestCase):
    def test_all_four_price_channels_are_expressible_in_one_schedule(self):
        cfg, controller, state, previous, forecast = _fixture()
        spec = controller._rollout_spec(score_mode="price")
        net = cfg.network
        signal = sorted(net.signals)[0]
        ramp = sorted(net.ramps)[0]
        link = sorted(net.freeway_links)[0]
        seg_key = f"{link}__seg0"
        total = float(net.effective_green_total)
        schedule = (
            LeverMove("green", signal, 40.0),
            LeverMove("meter", ramp, 900.0),
            LeverMove("vsl", seg_key, 70.0),
            LeverMove("offset", signal, 12.0),
        )
        control = apply_action_schedule(previous, schedule, spec)
        controller.close()
        self.assertAlmostEqual(control.green_times[f"{signal}_p1"], 40.0)
        self.assertAlmostEqual(control.green_times[f"{signal}_p2"], total - 40.0)
        self.assertAlmostEqual(control.ramp_metering[ramp], 900.0)
        self.assertAlmostEqual(control.vsl[seg_key], 70.0)
        self.assertLessEqual(control.vsl[link], 70.0)
        self.assertAlmostEqual(control.offsets[signal], 12.0)
        self.assertEqual(set(rep.LEVER_KINDS), {"green", "meter", "vsl", "offset"})


class BypassTests(unittest.TestCase):
    """우회 호출 0 - leader 층의 전역 plant rollout이 전부 endpoint 프레임 안에서 일어난다."""

    def _run_with_probe(self, horizon_steps):
        import src.simulation.coupling as coupling

        cfg, controller, state, previous, forecast = _fixture(horizon_steps)
        controller.signal_price_enabled = True
        controller.metering_price_enabled = True
        controller.vsl_price_enabled = True
        controller.offset_price_enabled = True
        original = coupling.run_coupled_interval
        counts = {"inside": 0, "outside": 0, "rollouts": 0}

        def probed(*args, **kwargs):
            if rep.endpoint_active():
                counts["inside"] += 1
            else:
                counts["outside"] += 1
            return original(*args, **kwargs)

        coupling.run_coupled_interval = probed
        before = rep.ENDPOINT_CALLS
        before_rollouts = rep.ROLLOUT_CALLS
        try:
            result = controller.decide_with_info(state.copy(), forecast, previous)
        finally:
            coupling.run_coupled_interval = original
            controller.close()
        counts["rollouts"] = rep.ROLLOUT_CALLS - before_rollouts
        return counts, rep.ENDPOINT_CALLS - before, result

    def test_one_step_decide_has_zero_bypass_rollouts(self):
        counts, endpoint_calls, result = self._run_with_probe(1)
        self.assertEqual(counts["outside"], 0)
        self.assertGreater(counts["inside"], 0)
        self.assertGreater(endpoint_calls, 0)
        self.assertEqual(endpoint_calls, counts["rollouts"])
        self.assertTrue(result.control.green_times)

    def test_h3_decide_has_zero_bypass_rollouts(self):
        counts, endpoint_calls, result = self._run_with_probe(3)
        self.assertEqual(counts["outside"], 0)
        self.assertGreater(counts["inside"], 0)
        self.assertGreater(endpoint_calls, 0)
        self.assertEqual(endpoint_calls, counts["rollouts"])
        self.assertTrue(result.control.ramp_metering)

    def test_one_candidate_scoring_is_exactly_one_endpoint_call(self):
        """후보 채점 1회 = endpoint 1회. leader base 가 자체 rollout 을 갖지 않음을 고정한다."""
        from src.controllers.nash_solver import NashResult

        cfg, controller, state, previous, forecast = _fixture(3)
        nash = controller.nash_solver.solve(state.copy(), None, forecast, previous)
        before = rep.ENDPOINT_CALLS
        controller._leader_evaluation_base(state.copy(), nash, forecast, previous=previous)
        calls = rep.ENDPOINT_CALLS - before
        controller.close()
        self.assertEqual(calls, 1)

    def test_endpoint_call_count_equals_evaluated_rollout_count(self):
        cfg, controller, state, previous, forecast = _fixture(1)
        controller.signal_price_enabled = True
        controller.metering_price_enabled = True
        before = rep.ENDPOINT_CALLS
        controller._maybe_refresh_signal_prices(state.copy(), forecast, previous)
        calls = rep.ENDPOINT_CALLS - before
        price_rollouts = int(controller._price_rollout_count)
        controller.close()
        self.assertGreater(price_rollouts, 0)
        self.assertEqual(calls, price_rollouts)


class ComponentTests(unittest.TestCase):
    def test_spec_flags_gate_objective_components(self):
        cfg, controller, state, previous, forecast = _fixture()
        raw = controller._rollout_spec(score_mode="raw")
        priced = controller._rollout_spec(score_mode="price", far_enabled=True)
        schedule = ()
        r_raw = evaluate_price_point(state, previous, forecast, schedule, raw)
        r_far = evaluate_price_point(state, previous, forecast, schedule, priced)
        controller.close()
        self.assertEqual(r_raw.ttt, r_far.ttt)
        self.assertEqual(r_raw.objective, r_raw.ttt)
        self.assertAlmostEqual(r_far.objective, r_far.ttt + r_far.far)

    def test_barrier_and_max_rho_are_reported_when_requested(self):
        cfg, controller, state, previous, forecast = _fixture()
        ramp = sorted(cfg.network.ramps)[0]
        link = cfg.network.ramp_to_freeway[ramp]
        spec = controller._rollout_spec(
            score_mode="price", barrier=True, barrier_weight=1.0,
            barrier_spillback_frac=0.2, max_rho_link=link,
        )
        result = evaluate_price_point(
            state, previous, forecast, (LeverMove("meter", ramp, 800.0),), spec,
        )
        controller.close()
        self.assertGreaterEqual(result.barrier, 0.0)
        self.assertGreater(result.max_rho, 0.0)


if __name__ == "__main__":
    unittest.main()
