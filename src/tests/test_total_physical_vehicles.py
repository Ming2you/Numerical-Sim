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


if __name__ == "__main__":
    unittest.main()
