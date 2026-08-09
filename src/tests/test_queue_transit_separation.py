# v3 W-pin(2) - 정지선 대기 큐와 주행 중 차량이 서로 다른 자료구조임을 동작으로 고정한다
"""정지선에서 신호를 기다리는 차량과 링크를 주행 중인 차량은 섞이면 안 된다.

  정지선 대기  state.urban_movement_queue          - 서비스 루프가 읽는 유일한 스톡
  주행 중      링크 storage 점유(cap − available)
               + state.urban_arrival_buffer          (다음 교차로 도착 예약)
               + state.urban_storage_release_buffer  (점유 반환 예약)

분리의 근거는 `urban_substep` 의 서비스 루프(urban_queue_model.py:967-990)가
`urban_arrival_buffer` 를 **한 번도 읽지 않는다**는 것이다. 그 루프의 `available` 은
오직 `state.urban_movement_queue.get(movement)` 다. arrival buffer 는 substep 맨 앞
(:876-881)에서 도착 예정 substep 에 도달했을 때만 β분할로 큐에 주입된다.

소스 핀closure(문자열 검색)로 고정하면 리팩터링에 무의미하게 깨지므로 동작으로 고정한다.
같은 차량 수를 (A) arrival buffer 에 미래 도착으로, (B) movement 큐에 직접 넣고
같은 substep 을 돌려 서비스량을 비교한다. 둘이 갈리는 것이 곧 분리의 증거이자
되돌림 증명이다 - 두 자료구조가 합쳐져 있었다면 A 도 B 와 같은 값을 냈어야 한다.
"""

from __future__ import annotations

import unittest

from src.models import urban_queue_model as uqm
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState

SOURCE_LINK = "A_to_D"   # 내부 링크, 끝단이 교차로 D 의 N approach
INJECTED_VEH = 100.0
SERVICE_STEP = 0         # D_p1 green fraction = 1.0 인 substep (실측: k=0..10 이 1.0)
FUTURE_STEP = 10         # 아직 도착하지 않은 예약 시각


class QueueTransitSeparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.control = ControlAction.fixed(self.cfg)
        # 외생 수요 0 - 서비스량 차이가 주입한 차량에서만 나오게 한다.
        self.demand = DemandProfile(
            self.cfg,
            ScenarioConfig("separation", urban_scale=0.0, ramp_scale=0.0),
        ).at(0)
        self.targets = uqm.approach_routing(self.cfg)[SOURCE_LINK]
        self.assertTrue(self.targets)

    def _empty_state(self) -> TrafficState:
        """모든 정지선 큐가 비고 모든 링크가 빈 초기 상태."""
        state = TrafficState.initial(self.cfg)
        uqm.ensure_urban_state(state, self.cfg)
        for movement in state.urban_movement_queue:
            state.urban_movement_queue[movement] = 0.0
        for ramp in state.ramp_queue:
            state.ramp_queue[ramp] = 0.0
        return state

    def _served(self, state: TrafficState, step_idx: int = SERVICE_STEP) -> float:
        _, diagnostics = uqm.urban_substep(
            state, self.control, self.demand, self.cfg, urban_step_index=step_idx
        )
        return float(diagnostics["urban_total_departures_veh"])

    def _state_with_in_transit(self, arrival_step: int) -> TrafficState:
        state = self._empty_state()
        state.urban_arrival_buffer[SOURCE_LINK] = {arrival_step: INJECTED_VEH}
        return state

    def _state_with_stop_line_queue(self) -> TrafficState:
        state = self._empty_state()
        for movement, beta in self.targets:
            state.urban_movement_queue[movement] = beta * INJECTED_VEH
        return state

    def test_baseline_has_nothing_to_serve(self) -> None:
        """주입 없이는 서비스량이 0 - 아래 비교의 기준선을 먼저 고정한다."""
        self.assertEqual(self._served(self._empty_state()), 0.0)

    def test_in_transit_vehicles_are_not_served_at_the_stop_line(self) -> None:
        """주행 중(arrival buffer) 차량은 서비스 루프가 건드리지 않는다."""
        state = self._state_with_in_transit(FUTURE_STEP)
        served = self._served(state)
        self.assertEqual(served, 0.0, f"주행 중인 차량이 서비스됐다: {served} veh")
        # 정지선 큐에도 옮겨지지 않아야 한다(도착 substep 이 아직 아니다).
        for movement, _ in self.targets:
            self.assertEqual(state.urban_movement_queue[movement], 0.0, movement)
        # 차량은 사라지지 않고 예약에 그대로 남아 있다.
        self.assertAlmostEqual(
            state.urban_arrival_buffer[SOURCE_LINK].get(FUTURE_STEP, 0.0),
            INJECTED_VEH,
            places=9,
        )

    def test_same_vehicles_in_the_stop_line_queue_are_served(self) -> None:
        """되돌림 증명 - 같은 차량을 정지선 큐에 두면 같은 substep 에 서비스된다.

        두 자료구조가 합쳐져 있었다면 위 테스트도 이 값을 냈어야 한다.
        """
        served = self._served(self._state_with_stop_line_queue())
        self.assertGreater(served, 0.0, "정지선 큐에 넣었는데도 서비스가 0 이다")

    def test_arrival_step_is_the_only_gate_between_the_two(self) -> None:
        """도착 substep 이 되면 buffer→큐 주입 후 같은 substep 에 서비스된다.

        예약 시각만 바꾼 것이므로 서비스량은 정지선 큐 직접 주입과 정확히 같아야 한다.
        `_pop_buffer` 가 서비스 루프보다 먼저 돌기 때문이다(:877 vs :967).
        """
        arrived_now = self._served(self._state_with_in_transit(SERVICE_STEP))
        stop_line = self._served(self._state_with_stop_line_queue())
        self.assertGreater(arrived_now, 0.0)
        self.assertAlmostEqual(arrived_now, stop_line, places=9)


if __name__ == "__main__":
    unittest.main()
