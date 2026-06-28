# 신호 한 개의 movement 큐만 전진시키는 Wu식 국소 plant stepper (이웃 입력 동결)
"""Wu(2022) §IV-D 충실 follower의 핵심 신규 구현물 — agent i(=신호 1개)의 국소동역학 f_i.

전체망 plant(`urban_step`/`run_coupled_interval`)를 일절 호출하지 않는다. agent i의
movement 큐 q_m만 N_p×K_cu substep 전진시키며, 이웃에서 들어오는 도착(arr)·이웃 downstream
링크 가용공간(S_eff)은 결합변수로 **고정**한다. 비용은 자기 차량수 합(자기 TTS)뿐이다.

서비스/spillback 회계는 `urban_substep`(urban_queue_model.py 877~964행)을 per-signal로 복제한다.
- service_m = min(q_m, green_fraction(phase)·cap_flow_m·dt)
- 같은 receiving 링크로 가는 movement들은 그 링크의 S_eff(가용공간)를 공유(`_allocate_receiving_counts`).
- 자기 내부 링크(이 신호의 다른 movement origin)면 S_eff를 전진 중 갱신, 이웃/sink 링크면 고정.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

from src.models.state import ControlAction, ExperimentConfig
from src.models.urban_queue_model import (
    _allocate_receiving_counts,
    _movement_capacity_flow,
    _phase_green_fraction,
)


@dataclass
class LocalSignalModel:
    """신호 i의 국소 rollout에 필요한, control과 무관한 정적 데이터(컨트롤러가 1회 구성).

    cap_flow는 control.inflow_outflow_allocation에 의존할 수 있으나 WU green-only 권한에서는
    allocation이 비어 있어 movement_capacity로 고정된다(여기서 미리 계산해 캐시)."""

    signal: str
    cfg: ExperimentConfig
    movements: List[str]
    specs: Dict[str, Mapping[str, object]]
    # movement -> 소속 phase id ("p1"/"p2")
    phase_of: Dict[str, str]
    # movement -> receiving 링크 키(없으면 "")
    receiving_of: Dict[str, str]
    # movement -> origin 링크 키(점큐가 점유하는 링크; 자기 내부 S_eff 갱신용)
    origin_of: Dict[str, str]
    # movement -> beta(phase arr 분배 가중)
    beta_of: Dict[str, float]
    # movement -> cap_flow[veh/h] (control 무관 캐시)
    cap_flow_of: Dict[str, float]
    receiving_space_rule: str


def build_local_model(
    cfg: ExperimentConfig,
    signal: str,
    specs: Mapping[str, Mapping[str, object]],
    phase_movements: Mapping[str, Mapping[str, List[str]]],
) -> LocalSignalModel:
    movements: List[str] = []
    phase_of: Dict[str, str] = {}
    receiving_of: Dict[str, str] = {}
    origin_of: Dict[str, str] = {}
    beta_of: Dict[str, float] = {}
    cap_flow_of: Dict[str, float] = {}
    # WU green-only 권한에서 allocation이 비어 cap_flow가 control 무관이므로 빈 control로 캐시한다.
    neutral_control = ControlAction.uncontrolled(cfg)
    neutral_control.inflow_outflow_allocation = {}
    for pid in ("p1", "p2"):
        for movement in phase_movements[signal][pid]:
            spec = specs[movement]
            movements.append(movement)
            phase_of[movement] = pid
            receiving_of[movement] = str(spec.get("receiving_link", ""))
            origin_of[movement] = str(spec.get("origin", ""))
            beta_of[movement] = float(spec.get("beta", 0.0))
            cap_flow_of[movement] = float(_movement_capacity_flow(neutral_control, cfg, movement, spec))
    return LocalSignalModel(
        signal=signal,
        cfg=cfg,
        movements=movements,
        specs={m: dict(specs[m]) for m in movements},
        phase_of=phase_of,
        receiving_of=receiving_of,
        origin_of=origin_of,
        beta_of=beta_of,
        cap_flow_of=cap_flow_of,
        receiving_space_rule=str(cfg.urban_follower.receiving_space_rule),
    )


def _phase_arrival_to_movements(
    model: LocalSignalModel,
    arr_phase: Mapping[str, float],
) -> Dict[str, float]:
    """phase 단위 도착유량[veh/h]을 그 phase movement들에 β비율로 분배한다.

    `_coupling`의 `arr_{signal}_{pid}`는 phase 전체 도착(게이트 demand·β + 이웃 leaving·β +
    off-ramp·β의 합)이다. movement별 β로 나눠 각 큐에 주입한다(보존: Σ분배 = arr_phase)."""
    arr_movement: Dict[str, float] = {}
    for pid in ("p1", "p2"):
        beta_sum = sum(model.beta_of[m] for m in model.movements if model.phase_of[m] == pid)
        total = float(arr_phase.get(pid, 0.0))
        if beta_sum <= 1.0e-12 or total <= 0.0:
            for m in model.movements:
                if model.phase_of[m] == pid:
                    arr_movement[m] = 0.0
            continue
        for m in model.movements:
            if model.phase_of[m] == pid:
                arr_movement[m] = total * model.beta_of[m] / beta_sum
    return arr_movement


def rollout_local_tts(
    model: LocalSignalModel,
    q0: Mapping[str, float],
    arr_phase: Mapping[str, float],
    s_eff0: Mapping[str, float],
    green_p1: float,
    green_p2: float,
    substeps: int,
    dt_h: float,
) -> float:
    """신호 i의 movement 큐만 `substeps`회 전진시키고 누적 자기 차량수(자기 TTS proxy)를 반환.

    - q: 자기 movement 큐(국소 복사). arr_movement: 고정 도착(β분배).
    - s_eff: receiving 링크 가용공간. 자기 origin 링크(이 신호가 점유)는 전진 중 갱신,
      이웃/sink 링크는 s_eff0 고정값을 유지(이웃 downstream 동결).
    - 비용 = Σ_substep (Σ_m q_m) · dt  (제어변화 penalty는 호출처에서 더함).
    이게 검증 포인트 1: B·C·D·F·freeway는 절대 전진하지 않는다."""
    net = model.cfg.network
    cycle = max(net.cycle_length, 1.0e-9)
    green = {"p1": float(green_p1), "p2": float(green_p2)}
    q: Dict[str, float] = {m: max(0.0, float(q0.get(m, 0.0))) for m in model.movements}
    arr_movement = _phase_arrival_to_movements(model, arr_phase)
    # 자기 origin 링크(이 신호의 movement가 점유하는 링크) 집합 — 이 링크들만 전진 중 S_eff 갱신.
    own_origin_links = {model.origin_of[m] for m in model.movements if model.origin_of[m]}
    s_eff: Dict[str, float] = {link: max(0.0, float(v)) for link, v in s_eff0.items()}

    cost = 0.0
    for _ in range(substeps):
        # 1) 고정 도착 주입.
        for m in model.movements:
            q[m] += arr_movement.get(m, 0.0) * dt_h
        # 2) receiving 링크별로 intended service를 모으고 S_eff로 게이트(spillback 복제).
        intended_by_link: Dict[str, Dict[str, float]] = {}
        no_link_intended: Dict[str, float] = {}
        for m in model.movements:
            pid = model.phase_of[m]
            green_fraction = green[pid] / cycle
            intended = min(q[m], dt_h * green_fraction * model.cap_flow_of[m])
            if intended < 0.0:
                intended = 0.0
            recv = model.receiving_of[m]
            if recv and recv in s_eff:
                intended_by_link.setdefault(recv, {})[m] = intended
            else:
                no_link_intended[m] = intended
        actual: Dict[str, float] = dict(no_link_intended)
        for link, intended in intended_by_link.items():
            available_space = s_eff.get(link, 0.0)
            actual.update(_allocate_receiving_counts(
                model.receiving_space_rule,
                intended,
                available_space,
            ))
        # 3) 큐 차감 + 자기 내부 링크 S_eff 점유 갱신(이웃/sink 링크는 고정 유지).
        for m in model.movements:
            departed = min(q[m], max(0.0, actual.get(m, 0.0)))
            if departed <= 0.0:
                continue
            q[m] -= departed
            recv = model.receiving_of[m]
            if recv in own_origin_links and recv in s_eff:
                # 자기 신호의 다른 movement가 origin으로 쓰는 링크면 그 링크 점유가 늘어 S_eff↓.
                s_eff[recv] = max(0.0, s_eff[recv] - departed)
        # 4) 누적 비용 = Σ 자기 차량수 · dt (자기 TTS).
        cost += sum(q.values()) * dt_h
    return float(cost)
