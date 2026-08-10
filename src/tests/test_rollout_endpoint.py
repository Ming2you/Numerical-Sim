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


# ---------------------------------------------------------------------------
# N7 잔여 - leader 층 밖에 남아 있던 전역 rollout 5곳(우회 호출)도 endpoint 를 거친다.
# 참조 구현(`_ref_*`)은 리팩터 직전 루프를 그대로 옮긴 것이다. 리팩터가 수치를 바꾸면
# 이 대조에서 걸린다.
# ---------------------------------------------------------------------------
def _plain(horizon_steps: int = 1):
    """controller 생성 없이 cfg/state/previous/forecast 만 만드는 가벼운 fixture."""
    cfg = _cfg(horizon_steps)
    profile = DemandProfile(
        cfg, ScenarioConfig("peak_demand", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0)
    )
    forecast = profile.horizon(0.0, horizon_steps + 2)
    return cfg, TrafficState.initial(cfg), ControlAction.fixed(cfg), forecast


def _probe(fn):
    """fn 실행 중 run_coupled_interval 이 endpoint 프레임 밖에서 불린 횟수를 센다."""
    import src.simulation.coupling as coupling

    original = coupling.run_coupled_interval
    counts = {"inside": 0, "outside": 0}

    def probed(*args, **kwargs):
        counts["inside" if rep.endpoint_active() else "outside"] += 1
        return original(*args, **kwargs)

    coupling.run_coupled_interval = probed
    try:
        out = fn()
    finally:
        coupling.run_coupled_interval = original
    return counts, out


def _ref_replay(cfg, scenario, traces, start_step, n_intervals, target):
    """stage2_mechanism._replay 리팩터 직전 루프."""
    from src.analysis.stage2_mechanism import _neutral_control
    from src.simulation.coupling import run_coupled_interval

    profile = DemandProfile(cfg, scenario)
    state = traces[start_step].state_before.copy()
    total = urban = freeway = 0.0
    for offset in range(n_intervals):
        idx = start_step + offset
        if idx >= len(traces):
            break
        control = traces[idx].control
        if target is not None:
            control = _neutral_control(cfg, control, target)
        demand = profile.at(idx * cfg.simulation.control_interval)
        result = run_coupled_interval(state, control, demand, cfg)
        state.time_sec += cfg.simulation.control_interval
        total += result.freeway_ttt + result.urban_ttt
        urban += result.urban_ttt
        freeway += result.freeway_ttt
    return {"total": total, "urban": urban, "freeway": freeway}


def _ref_hold_rollout(cfg, state, control, forecast, depth, incumbent_obj=None):
    """control 을 hold 한 채 depth 스텝 전진하는 리팩터 직전 공통 루프.

    반환 (states, total_ttt, freeway_ttt, urban_ttt, early_terminated, terminal_state).
    incumbent_obj 가 주어지면 `total > incumbent + 1e-12` 에서 조기 절단한다.
    """
    from src.simulation.coupling import run_coupled_interval

    s = state.copy()
    states = []
    total = freeway = urban = 0.0
    early = False
    for demand in forecast[:depth]:
        result = run_coupled_interval(s, control, demand, cfg)
        total += float(result.urban_ttt + result.freeway_ttt)
        freeway += float(result.freeway_ttt)
        urban += float(result.urban_ttt)
        s.time_sec += cfg.simulation.control_interval
        states.append(s.copy())
        if incumbent_obj is not None and total > incumbent_obj + 1.0e-12:
            early = True
            break
    return states, total, freeway, urban, early, s


def _traces(cfg, n: int):
    from src.analysis.stage2_mechanism import IntervalTrace

    state = TrafficState.initial(cfg)
    out = []
    for k in range(n):
        control = ControlAction.fixed(cfg)
        control.ramp_metering = {r: 900.0 + 50.0 * k for r in cfg.network.ramps}
        out.append(
            IntervalTrace(
                step=k,
                time_sec=k * cfg.simulation.control_interval,
                state_before=state.copy(),
                control=control,
                diagnostics={},
                interval_ttt=0.0,
                urban_ttt=0.0,
                freeway_ttt=0.0,
            )
        )
    return out


class CallSiteBypassTests(unittest.TestCase):
    """우회 호출 0 - leader 층 밖 5곳도 endpoint 프레임 안에서만 plant 를 전진시킨다."""

    def test_stage2_replay_has_no_bypass(self):
        from src.analysis import stage2_mechanism as s2

        cfg, _state, _prev, _fc = _plain(1)
        scenario = ScenarioConfig("peak_demand", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0)
        traces = _traces(cfg, 2)
        counts, _out = _probe(lambda: s2._replay(cfg, scenario, traces, 0, 2, None))
        self.assertGreater(counts["inside"], 0)
        self.assertEqual(counts["outside"], 0)

    def test_centralized_predict_with_ttt_has_no_bypass(self):
        from src.controllers.centralized_mpc import CentralizedMPC

        cfg, state, previous, forecast = _plain(2)
        controller = CentralizedMPC(cfg, mode="proposed")
        counts, _out = _probe(
            lambda: controller._predict_with_ttt(state, previous, forecast)
        )
        self.assertGreater(counts["inside"], 0)
        self.assertEqual(counts["outside"], 0)

    def test_centralized_grid_candidate_has_no_bypass(self):
        from src.controllers.centralized_mpc import CentralizedMPC
        from src.controllers.structured_grid import GridControlCandidate

        cfg, state, previous, forecast = _plain(2)
        controller = CentralizedMPC(cfg, mode="proposed")
        candidate = GridControlCandidate(label="probe", control=previous.copy(), stage="coarse")
        counts, _out = _probe(
            lambda: controller._evaluate_grid_candidate(state, forecast, previous, candidate)
        )
        self.assertGreater(counts["inside"], 0)
        self.assertEqual(counts["outside"], 0)

    def test_distributed_grid_objective_has_no_bypass(self):
        from src.controllers.distributed_coordinator import DistributedCoordinator
        from src.controllers.structured_grid import GridControlCandidate

        cfg, state, previous, forecast = _plain(2)
        coordinator = DistributedCoordinator(cfg)
        candidate = GridControlCandidate(label="probe", control=previous.copy(), stage="coarse")
        counts, _out = _probe(
            lambda: coordinator._rollout_grid_objective(state.copy(), candidate, forecast, None)
        )
        self.assertGreater(counts["inside"], 0)
        self.assertEqual(counts["outside"], 0)

    def test_wu_distributed_leader_scoring_has_no_bypass(self):
        from src.controllers.wu_distributed import WuDistributedController

        cfg, state, previous, forecast = _plain(2)
        controller = WuDistributedController(cfg, leader_enabled=True)
        counts, _out = _probe(
            lambda: controller.decide_with_info(state.copy(), forecast, previous)
        )
        self.assertGreater(counts["inside"], 0)
        self.assertEqual(counts["outside"], 0)


class CallSiteEquivalenceTests(unittest.TestCase):
    """endpoint 경유 리팩터가 수치를 바꾸지 않았는지 참조 구현과 대조한다."""

    def test_stage2_replay_matches_reference(self):
        from src.analysis import stage2_mechanism as s2

        cfg, _state, _prev, _fc = _plain(1)
        scenario = ScenarioConfig("peak_demand", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0)
        for target in (None, "metering"):
            with self.subTest(target=target):
                got = s2._replay(cfg, scenario, _traces(cfg, 3), 0, 3, target)
                want = _ref_replay(cfg, scenario, _traces(cfg, 3), 0, 3, target)
                self.assertEqual(set(got), set(want))
                for key in want:
                    self.assertAlmostEqual(got[key], want[key], places=9)

    def test_centralized_predict_with_ttt_matches_reference(self):
        from src.controllers.centralized_mpc import CentralizedMPC
        from src.controllers.stackelberg_mpc import mfd_far_cost_to_go

        cfg, state, previous, forecast = _plain(2)
        controller = CentralizedMPC(cfg, mode="proposed")
        states, ttt = controller._predict_with_ttt(state, previous, forecast)
        ref_states, ref_total, _fw, _ur, _early, ref_s = _ref_hold_rollout(
            cfg, state, previous, forecast, cfg.mpc.horizon_steps
        )
        ref_total += mfd_far_cost_to_go(cfg, ref_s)
        self.assertEqual(len(states), len(ref_states))
        self.assertAlmostEqual(ttt, float(ref_total), places=9)
        for got, want in zip(states, ref_states):
            self.assertAlmostEqual(got.time_sec, want.time_sec, places=9)
            self.assertAlmostEqual(
                got.total_physical_vehicles(cfg.network),
                want.total_physical_vehicles(cfg.network),
                places=9,
            )

    def test_centralized_grid_candidate_matches_reference(self):
        # mode="wu" 를 반드시 포함한다 - `_objective` 는 proposed 모드에서 trajectory_ttt 를
        # 무시하고 states 로 재계산하므로, proposed 만 보면 조기절단 부분합이 틀려도 통과한다.
        for mode in ("wu", "proposed"):
            with self.subTest(mode=mode):
                self._check_centralized_grid_candidate(mode)

    def _check_centralized_grid_candidate(self, mode):
        from src.controllers.centralized_mpc import CentralizedMPC
        from src.controllers.stackelberg_mpc import mfd_far_cost_to_go
        from src.controllers.structured_grid import GridControlCandidate

        cfg, state, previous, forecast = _plain(2)
        controller = CentralizedMPC(cfg, mode=mode)

        def reference(incumbent):
            control = previous.copy()
            ref_states, ref_total, _fw, _ur, early, ref_s = _ref_hold_rollout(
                cfg, state, control, forecast, cfg.mpc.horizon_steps,
                incumbent_obj=None if incumbent is None else float(incumbent),
            )
            if not early:
                ref_total += mfd_far_cost_to_go(cfg, ref_s)
            obj = controller._objective(ref_states, control, previous, ref_total)
            if early:
                obj = float(max(obj, float(incumbent) + 1.0e-9))
            return float(obj), early

        import numpy as np

        # (a) 완주 경로.
        candidate = GridControlCandidate(label="probe", control=previous.copy(), stage="coarse")
        _c, obj, control = controller._evaluate_grid_candidate(
            state, forecast, previous, candidate, incumbent_obj=np.inf,
        )
        ref_obj, ref_early = reference(None)
        self.assertAlmostEqual(obj, ref_obj, places=9)
        self.assertEqual(control.diagnostics["centralized_grid_early_terminated"], float(ref_early))

        # (b) 조기 절단 경로 - incumbent 를 1스텝 TTT 아래로 낮춰 강제한다.
        _s1, one_step_ttt, _f, _u, _e, _t = _ref_hold_rollout(cfg, state, previous, forecast, 1)
        incumbent = float(one_step_ttt) * 0.5
        candidate2 = GridControlCandidate(label="probe", control=previous.copy(), stage="coarse")
        _c2, obj2, control2 = controller._evaluate_grid_candidate(
            state, forecast, previous, candidate2, incumbent_obj=incumbent,
        )
        ref_obj2, ref_early2 = reference(incumbent)
        self.assertTrue(ref_early2, "조기 절단 경로가 발화하지 않으면 이 대조는 무의미하다")
        self.assertAlmostEqual(obj2, ref_obj2, places=9)
        self.assertEqual(control2.diagnostics["centralized_grid_early_terminated"], 1.0)

    def test_distributed_grid_objective_matches_reference(self):
        from src.controllers.distributed_coordinator import DistributedCoordinator
        from src.controllers.structured_grid import GridControlCandidate

        cfg, state, previous, forecast = _plain(2)
        coordinator = DistributedCoordinator(cfg)
        horizon = max(1, min(len(forecast), cfg.mpc.horizon_steps))

        def run(incumbent):
            candidate = GridControlCandidate(
                label="probe", control=previous.copy(), stage="coarse",
            )
            kwargs = {} if incumbent is None else {"incumbent_obj": float(incumbent)}
            _c, obj, control, diag = coordinator._rollout_grid_objective(
                state.copy(), candidate, forecast, None, **kwargs,
            )
            ref_control = coordinator._prepare_grid_control(candidate.control, None)
            ref_states, ref_total, ref_fw, ref_ur, ref_early, ref_s = _ref_hold_rollout(
                cfg, state, ref_control, forecast, horizon,
                incumbent_obj=None if incumbent is None else float(incumbent),
            )
            self.assertAlmostEqual(diag["distributed_grid_rollout_ttt"], ref_total, places=9)
            self.assertAlmostEqual(diag["distributed_grid_rollout_freeway_ttt"], ref_fw, places=9)
            self.assertAlmostEqual(diag["distributed_grid_rollout_urban_ttt"], ref_ur, places=9)
            self.assertEqual(diag["distributed_grid_rollout_completed_steps"], float(len(ref_states)))
            self.assertEqual(diag["distributed_grid_early_terminated"], float(ref_early))
            self.assertAlmostEqual(
                diag["distributed_response_terminal_rollout_vehicles"],
                float(
                    ref_s.total_urban_vehicles(cfg.network)
                    + ref_s.total_freeway_vehicles(cfg.network)
                ),
                places=9,
            )
            return float(obj), ref_early

        _obj, early = run(None)
        self.assertFalse(early)
        prepared = coordinator._prepare_grid_control(previous.copy(), None)
        _s1, one_step_ttt, _f, _u, _e, _t = _ref_hold_rollout(cfg, state, prepared, forecast, 1)
        _obj2, early2 = run(float(one_step_ttt) * 0.5)
        self.assertTrue(early2, "조기 절단 경로가 발화하지 않으면 이 대조는 무의미하다")

    def test_wu_distributed_leader_objective_matches_reference(self):
        from src.controllers.wu_distributed import WuDistributedController

        cfg, state, previous, forecast = _plain(2)
        controller = WuDistributedController(cfg, leader_enabled=True)
        info = controller.decide_with_info(state.copy(), forecast, previous)
        ref_states, _t, _f, _u, _e, _s = _ref_hold_rollout(
            cfg, state, info.control, forecast, cfg.mpc.horizon_steps
        )
        self.assertAlmostEqual(
            float(info.leader_objective),
            float(controller._system_objective(ref_states)),
            places=9,
        )


if __name__ == "__main__":
    unittest.main()
