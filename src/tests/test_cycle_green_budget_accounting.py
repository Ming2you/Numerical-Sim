# v3 N4-5 잔여 - 녹색 예산이 전역이라 신호별 주기를 채우면 무엇이 깨지는지 수치로 고정한다
"""N4-1 이 `cycle_length_by_signal` 을 비워 둔 이유를 주석이 아니라 검사로 남긴다.

## 회계

`effective_green_total` 은 **스칼라** `cycle_length` 에서만 나온다(`state.py:400`).

    effective_green_total = cycle_length - lost_time

컨트롤러는 예외 없이 `p2 = effective_green_total - p1` 로 두 현시를 배분하므로
(distributed_coordinator:1250, structured_grid:43, rollout_endpoint:133, ...),
한 신호의 녹색 합은 **어느 신호든 같은 전역 상수**다. 모델은 이 합이 주기를 정확히
채운다는 것을 항등식으로 갖고 있다.

    p1 + p2 + lost_time == cycle_length      (evaluation/metrics.py:242 가 위반을 센다)

`_phase_green_fraction` 의 현시 창 배치도 같은 전제 위에 서 있다.

    p1 = [0, g1)   //  lost/2  //  p2 = [g1 + lost/2, g1 + lost/2 + g2)  //  lost/2

즉 `cycle_length` 는 자유 파라미터가 아니라 **녹색 예산이 결정한 값**이다. 그래서
`cycle_length_by_signal` 에 예산과 무관한 native 주기를 넣으면, 그 신호의 주기는
길어지는데 채울 녹색은 그대로여서 한 주기에 **아무 현시도 녹색이 아닌 구간**이 생긴다.
이 구간은 clearance 가 아니다. 모델이 설명하지 못하는 순수한 암흑시간이다.

여기서는 그 암흑시간을 실제 `_phase_green_fraction` 으로 적분해 초 단위로 잰다.
"""

from __future__ import annotations

import unittest

from src.models.state import ControlAction, ExperimentConfig, reset_cycle_length_fallback_counts
from src.models.urban_queue_model import _phase_green_fraction

# VISSIM/outputs/signal_group_timing_v3.json 의 제어 15 SC native 주기(중복 제거).
NATIVE_CYCLES_SEC = (100.0, 140.0, 150.0, 160.0, 170.0)


def _config() -> ExperimentConfig:
    return ExperimentConfig.from_file("src/config/default.yaml")


class GreenBudgetIsGlobalTests(unittest.TestCase):
    """예산이 스칼라 주기에만 매여 있다는 것이 이 문제의 전부다."""

    def setUp(self) -> None:
        self.cfg = _config()
        reset_cycle_length_fallback_counts()

    def test_the_budget_exactly_fills_the_scalar_cycle(self) -> None:
        net = self.cfg.network
        self.assertEqual(net.effective_green_total + net.lost_time, net.cycle_length)

    def test_the_green_box_is_sized_to_that_same_budget(self) -> None:
        """green_min/green_max 도 예산에 묶여 있다 - 주기만 바꾸면 상자가 남는다."""
        net = self.cfg.network
        self.assertEqual(net.green_min + net.green_max, net.effective_green_total)

    def test_a_per_signal_cycle_does_not_move_the_budget(self) -> None:
        """핵심. 신호별 주기를 넣어도 예산은 스칼라에서 나온다."""
        net = self.cfg.network
        before = net.effective_green_total
        net.cycle_length_by_signal = {signal: 150.0 for signal in net.signals}
        self.assertEqual(net.effective_green_total, before)
        self.assertNotEqual(net.signal_cycle_length(net.signals[0]), net.cycle_length)


class DarkTimeOpenedByNativeCyclesTests(unittest.TestCase):
    """예산은 그대로 둔 채 주기만 native 로 늘렸을 때 생기는 암흑시간을 잰다."""

    def setUp(self) -> None:
        self.cfg = _config()
        reset_cycle_length_fallback_counts()
        self.control = ControlAction.fixed(self.cfg)
        self.signal = self.cfg.network.signals[0]

    def _served_green_sec_per_cycle(self, cycle_sec: float) -> float:
        """한 주기 동안 두 현시가 실제로 서비스하는 녹색 [s].

        `_phase_green_fraction` 의 offset-aware 분기를 그대로 적분한다 - 플랜트가
        substep 마다 부르는 바로 그 경로다.
        """
        t_u = self.cfg.simulation.T_u_sec
        substeps = int(round(cycle_sec / t_u))
        self.assertAlmostEqual(substeps * t_u, cycle_sec, places=9)
        total = 0.0
        for index in range(substeps):
            for phase in (f"{self.signal}_p1", f"{self.signal}_p2"):
                total += _phase_green_fraction(
                    self.control, self.cfg, {"phase": phase}, index
                ) * t_u
        return total

    def _dark_sec_per_cycle(self, cycle_sec: float) -> float:
        """녹색도 clearance 도 아닌 시간 [s]."""
        return cycle_sec - self._served_green_sec_per_cycle(cycle_sec) - self.cfg.network.lost_time

    def test_an_empty_mapping_leaves_no_dark_time(self) -> None:
        """되돌림 증명 - 매핑을 비우면 암흑시간은 정확히 0 이다."""
        net = self.cfg.network
        self.assertEqual(net.cycle_length_by_signal, {})
        self.assertEqual(self._dark_sec_per_cycle(net.cycle_length), 0.0)

    def test_a_native_cycle_longer_than_the_budget_opens_that_much_dark_time(self) -> None:
        """제어 15 SC 중 14곳(140/150/160/170)이 이쪽이다. 예산 120 s 를 못 채운다."""
        net = self.cfg.network
        for cycle, expected_dark in ((140.0, 20.0), (150.0, 30.0), (160.0, 40.0), (170.0, 50.0)):
            with self.subTest(cycle=cycle):
                net.cycle_length_by_signal = {self.signal: cycle}
                self.assertAlmostEqual(self._dark_sec_per_cycle(cycle), expected_dark, places=9)
                self.assertAlmostEqual(
                    expected_dark, cycle - net.effective_green_total - net.lost_time, places=9
                )

    def test_a_native_cycle_shorter_than_the_budget_truncates_the_second_phase(self) -> None:
        """SC6 의 native 주기 100 s 는 반대로 **모자란다** - p2 창이 잘린다.

        암흑시간이 아니라 서비스 손실이다. p1 [0,56) 은 온전하고 p2 [60,116) 이
        주기 끝 100 에서 잘려 16 s 를 잃는다.
        """
        net = self.cfg.network
        net.cycle_length_by_signal = {self.signal: 100.0}
        self.assertAlmostEqual(self._served_green_sec_per_cycle(100.0), 96.0, places=9)
        self.assertAlmostEqual(net.effective_green_total - 96.0, 16.0, places=9)

    def test_the_cycle_average_branch_oversubscribes_the_short_cycle(self) -> None:
        """더 나쁜 쪽. 주기 평균 분기는 자르지 않아 두 현시 합이 1 을 넘는다.

        `_phase_green_fraction` 의 `urban_step_index=None` 분기는 g/C 를 현시별로
        따로 클립하므로 합이 1 을 넘을 수 있다. 100 s 주기에 112 s 예산을 넣으면
        두 현시가 주기의 112% 를 녹색이라고 주장한다 - 물리적으로 불가능하다.
        """
        net = self.cfg.network
        net.cycle_length_by_signal = {self.signal: 100.0}
        coverage = sum(
            _phase_green_fraction(self.control, self.cfg, {"phase": f"{self.signal}_{p}"})
            for p in ("p1", "p2")
        )
        self.assertAlmostEqual(coverage, net.effective_green_total / 100.0, places=12)
        self.assertGreater(coverage, 1.0)

    def test_axis_green_coverage_tracks_the_budget_over_the_native_cycle(self) -> None:
        """축 녹색 분율 합은 언제나 예산/C 다 - 예산이 따라오지 않으니 C 만 바뀐다."""
        net = self.cfg.network
        budget = net.effective_green_total
        baseline = sum(
            _phase_green_fraction(self.control, self.cfg, {"phase": f"{self.signal}_{p}"})
            for p in ("p1", "p2")
        )
        self.assertAlmostEqual(baseline, budget / net.cycle_length, places=12)
        for cycle in NATIVE_CYCLES_SEC:
            with self.subTest(cycle=cycle):
                net.cycle_length_by_signal = {self.signal: cycle}
                coverage = sum(
                    _phase_green_fraction(
                        self.control, self.cfg, {"phase": f"{self.signal}_{p}"}
                    )
                    for p in ("p1", "p2")
                )
                self.assertAlmostEqual(coverage, budget / cycle, places=12)
                self.assertNotAlmostEqual(coverage, baseline, places=6)


class PlantCycleIdentityTests(unittest.TestCase):
    """플랜트(VBS)의 주기 식은 모델 항등식과 같은 모양이고 상수만 다르다.

    플랜트   C = major + minor + 2 x (AMBER_SEC + ALL_RED_SEC)
    모델     C = p1    + p2    + lost_time

    어댑터가 major <- p2, minor <- p1 을 그대로 싣기 때문에, 두 주기를 같게 만드는
    조건은 `lost_time == 2 x (amber + all_red)` 하나뿐이다. 실 플랜트는 3 + 2 라서
    10 s 이고 모델 기본값은 8 s 다. 이 차이가 주기 2 s 어긋남의 전부다.
    """

    PLANT_LOST_TIME_SEC = 10.0

    def test_the_default_lost_time_does_not_match_the_plant_clearance(self) -> None:
        self.assertNotEqual(_config().network.lost_time, self.PLANT_LOST_TIME_SEC)

    def test_matching_the_clearance_makes_the_two_cycles_identical(self) -> None:
        cfg = _config()
        net = cfg.network
        net.lost_time = self.PLANT_LOST_TIME_SEC
        for p1 in (net.green_min, net.effective_green_total / 2.0, net.effective_green_total - net.green_min):
            with self.subTest(p1=p1):
                p2 = net.effective_green_total - p1
                plant_cycle = p1 + p2 + self.PLANT_LOST_TIME_SEC
                self.assertEqual(plant_cycle, net.cycle_length)


if __name__ == "__main__":
    unittest.main()
