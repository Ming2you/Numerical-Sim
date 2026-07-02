# WuFaithfulFollower 국소 freeway 모델의 plant 정합 + Wu-metered leader prefilter action-분별 회귀 테스트
import sys
import unittest

from src.controllers.leader import LeaderAction
from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState


class TestLocalRampReleaseOrdering(unittest.TestCase):
    """Finding #3 회귀: 국소 모델 release가 유입 반영 전 reservoir 기준으로 결정돼야 한다."""

    def test_local_ramp_release_sees_pre_arrival_queue(self):
        # plant(run_coupled_interval)는 include_current_arrivals=False로 release를
        # 결정한 뒤 urban 유입을 reservoir에 적재한다. 버그 코드는 로컬 모델에서
        # 유입을 먼저 적재해 첫 substep의 ramp_queue가 approach*dt_h만큼 커진 채
        # release가 계산됐다. 여기서는 ramp_queue=0 + coupling>0으로 시작해 첫
        # _local_ramp_release 호출이 ramp_queue=0을 봐야 함을 검증한다(버그 코드는
        # 600 veh/h * T_f_h ≈ 1.67 veh > 0이 기록돼 실패한다 — 판별력 확보).
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "simulation": {"T_total": 180.0},
                "mpc": {"horizon_steps": 1},
                "freeway_follower": {
                    "freeway_prediction_horizon_steps": 1,
                    "vsl_sequence_search": False,
                },
            },
        )
        follower = WuFaithfulFollower(cfg)
        link = cfg.network.freeway_links[0]
        owned = [r for r in cfg.network.ramps if cfg.network.ramp_to_freeway.get(r) == link]
        self.assertTrue(owned)

        state = TrafficState.initial(cfg)
        for ramp in cfg.network.ramps:
            state.ramp_queue[ramp] = 0.0
        coupling = {f"u_on_{ramp}": 600.0 for ramp in owned}
        demand = DemandProfile(
            cfg,
            ScenarioConfig("probe", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0),
        ).horizon(0.0, 1)[0]
        previous = ControlAction.fixed(cfg)

        recorded = []
        original = follower._local_ramp_release

        def spy(link_arg, rhos, ramp_queue, candidate_control, demand_arg):
            recorded.append({r: float(v) for r, v in dict(ramp_queue).items()})
            return original(link_arg, rhos, ramp_queue, candidate_control, demand_arg)

        follower._local_ramp_release = spy
        try:
            follower._solve_freeway_agent_local(link, state, coupling, demand, previous)
        finally:
            follower._local_ramp_release = original

        self.assertTrue(recorded, "no _local_ramp_release call recorded")
        first_call_queue = recorded[0]
        for ramp in owned:
            self.assertAlmostEqual(
                first_call_queue.get(ramp, 0.0),
                0.0,
                places=9,
                msg=(
                    f"first-substep release for {ramp} must be decided on the "
                    "pre-arrival reservoir (plant include_current_arrivals=False)"
                ),
            )


class TestWuMeteredProxyActionAware(unittest.TestCase):
    """Finding #5 회귀: prefilter proxy가 N_UF_star에 따라 다른 objective를 내야 한다."""

    def test_proxy_score_distinguishes_nuf_candidates(self):
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "simulation": {"T_total": 180.0},
                "mpc": {"horizon_steps": 1, "max_nash_iter": 1},
            },
        )
        controller = StackelbergWuMeteredController(cfg)
        state = TrafficState.initial(cfg)
        # metering 차이가 rollout에 드러나도록 ramp queue를 수동 주입(혼잡 state).
        for ramp in cfg.network.ramps:
            state.ramp_queue[ramp] = 60.0
        forecast = DemandProfile(
            cfg,
            ScenarioConfig("probe", urban_scale=1.2, freeway_scale=1.0, ramp_scale=1.2),
        ).horizon(0.0, 1)
        previous = ControlAction.fixed(cfg)

        low = controller._proxy_score_candidate(
            0, LeaderAction(0.0, 200.0), state.copy(), forecast, previous,
        )
        high = controller._proxy_score_candidate(
            1, LeaderAction(0.0, 2800.0), state.copy(), forecast, previous,
        )

        for row in (low, high):
            for key in (
                "index", "N_P_star", "N_UF_star", "objective",
                "base", "follower_ttt", "spillback_violation",
            ):
                self.assertIn(key, row)
        self.assertGreater(
            abs(low["objective"] - high["objective"]),
            1.0e-9,
            "proxy objective must differ across N_UF_star candidates (action-blind regression)",
        )


class _LeaderStub:
    """N_P_star/N_UF_star float 속성만 가진 leader 대체(테스트 전용)."""

    def __init__(self, n_p_star: float = 50.0, n_uf_star: float = 0.0):
        self.N_P_star = float(n_p_star)
        self.N_UF_star = float(n_uf_star)


def _dual_test_config() -> ExperimentConfig:
    return ExperimentConfig.from_file(
        "src/config/default.yaml",
        {
            "simulation": {"T_total": 180.0},
            "mpc": {"horizon_steps": 1, "max_nash_iter": 1},
            "freeway_follower": {
                "freeway_prediction_horizon_steps": 1,
                "vsl_sequence_search": False,
            },
        },
    )


class TestLambdaDualIntegralUpdate(unittest.TestCase):
    """A1+A2 회귀: λ step 간 적분 갱신(비음수·cap·방향) + commit green == 합의 green."""

    def test_lambda_update_nonnegative_cap_direction(self):
        # A1 — λ_next = clip(λ + gain·(Σnin − target), 0, cap) 거동 검증.
        follower = WuFaithfulFollower(_dual_test_config())
        # 방향: Σnin > target(유입 과다) → λ 증가(억제 강화).
        self.assertAlmostEqual(
            follower._lambda_np_update(1.0, 200.0, 100.0),
            1.0 + follower.lambda_np_step_gain * 100.0,
            places=12,
        )
        self.assertGreater(follower._lambda_np_update(1.0, 200.0, 100.0), 1.0)
        # A1 핵심: target > Σnin이고 λ=0이면 0 유지(음수 λ 금지 — 유입 강제 보상 없음).
        self.assertEqual(follower._lambda_np_update(0.0, 50.0, 200.0), 0.0)
        # target > Σnin, λ>0이면 0을 향해 내려가되 음수로는 안 간다.
        self.assertEqual(follower._lambda_np_update(0.5, 0.0, 1.0e6), 0.0)
        # cap 초과 시 cap으로 clip.
        self.assertEqual(
            follower._lambda_np_update(follower.lambda_np_cap, 1.0e9, 0.0),
            follower.lambda_np_cap,
        )

    def test_commit_green_equals_last_consensus_sweep(self):
        # A2 — 이분법·commit sweep 폐지: 반환 green이 마지막 Jacobi 합의 sweep의 p1과
        # 일치해야 하고, _sum_nin_at_lambda 경유 urban solve가 아예 없어야 한다
        # (_np_feasible_range는 _agent_net_inflow_veh를 직접 쓰므로 여기 안 잡힌다).
        cfg = _dual_test_config()
        follower = WuFaithfulFollower(cfg)
        state = TrafficState.initial(cfg)
        forecast = DemandProfile(
            cfg,
            ScenarioConfig("probe", urban_scale=1.2, freeway_scale=1.0, ramp_scale=1.0),
        ).horizon(0.0, 1)
        previous = ControlAction.fixed(cfg)

        calls = []  # (caller, signal, p1)
        original = follower._solve_urban_agent_local

        def spy(signal, *args, **kwargs):
            result = original(signal, *args, **kwargs)
            caller = sys._getframe(1).f_code.co_name
            calls.append((caller, signal, float(result[0])))
            return result

        follower._solve_urban_agent_local = spy
        try:
            result = follower.solve(state, _LeaderStub(), forecast, previous)
        finally:
            follower._solve_urban_agent_local = original

        self.assertTrue(calls, "no _solve_urban_agent_local call recorded")
        callers = {caller for caller, _, _ in calls}
        self.assertNotIn(
            "_sum_nin_at_lambda",
            callers,
            "bisection/commit sweep must be gone (no _sum_nin_at_lambda-driven urban solve)",
        )
        # 신호별 마지막 _solve_followers sweep의 p1 == commit된 green_times p1.
        last_p1 = {}
        for caller, signal, p1 in calls:
            if caller == "_solve_followers":
                last_p1[signal] = p1
        self.assertEqual(set(last_p1), set(cfg.network.signals))
        for signal in cfg.network.signals:
            self.assertAlmostEqual(
                float(result.control.green_times[f"{signal}_p1"]),
                last_p1[signal],
                places=9,
                msg=f"committed green for {signal} must equal the last consensus sweep",
            )

    def test_solve_does_not_mutate_persistent_lambda(self):
        # 오염 방지 — solve()는 self._lambda_P를 절대 바꾸지 않고 λ_next를 diagnostics로만 낸다.
        cfg = _dual_test_config()
        follower = WuFaithfulFollower(cfg)
        follower._lambda_P = 0.5
        state = TrafficState.initial(cfg)
        forecast = DemandProfile(
            cfg,
            ScenarioConfig("probe", urban_scale=1.2, freeway_scale=1.0, ramp_scale=1.0),
        ).horizon(0.0, 1)
        previous = ControlAction.fixed(cfg)

        result = follower.solve(state, _LeaderStub(), forecast, previous)

        self.assertEqual(follower._lambda_P, 0.5)
        diag = result.control.diagnostics
        self.assertIn("wu_faithful_lambda_next", diag)
        self.assertGreaterEqual(float(diag["wu_faithful_lambda_next"]), 0.0)
        self.assertLessEqual(float(diag["wu_faithful_lambda_next"]), follower.lambda_np_cap)
        # solve에 사용된 λ는 warm-start 값 그대로여야 한다.
        self.assertAlmostEqual(float(diag["wu_faithful_lambda_P"]), 0.5, places=12)


if __name__ == "__main__":
    unittest.main()
