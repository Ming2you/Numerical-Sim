# N8-1 eps_J_endpoint 측정 하네스 - 동일 control 을 N회 평가해 endpoint 재현성 잡음을 낸다
"""`eps_J_endpoint` 와 `eps_g` 를 계획 N8-1 정의대로 산출한다.

## 왜 별도 모듈인가

계획 N8-1 은 "endpoint 재현성 잡음을 먼저 잰다" 고 하는데 하네스가 없었다. 그래서
N8-2 의 PASS 조항 `exact-FD 재채점 regret < max(2*eps_J_endpoint, 0.5%*|J_FD|)` 을
판정할 수 없었다.

## 두 잡음 척도를 섞지 않는다 (fail-closed)

N5 의 `eps_J_vissim` 은 **VISSIM 런간 분산**(하한 `1e-6 veh*h`)이고 N9 의 `ΔJ` 재료성
판정 전용이다. 이 모듈이 재는 `eps_J_endpoint` 는 **플랜트 endpoint 재현성**이고 하한이
세 자리 아래다. VISSIM 척도를 endpoint 자리에 넣으면 `eps_g` 가 과대해져
`|intercept| <= median(eps_g)` 가 느슨해지고 재료 표본이 줄어 지지 요건이 무너진다.

그래서 표본 출처(`source`)를 받고 `plant_endpoint_repeat` 이 아니면 **거부**한다.
`VISSIM/scripts/build_parent_run_spec.py:113` 의 `eps_j_endpoint` 와 같은 게이트다
(문자열 상수 일치를 `src/tests/test_endpoint_noise.py` 가 검사한다).

`eps_g` 는 맨 float 을 받지 않고 검증된 `EndpointNoiseResult` 만 받는다. 출처를 증명할 수
없는 숫자로는 환산 자체가 불가능해야 섞임이 구조적으로 막힌다.

## 산식이 spec builder 와 다르다 — 의도된 차이다

    이 모듈 (계획 N8-1 본문)   eps = max(q99(|J_r - J_1|), 1e-9 * max(|J_1|, 1))
    build_parent_run_spec.py   eps = max(1e-9, max(J) - min(J))

편차 기준점(J_1 대 min)과 하한(상대 대 절대)이 둘 다 다르다. 여기서는 계획 N8-1 본문을
따른다 — N8-1/N8-2 의 PASS 조항이 그 정의를 쓰기 때문이다. 두 정의를 하나로 합칠지는
계획 소유자의 결정이라 이 모듈은 고르지 않고 차이를 기록만 한다.

## 관측된 사실 (2026-08-11)

실 endpoint 는 **완전 결정론**이다. 동일 입력 20회 반복, `PYTHONHASHSEED` {0,1,12345,999},
`grid_parallel_backend` {serial,thread,process}, 1채널/4채널 schedule 전부에서
목적함수가 비트 단위로 같았다(spread = 0). `_rollout` 은 단일 스레드 루프이고
`run_coupled_interval` 에 난수도 프로세스 풀도 없다. 따라서 잡음 표본항 `q99` 는 0 이고
`eps_J_endpoint` 는 전적으로 상대 하한 `1e-9 * max(|J_1|, 1)` 이 정한다.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA_VERSION = "endpoint-noise-v1"

# 표본 출처. build_parent_run_spec.py:50-51 과 문자열이 같아야 두 저장소가 같은 게이트를 쓴다.
ENDPOINT_SOURCE = "plant_endpoint_repeat"
VISSIM_SOURCE = "vissim_base_replay"

# 계획 N8-1: "동일 control 목적함수를 최소 20회 평가해".
MIN_REPEATS = 20
DEFAULT_REPEATS = 20

# 계획 N8-1 의 상대 하한. N5 의 `1e-6 veh*h` 절대 하한과 혼동하지 마라.
RELATIVE_FLOOR = 1.0e-9

# 상태 출처. 합성 상태 측정은 qualification 측정이 아니다(계획: "합성 측정을 믿지 마라").
SYNTHETIC_STATE_SOURCE = "synthetic_initial"

STATUS_OK = "OK"
STATUS_NOT_EVALUATED = "NOT_EVALUATED"


class EndpointNoiseError(ValueError):
    """두 잡음 척도가 섞이거나 표본이 잡음 측정에 부적격일 때 던진다."""


def nearest_rank_quantile(values: Sequence[float], q: float) -> float:
    """nearest-rank 분위수. 보간을 쓰지 않아 표본 수와 무관하게 결정적이다.

    `ceil(q * n)` 번째 작은 값(1-indexed). n=20, q=0.99 면 20번째 = 최대값이다.
    """
    ordered = sorted(float(v) for v in values)
    if not ordered:
        raise EndpointNoiseError("nearest_rank_quantile needs at least one value")
    if not 0.0 <= float(q) <= 1.0:
        raise EndpointNoiseError(f"quantile must be in [0, 1], got {q!r}")
    rank = max(1, math.ceil(float(q) * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _check_source(source: str) -> None:
    if source != ENDPOINT_SOURCE:
        raise EndpointNoiseError(
            f"eps_j_endpoint requires source={ENDPOINT_SOURCE!r}, got {source!r} "
            "(VISSIM 런간 분산은 eps_j_vissim 이다 - 두 값을 섞지 마라)"
        )


def _check_objectives(
    objectives: Sequence[float], *, require_full_count: bool
) -> List[float]:
    values = [float(v) for v in objectives]
    if len(values) < 2:
        raise EndpointNoiseError("need at least two endpoint repeats to measure spread")
    if require_full_count and len(values) < MIN_REPEATS:
        raise EndpointNoiseError(
            f"need {MIN_REPEATS} endpoint repeats, got {len(values)}"
        )
    for v in values:
        if not math.isfinite(v):
            raise EndpointNoiseError(
                f"non-finite objective {v!r} - abort 된 rollout 로는 잡음을 잴 수 없다"
            )
    return values


def eps_j_endpoint(
    objectives: Sequence[float], *, source: str, require_full_count: bool = False
) -> float:
    """eps_J_endpoint = max(q99(|J_r - J_1|), 1e-9 * max(|J_1|, 1)).

    **VISSIM 표본을 받으면 거부한다.** 척도가 다르고 하한이 세 자리 다르다.
    """
    _check_source(source)
    values = _check_objectives(objectives, require_full_count=require_full_count)
    j1 = values[0]
    deviations = [abs(v - j1) for v in values]
    return max(
        nearest_rank_quantile(deviations, 0.99), RELATIVE_FLOOR * max(abs(j1), 1.0)
    )


@dataclass(frozen=True)
class EndpointNoiseResult:
    """한 qualification state 의 endpoint 재현성 측정 기록. 파생값은 property 다."""

    source: str
    state_id: str
    state_source: str
    objectives: Tuple[float, ...]
    require_full_count: bool = True
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _check_source(self.source)
        _check_objectives(self.objectives, require_full_count=self.require_full_count)
        if not str(self.state_source).strip():
            raise EndpointNoiseError(
                "state_source must be recorded (합성 상태와 실 anchor 상태를 구분해야 한다)"
            )

    @property
    def repeats(self) -> int:
        return len(self.objectives)

    @property
    def full_count(self) -> bool:
        return self.repeats >= MIN_REPEATS

    @property
    def j1(self) -> float:
        return float(self.objectives[0])

    @property
    def deviations(self) -> Tuple[float, ...]:
        j1 = self.j1
        return tuple(abs(float(v) - j1) for v in self.objectives)

    @property
    def max_abs_deviation(self) -> float:
        return max(self.deviations)

    @property
    def q99_abs_deviation(self) -> float:
        return nearest_rank_quantile(self.deviations, 0.99)

    @property
    def relative_floor(self) -> float:
        return RELATIVE_FLOOR * max(abs(self.j1), 1.0)

    @property
    def eps_j_endpoint(self) -> float:
        return eps_j_endpoint(self.objectives, source=self.source)

    @property
    def deterministic(self) -> bool:
        return len(set(self.objectives)) == 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "state_id": self.state_id,
            "state_source": self.state_source,
            "repeats": self.repeats,
            "full_count": self.full_count,
            "objectives": list(self.objectives),
            "j1": self.j1,
            "max_abs_deviation": self.max_abs_deviation,
            "q99_abs_deviation": self.q99_abs_deviation,
            "relative_floor": self.relative_floor,
            "eps_j_endpoint": self.eps_j_endpoint,
            "deterministic": self.deterministic,
        }


@dataclass(frozen=True)
class EpsGResult:
    """eps_g = 2 * eps_J_endpoint / realized_span. 못 재면 NOT_EVALUATED 로 남긴다."""

    status: str
    reason: str
    coordinate: str
    realized_span: Optional[float]
    eps_j_endpoint: Optional[float]
    eps_g: Optional[float]
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": self.reason,
            "coordinate": self.coordinate,
            "realized_span": self.realized_span,
            "eps_j_endpoint": self.eps_j_endpoint,
            "eps_g": self.eps_g,
        }


def eps_g_from_endpoint_noise(
    noise: EndpointNoiseResult,
    realized_span: Optional[float] = None,
    *,
    coordinate: str = "",
) -> EpsGResult:
    """검증된 endpoint 측정에서만 eps_g 를 환산한다.

    `realized_span` 은 **요청 진폭이 아니라 경계된 실현 변위**다(계획 N8-1). 아직 재지
    않았으면 0 으로 때우지 말고 NOT_EVALUATED 로 남긴다.
    """
    if not isinstance(noise, EndpointNoiseResult):
        raise EndpointNoiseError(
            "eps_g must be derived from a validated EndpointNoiseResult "
            "(맨 숫자는 출처를 증명하지 못한다 - eps_J_vissim 이 섞일 수 있다)"
        )
    eps_j = noise.eps_j_endpoint
    if realized_span is None:
        return EpsGResult(
            status=STATUS_NOT_EVALUATED,
            reason="realized_span not measured (N8-1 FD 실현 변위 미측정)",
            coordinate=coordinate,
            realized_span=None,
            eps_j_endpoint=eps_j,
            eps_g=None,
        )
    span = float(realized_span)
    if not math.isfinite(span) or span <= 0.0:
        return EpsGResult(
            status=STATUS_NOT_EVALUATED,
            reason=f"realized_span must be finite and positive, got {span!r}",
            coordinate=coordinate,
            realized_span=span if math.isfinite(span) else None,
            eps_j_endpoint=eps_j,
            eps_g=None,
        )
    return EpsGResult(
        status=STATUS_OK,
        reason="",
        coordinate=coordinate,
        realized_span=span,
        eps_j_endpoint=eps_j,
        eps_g=2.0 * eps_j / span,
    )


def measure_endpoint_noise(
    state,
    previous,
    forecast,
    action_schedule,
    objective_spec,
    *,
    repeats: int = DEFAULT_REPEATS,
    state_id: str = "",
    state_source: str = SYNTHETIC_STATE_SOURCE,
    require_full_count: bool = True,
) -> EndpointNoiseResult:
    """동일 control/state/forecast 로 endpoint 를 `repeats` 회 평가한다.

    endpoint 는 인자를 복사해 쓰므로 같은 객체를 그대로 반복해 넘긴다 - 그것이 "동일
    입력" 의 정의다. 인자 불변은 `evaluate_price_point` 의 순수성 계약이다.
    """
    from src.controllers.rollout_endpoint import evaluate_price_point

    n = int(repeats)
    if n < 2:
        raise EndpointNoiseError("need at least two endpoint repeats to measure spread")
    if require_full_count and n < MIN_REPEATS:
        raise EndpointNoiseError(f"need {MIN_REPEATS} endpoint repeats, got {n}")
    objectives = [
        float(
            evaluate_price_point(
                state, previous, forecast, action_schedule, objective_spec
            ).objective
        )
        for _ in range(n)
    ]
    return EndpointNoiseResult(
        source=ENDPOINT_SOURCE,
        state_id=state_id,
        state_source=state_source,
        objectives=tuple(objectives),
        require_full_count=require_full_count,
    )


# ---------------------------------------------------------------------------
# CLI - 합성 상태 결정론 확인용. qualification 측정은 실 anchor 상태를 받아야 한다.
# ---------------------------------------------------------------------------
def _synthetic_fixture(horizon_steps: int):
    from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
    from src.models.demand import DemandProfile, ScenarioConfig
    from src.models.state import ControlAction, ExperimentConfig, TrafficState

    cfg = ExperimentConfig.from_file(
        "src/config/default.yaml",
        {
            "simulation": {"T_total": 360.0},
            "mpc": {
                "horizon_steps": horizon_steps,
                "relaxed_quantized_controls": True,
                "grid_parallel_backend": "serial",
                "leader_global_refresh_sec": 1.0e9,
                "leader_candidate_count": 2,
                "max_nash_iter": 2,
            },
        },
    )
    controller = StackelbergWuMeteredController(cfg)
    profile = DemandProfile(
        cfg, ScenarioConfig("peak_demand", urban_scale=1.0, freeway_scale=1.0, ramp_scale=1.0)
    )
    return (
        cfg,
        controller,
        TrafficState.initial(cfg),
        ControlAction.fixed(cfg),
        profile.horizon(0.0, horizon_steps + 3),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    from src.controllers.rollout_endpoint import LeverMove

    parser = argparse.ArgumentParser(description="Measure eps_J_endpoint (N8-1)")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--horizon", type=int, default=3)
    parser.add_argument("--realized-span", type=float, default=None)
    args = parser.parse_args(argv)

    cfg, controller, state, previous, forecast = _synthetic_fixture(args.horizon)
    try:
        spec = controller._rollout_spec(score_mode="price")
        schedule = (LeverMove("green", sorted(cfg.network.signals)[0], 40.0),)
        noise = measure_endpoint_noise(
            state,
            previous,
            forecast,
            schedule,
            spec,
            repeats=args.repeats,
            state_id=f"synthetic-peak-H{args.horizon}",
            state_source=SYNTHETIC_STATE_SOURCE,
        )
    finally:
        controller.close()

    eps_g = eps_g_from_endpoint_noise(noise, args.realized_span, coordinate="green")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "endpoint_noise": noise.to_dict(),
        "eps_g": eps_g.to_dict(),
        "warning": (
            "state_source=synthetic_initial - 합성 상태다. N8-1 qualification 측정은 "
            "N5 부모-anchor 실 상태를 넣어 다시 돌려야 한다."
        ),
    }
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(
        "repeats=%d deterministic=%s J1=%.17g max_dev=%.17g eps_J_endpoint=%.17g eps_g=%s"
        % (
            noise.repeats,
            noise.deterministic,
            noise.j1,
            noise.max_abs_deviation,
            noise.eps_j_endpoint,
            eps_g.status if eps_g.eps_g is None else "%.17g" % eps_g.eps_g,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
