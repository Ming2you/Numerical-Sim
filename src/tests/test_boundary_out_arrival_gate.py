# v3 N3-2 - boundary_out 출구 게이트가 "링크 끝에 도착한" 차량만 이탈시키는지 고정한다
"""출구 게이트가 링크 주행을 건너뛰던 결함을 고정한다.

`urban_substep` 의 출구 게이트는 sink 링크에서 `min(점유, exit_cap*dt)` 를 이탈시켰다.
점유(cap-available)에는 **방금 링크에 진입해 아직 끝까지 못 간 차량**이 포함된다
(`urban_storage_release_buffer` 에 미래 substep 도착으로 예약된 몫). 그래서 진입 즉시
출구로 빠져나가 링크 통행시간이 과소평가됐다 - 질량은 보존되지만 물리가 틀린다.

W6 이 off-ramp 에 쓴 것과 같은 구조로 고친다. `offramp_transit_buffer` 가 램프 주행 중인
몫을 방출 후보에서 빼듯, 출구 게이트도 `urban_storage_release_buffer` 에 남아 있는
미래 도착 예약분을 점유에서 뺀 뒤 게이트를 건다.

여기서 고정하는 것.
  1. 주행 중인 몫은 이탈하지 않는다 (도착 예약 substep 전).
  2. 되돌림 증명 - 같은 차량을 "도착함" 으로 예약하면 같은 substep 에 exit_cap 만큼 이탈한다.
     고치기 전에는 (1) 과 (2) 가 같은 값을 냈다. 둘이 갈리는 것이 곧 수정의 증거다.
  3. 주행 중인 차량은 사라지지 않는다 (점유·예약 모두 보존).
  4. 목적함수 모드(leader.objective_mode / state_accumulation_exclude_boundary_legs)는
     물리 trace 를 바꾸지 않고, 목적함수 차이는 기록된 경계 기여분과 정확히 같다.
"""

from __future__ import annotations

import unittest

from src.controllers.leader import Leader
from src.models import urban_queue_model as uqm
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState

CONFIG_PATH = "src/config/default.yaml"
SINK_LINK = "A_top_out"      # boundary_out 링크 out_A_top 로 나가는 storage 링크
INJECTED_VEH = 100.0
FUTURE_ARRIVAL_STEP = 6      # 아직 링크 끝에 닿지 않은 예약 시각


def _empty_state(cfg: ExperimentConfig) -> TrafficState:
    """모든 정지선 큐·램프 큐가 비고 모든 링크가 빈 초기 상태."""
    state = TrafficState.initial(cfg)
    uqm.ensure_urban_state(state, cfg)
    for movement in state.urban_movement_queue:
        state.urban_movement_queue[movement] = 0.0
    for ramp in state.ramp_queue:
        state.ramp_queue[ramp] = 0.0
    return state


class BoundaryOutArrivalGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file(CONFIG_PATH)
        self.control = ControlAction.fixed(self.cfg)
        # 외생 수요 0 - 출구 유량이 주입한 차량에서만 나오게 한다.
        self.demand = DemandProfile(
            self.cfg,
            ScenarioConfig("exit_gate", urban_scale=0.0, freeway_scale=0.0, ramp_scale=0.0),
        ).at(0)
        self.capacity = float(self.cfg.network.urban_link_storage_veh[SINK_LINK])
        self.exit_cap_veh = float(
            self.cfg.network.boundary_out_capacity_veh_h * self.cfg.simulation.T_u_h
        )
        self.assertIn(SINK_LINK, uqm.sink_storage_links(self.cfg))
        self.assertGreater(self.exit_cap_veh, 0.0)
        # 무대 전제 - 주입량이 exit_cap 보다 훨씬 커야 "cap 만큼 나갔다" 가 의미를 갖는다.
        self.assertGreater(INJECTED_VEH, self.exit_cap_veh)

    def _state_with_sink_load(self, arrival_step: int) -> TrafficState:
        """sink 링크에 INJECTED_VEH 를 적재하고 링크 끝 도착을 arrival_step 으로 예약한다.

        `urban_substep` 이 내부 movement 를 sink 링크로 보낼 때 하는 것과 같다
        (점유 생성 + `urban_storage_release_buffer` 예약, urban_queue_model.py:1100-1110).
        """
        state = _empty_state(self.cfg)
        state.urban_link_storage[SINK_LINK] = self.capacity - INJECTED_VEH
        state.urban_storage_release_buffer[SINK_LINK] = {arrival_step: INJECTED_VEH}
        return state

    def _sink_veh(self, state: TrafficState, step_idx: int) -> float:
        _, diagnostics = uqm.urban_substep(
            state, self.control, self.demand, self.cfg, urban_step_index=step_idx
        )
        return float(diagnostics["boundary_out_sink_veh"])

    def test_in_transit_vehicles_do_not_exit(self) -> None:
        """아직 링크를 주행 중인 차량은 출구로 나가지 않는다."""
        state = self._state_with_sink_load(FUTURE_ARRIVAL_STEP)
        departed = self._sink_veh(state, step_idx=0)
        self.assertEqual(
            departed,
            0.0,
            f"주행 중인 차량이 출구로 빠져나갔다: {departed} veh",
        )

    def test_arrived_vehicles_exit_at_the_exit_capacity(self) -> None:
        """되돌림 증명 - 같은 차량을 "도착함" 으로 두면 exit_cap 만큼 이탈한다.

        수정 전에는 위 테스트도 이 값을 냈다(주행 중/도착 구분이 없었다).
        """
        state = self._state_with_sink_load(0)
        departed = self._sink_veh(state, step_idx=0)
        self.assertAlmostEqual(departed, self.exit_cap_veh, places=9)

    def test_in_transit_vehicles_are_not_lost(self) -> None:
        """주행 중인 차량은 사라지지 않는다 - 점유도 예약도 그대로다."""
        state = self._state_with_sink_load(FUTURE_ARRIVAL_STEP)
        self._sink_veh(state, step_idx=0)
        occupancy = self.capacity - state.urban_link_storage[SINK_LINK]
        self.assertAlmostEqual(occupancy, INJECTED_VEH, places=9)
        self.assertAlmostEqual(
            state.urban_storage_release_buffer[SINK_LINK].get(FUTURE_ARRIVAL_STEP, 0.0),
            INJECTED_VEH,
            places=9,
        )

    def test_exit_starts_only_at_the_scheduled_arrival_step(self) -> None:
        """도착 예약 substep 이 되기 전까지 출구 유량은 0 이고, 그 뒤로 cap 만큼 흐른다."""
        state = self._state_with_sink_load(FUTURE_ARRIVAL_STEP)
        trace = [self._sink_veh(state, step_idx=k) for k in range(FUTURE_ARRIVAL_STEP + 3)]
        before = trace[:FUTURE_ARRIVAL_STEP]
        after = trace[FUTURE_ARRIVAL_STEP:]
        self.assertEqual(
            before,
            [0.0] * FUTURE_ARRIVAL_STEP,
            f"도착 전 substep 에서 출구 유량이 생겼다: {before}",
        )
        for departed in after:
            self.assertAlmostEqual(departed, self.exit_cap_veh, places=9)

    def test_every_boundary_out_link_is_a_finite_stock(self) -> None:
        """출구 커버리지 - boundary_out 링크마다 유한 용량 sink storage 가 하나씩 있다."""
        net = self.cfg.network
        sinks = uqm.sink_storage_links(self.cfg)
        self.assertEqual(len(sinks), len(net.boundary_out_links))
        for link in sinks:
            capacity = net.urban_link_storage_veh.get(link)
            self.assertIsNotNone(capacity, f"sink 링크 {link} 에 storage 용량이 없다")
            self.assertGreater(float(capacity), 0.0, link)
        self.assertGreater(float(net.boundary_out_capacity_veh_h), 0.0)


class ObjectiveModeDoesNotChangePhysicsTests(unittest.TestCase):
    """목적함수 모드는 같은 물리 trace 에 다른 가중치만 적용한다(N3-2)."""

    STEPS = 24

    def setUp(self) -> None:
        self.base_cfg = ExperimentConfig.from_file(CONFIG_PATH)

    def _trace(self, cfg: ExperimentConfig) -> list[tuple]:
        control = ControlAction.fixed(cfg)
        profile = DemandProfile(cfg, ScenarioConfig("objective_mode", urban_scale=1.0))
        state = TrafficState.initial(cfg)
        uqm.ensure_urban_state(state, cfg)
        trace: list[tuple] = []
        for step in range(self.STEPS):
            demand = profile.at(step * cfg.simulation.T_u_sec)
            _, diagnostics = uqm.urban_substep(
                state, control, demand, cfg, urban_step_index=step
            )
            trace.append((
                tuple(sorted(state.urban_movement_queue.items())),
                tuple(sorted(state.urban_link_storage.items())),
                tuple(sorted(state.ramp_queue.items())),
                float(diagnostics["urban_total_departures_veh"]),
                float(diagnostics["boundary_out_sink_veh"]),
                float(diagnostics["inbound_service_veh"]),
                float(diagnostics["outbound_service_veh"]),
            ))
        return trace

    def _objective_variants(self) -> list[ExperimentConfig]:
        return [
            self.base_cfg.with_updates({"leader": {
                "objective_mode": mode,
                "state_accumulation_exclude_boundary_legs": exclude,
            }})
            for mode in ("follower_ttt", "state_accumulation")
            for exclude in (True, False)
        ]

    def test_physics_trace_is_identical_across_objective_modes(self) -> None:
        traces = [self._trace(cfg) for cfg in self._objective_variants()]
        # 무대 전제 - trace 가 실제로 움직여야 "동일" 이 의미를 갖는다.
        self.assertGreater(traces[0][-1][3], 0.0, "서비스량이 0 이라 비교가 공허하다")
        self.assertGreater(traces[0][-1][4], 0.0, "출구 유량이 0 이라 비교가 공허하다")
        for other in traces[1:]:
            self.assertEqual(traces[0], other, "목적함수 모드가 물리 trace 를 바꿨다")

    def test_trace_comparison_detects_a_real_physical_change(self) -> None:
        """비교 장치가 작동함을 증명한다 - 물리 파라미터를 바꾸면 trace 가 갈린다."""
        tighter = self.base_cfg.with_updates(
            {"network": {"boundary_out_capacity_veh_h": 100.0}}
        )
        self.assertNotEqual(self._trace(self.base_cfg), self._trace(tighter))

    def test_objective_difference_equals_recorded_boundary_contribution(self) -> None:
        """목적함수 차이 = 기록된 경계 기여분(1e-9 이내)."""
        cfg_excl = self.base_cfg.with_updates(
            {"leader": {"state_accumulation_exclude_boundary_legs": True}}
        )
        cfg_incl = self.base_cfg.with_updates(
            {"leader": {"state_accumulation_exclude_boundary_legs": False}}
        )
        control = ControlAction.fixed(cfg_excl)
        profile = DemandProfile(cfg_excl, ScenarioConfig("objective_mode", urban_scale=1.0))
        state = TrafficState.initial(cfg_excl)
        uqm.ensure_urban_state(state, cfg_excl)
        for step in range(self.STEPS):
            uqm.urban_substep(
                state,
                control,
                profile.at(step * cfg_excl.simulation.T_u_sec),
                cfg_excl,
                urban_step_index=step,
            )
        states = [state]
        terms_excl = Leader(cfg_excl).objective_terms(states, control, None, 0.0, True)
        terms_incl = Leader(cfg_incl).objective_terms(states, control, None, 0.0, True)
        recorded = terms_excl["leader_boundary_leg_excluded_veh"]
        # 무대 전제 - 경계 기여분이 0 이면 항등식이 공허하다.
        self.assertGreater(recorded, 0.0)
        self.assertAlmostEqual(
            terms_incl["leader_state_accumulation_base"]
            - terms_excl["leader_state_accumulation_base"],
            recorded,
            delta=1.0e-9,
        )


if __name__ == "__main__":
    unittest.main()
