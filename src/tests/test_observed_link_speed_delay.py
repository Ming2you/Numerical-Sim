# v3 N3-1b - 관측 링크속도를 링크 주행지연에 싣되 0 속도가 링크를 얼리지 않음을 고정한다
"""`_link_delay_steps` 는 지금 전역 상수 `urban_avg_speed_km_h` 만 쓴다.

계획 원문은 "관측 속도가 있으면 전역 평균속도를 쓰지 않는다. **0 속도는 0 지체가
아니다.**" 다. 관측 속도를 그대로 분모에 꽂으면 함정이 있다.

  delay[substep] = max(1, ceil(available · L_veh/1000 / v_obs / T_u))

VBS 가 내보내는 링크 속도는 `speed_sum / count` 라 **표본이 없는 링크(count=0)에서
0** 이다. 정체라서 0 인 게 아니라 관측이 없어서 0 이다. 그 0 을 `max(v, 1e-9)` 로만
막으면 delay 가 약 1e12 substep 이 되고, `_pop_buffer` 는 정확일치 pop 이라
(urban_queue_model.py:476-478) 그 예약은 사실상 영원히 꺼내지지 않는다. 차량과
링크 저류 공간이 **함께** 영구 격리된다.

그래서 관측 속도에는 하한을 둔다 — 자유류의 1/`OBSERVED_SPEED_DELAY_CAP_RATIO`.
지연 상한이 자유류 지연의 `OBSERVED_SPEED_DELAY_CAP_RATIO` 배로 유한하게 묶인다.

되돌림 증명 두 갈래.
  A. 하한 비율을 무한대로 키워(=하한 제거) delay 가 폭발하는 것을 보인다.
  B. 하한을 뺀 산식을 테스트 안에서 직접 재현해 같은 폭발을 보인다.

관측이 없을 때(빈 dict)는 기존과 **비트 동일**해야 한다 — 이것도 못 박는다.
"""

from __future__ import annotations

import math
import unittest
from unittest import mock

from src.models import urban_queue_model as uqm
from src.models.demand import DemandProfile, load_scenarios
from src.models.state import ControlAction, ExperimentConfig, TrafficState

SUBSTEPS = 3
SCENARIO = "urban_gridlock"


def _constant_speed_delay_steps(state: TrafficState, cfg: ExperimentConfig, link: str) -> int:
    """관측 속도를 모르던 시절의 원본 산식 재현 (urban_queue_model.py:592-597)."""
    net = cfg.network
    capacity = net.urban_link_storage_veh.get(link, net.boundary_queue_max_veh)
    available = max(0.0, state.urban_link_storage.get(link, capacity))
    distance_km = available * net.urban_avg_vehicle_length_m / 1000.0
    travel_time_h = distance_km / max(net.urban_avg_speed_km_h, 1.0e-9)
    return max(1, int(math.ceil(travel_time_h / max(cfg.simulation.T_u_h, 1.0e-9))))


def _unfloored_observed_delay_steps(
    state: TrafficState, cfg: ExperimentConfig, link: str, observed_kph: float
) -> int:
    """되돌림 증명 B - 하한 없이 관측 속도를 그대로 꽂은 산식."""
    net = cfg.network
    capacity = net.urban_link_storage_veh.get(link, net.boundary_queue_max_veh)
    available = max(0.0, state.urban_link_storage.get(link, capacity))
    distance_km = available * net.urban_avg_vehicle_length_m / 1000.0
    travel_time_h = distance_km / max(observed_kph, 1.0e-9)
    return max(1, int(math.ceil(travel_time_h / max(cfg.simulation.T_u_h, 1.0e-9))))


class ObservedLinkSpeedDelayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.net = self.cfg.network
        self.scenarios = load_scenarios("src/config/scenarios.yaml")

    def _loaded_state(self) -> TrafficState:
        state = TrafficState.initial(self.cfg)
        uqm.ensure_urban_state(state, self.cfg)
        return state

    def _biggest_link(self) -> str:
        return max(self.net.urban_link_storage_veh, key=self.net.urban_link_storage_veh.get)

    def _max_constant_delay(self) -> int:
        state = self._loaded_state()
        return max(
            uqm._link_delay_steps(state, self.cfg, link)
            for link in self.net.urban_link_storage_veh
        )

    def _latest_scheduled_step(self, state: TrafficState) -> int:
        """`_link_delay_steps` 가 정하는 두 버퍼의 가장 먼 도착 substep."""
        latest = 0
        for name in ("urban_arrival_buffer", "urban_storage_release_buffer"):
            for schedule in getattr(state, name).values():
                for arrival_step, vehicles in schedule.items():
                    if vehicles > 0.0:
                        latest = max(latest, int(arrival_step))
        return latest

    def test_zero_observed_speed_does_not_freeze_link(self) -> None:
        """0 속도 함정 - 관측 0 이어도 지연이 유한 상한 안이고 버퍼가 유한 step 에 열린다."""
        state = self._loaded_state()
        speeds = getattr(state, "urban_link_speed_kph", None)
        self.assertIsNotNone(
            speeds,
            "TrafficState 에 링크별 관측 속도 필드 `urban_link_speed_kph` 가 없다",
        )

        cap_ratio = uqm.OBSERVED_SPEED_DELAY_CAP_RATIO
        link = self._biggest_link()
        baseline = uqm._link_delay_steps(state, self.cfg, link)
        bound = int(math.ceil(cap_ratio * self._max_constant_delay()))

        for storage_link in self.net.urban_link_storage_veh:
            speeds[storage_link] = 0.0

        observed_delay = uqm._link_delay_steps(state, self.cfg, link)
        self.assertLessEqual(
            observed_delay,
            int(math.ceil(cap_ratio * baseline)),
            f"{link}: 관측 0 에서 지연 {observed_delay} substep - 자유류({baseline})의 "
            f"{cap_ratio}배 상한을 넘었다",
        )

        control = ControlAction.fixed(self.cfg)
        demand = DemandProfile(self.cfg, self.scenarios[SCENARIO]).at(0)
        for step_idx in range(SUBSTEPS):
            uqm.urban_substep(state, control, demand, self.cfg, urban_step_index=step_idx)
        latest = self._latest_scheduled_step(state)
        self.assertGreater(latest, 0, "예약이 하나도 안 생겼다 - 시나리오/설정을 확인하라")
        self.assertLessEqual(
            latest,
            SUBSTEPS + bound,
            f"관측 0 인데 가장 먼 도착 예약이 substep {latest} 다 - 상한 {SUBSTEPS + bound} 초과, "
            "버퍼가 유한 step 에 열리지 않는다",
        )

    def test_observed_speed_is_actually_used(self) -> None:
        """관측 속도가 자유류의 절반이면 지연이 대략 두 배가 된다(무시되면 그대로다)."""
        state = self._loaded_state()
        link = self._biggest_link()
        baseline = uqm._link_delay_steps(state, self.cfg, link)
        state.urban_link_speed_kph[link] = self.net.urban_avg_speed_km_h / 2.0
        halved = uqm._link_delay_steps(state, self.cfg, link)
        self.assertGreaterEqual(
            halved,
            2 * baseline - 1,
            f"{link}: 관측 속도 절반인데 지연이 {halved} substep 이다(자유류 {baseline}) - "
            "관측이 산식에 안 들어갔다",
        )

    def test_observed_speed_applies_only_to_the_observed_link(self) -> None:
        """관측이 없는 링크는 전역 상수 그대로다 - dict 하나가 전 링크를 덮지 않는다."""
        state = self._loaded_state()
        observed = self._biggest_link()
        others = [link for link in self.net.urban_link_storage_veh if link != observed]
        before = {link: uqm._link_delay_steps(state, self.cfg, link) for link in others}
        state.urban_link_speed_kph[observed] = 1.0
        for link in others:
            self.assertEqual(
                uqm._link_delay_steps(state, self.cfg, link),
                before[link],
                f"{link}: 관측이 없는 링크의 지연이 바뀌었다",
            )

    def test_no_observation_reproduces_the_constant_speed_formula(self) -> None:
        """관측이 비면 기존 산식과 비트 동일 - 저류 잔량을 훑어 전 링크에서 확인한다."""
        state = self._loaded_state()
        self.assertEqual(state.urban_link_speed_kph, {}, "초기 상태에 관측 속도가 들어 있다")
        for fraction in (0.0, 0.13, 0.5, 0.87, 1.0):
            for link, capacity in self.net.urban_link_storage_veh.items():
                state.urban_link_storage[link] = float(capacity) * fraction
            for link in self.net.urban_link_storage_veh:
                self.assertEqual(
                    uqm._link_delay_steps(state, self.cfg, link),
                    _constant_speed_delay_steps(state, self.cfg, link),
                    f"{link}(fraction={fraction}): 관측이 없는데 기존 산식과 값이 다르다",
                )

    def test_removing_the_floor_explodes_the_delay(self) -> None:
        """되돌림 증명 A - 하한 비율을 키워 하한을 사실상 없애면 지연이 폭발한다."""
        state = self._loaded_state()
        link = self._biggest_link()
        state.urban_link_speed_kph[link] = 0.0
        with mock.patch.object(uqm, "OBSERVED_SPEED_DELAY_CAP_RATIO", 1.0e18):
            exploded = uqm._link_delay_steps(state, self.cfg, link)
        self.assertGreater(
            exploded,
            1_000_000,
            f"{link}: 하한을 없앴는데 지연이 {exploded} substep 밖에 안 된다 - "
            "하한이 산식 밖에서 걸려 있는지 확인하라",
        )

    def test_unfloored_formula_strands_the_link(self) -> None:
        """되돌림 증명 B - 하한 없는 산식 재현이 같은 폭발을 보인다(재현식 정합 확인)."""
        state = self._loaded_state()
        link = self._biggest_link()
        self.assertGreater(
            _unfloored_observed_delay_steps(state, self.cfg, link, 0.0),
            1_000_000,
            "재현식이 원본과 어긋났다",
        )
        self.assertEqual(
            _unfloored_observed_delay_steps(
                state, self.cfg, link, self.net.urban_avg_speed_km_h
            ),
            _constant_speed_delay_steps(state, self.cfg, link),
            "재현식이 자유류 속도에서 원본과 값이 다르다",
        )


if __name__ == "__main__":
    unittest.main()
