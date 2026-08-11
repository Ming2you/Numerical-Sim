# N8-1 eps_J_endpoint 하네스 검사 - 두 잡음 척도 분리, 산출 스키마 동결, 실 endpoint 결정론
"""계획 N8-1 의 `eps_J_endpoint` 측정 하네스가 지켜야 할 것을 고정한다.

핵심은 **척도 분리**다. N5 의 `eps_J_vissim`(VISSIM 런간 분산, 하한 `1e-6 veh·h`)을
endpoint 자리에 넣으면 `eps_g` 가 과대해져 `|intercept| <= median(eps_g)` 가 느슨해진다.
그래서 표본 출처를 받으면 `plant_endpoint_repeat` 이 아닌 것은 **거부**해야 한다
(`VISSIM/scripts/build_parent_run_spec.py:113` 의 `eps_j_endpoint` 와 같은 규약).
"""
import math
import unittest

from src.analysis import endpoint_noise as en
from src.controllers.rollout_endpoint import LeverMove
from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState


def _sample(objectives, **kw):
    kw.setdefault("source", en.ENDPOINT_SOURCE)
    kw.setdefault("state_id", "unit")
    kw.setdefault("state_source", en.SYNTHETIC_STATE_SOURCE)
    kw.setdefault("require_full_count", False)
    return en.EndpointNoiseResult(objectives=tuple(objectives), **kw)


class SourceGateTests(unittest.TestCase):
    """VISSIM 표본이 endpoint 자리에 들어오면 fail-closed 로 막힌다."""

    def test_eps_j_endpoint_rejects_vissim_source(self):
        with self.assertRaises(en.EndpointNoiseError) as ctx:
            en.eps_j_endpoint([100.0, 100.5], source=en.VISSIM_SOURCE)
        self.assertIn(en.ENDPOINT_SOURCE, str(ctx.exception))

    def test_eps_j_endpoint_rejects_unknown_source(self):
        with self.assertRaises(en.EndpointNoiseError):
            en.eps_j_endpoint([100.0, 100.5], source="whatever")

    def test_result_rejects_vissim_source_at_construction(self):
        with self.assertRaises(en.EndpointNoiseError):
            _sample([100.0, 100.0], source=en.VISSIM_SOURCE)

    def test_source_constants_match_the_spec_builder(self):
        # VISSIM/scripts/build_parent_run_spec.py:50-51 과 문자열이 같아야 두 저장소가 같은 게이트를 쓴다.
        self.assertEqual(en.ENDPOINT_SOURCE, "plant_endpoint_repeat")
        self.assertEqual(en.VISSIM_SOURCE, "vissim_base_replay")


class EpsJFormulaTests(unittest.TestCase):
    """eps_J_endpoint = max(q99(|J_r - J_1|), 1e-9 * max(|J_1|, 1))."""

    def test_identical_repeats_fall_back_to_relative_floor(self):
        eps = en.eps_j_endpoint([100.0] * 20, source=en.ENDPOINT_SOURCE)
        self.assertAlmostEqual(eps, 1.0e-9 * 100.0, places=18)

    def test_relative_floor_never_drops_below_one(self):
        eps = en.eps_j_endpoint([0.25] * 20, source=en.ENDPOINT_SOURCE)
        self.assertAlmostEqual(eps, 1.0e-9, places=18)

    def test_spread_above_floor_uses_q99_deviation(self):
        vals = [100.0] * 19 + [100.5]
        eps = en.eps_j_endpoint(vals, source=en.ENDPOINT_SOURCE)
        self.assertAlmostEqual(eps, 0.5, places=12)

    def test_deviations_are_measured_against_the_first_repeat(self):
        # 계획은 max-min 이 아니라 |J_r - J_1| 을 쓴다. J_1 이 한쪽 끝이 아니면 값이 갈린다.
        vals = [100.0] + [100.4] * 18 + [99.8]
        eps = en.eps_j_endpoint(vals, source=en.ENDPOINT_SOURCE)
        self.assertAlmostEqual(eps, 0.4, places=12)

    def test_requires_at_least_two_samples(self):
        with self.assertRaises(en.EndpointNoiseError):
            en.eps_j_endpoint([100.0], source=en.ENDPOINT_SOURCE)

    def test_require_full_count_enforces_twenty_repeats(self):
        with self.assertRaises(en.EndpointNoiseError):
            en.eps_j_endpoint([100.0] * 19, source=en.ENDPOINT_SOURCE, require_full_count=True)
        self.assertGreater(
            en.eps_j_endpoint([100.0] * 20, source=en.ENDPOINT_SOURCE, require_full_count=True),
            0.0,
        )

    def test_non_finite_objective_is_rejected(self):
        # abort 된 rollout 은 objective 가 inf 다. inf 로 잡음을 재면 값이 의미를 잃는다.
        with self.assertRaises(en.EndpointNoiseError):
            en.eps_j_endpoint([100.0, float("inf")], source=en.ENDPOINT_SOURCE)
        with self.assertRaises(en.EndpointNoiseError):
            en.eps_j_endpoint([100.0, float("nan")], source=en.ENDPOINT_SOURCE)

    def test_nearest_rank_quantile_is_deterministic(self):
        vals = [0.0, 1.0, 2.0, 3.0, 4.0]
        self.assertEqual(en.nearest_rank_quantile(vals, 0.99), 4.0)
        self.assertEqual(en.nearest_rank_quantile(vals, 0.0), 0.0)
        self.assertEqual(en.nearest_rank_quantile(vals, 0.5), 2.0)
        self.assertEqual(en.nearest_rank_quantile([7.0], 0.99), 7.0)


class ResultSchemaTests(unittest.TestCase):
    """산출 스키마를 동결한다. 키가 바뀌면 하류 판정이 조용히 다른 값을 읽는다."""

    EXPECTED_KEYS = {
        "schema_version",
        "source",
        "state_id",
        "state_source",
        "repeats",
        "full_count",
        "objectives",
        "j1",
        "max_abs_deviation",
        "q99_abs_deviation",
        "relative_floor",
        "eps_j_endpoint",
        "deterministic",
    }

    def test_to_dict_keys_are_frozen(self):
        self.assertEqual(set(_sample([100.0] * 20).to_dict()), self.EXPECTED_KEYS)

    def test_derived_fields_on_a_deterministic_sample(self):
        r = _sample([100.0] * 20)
        self.assertEqual(r.repeats, 20)
        self.assertTrue(r.full_count)
        self.assertTrue(r.deterministic)
        self.assertEqual(r.max_abs_deviation, 0.0)
        self.assertEqual(r.q99_abs_deviation, 0.0)
        self.assertAlmostEqual(r.relative_floor, 1.0e-7, places=18)
        self.assertAlmostEqual(r.eps_j_endpoint, 1.0e-7, places=18)

    def test_short_sample_is_flagged_not_full_count(self):
        r = _sample([100.0] * 5)
        self.assertFalse(r.full_count)
        self.assertEqual(r.repeats, 5)

    def test_state_source_must_be_recorded(self):
        # 합성 상태 측정을 실 qualification 측정과 구분할 수 없으면 나중에 되짚을 수 없다.
        with self.assertRaises(en.EndpointNoiseError):
            _sample([100.0] * 20, state_source="")

    def test_non_deterministic_sample_is_flagged(self):
        r = _sample([100.0] * 19 + [100.5])
        self.assertFalse(r.deterministic)


class EpsGTests(unittest.TestCase):
    """eps_g = 2 * eps_J_endpoint / realized_span. 측정 불가면 NOT_EVALUATED 로 남긴다."""

    def test_eps_g_formula(self):
        noise = _sample([100.0] * 20)
        out = en.eps_g_from_endpoint_noise(noise, realized_span=6.0, coordinate="A_p1")
        self.assertEqual(out.status, en.STATUS_OK)
        self.assertEqual(out.coordinate, "A_p1")
        self.assertAlmostEqual(out.eps_g, 2.0 * 1.0e-7 / 6.0, places=18)
        self.assertEqual(out.realized_span, 6.0)

    def test_eps_g_not_evaluated_without_realized_span(self):
        out = en.eps_g_from_endpoint_noise(_sample([100.0] * 20), realized_span=None)
        self.assertEqual(out.status, en.STATUS_NOT_EVALUATED)
        self.assertIsNone(out.eps_g)
        self.assertTrue(out.reason)

    def test_eps_g_not_evaluated_for_non_positive_or_non_finite_span(self):
        for span in (0.0, -3.0, float("inf"), float("nan")):
            out = en.eps_g_from_endpoint_noise(_sample([100.0] * 20), realized_span=span)
            self.assertEqual(out.status, en.STATUS_NOT_EVALUATED, span)
            self.assertIsNone(out.eps_g)

    def test_eps_g_refuses_a_bare_number(self):
        # 검증된 EndpointNoiseResult 를 통해서만 환산된다 - 맨 float 은 출처를 증명하지 못한다.
        with self.assertRaises(en.EndpointNoiseError):
            en.eps_g_from_endpoint_noise(1.0e-7, realized_span=6.0)

    def test_eps_g_to_dict_keys_are_frozen(self):
        out = en.eps_g_from_endpoint_noise(_sample([100.0] * 20), realized_span=6.0)
        self.assertEqual(
            set(out.to_dict()),
            {
                "schema_version",
                "status",
                "reason",
                "coordinate",
                "realized_span",
                "eps_j_endpoint",
                "eps_g",
            },
        )


def _fixture(horizon_steps: int = 1):
    cfg = ExperimentConfig.from_file(
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
    controller = StackelbergWuMeteredController(cfg)
    profile = DemandProfile(
        cfg, ScenarioConfig("peak_demand", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0)
    )
    forecast = profile.horizon(0.0, horizon_steps + 2)
    return cfg, controller, TrafficState.initial(cfg), ControlAction.fixed(cfg), forecast


class MeasureOnRealEndpointTests(unittest.TestCase):
    """실 endpoint 를 20회 돌린다. 지금 관측은 '완전 결정론' 이고 그것이 기록돼야 한다."""

    def test_twenty_repeats_of_the_real_endpoint_are_bit_identical(self):
        cfg, controller, state, previous, forecast = _fixture()
        spec = controller._rollout_spec(score_mode="price")
        schedule = (LeverMove("green", sorted(cfg.network.signals)[0], 40.0),)
        try:
            r = en.measure_endpoint_noise(
                state, previous, forecast, schedule, spec, state_id="peak-h1"
            )
        finally:
            controller.close()
        self.assertEqual(r.repeats, 20)
        self.assertTrue(r.full_count)
        self.assertTrue(r.deterministic, r.objectives)
        self.assertEqual(r.max_abs_deviation, 0.0)
        self.assertTrue(math.isfinite(r.j1))
        # 잡음 표본이 0 이므로 eps 는 전적으로 상대 하한이 정한다.
        self.assertAlmostEqual(r.eps_j_endpoint, 1.0e-9 * max(abs(r.j1), 1.0), places=18)
        self.assertEqual(r.source, en.ENDPOINT_SOURCE)

    def test_measure_requires_twenty_repeats_by_default(self):
        cfg, controller, state, previous, forecast = _fixture()
        spec = controller._rollout_spec(score_mode="price")
        try:
            with self.assertRaises(en.EndpointNoiseError):
                en.measure_endpoint_noise(state, previous, forecast, (), spec, repeats=5)
        finally:
            controller.close()

    def test_measure_does_not_mutate_its_inputs(self):
        cfg, controller, state, previous, forecast = _fixture()
        spec = controller._rollout_spec(score_mode="price")
        before_green = dict(previous.green_times)
        before_time = float(state.time_sec)
        try:
            en.measure_endpoint_noise(
                state, previous, forecast, (), spec, repeats=2, require_full_count=False
            )
        finally:
            controller.close()
        self.assertEqual(before_green, previous.green_times)
        self.assertEqual(before_time, float(state.time_sec))


if __name__ == "__main__":
    unittest.main()
