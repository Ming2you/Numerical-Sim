# N4-0 - 모델이 dual-ring 4현시라는 것을 실 config·실 토폴로지 위에서 고정한다
"""2현시(p1/p2) 가정이 남아 있으면 여기서 걸린다.

## 무엇을 재는가

1. **현시 축** — `MODEL_PHASES` 가 4개이고 순서가 major직진 → major좌 → minor직진 → minor좌.
2. **예산 계약** — `C = Σ g_i + lost_time`, `green_max = 유효녹색 - (N-1) x green_min`.
   구 검사(`test_cycle_green_budget_accounting`)가 N=2 에서 주장하던 항등식의 일반화다.
3. **회전 분류** — 우측통행에서 좌회전이 좌회전으로 분류되는가(격자 방위 실측).
4. **movement 배정** — 실제 토폴로지에서 네 현시가 **전부** 쓰이는가. 이게 없으면
   "4현시로 바꿨다"고 해놓고 실제로는 두 현시만 도는 것을 못 잡는다.
5. **창 배치** — `_phase_green_fraction` 이 한 주기에 네 창을 겹치지 않게 놓고
   암흑시간 0 으로 주기를 정확히 채우는가.

전부 실 config(`src/config/default.yaml`)와 실 토폴로지에서 돈다. 합성 픽스처 없음.
"""

from __future__ import annotations

import unittest

from src.models.grid_topology import (
    LEG_DIRECTIONS,
    MAJOR_AXIS_LEGS,
    movement_phase_id,
    movement_turn,
)
from src.models.state import (
    MODEL_PHASES,
    ControlAction,
    ExperimentConfig,
    allocate_phase_green,
    clamp_primary_green,
    distribute_phase_green,
    phase_start_offsets,
    reset_cycle_length_fallback_counts,
)
from src.models.urban_queue_model import _phase_green_fraction


def _config() -> ExperimentConfig:
    return ExperimentConfig.from_file("src/config/default.yaml")


class PhaseAxisTests(unittest.TestCase):
    def test_the_model_has_four_phases_in_the_nema_order(self) -> None:
        self.assertEqual(MODEL_PHASES, ("p1", "p2", "p3", "p4"))

    def test_the_major_axis_legs_are_a_proper_subset_of_the_eight_headings(self) -> None:
        self.assertTrue(MAJOR_AXIS_LEGS)
        self.assertTrue(MAJOR_AXIS_LEGS.issubset(set(LEG_DIRECTIONS)))
        self.assertNotEqual(MAJOR_AXIS_LEGS, set(LEG_DIRECTIONS))


class TurnClassificationTests(unittest.TestCase):
    """우측통행. N 에서 들어오면 진행은 S 고 좌회전 출구는 E 다."""

    def test_straight_left_right_and_u_turn_are_told_apart(self) -> None:
        self.assertEqual(movement_turn("N", "S"), "through")
        self.assertEqual(movement_turn("N", "E"), "left")
        self.assertEqual(movement_turn("N", "W"), "right")
        self.assertEqual(movement_turn("N", "N"), "u_turn")

    def test_every_approach_has_exactly_one_through_and_one_left(self) -> None:
        for approach in LEG_DIRECTIONS:
            turns = [movement_turn(approach, exit_leg) for exit_leg in LEG_DIRECTIONS]
            self.assertEqual(turns.count("through"), 1, approach)
            self.assertEqual(turns.count("u_turn"), 1, approach)
            self.assertEqual(turns.count("left"), 3, approach)
            self.assertEqual(turns.count("right"), 3, approach)

    def test_the_phase_is_the_axis_times_the_turn(self) -> None:
        major = sorted(MAJOR_AXIS_LEGS)[0]
        minor = next(leg for leg in LEG_DIRECTIONS if leg not in MAJOR_AXIS_LEGS)
        from src.models.grid_topology import OPPOSITE_LEG

        self.assertEqual(movement_phase_id(major, OPPOSITE_LEG[major]), "p1")
        self.assertEqual(movement_phase_id(minor, OPPOSITE_LEG[minor]), "p3")
        major_left = next(
            leg for leg in LEG_DIRECTIONS if movement_turn(major, leg) == "left"
        )
        minor_left = next(
            leg for leg in LEG_DIRECTIONS if movement_turn(minor, leg) == "left"
        )
        self.assertEqual(movement_phase_id(major, major_left), "p2")
        self.assertEqual(movement_phase_id(minor, minor_left), "p4")


class RealTopologyPhaseCoverageTests(unittest.TestCase):
    """실 토폴로지에서 네 현시가 전부 쓰이는가 — 합성 픽스처가 아니라 config 유도 movement."""

    def setUp(self) -> None:
        self.cfg = _config()

    def test_every_controlled_signal_uses_all_four_phases(self) -> None:
        net = self.cfg.network
        for signal in net.signals:
            used = {
                str(spec.get("phase", "")).rpartition("_")[2]
                for spec in net.urban_movements.values()
                if str(spec.get("phase", "")).startswith(f"{signal}_")
            }
            self.assertEqual(used, set(MODEL_PHASES), signal)

    def test_left_turn_movements_land_only_in_the_left_turn_phases(self) -> None:
        net = self.cfg.network
        left_phases = {"p2", "p4"}
        seen_left = 0
        for spec in net.urban_movements.values():
            phase = str(spec.get("phase", ""))
            if not phase:
                continue
            pid = phase.rpartition("_")[2]
            is_left = str(spec.get("turn", "")) == "left"
            self.assertEqual(is_left, pid in left_phases, spec)
            seen_left += int(is_left)
        self.assertGreater(seen_left, 0)


class GreenBudgetContractTests(unittest.TestCase):
    """`C = Σ g_i + lost_time` — 구 2현시 항등식의 N 현시 일반화."""

    def setUp(self) -> None:
        self.cfg = _config()
        self.net = self.cfg.network

    def test_the_budget_exactly_fills_the_cycle(self) -> None:
        self.assertEqual(
            self.net.effective_green_total + self.net.lost_time, self.net.cycle_length
        )

    def test_green_max_is_the_budget_minus_the_other_phases_at_minimum(self) -> None:
        net = self.net
        self.assertAlmostEqual(
            net.green_max,
            net.effective_green_total - (net.num_phases - 1) * net.green_min,
            places=9,
        )

    def test_the_target_spec_numbers(self) -> None:
        """N4-0 확정 스펙 — 주기 150 · lost 12 · 유효녹색 138 · 상자 [20, 78]."""
        net = self.net
        self.assertEqual(net.cycle_length, 150.0)
        self.assertEqual(net.lost_time, 12.0)
        self.assertEqual(net.effective_green_total, 138.0)
        self.assertEqual(net.green_min, 20.0)
        self.assertEqual(net.green_max, 78.0)
        self.assertEqual(net.num_phases, 4)

    def test_pushing_the_primary_phase_to_its_max_puts_the_rest_at_green_min(self) -> None:
        net = self.net
        values = distribute_phase_green(net, net.green_max)
        self.assertAlmostEqual(values[MODEL_PHASES[0]], net.green_max, places=9)
        for pid in MODEL_PHASES[1:]:
            self.assertAlmostEqual(values[pid], net.green_min, places=9)
        self.assertAlmostEqual(sum(values.values()), net.effective_green_total, places=9)

    def test_the_primary_box_is_reachable_at_both_ends(self) -> None:
        net = self.net
        self.assertAlmostEqual(clamp_primary_green(net, -1.0e6), net.green_min, places=9)
        self.assertAlmostEqual(clamp_primary_green(net, 1.0e6), net.green_max, places=9)

    def test_distribution_always_conserves_the_budget_and_the_box(self) -> None:
        net = self.net
        for target in (0.0, net.green_min, 40.0, 60.0, net.green_max, 1.0e6):
            with self.subTest(target=target):
                values = distribute_phase_green(net, target)
                self.assertAlmostEqual(
                    sum(values.values()), net.effective_green_total, places=9
                )
                for pid, green in values.items():
                    self.assertGreaterEqual(green, net.green_min - 1.0e-9, pid)
                    self.assertLessEqual(green, net.green_max + 1.0e-9, pid)

    def test_allocation_by_pressure_conserves_the_budget_and_the_box(self) -> None:
        net = self.net
        cases = (
            {"p1": 1.0, "p2": 0.0, "p3": 0.0, "p4": 0.0},
            {"p1": 0.0, "p2": 0.0, "p3": 0.0, "p4": 0.0},
            {"p1": 3.0, "p2": 1.0, "p3": 5.0, "p4": 2.0},
        )
        for scores in cases:
            with self.subTest(scores=scores):
                values = allocate_phase_green(net, scores)
                self.assertEqual(set(values), set(MODEL_PHASES))
                self.assertAlmostEqual(
                    sum(values.values()), net.effective_green_total, places=9
                )
                for pid, green in values.items():
                    self.assertGreaterEqual(green, net.green_min - 1.0e-9, pid)
                    self.assertLessEqual(green, net.green_max + 1.0e-9, pid)


class CycleWindowTests(unittest.TestCase):
    """네 창이 겹치지 않고 clearance 를 사이에 두고 주기를 정확히 채운다."""

    def setUp(self) -> None:
        self.cfg = _config()
        reset_cycle_length_fallback_counts()
        self.control = ControlAction.fixed(self.cfg)
        self.signal = self.cfg.network.signals[0]

    def test_phase_starts_are_green_plus_clearance_cumulative(self) -> None:
        net = self.cfg.network
        greens = {pid: net.default_phase_green for pid in MODEL_PHASES}
        starts = phase_start_offsets(net, greens)
        clearance = net.lost_time / net.num_phases
        self.assertEqual(clearance, 3.0)
        for index, pid in enumerate(MODEL_PHASES):
            self.assertAlmostEqual(
                starts[pid], index * (net.default_phase_green + clearance), places=9
            )
        last = MODEL_PHASES[-1]
        self.assertAlmostEqual(
            starts[last] + greens[last] + clearance, net.cycle_length, places=9
        )

    def _served_green_sec_per_cycle(self) -> float:
        cfg = self.cfg
        t_u = cfg.simulation.T_u_sec
        cycle = cfg.network.cycle_length
        substeps = int(round(cycle / t_u))
        self.assertAlmostEqual(substeps * t_u, cycle, places=9)
        total = 0.0
        for index in range(substeps):
            for pid in MODEL_PHASES:
                total += _phase_green_fraction(
                    self.control, cfg, {"phase": f"{self.signal}_{pid}"}, index
                ) * t_u
        return total

    def test_the_four_windows_leave_no_dark_time(self) -> None:
        net = self.cfg.network
        served = self._served_green_sec_per_cycle()
        self.assertAlmostEqual(served, net.effective_green_total, places=9)
        dark = net.cycle_length - served - net.lost_time
        self.assertAlmostEqual(dark, 0.0, places=9)

    def test_the_cycle_average_branch_matches_the_budget_over_the_cycle(self) -> None:
        cfg = self.cfg
        net = cfg.network
        coverage = sum(
            _phase_green_fraction(self.control, cfg, {"phase": f"{self.signal}_{pid}"})
            for pid in MODEL_PHASES
        )
        self.assertAlmostEqual(
            coverage, net.effective_green_total / net.cycle_length, places=12
        )

    def test_a_lopsided_split_still_fills_the_cycle_without_overlap(self) -> None:
        """주 현시를 상한까지 밀어도 창이 안 겹치고 암흑시간이 0 이다."""
        net = self.cfg.network
        for pid, green in distribute_phase_green(net, net.green_max).items():
            self.control.green_times[f"{self.signal}_{pid}"] = green
        served = self._served_green_sec_per_cycle()
        self.assertAlmostEqual(served, net.effective_green_total, places=9)


if __name__ == "__main__":
    unittest.main()
