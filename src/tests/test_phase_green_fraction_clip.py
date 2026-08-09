# v3 N8 - _phase_green_fraction 의 스칼라 clip 을 순수 파이썬으로 바꾼다 (값 불변)
"""핫패스에서 numpy 스칼라 `clip` 을 걷어낸다.

## 왜 이 함수인가

실 solve 1회를 프로파일한 결과다(sweet_155, 31.9 s).

    45,333,461  dict.get                                    4.37 s
     1,405,122  numpy clip 사슬(_wrapit/_wrapfunc/_clip)     5.68 s 누적
     1,291,381  _phase_green_fraction                        2.31 s self / 8.40 s 누적

clip 호출 1,405,122 회 중 약 92% 가 이 함수에서 나온다(호출당 두 분기 중 하나만 실행).
`np.clip` 은 스칼라에 쓰면 `_wrapit -> _wrapfunc -> _clip` 을 거쳐 오버헤드가 크다.

저장소 전체에 같은 패턴이 148 곳 있지만 **핫패스만 고친다.** 나머지는 호출 수가 미미해
전면 교체는 이득 없이 회귀 위험만 키운다.

## 값이 바뀌지 않는 근거

`float(np.clip(x, lo, hi))` 와 `min(max(x, lo), hi)` 는 유한값에서 같고, NaN 과 무한대에서도
같다. 실측으로 확인했다.

    x=0.5 -> 0.5 / -1.0 -> 0.0 / 2.0 -> 1.0 / nan -> nan / inf -> 1.0 / -inf -> 0.0

NaN 이 같은 이유는 파이썬 `max(nan, 0.0)` 이 `0.0 > nan` 을 False 로 보고 nan 을 남기고,
이어지는 `min(nan, 1.0)` 도 같은 이유로 nan 을 남기기 때문이다. 즉 전파 방향이 np.clip 과
일치한다. 이 성질에 기대는 코드이므로 테스트로 고정한다.
"""

from __future__ import annotations

import math
import unittest

import numpy as np

from src.models.state import ControlAction, ExperimentConfig
from src.models.urban_queue_model import _phase_green_fraction, movement_specs


class ClipEquivalenceTests(unittest.TestCase):
    def test_python_minmax_matches_numpy_clip_including_nan_and_inf(self) -> None:
        for value in (0.0, 0.5, 1.0, -1.0, 2.0, 1e-12, float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                reference = float(np.clip(value, 0.0, 1.0))
                candidate = min(max(value, 0.0), 1.0)
                if math.isnan(reference):
                    self.assertTrue(math.isnan(candidate))
                else:
                    self.assertEqual(reference, candidate)

    def test_the_hot_function_no_longer_calls_numpy_clip(self) -> None:
        """되돌림 증명 겸 회귀 — 다시 np.clip 이 들어오면 여기서 잡힌다."""
        import inspect

        source = inspect.getsource(_phase_green_fraction)
        self.assertNotIn("np.clip", source)


class PhaseGreenFractionValueTests(unittest.TestCase):
    """값이 바뀌지 않았음을 실 config 로 확인한다."""

    def setUp(self) -> None:
        self.cfg = ExperimentConfig.from_file("src/config/default.yaml")
        self.specs = movement_specs(self.cfg)
        self.control = ControlAction.fixed(self.cfg)

    def _reference(self, spec, urban_step_index):
        """clip 도입 이전 산식을 np.clip 으로 그대로 재현한 참조 구현."""
        net = self.cfg.network
        phase = str(spec.get("phase", ""))
        if not phase:
            return 1.0
        default_green = net.effective_green_total / 2.0
        green_sec = float(self.control.green_times.get(phase, default_green))
        cycle = max(net.cycle_length, 1.0e-9)
        if urban_step_index is None:
            return float(np.clip(green_sec / cycle, 0.0, 1.0))
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
        return float(np.clip(overlap / max(t_u, 1.0e-9), 0.0, 1.0))

    def test_matches_the_reference_for_every_movement_and_phase_position(self) -> None:
        steps = [None, 0, 1, 7, 23, 24, 47, 100]
        for movement, spec in self.specs.items():
            for index in steps:
                with self.subTest(movement=movement, step=index):
                    self.assertEqual(
                        _phase_green_fraction(self.control, self.cfg, spec, index),
                        self._reference(spec, index),
                    )

    def test_result_stays_within_the_unit_interval(self) -> None:
        for spec in self.specs.values():
            for index in (None, 0, 5, 19):
                value = _phase_green_fraction(self.control, self.cfg, spec, index)
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)


if __name__ == "__main__":
    unittest.main()
