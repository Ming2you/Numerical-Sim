# v3 W-pin(1) - 링크 주행 지연의 구조적 하한(1 substep)을 회귀로 고정한다
"""`_link_delay_steps` 의 `max(1, ...)` 가 없어지면 차량이 영구히 갇힌다.

`urban_substep` 은 substep k 의 맨 앞에서 `_pop_buffer(..., k)` 로 그 substep 도착분을
꺼내고(urban_queue_model.py:844, 877), 그 아래 서비스 루프에서 새 도착을 `k + delay`
에 예약한다(:1006-1011). 그래서 `delay == 0` 이면 예약 키가 **이미 pop 이 끝난 k** 가
되어 다시는 꺼내지지 않는다. urban_arrival_buffer 쪽이면 그 차량은 영원히 movement
큐에 도달하지 못하고, urban_storage_release_buffer 쪽이면 링크 점유가 영원히
복원되지 않는다. 질량은 남지만 그 차량은 무한 지연에 갇힌다.

delay 는 `available` 에만 의존하고 `available == 0` 일 때만 0 이 될 수 있다
(`ceil(x) == 0` 은 `x <= 0` 에서만 성립). 실측으로 sweet_115 / urban_gridlock /
sweet_220 을 24 control step 돌리는 동안 `_link_delay_steps` 가 본 `available` 의
최소값은 178.19 veh 였다 - 즉 이 클램프는 지금 한 번도 발동하지 않는 "구조적 하한"
이고, 회귀로 못 박아 두지 않으면 아무 테스트도 깨뜨리지 않은 채 사라질 수 있다.

되돌림 증명은 두 갈래로 둔다.
  A. 클램프 없는 산식을 테스트 안에서 직접 재현해 available=0 링크에서 0 이 나옴을 보인다.
  B. 그 0 을 실제 주입하면 버퍼 엔트리가 stranded 되는 것을 동작으로 보인다.
"""

from __future__ import annotations

import math
import unittest
from unittest import mock

from src.models import urban_queue_model as uqm
from src.models.demand import DemandProfile, load_scenarios
from src.models.state import ControlAction, ExperimentConfig, TrafficState

SUBSTEPS = 40


def _unclamped_delay_steps(state: TrafficState, cfg: ExperimentConfig, link: str) -> int:
    """`max(1, ...)` 만 뺀 `_link_delay_steps` 재현 (urban_queue_model.py:524-529)."""
    net = cfg.network
    capacity = net.urban_link_storage_veh.get(link, net.boundary_queue_max_veh)
    available = max(0.0, state.urban_link_storage.get(link, capacity))
    distance_km = available * net.urban_avg_vehicle_length_m / 1000.0
    travel_time_h = distance_km / max(net.urban_avg_speed_km_h, 1.0e-9)
    return int(math.ceil(travel_time_h / max(cfg.simulation.T_u_h, 1.0e-9)))


class LinkTransitDelayFloorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.net = self.cfg.network
        self.scenarios = load_scenarios("src/config/scenarios.yaml")

    def _loaded_state(self) -> TrafficState:
        state = TrafficState.initial(self.cfg)
        uqm.ensure_urban_state(state, self.cfg)
        return state

    def _stale_entries(self, state: TrafficState, step_idx: int) -> list[tuple[str, str, int, float]]:
        """현재 substep 이하 키에 남아 있는 예약 = 다시는 pop 되지 않는 stranded 엔트리."""
        stale = []
        for name in ("urban_arrival_buffer", "urban_storage_release_buffer"):
            for key, schedule in getattr(state, name).items():
                for arrival_step, vehicles in schedule.items():
                    if arrival_step <= step_idx and vehicles > 0.0:
                        stale.append((name, key, arrival_step, vehicles))
        return stale

    def _run(self, state: TrafficState, steps: int = SUBSTEPS) -> list[int]:
        control = ControlAction.fixed(self.cfg)
        demand = DemandProfile(self.cfg, self.scenarios["urban_gridlock"]).at(0)
        stale_counts = []
        for step_idx in range(steps):
            uqm.urban_substep(state, control, demand, self.cfg, urban_step_index=step_idx)
            stale_counts.append(len(self._stale_entries(state, step_idx)))
        return stale_counts

    def test_full_link_still_costs_one_substep(self) -> None:
        """available=0(꽉 찬 링크)에서도 지연은 최소 1 substep 이다."""
        state = self._loaded_state()
        for link in self.net.urban_link_storage_veh:
            state.urban_link_storage[link] = 0.0
        for link in self.net.urban_link_storage_veh:
            self.assertGreaterEqual(
                uqm._link_delay_steps(state, self.cfg, link),
                1,
                f"{link}: 꽉 찬 링크의 주행 지연이 0 substep 이다",
            )

    def test_delay_is_not_a_constant_floor(self) -> None:
        """하한만 남고 실제 주행시간이 사라지면 위 테스트는 `return 1` 로도 통과한다."""
        state = self._loaded_state()  # 초기 storage = 용량 전량(빈 링크)
        biggest = max(self.net.urban_link_storage_veh, key=self.net.urban_link_storage_veh.get)
        self.assertGreater(
            uqm._link_delay_steps(state, self.cfg, biggest),
            1,
            f"{biggest}: 빈 링크인데 지연이 하한(1) 그대로다",
        )

    def test_no_arrival_is_ever_scheduled_into_an_already_popped_substep(self) -> None:
        """동작 핀 - 어떤 substep 에서도 '지금 이하' 키로 예약이 생기지 않는다."""
        stale_counts = self._run(self._loaded_state())
        self.assertEqual(
            max(stale_counts),
            0,
            f"stranded 예약이 생겼다: substep별 개수 {stale_counts}",
        )

    def test_unclamped_formula_returns_zero_on_a_full_link(self) -> None:
        """되돌림 증명 A - 클램프를 뺀 산식은 available=0 에서 0 을 돌려준다."""
        state = self._loaded_state()
        for link in self.net.urban_link_storage_veh:
            state.urban_link_storage[link] = 0.0
        for link in self.net.urban_link_storage_veh:
            self.assertEqual(
                _unclamped_delay_steps(state, self.cfg, link),
                0,
                f"{link}: 클램프 없는 산식이 0 이 아니다 - 재현식이 원본과 어긋났다",
            )

    def test_zero_delay_strands_vehicles_forever(self) -> None:
        """되돌림 증명 B - 지연 0 을 주입하면 stranded 예약이 매 substep 누적된다."""
        state = self._loaded_state()
        with mock.patch.object(uqm, "_link_delay_steps", lambda state, cfg, link: 0):
            stale_counts = self._run(state)
        self.assertGreater(
            stale_counts[-1],
            0,
            "지연 0 인데 stranded 예약이 하나도 없다 - pop/schedule 순서가 바뀌었는지 확인하라",
        )
        # 한 번 갇히면 회수 경로가 없으므로 단조 증가해야 한다.
        self.assertGreater(stale_counts[-1], stale_counts[len(stale_counts) // 2])


if __name__ == "__main__":
    unittest.main()
