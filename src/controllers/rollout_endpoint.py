# N7 production rollout endpoint - 모든 leader rollout·가격 평가가 통과하는 단일 순수 함수
"""`evaluate_price_point` — 상태 투영·제어독립 동역학·레버 반응·목적함수 성분 평가.

책임 분리(v3 N7).
  - MPC(`stackelberg_mpc` / `stackelberg_wu_metered`)가 **후보 생성·목적함수 비교·action 선택**을 소유한다.
  - 이 endpoint 는 한 점(action_schedule)을 받아 **평가만** 한다. 후보를 만들지도, 고르지도 않는다.
  - exact FD, SPSA, no-control replay, leader 후보 채점이 **전부 이 함수**와
    `ObjectiveSpec`(동결 파라미터)을 통과한다. 우회 경로가 생기면 `endpoint_active()`
    프로브로 잡힌다(`src/tests/test_rollout_endpoint.py`).

순수성. cfg 와 spec 은 읽기 전용으로만 쓰고, `state`/`previous` 는 복사한 뒤 만진다.
같은 인자면 같은 결과다(plant `run_coupled_interval` 자체가 결정론적이므로).
"""
from __future__ import annotations

import copy as _copy
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from src.models.demand import DemandStep
from src.models.state import (
    PRIMARY_PHASE,
    ControlAction,
    ExperimentConfig,
    TrafficState,
    clamp_primary_green,
    set_signal_green,
)

# 가격 채널 4종. `apply_action_schedule` 이 이 전부를 다룬다(채널 커버리지 100%의 정의).
LEVER_KINDS: Tuple[str, ...] = ("green", "meter", "vsl", "offset")
# "vsl_link" 는 vsl 채널의 하위형 — segment 키가 아니라 link fallback 키를 직접 덮는다.
# (joint vsl×metering 스텐실이 link 대표값을 min 이 아니라 지정값으로 두는 규약을 보존한다.)
MOVE_KINDS: Tuple[str, ...] = LEVER_KINDS + ("vsl_link",)

# ---- 계측(우회 호출 0 검증 전용, 수치 경로 불변) --------------------------------
ENDPOINT_CALLS: int = 0   # evaluate_price_point 호출 수
ROLLOUT_CALLS: int = 0    # 실제 전역 rollout 수행 수 (endpoint 호출당 정확히 1)
_ACTIVE: int = 0


def endpoint_active() -> bool:
    """지금 endpoint 프레임 안인가. 전역 plant rollout이 밖에서 일어나면 우회 호출이다."""
    return _ACTIVE > 0


def reset_counters() -> None:
    global ENDPOINT_CALLS, ROLLOUT_CALLS
    ENDPOINT_CALLS = 0
    ROLLOUT_CALLS = 0


@dataclass(frozen=True)
class LeverMove:
    """레버 한 개의 절대 setpoint. kind 는 `LEVER_KINDS` 중 하나."""

    kind: str
    key: str
    value: float


@dataclass(frozen=True)
class ObjectiveSpec:
    """평가 파라미터 동결 묶음. FD·SPSA·replay 가 같은 spec 을 써야 비교가 성립한다."""

    cfg: ExperimentConfig
    # ---- rollout 동역학 ----
    depth_override: Optional[int] = None
    abort_above: Optional[float] = None
    # box-walk(다중스텝 레버 반응). green 축 walk 은 follower trust 반경을 쓴다.
    box_walk: bool = True
    green_trust_sec: Optional[float] = None
    walk_previous: Optional[ControlAction] = None
    # ---- 목적함수 성분 ----
    score_mode: str = "raw"          # "raw" | "price" | "leader"
    far_enabled: bool = False        # terminal MFD tail(far) 가산
    price_hinge: bool = False        # force=True hinge 를 price_hinge_weight 로 가산
    price_hinge_weight: float = 1.0
    leader_hinge: bool = False       # cfg 게이트를 따르는 leader hinge 가산
    protected_queue: bool = False    # 보호 movement 큐 초과 벌점
    hinge_forecast: bool = False     # hinge 에 forecast(폐쇄 세그 면제)를 넘길지
    # ---- 부가 성분 ----
    barrier: bool = False
    barrier_weight: float = 1.0
    barrier_spillback_frac: float = 0.2
    max_rho_link: Optional[str] = None
    split_ttt: bool = False          # freeway/urban TTT 분해가 필요한 호출용


@dataclass
class PricePointResult:
    """한 점의 평가 결과. `objective` = spec 이 지시한 성분 합."""

    control: ControlAction
    states: List[TrafficState]
    ttt: float
    objective: float
    far: float = 0.0
    price_hinge: float = 0.0
    leader_hinge: float = 0.0
    protected_queue: float = 0.0
    barrier: float = 0.0
    max_rho: float = 0.0
    freeway_ttt: float = 0.0
    urban_ttt: float = 0.0
    aborted: bool = False
    # abort 시 `ttt` 는 inf 로 막지만(기존 규약 불변), 조기절단 후보의 목적함수를 부분합에서
    # 이어 계산하는 호출처(centralized/distributed grid)를 위해 유한 누적값을 함께 낸다.
    partial_ttt: float = 0.0


# ---------------------------------------------------------------------------
# 1) 상태 투영 - action_schedule 을 previous 위에 얹어 평가용 control 을 만든다.
# ---------------------------------------------------------------------------
def apply_action_schedule(
    previous: ControlAction,
    action_schedule: Sequence[LeverMove],
    spec: ObjectiveSpec,
) -> ControlAction:
    """`previous` 를 hold 한 채 schedule 의 레버만 절대값으로 덮는다(원본 불변).

    규약은 기존 per-channel rollout 헬퍼와 동일하다.
      green    : 주 현시 = value, 나머지 현시는 예산에서 사영(사이클 예산 보존)
      meter    : ramp_metering[key] = value
      vsl      : segment 키 설정 + link fallback 키를 min 으로 동기화(plant 정합)
      vsl_link : link fallback 키를 지정값으로 직접 설정(min 동기화보다 우선)
      offset   : offsets[key] = value (원형 규약 `% cycle` 은 호출처가 이미 적용해 넘긴다)
    """
    if not action_schedule:
        # 빈 schedule = previous 를 그대로 hold. plant(`run_coupled_interval`)는 control 을
        # 변경하지 않으므로 사본을 만들지 않는다(구 `_predict` 와 객체 동일성까지 일치).
        return previous
    net = spec.cfg.network
    control = previous.copy()
    touched_links: Dict[str, float] = {}
    link_overrides: Dict[str, float] = {}
    for move in action_schedule:
        kind = move.kind
        value = float(move.value)
        if kind == "green":
            set_signal_green(control, net, move.key, value)
        elif kind == "meter":
            control.ramp_metering[move.key] = value
        elif kind == "vsl":
            control.vsl[move.key] = value
            link = move.key.split("__seg")[0]
            touched_links[link] = min(touched_links.get(link, float("inf")), value)
        elif kind == "vsl_link":
            link_overrides[move.key] = value
        elif kind == "offset":
            control.offsets[move.key] = value
        else:
            raise ValueError(f"unknown lever kind: {kind}")
    for link, vmin in touched_links.items():
        control.vsl[link] = min(float(control.vsl.get(link, vmin)), vmin)
    for link, value in link_overrides.items():
        control.vsl[link] = value
    return control


# ---------------------------------------------------------------------------
# 2) 제어독립 동역학 + 레버 반응(box-walk) - 구 `StackelbergMPCController._predict`.
# ---------------------------------------------------------------------------
def _rollout(
    state: TrafficState,
    control: ControlAction,
    forecast: List[DemandStep],
    spec: ObjectiveSpec,
) -> Tuple[List[TrafficState], float, bool, float, float]:
    """horizon(+leader_value_depth) rollout. (states, partial_ttt, aborted, fw_ttt, ur_ttt).

    두번째 원소는 abort 여부와 무관하게 **유한 누적 TTT** 다. inf 로 막는 것은
    `evaluate_price_point` 가 `PricePointResult.ttt` 에서만 한다.
    """
    from src.simulation.coupling import run_coupled_interval

    global ROLLOUT_CALLS
    ROLLOUT_CALLS += 1
    cfg = spec.cfg
    abort_above = spec.abort_above
    previous = spec.walk_previous
    s = state.copy()
    states: List[TrafficState] = []
    total_ttt = 0.0
    freeway_ttt = 0.0
    urban_ttt = 0.0
    # leader full rollout: horizon + leader_value_depth 만큼(V 포함).
    depth = cfg.mpc.horizon_steps + max(0, int(getattr(cfg.mpc, "leader_value_depth", 0)))
    if spec.depth_override is not None:
        depth = max(1, int(spec.depth_override))
    # BOX-WALK(2026-07-17): rollout 2번째 interval부터 metering 을 후보 intent(N_UF*)
    # 방향으로 스텝당 램프별 ±R 씩 전진시켜 다중스텝 도달을 채점에 반영한다.
    _walk_r = getattr(cfg.mpc, "seg13_meter_box_veh_h", None)
    _do_walk = (
        spec.box_walk
        and bool(getattr(cfg.mpc, "leader_rollout_box_walk", False))
        and _walk_r is not None
        and bool(control.ramp_metering)
        and float(getattr(control, "N_UF_star", 0.0)) > 0.0
    )
    if _do_walk:
        _r_dn = float(_walk_r)
        _bu_w = getattr(cfg.mpc, "seg13_meter_box_up_veh_h", None)
        _r_up = float(_bu_w) if _bu_w is not None else _r_dn
        _net = cfg.network
        _caps = {r: float(_net.ramp_capacity_veh_h[r]) for r in control.ramp_metering}
        _target_total = float(control.N_UF_star)
    # BOX-WALK-VG: VSL·green 도 끝 지속(edge persistence)으로 다중스텝 이동을 모델링.
    _vg_moves: list = []
    if (
        spec.box_walk
        and bool(getattr(cfg.mpc, "leader_rollout_box_walk_vg", False))
        and previous is not None
    ):
        _rv = getattr(cfg.mpc, "seg13_vsl_box_kmh", None)
        if _rv is not None:
            _rv = float(_rv)
            _vmin = float(min(cfg.freeway_follower.vsl_set))
            _vmax = float(max(cfg.freeway_follower.vsl_set))
            for _key, _v in control.vsl.items():
                if "__seg" not in _key:
                    continue
                _pv = previous.vsl.get(_key)
                if _pv is None:
                    continue
                _d0 = float(_v) - float(_pv)
                if _d0 >= _rv - 1.0e-6:
                    _vg_moves.append(("vsl", _key, _rv, _vmin, _vmax))
                elif _d0 <= -(_rv - 1.0e-6):
                    _vg_moves.append(("vsl", _key, -_rv, _vmin, _vmax))
        _gt = spec.green_trust_sec
        if _gt:
            _gt = float(_gt)
            # 주 현시 상자 양끝 — 나머지 현시가 green_min 을 지킬 수 있는 범위다.
            _glo = clamp_primary_green(cfg.network, float("-inf"))
            _ghi = clamp_primary_green(cfg.network, float("inf"))
            _primary_suffix = "_" + PRIMARY_PHASE
            for _key, _g in list(control.green_times.items()):
                if not _key.endswith(_primary_suffix):
                    continue
                _pg = previous.green_times.get(_key)
                if _pg is None:
                    continue
                _d0 = float(_g) - float(_pg)
                if _d0 >= _gt - 1.0e-6:
                    _vg_moves.append(("green", _key, _gt, _glo, _ghi))
                elif _d0 <= -(_gt - 1.0e-6):
                    _vg_moves.append(("green", _key, -_gt, _glo, _ghi))
    if _do_walk or _vg_moves:
        # 얕은 사본 + 변형할 dict만 교체 — 원본(commit 후보 control)은 불변.
        _ctrl_w = _copy.copy(control)
        if _do_walk:
            _ctrl_w.ramp_metering = dict(control.ramp_metering)
        if _vg_moves:
            _ctrl_w.vsl = dict(control.vsl)
            _ctrl_w.green_times = dict(control.green_times)
        control = _ctrl_w
    for _k, demand in enumerate(forecast[:depth]):
        if _vg_moves and _k >= 1:
            for _kind, _key, _rate, _lo, _hi in _vg_moves:
                if _kind == "vsl":
                    control.vsl[_key] = min(max(
                        float(control.vsl[_key]) + _rate, _lo), _hi)
                else:
                    _np1 = min(max(
                        float(control.green_times[_key]) + _rate, _lo), _hi)
                    # 나머지 현시가 예산을 나눠 갖는다(사이클 예산 불변).
                    _sig = _key[: -len("_" + PRIMARY_PHASE)]
                    set_signal_green(control, cfg.network, _sig, _np1)
            # link 대표 VSL = min(seg) 재계산(plant fallback 정합).
            for _lnk in cfg.network.freeway_links:
                _sv = [float(v) for k, v in control.vsl.items()
                       if k.startswith(_lnk + "__seg")]
                if _sv:
                    control.vsl[_lnk] = min(_sv)
        if _do_walk and _k >= 1:
            _m = control.ramp_metering
            _gap = _target_total - sum(_m.values())
            if _gap > 1.0e-9:
                # 여유 큰 램프부터 스텝당 ≤ R_up씩 올림.
                for _r in sorted(_m, key=lambda x: _caps[x] - _m[x], reverse=True):
                    _step = min(_r_up, _caps[_r] - _m[_r], _gap)
                    if _step <= 0.0:
                        continue
                    _m[_r] += _step
                    _gap -= _step
                    if _gap <= 1.0e-9:
                        break
            elif _gap < -1.0e-9:
                _need = -_gap
                for _r in sorted(_m, key=lambda x: _m[x], reverse=True):
                    _step = min(_r_dn, _m[_r], _need)
                    if _step <= 0.0:
                        continue
                    _m[_r] -= _step
                    _need -= _step
                    if _need <= 1.0e-9:
                        break
        result = run_coupled_interval(s, control, demand, cfg)
        s.time_sec += cfg.simulation.control_interval
        total_ttt += result.freeway_ttt + result.urban_ttt
        if spec.split_ttt:
            freeway_ttt += float(result.freeway_ttt)
            urban_ttt += float(result.urban_ttt)
        states.append(s.copy())
        # TTT는 비음 누적 + 모든 penalty/far ≥0 → 부분합이 incumbent를 넘으면 이 후보의
        # 최종 objective도 반드시 초과 = exact pruning(argmin 불변). inf로 즉시 기각.
        if abort_above is not None and total_ttt > abort_above:
            return states, float(total_ttt), True, float(freeway_ttt), float(urban_ttt)
    return states, float(total_ttt), False, float(freeway_ttt), float(urban_ttt)


# ---------------------------------------------------------------------------
# 3) 목적함수 성분.
# ---------------------------------------------------------------------------
def _barrier_component(states: List[TrafficState], spec: ObjectiveSpec) -> float:
    """freeway rho_crit 초과차량 + urban 링크 spillback 여유부족(선형 hinge, veh·h)."""
    from src.models.urban_queue_model import _effective_available_space

    if not spec.barrier:
        return 0.0
    net = spec.cfg.network
    t_c_h = float(spec.cfg.simulation.T_c_h)
    seg_veh = float(net.freeway_segment_length_km) * float(net.freeway_lanes)
    rho_crit = float(net.rho_crit)
    spill_frac = float(spec.barrier_spillback_frac)
    weight = float(spec.barrier_weight)
    barrier = 0.0
    for s in states:
        for link in net.freeway_links:
            for rho in s.freeway_density.get(link, []):
                excess = max(0.0, float(rho) - rho_crit) * seg_veh
                barrier += weight * excess * t_c_h
        for u_link, cap in net.urban_link_storage_veh.items():
            space = float(_effective_available_space(s, spec.cfg, u_link))
            deficit = max(0.0, spill_frac * float(cap) - space)
            barrier += weight * deficit * t_c_h
    return float(barrier)


def _protected_queue_component(states: List[TrafficState], spec: ObjectiveSpec) -> float:
    """보호 movement 큐 초과 벌점 — 가격 채점(`_price_ttt`)에만 들어간다."""
    if not spec.protected_queue or not states:
        return 0.0
    mv = str(getattr(spec.cfg.mpc, "protected_queue_movement", "") or "")
    if not mv:
        return 0.0
    weight = float(getattr(spec.cfg.mpc, "protected_queue_weight", 0.0))
    if weight <= 0.0:
        return 0.0
    q_max = float(getattr(spec.cfg.mpc, "protected_queue_max_veh", 50.0))
    tc_h = float(spec.cfg.simulation.T_c_h)
    out = 0.0
    for s in states:
        q = max(0.0, float(s.urban_movement_queue.get(mv, 0.0)))
        out += weight * max(0.0, q - q_max) * tc_h
    return float(out)


def _max_rho_component(states: List[TrafficState], spec: ObjectiveSpec) -> float:
    """지정 링크의 예측 밀도 최대(전 세그먼트·전 horizon). B3CERT 안전 증명서 재료."""
    if spec.max_rho_link is None:
        return 0.0
    max_rho = 0.0
    for s in states:
        for rho in s.freeway_density.get(spec.max_rho_link, []):
            max_rho = max(max_rho, float(rho))
    return float(max_rho)


# ---------------------------------------------------------------------------
# 4) production endpoint.
# ---------------------------------------------------------------------------
def evaluate_price_point(
    state: TrafficState,
    previous: ControlAction,
    forecast: List[DemandStep],
    action_schedule: Sequence[LeverMove],
    objective_spec: ObjectiveSpec,
) -> PricePointResult:
    """한 점(previous + action_schedule)을 rollout 해 목적함수 성분을 낸다.

    후보를 만들지 않고 고르지도 않는다 — 평가만 한다. 호출 1회 = 전역 rollout 1회다.
    """
    global ENDPOINT_CALLS, _ACTIVE
    spec = objective_spec
    ENDPOINT_CALLS += 1
    _ACTIVE += 1
    try:
        control = apply_action_schedule(previous, action_schedule, spec)
        states, partial_ttt, aborted, fw_ttt, ur_ttt = _rollout(state, control, forecast, spec)
    finally:
        _ACTIVE -= 1

    # abort 된 점은 기존대로 inf 로 막아 argmin 에서 확실히 밀어낸다.
    ttt = float("inf") if aborted else float(partial_ttt)

    hinge_fc = forecast if spec.hinge_forecast else None
    objective = float(ttt)
    far = 0.0
    price_hinge = 0.0
    leader_hinge = 0.0
    pq = 0.0
    if spec.score_mode != "raw":
        # 지연 import 는 순환 참조 회피용(stackelberg_mpc 가 이 모듈을 import 한다).
        from src.controllers.stackelberg_mpc import leader_hinge_cost, mfd_far_cost_to_go

        if spec.far_enabled and states:
            far = float(mfd_far_cost_to_go(spec.cfg, states[-1]))
            objective += far
        if spec.price_hinge and states:
            price_hinge = float(spec.price_hinge_weight) * float(
                leader_hinge_cost(spec.cfg, states, hinge_fc, force=True)
            )
            objective += price_hinge
        if spec.leader_hinge:
            leader_hinge = float(leader_hinge_cost(spec.cfg, states, hinge_fc))
            objective += leader_hinge
        pq = _protected_queue_component(states, spec)
        objective += pq

    return PricePointResult(
        control=control,
        states=states,
        ttt=float(ttt),
        objective=float(objective),
        far=far,
        price_hinge=price_hinge,
        leader_hinge=leader_hinge,
        protected_queue=pq,
        barrier=_barrier_component(states, spec),
        max_rho=_max_rho_component(states, spec),
        freeway_ttt=float(fw_ttt),
        urban_ttt=float(ur_ttt),
        aborted=bool(aborted),
        partial_ttt=float(partial_ttt),
    )
