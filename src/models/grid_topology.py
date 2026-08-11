# 그리드 leg 인접 그래프에서 directed link·movement(o,s,d)·turning ratio β를 자동 유도하는 모듈 (docs/grid_routing_proposal.md)
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

# leg 방위와 정반대(직진) 매핑 — proposal §4: 직진 = 들어온 approach의 정반대 leg.
#
# 8방위 확장(2026-08-04). 실제 도로망은 격자가 아니다 — 개포동 36개 교차로의 인접관계를
# 네트워크에서 유도하면(scripts/derive_intersection_adjacency.py) 방향성 인접쌍 116개 중
# **21쌍이 4방위로는 표현 불가**였다(같은 방위에 이웃 2개 이상). 대각 연결·5지 교차로 때문이다.
# 4방위로 강행하면 그 21쌍을 버려야 하고, 어느 것을 버릴지가 순서 의존이라 재현성도 없다.
#
# 8방위를 축으로 묶는 규칙은 **축 방위각**이다.
#   축 각도(mod 180): N-S 90°, NE-SW 45°, E-W 0°, NW-SE 135°
#   [45°, 135°) 구간 = 세로축에 가까움 -> major,  나머지 = 가로축에 가까움 -> minor
#
# 2026-08-12 4현시 전환. 축만으로는 현시가 정해지지 않는다 — 현시는 (축, 회전)의 조합이다.
#   p1 major 직진(+우)   p2 major 좌   p3 minor 직진(+우)   p4 minor 좌
# 우회전은 같은 접근로의 직진 현시에 붙인다(NEMA 관행, 실 `.sig` 136 SG 에 우회전 SG 없음).
#
# LEG_DIRECTIONS 는 **시계방향** 이다. 이 순서가 회전 분류의 근거다(movement_turn 참조).
LEG_DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
_LEG_INDEX = {leg: i for i, leg in enumerate(LEG_DIRECTIONS)}
OPPOSITE_LEG = {
    "N": "S", "S": "N", "E": "W", "W": "E",
    "NE": "SW", "SW": "NE", "NW": "SE", "SE": "NW",
}
# 대각 leg 를 어느 phase 축에 넣을지 — 실측 방위각으로 정한다.
#
# 2026-08-05 정정. 처음엔 {"N","S","NE","SW"} 였다. "축각 mod 180 이 [45,135) 면 남북축"
# 이라는 기준 자체는 맞지만, NE/SW 를 45° 로 가정한 것이 틀렸다. 개포동 격자가 좌표축에서
# 15~37° 돌아가 있어 실측 축각은 NE 36.1° / SW 37.2°(동서축에 가깝다), NW 122.2° /
# SE 121.6°(남북축에 가깝다) 다. 정확히 45/135° 인 leg 는 하나도 없고, 45° 동률처럼 보인
# 것은 derive_intersection_adjacency 의 22.5° 이산화 산물이다. 코드 자신의 기준을 실제
# 방위각에 적용하면 현행 배정은 대각 leg 76개 중 **0개**가 맞고 뒤집은 배정이 76개 맞는다.
# 4방위 격자에는 대각 leg 가 없으므로 이 정정으로 기존 회귀는 비트 동일하다.
#
# 2026-08-12 4현시 전환 후에도 이 집합은 남는다. 다만 역할이 "phase 그 자체"에서
# "**major 축 leg 집합**"으로 좁아졌다 — 현시는 여기에 회전(직진/좌)을 곱해야 나온다.
NS_AXIS = {"N", "S", "NW", "SE"}
MAJOR_AXIS_LEGS = NS_AXIS

# 램프 leg(D·F의 S)는 4갈래: 나가는 on_ramp 2(W/E) + 들어오는 off_ramp 2(W/E) — proposal §1.
RAMP_SIDES = ("W", "E")


def default_grid_node_legs() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """proposal §1 leg 표를 그대로 코드화한 기본 토폴로지.

    leg spec 종류:
      {"type": "grid", "node": X}                      — 내부 도로(양방향 directed 2개)
      {"type": "boundary", "in": .., "out": .., "out_link": ..} — 경계 게이트(in/out 링크)
      {"type": "ramp", "on": {side: ramp}, "off": {side: off_ramp}} — D·F 램프 leg
    """
    return {
        "A": {
            "N": {"type": "boundary", "in": "in_A_top", "out": "out_A_top", "out_link": "A_top_out"},
            "S": {"type": "grid", "node": "D"},
            "E": {"type": "grid", "node": "B"},
            "W": {"type": "boundary", "in": "in_A_left", "out": "out_A_left", "out_link": "A_left_out"},
        },
        "B": {
            "N": {"type": "boundary", "in": "in_B_top", "out": "out_B_top", "out_link": "B_top_out"},
            "S": {"type": "grid", "node": "E"},
            "E": {"type": "grid", "node": "C"},
            "W": {"type": "grid", "node": "A"},
        },
        "C": {
            "N": {"type": "boundary", "in": "in_C_top", "out": "out_C_top", "out_link": "C_top_out"},
            "S": {"type": "grid", "node": "F"},
            "E": {"type": "boundary", "in": "in_C_right", "out": "out_C_right", "out_link": "C_right_out"},
            "W": {"type": "grid", "node": "B"},
        },
        "D": {
            "N": {"type": "grid", "node": "A"},
            "S": {"type": "ramp", "on": {"W": "R_D_W", "E": "R_D_E"}, "off": {"W": "OR_D_W", "E": "OR_D_E"}},
            "E": {"type": "grid", "node": "E"},
            "W": {"type": "boundary", "in": "in_D_left", "out": "out_D_left", "out_link": "D_left_out"},
        },
        "E": {
            "N": {"type": "grid", "node": "B"},
            "E": {"type": "grid", "node": "F"},
            "W": {"type": "grid", "node": "D"},
        },
        "F": {
            "N": {"type": "grid", "node": "C"},
            "S": {"type": "ramp", "on": {"W": "R_F_W", "E": "R_F_E"}, "off": {"W": "OR_F_W", "E": "OR_F_E"}},
            "E": {"type": "boundary", "in": "in_F_right", "out": "out_F_right", "out_link": "F_right_out"},
            "W": {"type": "grid", "node": "E"},
        },
    }


def internal_link_name(from_node: str, to_node: str) -> str:
    return f"{from_node}_to_{to_node}"


def internal_links(grid_node_legs: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> List[str]:
    """leg 인접에서 내부 directed link(7도로 × 2방향 = 14개) 이름을 유도한다."""
    links: List[str] = []
    for node, legs in grid_node_legs.items():
        for leg in legs.values():
            if leg.get("type") == "grid":
                links.append(internal_link_name(node, str(leg["node"])))
    return sorted(links)


def _approach_tokens(legs: Mapping[str, Mapping[str, Any]]) -> List[Tuple[str, str]]:
    """노드의 incoming approach (token, leg방위) 목록. 램프 leg는 off_ramp 2개가 별도 incoming."""
    out: List[Tuple[str, str]] = []
    for direction, leg in legs.items():
        kind = leg.get("type")
        if kind in {"grid", "boundary"}:
            out.append((direction, direction))
        elif kind == "ramp":
            for side in RAMP_SIDES:
                if side in leg.get("off", {}):
                    out.append((f"off{side}", direction))
    return out


def _outgoing_leg_dirs(legs: Mapping[str, Mapping[str, Any]]) -> List[str]:
    """나가는 leg 방위 목록(램프 leg는 on_ramp가 있으면 한 leg로 취급)."""
    out: List[str] = []
    for direction, leg in legs.items():
        kind = leg.get("type")
        if kind in {"grid", "boundary"}:
            out.append(direction)
        elif kind == "ramp" and leg.get("on"):
            out.append(direction)
    return out


def derive_turning_ratios(
    grid_node_legs: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """직진우대 β 자동 유도 — proposal §4.

    - 직진(들어온 leg의 정반대 방위)이 있으면 β(직진 leg)=0.5, 나머지 leg 균등.
    - 직진 leg가 없으면(E의 N approach) 가용 leg 균등. U-turn(같은 leg) 제외, Σ_d β=1.
    - 램프 leg가 받는 몫은 on_ramp W/E에 균등 분할(각 절반) — d token: onW/onE.
    """
    ratios: Dict[str, Dict[str, Dict[str, float]]] = {}
    for node, legs in grid_node_legs.items():
        node_ratios: Dict[str, Dict[str, float]] = {}
        outgoing_dirs = _outgoing_leg_dirs(legs)
        for token, leg_dir in _approach_tokens(legs):
            available = [d for d in outgoing_dirs if d != leg_dir]
            if not available:
                continue
            # 직진 = 들어온 approach 의 정반대 **방위**. 복합 키에서는 그 방위를 가진 leg 가
            # 여럿일 수 있으므로 후보를 모아 균등 분배한다(단일 후보면 구 동작과 비트 동일).
            straight_dir = OPPOSITE_LEG.get(leg_base_dir(leg_dir), "")
            straight_keys = [d for d in available if leg_base_dir(d) == straight_dir] if straight_dir else []
            leg_share: Dict[str, float] = {}
            if straight_keys:
                others = [d for d in available if d not in straight_keys]
                total_straight = 0.5 if others else 1.0
                for s in straight_keys:
                    leg_share[s] = total_straight / len(straight_keys)
                for d in others:
                    leg_share[d] = 0.5 / len(others)
            else:
                for d in available:
                    leg_share[d] = 1.0 / len(available)
            beta: Dict[str, float] = {}
            for d, share in leg_share.items():
                leg = legs[d]
                if leg.get("type") == "ramp":
                    on_sides = [side for side in RAMP_SIDES if side in leg.get("on", {})]
                    for side in on_sides:
                        beta[f"on{side}"] = share / len(on_sides)
                else:
                    beta[d] = share
            node_ratios[token] = beta
        ratios[node] = node_ratios
    return ratios


def _token_leg_dir(token: str, legs: Optional[Mapping[str, Mapping[str, Any]]] = None) -> str:
    """approach/exit token의 leg **키**.

    반환값은 grid_node_legs 의 키로 그대로 쓰인다(legs[_token_leg_dir(t, legs)]).
    복합 키('N_SC1002')를 쓰는 경우 축 방위는 leg_base_dir 로 따로 뽑는다.

    off*/on* 은 램프 leg 다. 예전에는 램프 leg 가 항상 "S" 에 있다고 가정해 상수를 돌려줬는데,
    실제 도로망에서 유도한 토폴로지는 S 가 이미 인접 도로에 쓰여 램프를 다른 방위에 심어야
    하는 노드가 생긴다(2026-08-04 SC1001/SC1004). legs 를 주면 실제 램프 leg 키를 찾는다.
    """
    if token.startswith("off") or token.startswith("on"):
        if legs:
            for key, leg in legs.items():
                if leg.get("type") == "ramp":
                    return key
        return "S"
    return token


def leg_base_dir(leg_key: str) -> str:
    """leg 키에서 **방위 접두사**를 뽑는다 — 'N' -> 'N', 'N_SC1002' -> 'N'.

    실제 도로망은 격자가 아니라 한 방위에 이웃이 둘 이상 붙는다(개포동 36교차로에서
    인접쌍 116개 중 8방위로도 13쌍이 같은 방위에 겹쳤고, 그 10쌍이 인터체인지 클러스터였다).
    leg 키를 '방위_이웃ID' 로 두면 이웃을 하나도 버리지 않으면서 방위는 접두사로 복원된다.
    접두사가 알려진 방위가 아니면 키 전체를 방위로 본다(구 4방위 키와 비트 동일).
    """
    head = str(leg_key).split("_", 1)[0]
    return head if head in OPPOSITE_LEG else str(leg_key)


def movement_turn(approach_leg_key: str, exit_leg_key: str) -> str:
    """movement 의 회전 종류 — "through" | "left" | "right" | "u_turn" | "unknown".

    approach leg d 로 **들어온** 차량의 진행 방위는 정반대 leg 다(OPPOSITE_LEG). 거기서
    exit leg 까지의 시계방향 각 차이로 회전을 가른다. LEG_DIRECTIONS 가 시계방향이므로
    인덱스 증가 = 우회전 쪽이다(우측통행).

        delta = (exit_idx - heading_idx) mod 8
        0 -> 직진 · 1~3 -> 우 · 4 -> U턴 · 5~7 -> 좌

    검산: N 에서 들어오면 진행은 S(idx 4). 좌회전 출구는 E(idx 2), delta=6 -> left.
    우회전 출구는 W(idx 6), delta=2 -> right. 직진 출구는 S, delta=0 -> through.

    방위를 모르는 leg 키(격자 밖 토큰)는 "unknown" 이고 호출측이 직진과 같이 다룬다.
    """
    approach = leg_base_dir(approach_leg_key)
    exit_dir = leg_base_dir(exit_leg_key)
    if approach not in _LEG_INDEX or exit_dir not in _LEG_INDEX:
        return "unknown"
    heading = _LEG_INDEX[OPPOSITE_LEG[approach]]
    delta = (_LEG_INDEX[exit_dir] - heading) % len(LEG_DIRECTIONS)
    if delta == 0:
        return "through"
    if delta == 4:
        return "u_turn"
    return "right" if delta < 4 else "left"


def movement_phase_id(approach_leg_key: str, exit_leg_key: str) -> str:
    """(축, 회전) -> 현시 id. src.models.state.MODEL_PHASES 와 순서가 같다.

    major 직진 p1 · major 좌 p2 · minor 직진 p3 · minor 좌 p4.
    우회전·미상 회전은 같은 축의 직진 현시에 붙인다.
    """
    major = leg_base_dir(approach_leg_key) in MAJOR_AXIS_LEGS
    left = movement_turn(approach_leg_key, exit_leg_key) == "left"
    if major:
        return "p2" if left else "p1"
    return "p4" if left else "p3"


def build_urban_movements(
    grid_node_legs: Mapping[str, Mapping[str, Mapping[str, Any]]],
    turning_ratios: Mapping[str, Mapping[str, Mapping[str, float]]],
    signals: List[str],
    ramp_to_freeway: Mapping[str, str],
) -> Dict[str, Dict[str, Any]]:
    """movement (o,s,d)를 토폴로지+β에서 자동 생성한다 — proposal §3.

    - phase = (incoming approach 축) x (회전) 4현시 — movement_phase_id (램프 movement 포함).
    - E(비통제)는 phase=""(green=1 상당)로 신호 없이 통과.
    - kind 우선순위: origin이 경계 게이트 → boundary_in, origin이 off_ramp → off_ramp,
      exit이 on_ramp → on_ramp, exit이 경계 → boundary_out, 그 외 internal.
    """
    signal_set = set(signals)
    movements: Dict[str, Dict[str, Any]] = {}
    for node, legs in grid_node_legs.items():
        node_ratios = turning_ratios.get(node, {})
        for token, leg_dir in _approach_tokens(legs):
            beta_map = node_ratios.get(token, {})
            approach_leg = legs[leg_dir]
            for exit_token, beta in beta_map.items():
                exit_leg_dir = _token_leg_dir(exit_token, legs)
                exit_leg = legs[exit_leg_dir]
                spec: Dict[str, Any] = {
                    "intersection": node,
                    "approach": token,
                    "exit": exit_token,
                    "beta": float(beta),
                    "signal": node,
                }
                # phase: (approach 축) x (회전) 으로 결정하는 4현시. E는 비통제.
                if node in signal_set:
                    approach_leg_key = _token_leg_dir(token, legs)
                    spec["turn"] = movement_turn(approach_leg_key, exit_leg_dir)
                    spec["phase"] = f"{node}_{movement_phase_id(approach_leg_key, exit_leg_dir)}"
                else:
                    spec["turn"] = movement_turn(_token_leg_dir(token, legs), exit_leg_dir)
                    spec["phase"] = ""
                # origin(legacy): 게이트 in링크 / off_ramp 이름 / 내부 incoming link.
                if approach_leg.get("type") == "boundary":
                    spec["origin"] = str(approach_leg["in"])
                elif approach_leg.get("type") == "ramp":
                    side = token[len("off"):]
                    spec["origin"] = str(approach_leg["off"][side])
                    spec["off_ramp"] = str(approach_leg["off"][side])
                else:
                    spec["origin"] = internal_link_name(str(approach_leg["node"]), node)
                # destination/receiving_link: exit leg 타입별.
                if exit_leg.get("type") == "grid":
                    receiving = internal_link_name(node, str(exit_leg["node"]))
                    spec["destination"] = receiving
                    spec["receiving_link"] = receiving
                elif exit_leg.get("type") == "boundary":
                    spec["destination"] = str(exit_leg["out"])
                    spec["receiving_link"] = str(exit_leg["out_link"])
                else:  # ramp exit (onW/onE)
                    side = exit_token[len("on"):]
                    ramp = str(exit_leg["on"][side])
                    spec["ramp"] = ramp
                    spec["destination"] = str(ramp_to_freeway.get(ramp, ramp))
                    spec["receiving_link"] = f"{node}_R_{side}"
                # kind 분류(우선순위: origin 경계 > origin off_ramp > exit ramp > exit 경계 > internal).
                if approach_leg.get("type") == "boundary":
                    spec["kind"] = "boundary_in"
                elif approach_leg.get("type") == "ramp":
                    spec["kind"] = "off_ramp"
                elif exit_leg.get("type") == "ramp":
                    spec["kind"] = "on_ramp"
                elif exit_leg.get("type") == "boundary":
                    spec["kind"] = "boundary_out"
                else:
                    spec["kind"] = "internal"
                movements[f"{node}_{token}_to_{exit_token}"] = spec
    return movements


def approach_sources(
    grid_node_legs: Mapping[str, Mapping[str, Mapping[str, Any]]],
    off_ramp_storage_link: Mapping[str, str],
) -> Dict[str, Tuple[str, str]]:
    """arrival buffer key(=approach source link) → (교차로, approach token) 매핑.

    내부 링크 X_to_Y는 Y에 leg방위로 도착, off-ramp storage 링크는 offW/offE로 도착.
    게이트 수요는 in링크 이름으로 주입된다.
    """
    out: Dict[str, Tuple[str, str]] = {}
    for node, legs in grid_node_legs.items():
        for direction, leg in legs.items():
            kind = leg.get("type")
            if kind == "grid":
                out[internal_link_name(str(leg["node"]), node)] = (node, direction)
            elif kind == "boundary":
                out[str(leg["in"])] = (node, direction)
            elif kind == "ramp":
                for side, off_ramp in leg.get("off", {}).items():
                    storage = off_ramp_storage_link.get(str(off_ramp), f"{off_ramp}_storage")
                    out[storage] = (node, f"off{side}")
    return out
