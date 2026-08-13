# v3 N4-7 - SC별 '켤 수 있는 현시 집합'과 그 위에서만 도는 녹색 배분을 고정한다
"""개수만으로는 부족하다.

앞 회차에서 `live_phase_count_by_signal` 로 SC별 현시 **수**를 열었다. 예산은 그것으로
맞았지만(`C - N x clearance`), 어느 현시가 살아 있는지는 담지 못한다. 실 망에서 SC107 의
살아 있는 현시는 (p2, p3, p4) 다 - p1 이 아니라 **p1 만 빠진** 셋이다.

짝지은 런이 그 간극을 그대로 드러냈다.

    SignalGroupPlanError: sc 107: action commands green on phases
        ('p1','p2','p3','p4') but the actuation plan has signal groups on
        ('p2','p3','p4')

모델이 죽은 현시에 녹색을 주면 플랜트는 그 시간을 전현시 적색으로 흘린다. 어댑터가
fail-closed 로 막았으므로 런이 죽었을 뿐, 막지 않았다면 그 이동류가 통째로 적색이 된다.

## 계약

    live_phases_by_signal   SC -> 켤 수 있는 현시 목록. 비면 legacy(전 현시)다.
    signal_live_phases(s)   그 목록. 없으면 MODEL_PHASES 전부.
    signal_lost_time(s)     len(signal_live_phases) x clearance  ← 개수는 집합에서 유도

배분 함수 둘은 `signal` 을 받으면 그 집합 위에서만 돈다. 안 받으면(기본값 None) 종전과
비트 동일하다 - 호출부 45곳을 한꺼번에 안 건드리기 위한 것이다.
"""

from __future__ import annotations

import unittest

from src.models.state import (
    MODEL_PHASES,
    ExperimentConfig,
    allocate_phase_green,
    distribute_phase_green,
)


def _config() -> ExperimentConfig:
    return ExperimentConfig.from_file("src/config/default.yaml")


class PerSignalLivePhaseTests(unittest.TestCase):
    def test_an_empty_mapping_keeps_every_phase(self) -> None:
        net = _config().network
        self.assertEqual({}, net.live_phases_by_signal)
        self.assertEqual(tuple(MODEL_PHASES), net.signal_live_phases("SC107"))

    def test_the_dead_phase_is_not_in_the_live_set(self) -> None:
        net = _config().network
        net.live_phases_by_signal = {"SC107": ["p2", "p3", "p4"]}
        self.assertEqual(("p2", "p3", "p4"), net.signal_live_phases("SC107"))
        self.assertEqual(tuple(MODEL_PHASES), net.signal_live_phases("SC1"))

    def test_lost_time_is_derived_from_the_set_not_a_separate_count(self) -> None:
        """개수를 따로 들고 있으면 둘이 어긋날 수 있다. 집합 하나가 정본이다."""
        net = _config().network
        net.live_phases_by_signal = {"SC107": ["p2", "p3", "p4"]}
        clearance = net.lost_time / float(len(MODEL_PHASES))
        self.assertEqual(3.0 * clearance, net.signal_lost_time("SC107"))
        self.assertEqual(
            net.cycle_length - 3.0 * clearance, net.signal_effective_green_total("SC107")
        )

    def test_allocation_gives_no_green_to_a_dead_phase(self) -> None:
        net = _config().network
        net.live_phases_by_signal = {"SC107": ["p2", "p3", "p4"]}
        scores = {pid: 1.0 for pid in MODEL_PHASES}
        values = allocate_phase_green(net, scores, signal="SC107")
        self.assertEqual(0.0, values["p1"])
        self.assertEqual(sorted(MODEL_PHASES), sorted(values), "키는 전 현시를 유지한다")
        # 죽은 현시의 몫이 사라지지 않고 살아 있는 셋이 예산 전체를 나눠 갖는다.
        self.assertAlmostEqual(
            net.signal_effective_green_total("SC107"), sum(values.values()), places=6
        )

    def test_distribution_gives_no_green_to_a_dead_phase(self) -> None:
        net = _config().network
        net.live_phases_by_signal = {"SC107": ["p2", "p3", "p4"]}
        reference = {pid: 30.0 for pid in MODEL_PHASES}
        values = distribute_phase_green(net, 50.0, reference, signal="SC107")
        self.assertEqual(0.0, values["p1"])
        self.assertAlmostEqual(
            net.signal_effective_green_total("SC107"), sum(values.values()), places=6
        )

    def test_without_a_signal_the_functions_are_bit_identical(self) -> None:
        """되돌림 증명 - 기본 경로가 바뀌면 호출부 45곳이 조용히 움직인다."""
        net = _config().network
        scores = {"p1": 3.0, "p2": 1.0, "p3": 2.0, "p4": 1.0}
        reference = {"p1": 40.0, "p2": 20.0, "p3": 30.0, "p4": 25.0}
        before_alloc = allocate_phase_green(net, scores)
        before_dist = distribute_phase_green(net, 45.0, reference)
        net.live_phases_by_signal = {"SC107": ["p2", "p3", "p4"]}
        self.assertEqual(before_alloc, allocate_phase_green(net, scores))
        self.assertEqual(before_dist, distribute_phase_green(net, 45.0, reference))


if __name__ == "__main__":
    unittest.main()
