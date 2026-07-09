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

    def test_e2_vsl_price_subtracts_local_gradient(self):
        # E2: VSL 채널이 raw g_i가 아니라 g_ext = g_i − d_local. d_local 재료인
        # local_vsl_costs가 유한하고, 채널 출력도 유한해야 한다.
        cfg = _build_cfg()
        controller = StackelbergWuMeteredController(cfg)
        controller.signal_price_enabled = False
        controller.vsl_price_enabled = True
        state = TrafficState.initial(cfg)
        state.time_sec = float(cfg.simulation.control_interval)
        controller._maybe_refresh_signal_prices(
            state, _demand(cfg), ControlAction.fixed(cfg),
        )
        f = controller.nash_solver
        net = cfg.network
        self.assertIsNotNone(f.vsl_marginal_price)
        expected_keys = {
            f"{link}__seg{i}"
            for link in net.freeway_links
            for i in range(int(net.freeway_segments_per_link))
        }
        self.assertEqual(set(f.vsl_marginal_price), expected_keys)
        for v in f.vsl_marginal_price.values():
            self.assertTrue(v == v and v not in (float("inf"), -float("inf")))
        # d_local 프리미티브 자체도 직접 검증(전 링크, 벡터 override 유한).
        vhi = max(cfg.freeway_follower.vsl_set)
        n_seg = int(net.freeway_segments_per_link)
        reqs = {link: [[vhi] * n_seg] for link in net.freeway_links}
        costs = f.local_vsl_costs(reqs, state, ControlAction.fixed(cfg), _demand(cfg)[0])
        for link in net.freeway_links:
            self.assertEqual(len(costs[link]), 1)
            self.assertGreaterEqual(costs[link][0], 0.0)

    def test_e1_price_far_changes_price_rollout_only_when_enabled(self):
        # E1: price_far_enabled+leader_mfd_far_enabled면 가격 rollout 채점이 TTT+far,
        # 아니면 TTT 그대로(비트동일). 혼잡 state를 만들어 far>0로 확인.
        cfg = _build_cfg()
        cfg.mpc.leader_mfd_far_enabled = True
        controller = StackelbergWuMeteredController(cfg)
        state = TrafficState.initial(cfg)
        # urban accumulation을 인위적으로 채워 far>0 유도.
        for m in list(state.urban_movement_queue):
            state.urban_movement_queue[m] = 40.0
        net = cfg.network
        sig = net.signals[0]
        p1 = float(net.effective_green_total) / 2.0
        controller.price_far_enabled = False  # 기본 True(2026-07-09) — OFF 기준선 명시
        base = controller._global_rollout_ttt_with_green(
            state, ControlAction.fixed(cfg), _demand(cfg), sig, p1,
        )
        controller.price_far_enabled = True
        with_far = controller._global_rollout_ttt_with_green(
            state, ControlAction.fixed(cfg), _demand(cfg), sig, p1,
        )
        self.assertGreater(with_far, base,
                           msg="price_far ON이면 가격 rollout 채점에 far가 가산돼야 한다")

    def test_price_tr_smoothness_censoring_removed(self):
        # PRICE-TR: 가격 활성 신호는 smoothness 마찰 0 — 거대 마찰(1e6)에서도 가격이
        # green을 움직인다. 플래그 OFF면 마찰이 가격을 검열(deadband)해 움직이지 못한다.
        cfg = ExperimentConfig.from_file(
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
                "urban_follower": {"green_smoothness_weight": 1.0e6},
            },
        )
        net = cfg.network
        total = float(net.effective_green_total)

        def _solve(disabled: bool) -> float:
            f = WuFaithfulFollower(cfg)
            f.price_smoothness_disabled = disabled
            sig = [s for s in net.signals if not f._local_models[s].has_ramps][0]
            prev = ControlAction.fixed(cfg)
            p0 = float(prev.green_times.get(f"{sig}_p1", total / 2.0))
            f.signal_marginal_price = {sig: -100.0}  # "p1을 키워라"
            f.signal_marginal_price_ref = {sig: p0}
            f.signal_marginal_price_trust_sec = 6.0
            nash = f.solve(TrafficState.initial(cfg), None, _demand(cfg), prev)
            return float(nash.control.green_times.get(f"{sig}_p1", p0)) - p0

        moved = _solve(disabled=True)
        censored = _solve(disabled=False)
        self.assertGreater(abs(moved), 1e-9,
                           msg="마찰 무시(PRICE-TR)면 가격이 green을 움직여야 한다")
        self.assertLess(abs(censored), 1e-9,
                        msg="마찰 유지면 1e6 smoothness가 가격을 검열해야 한다")

    def test_vsl_trust_handed_down_and_bounds_moves(self):
        # PRICE-TR: 컨트롤러가 vsl trust(±10)를 하달하고, follower의 VSL 선택이
        # ref에서 trust 반경 이내로 제한된다.
        cfg = _build_cfg()
        controller = StackelbergWuMeteredController(cfg)
        controller.signal_price_enabled = False
        controller.vsl_price_enabled = True
        state = TrafficState.initial(cfg)
        state.time_sec = float(cfg.simulation.control_interval)
        controller._maybe_refresh_signal_prices(
            state, _demand(cfg), ControlAction.fixed(cfg),
        )
        f = controller.nash_solver
        self.assertEqual(f.vsl_marginal_price_trust_kmh, 10.0)
        # follower 단독: 거대 음수 가격("VSL 올려라")에도 trust가 보폭을 ±10으로 제한.
        net = cfg.network
        link = net.freeway_links[0]
        n_seg = int(net.freeway_segments_per_link)
        vlo = min(cfg.freeway_follower.vsl_set)
        ref_v = vlo + 0.0  # 낮은 ref에서 시작
        f2 = WuFaithfulFollower(cfg)
        f2.vsl_marginal_price = {f"{link}__seg{i}": -1.0e6 for i in range(n_seg)}
        f2.vsl_marginal_price_ref = {f"{link}__seg{i}": ref_v for i in range(n_seg)}
        f2.vsl_marginal_price_trust_kmh = 10.0
        prev = ControlAction.fixed(cfg)
        for i in range(n_seg):
            prev.vsl[f"{link}__seg{i}"] = ref_v
        prev.vsl[link] = ref_v
        ctrl_dem = _demand(cfg)[0]
        coupling = f2._wu._coupling(state, prev, ctrl_dem)
        vsl_dict, _, _ = f2._solve_freeway_agent_local(link, state, coupling, ctrl_dem, prev)
        for i in range(n_seg):
            chosen = float(vsl_dict.get(f"{link}__seg{i}", ref_v))
            self.assertLessEqual(abs(chosen - ref_v), 10.0 + 1e-6,
                                 msg="VSL trust(±10km/h)가 보폭을 제한해야 한다")

    def test_link_share_omega_density_responds_to_headroom(self):
        # LINK-SHARE(density): 균등 밀도 → 균등 분할, 한 링크 혼잡 → 그 링크 몫 축소,
        # 전 링크 임계 초과 → 균등 fallback.
        cfg = _build_cfg()
        controller = StackelbergWuMeteredController(cfg)
        net = cfg.network
        l0, l1 = net.freeway_links[0], net.freeway_links[1]
        state = TrafficState.initial(cfg)
        omega = controller._link_share_omega(state)
        self.assertAlmostEqual(omega[l0], 0.5, places=6)
        self.assertAlmostEqual(sum(omega.values()), 1.0, places=9)
        # l0 혼잡(임계 근접) → l0 몫 < 0.5.
        rho_crit = float(net.rho_crit)
        state.freeway_density[l0] = [rho_crit * 0.9 for _ in state.freeway_density[l0]]
        omega = controller._link_share_omega(state)
        self.assertLess(omega[l0], 0.5)
        self.assertAlmostEqual(sum(omega.values()), 1.0, places=9)
        # 전 링크 임계 초과 → headroom 0 → 균등 fallback.
        for l in (l0, l1):
            state.freeway_density[l] = [rho_crit * 1.5 for _ in state.freeway_density[l]]
        omega = controller._link_share_omega(state)
        self.assertAlmostEqual(omega[l0], 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
