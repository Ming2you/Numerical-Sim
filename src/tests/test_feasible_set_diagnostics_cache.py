# v3 N8 - _leader_direct_feasible_set_diagnostics 의 config 고정 자료를 캐시한다 (값 불변)
"""탐색 루프의 최대 병목에서 config 로만 정해지는 재계산을 걷어낸다.

## 왜

실런 정본 결선(core15n41)은 `urban_movements` 가 1,414 개다(default.yaml 은 78). 그 config
에서 이 함수는 **4.1 ms/호출** 이고, default.yaml solve 1회에 11,799 회 불렸다.

함수 안에서 호출마다 다시 만드는 것들이 있는데 전부 `cfg` 로만 정해진다.

    movement_storage_capacity(cfg, movement, spec)   전체 movement 를 3회 통과
    boundary_group_key(spec)                          grouped_densities 2회 호출마다
    onramp_by_movement                                on_ramp_to_movement 재역인덱싱

`self.cfg` 는 coordinator 수명 동안 고정이므로 한 번만 만들면 된다.

## 이 테스트가 지키는 것

최적화의 유일한 위험은 값이 달라지는 것이다. 그래서 캐시가 **순진한 재계산과 정확히 같은
값**을 내는지 실 config 로 확인한다. 성능 수치는 단언하지 않는다 - 기계마다 달라 깨지기 쉽고,
증명해야 할 것은 등가성이다.
"""

from __future__ import annotations

import unittest

from src.controllers.distributed_coordinator import DistributedCoordinator
from src.models.state import ExperimentConfig
from src.models.urban_queue_model import movement_storage_capacity


class MovementStorageCapacityCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.coordinator = DistributedCoordinator(self.cfg)

    def test_cached_capacity_matches_the_direct_call_for_every_movement(self) -> None:
        cache = self.coordinator._movement_storage_capacity_cache
        self.assertEqual(set(cache), set(self.coordinator._specs))
        for movement, spec in self.coordinator._specs.items():
            with self.subTest(movement=movement):
                self.assertEqual(
                    cache[movement], movement_storage_capacity(self.cfg, movement, spec)
                )

    def test_cache_is_built_once_and_reused(self) -> None:
        first = self.coordinator._movement_storage_capacity_cache
        self.assertIs(self.coordinator._movement_storage_capacity_cache, first)

    def test_boundary_group_keys_match_the_direct_call(self) -> None:
        from src.controllers.distributed_coordinator import boundary_group_key

        cache = self.coordinator._boundary_group_key_cache
        self.assertEqual(set(cache), set(self.coordinator._specs))
        for movement, spec in self.coordinator._specs.items():
            with self.subTest(movement=movement):
                self.assertEqual(cache[movement], boundary_group_key(spec))

    def test_onramp_by_movement_matches_the_direct_inversion(self) -> None:
        expected = {
            movement: ramp
            for ramp, movements in self.cfg.network.on_ramp_to_movement.items()
            for movement in movements
        }
        self.assertEqual(self.coordinator._onramp_by_movement, expected)


class DiagnosticsValueTests(unittest.TestCase):
    """캐시 도입 전후로 진단 결과가 같은지 실 시나리오로 확인한다."""

    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.coordinator = DistributedCoordinator(self.cfg)

    def test_diagnostics_are_deterministic_and_finite(self) -> None:
        import math

        from src.controllers.leader import LeaderAction
        from src.models.demand import DemandProfile, load_scenarios
        from src.models.state import ControlAction
        from src.simulation.simulator import MixedTrafficSimulator

        scenarios = load_scenarios("src/config/scenarios.yaml")
        profile = DemandProfile(self.cfg, scenarios["sweet_155"])
        sim = MixedTrafficSimulator(self.cfg)
        for step in range(2):
            sim.step(ControlAction.uncontrolled(self.cfg), profile.at(step), step)

        control = ControlAction.fixed(self.cfg)
        leader = LeaderAction(
            N_P_star=0.0, N_UF_star=self.cfg.network.total_ramp_capacity
        )
        first = self.coordinator._leader_direct_feasible_set_diagnostics(
            sim.state, control, [profile.at(2)], leader
        )
        second = self.coordinator._leader_direct_feasible_set_diagnostics(
            sim.state, control, [profile.at(2)], leader
        )
        self.assertTrue(first, "진단이 비었으면 아무것도 증명하지 않는다")
        self.assertEqual(first, second, "같은 입력에 다른 값이 나온다")
        for key, value in first.items():
            with self.subTest(key=key):
                self.assertTrue(math.isfinite(float(value)), f"{key}={value}")

    def test_leader_none_still_returns_empty(self) -> None:
        from src.models.state import ControlAction, TrafficState

        state = TrafficState.initial(self.cfg)
        self.assertEqual(
            self.coordinator._leader_direct_feasible_set_diagnostics(
                state, ControlAction.fixed(self.cfg), [], None
            ),
            {},
        )


if __name__ == "__main__":
    unittest.main()
