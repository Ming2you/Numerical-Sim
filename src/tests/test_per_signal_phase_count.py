# v3 N4-6 - SC별 현시 수(live_phases_by_signal)와 그로부터 유도되는 녹색 예산을 고정한다
"""전역 스칼라 녹색 예산 하나를 신호별 예산으로 쪼갠다.

## 왜

`effective_green_total = cycle_length - lost_time` 은 **스칼라**다. 그런데 lost time 은
현시 수에 비례한다(`N x clearance`) 이고, 개포동 실망의 현시 수는 SC마다 다르다 —
VISSIM 안에서 400 초를 돌려 SG 상태를 초당 받아 세면 15 SC 중 12 개가 4현시, SC107·108·
109 가 3현시다(VISSIM/outputs/live_signal_cycle_probe_n4dr150_20260812.json). 그 셋은 한
현시의 SG 가 `.sig` 에서 영구적색이라 플랜트가 아예 안 돌린다.

스칼라 하나로 밀면 3현시 SC 에서 예산이 3 s 모자란다. 실측하면 그 어긋남이 이렇게 나온다 —
모델이 SC107 의 죽은 현시에 97.5 s 를 명령하고 플랜트는 0.0 s 를 실현한다.

## 계약

`cycle_length_by_signal` 과 **같은 모양**이다.

    스칼라 lost_time + dict live_phases_by_signal + 헬퍼 signal_lost_time() /
    signal_effective_green_total()

- 매핑이 **비면** 스칼라로 폴백하고 기존 거동과 비트 동일하다(legacy 모드).
- 예산은 상수로 적지 않는다. `C - N x clearance` 로 **유도**한다. 141 이나 138 을 손으로
  적으면 현시 수가 바뀔 때 조용히 틀린다.
"""

from __future__ import annotations

import unittest

from src.models.state import MODEL_PHASES, ExperimentConfig


def _config() -> ExperimentConfig:
    return ExperimentConfig.from_file("src/config/default.yaml")


class PerSignalPhaseCountTests(unittest.TestCase):
    def test_an_empty_mapping_keeps_the_scalar_behaviour(self) -> None:
        """legacy 모드 - 매핑이 비면 스칼라와 비트 동일하다."""
        net = _config().network
        self.assertEqual({}, net.live_phases_by_signal)
        for signal in ("SC1", "SC107", "없는신호"):
            with self.subTest(signal=signal):
                self.assertEqual(net.lost_time, net.signal_lost_time(signal))
                self.assertEqual(
                    net.effective_green_total, net.signal_effective_green_total(signal)
                )

    def test_a_three_phase_signal_gets_a_larger_green_budget(self) -> None:
        """현시가 하나 적으면 clearance 를 한 번 덜 문다 - 그만큼 녹색이 늘어난다."""
        net = _config().network
        net.live_phases_by_signal = {"SC107": ["p2", "p3", "p4"]}
        clearance = net.lost_time / float(len(MODEL_PHASES))

        self.assertEqual(3.0 * clearance, net.signal_lost_time("SC107"))
        self.assertEqual(
            net.cycle_length - 3.0 * clearance, net.signal_effective_green_total("SC107")
        )
        # 4현시 SC 는 그대로다.
        self.assertEqual(net.lost_time, net.signal_lost_time("SC1"))
        self.assertEqual(
            net.effective_green_total, net.signal_effective_green_total("SC1")
        )

    def test_both_phase_counts_land_on_the_same_cycle(self) -> None:
        """이것이 목적이다 - N 이 몇이든 예산 + lost time 이 주기와 같다.

        값을 손으로 적지 않는다. 두 N 을 넣고 주기가 나오는지만 본다.
        """
        net = _config().network
        for count in (2, 3, 4):
            with self.subTest(count=count):
                net.live_phases_by_signal = {"SC107": list(MODEL_PHASES[:count])}
                self.assertAlmostEqual(
                    net.cycle_length,
                    net.signal_effective_green_total("SC107")
                    + net.signal_lost_time("SC107"),
                    places=9,
                )

    def test_a_signal_missing_from_a_populated_mapping_falls_back(self) -> None:
        """결선 실수는 조용히 넘어가되 스칼라로 떨어진다 - 주기 쪽과 같은 규칙이다."""
        net = _config().network
        net.live_phases_by_signal = {"SC107": ["p2", "p3", "p4"]}
        self.assertEqual(net.lost_time, net.signal_lost_time("SC999"))

    def test_a_non_positive_phase_count_is_rejected(self) -> None:
        net = _config().network
        net.live_phases_by_signal = {"SC107": []}
        with self.assertRaises(ValueError):
            net.signal_lost_time("SC107")


if __name__ == "__main__":
    unittest.main()
