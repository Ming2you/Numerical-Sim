# v3 N2 - 단일 total_physical_vehicles(). 질량 회계가 한 곳에서만 나오도록 고정한다
"""`TrafficState.total_physical_vehicles()` 가 네트워크의 모든 차량을 한 번씩만 센다.

지금은 총량이 `total_urban_vehicles` 와 `total_freeway_vehicles` 로 갈라져 있고, 호출자가
둘을 어떻게 합치는지에 따라 결과가 달라진다. v3 N2 는 substep 질량 장부의 전역 항등식
`N_close = N_open + accepted_external - sink_out` 을 요구하는데, 그 `N` 이 단일 정의여야
항등식이 의미를 가진다.
"""

from __future__ import annotations

import unittest

from src.models.state import ExperimentConfig, TrafficState


class TotalPhysicalVehiclesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.net = self.cfg.network
        self.state = TrafficState.initial(self.cfg)

    def test_counts_urban_and_freeway_including_ramp_and_origin_queues(self) -> None:
        expected = self.state.total_urban_vehicles(self.net) + self.state.total_freeway_vehicles(
            self.net
        )
        self.assertAlmostEqual(
            self.state.total_physical_vehicles(self.net), expected, places=9
        )

    def test_added_ramp_and_origin_queue_vehicles_are_counted_once(self) -> None:
        before = self.state.total_physical_vehicles(self.net)
        ramp = next(iter(self.state.ramp_queue))
        origin = next(iter(self.state.mainline_origin_queue))
        self.state.ramp_queue[ramp] += 3.0
        self.state.mainline_origin_queue[origin] += 5.0

        # 램프와 본선 원점 큐도 물리 차량이다. 빠지면 전역 항등식이 성립하지 않는다.
        self.assertAlmostEqual(
            self.state.total_physical_vehicles(self.net), before + 8.0, places=9
        )

    def test_off_ramp_storage_occupancy_is_counted(self) -> None:
        """off-ramp 램프 storage 점유는 어느 쪽도 세지 않아 통째로 사라진다.

        `total_urban_vehicles` 는 "freeway 로 재귀속" 을 이유로 `OR_*_storage` 를 빼는데
        (state.py:1032-1038), `total_freeway_vehicles` 는 그것을 더하지 않는다
        (state.py:1011-1016). 두 함수의 합만 쓰면 그 차량들이 어느 계정에도 없다.
        """
        storage_links = sorted(set(self.net.off_ramp_storage_link.values()))
        self.assertTrue(storage_links, "off-ramp storage link 이 없으면 이 테스트는 무의미하다")

        before = self.state.total_physical_vehicles(self.net)
        # available 을 줄이는 것이 점유를 늘리는 방법이다(점유 = capacity − available).
        for link in storage_links:
            capacity = self.net.urban_link_storage_veh[link]
            self.state.urban_link_storage[link] = capacity - 7.0
        expected_occupancy = 7.0 * len(storage_links)

        self.assertAlmostEqual(
            self.state.off_ramp_storage_occupancy_veh(self.net),
            expected_occupancy,
            places=9,
        )
        self.assertAlmostEqual(
            self.state.total_physical_vehicles(self.net),
            before + expected_occupancy,
            places=9,
        )

    def test_decomposition_identity_holds_after_stepping(self) -> None:
        """물리 stock 을 전부 직접 더한 값과 일치해야 한다 — 초기상태가 아니라 전진 후에.

        초기상태는 거의 모든 stock 이 0 이라 어떤 누락도 드러나지 않는다. 실제로
        `off_ramp_storage` 누락은 스텝을 밟아야 보인다.

        `urban_arrival_buffer` 와 `urban_storage_release_buffer` 는 **여기에 더하지 않는다**.
        둘은 stock 이 아니라 일정표다 — 링크에 진입한 차량은 storage 점유로 한 번 계상되고
        같은 양이 두 버퍼에 예약된다(urban_queue_model.py:1001-1011). 실측으로 내부 링크에서
        점유와 release buffer 가 소수점까지 일치함을 확인했다(각 251.0444 veh).
        """
        from src.models.demand import DemandProfile, load_scenarios
        from src.models.state import ControlAction
        from src.simulation.simulator import MixedTrafficSimulator

        scenarios = load_scenarios("src/config/scenarios.yaml")
        profile = DemandProfile(self.cfg, scenarios[next(iter(scenarios))])
        sim = MixedTrafficSimulator(self.cfg)
        control = ControlAction.uncontrolled(self.cfg)
        for step in range(4):
            sim.step(control, profile.at(step), step)
        state = sim.state

        occupancy = sum(
            max(0.0, capacity - state.urban_link_storage.get(link, capacity))
            for link, capacity in self.net.urban_link_storage_veh.items()
        )
        expected = (
            state.freeway_segment_vehicles(self.net)
            + sum(state.ramp_queue.values())
            + sum(state.mainline_origin_queue.values())
            + sum(state.urban_movement_queue.values())
            + occupancy
        )

        self.assertGreater(occupancy, 0.0, "전진 후에도 점유가 0 이면 시나리오가 잘못됐다")
        self.assertAlmostEqual(
            state.total_physical_vehicles(self.net), expected, places=6
        )


if __name__ == "__main__":
    unittest.main()
