# v3 W6 - 지연 0 주입 3경로. 차량이 진입한 substep 에 곧바로 도착하지 않음을 고정한다
"""주입된 차량이 같은 substep 에 정지선/램프에 도달하면 순간이동이다.

세 경로가 모두 지연 0 이었다(`urban_queue_model.py`).

  1. boundary_in 게이트 수요   `_schedule` 없이 `urban_movement_queue` 에 즉시 가산
  2. 외생 on-ramp 수요         동일 — 같은 substep 에 green 으로 freeway ramp 저수지까지 감
  3. off-ramp 유입             `schedule_offramp_arrivals` 가 `urban_step_index` 를 받고도
                               본문에서 쓰지 않아 같은 substep 의 `_drain_offramp_storage`
                               가 그대로 뺄 수 있음

검증은 "도착한 차량" 의 차분으로 한다. 절대량이 아니라 **같은 초기상태에서 수요만 다른
두 런의 차이**를 보므로 green 위상·용량 제약과 무관하게 주입 즉시성만 잡힌다.
"""

from __future__ import annotations

import unittest

from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    ensure_urban_state,
    schedule_offramp_arrivals,
    urban_substep,
)


# cycle 120 s / T_u 5 s = 24 substep. 한 cycle 을 다 돌면 green 위상 전체를 밟는다.
CYCLE_SUBSTEPS = 24


def _zero_demand(cfg: ExperimentConfig) -> DemandStep:
    net = cfg.network
    return DemandStep(
        freeway_mainline={link: 0.0 for link in net.freeway_links},
        urban_boundary={link: 0.0 for link in net.boundary_in_links},
        ramp_arrival={ramp: 0.0 for ramp in net.ramps},
    )


def _landed_veh(state: TrafficState, net) -> float:
    """이미 "도착한" 차량[veh] — movement 큐 + urban 링크 점유 + freeway ramp 저수지.

    주행 지연 버퍼(아직 정지선/램프에 닿지 않은 차량)는 일부러 뺀다. 지연이 있으면 주입
    substep 에 이 값이 늘어나면 안 되고, 지연이 끝나면 늘어나야 한다.
    """
    total = float(sum(state.urban_movement_queue.values()))
    total += float(sum(state.ramp_queue.values()))
    for link, capacity in net.urban_link_storage_veh.items():
        total += max(0.0, capacity - state.urban_link_storage.get(link, capacity))
    return float(total)


class InjectionDelayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.net = self.cfg.network
        self.control = ControlAction.uncontrolled(self.cfg)
        self.zero = _zero_demand(self.cfg)

    def _landed_series(self, first_step_demand: DemandStep, steps: int) -> list[float]:
        """수요를 step 0 에만 주고 `steps` 번 전진하며 매 substep 의 landed 를 기록한다.

        landed 에 boundary_out sink 누적을 더한다. 도착한 차량 중 일부는 곧바로 출구
        링크(예: `in_A_top`→`A_N_to_W`→`A_left_out`)로 빠져 시스템을 떠나므로(실측: 1.0 veh
        중 0.25 veh 가 step 8 에 이탈) landed 만 보면 도착분을 과소평가한다.
        """
        state = TrafficState.initial(self.cfg)
        ensure_urban_state(state, self.cfg)
        series = []
        cumulative_sink = 0.0
        for step in range(steps):
            demand = first_step_demand if step == 0 else self.zero
            _, diagnostics = urban_substep(
                state, self.control, demand, self.cfg, urban_step_index=step
            )
            cumulative_sink += diagnostics.get("boundary_out_sink_veh", 0.0)
            series.append(_landed_veh(state, self.net) + cumulative_sink)
        return series

    def _assert_delayed_then_landed(self, demand: DemandStep, arrival_veh: float) -> None:
        with_demand = self._landed_series(demand, CYCLE_SUBSTEPS)
        baseline = self._landed_series(self.zero, CYCLE_SUBSTEPS)
        diff = [a - b for a, b in zip(with_demand, baseline)]

        self.assertAlmostEqual(
            diff[0],
            0.0,
            places=9,
            msg=f"주입 substep 에 이미 {diff[0]:.6f} veh 가 도착했다 — 순간이동",
        )
        self.assertAlmostEqual(
            diff[-1],
            arrival_veh,
            places=6,
            msg=f"한 cycle 안에 도착하지 않았다(마지막 차분 {diff[-1]:.6f} veh)",
        )

    def test_boundary_in_demand_is_delayed(self) -> None:
        origin = self.net.boundary_in_links[0]
        flow_veh_h = 720.0  # substep 당 1.0 veh.
        demand = _zero_demand(self.cfg)
        demand.urban_boundary[origin] = flow_veh_h
        self._assert_delayed_then_landed(demand, flow_veh_h * self.cfg.simulation.T_u_h)

    def test_onramp_exogenous_demand_is_delayed(self) -> None:
        ramp = self.net.ramps[0]
        flow_veh_h = 720.0  # substep 당 1.0 veh.
        demand = _zero_demand(self.cfg)
        demand.ramp_arrival[ramp] = flow_veh_h
        self._assert_delayed_then_landed(demand, flow_veh_h * self.cfg.simulation.T_u_h)

    def test_offramp_arrival_is_not_drainable_same_substep(self) -> None:
        off_ramp = self.net.off_ramps[0]
        key = f"offramp_departures_{off_ramp}_veh"
        for step in range(CYCLE_SUBSTEPS):
            with self.subTest(step=step):
                state = TrafficState.initial(self.cfg)
                ensure_urban_state(state, self.cfg)
                accepted, rejected = schedule_offramp_arrivals(
                    state, self.cfg, off_ramp, 60.0, step
                )
                self.assertAlmostEqual(accepted, 60.0)
                self.assertAlmostEqual(rejected, 0.0)
                _, diagnostics = urban_substep(
                    state, self.control, self.zero, self.cfg, urban_step_index=step
                )
                self.assertAlmostEqual(
                    diagnostics.get(key, 0.0),
                    0.0,
                    places=9,
                    msg="적재한 substep 에 그대로 방출됐다 — 램프 주행시간이 0",
                )

    def test_offramp_arrival_drains_after_the_delay(self) -> None:
        """비어있음 방지 — 지연이 무한대가 아니라 한 cycle 안에 방출돼야 한다."""
        off_ramp = self.net.off_ramps[0]
        key = f"offramp_departures_{off_ramp}_veh"
        state = TrafficState.initial(self.cfg)
        ensure_urban_state(state, self.cfg)
        schedule_offramp_arrivals(state, self.cfg, off_ramp, 60.0, 0)
        released = 0.0
        for step in range(CYCLE_SUBSTEPS):
            _, diagnostics = urban_substep(
                state, self.control, self.zero, self.cfg, urban_step_index=step
            )
            released += diagnostics.get(key, 0.0)
        self.assertGreater(released, 0.0)


if __name__ == "__main__":
    unittest.main()
