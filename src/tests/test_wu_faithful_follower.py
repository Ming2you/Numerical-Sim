# WuFaithfulFollower 국소 freeway 모델의 plant 정합 + Wu-metered leader prefilter action-분별 회귀 테스트
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


if __name__ == "__main__":
    unittest.main()
