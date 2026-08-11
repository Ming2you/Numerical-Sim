# v3 N4-5 잔여 - 녹색 예산이 전역이라 신호별 주기를 채우면 무엇이 깨지는지 수치로 고정한다
"""N4-1 이 `cycle_length_by_signal` 을 비워 둔 이유를 주석이 아니라 검사로 남긴다.

## 회계 (2026-08-12 4현시 일반화)

`effective_green_total` 은 **스칼라** `cycle_length` 에서만 나온다(`state.py`).

    effective_green_total = cycle_length - lost_time

컨트롤러는 주 현시(`MODEL_PHASES[0]`) 하나만 결정변수로 움직이고 나머지 예산은
`distribute_phase_green` 이 나눈다. 어느 신호든 녹색 합은 **같은 전역 상수**다.
모델은 이 합이 주기를 정확히 채운다는 것을 항등식으로 갖고 있다.

    Σ_i g_i + lost_time == cycle_length      (evaluation/metrics.py 가 위반을 센다)

이건 구 2현시 항등식 `p1 + p2 + lost_time == cycle_length` 의 일반화다.
`_phase_green_fraction` 의 현시 창 배치도 같은 전제 위에 서 있다.

    c = lost_time / N
    p_k = [Σ_{j<k} g_j + k·c,  Σ_{j<k} g_j + k·c + g_k)

즉 `cycle_length` 는 자유 파라미터가 아니라 **녹색 예산이 결정한 값**이다. 그래서
`cycle_length_by_signal` 에 예산과 무관한 native 주기를 넣으면, 그 신호의 주기는
길어지는데 채울 녹색은 그대로여서 한 주기에 **아무 현시도 녹색이 아닌 구간**이 생긴다.
이 구간은 clearance 가 아니다. 모델이 설명하지 못하는 순수한 암흑시간이다.

여기서는 그 암흑시간을 실제 `_phase_green_fraction` 으로 적분해 초 단위로 잰다.
"""

from __future__ import annotations

import unittest

from src.models.state import (
    MODEL_PHASES,
    ControlAction,
    ExperimentConfig,
    reset_cycle_length_fallback_counts,
)
from src.models.urban_queue_model import _phase_green_fraction

# VISSIM/outputs/signal_group_timing_v3.json 의 제어 15 SC native 주기(중복 제거).
# N4-0 이후 목표는 150 통일이지만, 여기서는 "예산과 다른 주기를 넣으면 무엇이 깨지는가"를
# 재는 것이므로 실측 분포를 그대로 둔다.
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
        """green_min/green_max 도 예산에 묶여 있다 - 주기만 바꾸면 상자가 남는다.

        N 현시에서는 한 현시를 상한까지 밀었을 때 나머지 (N-1) 이 정확히 하한에 앉아야
        한다. N=2 면 구 식 `green_min + green_max == 유효녹색` 과 같다.
        """
        net = self.cfg.network
        self.assertEqual(
            net.green_max + (net.num_phases - 1) * net.green_min,
            net.effective_green_total,
        )

    def test_a_per_signal_cycle_does_not_move_the_budget(self) -> None:
        """핵심. 신호별 주기를 넣어도 예산은 스칼라에서 나온다."""
        net = self.cfg.network
        before = net.effective_green_total
        net.cycle_length_by_signal = {signal: 170.0 for signal in net.signals}
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
        """한 주기 동안 네 현시가 실제로 서비스하는 녹색 [s].

        `_phase_green_fraction` 의 offset-aware 분기를 그대로 적분한다 - 플랜트가
        substep 마다 부르는 바로 그 경로다.
        """
        t_u = self.cfg.simulation.T_u_sec
        substeps = int(round(cycle_sec / t_u))
        self.assertAlmostEqual(substeps * t_u, cycle_sec, places=9)
        total = 0.0
        for index in range(substeps):
            for pid in MODEL_PHASES:
                total += _phase_green_fraction(
                    self.control, self.cfg, {"phase": f"{self.signal}_{pid}"}, index
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
        """예산 주기(150)보다 긴 native 주기는 그 차이만큼 암흑시간을 연다."""
        net = self.cfg.network
        for cycle in (160.0, 170.0):
            with self.subTest(cycle=cycle):
                net.cycle_length_by_signal = {self.signal: cycle}
                expected_dark = cycle - net.effective_green_total - net.lost_time
                self.assertGreater(expected_dark, 0.0)
                self.assertAlmostEqual(self._dark_sec_per_cycle(cycle), expected_dark, places=9)

    def test_a_native_cycle_shorter_than_the_budget_truncates_the_last_phase(self) -> None:
        """주기가 예산보다 **짧으면** 반대로 마지막 현시 창이 잘린다.

        암흑시간이 아니라 서비스 손실이다. 잘리는 양은 마지막 현시 창의 끝이 주기를
        넘어선 만큼이고, 창 배치에서 정확히 유도된다 - 마법의 상수가 아니다.
        """
        from src.models.state import phase_start_offsets, signal_green_reference

        net = self.cfg.network
        short_cycle = 140.0
        net.cycle_length_by_signal = {self.signal: short_cycle}
        greens = signal_green_reference(self.control, net, self.signal)
        last = MODEL_PHASES[-1]
        overrun = phase_start_offsets(net, greens)[last] + greens[last] - short_cycle
        self.assertGreater(overrun, 0.0)
        served = self._served_green_sec_per_cycle(short_cycle)
        self.assertAlmostEqual(served, net.effective_green_total - overrun, places=9)
        self.assertAlmostEqual(overrun, 7.0, places=9)

    def test_the_cycle_average_branch_oversubscribes_the_short_cycle(self) -> None:
        """더 나쁜 쪽. 주기 평균 분기는 자르지 않아 네 현시 합이 1 을 넘는다.

        `_phase_green_fraction` 의 `urban_step_index=None` 분기는 g/C 를 현시별로
        따로 클립하므로 합이 1 을 넘을 수 있다. 100 s 주기에 138 s 예산을 넣으면
        네 현시가 주기의 138% 를 녹색이라고 주장한다 - 물리적으로 불가능하다.
        """
        net = self.cfg.network
        net.cycle_length_by_signal = {self.signal: 100.0}
        coverage = sum(
            _phase_green_fraction(self.control, self.cfg, {"phase": f"{self.signal}_{pid}"})
            for pid in MODEL_PHASES
        )
        self.assertAlmostEqual(coverage, net.effective_green_total / 100.0, places=12)
        self.assertGreater(coverage, 1.0)

    def test_phase_green_coverage_tracks_the_budget_over_the_native_cycle(self) -> None:
        """현시 녹색 분율 합은 언제나 예산/C 다 - 예산이 따라오지 않으니 C 만 바뀐다."""
        net = self.cfg.network
        budget = net.effective_green_total
        baseline = sum(
            _phase_green_fraction(self.control, self.cfg, {"phase": f"{self.signal}_{pid}"})
            for pid in MODEL_PHASES
        )
        self.assertAlmostEqual(baseline, budget / net.cycle_length, places=12)
        for cycle in NATIVE_CYCLES_SEC:
            if cycle == net.cycle_length:
                continue
            with self.subTest(cycle=cycle):
                net.cycle_length_by_signal = {self.signal: cycle}
                coverage = sum(
                    _phase_green_fraction(
                        self.control, self.cfg, {"phase": f"{self.signal}_{pid}"}
                    )
                    for pid in MODEL_PHASES
                )
                self.assertAlmostEqual(coverage, budget / cycle, places=12)
                self.assertNotAlmostEqual(coverage, baseline, places=6)


class PlantCycleIdentityTests(unittest.TestCase):
    """플랜트(VBS)의 주기 식은 모델 항등식과 같은 모양이고 상수만 다르다.

    플랜트   C = Σ 현시녹색 + Σ 현시전이 clearance
    모델     C = Σ_i g_i    + lost_time

    두 주기를 같게 만드는 조건은 `lost_time == N x clearance` 하나뿐이다. 실 `.sig`
    136 SG 의 amber 는 전부 3.0 s 단독이고 all-red 는 없다(VISSIM
    scripts/survey_signal_programs.py 실측). 4현시면 4 x 3 = 12 s 다.

    구 러너 상수 `AMBER_SEC 3 + ALL_RED_SEC 2` 의 2현시 값 10 s 는 실 프로그램과도
    현행 모델과도 어긋난다 - 그 어긋남을 여기 고정한다.
    """

    PLANT_CLEARANCE_SEC = 3.0
    LEGACY_RUNNER_LOST_TIME_SEC = 10.0

    def test_the_lost_time_is_the_measured_clearance_times_the_phase_count(self) -> None:
        net = _config().network
        self.assertEqual(net.lost_time, self.PLANT_CLEARANCE_SEC * net.num_phases)

    def test_the_legacy_runner_constant_no_longer_matches(self) -> None:
        """러너의 3+2 는 실 `.sig`(amber 3 단독)와도 4현시 모델과도 다르다."""
        net = _config().network
        self.assertNotEqual(net.lost_time, self.LEGACY_RUNNER_LOST_TIME_SEC)

    def test_matching_the_clearance_makes_the_two_cycles_identical(self) -> None:
        from src.models.state import distribute_phase_green

        cfg = _config()
        net = cfg.network
        for primary in (net.green_min, net.default_phase_green, net.green_max):
            with self.subTest(primary=primary):
                greens = distribute_phase_green(net, primary)
                plant_cycle = sum(greens.values()) + self.PLANT_CLEARANCE_SEC * net.num_phases
                self.assertAlmostEqual(plant_cycle, net.cycle_length, places=9)


if __name__ == "__main__":
    unittest.main()
