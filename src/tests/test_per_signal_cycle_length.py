# v3 N4-1 - SC별 고유 주기(cycle_length_by_signal)와 폴백 진단 카운터를 고정한다
"""전역 스칼라 주기 하나를 신호별 주기로 쪼갠다.

## 왜

모델은 `NetworkConfig.cycle_length = 120.0` 하나뿐인데 개포동 실망의 native 주기는
100 / 140 / 150 / 160 / 170 s 이고 **120 s 는 하나도 없다**(실측:
VISSIM/outputs/signal_group_timing_v3.json, 제어 15 SC 는 140/150/160/170 네 종).
주기가 틀리면 `_phase_green_fraction` 의 green 분율 g/C 가 통째로 틀어진다.

## 계약

램프 상한(`ramp_queue_max_veh` + `ramp_queue_max_veh_by_ramp` + `ramp_queue_cap()`)과
같은 모양이다.

    스칼라 cycle_length + dict cycle_length_by_signal + 헬퍼 signal_cycle_length()

- 매핑이 **비면** 스칼라로 폴백하고 기존 거동과 **비트 동일**해야 한다(legacy 모드).
- 매핑이 **비어 있지 않은데** 신호가 빠지면 그것은 결선 실수다. 스칼라로 떨어지되
  진단 카운터에 남긴다 — 계획이 production fallback 0 을 요구하므로 세지 않으면
  확인할 수 없다.
"""

from __future__ import annotations

import unittest

from src.models.state import (
    ControlAction,
    ExperimentConfig,
    cycle_length_fallback_counts,
    reset_cycle_length_fallback_counts,
)
from src.models.urban_queue_model import _phase_green_fraction, movement_specs


def _config() -> ExperimentConfig:
    return ExperimentConfig.from_file("src/config/default.yaml")


class SignalCycleLengthHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = _config()
        reset_cycle_length_fallback_counts()

    def test_empty_mapping_returns_the_scalar_bit_identically(self) -> None:
        net = self.cfg.network
        self.assertEqual(net.cycle_length_by_signal, {})
        for signal in net.signals:
            self.assertEqual(net.signal_cycle_length(signal), net.cycle_length)

    def test_mapped_signal_returns_its_own_cycle(self) -> None:
        net = self.cfg.network
        net.cycle_length_by_signal = {"A": 150.0, "B": 170.0}
        self.assertEqual(net.signal_cycle_length("A"), 150.0)
        self.assertEqual(net.signal_cycle_length("B"), 170.0)

    def test_missing_signal_in_a_nonempty_mapping_falls_back_to_the_scalar(self) -> None:
        net = self.cfg.network
        net.cycle_length_by_signal = {"A": 150.0}
        self.assertEqual(net.signal_cycle_length("C"), net.cycle_length)


class FallbackDiagnosticsTests(unittest.TestCase):
    """폴백을 셀 수 있어야 production fallback 0 을 확인할 수 있다."""

    def setUp(self) -> None:
        self.cfg = _config()
        reset_cycle_length_fallback_counts()

    def test_a_fallback_inside_a_nonempty_mapping_is_counted_per_signal(self) -> None:
        net = self.cfg.network
        net.cycle_length_by_signal = {"A": 150.0}
        net.signal_cycle_length("C")
        net.signal_cycle_length("C")
        net.signal_cycle_length("D")
        net.signal_cycle_length("A")
        self.assertEqual(cycle_length_fallback_counts(), {"C": 2, "D": 1})

    def test_legacy_scalar_mode_is_not_counted_as_a_fallback(self) -> None:
        """매핑이 통째로 비면 legacy 스칼라 모드다 — 신호별 결선 누락이 아니다.

        여기서 세면 실 config 1 회 solve 에 129 만 건이 쌓여 진단이 무의미해지고
        핫패스(`_phase_green_fraction`)에 dict 쓰기가 들어간다."""
        net = self.cfg.network
        for signal in net.signals:
            net.signal_cycle_length(signal)
        self.assertEqual(cycle_length_fallback_counts(), {})

    def test_the_counter_snapshot_is_a_copy(self) -> None:
        net = self.cfg.network
        net.cycle_length_by_signal = {"A": 150.0}
        net.signal_cycle_length("C")
        snapshot = cycle_length_fallback_counts()
        snapshot["C"] = 999
        self.assertEqual(cycle_length_fallback_counts(), {"C": 1})


class PhaseGreenFractionUsesPerSignalCycleTests(unittest.TestCase):
    """`_phase_green_fraction` 의 g/C 가 신호별 C 를 쓰는지가 이 작업의 본체다."""

    def setUp(self) -> None:
        self.cfg = _config()
        reset_cycle_length_fallback_counts()
        self.control = ControlAction.fixed(self.cfg)
        self.control.green_times["A_p1"] = 60.0
        self.control.green_times["A_p2"] = 40.0
        self.control.green_times["B_p1"] = 60.0
        self.control.green_times["B_p2"] = 40.0

    def test_cycle_average_branch_divides_by_the_signals_own_cycle(self) -> None:
        net = self.cfg.network
        self.assertEqual(net.cycle_length, 120.0)
        net.cycle_length_by_signal = {"A": 240.0}
        # A 는 240 s 주기 -> 60/240, 매핑에 없는 B 는 스칼라 120 s -> 60/120.
        self.assertEqual(_phase_green_fraction(self.control, self.cfg, {"phase": "A_p1"}), 0.25)
        self.assertEqual(_phase_green_fraction(self.control, self.cfg, {"phase": "B_p1"}), 0.5)

    def test_offset_aware_branch_uses_the_signals_own_cycle(self) -> None:
        """substep 겹침 분율도 신호별 C 로 감긴다 — 주기가 길면 green window 위치가 다르다."""
        net = self.cfg.network
        net.cycle_length_by_signal = {"A": 240.0}
        self.control.offsets["A"] = 0.0
        t_u = self.cfg.simulation.T_u_sec
        # C=240, p1 green = [0, 60). C=120 이었다면 p1 green 도 [0, 60) 로 같지만,
        # 한 주기 뒤 substep 은 갈린다: t=120 s 는 C=120 에서 green, C=240 에서 red.
        index = int(round(120.0 / t_u))
        self.assertEqual(
            _phase_green_fraction(self.control, self.cfg, {"phase": "A_p1"}, index), 0.0
        )
        self.assertEqual(
            _phase_green_fraction(self.control, self.cfg, {"phase": "B_p1"}, index), 1.0
        )

    def test_a_phase_whose_signal_is_missing_from_a_nonempty_mapping_is_counted(self) -> None:
        self.cfg.network.cycle_length_by_signal = {"A": 240.0}
        _phase_green_fraction(self.control, self.cfg, {"phase": "B_p1"})
        self.assertEqual(cycle_length_fallback_counts(), {"B": 1})

    def test_an_empty_phase_still_short_circuits_without_touching_the_counter(self) -> None:
        self.cfg.network.cycle_length_by_signal = {"A": 240.0}
        self.assertEqual(_phase_green_fraction(self.control, self.cfg, {"phase": ""}), 1.0)
        self.assertEqual(cycle_length_fallback_counts(), {})


class EmptyMappingIsBitIdenticalTests(unittest.TestCase):
    """되돌림 증명 — 매핑이 비면 실 spec 전수에서 옛 산식과 비트 동일해야 한다."""

    def setUp(self) -> None:
        self.cfg = _config()
        reset_cycle_length_fallback_counts()
        self.specs = movement_specs(self.cfg)
        self.control = ControlAction.fixed(self.cfg)

    def _legacy(self, spec, urban_step_index):
        """전역 스칼라만 쓰던 이전 구현을 그대로 옮긴 참조."""
        net = self.cfg.network
        phase = str(spec.get("phase", ""))
        if not phase:
            return 1.0
        default_green = net.effective_green_total / 2.0
        green_sec = float(self.control.green_times.get(phase, default_green))
        cycle = max(net.cycle_length, 1.0e-9)
        if urban_step_index is None:
            return min(max(green_sec / cycle, 0.0), 1.0)
        signal, _, phase_id = phase.rpartition("_")
        g1 = float(self.control.green_times.get(f"{signal}_p1", default_green))
        half_lost = max(0.0, net.lost_time) / 2.0
        start = 0.0 if phase_id == "p1" else g1 + half_lost
        end = min(start + green_sec, cycle)
        offset = float(self.control.offsets.get(signal, 0.0))
        t_u = self.cfg.simulation.T_u_sec
        t0 = (urban_step_index * t_u - offset) % cycle

        def seg(a0, a1, b0, b1):
            return max(0.0, min(a1, b1) - max(a0, b0))

        overlap = seg(t0, min(t0 + t_u, cycle), start, end)
        if t0 + t_u > cycle:
            overlap += seg(0.0, t0 + t_u - cycle, start, end)
        return min(max(overlap / max(t_u, 1.0e-9), 0.0), 1.0)

    def test_every_movement_and_substep_matches_the_legacy_formula_exactly(self) -> None:
        self.assertEqual(self.cfg.network.cycle_length_by_signal, {})
        for movement, spec in self.specs.items():
            for index in (None, 0, 1, 7, 12, 23, 24, 47, 100):
                with self.subTest(movement=movement, step=index):
                    self.assertEqual(
                        _phase_green_fraction(self.control, self.cfg, spec, index),
                        self._legacy(spec, index),
                    )

    def test_the_default_green_fallback_also_matches_when_green_times_are_absent(self) -> None:
        """green_times 가 비어 default_green(=effective_green_total/2)으로 떨어지는 경로."""
        bare = ControlAction(green_times={}, offsets={})
        for spec in self.specs.values():
            phase = str(spec.get("phase", ""))
            if not phase:
                continue
            net = self.cfg.network
            expected = min(max((net.effective_green_total / 2.0) / max(net.cycle_length, 1.0e-9), 0.0), 1.0)
            self.assertEqual(_phase_green_fraction(bare, self.cfg, spec), expected)


class ConfigLoadingTests(unittest.TestCase):
    def test_the_mapping_round_trips_through_from_dict(self) -> None:
        cfg = ExperimentConfig.from_dict({"network": {"cycle_length_by_signal": {"SC1001": 150.0}}})
        self.assertEqual(cfg.network.signal_cycle_length("SC1001"), 150.0)


class MassConservationUnderPerSignalCyclesTests(unittest.TestCase):
    """매핑이 **채워진** 경로에서도 전역 질량 항등식이 성립해야 한다.

    빈 매핑 경로는 비트 동일이라 `test_global_mass_conservation` 이 이미 지킨다. 정작
    N4-2 가 굴릴 경로는 채워진 쪽이므로 여기서 따로 고정한다. 항등식은
    `N_close = N_open + accepted_external − sink_out`(같은 테스트의 계약).
    """

    def test_no_vehicle_is_created_or_destroyed_when_every_signal_has_its_own_cycle(self) -> None:
        from src.models.demand import DemandProfile, load_scenarios
        from src.simulation.simulator import MixedTrafficSimulator

        cfg = _config()
        # 실측 native 주기(140/150/160/170)를 5 신호에 돌려 붙인다. 120 은 일부러 안 쓴다.
        natives = [140.0, 150.0, 160.0, 170.0]
        cfg.network.cycle_length_by_signal = {
            signal: natives[i % len(natives)] for i, signal in enumerate(cfg.network.signals)
        }
        reset_cycle_length_fallback_counts()

        scenarios = load_scenarios("src/config/scenarios.yaml")
        interval_h = cfg.simulation.T_c_h
        for scenario in ("sweet_115", "urban_gridlock"):
            with self.subTest(scenario=scenario):
                profile = DemandProfile(cfg, scenarios[scenario])
                sim = MixedTrafficSimulator(cfg)
                control = ControlAction.uncontrolled(cfg)
                worst = 0.0
                for step in range(24):
                    opening = sim.state.total_physical_vehicles(cfg.network)
                    demand = profile.at(step)
                    diagnostics = sim.step(control, demand, step).diagnostics
                    closing = sim.state.total_physical_vehicles(cfg.network)
                    accepted = (
                        diagnostics.get("urban_demand_arrivals_veh", 0.0)
                        + diagnostics.get("onramp_arrivals_veh", 0.0)
                        + sum(demand.freeway_mainline.values()) * interval_h
                    )
                    sink = (
                        diagnostics.get("boundary_out_sink_veh", 0.0)
                        + diagnostics.get("mainline_exit_flow_total", 0.0) * interval_h
                    )
                    worst = max(worst, abs((closing - opening) - (accepted - sink)))
                self.assertLessEqual(worst, 1.0e-6, f"{scenario}: 최대 질량 잔차 {worst:.3e} veh")

        # 모든 신호가 매핑에 있으므로 폴백은 0 이어야 한다(production 계약과 같은 검사).
        self.assertEqual(cycle_length_fallback_counts(), {})


if __name__ == "__main__":
    unittest.main()
