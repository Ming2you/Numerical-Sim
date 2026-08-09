# v3 W-pin(3) - substep 경계를 넘는 추월이 불가능하도록 하는 파라미터 여유를 고정한다
"""링크 주행 지연은 `available` 의 함수라 `available` 이 줄면 지연도 줄어든다.

`_link_delay_steps` (urban_queue_model.py:518-529)
    delay[substep] = max(1, ceil(available · L_veh/1000 / v / T_u))

한 substep 동안 그 링크에 차가 들어오면 `available` 이 줄고, 뒤에 들어온 차량이 더
짧은 지연을 받는다. 그 감소폭이 지연 1 substep 어치를 넘어서면 뒤차가 앞차보다
먼저 도착하는 추월이 생긴다. 이를 막는 충분조건이 아래 여유 부등식이다.

  LHS  한 substep 에 한 링크로 들어올 수 있는 최대 차량수 [veh]
       max_movements_per_link × movement_capacity_veh_h × T_u_h
  RHS  지연 1 substep 에 해당하는 available 폭 [veh]
       urban_avg_speed_km_h × T_u_h × 1000 / urban_avg_vehicle_length_m

실 config(src/config/default.yaml) 실측값.
  max_movements_per_link  = 4      (D_to_E, D_to_A, F_to_E, F_to_C ... 4개 링크)
  movement_capacity_veh_h = 1400.0
  T_u_h                   = 5/3600
  urban_avg_speed_km_h    = 50.0
  urban_avg_vehicle_length_m = 6.0
  LHS = 7.7778 veh,  RHS = 11.5741 veh,  여유 3.7963 veh (LHS/RHS = 0.672)

LHS 가 진짜 상한인 근거는 `_movement_capacity_flow` 가 어떤 control 에서도
`movement_capacity_veh_h` 를 넘지 않고(:593-606) green fraction ≤ 1 이라는 것이다.
그 둘을 아래에서 함께 못 박는다.

되돌림 증명은 지시대로 `movement_capacity_veh_h = 2200` 이다. 다만 **실측상 2200 에서는
부등식만 깨지고 실제 역전은 관측되지 않았다** (urban_gridlock / sweet_220, 200 substep,
역전 0건). 부등식은 충분조건이지 필요조건이 아니고, 실제 유입은 큐 잔량과 receiving
공간에도 걸리기 때문이다. 동작 자체가 깨지는 값은 5000 veh/h 로, 그때 역전이 2건
(최대 1 substep) 실제로 발생한다. 그래서 되돌림 증명을 두 겹으로 둔다 -
부등식은 2200 에서, 동작은 5000 에서.
"""

from __future__ import annotations

import unittest
from collections import defaultdict

from src.models import urban_queue_model as uqm
from src.models.demand import DemandProfile, load_scenarios
from src.models.state import ControlAction, ExperimentConfig, TrafficState

SUBSTEPS = 200
SCENARIO = "urban_gridlock"
REVERSAL_CAPACITY_VEH_H = 2200.0          # 부등식이 깨지는 값 (지시)
BEHAVIOURAL_REVERSAL_CAPACITY_VEH_H = 5000.0   # 실제 역전이 관측되는 값 (실측)


def _max_movements_per_link(cfg: ExperimentConfig) -> int:
    """한 storage 링크를 receiving_link 로 삼는 movement 의 최대 개수."""
    counts: dict[str, int] = defaultdict(int)
    for spec in uqm.movement_specs(cfg).values():
        link = str(spec.get("receiving_link", ""))
        if link and link in cfg.network.urban_link_storage_veh:
            counts[link] += 1
    return max(counts.values())


def _margin(cfg: ExperimentConfig) -> tuple[float, float]:
    net = cfg.network
    dt_h = cfg.simulation.T_u_h
    lhs = _max_movements_per_link(cfg) * net.movement_capacity_veh_h * dt_h
    rhs = net.urban_avg_speed_km_h * dt_h * 1000.0 / net.urban_avg_vehicle_length_m
    return lhs, rhs


def _count_inversions(cfg: ExperimentConfig, steps: int = SUBSTEPS) -> int:
    """substep k 의 최대 도착 substep 이 substep k+1 의 최소 도착 substep 을 넘는 건수.

    `_schedule` 은 차량이 링크에 진입하는 시점에 호출되므로 호출 순서가 곧 진입
    순서다. 같은 substep 안에서는 동시 진입이라 순서를 따지지 않고, substep 경계를
    넘는 역전만 센다.
    """
    original = uqm._schedule
    current = {"substep": 0}
    scheduled: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))

    def spy(buffer, key, step, vehicles):  # noqa: ANN001
        if vehicles > 0.0:
            scheduled[key][current["substep"]].append(step)
        return original(buffer, key, step, vehicles)

    uqm._schedule = spy
    try:
        state = TrafficState.initial(cfg)
        uqm.ensure_urban_state(state, cfg)
        control = ControlAction.fixed(cfg)
        demand = DemandProfile(cfg, load_scenarios("src/config/scenarios.yaml")[SCENARIO]).at(0)
        for substep in range(steps):
            current["substep"] = substep
            uqm.urban_substep(state, control, demand, cfg, urban_step_index=substep)
    finally:
        uqm._schedule = original

    inversions = 0
    for by_substep in scheduled.values():
        keys = sorted(by_substep)
        for earlier, later in zip(keys, keys[1:]):
            if later != earlier + 1:
                continue
            if max(by_substep[earlier]) > min(by_substep[later]):
                inversions += 1
    return inversions


class CrossSubstepFifoMarginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")

    def test_real_config_leaves_margin_below_one_substep_of_delay(self) -> None:
        """실 config 로 양변을 계산해 여유가 있음을 단언한다."""
        lhs, rhs = _margin(self.cfg)
        self.assertLess(
            lhs,
            rhs,
            f"여유 없음 - 한 substep 유입 상한 {lhs:.4f} veh >= 지연 1 substep 폭 {rhs:.4f} veh "
            f"(max_movements_per_link={_max_movements_per_link(self.cfg)}, "
            f"movement_capacity_veh_h={self.cfg.network.movement_capacity_veh_h})",
        )

    def test_movement_capacity_flow_never_exceeds_the_link_parameter(self) -> None:
        """LHS 가 진짜 상한이려면 어떤 movement 도 movement_capacity_veh_h 를 못 넘어야 한다."""
        cap = self.cfg.network.movement_capacity_veh_h
        specs = uqm.movement_specs(self.cfg)
        for control in (ControlAction.fixed(self.cfg), ControlAction.uncontrolled(self.cfg)):
            for movement, spec in specs.items():
                flow = uqm._movement_capacity_flow(control, self.cfg, movement, spec)
                self.assertLessEqual(flow, cap, f"{movement}: cap_flow {flow} > {cap}")

    def test_no_cross_substep_overtaking_in_a_saturated_run(self) -> None:
        """동작 핀 - 포화 주행 200 substep 동안 substep 경계 역전이 0 건이다."""
        self.assertEqual(_count_inversions(self.cfg), 0)

    def test_margin_is_lost_at_2200(self) -> None:
        """되돌림 증명(부등식) - movement_capacity_veh_h 를 2200 으로 올리면 여유가 사라진다."""
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {"network": {"movement_capacity_veh_h": REVERSAL_CAPACITY_VEH_H}},
        )
        self.assertEqual(cfg.network.movement_capacity_veh_h, REVERSAL_CAPACITY_VEH_H)
        lhs, rhs = _margin(cfg)
        self.assertGreaterEqual(
            lhs,
            rhs,
            f"2200 인데도 여유가 남는다 ({lhs:.4f} < {rhs:.4f}) - 링크 토폴로지나 "
            "속도/차장 파라미터가 바뀌었는지 확인하라",
        )

    def test_overtaking_actually_appears_at_5000(self) -> None:
        """되돌림 증명(동작) - 유입 상한을 충분히 키우면 역전이 실제로 발생한다.

        위 동작 핀이 "원래 0 이 나오는 검사" 가 아님을 보인다.
        """
        cfg = ExperimentConfig.from_file(
            "src/config/default.yaml",
            {"network": {"movement_capacity_veh_h": BEHAVIOURAL_REVERSAL_CAPACITY_VEH_H}},
        )
        self.assertGreater(_count_inversions(cfg), 0)


if __name__ == "__main__":
    unittest.main()
