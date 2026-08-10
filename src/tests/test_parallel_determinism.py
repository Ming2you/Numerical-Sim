# N8-3 통합 rollout 스케줄러 - worker 수 0/1/2/5 에서 결과가 같은지 검사한다
"""병렬화가 결과를 바꾸면 그것이 결함이다.

검사 대상은 세 개의 병렬 표면이다.
  1. `stackelberg_mpc._evaluate_candidate_set` - leader 후보 평가(serial/thread/process).
  2. `grid_parallel.evaluate_grid_items` - centralized/distributed grid 후보 평가.
  3. `stackelberg_wu_metered._green_price_rollouts` - green 가격 ±delta 전역 rollout.

"workers 0" 은 직렬(backend=serial), "workers 1" 은 풀을 요청했지만 1개라 직렬로 접히는
경로, "workers 2/5" 는 실제 풀이다. 세 경우가 같은 값을 내야 한다.
"""
import time
import unittest
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List

import src.controllers.stackelberg_mpc as smpc
from src.controllers.grid_parallel import evaluate_grid_items
from src.controllers.leader import LeaderAction
from src.controllers.nash_solver import NashResult
from src.controllers.stackelberg_mpc import _LeaderCandidateEvaluation
from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
from src.models.demand import DemandProfile, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState


WORKER_COUNTS = (0, 1, 2, 5)


def _cfg(overrides: Dict[str, object] | None = None) -> ExperimentConfig:
    mpc: Dict[str, object] = {
        "horizon_steps": 1,
        "relaxed_quantized_controls": True,
        "grid_parallel_backend": "serial",
        "leader_global_refresh_sec": 1.0e9,
        "leader_search_mode": "grid",
        "leader_candidate_count": 9,
        "leader_refinement_candidate_count": 5,
        "stackelberg_prefilter_top_k": 6,
        "stackelberg_prefilter_local_top_k": 6,
        "max_nash_iter": 2,
    }
    mpc.update(overrides or {})
    return ExperimentConfig.from_file(
        "src/config/default.yaml",
        {
            "simulation": {"T_total": 360.0},
            "mpc": mpc,
            "freeway_follower": {
                "freeway_prediction_horizon_steps": 1,
                "vsl_sequence_search": False,
                "horizon_beam_width": 1,
                "horizon_ramp_candidate_limit": 1,
                "horizon_vsl_candidate_limit_per_link": 1,
            },
        },
    )


def _backend_and_workers(count: int) -> Dict[str, object]:
    """workers 0 = 직렬 backend, 1/2/5 = thread backend 에 max_workers 를 그대로 준다."""
    if count == 0:
        return {
            "stackelberg_leader_parallel_backend": "serial",
            "stackelberg_leader_parallel_max_workers": 1,
        }
    return {
        "stackelberg_leader_parallel_backend": "thread",
        "stackelberg_leader_parallel_max_workers": count,
    }


def _dummy_nash(cfg: ExperimentConfig) -> NashResult:
    return NashResult(ControlAction.fixed(cfg), 0.0, 0, True, 0.0, 0.0, {})


class LeaderCandidateOrderTests(unittest.TestCase):
    """후보 평가 결과의 순서와 동점 처리는 worker 수에 의존하면 안 된다."""

    # 후보별 목적함수. 인덱스 2 와 5 가 최소값에서 동점이다(동점 깨기는 최소 인덱스여야 한다).
    OBJECTIVES = (30.0, 20.0, 10.0, 40.0, 25.0, 10.0, 35.0)
    # 완료 순서를 인덱스 순서와 어긋나게 만드는 지연(초). 뒤 인덱스가 먼저 끝난다.
    DELAYS = (0.30, 0.25, 0.20, 0.15, 0.10, 0.05, 0.0)

    def _run(
        self,
        workers: int,
        selected_indices: tuple[int, ...] | None = None,
    ) -> List[_LeaderCandidateEvaluation]:
        cfg = _cfg(_backend_and_workers(workers))
        controller = smpc.StackelbergMPCController(cfg)
        candidates = [
            LeaderAction(float(100 + 10 * i), float(1000 + 100 * i))
            for i in range(len(self.OBJECTIVES))
        ]
        objectives = self.OBJECTIVES
        delays = self.DELAYS

        def fake_worker(payload):
            index = int(payload["index"])
            time.sleep(delays[index])
            return _LeaderCandidateEvaluation(
                index=index,
                action=payload["action"],
                nash=_dummy_nash(cfg),
                objective=float(objectives[index]),
                objective_terms={"leader_total_objective": float(objectives[index])},
                metadata={},
                rollout_used=False,
                stage=payload.get("stage", "coarse"),
            )

        original = smpc._stackelberg_candidate_worker
        smpc._stackelberg_candidate_worker = fake_worker
        try:
            results = controller._evaluate_candidate_set(
                candidates,
                list(selected_indices if selected_indices is not None else range(len(candidates))),
                TrafficState.initial(cfg),
                [],
                ControlAction.fixed(cfg),
                stage="coarse",
            )
        finally:
            smpc._stackelberg_candidate_worker = original
            controller.close()
        return results

    def test_results_are_index_ordered_for_every_worker_count(self):
        expected = list(range(len(self.OBJECTIVES)))
        for workers in WORKER_COUNTS:
            with self.subTest(workers=workers):
                results = self._run(workers)
                self.assertEqual([item.index for item in results], expected)

    def test_tied_minimum_selects_lowest_index_for_every_worker_count(self):
        """`min(..., key=objective)` 은 첫 최소값을 고른다 - 순서가 흔들리면 선택도 흔들린다."""
        for workers in WORKER_COUNTS:
            with self.subTest(workers=workers):
                results = self._run(workers)
                best = min(results, key=lambda item: item.objective)
                self.assertEqual(best.index, 2)


class LeaderCandidatePrefilterOrderTests(LeaderCandidateOrderTests):
    """prefilter 가 활성이면 `selected_indices` 는 인덱스 순서가 아니다.

    `_prefilter_leader_candidates` 는 `selected` 를 proxy 랭킹 순서로 쌓는다
    (`stackelberg_mpc.py:2020-2036`). flagship override 도 그 순서를 그대로 낸다
    (`stackelberg_wu_metered.py:2782-2790`). 그러므로 정본 순서는 `selected_indices`
    순서이고, 병렬화는 그것을 재현해야 한다.

    위 `LeaderCandidateOrderTests` 는 `selected_indices` 로 `range(n)` 을 넘겨 prefilter
    재정렬을 우회하므로, 인덱스 순서로 재정렬하는 구현도 통과한다. 실제 배선에서 prefilter 는
    항상 활성이다(`default.yaml` top_k 4 / 후보 49, core15n41 top_k 3 / 후보 9).
    """

    # `_prefilter_leader_candidates` 가 실제로 내는 모양 - proxy 랭킹 순서.
    PREFILTER_ORDER = (5, 2, 0, 4, 1, 3, 6)

    def test_prefilter_order_is_preserved_for_every_worker_count(self):
        expected = list(self.PREFILTER_ORDER)
        for workers in WORKER_COUNTS:
            with self.subTest(workers=workers):
                results = self._run(workers, selected_indices=self.PREFILTER_ORDER)
                self.assertEqual([item.index for item in results], expected)

    def test_parallel_tie_break_matches_serial_instead_of_moving_it(self):
        """동점(2 와 5)에서 직렬이 고르던 후보를 병렬도 골라야 한다.

        직렬은 `selected_indices` 순서로 쌓으므로 랭킹이 앞선 5 를 고른다. 결과를 인덱스
        순서로 재정렬하면 병렬을 직렬에 맞추는 대신 **직렬 쪽이** 2 로 바뀐다.
        """
        for workers in WORKER_COUNTS:
            with self.subTest(workers=workers):
                results = self._run(workers, selected_indices=self.PREFILTER_ORDER)
                best = min(results, key=lambda item: item.objective)
                self.assertEqual(best.index, 5)


class GridParallelOrderTests(unittest.TestCase):
    """`evaluate_grid_items` 는 backend 와 무관하게 입력 순서를 보존한다."""

    def _run(self, workers: int) -> List[float]:
        backend = "serial" if workers == 0 else "thread"
        cfg = _cfg({
            "grid_parallel_backend": backend,
            "grid_parallel_max_workers": max(1, workers),
            "grid_parallel_min_items": 1,
        })
        items = [0.30, 0.25, 0.20, 0.15, 0.10, 0.05, 0.0]

        def serial_fn(delay: float) -> float:
            time.sleep(delay)
            return float(delay)

        run = evaluate_grid_items(cfg, items, serial_fn)
        return list(run.results)

    def test_result_order_matches_input_order_for_every_worker_count(self):
        expected = [0.30, 0.25, 0.20, 0.15, 0.10, 0.05, 0.0]
        for workers in WORKER_COUNTS:
            with self.subTest(workers=workers):
                self.assertEqual(self._run(workers), expected)


def _price_fixture(workers: int):
    cfg = _cfg()
    controller = StackelbergWuMeteredController(cfg)
    controller.signal_price_enabled = True
    controller.price_parallel_workers = workers
    profile = DemandProfile(
        cfg, ScenarioConfig("peak_demand", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0)
    )
    forecast = profile.horizon(0.0, 3)
    return cfg, controller, TrafficState.initial(cfg), ControlAction.fixed(cfg), forecast


class GreenPriceParallelTests(unittest.TestCase):
    """green 가격 rollout 은 worker 수에 무관하게 같은 값을 내고, 직렬 재실행은 조용하면 안 된다."""

    @staticmethod
    def _points(cfg: ExperimentConfig) -> Dict[str, tuple]:
        total = float(cfg.network.effective_green_total)
        base = total / 2.0
        return {
            signal: (base, base - 4.0, base + 4.0)
            for signal in sorted(cfg.network.signals)
        }

    def _prices(self, workers: int) -> tuple[Dict[tuple, tuple], int]:
        cfg, controller, state, previous, forecast = _price_fixture(workers)
        try:
            out = controller._green_price_rollouts(
                state, previous, forecast, self._points(cfg),
            )
            return out, int(controller.price_parallel_serial_rerun_count)
        finally:
            controller.close()

    def test_green_prices_identical_for_every_worker_count(self):
        base, base_rerun = self._prices(0)
        self.assertTrue(base)
        self.assertEqual(base_rerun, 0)
        for workers in (1, 2, 5):
            with self.subTest(workers=workers):
                other, rerun = self._prices(workers)
                # 병렬 풀이 조용히 직렬로 접혔으면 "값이 같다"는 주장이 공허하다.
                self.assertEqual(rerun, 0)
                self.assertEqual(sorted(base), sorted(other))
                for key in base:
                    self.assertAlmostEqual(base[key][0], other[key][0], delta=1.0e-9)
                    self.assertAlmostEqual(base[key][1], other[key][1], delta=1.0e-9)

    def test_serial_rerun_after_parallel_exception_is_recorded(self):
        """병렬 예외 뒤 직렬 재실행이 일어났다면 진단에 남아야 한다(조용한 재실행 0)."""
        cfg, controller, state, previous, forecast = _price_fixture(4)
        original = ProcessPoolExecutor.__init__

        def boom(self, *args, **kwargs):
            raise RuntimeError("injected pool failure")

        ProcessPoolExecutor.__init__ = boom
        try:
            out = controller._green_price_rollouts(
                state, previous, forecast, self._points(cfg),
            )
        finally:
            ProcessPoolExecutor.__init__ = original
            controller.close()
        self.assertTrue(out)
        self.assertEqual(int(controller.price_parallel_serial_rerun_count), 1)
        self.assertEqual(
            controller.price_parallel_last_error, "RuntimeError: injected pool failure",
        )


class DecideWorkerEquivalenceTests(unittest.TestCase):
    """end-to-end - worker 수가 선택 action 을 바꾸면 안 된다."""

    def _decide(self, workers: int):
        cfg = _cfg(_backend_and_workers(workers))
        controller = smpc.StackelbergMPCController(cfg)
        profile = DemandProfile(
            cfg, ScenarioConfig("peak_demand", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0)
        )
        forecast = profile.horizon(0.0, 3)
        try:
            return controller.decide_with_info(
                TrafficState.initial(cfg), forecast, ControlAction.fixed(cfg),
            )
        finally:
            controller.close()

    def test_selected_action_and_objective_identical_for_every_worker_count(self):
        base = self._decide(0)
        for workers in (1, 2, 5):
            with self.subTest(workers=workers):
                other = self._decide(workers)
                self.assertAlmostEqual(
                    base.leader_objective, other.leader_objective, delta=1.0e-9,
                )
                self.assertEqual(base.control.green_times, other.control.green_times)
                self.assertEqual(base.control.ramp_metering, other.control.ramp_metering)
                self.assertEqual(base.control.vsl, other.control.vsl)
                self.assertEqual(base.control.offsets, other.control.offsets)
                self.assertAlmostEqual(
                    float(base.control.N_P_star), float(other.control.N_P_star), delta=1.0e-9,
                )
                self.assertAlmostEqual(
                    float(base.control.N_UF_star), float(other.control.N_UF_star), delta=1.0e-9,
                )


if __name__ == "__main__":
    unittest.main()
