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


def _distributed_cfg(overrides: Dict[str, object] | None = None) -> ExperimentConfig:
    """조기종료(early termination)가 실제로 발동하는 배선.

    `_evaluate_full_candidate`는 `isinstance(self.nash_solver, DistributedCoordinator)`
    일 때만 `leader_incumbent_obj`를 follower에 넘긴다(`stackelberg_mpc.py:1525-1532`).
    기본 `follower_solver_mode: two_block`에서는 incumbent가 solver에 도달조차 하지
    않으므로 아래 `DecideWorkerEquivalenceTests`는 조기종료에 대해 공허하다.
    horizon_steps=2 는 조기종료가 마지막 스텝 이전에 끊길 여지를 만들기 위한 최소값이다.
    """
    mpc: Dict[str, object] = {
        "horizon_steps": 2,
        "follower_solver_mode": "distributed",
        "leader_candidate_count": 9,
        "leader_refinement_candidate_count": 5,
    }
    mpc.update(overrides or {})
    return _cfg(mpc)


def _distributed_fixture(workers: int):
    cfg = _distributed_cfg(_backend_and_workers(workers))
    controller = smpc.StackelbergMPCController(cfg)
    profile = DemandProfile(
        cfg, ScenarioConfig("peak_demand", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0)
    )
    return cfg, controller, TrafficState.initial(cfg), ControlAction.fixed(cfg), profile.horizon(0.0, 4)


class LeaderIncumbentWiringTests(unittest.TestCase):
    """`_evaluate_candidate_set`의 incumbent 배선은 worker 수에 따라 비대칭이다.

    `stackelberg_mpc.py:2114-2119` - seed 후보를 평가한 뒤
      - 병렬(thread/process)은 payload 전부에 **seed 직후 값**을 박아 넣고 그대로 제출한다.
      - 직렬은 루프 안에서 후보마다 `stage_incumbent`를 다시 써서 **점점 조인다**.
    이 incumbent 는 `DistributedCoordinator.solve(leader_incumbent_obj=...)` 로 내려가
    follower grid 의 `abort_above` 가 되고(`distributed_coordinator.py:676-709`),
    조기절단된 후보는 **부분합**(`partial_ttt`)으로 채점된다.

    즉 bound 가 달라지면 후보 목적함수가 달라질 수 있는 배선이다. 아래 두 검사는
    (1) 병렬 bound 가 직렬보다 느슨한 쪽으로만 어긋난다는 것과
    (2) 이 배선에서 그 어긋남이 목적함수를 바꾸지 않는 이유를 각각 못박는다.
    """

    OBJECTIVES = (30.0, 25.0, 20.0, 15.0, 10.0, 5.0, 1.0)

    def _handed_incumbents(self, workers: int) -> List[float]:
        """후보 순서대로 worker 에게 실제로 전달된 incumbent 값을 모은다."""
        cfg = _cfg(_backend_and_workers(workers))
        controller = smpc.StackelbergMPCController(cfg)
        candidates = [
            LeaderAction(float(100 + 10 * i), float(1000 + 100 * i))
            for i in range(len(self.OBJECTIVES))
        ]
        objectives = self.OBJECTIVES
        handed: Dict[int, float] = {}

        def fake_worker(payload):
            index = int(payload["index"])
            handed[index] = float(payload["incumbent_obj"])
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
            controller._evaluate_candidate_set(
                candidates,
                list(range(len(candidates))),
                TrafficState.initial(cfg),
                [],
                ControlAction.fixed(cfg),
                stage="coarse",
            )
        finally:
            smpc._stackelberg_candidate_worker = original
            controller.close()
        return [handed[i] for i in range(len(objectives))]

    def test_incumbent_sequence_is_monotone_for_every_worker_count(self):
        """incumbent 는 best-so-far 상한이므로 후보 순서를 따라 느슨해지면 안 된다."""
        for workers in WORKER_COUNTS:
            with self.subTest(workers=workers):
                handed = self._handed_incumbents(workers)
                for position in range(1, len(handed)):
                    self.assertLessEqual(handed[position], handed[position - 1])

    def test_pool_incumbent_is_never_tighter_than_serial(self):
        """병렬 bound 는 직렬 bound 보다 느슨(≥)해야 한다.

        느슨한 bound 는 가지치기를 덜 할 뿐이지만, 직렬보다 **조인** bound 는 직렬이
        살려두던 follower 후보를 잘라 결과를 바꾼다. `as_completed` 순서로 조이는
        구현을 넣으면 이 검사가 비결정적으로 터진다.
        """
        serial = self._handed_incumbents(0)
        for workers in (2, 5):
            with self.subTest(workers=workers):
                pooled = self._handed_incumbents(workers)
                self.assertEqual(len(pooled), len(serial))
                for position, (pool_value, serial_value) in enumerate(zip(pooled, serial)):
                    self.assertGreaterEqual(
                        pool_value, serial_value, msg=f"position={position}"
                    )


class LeaderIncumbentObjectiveInsensitivityTests(unittest.TestCase):
    """병렬/직렬 incumbent 비대칭이 무해한 **이유**를 못박는다.

    조기절단은 `total_ttt`가 `abort_above`를 넘는 **첫 스텝에서** 끊고 그 부분합을
    목적함수로 보고한다(`rollout_endpoint.py:295-306`, `distributed_coordinator.py:682-709`).
    TTT 는 스텝마다 비슷한 크기로 쌓이므로, 마지막 스텝 이전에 끊기려면 bound 가
    후보 목적함수의 약 (H-1)/H 아래로 내려가야 한다. 그 위에서는 절단이 **마지막 스텝**에서만
    걸려 부분합 = 전체합이라 값이 그대로다.

    실측(이 fixture, H=2, LeaderAction(480, 1260)) - incumbent 를 objective 대비 배율로 조여가며:
        inf / 0.67x / 0.55x / 0.50x / 0.45x → objective 59.88057255580024 (절단 29 → 149개)
        0.35x / 0.25x / 0.10x              → objective 23.41523081033207 (절단 151개)
    0.45x 와 0.35x 사이가 경계다 - 그 위에서는 bound 를 33% 조여 절단 후보가 5배로 늘어도
    목적함수가 비트 단위로 같고, 아래로 내려가면 첫 스텝에서 끊겨 값이 무너진다.

    직렬/병렬 incumbent 격차는 leader 후보 목적함수의 분산을 넘을 수 없는데, leader action
    전역(N_P 0~5000, N_UF 0~8000)을 훑어도 그 분산은 15% 남짓(133.41~156.41)이라
    경계(H=3 실 배선에서 (H-1)/H = 33% 아래)에 닿지 못한다. 그래서 비대칭이 목적함수
    차이로 재현되지 않는다.

    이 검사가 깨지면 그 전제가 무너진 것이고, `_evaluate_candidate_set`의 병렬/직렬
    incumbent 배선을 먼저 통일해야 한다.
    """

    ACTION = LeaderAction(480.0, 1260.0)

    def _evaluate(self, controller, state, forecast, previous, incumbent: float):
        evaluation = controller._evaluate_full_candidate(
            0, self.ACTION, state, forecast, previous, "coarse", incumbent,
        )
        return (
            float(evaluation.objective),
            float(evaluation.metadata["leader_candidate_follower_early_terminated_candidates"]),
        )

    def test_no_incumbent_level_prunes_at_all_under_four_phases(self):
        """4현시로 간 뒤 이 배선에서는 **조기절단이 아예 발동하지 않는다**.

        2현시 시절 이 검사는 "bound 를 (H-1)/H 아래로 조이면 절단이 5배로 늘지만
        목적함수는 비트 동일" 을 못박았다. 4현시(2026-08-12)에서 다시 재니 그 전제가
        성립하지 않는다 - incumbent 를 0.25 배까지 조여도 절단이 **0** 이다.

            incumbent   inf  0.90x  0.80x  0.67x  0.55x  0.45x  0.35x  0.25x
            절단          0      0      0      0      0      0      0      0
            objective  전부 61.876062 (비트 동일)

        그래서 무해한 **이유가 바뀌었다.** "경계 위에서는 부분합 = 전체합" 이 아니라
        "끊길 일이 없다" 다. 병렬/직렬 incumbent 격차가 무엇이든 목적함수에 닿지 못한다.

        **왜 안 끊기는지는 확인하지 못했다.** 녹색 예산 138 이 넷으로 갈리면서 follower
        grid 의 후보 지형이 바뀐 것으로 보이나 추적하지 않았다.

        이 검사는 그 사실의 **트립와이어** 다. 절단이 다시 발동하기 시작하면
        `_evaluate_candidate_set` 의 병렬/직렬 incumbent 배선(`:2116` 고정 대 `:2119` 조임)이
        목적함수를 바꿀 수 있으므로, 그때 무해성 논거를 다시 세워야 한다.
        """
        _cfg_unused, controller, state, previous, forecast = _distributed_fixture(0)
        try:
            base_obj, base_pruned = self._evaluate(
                controller, state, forecast, previous, float("inf"),
            )
            measured = [
                self._evaluate(controller, state, forecast, previous, base_obj * factor)
                for factor in (0.67, 0.45, 0.25)
            ]
        finally:
            controller.close()
        self.assertEqual(base_pruned, 0.0, "절단이 발동했다 - 무해성 논거를 다시 세워라")
        for factor, (objective, pruned) in zip((0.67, 0.45, 0.25), measured):
            with self.subTest(factor=factor):
                self.assertEqual(pruned, 0.0, "절단이 발동했다 - 무해성 논거를 다시 세워라")
                self.assertEqual(objective, base_obj)


class DistributedFollowerWorkerEquivalenceTests(unittest.TestCase):
    """조기종료가 발동하는 배선에서 worker 수별 후보 목적함수가 같아야 한다(N8-3 PASS 조건).

    **이 검사는 지금 공허하다 - 통과해도 아무것도 보장하지 않는다(2026-08-11 확인).**

    아래 fixture 는 후보 3개인데 세 목적함수가 비트 단위로 같게 나온다.

        workers=0  {0: 59.56902323410081, 1: 59.56902323410081, 2: 59.56902323410081}
        workers=2  {0: 59.56902323410081, 1: 59.56902323410081, 2: 59.56902323410081}

    전부 같으면 직렬의 `stage_incumbent = min(stage_incumbent, result.objective)` 가
    seed 값 아래로 내려가지 못한다. 그러면 직렬도 병렬과 **같은 incumbent** 를 넘기므로
    재려던 비대칭이 fixture 안에 존재하지 않는다. 가드로 넣은 `assertGreater(base_pruned, 0)`
    는 조기절단이 발동한다는 것만 보지 두 경로의 bound 가 다른지는 보지 않는다.

    실제로 `stackelberg_mpc.py:2116` 을 `stage_incumbent * 0.5` 로 개악해도 이 검사는
    255 초 걸려 통과했다. 240 초를 쓰면서 통과할 수밖에 없는 검사다.

    비대칭을 재려면 후보를 늘려 목적함수가 서로 달라야 한다(같은 fixture 를 후보 7개로
    늘리면 인덱스 5부터 나타난다는 보고가 있으나 재측정하지 않았다).

    **미루는 근거.** 실 런은 병렬 경로를 타지 않는다 - 어댑터가 세 겹으로 막는다
    (`vissim_stackelberg_adapter.py:2291, 2753` 하드코딩, `default.yaml:244, 259`).
    그 사실은 아래 `RealRunStaysSerialTests` 가 1 초에 못박는다. 병렬을 켜려는 순간
    그 검사가 터지고, 그때 이 검사를 제대로 고치면 된다.
    """

    def _objectives(self, workers: int) -> tuple[Dict[int, float], float]:
        cfg, controller, state, previous, forecast = _distributed_fixture(workers)
        candidates = [LeaderAction(float(300 + 60 * i), float(600 + 220 * i)) for i in range(3)]
        try:
            results = controller._evaluate_candidate_set(
                candidates, list(range(len(candidates))), state, forecast, previous, stage="coarse",
            )
        finally:
            controller.close()
        pruned = float(
            results[0].metadata["leader_candidate_follower_early_terminated_candidates"]
        )
        return {item.index: float(item.objective) for item in results}, pruned

    @unittest.skip(
        "fixture 의 후보 3개가 같은 목적함수를 내 직렬 incumbent 가 seed 아래로 안 내려간다. "
        "비대칭을 못 재면서 240 초를 쓴다. 실 런은 serial 고정이라(RealRunStaysSerialTests) "
        "병렬을 켤 때 후보 6개 이상 fixture 로 다시 만든다."
    )
    def test_candidate_objectives_identical_for_every_worker_count(self):
        base, base_pruned = self._objectives(0)
        # 조기종료가 발동하지 않으면 이 검사는 배선을 재지 못한다.
        self.assertGreater(base_pruned, 0.0)
        for workers in (1, 2, 5):
            with self.subTest(workers=workers):
                other, _pruned = self._objectives(workers)
                self.assertEqual(sorted(base), sorted(other))
                for index in base:
                    self.assertAlmostEqual(base[index], other[index], delta=1.0e-9)


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
