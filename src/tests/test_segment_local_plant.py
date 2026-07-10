# 13-player segment agent 국소 plant 검증 — link 전진과의 비트 일치·소유 매핑·결합 반응성
import unittest

from src.controllers.local_freeway_plant import (
    build_local_freeway_model,
    freeway_substep_local,
)
from src.controllers.segment_local_plant import (
    FrozenLinkTrajectory,
    SegmentLocalState,
    build_segment_agent_models,
    frozen_trajectory_from_state,
    segment_substep_local,
)
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState

CONFIG_PATH = "src/config/default.yaml"


def _cfg() -> ExperimentConfig:
    return ExperimentConfig.from_file(CONFIG_PATH, {})


def _demand(link: str = "FW_W") -> DemandStep:
    return DemandStep(
        freeway_mainline={link: 1500.0},
        urban_boundary={},
        ramp_arrival={},
    )


def _run_link_forward(cfg, link, control, demand, substeps):
    """link stepper를 substeps번 전진 — 매 substep의 (입력 스냅샷, 출력)을 기록.

    occupancy는 호출자 규약대로 offramp_flow 유입 − drain 유출로 갱신(고정 drain 300 veh/h).
    """
    model = build_local_freeway_model(cfg, link)
    net = cfg.network
    dt_h = cfg.simulation.T_f_h
    n = model.n_seg
    rhos = [30.0, 45.0, 60.0, 90.0][:n]
    speeds = [80.0, 65.0, 50.0, 25.0][:n]
    prev_lanes = [float(net.freeway_lanes)] * n
    origin_q = 12.0
    # capacity-drop 영역에 들어가도록 60% 점유에서 시작.
    occupancy = {o: 0.6 * model.offramp_storage_cap.get(o, 0.0) for o in model.owned_offramps}
    releases = {r: 800.0 for r in model.owned_ramps}
    caps = {o: 400.0 for o in model.owned_offramps}
    drain = 300.0

    inputs, outputs = [], []
    for _ in range(substeps):
        inputs.append(
            dict(
                rhos=list(rhos), speeds=list(speeds), prev_lanes=list(prev_lanes),
                origin_q=float(origin_q), occupancy=dict(occupancy),
                releases=dict(releases), caps=dict(caps),
            )
        )
        rhos, speeds, prev_lanes, origin_q, off_flow, veh = freeway_substep_local(
            model, rhos, speeds, prev_lanes, occupancy, origin_q, releases, caps,
            control, demand,
        )
        outputs.append(dict(rhos=list(rhos), speeds=list(speeds), origin_q=float(origin_q),
                            off_flow=dict(off_flow), veh=list(veh)))
        for o in model.owned_offramps:
            cap_v = model.offramp_storage_cap.get(o, 0.0)
            occ_new = occupancy[o] + dt_h * (off_flow.get(o, 0.0) - drain)
            occupancy[o] = min(max(occ_new, 0.0), cap_v)
    return model, inputs, outputs


class TestSegmentAgentMapping(unittest.TestCase):
    def test_13_player_ownership(self):
        # 승인 매핑: F_L2=R_D(merge seg2), F_L3=R_F(merge seg3), seg0=origin queue,
        # off-ramp 유출 경계는 seg1(OR_D)·seg2(OR_F). 총 agent 수 = 5 urban + 8 seg = 13.
        cfg = _cfg()
        agents_w = build_segment_agent_models(cfg, "FW_W")
        agents_e = build_segment_agent_models(cfg, "FW_E")
        self.assertEqual(len(agents_w), 4)
        self.assertEqual(
            len(cfg.network.signals) + len(agents_w) + len(agents_e), 13,
        )
        self.assertEqual(agents_w[0].owned_ramps, [])
        self.assertTrue(agents_w[0].owns_origin_queue)
        self.assertEqual(agents_w[1].owned_ramps, [])
        self.assertEqual(agents_w[2].owned_ramps, ["R_D_W"])
        self.assertEqual(agents_w[3].owned_ramps, ["R_F_W"])
        self.assertEqual(agents_w[1].boundary_offramps, ["OR_D_W"])
        self.assertEqual(agents_w[2].boundary_offramps, ["OR_F_W"])
        self.assertEqual(agents_e[2].owned_ramps, ["R_D_E"])
        self.assertEqual(agents_e[3].owned_ramps, ["R_F_E"])


class TestSegmentLocalExactness(unittest.TestCase):
    """참 이웃 궤적(y)을 동결 입력으로 주면 segment-local 전진이 link 전진과 비트 일치."""

    def test_matches_link_forward_bitwise(self):
        cfg = _cfg()
        link = "FW_W"
        control = ControlAction.uncontrolled(cfg)
        demand = _demand(link)
        substeps = 20
        model, inputs, outputs = _run_link_forward(cfg, link, control, demand, substeps)

        frozen = FrozenLinkTrajectory(
            rhos=[inp["rhos"] for inp in inputs],
            speeds=[inp["speeds"] for inp in inputs],
            prev_lanes=[inp["prev_lanes"] for inp in inputs],
            origin_queue=[inp["origin_q"] for inp in inputs],
            ramp_release=[inp["releases"] for inp in inputs],
            occupancy=[inp["occupancy"] for inp in inputs],
            offramp_capacity=[inp["caps"] for inp in inputs],
        )
        for agent in build_segment_agent_models(cfg, link):
            own = SegmentLocalState(
                rho=inputs[0]["rhos"][agent.seg],
                speed=inputs[0]["speeds"][agent.seg],
                prev_lane=inputs[0]["prev_lanes"][agent.seg],
                origin_queue=inputs[0]["origin_q"],
            )
            for t in range(substeps):
                own, off_flow, veh = segment_substep_local(
                    agent, frozen, t, own,
                    inputs[t]["releases"], control, demand,
                )
                self.assertAlmostEqual(
                    own.rho, outputs[t]["rhos"][agent.seg], places=9,
                    msg=f"seg{agent.seg} rho @t={t}",
                )
                self.assertAlmostEqual(
                    own.speed, outputs[t]["speeds"][agent.seg], places=9,
                    msg=f"seg{agent.seg} speed @t={t}",
                )
                self.assertAlmostEqual(veh, outputs[t]["veh"][agent.seg], places=9)
                if agent.owns_origin_queue:
                    self.assertAlmostEqual(own.origin_queue, outputs[t]["origin_q"], places=9)
                for o in agent.boundary_offramps:
                    self.assertAlmostEqual(
                        off_flow[o], outputs[t]["off_flow"][o], places=9,
                    )


class TestSegmentCouplingResponsiveness(unittest.TestCase):
    """결합변수가 살아있는지 — 동결 y·자기 lever 변화가 자기 seg 전진에 반영돼야 한다."""

    def _base(self):
        cfg = _cfg()
        link = "FW_W"
        control = ControlAction.uncontrolled(cfg)
        demand = _demand(link)
        agents = build_segment_agent_models(cfg, link)
        # 하류(seg3)를 rho_max 근처로 — receiving이 병목이 되는 영역.
        state_arrays = dict(
            rhos=[30.0, 45.0, 40.0, 90.0], speeds=[80.0, 65.0, 60.0, 20.0],
            lanes=[float(cfg.network.freeway_lanes)] * 4,
        )
        return cfg, link, control, demand, agents, state_arrays

    def _frozen(self, cfg, arrays, releases):
        return FrozenLinkTrajectory(
            rhos=[list(arrays["rhos"])],
            speeds=[list(arrays["speeds"])],
            prev_lanes=[list(arrays["lanes"])],
            origin_queue=[0.0],
            ramp_release=[dict(releases)],
            occupancy=[{}],
            offramp_capacity=[{}],
        )

    def test_neighbor_ramp_release_in_y_moves_own_outflow(self):
        # F_L2(seg2)의 q_out은 하류 receiving에서 F_L3의 R_F 방류를 차감 — 이웃 lever가
        # y를 통해 자기 전진을 바꿔야 결합이 실체다(동결이어도 iteration 간 전파의 기반).
        cfg, link, control, demand, agents, arrays = self._base()
        seg2 = agents[2]
        own = SegmentLocalState(rho=arrays["rhos"][2], speed=arrays["speeds"][2],
                                prev_lane=arrays["lanes"][2])
        results = []
        for rf_release in (0.0, 1200.0):
            frozen = self._frozen(cfg, arrays, {"R_D_W": 0.0, "R_F_W": rf_release})
            nxt, _, _ = segment_substep_local(
                seg2, frozen, 0, own, {"R_D_W": 0.0}, control, demand,
            )
            results.append(nxt.rho)
        # R_F 방류가 크면 seg3 receiving이 줄어 seg2 유출이 막힘 → seg2 밀도 상승.
        self.assertGreater(results[1], results[0] + 1.0e-6)

    def test_own_metering_moves_own_state_when_uncongested(self):
        # 비혼잡(receiving 여유) 영역: F_L3의 자기 lever(R_F 방류)가 자기 밀도에 직접 반영.
        cfg, link, control, demand, agents, arrays = self._base()
        arrays["rhos"][3], arrays["speeds"][3] = 40.0, 60.0
        seg3 = agents[3]
        own = SegmentLocalState(rho=arrays["rhos"][3], speed=arrays["speeds"][3],
                                prev_lane=arrays["lanes"][3])
        frozen = self._frozen(cfg, arrays, {"R_D_W": 0.0, "R_F_W": 0.0})
        rho_by_release = []
        for release in (0.0, 1200.0):
            nxt, _, _ = segment_substep_local(
                seg3, frozen, 0, own, {"R_F_W": release}, control, demand,
            )
            rho_by_release.append(nxt.rho)
        self.assertGreater(rho_by_release[1], rho_by_release[0] + 1.0e-6)

    def test_own_metering_displaced_when_receiving_bound(self):
        # 혼잡(receiving 병목) 영역의 보존식 물리: 자기 방류가 본선 유입을 1:1로 밀어내
        # 자기 seg 총유입은 receiving에 포화 → **자기 밀도는 거의 불변**. metering의 이득은
        # 상류 seg 유출 개방으로 넘어간다(cross-agent externality) — 13-player에서 이 배분을
        # 교정하는 장치가 예산 equality + g_ext 가격(plan-13player-rebuild.md 리스크 2 근거).
        cfg, link, control, demand, agents, arrays = self._base()
        seg3 = agents[3]
        own = SegmentLocalState(rho=arrays["rhos"][3], speed=arrays["speeds"][3],
                                prev_lane=arrays["lanes"][3])
        frozen = self._frozen(cfg, arrays, {"R_D_W": 0.0, "R_F_W": 0.0})
        rho_by_release = []
        for release in (0.0, 1200.0):
            nxt, _, _ = segment_substep_local(
                seg3, frozen, 0, own, {"R_F_W": release}, control, demand,
            )
            rho_by_release.append(nxt.rho)
        self.assertAlmostEqual(rho_by_release[1], rho_by_release[0], delta=0.01)


class TestFrozenWarmStart(unittest.TestCase):
    def test_hold_constant_from_state(self):
        cfg = _cfg()
        state = TrafficState.initial(cfg)
        control = ControlAction.uncontrolled(cfg)
        frozen = frozen_trajectory_from_state(cfg, "FW_W", state, control, 6)
        self.assertEqual(len(frozen.rhos), 6)
        # hold-last: horizon 밖 t도 마지막 값.
        self.assertEqual(frozen.at(99)[0], frozen.at(5)[0])
        self.assertIn("R_D_W", frozen.ramp_release[0])
        self.assertIn("R_F_W", frozen.ramp_release[0])


if __name__ == "__main__":
    unittest.main()
