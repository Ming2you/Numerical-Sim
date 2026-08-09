# v3 N8 - _allocation_control_map 의 경계링크 집계를 인덱스화한다 (결과 불변, 비용만 절감)
"""탐색 루프 안에서 매번 도는 O(경계링크 x 전체 movement) 스캔을 없앤다.

## 왜 지금인가

N9 행렬을 실제로 전개하니 제어 결정이 59,616 회다. 결정당 solve 가 300 초대면 4,968 시간
(207일)이라 N9 자체가 성립하지 않는다. 그래서 solve 비용은 선택지가 아니라 전제다.

`_allocation_control_map` 은 호출부 셋(`distributed_coordinator.py:1216, :1740, :1945`)이 전부
탐색 루프 안이고, 호출마다 경계링크 14개 x movement 78개 = **1,092 회** `spec.get` 을 돈다.
링크별 movement 목록은 config 가 고정이면 불변이므로 한 번만 만들면 된다.

실측 - 20,000 회 반복에서 0.925 s -> 0.133 s (**7.0 배**), 결과는 소수점까지 동일.

## 이 테스트가 지키는 것

최적화의 유일한 위험은 "빨라졌는데 답이 달라지는 것" 이다. 그래서 인덱스 구현이 순진한
구현과 **정확히 같은 dict** 를 내는지 실 config 로 확인한다. 성능 수치 자체는 단언하지
않는다 - 기계마다 달라 깨지기 쉽고, 여기서 증명해야 할 것은 등가성이다.
"""

from __future__ import annotations

import unittest

from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.inflow_outflow_allocation import AllocationResult
from src.models.state import ExperimentConfig


def naive_allocation_control_map(cfg, allocation_plan) -> dict:
    """`_allocation_control_map` 의 인덱스 도입 이전 구현을 그대로 재현한 참조 구현."""
    if allocation_plan is None:
        return {}
    allocation = dict(allocation_plan.movement_flows)
    for link in cfg.network.boundary_in_links:
        allocation[link] = sum(
            allocation.get(movement, 0.0)
            for movement, spec in cfg.network.urban_movements.items()
            if spec.get("origin") == link and spec.get("kind") == "boundary_in"
        )
    for link in cfg.network.boundary_out_links:
        allocation[link] = sum(
            allocation.get(movement, 0.0)
            for movement, spec in cfg.network.urban_movements.items()
            if spec.get("destination") == link and spec.get("kind") == "boundary_out"
        )
    return allocation


class AllocationControlMapIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.coordinator = DistributedCoordinator(self.cfg)

    def _plan(self, flows: dict) -> AllocationResult:
        result = AllocationResult.__new__(AllocationResult)
        object.__setattr__(result, "movement_flows", flows)
        return result

    def test_matches_the_naive_reference_on_the_real_config(self) -> None:
        flows = {
            movement: 1.0 + index * 0.25
            for index, movement in enumerate(self.cfg.network.urban_movements)
        }
        plan = self._plan(flows)
        self.assertEqual(
            self.coordinator._allocation_control_map(plan),
            naive_allocation_control_map(self.cfg, plan),
        )

    def test_zero_and_empty_flows_still_match(self) -> None:
        for flows in ({}, {m: 0.0 for m in self.cfg.network.urban_movements}):
            plan = self._plan(flows)
            self.assertEqual(
                self.coordinator._allocation_control_map(plan),
                naive_allocation_control_map(self.cfg, plan),
            )

    def test_none_plan_returns_empty(self) -> None:
        self.assertEqual(self.coordinator._allocation_control_map(None), {})

    def test_boundary_index_is_built_once_and_reused(self) -> None:
        """호출마다 다시 만들면 최적화의 의미가 없다. 같은 객체여야 한다."""
        plan = self._plan({m: 1.0 for m in self.cfg.network.urban_movements})
        self.coordinator._allocation_control_map(plan)
        first = self.coordinator._boundary_movement_index
        self.coordinator._allocation_control_map(plan)
        self.assertIs(self.coordinator._boundary_movement_index, first)

    def test_index_covers_every_boundary_link(self) -> None:
        """링크가 인덱스에 없으면 조용히 0 이 된다 - 순진한 구현은 그 경우 빈 합이었다.

        두 구현이 그 지점에서 갈리면 안 되므로 명시적으로 확인한다.
        """
        self.coordinator._allocation_control_map(self._plan({}))
        inbound, outbound = self.coordinator._boundary_movement_index
        for link in self.cfg.network.boundary_in_links:
            self.assertIn(link, inbound)
        for link in self.cfg.network.boundary_out_links:
            self.assertIn(link, outbound)


if __name__ == "__main__":
    unittest.main()
