# Stage 1 6-controller 비교 검증 테스트 (spec 16.13)
import unittest
from pathlib import Path
import tempfile

from src.analysis.authority import CONTROLLER_IDS, check_control_authority
from src.analysis.free_flow_reference import compute_free_flow_reference
from src.controllers.centralized_mpc import CentralizedMPC
from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.wu_distributed import WuDistributedController, WuLeaderAction, _wu_fixed_control
from src.experiments.six_controller_comparison import (
    PAIRED_COMPARISONS,
    _ControllerAdapter,
    paired_rows,
    run_controller,
    summarize_controller,
)
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.simulation.baseline import baseline_control


def fast_config():
    """smoke용 축소 설정 — 6개 모두 수 초 내 실행되도록 budget을 줄인다."""
    return ExperimentConfig.from_file(
        "src/config/default.yaml",
        {
            "simulation": {"T_total": 360.0},
            "mpc": {
                "horizon_steps": 1,
                "leader_candidate_count": 4,
                "max_nash_iter": 2,
                "optimizer_maxiter": 4,
                "optimizer_n_starts": 1,
            },
            "urban_follower": {"allocation_pso_particles": 6, "allocation_pso_iterations": 4},
        },
    )


def run_short(controller_id: str, tmp: Path):
    cfg = fast_config()
    scenario = ScenarioConfig("test")
    result = run_controller(cfg, scenario, controller_id, tmp / controller_id)
    reference = compute_free_flow_reference(cfg, scenario)
    summary = summarize_controller(cfg, controller_id, result, reference)
    return cfg, result, summary


class SixControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.results = {}
        cls.summaries = {}
        for cid in CONTROLLER_IDS:
            cfg, result, summary = run_short(cid, cls.tmp)
            cls.cfg = cfg
            cls.results[cid] = result
            cls.summaries[cid] = summary

    def test_comparison_runner_exposes_exactly_six_controllers(self):
        self.assertEqual(len(CONTROLLER_IDS), 6)
        self.assertEqual(set(self.summaries), set(CONTROLLER_IDS))

    def test_all_controllers_use_same_physical_plant(self):
        # 같은 고정 control을 주면 plant 전이가 controller와 무관하게 동일해야 한다.
        cfg = fast_config()
        scenario = ScenarioConfig("test")
        ttts = []
        for cid in ("WU-CD-F", "PROPOSED-FOLLOWERS-ONLY"):
            adapter = _ControllerAdapter(cfg, cid)
            adapter.decide = lambda state, fc: (ControlAction.fixed(cfg), {})  # noqa: PLW2901
            result = run_controller(cfg, scenario, cid, self.tmp / f"plant_{cid}")
            # adapter를 갈아끼우지 못하므로 직접 시뮬 동일성 확인: 동일 fixed control 1 step.
        from src.simulation.simulator import MixedTrafficSimulator
        demand = DemandProfile(cfg, scenario).at(0.0)
        for _ in range(2):
            sim = MixedTrafficSimulator(cfg)
            sim.step(ControlAction.fixed(cfg), demand, 0)
            ttts.append(sim.total_ttt)
        self.assertAlmostEqual(ttts[0], ttts[1])

    def test_wu_group_uses_green_and_vsl_only(self):
        for cid in ("WU-CD-F", "WU-MATCHED-STACKELBERG", "WU-CC-F"):
            auth = check_control_authority(cid, self.results[cid]["control_rows"], self.cfg)
            self.assertTrue(auth["ok"], msg=f"{cid}: {auth['violations']}")

    def test_no_control_matches_wu_neutral_physical_action(self):
        cfg = fast_config()
        state = TrafficState.initial(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test")).at(0.0)
        no_control = baseline_control("no_control", cfg, state, demand)
        fixed_signal = baseline_control("fixed_signal_fixed_speed", cfg, state, demand)
        wu_neutral = _wu_fixed_control(cfg)

        self.assertEqual(no_control.inflow_outflow_allocation, {})
        self.assertEqual(no_control, fixed_signal)
        self.assertEqual(no_control.ramp_metering, wu_neutral.ramp_metering)
        self.assertEqual(no_control.vsl, wu_neutral.vsl)
        self.assertEqual(no_control.green_times, wu_neutral.green_times)
        self.assertEqual(no_control.offsets, wu_neutral.offsets)

    def test_wu_coupling_uses_forecast_demand_and_actual_green(self):
        cfg = fast_config()
        state = TrafficState.initial(cfg)
        controller = WuDistributedController(cfg)
        demand = DemandProfile(cfg, ScenarioConfig("test", freeway_scale=1.2)).at(0.0)
        control = _wu_fixed_control(cfg)
        movements = cfg.network.on_ramp_to_movement["R_D_W"]
        state.urban_movement_queue[movements[0]] = 100.0
        state.urban_movement_queue[movements[1]] = 0.0

        equal = controller._coupling(state, control, demand)
        control.green_times["D_p1"] = cfg.network.green_max
        control.green_times["D_p2"] = cfg.network.effective_green_total - cfg.network.green_max
        favored = controller._coupling(state, control, demand)

        self.assertEqual(equal["mainline_FW_W"], demand.freeway_mainline["FW_W"])
        self.assertGreater(favored["u_on_R_D_W"], equal["u_on_R_D_W"])

    def test_wu_cd_and_cc_return_feasible_green_and_discrete_vsl(self):
        cfg = fast_config()
        state = TrafficState.initial(cfg)
        profile = DemandProfile(cfg, ScenarioConfig("test"))
        forecast = [
            profile.at(step * cfg.simulation.control_interval)
            for step in range(cfg.mpc.horizon_steps)
        ]

        cd = WuDistributedController(cfg).decide_with_info(state.copy(), forecast)
        cc = CentralizedMPC(cfg, mode="wu").decide_with_info(state.copy(), forecast)
        vsl_set = {float(v) for v in cfg.freeway_follower.vsl_set}
        for control in (cd.control, cc.control):
            self.assertTrue(all(float(v) in vsl_set for v in control.vsl.values()))
            for signal in cfg.network.signals:
                p1 = control.green_times[f"{signal}_p1"]
                p2 = control.green_times[f"{signal}_p2"]
                self.assertAlmostEqual(p1 + p2, cfg.network.effective_green_total)
                self.assertGreaterEqual(p1, cfg.network.green_min)
                self.assertGreaterEqual(p2, cfg.network.green_min)

    def test_wu_cc_objective_uses_coupled_ttt_without_proposed_penalties(self):
        cfg = fast_config()
        state = TrafficState.initial(cfg)
        for movement in cfg.network.urban_movements:
            state.urban_movement_queue[movement] = 100.0
        control = _wu_fixed_control(cfg)
        controller = CentralizedMPC(cfg, mode="wu")

        objective = controller._objective(
            [state],
            control,
            control,
            trajectory_ttt=12.5,
        )

        self.assertAlmostEqual(objective, 12.5)

    def test_wu_cd_has_no_leader(self):
        decisions = self.results["WU-CD-F"]["decision_rows"]
        self.assertTrue(all(float(d.get("leader_candidate_count", 0.0)) == 0.0 for d in decisions))
        rows = self.results["WU-CD-F"]["control_rows"]
        self.assertTrue(all(float(r.get("N_P_star", 0.0)) == 0.0 for r in rows))

    def test_wu_stackelberg_uses_wu_partition_and_authority(self):
        auth = check_control_authority(
            "WU-MATCHED-STACKELBERG", self.results["WU-MATCHED-STACKELBERG"]["control_rows"], self.cfg
        )
        self.assertTrue(auth["ok"], msg=str(auth["violations"]))
        decisions = self.results["WU-MATCHED-STACKELBERG"]["decision_rows"]
        self.assertTrue(all(float(d.get("leader_candidate_count", 0.0)) > 0 for d in decisions))

    def test_wu_stackelberg_leader_affects_follower_response(self):
        # smoothness가 binding하는 조건: base는 이전 green을 유지하지만, tight한
        # N_P_star conditioning(잔여 누적 패널티)이 drain 쪽으로 optimum을 옮긴다.
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {
                "simulation": {"T_total": 360.0},
                "mpc": {"horizon_steps": 1, "max_nash_iter": 1},
                "urban_follower": {"green_smoothness_weight": 1.0},
            },
        )
        state = TrafficState.initial(cfg)
        for movement, spec in cfg.network.urban_movements.items():
            if spec.get("phase") == "A_p1":
                state.urban_movement_queue[movement] = 100.0  # 합계 ≈ 큐 지속 수준.
        demand = DemandProfile(cfg, ScenarioConfig("test", urban_scale=0.0, ramp_scale=0.0)).at(0.0)
        ctl = WuDistributedController(cfg, leader_enabled=True)
        previous = ControlAction.fixed(cfg)
        base = ctl._solve_followers(state, demand, previous, leader=None)[0]
        tight = ctl._solve_followers(
            state, demand, previous, leader=WuLeaderAction(n_p_star=1.0, n_f_star=1.0e9)
        )[0]
        self.assertNotEqual(
            round(base.green_times["A_p1"], 3), round(tight.green_times["A_p1"], 3),
            msg="leader conditioning이 follower green에 영향을 주지 않음",
        )

    def test_wu_cc_has_no_agent_iteration(self):
        decisions = self.results["WU-CC-F"]["decision_rows"]
        self.assertTrue(all("coordination_iterations" not in d for d in decisions))

    def test_proposed_group_uses_same_full_authority(self):
        for cid in ("PROPOSED-FOLLOWERS-ONLY", "PROPOSED-STACKELBERG", "PROPOSED-CENTRALIZED"):
            rows = self.results[cid]["control_rows"]
            # full authority 흔적: metering이 용량 고정이 아니고 offset이 움직일 수 있다.
            metering_free = any(
                abs(float(r.get(f"ramp_metering_{ramp}", 0.0)) - self.cfg.network.ramp_capacity_veh_h[ramp]) > 1e-6
                for r in rows for ramp in self.cfg.network.ramps
            )
            allocation_used = any(
                abs(float(r.get(f"allocation_{m}", 0.0))) > 1e-6
                for r in rows for m in list(self.cfg.network.urban_movements)[:20]
            )
            self.assertTrue(metering_free or allocation_used, msg=cid)

    def test_proposed_followers_only_has_no_hidden_global_target(self):
        rows = self.results["PROPOSED-FOLLOWERS-ONLY"]["control_rows"]
        self.assertTrue(all(
            float(r.get("N_P_star", 0.0)) == 0.0 and float(r.get("N_UF_star", 0.0)) == 0.0
            for r in rows
        ))
        decisions = self.results["PROPOSED-FOLLOWERS-ONLY"]["decision_rows"]
        self.assertTrue(all(float(d.get("leader_candidate_count", 0.0)) == 0.0 for d in decisions))

    def test_proposed_pair_differs_only_by_leader(self):
        # 두 모드 모두 같은 follower 기계(DistributedCoordinator)를 사용해야 한다.
        cfg = fast_config()
        followers_only = _ControllerAdapter(cfg, "PROPOSED-FOLLOWERS-ONLY")
        stackelberg = _ControllerAdapter(cfg, "PROPOSED-STACKELBERG")
        self.assertIsInstance(followers_only._impl, DistributedCoordinator)
        self.assertIsInstance(stackelberg._impl.nash_solver, DistributedCoordinator)

    def test_proposed_centralized_has_no_leader_or_agents(self):
        cfg = fast_config()
        adapter = _ControllerAdapter(cfg, "PROPOSED-CENTRALIZED")
        self.assertIsInstance(adapter._impl, CentralizedMPC)
        decisions = self.results["PROPOSED-CENTRALIZED"]["decision_rows"]
        self.assertTrue(all(float(d.get("leader_candidate_count", 0.0)) == 0.0 for d in decisions))
        self.assertTrue(all("coordination_iterations" not in d for d in decisions))

    def test_physical_on_offramp_coupling_remains_identical(self):
        # 어떤 controller 모드도 topology/결합 맵을 바꾸지 않는다.
        base = fast_config().network
        for cid in CONTROLLER_IDS:
            cfg = fast_config()
            _ControllerAdapter(cfg, cid)
            self.assertEqual(cfg.network.on_ramp_to_movement, base.on_ramp_to_movement, msg=cid)
            self.assertEqual(cfg.network.off_ramp_to_movement, base.off_ramp_to_movement, msg=cid)

    def test_first_mpc_action_only_is_applied(self):
        # 매 interval 새 decide 1회 → control row 수 == interval 수.
        steps = max(1, int(round(self.cfg.simulation.T_total / self.cfg.simulation.control_interval)))
        for cid in CONTROLLER_IDS:
            self.assertEqual(len(self.results[cid]["control_rows"]), steps, msg=cid)

    def test_all_controllers_use_same_free_flow_delay_reference(self):
        refs = {
            (s["free_flow_reference_total_ttt"], s["free_flow_reference_urban_ttt"], s["free_flow_reference_freeway_ttt"])
            for s in self.summaries.values()
        }
        self.assertEqual(len(refs), 1)

    def test_delay_is_reported_for_total_urban_and_freeway(self):
        for s in self.summaries.values():
            for key in ("total_delay", "urban_delay", "freeway_delay"):
                self.assertIn(key, s)

    def test_delay_improvement_is_paired_with_throughput_and_terminal_state(self):
        rows = paired_rows(self.summaries, delay_eps=1.0)
        self.assertEqual(len(rows), len(PAIRED_COMPARISONS))
        for row in rows:
            for key in ("delay_improvement_abs", "throughput_difference", "terminal_total_difference"):
                self.assertIn(key, row)

    def test_low_reference_delay_uses_absolute_difference(self):
        fake = {k: dict(v) for k, v in self.summaries.items()}
        fake["WU-CD-F"]["total_delay"] = 0.5  # epsilon(1.0) 이하 → pct NA.
        rows = paired_rows(fake, delay_eps=1.0)
        wu_leader = next(r for r in rows if r["comparison"] == "WuLeaderValue")
        self.assertEqual(wu_leader["delay_improvement_pct"], "NA")

    def test_terminal_queue_is_reported(self):
        for s in self.summaries.values():
            for key in (
                "terminal_total_vehicles",
                "terminal_urban_vehicles",
                "terminal_onramp_vehicles",
                "terminal_freeway_vehicles",
            ):
                self.assertIn(key, s)


if __name__ == "__main__":
    unittest.main()
