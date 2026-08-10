# v3 N8 - movement_specs 를 network 참조 동일성으로 메모이즈한다 (값 불변)
"""호출마다 movement dict 1,414 개를 복사하던 것을 없앤다.

## 왜

`movement_specs(cfg)` 는 `{key: dict(value) for ...}` 로 **전체 movement 를 매번 복사**한다.
호출부가 14 곳이고 그중 여럿이 후보 평가 안쪽이다.

    inflow_outflow_allocation.py:84, :240, :328
    simplified_inflow_outflow_allocation.py:44   <- 실런은 allocation_mode=simplified
    spillback_constraints.py:18
    distributed_coordinator.py:1090, :2857, :3112

실런 정본 결선(core15n41)은 movement 가 1,414 개다(default.yaml 은 78). 후보 평가마다
1,414 개 dict 를 새로 만드는 셈이다.

## 복사를 없애도 되는 근거

복사하는 이유는 호출자가 변형할 수 있어서인데, **변형하는 호출자가 없다.** 저장소 전체에서
`spec[...] = ` 쓰기는 network 를 만드는 `grid_topology.py`(config 생성 이전)와 이름만 같은
`rl/agents.py` 의 다른 `specs` 뿐이다.

캐시 방식은 저장소에 이미 있는 `_legacy_sync_index` 와 같다 — network 객체 참조 동일성으로
재사용을 판정한다(`urban_queue_model.py:42-46` 의 전제와 동일).

## 이 테스트가 지키는 것

값이 같아야 하고, 서로 다른 network 는 서로 다른 결과를 받아야 한다. 후자가 없으면 캐시가
다른 config 의 값을 돌려주는 사고를 못 잡는다.
"""

from __future__ import annotations

import unittest

from src.models.state import ExperimentConfig
from src.models.urban_queue_model import movement_specs


class MovementSpecsMemoizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")

    def test_repeated_calls_return_the_same_object(self) -> None:
        self.assertIs(movement_specs(self.cfg), movement_specs(self.cfg))

    def test_values_match_the_network_definition(self) -> None:
        specs = movement_specs(self.cfg)
        self.assertEqual(set(specs), set(self.cfg.network.urban_movements))
        for movement, spec in self.cfg.network.urban_movements.items():
            with self.subTest(movement=movement):
                self.assertEqual(dict(specs[movement]), dict(spec))

    def test_insertion_order_is_preserved(self) -> None:
        """합산 순서가 바뀌면 부동소수 결과가 달라진다. 기존 캐시도 같은 전제를 둔다."""
        self.assertEqual(
            list(movement_specs(self.cfg)), list(self.cfg.network.urban_movements)
        )

    def test_a_different_network_is_not_served_from_the_cache(self) -> None:
        """캐시가 다른 config 의 값을 돌려주면 조용히 틀린 답이 나온다."""
        other = ExperimentConfig.from_file("src/config/default.yaml")
        self.assertIsNot(other.network, self.cfg.network)

        first = movement_specs(self.cfg)
        second = movement_specs(other)
        self.assertIsNot(first, second)
        self.assertEqual(set(first), set(second))

        # 앞선 config 로 다시 물으면 그쪽 캐시가 살아 있어야 한다(교대 호출에도 안전).
        self.assertIs(movement_specs(self.cfg), first)


if __name__ == "__main__":
    unittest.main()
