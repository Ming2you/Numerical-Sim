# B3(metering/VSL 가격 포팅)·B4(barrier 가격): 휴면=비트동일, 부호 반응, refresh 하달, barrier 계산 검증
import unittest

from src.controllers.leader import LeaderAction
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


def _setup_freeway(cfg):
    follower = WuFaithfulFollower(cfg)
    state = TrafficState.initial(cfg)
    demand = DemandProfile(
        cfg,
        ScenarioConfig("probe", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0),
    ).horizon(0.0, 1)[0]
    snapshot = ControlAction.fixed(cfg)
    coupling = follower._wu._coupling(state, ControlAction.uncontrolled(cfg), demand)
    link = next(
        l for l in cfg.network.freeway_links
        if any(cfg.network.ramp_to_freeway.get(r) == l for r in cfg.network.ramps)
        and float(follower._wu._omega_f.get(l, 0.0)) > 0.0
    )
    owned = [r for r in cfg.network.ramps if cfg.network.ramp_to_freeway.get(r) == link]
    return follower, state, demand, snapshot, coupling, link, owned


class TestMeteringPriceFollower(unittest.TestCase):
    def test_zero_price_matches_none_in_pfo_branch(self):
        cfg = _build_cfg()
        follower, state, demand, snapshot, coupling, link, owned = _setup_freeway(cfg)
        _, meter_none, _ = follower._solve_freeway_agent_metered(
            link, state, coupling, demand, snapshot, None,
        )
        follower.metering_marginal_price = {r: 0.0 for r in owned}
        follower.metering_marginal_price_ref = {
            r: float(snapshot.ramp_metering.get(r, 0.0)) for r in owned
        }
        _, meter_zero, _ = follower._solve_freeway_agent_metered(
            link, state, coupling, demand, snapshot, None,
        )
        for ramp, value in meter_none.items():
            self.assertAlmostEqual(
                meter_zero[ramp], value, places=9,
                msg=f"zero metering price must not move metering ({ramp})",
            )

    def test_price_sign_pushes_release(self):
        # 큰 음수 g_ext(방류 이득) → 방류 합이, 큰 양수(방류 비쌈) → 억제되어야 한다.
        cfg = _build_cfg()
        leader = LeaderAction(0.0, 3000.0)

        def solve_with(g_ext):
            follower, state, demand, snapshot, coupling, link, owned = _setup_freeway(cfg)
            follower.metering_marginal_price = {r: float(g_ext) for r in owned}
            follower.metering_marginal_price_ref = {
                r: float(snapshot.ramp_metering.get(r, 0.0)) for r in owned
            }
            _, meter, _ = follower._solve_freeway_agent_metered(
                link, state, coupling, demand, snapshot, leader,
            )
            return sum(meter.values())

        release_cheap = solve_with(-10.0)
        release_costly = solve_with(+10.0)
        self.assertGreater(
            release_cheap, release_costly,
            msg="negative metering price must yield more release than positive",
        )

    def test_local_metering_costs_ignores_active_price(self):
        cfg = _build_cfg()
        follower, state, demand, snapshot, coupling, link, owned = _setup_freeway(cfg)
        ramp = owned[0]
        cap = float(cfg.network.ramp_capacity_veh_h[ramp])
        requests = {ramp: [0.5 * cap, cap]}
        control = ControlAction.fixed(cfg)

        clean = follower.local_metering_costs(requests, state, control, demand)
        follower.metering_marginal_price = {ramp: 100.0}
        priced = follower.local_metering_costs(requests, state, control, demand)

        self.assertEqual(follower.metering_marginal_price, {ramp: 100.0})
        for a, b in zip(clean[ramp], priced[ramp]):
            self.assertAlmostEqual(a, b, places=12)


class TestBarrierAndRefresh(unittest.TestCase):
    @staticmethod
    def _saturated_setup(cfg):
        """barrier가 horizon 동안 살아있는 과포화 셋업.

        기본 수요(scale 1.0)는 rho_crit+20에서 시작해도 한 interval(180s) 만에 임계
        아래로 배수된다(실측 9~23 veh/km) — barrier는 예측 상태에서 평가되므로 유지
        가능한 과수요(freeway/ramp ×4)와 높은 초기 밀도가 필요하다(실측 33~93 유지)."""
        state = TrafficState.initial(cfg)
        net = cfg.network
        for link in net.freeway_links:
            n_seg = len(state.freeway_density.get(link, []))
            state.freeway_density[link] = [float(net.rho_crit) + 40.0] * n_seg
        forecast = DemandProfile(
            cfg,
            ScenarioConfig("probe", urban_scale=2.0, freeway_scale=4.0, ramp_scale=4.0),
        ).horizon(0.0, 1)
        return state, forecast

    def test_barrier_zero_when_disabled_positive_when_saturated(self):
        cfg = _build_cfg()
        controller = StackelbergWuMeteredController(cfg)
        state, forecast = self._saturated_setup(cfg)
        control = ControlAction.fixed(cfg)

        controller.barrier_price_enabled = False
        _, barrier_off = controller._predict_ttt_and_barrier(state.copy(), control, forecast)
        self.assertEqual(barrier_off, 0.0)

        controller.barrier_price_enabled = True
        _, barrier_on = controller._predict_ttt_and_barrier(state.copy(), control, forecast)
        self.assertGreater(
            barrier_on, 0.0,
            msg="saturated freeway densities must produce positive barrier",
        )

    def test_refresh_hands_metering_prices_and_barrier_changes_them(self):
        cfg = _build_cfg()
        state, forecast = self._saturated_setup(cfg)
        state.time_sec = float(cfg.simulation.control_interval)
        net = cfg.network
        previous = ControlAction.fixed(cfg)
        # metering 운영점을 cap 미만으로(유한차분 양방향 확보).
        for ramp in net.ramps:
            previous.ramp_metering[ramp] = 0.5 * float(net.ramp_capacity_veh_h[ramp])

        controller = StackelbergWuMeteredController(cfg)
        controller.metering_price_enabled = True
        controller._maybe_refresh_signal_prices(state, forecast, previous)
        follower = controller.nash_solver
        self.assertIsNotNone(follower.metering_marginal_price)
        self.assertEqual(set(follower.metering_marginal_price), set(net.ramps))
        base_prices = dict(follower.metering_marginal_price)

        controller_b4 = StackelbergWuMeteredController(cfg)
        controller_b4.metering_price_enabled = True
        controller_b4.barrier_price_enabled = True
        controller_b4._maybe_refresh_signal_prices(state, forecast, previous)
        b4_prices = dict(controller_b4.nash_solver.metering_marginal_price)

        # barrier gradient(방류↑ → 초과밀도↑ → 양수)가 최소 한 ramp의 가격을 위로 민다.
        moved_up = any(
            b4_prices[r] > base_prices[r] + 1.0e-12 for r in net.ramps
        )
        self.assertTrue(
            moved_up,
            msg=f"barrier must push some metering price upward: base={base_prices}, b4={b4_prices}",
        )


if __name__ == "__main__":
    unittest.main()
