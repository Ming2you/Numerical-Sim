# N8-2 결정 동등성 - 두 결정 경로의 상태·feasibility·안전 인증서·fallback 등급·리더 후보를 대조한다
"""결정 twin 을 지문으로 만들어 정확 일치 여부를 필드별로 판정한다.

계획(`IMPLEMENTATION_PLAN_V3_LEAN.md` N8-2)의 PASS 는
`상태·feasibility·안전 인증서·fallback 등급·리더 후보 36/36 정확 일치`이고
명령은 `정확 일치 또는 선언된 양자화 1단계 이내`다. 그 다섯 필드를 여기서 **명시적으로**
정의한다 — 계획은 이름만 주고 정의를 주지 않으므로, 정의를 코드에 고정하지 않으면
"일치"가 해석에 따라 움직인다.

| 필드 | 정의 |
|---|---|
| `state` | 선택 action 을 hold 해 forecast 를 H 스텝 전진시킨 **종단 예측 상태** 요약 |
| `feasibility` | metadata 중 이름에 `feasib` 가 든 항목 전부 |
| `safety_certificate` | B3CERT 비대칭 방류 인증서 `wu_b3cert_*`(0/1) |
| `fallback_grade` | fallback guard 의 **범주형** 등급만(값·목적함수는 제외) |
| `leader_candidates` | 실제로 full 평가된 후보의 `(index, stage, N_P*, N_UF*)` 열 |
| `command` | 선택 control 의 green/meter/vsl/offset + `N_P*`/`N_UF*` |

`command` 는 별도로 둔다. 계획이 명령에만 양자화 1단계 허용을 주기 때문이다.

`state` 를 종단 예측 상태로 잡은 이유. 입력 상태로 잡으면 twin 구성상 항상 같아 검사가
공허해지고, rollout TTT 같은 목적함수형 값을 넣으면 `상태` 가 아니라 `점수` 를 재게 된다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState


# fallback 등급 = 범주형 플래그만. 목적함수 값(`..._objective`, `..._rollout_ttt`)은 등급이
# 아니라 점수라 제외한다.
FALLBACK_GRADE_KEYS: Tuple[str, ...] = (
    "leader_fallback_enabled",
    "leader_pfo_incumbent_enabled",
    "leader_fallback_incumbent_seed_active",
    "leader_fallback_guard_active",
    "leader_fallback_guard_selected",
    "leader_fallback_guard_selected_pfo",
    "leader_fallback_guard_selected_no_control",
    "leader_fallback_guard_rejected_leader",
    "leader_fallback_guard_metric_ttt",
    "leader_fallback_guard_ttt_worse",
    "leader_fallback_guard_terminal_worse",
    "leader_fallback_guard_terminal_severe",
    "leader_fallback_guard_completed_worse",
    "leader_fallback_guard_completed_severe",
    "leader_fallback_guard_objective_worse",
    "leader_fallback_guard_insufficient_gain",
    "leader_fallback_best_stage_pfo",
    "leader_fallback_best_stage_no_control",
    "leader_fallback_candidate_count",
    "leader_fallback_evaluated_count",
)

FIELDS: Tuple[str, ...] = (
    "state",
    "feasibility",
    "safety_certificate",
    "fallback_grade",
    "leader_candidates",
)


@dataclass(frozen=True)
class DecisionFingerprint:
    """한 결정의 비교 가능한 지문. 모든 필드는 hashable 하고 `==` 로 정확 비교된다."""

    state: Tuple[Tuple[str, float], ...]
    feasibility: Tuple[Tuple[str, float], ...]
    safety_certificate: Tuple[Tuple[str, float], ...]
    fallback_grade: Tuple[Tuple[str, float], ...]
    leader_candidates: Tuple[Tuple[int, str, float, float], ...]
    command: Tuple[Any, ...]

    def field(self, name: str) -> Any:
        return getattr(self, name)


def _numeric_metadata(result: Any) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for key, value in getattr(result, "metadata", {}).items():
        if isinstance(value, (int, float, bool)) and not isinstance(value, str):
            out[str(key)] = float(value)
    return out


def _select(source: Dict[str, float], predicate: Callable[[str], bool]) -> Tuple[Tuple[str, float], ...]:
    return tuple(sorted((k, float(v)) for k, v in source.items() if predicate(k)))


def _round(value: float, digits: int = 12) -> float:
    return float(round(float(value), digits))


def terminal_state_digest(
    cfg: ExperimentConfig,
    state: TrafficState,
    control: ControlAction,
    forecast: Sequence[DemandStep],
    digits: int = 12,
) -> Tuple[Tuple[str, float], ...]:
    """선택 control 을 hold 해 H 스텝 전진시킨 종단 상태의 요약.

    production endpoint 를 통과한다(N7 우회 호출 0 규약). `action_schedule` 이 비어 있으므로
    control 은 그대로 hold 된다.
    """
    from src.controllers.rollout_endpoint import ObjectiveSpec, evaluate_price_point

    horizon = max(1, int(cfg.mpc.horizon_steps))
    point = evaluate_price_point(
        state.copy(),
        control,
        list(forecast)[:horizon],
        (),
        ObjectiveSpec(cfg=cfg, score_mode="raw", box_walk=False, depth_override=horizon),
    )
    if not point.states:
        return ()
    terminal = point.states[-1]
    out: Dict[str, float] = {}
    for link, densities in terminal.freeway_density.items():
        for index, rho in enumerate(densities):
            out[f"rho::{link}::{index}"] = _round(rho, digits)
    for name, source in (
        ("urban_queue", getattr(terminal, "urban_queue", {})),
        ("movement_queue", getattr(terminal, "urban_movement_queue", {})),
        ("ramp_queue", getattr(terminal, "ramp_queue", {})),
    ):
        for key, value in source.items():
            out[f"{name}::{key}"] = _round(value, digits)
    return tuple(sorted(out.items()))


def fingerprint(
    result: Any,
    cfg: ExperimentConfig,
    state: TrafficState,
    forecast: Sequence[DemandStep],
    leader_candidates: Sequence[Tuple[int, str, float, float]] = (),
    digits: int = 12,
) -> DecisionFingerprint:
    metadata = _numeric_metadata(result)
    control = result.control
    return DecisionFingerprint(
        state=terminal_state_digest(cfg, state, control, forecast, digits=digits),
        feasibility=_select(metadata, lambda k: "feasib" in k),
        safety_certificate=_select(metadata, lambda k: "b3cert" in k),
        fallback_grade=tuple(
            (key, _round(metadata[key], digits))
            for key in FALLBACK_GRADE_KEYS
            if key in metadata
        ),
        leader_candidates=tuple(
            (int(i), str(stage), _round(np_star, digits), _round(nuf_star, digits))
            for i, stage, np_star, nuf_star in leader_candidates
        ),
        command=(
            tuple(sorted((k, _round(v, digits)) for k, v in control.green_times.items())),
            tuple(sorted((k, _round(v, digits)) for k, v in control.ramp_metering.items())),
            tuple(sorted((k, _round(v, digits)) for k, v in control.vsl.items())),
            tuple(sorted((k, _round(v, digits)) for k, v in control.offsets.items())),
            _round(float(control.N_P_star), digits),
            _round(float(control.N_UF_star), digits),
        ),
    )


def compare(a: DecisionFingerprint, b: DecisionFingerprint) -> Dict[str, bool]:
    """다섯 필드 + `command` 의 정확 일치 여부."""
    out = {name: a.field(name) == b.field(name) for name in FIELDS}
    out["command"] = a.command == b.command
    return out


def field_diff(a: DecisionFingerprint, b: DecisionFingerprint, name: str) -> List[Tuple[str, Any, Any]]:
    """한 필드의 항목별 차이. 보고에 넣을 수치를 뽑는 용도."""
    left, right = (a.command, b.command) if name == "command" else (a.field(name), b.field(name))
    if name == "command":
        return [
            (channel, l, r)
            for channel, l, r in zip(
                ("green", "meter", "vsl", "offset", "N_P_star", "N_UF_star"), left, right
            )
            if l != r
        ]
    if name == "leader_candidates":
        return [
            (f"#{index}", l, r)
            for index, (l, r) in enumerate(zip(left, right))
            if l != r
        ] + [
            (f"#{index}", None, right[index])
            for index in range(len(left), len(right))
        ] + [
            (f"#{index}", left[index], None)
            for index in range(len(right), len(left))
        ]
    dl, dr = dict(left), dict(right)
    return [
        (key, dl.get(key), dr.get(key))
        for key in sorted(set(dl) | set(dr))
        if dl.get(key) != dr.get(key)
    ]


def command_within_one_quantum(
    a: DecisionFingerprint,
    b: DecisionFingerprint,
    quanta: Dict[str, float],
) -> bool:
    """명령이 정확 일치이거나 채널별 선언 양자화 1단계 이내인가.

    `quanta` 는 `{"green": s, "meter": veh/h, "vsl": km/h, "offset": s}`.
    """
    order = ("green", "meter", "vsl", "offset")
    for index, channel in enumerate(order):
        left, right = dict(a.command[index]), dict(b.command[index])
        if set(left) != set(right):
            return False
        limit = float(quanta[channel]) + 1.0e-9
        for key, value in left.items():
            if abs(value - right[key]) > limit:
                return False
    return True


# ---------------------------------------------------------------------------
# 평가 궤적 - 결정 지문만으로는 부족하다.
#
# 결정 지문은 필요조건이지 충분조건이 아니다. 후보가 포화하거나 fallback 이 선택되면
# rollout 값이 흔들려도 결정이 그대로일 수 있고(실측: 이 저장소의 lean fixture 에서
# 가격 schedule 의 레버를 전부 빼도 결정 지문이 안 움직인다), 그러면 twin 이 이빨을 잃는다.
# 그래서 두 경로가 **평가한 점의 목적함수 열**도 같은지 함께 본다.
# ---------------------------------------------------------------------------
_PRICE_POINT_MODULES = (
    "src.controllers.rollout_endpoint",
    "src.controllers.stackelberg_mpc",
    "src.controllers.stackelberg_wu_metered",
)


class PricePointSwap:
    """decide 한 번 동안 `evaluate_price_point` 를 다른 구현으로 바꿔 끼운다.

    `stackelberg_mpc` / `stackelberg_wu_metered` 는 import 시점에 이름을 묶으므로
    `rollout_endpoint` 만 갈아끼우면 새지 않는다 — 세 모듈 전부를 바꾼다.
    """

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.fn = fn
        self._saved: List[Tuple[Any, Any]] = []

    def __enter__(self) -> "PricePointSwap":
        import importlib

        for name in _PRICE_POINT_MODULES:
            module = importlib.import_module(name)
            if hasattr(module, "evaluate_price_point"):
                self._saved.append((module, module.evaluate_price_point))
                module.evaluate_price_point = self.fn
        return self

    def __exit__(self, *exc: Any) -> None:
        for module, original in self._saved:
            module.evaluate_price_point = original
        self._saved.clear()


def schedule_key(action_schedule: Sequence[Any], digits: int = 12) -> Tuple[Tuple[str, str, float], ...]:
    return tuple(
        (str(move.kind), str(move.key), _round(float(move.value), digits))
        for move in action_schedule
    )


def tracing(fn: Callable[..., Any], sink: List[Tuple[Any, ...]], digits: int = 12) -> Callable[..., Any]:
    """`evaluate_price_point` 호출을 순서대로 기록하는 래퍼(수치 경로 불변)."""

    def wrapped(state, previous, forecast, action_schedule, objective_spec):
        result = fn(state, previous, forecast, action_schedule, objective_spec)
        sink.append((
            schedule_key(action_schedule, digits),
            str(objective_spec.score_mode),
            _round(result.objective, digits),
            _round(result.partial_ttt, digits),
            bool(result.aborted),
            len(result.states),
        ))
        return result

    return wrapped


# ---------------------------------------------------------------------------
# 리더 후보 기록 - `DecisionResult` 는 평가된 후보 열을 노출하지 않는다.
# ---------------------------------------------------------------------------
class LeaderCandidateRecorder:
    """`_evaluate_full_candidate` 를 감싸 실제 full 평가된 후보를 순서대로 기록한다.

    수치 경로는 건드리지 않는다(원 메서드를 그대로 호출하고 반환값을 돌려준다).
    """

    def __init__(self, controller: Any) -> None:
        self.controller = controller
        self.rows: List[Tuple[int, str, float, float]] = []
        self._original: Optional[Callable[..., Any]] = None

    def __enter__(self) -> "LeaderCandidateRecorder":
        self._original = self.controller._evaluate_full_candidate

        def wrapped(index, action, *args, **kwargs):
            stage = kwargs.get("stage")
            if stage is None and len(args) >= 4:
                stage = args[3]
            self.rows.append(
                (int(index), str(stage or "coarse"), float(action.N_P_star), float(action.N_UF_star))
            )
            return self._original(index, action, *args, **kwargs)

        self.controller._evaluate_full_candidate = wrapped
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._original is not None:
            self.controller._evaluate_full_candidate = self._original
