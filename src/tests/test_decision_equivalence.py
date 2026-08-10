# N8-2 결정 동등성 - 두 결정 경로가 같은 입력에서 같은 결정을 내는지 twin 행렬로 검사한다
"""twin 두 종류.

1. **endpoint 경유 대 직접** — production `evaluate_price_point` 를 우회하는 직접
   구현(`_direct_evaluate_price_point`)으로 같은 결정을 다시 내고 정확 일치를 요구한다.
   N7 이 rollout 을 endpoint 로 모은 뒤 "결정이 그대로인가" 를 결정 층에서 고정한다.
2. **FD 대 SPSA** — 계획 N8-2 의 원래 축. 두 gradient 추정기가 같은 endpoint·같은 spec 을
   쓰고(`_rollout_spec`), 결정이 같아야 한다는 주장이다.

계획의 `36` 은 `holdout 상태 12개 × 방향 seed 3개` 다(N8-2 산술 근거 절). 그 12 상태는
N5 부모 런(demand 3 × seed 47 = 부모 3, anchor 4)에서 나오는 **VISSIM holdout anchor** 라
실 런 없이는 만들 수 없다. 여기서는 같은 **모양**(demand 3 × anchor 4 = 상태 12, seed 3)을
플랜트 모델 상태로 재현한다. VISSIM anchor 가 아니라는 점이 이 검사의 한계이며,
계획의 N8-2 자체는 실 런 전까지 NOT_EVALUATED 다.
"""
from __future__ import annotations

import unittest
from typing import Dict, List, Sequence, Tuple

import src.controllers.rollout_endpoint as rep
from src.analysis.decision_equivalence import (
    FIELDS,
    LeaderCandidateRecorder,
    PricePointSwap,
    command_within_one_quantum,
    compare,
    field_diff,
    fingerprint,
    tracing,
)
from src.controllers.rollout_endpoint import ObjectiveSpec, PricePointResult
from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
from src.models.demand import DemandProfile, DemandStep, ScenarioConfig
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.simulation.coupling import run_coupled_interval


# 계획 N8-2 의 모양: demand 3 × anchor 4 = 상태 12, 방향 seed 3 → 36 twin.
DEMAND_SCALES: Tuple[float, ...] = (0.75, 1.0, 1.25)
ANCHOR_STEPS: Tuple[int, ...] = (4, 8, 12, 16)
DIRECTION_SEEDS: Tuple[int, ...] = (0, 1, 2)

# 명령 양자화 1단계(계획 사전 등록 전진폭과 같은 축을 쓴다).
COMMAND_QUANTA: Dict[str, float] = {"green": 6.0, "meter": 300.0, "vsl": 10.0, "offset": 0.0}


def _cfg() -> ExperimentConfig:
    return ExperimentConfig.from_file(
        "src/config/default.yaml",
        {
            "simulation": {"T_total": 3600.0},
            "mpc": {
                "horizon_steps": 1,
                "relaxed_quantized_controls": True,
                "grid_parallel_backend": "serial",
                "leader_global_refresh_sec": 1.0e9,
                "leader_search_mode": "grid",
                "leader_candidate_count": 3,
                "leader_refinement_candidate_count": 1,
                "stackelberg_prefilter_top_k": 3,
                "stackelberg_prefilter_local_top_k": 3,
                "max_nash_iter": 1,
            },
            "freeway_follower": {
                "freeway_prediction_horizon_steps": 1,
                "vsl_sequence_search": False,
                "horizon_beam_width": 1,
                "horizon_ramp_candidate_limit": 1,
                "horizon_vsl_candidate_limit_per_link": 1,
            },
        },
    )


def _anchor_states(cfg: ExperimentConfig, scale: float):
    """고정 신호로 플랜트를 전진시켜 anchor 4개의 상태를 만든다(VISSIM anchor 의 모델 대역)."""
    profile = DemandProfile(
        cfg, ScenarioConfig("peak_demand", urban_scale=scale, freeway_scale=scale, ramp_scale=scale)
    )
    interval = float(cfg.simulation.control_interval)
    state = TrafficState.initial(cfg)
    control = ControlAction.fixed(cfg)
    out: Dict[int, TrafficState] = {}
    for k in range(max(ANCHOR_STEPS)):
        run_coupled_interval(state, control, profile.at(k * interval), cfg)
        state.time_sec = (k + 1) * interval
        if (k + 1) in ANCHOR_STEPS:
            out[k + 1] = state.copy()
    return out, profile


def _decide(cfg, state, profile, t0, *, spsa: bool, seed: int):
    """4채널 가격을 켠 정본 decide 1회. 후보 열을 함께 기록해 돌려준다."""
    controller = StackelbergWuMeteredController(cfg)
    controller.signal_price_enabled = True
    controller.metering_price_enabled = True
    controller.vsl_price_enabled = True
    controller.offset_price_enabled = True
    controller.price_spsa_enabled = spsa
    # SPSA 방향 부호는 `100003 * _signal_price_refresh_count + s` 로 시드된다 —
    # 방향 seed 축은 이 값으로만 움직인다(production 코드 무변경).
    controller._signal_price_refresh_count = seed
    forecast = profile.horizon(t0, 3)
    try:
        with LeaderCandidateRecorder(controller) as recorder:
            result = controller.decide_with_info(state.copy(), forecast, ControlAction.fixed(cfg))
        return result, list(recorder.rows), forecast
    finally:
        controller.close()


def _twin_grid(cfg):
    """(scale, anchor step, state, profile) 12개."""
    grid = []
    for scale in DEMAND_SCALES:
        states, profile = _anchor_states(cfg, scale)
        for step in ANCHOR_STEPS:
            grid.append((scale, step, states[step], profile))
    return grid


# ---------------------------------------------------------------------------
# twin 1 - endpoint 를 우회하는 직접 구현.
# ---------------------------------------------------------------------------
def _direct_evaluate_price_point(
    state: TrafficState,
    previous: ControlAction,
    forecast: List[DemandStep],
    action_schedule: Sequence[rep.LeverMove],
    objective_spec: ObjectiveSpec,
) -> PricePointResult:
    """`evaluate_price_point` 와 같은 계약의 **독립 구현**.

    상태 투영(action_schedule -> control), rollout 루프, abort/inf 규약, 목적함수 조립을
    endpoint 를 거치지 않고 직접 쓴다. barrier/far/hinge/protected-queue 같은 **물리 성분**은
    endpoint 의 것이 아니라 공용 물리라 그대로 재사용한다 — 이 twin 이 재는 것은 배선이다.

    box-walk 은 이 twin 의 config 에서 꺼져 있다. 켜져 있으면 조용히 갈라지지 않도록 세운다.
    """
    spec = objective_spec
    cfg = spec.cfg
    if spec.box_walk and (
        bool(getattr(cfg.mpc, "leader_rollout_box_walk", False))
        or bool(getattr(cfg.mpc, "leader_rollout_box_walk_vg", False))
    ):
        raise NotImplementedError("direct reference does not model box-walk")

    # ---- 상태 투영 ----
    net = cfg.network
    if not action_schedule:
        control = previous
    else:
        control = previous.copy()
        total_green = float(net.effective_green_total)
        link_min: Dict[str, float] = {}
        link_set: Dict[str, float] = {}
        for move in action_schedule:
            value = float(move.value)
            if move.kind == "green":
                control.green_times[f"{move.key}_p1"] = value
                control.green_times[f"{move.key}_p2"] = total_green - value
            elif move.kind == "meter":
                control.ramp_metering[move.key] = value
            elif move.kind == "vsl":
                control.vsl[move.key] = value
                link = move.key.split("__seg")[0]
                link_min[link] = min(link_min.get(link, float("inf")), value)
            elif move.kind == "vsl_link":
                link_set[move.key] = value
            elif move.kind == "offset":
                control.offsets[move.key] = value
            else:
                raise ValueError(f"unknown lever kind: {move.kind}")
        for link, vmin in link_min.items():
            control.vsl[link] = min(float(control.vsl.get(link, vmin)), vmin)
        for link, value in link_set.items():
            control.vsl[link] = value

    # ---- rollout ----
    depth = int(cfg.mpc.horizon_steps) + max(0, int(getattr(cfg.mpc, "leader_value_depth", 0)))
    if spec.depth_override is not None:
        depth = max(1, int(spec.depth_override))
    s = state.copy()
    states: List[TrafficState] = []
    partial = 0.0
    freeway_ttt = 0.0
    urban_ttt = 0.0
    aborted = False
    for demand in list(forecast)[:depth]:
        outcome = run_coupled_interval(s, control, demand, cfg)
        s.time_sec += cfg.simulation.control_interval
        partial += outcome.freeway_ttt + outcome.urban_ttt
        if spec.split_ttt:
            freeway_ttt += float(outcome.freeway_ttt)
            urban_ttt += float(outcome.urban_ttt)
        states.append(s.copy())
        if spec.abort_above is not None and partial > spec.abort_above:
            aborted = True
            break

    # ---- 목적함수 조립 ----
    ttt = float("inf") if aborted else float(partial)
    objective = float(ttt)
    far = price_hinge = leader_hinge = protected = 0.0
    if spec.score_mode != "raw":
        from src.controllers.stackelberg_mpc import leader_hinge_cost, mfd_far_cost_to_go

        hinge_forecast = forecast if spec.hinge_forecast else None
        if spec.far_enabled and states:
            far = float(mfd_far_cost_to_go(cfg, states[-1]))
            objective += far
        if spec.price_hinge and states:
            price_hinge = float(spec.price_hinge_weight) * float(
                leader_hinge_cost(cfg, states, hinge_forecast, force=True)
            )
            objective += price_hinge
        if spec.leader_hinge:
            leader_hinge = float(leader_hinge_cost(cfg, states, hinge_forecast))
            objective += leader_hinge
        protected = rep._protected_queue_component(states, spec)
        objective += protected

    return PricePointResult(
        control=control,
        states=states,
        ttt=float(ttt),
        objective=float(objective),
        far=far,
        price_hinge=price_hinge,
        leader_hinge=leader_hinge,
        protected_queue=protected,
        barrier=rep._barrier_component(states, spec),
        max_rho=rep._max_rho_component(states, spec),
        freeway_ttt=float(freeway_ttt),
        urban_ttt=float(urban_ttt),
        aborted=bool(aborted),
        partial_ttt=float(partial),
    )


def _drop(kind: str):
    """schedule 에서 한 채널을 통째로 뺀다(레버 반응이 사라진다)."""

    def fn(state, previous, forecast, schedule, spec):
        return _direct_evaluate_price_point(
            state, previous, forecast, tuple(m for m in schedule if m.kind != kind), spec,
        )

    return fn


def _deeper(state, previous, forecast, schedule, spec):
    """rollout 깊이를 1 늘린다."""
    base = int(spec.cfg.mpc.horizon_steps) if spec.depth_override is None else int(spec.depth_override)
    grown = ObjectiveSpec(**{
        **{f: getattr(spec, f) for f in spec.__dataclass_fields__},
        "depth_override": base + 1,
    })
    return _direct_evaluate_price_point(state, previous, forecast, schedule, grown)


def _no_vsl_link_sync(state, previous, forecast, schedule, spec):
    """vsl segment 를 덮은 뒤 link fallback 키를 previous 값으로 되돌린다(min 동기화 제거)."""
    extra = [
        rep.LeverMove("vsl_link", m.key.split("__seg")[0],
                      float(previous.vsl.get(m.key.split("__seg")[0], m.value)))
        for m in schedule if m.kind == "vsl"
    ]
    return _direct_evaluate_price_point(
        state, previous, forecast, tuple(schedule) + tuple(extra), spec,
    )


def _no_green_budget(state, previous, forecast, schedule, spec):
    """green p1 만 덮고 p2 = total - p1 예산 보존을 뺀다."""
    if not any(m.kind == "green" for m in schedule):
        return _direct_evaluate_price_point(state, previous, forecast, schedule, spec)
    control = previous.copy()
    for move in schedule:
        if move.kind == "green":
            control.green_times[f"{move.key}_p1"] = float(move.value)
        elif move.kind == "meter":
            control.ramp_metering[move.key] = float(move.value)
        elif move.kind in ("vsl", "vsl_link"):
            control.vsl[move.key] = float(move.value)
        elif move.kind == "offset":
            control.offsets[move.key] = float(move.value)
    return _direct_evaluate_price_point(state, control, forecast, (), spec)


# 되돌림 증명용 교란. **vsl 축은 여기 없다** — 이 fixture 에서 vsl 가격점(105/115 km/h)이
# 전부 같은 목적함수를 내기 때문이다(자유류라 상한이 안 물린다). 교란해도 안 잡히는 검사를
# 통과로 세지 않으려고 뺐고, 대신 그 사실 자체를
# `VslChannelInertnessTests` 가 못박는다. vsl 이 다시 물리기 시작하면 그쪽이 먼저 깨진다.
PERTURBATIONS = (
    ("depth+1", _deeper),
    ("drop-green", _drop("green")),
    ("drop-meter", _drop("meter")),
    ("drop-offset", _drop("offset")),
    ("no-green-budget", _no_green_budget),
)


class EndpointVersusDirectTwinTests(unittest.TestCase):
    """endpoint 경유 결정과 직접 구현 결정이 평가 궤적·다섯 필드·명령에서 정확 일치해야 한다.

    결정 지문만으로는 이빨이 없다. 이 fixture 는 가격 schedule 의 레버를 통째로 빼도
    결정이 안 움직인다(후보가 포화하고 fallback 이 선택되기 때문). 그래서
    **평가 궤적**(evaluate_price_point 호출 열의 목적함수)까지 함께 비교한다.
    """

    SCALES = (1.0,)
    # 교란 검사는 한 anchor 로 충분하다(전 교란이 여기서 잡힌다). 본 검사만 anchor 4개를 돈다.
    PERTURBATION_STEPS = (8,)

    def _twins(self, direct_fn=_direct_evaluate_price_point, steps=ANCHOR_STEPS):
        cfg = _cfg()
        rows = []
        for scale in self.SCALES:
            states, profile = _anchor_states(cfg, scale)
            for step in steps:
                state = states[step]
                t0 = step * float(cfg.simulation.control_interval)
                trace_a: List[tuple] = []
                with PricePointSwap(tracing(rep.evaluate_price_point, trace_a)):
                    a, cand_a, fc = _decide(cfg, state, profile, t0, spsa=False, seed=0)
                trace_b: List[tuple] = []
                with PricePointSwap(tracing(direct_fn, trace_b)):
                    b, cand_b, _ = _decide(cfg, state, profile, t0, spsa=False, seed=0)
                rows.append((
                    (scale, step),
                    fingerprint(a, cfg, state, fc, cand_a),
                    fingerprint(b, cfg, state, fc, cand_b),
                    trace_a,
                    trace_b,
                ))
        return rows

    def test_evaluation_trace_and_all_fields_match_exactly(self):
        rows = self._twins()
        self.assertEqual(len(rows), len(ANCHOR_STEPS) * len(self.SCALES))
        failures = []
        for label, fa, fb, ta, tb in rows:
            self.assertTrue(ta, f"{label}: endpoint 호출이 0회면 검사가 공허하다")
            if ta != tb:
                first = next(
                    (i for i, (x, y) in enumerate(zip(ta, tb)) if x != y), min(len(ta), len(tb))
                )
                failures.append((label, "trace", len(ta), len(tb), ta[first:first + 1], tb[first:first + 1]))
            for name, ok in compare(fa, fb).items():
                if not ok:
                    failures.append((label, name, field_diff(fa, fb, name)[:3]))
        self.assertEqual(failures, [])

    def test_every_perturbation_of_the_direct_reference_is_detected(self):
        """되돌림 증명 - 직접 구현의 규약을 하나씩 깨면 궤적이 반드시 갈라져야 한다."""
        for name, broken in PERTURBATIONS:
            with self.subTest(perturbation=name):
                rows = self._twins(broken, steps=self.PERTURBATION_STEPS)
                changed = [
                    label for label, fa, fb, ta, tb in rows
                    if ta != tb or not all(compare(fa, fb).values())
                ]
                self.assertTrue(changed, f"{name} 를 깨도 twin 이 통과하면 검사에 이빨이 없다")


class VslChannelInertnessTests(unittest.TestCase):
    """이 fixture 에서 vsl 가격점이 목적함수를 전혀 못 움직인다는 사실을 못박는다.

    실측(2026-08-10): anchor step 8, demand 1.0 에서 vsl 단일 레버 점 32개의 목적함수가
    **전부 같은 값** 이다. 운영점 100 km/h 에 delta 를 얹은 105/115 는 자유류 상한 위라
    plant 가 반응하지 않는다. 그래서 vsl 축 교란은 되돌림 증명이 안 된다.
    이 검사가 깨지면(= vsl 이 물리기 시작하면) `PERTURBATIONS` 에 vsl 축을 되살려야 한다.
    """

    def test_all_vsl_only_price_points_share_one_objective(self):
        cfg = _cfg()
        states, profile = _anchor_states(cfg, 1.0)
        trace: List[tuple] = []
        with PricePointSwap(tracing(rep.evaluate_price_point, trace)):
            _decide(cfg, states[8], profile, 8 * float(cfg.simulation.control_interval),
                    spsa=False, seed=0)
        vsl_points = {
            key: objective
            for key, _mode, objective, _ttt, _aborted, _n in trace
            if key and {kind for kind, _k, _v in key} == {"vsl"}
        }
        self.assertGreaterEqual(len(vsl_points), 8)
        self.assertEqual(
            len(set(vsl_points.values())), 1,
            msg="vsl 가격점이 갈라지기 시작했다 - PERTURBATIONS 에 vsl 축을 되살려라",
        )


class FiniteDifferenceVersusSpsaTwinTests(unittest.TestCase):
    """계획 N8-2 의 원래 축. 36 twin 을 실제로 돌려 필드별 일치 수를 센다."""

    @classmethod
    def setUpClass(cls):
        cfg = _cfg()
        cls.cfg = cfg
        cls.rows = []
        for scale, step, state, profile in _twin_grid(cfg):
            t0 = step * float(cfg.simulation.control_interval)
            for seed in DIRECTION_SEEDS:
                a, cand_a, fc = _decide(cfg, state, profile, t0, spsa=False, seed=seed)
                b, cand_b, _ = _decide(cfg, state, profile, t0, spsa=True, seed=seed)
                cls.rows.append((
                    (scale, step, seed),
                    fingerprint(a, cfg, state, fc, cand_a),
                    fingerprint(b, cfg, state, fc, cand_b),
                ))

    def test_twin_count_is_thirty_six(self):
        self.assertEqual(len(self.rows), 36)
        self.assertEqual(len(DEMAND_SCALES) * len(ANCHOR_STEPS), 12)

    def test_state_mismatch_only_ever_follows_a_command_mismatch(self):
        """상태가 갈라지는 twin 은 전부 명령이 갈라진 twin 이다.

        계획 PASS 는 명령에 양자화 1단계를 허용하면서 상태는 정확 일치를 요구한다.
        명령이 한 칸 움직이면 종단 예측 상태도 반드시 움직이므로 두 조항은 함께 성립할 수
        없다. 여기서 고정하는 것은 **상태 불일치의 원인이 명령 불일치 뿐** 이라는 사실이다.
        """
        for label, fa, fb in self.rows:
            with self.subTest(twin=label):
                if fa.command == fb.command:
                    self.assertEqual(fa.state, fb.state)

    def test_feasibility_and_safety_certificate_match_on_every_twin(self):
        for label, fa, fb in self.rows:
            with self.subTest(twin=label):
                self.assertEqual(fa.feasibility, fb.feasibility)
                self.assertEqual(fa.safety_certificate, fb.safety_certificate)

    def test_fallback_grade_matches_on_every_twin(self):
        for label, fa, fb in self.rows:
            with self.subTest(twin=label):
                self.assertEqual(
                    fa.fallback_grade, fb.fallback_grade,
                    msg=str(field_diff(fa, fb, "fallback_grade")),
                )

    def test_leader_candidate_sequence_matches_on_every_twin(self):
        for label, fa, fb in self.rows:
            with self.subTest(twin=label):
                self.assertEqual(
                    fa.leader_candidates, fb.leader_candidates,
                    msg=str(field_diff(fa, fb, "leader_candidates")),
                )

    def test_command_is_within_one_declared_quantum_on_every_twin(self):
        for label, fa, fb in self.rows:
            with self.subTest(twin=label):
                self.assertTrue(
                    command_within_one_quantum(fa, fb, COMMAND_QUANTA),
                    msg=f"{label}: {fa.command != fb.command}",
                )

    # 실측(2026-08-10, 모델 anchor 36 twin, `_cfg()` 구성).
    # 계획의 `36/36 정확 일치` 가 **어느 필드에서 성립하고 어디서 안 되는지**를 수치로
    # 못박는다. `state`/`command` 가 36 이 아닌 것은 결함이 아니라 측정 결과다 —
    # FD 와 SPSA 는 서로 다른 gradient 추정기라 명령이 양자화 1단계 안에서 갈릴 수 있고,
    # 계획도 명령에는 그 여유를 준다. 값이 움직이면 이 검사가 먼저 깨져 재보고를 강제한다.
    MEASURED_EXACT_MATCH_COUNTS: Dict[str, int] = {
        "state": 3,
        "feasibility": 36,
        "safety_certificate": 36,
        "fallback_grade": 36,
        "leader_candidates": 36,
        "command": 3,
    }

    def test_measured_per_field_exact_match_counts_are_unchanged(self):
        counts = {name: 0 for name in FIELDS}
        counts["command"] = 0
        for _label, fa, fb in self.rows:
            for name, ok in compare(fa, fb).items():
                counts[name] += int(ok)
        report = ", ".join(f"{name} {counts[name]}/{len(self.rows)}" for name in counts)
        self.assertEqual(
            counts,
            self.MEASURED_EXACT_MATCH_COUNTS,
            msg=f"FD-vs-SPSA 필드별 정확 일치: {report}",
        )


if __name__ == "__main__":
    unittest.main()
