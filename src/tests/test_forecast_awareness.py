# 분산 follower forecast-awareness(진단 문서 2026-06-17) 검증 단위테스트
import copy
import unittest

from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.leader import Leader, LeaderAction
from src.controllers.urban_follower import UrbanFollower
from src.models.demand import DemandProfile, DemandStep, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState


def _scale_future_demand(forecast: list[DemandStep], factor: float) -> list[DemandStep]:
    """forecast[0]은 그대로 두고 미래 스텝(forecast[1:])의 모든 수요만 factor배 한다.

    현재 상태·현재 스텝 수요는 고정한 채 '미래 도착'만 바꾸므로, 결과가 변하면
    follower가 forecast[0] 외 미래 스텝을 실제로 사용한다는 증거가 된다."""
    out = [forecast[0]]
    for step in forecast[1:]:
        out.append(DemandStep(
            freeway_mainline={k: v * factor for k, v in step.freeway_mainline.items()},
            urban_boundary={k: v * factor for k, v in step.urban_boundary.items()},
            ramp_arrival={k: v * factor for k, v in step.ramp_arrival.items()},
            incident_capacity_factor=step.incident_capacity_factor,
        ))
    return out


class ForecastAwarenessTests(unittest.TestCase):
    def setUp(self):
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.net = self.cfg.network
        self.profile = DemandProfile(
            self.cfg, ScenarioConfig(name="peak", urban_scale=2.0, freeway_scale=1.5, ramp_scale=1.5)
        )
        self.forecast = self.profile.horizon(0.0, max(3, self.cfg.mpc.horizon_steps))
        self.leader = LeaderAction(N_P_star=float(self.cfg.leader.N_P_crit_veh), N_UF_star=1000.0)

    # ---------- (a) 미래 스텝을 실제로 사용 ----------
    def test_urban_green_uses_future_arrivals(self):
        """현재 큐 고정, 미래 phase 도착만 바꾸면 green이 변한다(forecast[0] 외 사용)."""
        state = TrafficState.initial(self.cfg)
        follower = UrbanFollower(self.cfg)
        low = follower.solve(
            state.copy(), self.leader, self.forecast[0],
            forecast=_scale_future_demand(self.forecast, 0.1),
        )
        high = follower.solve(
            state.copy(), self.leader, self.forecast[0],
            forecast=_scale_future_demand(self.forecast, 5.0),
        )
        # 미래 도착이 5배 다른데 green split이 같으면 forecast를 안 쓰는 것.
        self.assertNotEqual(low.green_times, high.green_times)

    def test_allocation_target_uses_future_offramp(self):
        """현재 N_P 고정, 미래 본선 수요(→off-ramp 외란)만 바꾸면 allocation target이 변한다."""
        state = TrafficState.initial(self.cfg)
        module = UrbanFollower(self.cfg).allocation_module
        low = module.solve(state.copy(), self.leader, _scale_future_demand(self.forecast, 0.1))
        high = module.solve(state.copy(), self.leader, _scale_future_demand(self.forecast, 5.0))
        self.assertNotEqual(
            low.target_net_inflow_veh_h, high.target_net_inflow_veh_h,
            "allocation target이 미래 off-ramp 외란 예측에 반응하지 않음",
        )

    def test_freeway_vsl_uses_future_offramp_inflow(self):
        """off-ramp storage를 backup시키고 미래 본선 수요만 바꾸면 VSL이 변한다."""
        state = TrafficState.initial(self.cfg)
        # off-ramp storage를 거의 가득 채워 spillback 압력을 만든다.
        for storage_link in set(self.net.off_ramp_storage_link.values()):
            cap = float(self.net.urban_link_storage_veh[storage_link])
            state.urban_link_storage[storage_link] = cap * 0.02
        coord = DistributedCoordinator(self.cfg)
        prev = ControlAction.fixed(self.cfg)
        low = coord.solve(state.copy(), self.leader, _scale_future_demand(self.forecast, 0.1), prev)
        high = coord.solve(state.copy(), self.leader, _scale_future_demand(self.forecast, 5.0), prev)
        self.assertNotEqual(
            low.control.vsl, high.control.vsl,
            "freeway VSL이 미래 off-ramp 예측 유입에 반응하지 않음",
        )

    # ---------- (b) off-ramp backup 시 VSL이 objective 최소화로 낮아짐 ----------
    def test_freeway_vsl_lower_when_offramp_backed_up(self):
        """off-ramp가 backup하면(트리거 아님, 후보 평가로) VSL이 비backup 대비 낮거나 같다."""
        coord = DistributedCoordinator(self.cfg)
        prev = ControlAction.fixed(self.cfg)
        # 큰 미래 본선 수요 → off-ramp 예측 유입 큼.
        forecast = _scale_future_demand(self.forecast, 5.0)

        empty = TrafficState.initial(self.cfg)  # off-ramp 비어 있음.
        backed = empty.copy()
        for storage_link in set(self.net.off_ramp_storage_link.values()):
            cap = float(self.net.urban_link_storage_veh[storage_link])
            backed.urban_link_storage[storage_link] = cap * 0.02  # 거의 가득.

        vsl_empty = coord.solve(empty, self.leader, forecast, prev).control.vsl
        vsl_backed = coord.solve(backed, self.leader, forecast, prev).control.vsl
        for link in self.net.freeway_links:
            self.assertLessEqual(
                vsl_backed.get(link, 0.0), vsl_empty.get(link, 0.0) + 1.0e-6,
                f"{link}: off-ramp backup인데 VSL이 비backup보다 높다(emergence 실패)",
            )
        # 적어도 한 link에서는 backup 시 VSL이 엄격히 낮아져야 emergence가 발현한 것.
        self.assertTrue(
            any(
                vsl_backed.get(link, 0.0) < vsl_empty.get(link, 0.0) - 1.0e-6
                for link in self.net.freeway_links
            ),
            "off-ramp backup에서 어떤 link도 VSL을 낮추지 않음",
        )

    # ---------- (c) leader 후보가 forecast 요약 반영 ----------
    def test_leader_candidates_reflect_forecast_summary(self):
        """미래 ramp/boundary 수요가 큰 forecast는 first-demand만 쓸 때와 다른 후보를 만든다."""
        state = TrafficState.initial(self.cfg)
        leader = Leader(self.cfg)
        prev = ControlAction.fixed(self.cfg)
        big_future = _scale_future_demand(self.forecast, 5.0)
        # first-demand만(forecast 미전달) vs horizon 요약(forecast 전달).
        first_only = leader.candidates(state.copy(), prev, self.forecast[0])
        with_forecast = leader.candidates(state.copy(), prev, self.forecast[0], forecast=big_future)
        first_nuf = sorted(a.N_UF_star for a in first_only)
        forecast_nuf = sorted(a.N_UF_star for a in with_forecast)
        self.assertNotEqual(
            first_nuf, forecast_nuf,
            "leader 후보 N_UF 집합이 forecast 요약을 반영하지 않음",
        )


if __name__ == "__main__":
    unittest.main()
