# freeway agent가 소유한 seg(기본 1개, zone이면 구간)만 전진시키는 국소 plant — 이웃 seg는 동결 궤적(y)
"""13-player 재구축(plan-13player-rebuild.md)의 1단계 — segment agent의 국소동역학.

설계 원칙: METANET 수식을 복제하지 않는다. 기존 link-국소 stepper(`freeway_substep_local`)에
**이웃 segment 값은 동결 궤적(y)에서, 자기 segment 값은 자기 국소 상태에서** 채운 배열을
넘겨 호출하고, 자기 segment 결과만 취한다. 이러면

- link 전진과의 비트 일치가 구조적으로 보장되고(정합성 테스트가 이를 고정),
- 이웃은 substep당 상수 입력이므로 Wu §IV-D의 "결합변수 고정 + 자기 서브망만 전진"
  의미론이 정확히 성립한다(4-seg 산술을 전부 계산하지만 이웃 상태는 절대 갱신하지 않음 —
  비용 지배항은 후보 열거 × rollout이지 seg당 산술이 아니다).

y 스키마(FrozenLinkTrajectory) — agent 간 교환 대상:
- rhos/speeds/prev_lanes[t][j]: 이웃 segment 본선 상태 (f↔f 경계: METANET 상류 유입·속도,
  하류 receiving·anticipation 밀도가 전부 이 셋에서 유도됨)
- ramp_release[t][ramp]: 이웃 agent 소유 on-ramp의 방류(F_L2↔F_L3 예산 합의 결합변수 겸용)
- occupancy[t][off_ramp]: off-ramp storage 점유 — **urban D/F agent 소유 상태**(f→u 유출과
  u 신호 drain으로 urban이 갱신), freeway는 λ_eff(capacity drop) 입력으로만 읽음
- offramp_capacity[t][off_ramp]: urban receiving link 가용공간이 주는 유출 상한(u→f supply)
- origin_queue[t]: seg0 소유 상태의 동결값(비-seg0 agent의 배열 조립용; 자기 출력엔 무영향)

horizon을 넘어가는 t는 마지막 값 유지(hold-last).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

from src.controllers.local_freeway_plant import (
    LocalFreewayModel,
    build_local_freeway_model,
    freeway_substep_local,
)
from src.models.state import ControlAction, ExperimentConfig


@dataclass
class SegmentAgentModel:
    """segment agent 1개의 정적 데이터 — 소유 lever와 link-모델 참조(컨트롤러가 1회 구성).

    ZONE-4(2026-08-01): `segs`가 소유 세그먼트 집합(오름차순·연속)이다. 기본 구성은
    zone당 1 세그먼트라 `segs=[i]`이고, 이때 `seg` property가 기존 단일-세그먼트 계약을
    그대로 만족한다(하위 호환).
    """

    link: str
    segs: List[int]
    link_model: LocalFreewayModel
    # 이 zone에 merge하는 on-ramp(소유 lever). 13-player 매핑: seg2=R_D, seg3=R_F.
    owned_ramps: List[str]
    # 이 zone에서 갈라지는 off-ramp — 유출(q_out) 계산 담당은 이 agent, storage 상태는 urban 소유.
    boundary_offramps: List[str]
    # seg0을 포함하는 zone만 mainline origin queue를 소유 상태로 가진다.
    owns_origin_queue: bool = False
    # 진단·리포트용 zone 이름. 기본 구성(세그먼트당 1 에이전트)에서는 빈 문자열이다.
    zone_id: str = ""
    # 이 link에 freeway_agent_groups가 실제로 적용됐는가. 빌더가 명시적으로 채운다 —
    # 솔버는 이 플래그로 zone 경로를 판정한다(len(segs)>1 휴리스틱 금지: 전부 단일
    # 세그먼트인 zone 지정에서 영수증·안전망이 꺼지는 false-negative가 생긴다).
    zone_mode: bool = False

    @property
    def seg(self) -> int:
        """대표(최상류) 세그먼트 — 단일 세그먼트 구성에서는 소유 세그먼트 그 자체."""
        return self.segs[0]


def _as_segment_index(value, where: str) -> int:
    """세그먼트 인덱스를 정수로 변환 — 절삭 금지(3.7 → 3은 조용한 오배정).

    int(3.7)==3처럼 float을 잘라내면 오타가 '다른 zone'으로 조용히 흡수된다. 정수성을
    먼저 검사하고, 아니면 RuntimeError.
    """
    if isinstance(value, bool):
        raise RuntimeError(f"{where}의 세그먼트 인덱스가 bool이다: {value!r}")
    if isinstance(value, int):
        return int(value)
    try:
        fval = float(value)
    except (TypeError, ValueError):
        raise RuntimeError(f"{where}의 세그먼트 인덱스가 수치가 아니다: {value!r}") from None
    if fval != int(fval):
        raise RuntimeError(
            f"{where}의 세그먼트 인덱스가 정수가 아니다: {value!r} "
            "(절삭하면 오타가 조용히 다른 zone으로 흡수된다)"
        )
    return int(fval)


def _normalize_zone_groups(
    raw, link: str, n_seg: int, valid_links=None,
) -> Optional[List[Tuple[str, List[int]]]]:
    """cfg.mpc.freeway_agent_groups에서 link의 zone 분할을 뽑아 검증한다.

    반환 None = 이 link에는 zone 지정이 없음(세그먼트당 1 에이전트). 검증 실패는 조용히
    무시하지 않고 RuntimeError로 즉사시킨다 — 침묵 무효화(BUDGET_OFF 20런 사고)의 재발
    패턴이 정확히 "전용 키가 다른 경로에 꽂혀 조용히 무시됨"이다.

    valid_links를 주면 raw의 **모든** 키가 실재 freeway link인지 검사한다. 오타 하나로
    zone 런 전체가 flagship으로 퇴화하는 침묵 무효화를 막는다. 링크 부분 지정
    (예: FW_E만 zone화)은 계속 허용 — 미지정 링크는 세그먼트당 1 에이전트로 남는다.
    """
    if not raw:
        return None
    if not isinstance(raw, Mapping):
        raise RuntimeError(
            f"freeway_agent_groups는 {{link: [[seg,...], ...]}} 매핑이어야 한다: {type(raw)!r}"
        )
    if valid_links is not None:
        unknown = sorted(set(map(str, raw)) - set(map(str, valid_links)))
        if unknown:
            raise RuntimeError(
                f"freeway_agent_groups에 알 수 없는 링크 키가 있다: {unknown} "
                f"(유효 링크: {sorted(map(str, valid_links))}). 오타면 zone 지정이 통째로 "
                "무시돼 기본 경로로 조용히 퇴화한다."
            )
    spec = raw.get(link)
    if spec is None:
        return None
    if not isinstance(spec, (list, tuple)) or not spec:
        raise RuntimeError(
            f"freeway_agent_groups[{link}]는 비어 있지 않은 zone 리스트여야 한다: {spec!r}"
        )
    zones: List[Tuple[str, List[int]]] = []
    for idx, item in enumerate(spec):
        if isinstance(item, Mapping):
            segs_raw = item.get("segments")
            zone_id = str(item.get("id", "") or f"{link}__z{idx}")
        else:
            segs_raw = item
            zone_id = f"{link}__z{idx}"
        if not isinstance(segs_raw, (list, tuple)) or not segs_raw:
            raise RuntimeError(
                f"freeway_agent_groups[{link}][{idx}]의 segments가 비었거나 리스트가 아니다: {segs_raw!r}"
            )
        segs = [
            _as_segment_index(s, f"freeway_agent_groups[{link}][{idx}]") for s in segs_raw
        ]
        for s in segs:
            if not (0 <= s < n_seg):
                raise RuntimeError(
                    f"freeway_agent_groups[{link}][{idx}] 세그먼트 {s}가 범위 [0,{n_seg}) 밖이다."
                )
        if segs != sorted(segs):
            raise RuntimeError(
                f"freeway_agent_groups[{link}][{idx}]의 세그먼트는 오름차순이어야 한다: {segs}"
            )
        if len(set(segs)) != len(segs):
            raise RuntimeError(
                f"freeway_agent_groups[{link}][{idx}]에 중복 세그먼트가 있다: {segs}"
            )
        if segs[-1] - segs[0] + 1 != len(segs):
            raise RuntimeError(
                f"freeway_agent_groups[{link}][{idx}]의 세그먼트가 불연속이다: {segs} "
                "(zone은 연속 구간이어야 이웃 정의·궤적 교환이 성립한다)"
            )
        zones.append((zone_id, segs))
    # zone_id는 link 안에서 유일해야 한다 — 겹치면 진단 키(wu_zone_*_{link}_{zid})가
    # 서로를 덮어써 영수증이 조용히 하나로 합쳐진다.
    _ids = [z[0] for z in zones]
    if len(set(_ids)) != len(_ids):
        _dup = sorted({i for i in _ids if _ids.count(i) > 1})
        raise RuntimeError(
            f"freeway_agent_groups[{link}]에 중복 zone_id가 있다: {_dup} "
            "(진단 키가 서로를 덮어쓴다)"
        )
    if [z[1][0] for z in zones] != sorted(z[1][0] for z in zones):
        raise RuntimeError(
            f"freeway_agent_groups[{link}]의 zone 순서는 최상류 세그먼트 오름차순이어야 한다: "
            f"{[z[1] for z in zones]}"
        )
    covered = [s for _, segs in zones for s in segs]
    if sorted(covered) != list(range(n_seg)):
        raise RuntimeError(
            f"freeway_agent_groups[{link}]가 세그먼트 0~{n_seg - 1}를 빠짐없이·중복없이 "
            f"덮지 않는다: {[z[1] for z in zones]}"
        )
    return zones


def build_segment_agent_models(
    cfg: ExperimentConfig, link: str, groups=None,
) -> List[SegmentAgentModel]:
    """link 하나를 segment agent들로 분할 — 13-player 매핑(승인 2026-07-10).

    groups=None이면 `cfg.mpc.freeway_agent_groups`를 읽는다(cfg가 단일 진실원천). 거기에도
    이 link 항목이 없으면 세그먼트당 1 에이전트 = 기존 거동 비트 동일.

    반환 에이전트의 `zone_mode`가 "이 link에 groups가 적용됐는가"의 단일 진실원천이다.
    """
    link_model = build_local_freeway_model(cfg, link)
    if groups is None:
        groups = getattr(cfg.mpc, "freeway_agent_groups", None)
    zones = _normalize_zone_groups(
        groups, link, link_model.n_seg, getattr(cfg.network, "freeway_links", None),
    )
    zone_mode = zones is not None
    if zones is None:
        zones = [("", [seg]) for seg in range(link_model.n_seg)]
    agents: List[SegmentAgentModel] = []
    for zone_id, segs in zones:
        seg_set = set(segs)
        owned = [
            r for r in link_model.owned_ramps if link_model.ramp_merge_idx[r] in seg_set
        ]
        offramps: List[str] = []
        for seg in segs:
            offramps.extend(link_model.offramps_by_segment.get(seg, []))
        agents.append(
            SegmentAgentModel(
                link=link,
                segs=list(segs),
                link_model=link_model,
                owned_ramps=owned,
                boundary_offramps=offramps,
                owns_origin_queue=(0 in seg_set),
                zone_id=zone_id,
                zone_mode=zone_mode,
            )
        )
    return agents


@dataclass
class FrozenLinkTrajectory:
    # Phase B: 완충 plant 동결 경계 (bu_send, bu_speed, bd_rho0) — None이면 무완충.
    buffer_bc = None
    """이웃 agent들이 내놓은 link 전체 궤적의 동결 스냅샷 — substep t 인덱스, hold-last."""

    rhos: List[List[float]]
    speeds: List[List[float]]
    prev_lanes: List[List[float]]
    origin_queue: List[float]
    ramp_release: List[Dict[str, float]]
    occupancy: List[Dict[str, float]]
    offramp_capacity: List[Dict[str, float]] = field(default_factory=list)

    def _idx(self, t: int) -> int:
        n = len(self.rhos)
        return min(max(t, 0), n - 1)

    def at(self, t: int) -> Tuple[
        List[float], List[float], List[float], float,
        Dict[str, float], Dict[str, float], Dict[str, float],
    ]:
        k = self._idx(t)
        cap = self.offramp_capacity[k] if self.offramp_capacity else {}
        return (
            list(self.rhos[k]),
            list(self.speeds[k]),
            list(self.prev_lanes[k]),
            float(self.origin_queue[k]),
            dict(self.ramp_release[k]),
            dict(self.occupancy[k]),
            dict(cap),
        )


@dataclass
class SegmentLocalState:
    """segment agent가 rollout 동안 스스로 갱신하는 자기 상태."""

    rho: float
    speed: float
    prev_lane: float
    origin_queue: float = 0.0  # seg0만 의미


def segment_zone_substep_local(
    agent: SegmentAgentModel,
    frozen: FrozenLinkTrajectory,
    t: int,
    own: Mapping[int, SegmentLocalState],
    own_ramp_release: Mapping[str, float],
    control: ControlAction,
    demand,
    extra_overrides: Optional[Mapping[int, SegmentLocalState]] = None,
) -> Tuple[Dict[int, SegmentLocalState], Dict[str, float], Dict[int, float]]:
    """zone agent 1 substep 전진 — 반환 (다음 자기 상태들, zone off-ramp 유출, 세그먼트별 차량수).

    이웃 배열은 frozen.at(t)로 채우고 **own에 담긴 세그먼트 항목만** 덮어쓴 뒤
    `freeway_substep_local`을 호출, own 인덱스 결과만 취한다. zone 내부는 동결이 아니라
    동시 전진이며, 이는 이미 extra_overrides(radius-1)가 쓰는 메커니즘과 동일하다.
    len(own)==1이면 넘기는 배열이 단일 세그먼트 경로와 완전히 같아 비트 동일하다.

    extra_overrides: radius-국소 rollout용 — frozen 대신 함께 전진 중인 이웃 seg의
    현재 상태를 주입(PFO 강화 변형; 기본 None이면 순수 동결-이웃).
    """
    rhos, speeds, prev_lanes, origin_q, releases, occupancy, cap = frozen.at(t)
    own_segs = {int(s) for s in own}
    for s, st in own.items():
        rhos[int(s)] = float(st.rho)
        speeds[int(s)] = float(st.speed)
        prev_lanes[int(s)] = float(st.prev_lane)
    if extra_overrides:
        for j, st in extra_overrides.items():
            if 0 <= int(j) < len(rhos) and int(j) not in own_segs:
                rhos[int(j)] = float(st.rho)
                speeds[int(j)] = float(st.speed)
                prev_lanes[int(j)] = float(st.prev_lane)
    # origin queue는 zone이 seg0을 소유할 때 seg0 상태에만 실린다(스칼라 — 이중계상 금지).
    if agent.owns_origin_queue and 0 in own_segs:
        origin_q = float(own[0].origin_queue)
    for ramp in agent.owned_ramps:
        releases[ramp] = max(0.0, float(own_ramp_release.get(ramp, 0.0)))

    next_rhos, next_speeds, next_lanes, next_origin_q, offramp_flow, vehicle_count = (
        freeway_substep_local(
            agent.link_model,
            rhos,
            speeds,
            prev_lanes,
            occupancy,
            origin_q,
            releases,
            cap,
            control,
            demand,
            buffer_bc=getattr(frozen, "buffer_bc", None),
        )
    )
    next_states = {
        int(s): SegmentLocalState(
            rho=float(next_rhos[int(s)]),
            speed=float(next_speeds[int(s)]),
            prev_lane=float(next_lanes[int(s)]),
            origin_queue=(
                float(next_origin_q) if (agent.owns_origin_queue and int(s) == 0) else 0.0
            ),
        )
        for s in own
    }
    own_offramp_flow = {
        o: float(offramp_flow.get(o, 0.0)) for o in agent.boundary_offramps
    }
    own_veh = {int(s): float(vehicle_count[int(s)]) for s in own}
    return next_states, own_offramp_flow, own_veh


def segment_substep_local(
    agent: SegmentAgentModel,
    frozen: FrozenLinkTrajectory,
    t: int,
    own: SegmentLocalState,
    own_ramp_release: Mapping[str, float],
    control: ControlAction,
    demand,
    extra_overrides: Optional[Mapping[int, SegmentLocalState]] = None,
) -> Tuple[SegmentLocalState, Dict[str, float], float]:
    """단일 세그먼트 전진 — `segment_zone_substep_local`의 대표 세그먼트 래퍼(하위 호환)."""
    seg = agent.seg
    states, off_flow, vehs = segment_zone_substep_local(
        agent, frozen, t, {seg: own}, own_ramp_release, control, demand,
        extra_overrides=extra_overrides,
    )
    return states[seg], off_flow, vehs[seg]


def frozen_trajectory_from_state(
    cfg: ExperimentConfig,
    link: str,
    state,
    control: ControlAction,
    horizon_substeps: int,
) -> FrozenLinkTrajectory:
    """합의 첫 iteration용 warm-start — 현재 실측 상태를 hold-constant로 편 궤적.

    이후 iteration은 각 agent가 직전 rollout에서 내놓은 궤적으로 교체한다(합의 루프 담당).
    ramp_release는 직전 control의 metering을 유지, occupancy는 현 storage 점유를 유지.
    """
    net = cfg.network
    n_seg = net.freeway_segments_per_link
    rhos0 = [float(v) for v in state.freeway_density.get(link, [0.0] * n_seg)]
    speeds0 = [float(v) for v in state.freeway_speed.get(link, [net.v_free] * n_seg)]
    lanes0 = [float(v) for v in state.freeway_effective_lanes.get(link, [])] or [
        float(net.freeway_lanes) for _ in range(n_seg)
    ]
    if len(lanes0) != n_seg:
        lanes0 = [float(net.freeway_lanes) for _ in range(n_seg)]
    origin0 = max(0.0, float(state.mainline_origin_queue.get(link, 0.0)))
    release0: Dict[str, float] = {}
    for ramp in net.ramps:
        if net.ramp_to_freeway.get(ramp) == link:
            release0[ramp] = max(0.0, float(control.ramp_metering.get(ramp, 0.0)))
    occ0: Dict[str, float] = {}
    for off_ramp in net.off_ramps:
        if net.off_ramp_from_freeway.get(off_ramp) != link:
            continue
        storage = net.off_ramp_storage_link.get(off_ramp, "")
        cap = float(net.urban_link_storage_veh.get(storage, 0.0))
        avail = float(state.urban_link_storage.get(storage, cap))
        occ0[off_ramp] = max(0.0, cap - avail)
    steps = max(1, int(horizon_substeps))
    traj = FrozenLinkTrajectory(
        rhos=[list(rhos0) for _ in range(steps)],
        speeds=[list(speeds0) for _ in range(steps)],
        prev_lanes=[list(lanes0) for _ in range(steps)],
        origin_queue=[origin0 for _ in range(steps)],
        ramp_release=[dict(release0) for _ in range(steps)],
        occupancy=[dict(occ0) for _ in range(steps)],
        offramp_capacity=[{} for _ in range(steps)],
    )
    # Phase B(완충 동결 결합): 완충 plant면 결정시점 완충 경계를 동결해 첨부.
    if int(getattr(net, "freeway_buffer_segments", 0)) > 0:
        _bu_r = state.freeway_buffer_up_density.get(link) or []
        _bu_v = state.freeway_buffer_up_speed.get(link) or []
        _bd_r = state.freeway_buffer_down_density.get(link) or []
        if _bu_r and _bd_r:
            from src.models.metanet import segment_flow_veh_h as _sfvh
            _bu_send = _sfvh(_bu_r[-1], _bu_v[-1], float(net.freeway_lanes))
            _phi_bc = float(getattr(net, "capacity_drop_discharge_phi", 1.0) or 1.0)
            if _phi_bc < 1.0 and _bu_r[-1] > float(net.rho_crit):
                # plant capacity drop과 동일 cap(동결 BC 정합).
                _bu_send = min(_bu_send, _phi_bc * float(net.freeway_capacity_veh_h))
            traj.buffer_bc = (
                _bu_send,
                float(_bu_v[-1]),
                float(_bd_r[0]),
            )
    return traj
