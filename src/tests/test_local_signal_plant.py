# local_signal_plant.rollout_local_tts_ramp_aware의 off-ramp drain(S_eff 부호) 단위 테스트
"""`rollout_local_tts_ramp_aware` step (b)(off_ramp drain)의 S_eff 부호 회귀 테스트.

`s_eff`는 receiving 링크의 **가용공간**이다(`_allocate_receiving_counts`/
`_effective_available_space`와 동일 의미). 차량이 그 링크로 유입되면 가용공간은
반드시 감소해야 한다 — `_drain_offramp_storage`(urban_queue_model.py)가
`state.urban_link_storage[receiving_link] -= actual`로 구현하는 것과 동일해야 한다.

시나리오: off-ramp storage(occupancy=40)에서 같은 receiving 링크("own_link", 가용공간
초기 5)로 방출을 시도하는 movement 2개를 순서대로 처리시킨다. 이 링크는 이 신호의
다른(non-off-ramp) movement의 origin이기도 해서(own_origin_links에 포함) step (b)의
갱신 분기가 실제로 실행된다.

- 부호가 맞으면(가용공간 감소): 1번째 movement가 가용공간 5를 모두 소진 → 2번째
  movement는 막힘 → 이 substep에 총 5대만 배출 → storage 잔류 occupancy = 35 →
  own-TTS(반환 cost) = 35.0.
- 부호가 틀리면(가용공간이 오히려 증가): 1번째 배출이 가용공간을 5+5=10으로 늘려버려
  2번째 movement도 유입돼 총 15대 배출(용량 보존 위반, occupancy=25 → cost=25.0).
"""
import unittest

from src.controllers.local_signal_plant import (
    LocalSignalModel,
    rollout_local_tts_ramp_aware,
)
from src.models.state import ExperimentConfig


def _build_model(cfg: ExperimentConfig) -> LocalSignalModel:
    # off_m1/off_m2: 같은 off-ramp(OR_X)에서 같은 receiving 링크("own_link")로 배출.
    # internal_m: origin이 "own_link"인 일반 movement 하나를 둬서 "own_link"가
    # 이 신호의 own_origin_links에 포함되도록 한다(그래야 step (b)의 자기-origin
    # 갱신 분기가 실제로 실행된다).
    return LocalSignalModel(
        signal="X",
        cfg=cfg,
        movements=["off_m1", "off_m2", "internal_m"],
        specs={"off_m1": {}, "off_m2": {}, "internal_m": {}},
        phase_of={"off_m1": "p1", "off_m2": "p1", "internal_m": "p2"},
        receiving_of={
            "off_m1": "own_link",
            "off_m2": "own_link",
            "internal_m": "sink_link",
        },
        origin_of={"off_m1": "OR_X", "off_m2": "OR_X", "internal_m": "own_link"},
        beta_of={"off_m1": 0.5, "off_m2": 0.5, "internal_m": 0.0},
        cap_flow_of={"off_m1": 1.0e5, "off_m2": 1.0e5, "internal_m": 0.0},
        receiving_space_rule="proportional",
        kind_of={"off_m1": "off_ramp", "off_m2": "off_ramp", "internal_m": "internal"},
        offramp_movements={"OR_X": ["off_m1", "off_m2"]},
        offramp_storage_cap={"OR_X": 100.0},
        onramp_movements={},
        ramp_queue_max=180.0,
        has_ramps=True,
    )


class TestOffRampDrainSignConvention(unittest.TestCase):
    def test_offramp_drain_decreases_receiving_space(self):
        cfg = ExperimentConfig()
        model = _build_model(cfg)

        s_eff0 = {"own_link": 5.0}
        occ0 = {"OR_X": 40.0}

        cost = rollout_local_tts_ramp_aware(
            model,
            q0={"internal_m": 0.0},
            arr_movement={},
            s_eff0=s_eff0,
            offramp_inflow={"OR_X": 0.0},
            offramp_occ0=occ0,
            ramp_queue0={},
            reservoir_drain={},
            freeway_congestion={},
            ramp_metering_weight=0.0,
            green_p1=120.0,
            green_p2=0.0,
            substeps=1,
            dt_h=1.0,
        )

        # 용량 보존: receiving 링크의 가용공간(5)보다 많이 배출될 수 없으므로,
        # storage 잔류 occupancy는 40 - 5 = 35 이상이어야 하고, own-TTS(cost)도
        # 그만큼(35.0) 나와야 한다. 부호가 반전되면(버그) 가용공간이 오히려 늘어나
        # 두 번째 movement까지 통과해 15대가 빠져나가 cost가 25.0으로 더 작게 나온다.
        self.assertAlmostEqual(cost, 35.0, places=6)


if __name__ == "__main__":
    unittest.main()
