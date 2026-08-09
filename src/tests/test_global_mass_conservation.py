# v3 N2 - control interval 전역 질량 항등식. 차량이 생기거나 사라지지 않음을 고정한다
"""`N_close = N_open + accepted_external − sink_out` 을 시나리오별로 검증한다.

이것이 N2 의 최상위 수용 기준이다. 스톡을 아무리 잘 분해해도 전역 항등식이 깨지면
질량 회계는 의미가 없다.

유입 세 갈래와 유출 두 갈래를 모두 세야 한다. 하나라도 빠지면 잔차가 상수로 남는다 —
실측으로 `freeway_mainline` 을 빠뜨렸을 때 매 스텝 194.49 veh 의 상수 잔차가 나왔고,
그 값은 정확히 `sum(freeway_mainline) × T_c_h` 였다.

  유입  urban_demand_arrivals_veh      urban 경계 수요
        onramp_arrivals_veh            램프 수요
        freeway_mainline × T_c_h       본선 원점 수요
  유출  boundary_out_sink_veh          urban 경계 이탈
        mainline_exit_flow_total × T_c_h   본선 하류 이탈

`mainline_exit_flow_total` 은 `_aggregate_freeway_diagnostics` 의 `avg_keys` 라 substep
평균 유량[veh/h]이다. 합이 아니므로 `T_c_h` 를 곱해야 대수가 맞는다.
"""

from __future__ import annotations

import unittest

from src.models.demand import DemandProfile, load_scenarios
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator


# 정상 / urban 포화 / 고수요 포화. 포화 계열을 넣는 이유는 storage 클리핑과 수용 거부가
# 그때만 발동하기 때문이다(sweet_115 만으로는 그 경로를 한 번도 밟지 않는다).
SCENARIOS = ("sweet_115", "urban_gridlock", "sweet_220")
STEPS = 24
TOLERANCE_VEH = 1.0e-6


class GlobalMassConservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.net = self.cfg.network
        self.interval_h = self.cfg.simulation.T_c_h
        self.scenarios = load_scenarios("src/config/scenarios.yaml")

    def _residuals(self, scenario: str, measure=None) -> list[float]:
        measure = measure or (lambda state: state.total_physical_vehicles(self.net))
        profile = DemandProfile(self.cfg, self.scenarios[scenario])
        sim = MixedTrafficSimulator(self.cfg)
        control = ControlAction.uncontrolled(self.cfg)
        residuals = []
        for step in range(STEPS):
            opening = measure(sim.state)
            demand = profile.at(step)
            diagnostics = sim.step(control, demand, step).diagnostics
            closing = measure(sim.state)

            accepted_external = (
                diagnostics.get("urban_demand_arrivals_veh", 0.0)
                + diagnostics.get("onramp_arrivals_veh", 0.0)
                + sum(demand.freeway_mainline.values()) * self.interval_h
            )
            sink_out = (
                diagnostics.get("boundary_out_sink_veh", 0.0)
                + diagnostics.get("mainline_exit_flow_total", 0.0) * self.interval_h
            )
            residuals.append((closing - opening) - (accepted_external - sink_out))
        return residuals

    def test_no_vehicle_is_created_or_destroyed(self) -> None:
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                residuals = self._residuals(scenario)
                worst = max(abs(value) for value in residuals)
                self.assertLessEqual(
                    worst,
                    TOLERANCE_VEH,
                    f"{scenario}: 최대 질량 잔차 {worst:.3e} veh",
                )

    def test_saturating_scenarios_actually_load_the_network(self) -> None:
        """포화 시나리오가 실제로 포화하지 않으면 위 테스트는 아무것도 증명하지 않는다."""
        profile = DemandProfile(self.cfg, self.scenarios["urban_gridlock"])
        sim = MixedTrafficSimulator(self.cfg)
        control = ControlAction.uncontrolled(self.cfg)
        for step in range(STEPS):
            sim.step(control, profile.at(step), step)

        # 초기 428 veh 대비 10배 이상 쌓여야 저장용량 경로를 밟았다고 본다(실측 4677 veh).
        self.assertGreater(sim.state.total_physical_vehicles(self.net), 4000.0)

    def test_pre_fix_measure_breaks_the_identity(self) -> None:
        """되돌림 증명 — 수정 전 정의로는 이 항등식이 반드시 깨져야 한다.

        `5018c28` 이전의 `total_physical_vehicles` 는 `urban + freeway` 였고 off-ramp 램프
        storage 를 어디에서도 세지 않았다. 그 정의로 같은 잔차를 계산하면 27~50 veh 가 남는다.

        이 테스트가 없으면 위 테스트는 "원래 통과하는 항등식" 과 구별되지 않는다. 여기서
        수정 전 정의를 직접 재현해 두면 되돌림 증명이 저장소에 영구히 남는다 — git stash 로
        코드를 물리적으로 되돌려 볼 필요가 없다.
        """
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                residuals = self._residuals(
                    scenario,
                    measure=lambda state: (
                        state.total_urban_vehicles(self.net)
                        + state.total_freeway_vehicles(self.net)
                    ),
                )
                worst = max(abs(value) for value in residuals)
                self.assertGreater(
                    worst,
                    1.0,
                    f"{scenario}: 수정 전 정의인데 잔차가 {worst:.3e} veh 밖에 안 된다 — "
                    "off-ramp storage 회계가 다른 곳에서 바뀌었는지 확인하라",
                )
