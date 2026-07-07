from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .demand import DemandStep
from .state import ControlAction, ExperimentConfig, TrafficState, segment_vsl


def segment_flow_veh_h(rho_veh_km_lane: float, speed_km_h: float, lanes: float) -> float:
    """METANET segment flow q = rho * v * lanes in veh/h."""
    return float(max(rho_veh_km_lane, 0.0) * max(speed_km_h, 0.0) * max(lanes, 0.0))


def desired_speed_kmh(rho: float, v_free: float, rho_crit: float, a: float = 1.867) -> float:
    ratio = max(rho, 0.0) / max(rho_crit, 1.0e-9)
    return float(v_free * math.exp(-(1.0 / a) * (ratio ** a)))


def two_branch_vsl_speed_kmh(
    rho: float,
    v_free: float,
    rho_crit: float,
    rho_jam: float,
    vsl: float,
) -> float:
    """VSL이 임계밀도를 옮기는 two-branch(삼각형/Newell) FD의 속도.

    혼잡(right) branch는 (rho_crit, rho_jam)로 고정하고, 자유류(left) branch의 기울기를
    VSL(=자유류 속도)로 회전시킨다. 임계밀도 rho_c = 두 branch 접점이므로 VSL이 낮아지면
    rho_c는 오르고 capacity(=VSL·rho_c)는 내린다 — capacity-drop 회피의 물리적 근거.
    VSL=v_free에서 접점=nominal rho_crit이 되도록 backward-wave 속도 w를 앵커한다."""
    s = max(vsl, 1.0e-9)                                      # 자유류 branch 속도 = VSL
    rho_c = rho_crit_for_vsl(vsl, v_free, rho_crit, rho_jam)  # VSL 의존 임계밀도(접점)
    if rho <= rho_c:
        return float(s)
    w = v_free * rho_crit / max(rho_jam - rho_crit, 1.0e-9)   # 고정 backward-wave 속도
    return float(max(0.0, w * max(rho_jam - rho, 0.0) / max(rho, 1.0e-9)))


def rho_crit_for_vsl(vsl: float, v_free: float, rho_crit: float, rho_jam: float) -> float:
    """two-branch FD에서 VSL이 옮긴 임계밀도 ρ_crit(VSL)=두 branch 접점.

    w = v_free·rho_crit/(rho_jam−rho_crit)(고정 backward-wave), ρ_c(vsl)=w·rho_jam/(vsl+w).
    VSL=v_free이면 ρ_c=nominal rho_crit(정확히 앵커). VSL↓ → ρ_c↑(감속으로 더 촘촘히 = 임계↑).
    rho_crit(VSL)의 유일 출처 — plant/leader/follower의 모든 rho_crit 소비처가 정합하게 이걸 쓴다."""
    w = v_free * rho_crit / max(rho_jam - rho_crit, 1.0e-9)
    return float(w * rho_jam / max(max(vsl, 1.0e-9) + w, 1.0e-9))


def two_branch_nominal_rho_crit(net) -> float:
    """two-branch 삼각형 FD의 nominal 임계밀도(VSL=v_free 앵커).

    삼각형 capacity = v_free·rho_crit이라 exponential용 rho_crit(33.5)을 그대로 쓰면 capacity가
    뻥튀기됨(3350). `rho_crit_two_branch`(예: 19.6)를 설정하면 삼각형 capacity를 현실값(~1950)으로
    재calibration. 미설정(0/None)이면 net.rho_crit로 fallback(=구 동작)."""
    tb = float(getattr(net, "rho_crit_two_branch", 0.0) or 0.0)
    return tb if tb > 0.0 else float(net.rho_crit)


def effective_rho_crit(net, vsl: float) -> float:
    """net 설정에 따른 유효 임계밀도. two_branch면 ρ_crit(VSL), 아니면 고정 nominal rho_crit.

    기본(vsl_fd_two_branch=False)이면 net.rho_crit 그대로 → 비트 동일. vsl=None/음수 방어."""
    if not getattr(net, "vsl_fd_two_branch", False):
        return float(net.rho_crit)
    v = float(vsl) if vsl is not None else float(net.v_free)
    return rho_crit_for_vsl(v, float(net.v_free), two_branch_nominal_rho_crit(net), float(net.rho_max))


def effective_desired_speed_kmh(
    rho: float,
    v_free: float,
    rho_crit: float,
    vsl: float,
    alpha_vsl: float = 0.0,
    vsl_active: bool = True,
    a: float = 1.867,
    two_branch: bool = False,
    rho_jam: float = 0.0,
    rho_crit_tb: float = 0.0,
) -> float:
    """Compute V_eff from the split spec's VSL desired-speed rule.

    two_branch=True면 speed-cap(min form) 대신 VSL이 임계밀도를 옮기는 two-branch FD를
    쓴다(기본 False → 기존 동작·테스트 불변). vsl_active=False면 VSL=v_free의 nominal FD.
    rho_crit_tb>0이면 삼각형 nominal 임계밀도로 그 값을 씀(capacity 재calibration; 0이면 rho_crit)."""
    if two_branch and rho_jam > 0.0:
        nominal = rho_crit_tb if rho_crit_tb > 0.0 else rho_crit
        return two_branch_vsl_speed_kmh(
            rho, v_free, nominal, rho_jam, vsl if vsl_active else v_free
        )
    no_vsl = desired_speed_kmh(rho, v_free, rho_crit, a)
    if not vsl_active:
        return no_vsl
    return float(min(no_vsl, (1.0 + alpha_vsl) * vsl))


def metanet_speed_update_kmh(
    speed: float,
    upstream_speed: float,
    rho: float,
    downstream_rho: float,
    v_eff: float,
    dt_h: float,
    length_km: float,
    tau_h: float,
    nu_km2_h: float,
    kappa_veh_km_lane: float,
    v_min: float,
) -> float:
    """METANET relaxation + convection + anticipation speed update."""
    relaxation = dt_h / max(tau_h, 1.0e-9) * (v_eff - speed)
    convection = dt_h / max(length_km, 1.0e-9) * speed * (upstream_speed - speed)
    anticipation = (
        -nu_km2_h
        * dt_h
        / (max(tau_h, 1.0e-9) * max(length_km, 1.0e-9))
        * (downstream_rho - rho)
        / max(rho + kappa_veh_km_lane, 1.0e-9)
    )
    return float(max(v_min, speed + relaxation + convection + anticipation))


def select_anticipation_nu(rho: float, net, vsl: float = None) -> float:
    """Arora & Kattan modified METANET(eq 9): 혼잡 regime(ρ>ρ_crit)에서 anticipation ν를
    ν_cong로 전환해 capacity drop을 표현. toggle off면 단일 ν_free.

    anticipation 항은 음수(하류가 더 혼잡할 때 감속)이므로 ν_cong>ν_free면 혼잡 시 감속이 커져
    속도·flow가 더 떨어진다(capacity drop 방향).

    two_branch면 capacity-drop 발화 임계를 ρ_crit(VSL)로 — VSL이 임계를 올려 merge를 subcritical로
    지키면 nu-drop을 실제로 피한다(VSL의 교과서 이득). vsl=None이면 nominal(비트 동일)."""
    rho_c = effective_rho_crit(net, vsl) if vsl is not None else float(net.rho_crit)
    if getattr(net, "capacity_drop_anticipation", False) and rho > rho_c:
        return float(net.metanet_nu_cong_km2_h)
    return float(net.metanet_nu_km2_h)


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _nuf_target_flow_veh_h(control: ControlAction, cfg: ExperimentConfig) -> float:
    if cfg.leader.N_UF_star_unit == "veh_per_control_interval":
        return float(control.N_UF_star / max(cfg.simulation.T_c_h, 1.0e-9))
    return float(control.N_UF_star)


def _ramp_merge_index(cfg: ExperimentConfig, ramp: str, n_segments: int) -> int:
    configured = getattr(cfg.network, "ramp_merge_segment_index", {})
    if isinstance(configured, dict) and ramp in configured:
        return int(_clip(float(configured[ramp]), 0.0, float(n_segments - 1)))
    return n_segments // 2


def _configured_segment_index(
    configured: Dict[str, int],
    key: str,
    default: int,
    n_segments: int,
) -> int:
    if isinstance(configured, dict) and key in configured:
        return int(_clip(float(configured[key]), 0.0, float(n_segments - 1)))
    return int(_clip(float(default), 0.0, float(n_segments - 1)))


def offramp_spillback_lambda_eff(
    occupancy_veh: float,
    capacity_veh: float,
    nominal_lanes: float,
    lane_reduction: float,
    gamma: float,
    b: float,
) -> float:
    """Wu Eq.(22) 계열 spill-back lane reduction을 분수 차로 감소까지 일반화한다."""
    if capacity_veh <= 0.0 or lane_reduction <= 0.0:
        return float(nominal_lanes)
    occupancy = _clip(float(occupancy_veh), 0.0, float(capacity_veh))
    if occupancy <= 1.0e-9:
        return float(nominal_lanes)
    if occupancy >= capacity_veh - 1.0e-9:
        return float(max(1.0e-9, nominal_lanes - lane_reduction))
    scale = occupancy / max(gamma * capacity_veh, 1.0e-9)
    decay = math.exp(-(1.0 / max(b, 1.0e-9)) * (scale ** b))
    return float(max(1.0e-9, nominal_lanes - lane_reduction * (1.0 - decay)))


def effective_lane_profile(
    state: TrafficState,
    cfg: ExperimentConfig,
    demand: DemandStep | None = None,
) -> Tuple[Dict[str, List[float]], Dict[str, float]]:
    """현재 off-ramp storage 점유율에서 freeway segment별 effective lane profile을 계산한다."""
    net = cfg.network
    drop = cfg.freeway_offramp_capacity_drop
    state.ensure_freeway_lane_profile(net)
    profile = {
        link: [float(net.freeway_lanes) for _ in state.freeway_density.get(link, [])]
        for link in net.freeway_links
    }
    diagnostics: Dict[str, float] = {"capacity_drop_active": 0.0}
    if drop.enabled:
        for off_ramp in net.off_ramps:
            link = net.off_ramp_from_freeway.get(off_ramp)
            if link not in profile or not profile[link]:
                continue
            storage_link = net.off_ramp_storage_link.get(off_ramp)
            capacity = float(net.urban_link_storage_veh.get(storage_link, 0.0))
            available = float(state.urban_link_storage.get(storage_link, capacity))
            occupancy = _clip(capacity - available, 0.0, capacity)
            ratio = occupancy / max(capacity, 1.0e-9)
            lambda_eff = offramp_spillback_lambda_eff(
                occupancy,
                capacity,
                float(net.freeway_lanes),
                float(drop.lane_reduction),
                float(drop.gamma),
                float(drop.b),
            )
            segment_idx = _configured_segment_index(
                getattr(net, "off_ramp_segment_index", {}),
                off_ramp,
                len(profile[link]) - 1,
                len(profile[link]),
            )
            profile[link][segment_idx] = min(profile[link][segment_idx], lambda_eff)
            diagnostics[f"offramp_occupancy_ratio_{off_ramp}"] = float(ratio)
            diagnostics[f"lambda_eff_{link}_seg{segment_idx}"] = float(profile[link][segment_idx])
            diagnostics[f"capacity_drop_lane_loss_{link}_seg{segment_idx}"] = float(
                max(0.0, net.freeway_lanes - profile[link][segment_idx])
            )

    diagnostics["incident_lane_closure_active"] = 0.0
    lane_losses = getattr(demand, "freeway_lane_loss", {}) if demand is not None else {}
    # Incident 차로 폐쇄와 off-ramp spillback이 겹치면 더 작은 effective lane 수를 적용한다.
    for link, segment_losses in lane_losses.items():
        if link not in profile:
            continue
        for segment, loss in segment_losses.items():
            segment_idx = int(segment)
            if not 0 <= segment_idx < len(profile[link]):
                continue
            incident_lanes = max(1.0e-9, float(net.freeway_lanes) - max(0.0, float(loss)))
            profile[link][segment_idx] = min(profile[link][segment_idx], incident_lanes)
            diagnostics["incident_lane_closure_active"] = 1.0
            diagnostics[f"incident_lane_loss_{link}_seg{segment_idx}"] = float(
                max(0.0, net.freeway_lanes - profile[link][segment_idx])
            )

    for link, lanes in profile.items():
        if not lanes:
            continue
        diagnostics.setdefault(f"lambda_eff_{link}_last", float(lanes[-1]))
        diagnostics.setdefault(f"capacity_drop_lane_loss_{link}_last", 0.0)
        for i, lane in enumerate(lanes):
            diagnostics.setdefault(f"lambda_eff_{link}_seg{i}", float(lane))
            diagnostics.setdefault(
                f"capacity_drop_lane_loss_{link}_seg{i}",
                float(max(0.0, net.freeway_lanes - lane)),
            )
        if min(lanes) < net.freeway_lanes - 1.0e-9:
            diagnostics["capacity_drop_active"] = 1.0
    return profile, diagnostics


def compute_ramp_release_flows(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
    include_current_arrivals: bool = True,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Spec 3.2 ramp outflow 제약을 한 `T_f` 경계에서 계산한다."""
    net = cfg.network
    dt_h = cfg.simulation.T_f_h
    cap_factor = getattr(demand, "incident_capacity_factor", 1.0)
    q_cap = net.freeway_capacity_veh_h * cap_factor
    ramp_release: Dict[str, float] = {}
    receiving_factor_acc = 0.0
    no_meter_total = 0.0

    for ramp in net.ramps:
        link = net.ramp_to_freeway[ramp]
        merge_idx = _ramp_merge_index(cfg, ramp, len(state.freeway_density[link]))
        rho_merge = state.freeway_density[link][merge_idx]
        # two_branch면 merge segment의 VSL이 옮긴 ρ_crit(VSL)로 수용력 계산 — VSL이 임계를 올리면
        # (rho_max−ρ_crit(VSL))↓ → receiving_factor↑ → freeway가 더 받음(VSL의 방류-허용 이득).
        rho_c_merge = effective_rho_crit(net, segment_vsl(control, link, merge_idx, cfg))
        receiving_factor = _clip(
            (net.rho_max - rho_merge) / max(net.rho_max - rho_c_merge, 1.0e-9),
            0.0,
            1.0,
        )
        receiving_factor_acc += receiving_factor

        cap = net.ramp_capacity_veh_h[ramp]
        arrival = demand.ramp_arrival.get(ramp, 0.0) if include_current_arrivals else 0.0
        requested = _clip(control.ramp_metering.get(ramp, cap), 0.0, cap)
        available = max(0.0, arrival + state.ramp_queue.get(ramp, 0.0) / max(dt_h, 1.0e-9))
        no_meter = min(available, cap, q_cap * receiving_factor)
        release = min(no_meter, requested)
        ramp_release[ramp] = release
        no_meter_total += no_meter

    diagnostics = {
        "total_metering_flow": float(sum(ramp_release.values())),
        "total_no_meter_flow": float(no_meter_total),
        # 방출 결정 시점(T_f 시작)의 w_r 환산유량 — metering binding 판정 기준.
        # (cycle 위상 plant에서는 green 펄스가 T_f 중간에 w_r을 채우는데, 그 분량은
        # 이번 방출 결정이 볼 수 없었던 차량이라 '잡아둠'으로 채점하면 안 된다.)
        "total_ramp_queue_start_flow": float(
            sum(max(0.0, state.ramp_queue.get(r, 0.0)) for r in net.ramps) / max(dt_h, 1.0e-9)
        ),
        "mean_ramp_receiving_factor": (
            receiving_factor_acc / max(len(net.ramps), 1)
        ),
    }
    return ramp_release, diagnostics


def freeway_substep(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
    offramp_capacity_veh_h: Dict[str, float] | None = None,
    ramp_release_veh_h: Dict[str, float] | None = None,
    ramp_release_diagnostics: Dict[str, float] | None = None,
    update_ramp_queues: bool = True,
    include_ramp_queue_ttt: bool = True,
) -> Tuple[float, Dict[str, float]]:
    """Spec 3.1/3.2 METANET plant를 정확히 한 `T_f` step만 전진한다."""
    net = cfg.network
    sim = cfg.simulation
    dt_h = sim.T_f_h

    state.ensure_freeway_lane_profile(net)
    for link in net.freeway_links:
        state.mainline_origin_queue.setdefault(link, 0.0)
    freeway_ttt = 0.0
    density_projection_count = 0
    speed_projection_count = 0
    flow_acc = 0.0
    flow_count = 0
    offramp_flow_acc: Dict[str, float] = {link: 0.0 for link in net.freeway_links}
    offramp_blocked_acc: Dict[str, float] = {link: 0.0 for link in net.freeway_links}
    # 본선 마지막 세그먼트에서 off-ramp로 빠지지 않고 시스템을 이탈하는 유량(완료차량 회계용).
    mainline_exit_acc: Dict[str, float] = {link: 0.0 for link in net.freeway_links}
    cap_factor = getattr(demand, "incident_capacity_factor", 1.0)
    q_cap = net.freeway_capacity_veh_h * cap_factor
    target_flow = _nuf_target_flow_veh_h(control, cfg)

    if ramp_release_veh_h is None:
        ramp_release, ramp_diag = compute_ramp_release_flows(state, control, demand, cfg)
    else:
        ramp_release = dict(ramp_release_veh_h)
        ramp_diag = (
            dict(ramp_release_diagnostics)
            if ramp_release_diagnostics is not None
            else compute_ramp_release_flows(state, control, demand, cfg)[1]
        )

    ramp_in_by_link = {
        link: [0.0 for _ in state.freeway_density[link]]
        for link in net.freeway_links
    }
    for ramp, release in ramp_release.items():
        link = net.ramp_to_freeway[ramp]
        merge_idx = _ramp_merge_index(cfg, ramp, len(state.freeway_density[link]))
        ramp_in_by_link[link][merge_idx] += max(0.0, release)
        if update_ramp_queues:
            # standalone freeway_step에서는 ramp demand와 release를 여기서 보존식으로 갱신한다.
            arrival = demand.ramp_arrival.get(ramp, 0.0)
            next_queue = state.ramp_queue.get(ramp, 0.0) + dt_h * (arrival - release)
            state.ramp_queue[ramp] = max(0.0, next_queue)

    lane_now_by_link, lane_diag_start = effective_lane_profile(state, cfg, demand)
    for link in net.freeway_links:
        rhos = list(state.freeway_density[link])
        speeds = list(state.freeway_speed[link])
        previous_lanes = list(state.freeway_effective_lanes.get(link, []))
        lanes_now = lane_now_by_link[link]
        offramps_by_segment: Dict[int, list[str]] = {}
        for off_ramp in net.off_ramps:
            if net.off_ramp_from_freeway.get(off_ramp) != link:
                continue
            segment_idx = _configured_segment_index(
                getattr(net, "off_ramp_segment_index", {}),
                off_ramp,
                len(rhos) - 1,
                len(rhos),
            )
            offramps_by_segment.setdefault(segment_idx, []).append(off_ramp)
        vehicles = [
            max(0.0, rho) * net.freeway_segment_length_km * max(lane, 1.0e-9)
            for rho, lane in zip(rhos, previous_lanes)
        ]
        rho_for_flow = [
            n / max(net.freeway_segment_length_km * max(lane, 1.0e-9), 1.0e-9)
            for n, lane in zip(vehicles, lanes_now)
        ]
        vsl_max = max(cfg.freeway_follower.vsl_set)
        # sending[i] = METANET 유량(=demand). spec §3.1.2 demand-supply의 송출량.
        q_values = [
            segment_flow_veh_h(rho, speed, lane)
            for rho, speed, lane in zip(rho_for_flow, speeds, lanes_now)
        ]
        flow_acc += sum(q_values)
        flow_count += len(q_values)

        # receiving[i] = 하류 segment i가 이번 step에 받을 수 있는 CTM supply [veh/h].
        # (rho_max - rho_for_flow)·L·lambda_eff / dt 로, 채우면 정확히 rho_max가 되는 양.
        receiving = [
            max(
                0.0,
                (net.rho_max - rho_for_flow[i])
                * net.freeway_segment_length_km
                * max(lanes_now[i], 1.0e-9)
                / max(dt_h, 1.0e-9),
            )
            for i in range(len(rho_for_flow))
        ]
        # merge segment의 supply 중 ramp 유입분을 먼저 예약하고, 본선 inter-segment 흐름은
        # 남은 supply로만 제한한다(ramp release는 이미 receiving_factor로 게이트됨).
        receiving_for_mainline = [
            max(0.0, receiving[i] - max(0.0, ramp_in_by_link[link][i]))
            for i in range(len(rho_for_flow))
        ]
        # 각 segment에서 빠지는 off-ramp split은 downstream mainline sending에서 제외한다.
        off_ratio_by_segment = [
            _clip(
                sum(net.off_ramp_split_ratio.get(off_ramp, 0.0) for off_ramp in offramps_by_segment.get(i, [])),
                0.0,
                1.0,
            )
            for i in range(len(rho_for_flow))
        ]
        mainline_sending = [
            (1.0 - off_ratio_by_segment[i]) * q_values[i]
            for i in range(len(rho_for_flow))
        ]
        # q_inter[i] = segment i -> i+1 실제 본선 흐름 = min(mainline sending, 하류 supply).
        q_inter = [
            min(mainline_sending[i], receiving_for_mainline[i + 1])
            for i in range(len(rho_for_flow) - 1)
        ]
        # 진입 경계: 본선 수요 + origin 큐 환산을 receiving[0]·q_cap으로 제한, 못 들어간
        # 본선 수요는 origin 큐에 누적(보존). ramp 유입은 별도 게이트라 여기서 제외.
        if state.mainline_origin_queue.get(link) is None:
            state.mainline_origin_queue[link] = 0.0
        mainline_demand = max(0.0, demand.freeway_mainline.get(link, 0.0))
        queued_flow = state.mainline_origin_queue[link] / max(dt_h, 1.0e-9)
        entry_request = mainline_demand + queued_flow
        entry_realized = min(entry_request, q_cap, receiving_for_mainline[0])
        # 큐 갱신: 새 본선 수요 중 실제 진입 못한 분량을 origin 큐에 보관.
        state.mainline_origin_queue[link] = max(
            0.0,
            state.mainline_origin_queue[link] + dt_h * (mainline_demand - entry_realized),
        )

        next_rhos = []
        next_speeds = []
        next_flows = []
        next_lanes = []
        next_vehicle_count = []
        for i, rho in enumerate(rho_for_flow):
            # Spec 3.1.2 밀도 갱신: q_in/q_out은 veh/h, dt는 hour 단위로 계산한다.
            q_in = entry_realized if i == 0 else q_inter[i - 1]
            q_in += ramp_in_by_link[link][i]
            q_out = mainline_sending[i] if i == len(rhos) - 1 else q_inter[i]
            boundary_speed_cap = None
            effective_off_total = 0.0
            normal_off_total = 0.0
            for off_ramp in offramps_by_segment.get(i, []):
                ratio = _clip(net.off_ramp_split_ratio.get(off_ramp, 0.0), 0.0, 1.0)
                normal_off = ratio * q_values[i]
                if offramp_capacity_veh_h is None:
                    cap = None
                else:
                    cap = offramp_capacity_veh_h.get(
                        off_ramp,
                        offramp_capacity_veh_h.get(link),
                    )
                effective_off = normal_off if cap is None else min(normal_off, max(0.0, cap))
                effective_off_total += effective_off
                normal_off_total += normal_off
                offramp_flow_acc[off_ramp] = offramp_flow_acc.get(off_ramp, 0.0) + effective_off
                offramp_blocked_acc[off_ramp] = offramp_blocked_acc.get(off_ramp, 0.0) + max(
                    0.0,
                    normal_off - effective_off,
                )
            if normal_off_total > 0.0:
                q_out += effective_off_total
                offramp_flow_acc[link] += effective_off_total
                offramp_blocked_acc[link] += max(0.0, normal_off_total - effective_off_total)
                if normal_off_total > effective_off_total + 1.0e-9:
                    boundary_speed_cap = q_out / max(rho * lanes_now[i], 1.0e-9)
            if i == len(rhos) - 1:
                mainline_exit_acc[link] += mainline_sending[i]
            vehicle_raw = vehicles[i] + dt_h * (q_in - q_out)
            vehicle_new = max(0.0, vehicle_raw)
            if abs(vehicle_new - vehicle_raw) > 1.0e-9:
                density_projection_count += 1
            rho_new = vehicle_new / max(net.freeway_segment_length_km * max(lanes_now[i], 1.0e-9), 1.0e-9)

            upstream_speed = net.v_free if i == 0 else speeds[i - 1]
            downstream_rho = rho_for_flow[i + 1] if i + 1 < len(rhos) else rho_for_flow[i]
            # Option C: VSL을 segment별로 읽는다(segment 키 없으면 link 키 fallback).
            vsl_i = segment_vsl(control, link, i, cfg)
            vsl_active_i = vsl_i < vsl_max - 0.5
            v_eff = effective_desired_speed_kmh(
                rho,
                net.v_free,
                net.rho_crit,
                vsl_i,
                net.alpha_vsl,
                vsl_active_i,
                net.metanet_a_m,
                getattr(net, "vsl_fd_two_branch", False),
                net.rho_max,
                float(getattr(net, "rho_crit_two_branch", 0.0) or 0.0),
            )
            v_new = metanet_speed_update_kmh(
                speeds[i],
                upstream_speed,
                rho,
                downstream_rho,
                v_eff,
                dt_h,
                net.freeway_segment_length_km,
                net.metanet_tau_h,
                select_anticipation_nu(rho, net, vsl_i),
                net.metanet_kappa_veh_km_lane,
                net.v_min,
            )
            if v_new <= net.v_min + 1.0e-9:
                speed_projection_count += 1
            if boundary_speed_cap is not None and v_new > boundary_speed_cap:
                v_new = max(net.v_min, boundary_speed_cap)
                speed_projection_count += 1
            next_rhos.append(rho_new)
            next_speeds.append(v_new)
            next_lanes.append(float(lanes_now[i]))
            next_vehicle_count.append(float(vehicle_new))
            next_flows.append(segment_flow_veh_h(rho_new, v_new, lanes_now[i]))

        state.freeway_density[link] = next_rhos
        state.freeway_speed[link] = next_speeds
        state.freeway_flow[link] = next_flows
        state.freeway_effective_lanes[link] = next_lanes
        freeway_ttt += sum(next_vehicle_count) * dt_h

    if include_ramp_queue_ttt:
        freeway_ttt += sum(state.ramp_queue.values()) * dt_h
        # origin 큐 대기 차량도 freeway 지연을 겪으므로 ramp 큐와 동일하게 TTT에 적분한다.
        freeway_ttt += sum(max(0.0, q) for q in state.mainline_origin_queue.values()) * dt_h

    diagnostics: Dict[str, float] = {}
    avg_metering = float(sum(ramp_release.values()))
    avg_no_meter = ramp_diag["total_no_meter_flow"]
    diagnostics["total_metering_flow"] = avg_metering
    # N_UF_star는 "여기까지 허용"하는 상한(ceiling)이다. 잔차는 비대칭으로 채점한다.
    # ① 상한 초과(actual > target): 초과분이 위반.
    # ② 잡아둠(shortfall): 목표 미달이면서 그만큼 w_r이 실제로 누적된 양만 위반.
    #    no_meter의 available(w_r/dt)은 재고 10대를 10초 창 유량 3600veh/h로 환산하는
    #    stock/flow 범주 오류라 판정 기준으로 쓰지 않는다 — 방출이 목표 아래여도
    #    큐가 자라지 않으면(도착을 소화하면) 잡아둔 것이 아니다.
    # 원목표 미달은 metering_target_infeasible로 따로 표시.
    queue_start_veh = float(ramp_diag.get("total_ramp_queue_start_flow", 0.0)) * dt_h
    queue_end_veh = sum(max(0.0, q) for q in state.ramp_queue.values())
    queue_growth_flow = max(0.0, queue_end_veh - queue_start_veh) / max(dt_h, 1.0e-9)
    over_release = max(0.0, avg_metering - target_flow)
    shortfall = min(max(0.0, target_flow - avg_metering), queue_growth_flow)
    diagnostics["total_metering_error"] = over_release + shortfall
    diagnostics["total_no_meter_flow"] = float(avg_no_meter)
    diagnostics["metering_over_release_flow"] = float(over_release)
    diagnostics["metering_shortfall_flow"] = float(shortfall)
    # interval 단위 재채점용 원자료(coupling 집계에서 사용): cycle 위상 plant에서는
    # T_f(10s) 창의 큐 증감이 green 펄스로 진동하므로 interval 수준에서 채점해야 한다.
    diagnostics["nuf_target_flow"] = float(target_flow)
    diagnostics["total_ramp_queue_start_veh"] = float(queue_start_veh)
    diagnostics["total_ramp_queue_end_veh"] = float(queue_end_veh)
    diagnostics["metering_target_infeasible"] = float(target_flow > avg_no_meter + cfg.freeway_follower.eps_F)
    diagnostics["ramp_queue_overflow_count"] = float(sum(
        1 for q in state.ramp_queue.values() if q > net.ramp_queue_max_veh
    ))
    diagnostics["mean_ramp_receiving_factor"] = ramp_diag["mean_ramp_receiving_factor"]
    diagnostics["mean_segment_flow"] = flow_acc / flow_count if flow_count else 0.0
    diagnostics.update(lane_diag_start)
    diagnostics["offramp_storage_binding"] = float(any(v > 1.0e-9 for v in offramp_blocked_acc.values()))
    diagnostics["offramp_flow_total"] = float(
        sum(offramp_flow_acc.get(off_ramp, 0.0) for off_ramp in net.off_ramps)
    )
    diagnostics["offramp_blocked_flow_total"] = float(
        sum(offramp_blocked_acc.get(off_ramp, 0.0) for off_ramp in net.off_ramps)
    )
    # 완료차량 회계: 본선 이탈 유량[veh/h] — × T_f_h 적분 시 이탈 차량수.
    diagnostics["mainline_exit_flow_total"] = float(sum(mainline_exit_acc.values()))
    for off_ramp in net.off_ramps:
        diagnostics[f"offramp_flow_{off_ramp}"] = float(offramp_flow_acc.get(off_ramp, 0.0))
        diagnostics[f"offramp_blocked_flow_{off_ramp}"] = float(offramp_blocked_acc.get(off_ramp, 0.0))
    for link in net.freeway_links:
        diagnostics[f"offramp_flow_{link}"] = float(offramp_flow_acc.get(link, 0.0))
        diagnostics[f"offramp_blocked_flow_{link}"] = float(offramp_blocked_acc.get(link, 0.0))
    diagnostics["density_projection_count"] = float(density_projection_count)
    diagnostics["speed_projection_count"] = float(speed_projection_count)
    # CTM receiving 제약으로 본선 진입 못한 대기 차량[veh] — origin 보관 보존 확인용.
    diagnostics["mainline_origin_queue_total_veh"] = float(
        sum(max(0.0, q) for q in state.mainline_origin_queue.values())
    )
    diagnostics["density_exceedance_count"] = float(sum(
        1
        for values in state.freeway_density.values()
        for rho in values
        if rho > net.rho_crit
    ))
    return float(freeway_ttt), diagnostics


def _aggregate_freeway_diagnostics(rows: list[Dict[str, float]]) -> Dict[str, float]:
    if not rows:
        return {}
    avg_keys = {
        "total_metering_flow",
        "total_metering_error",
        "mean_ramp_receiving_factor",
        "mean_segment_flow",
        "offramp_flow_total",
        "offramp_blocked_flow_total",
    }
    out: Dict[str, float] = {}
    keys = set().union(*(row.keys() for row in rows))
    for key in keys:
        values = [row.get(key, 0.0) for row in rows]
        if (
            key in avg_keys
            or key.startswith("offramp_flow_")
            or key.startswith("offramp_blocked_flow_")
            or key.startswith("lambda_eff_")
            or key.startswith("capacity_drop_lane_loss_")
            or key.startswith("offramp_occupancy_ratio_")
        ):
            out[key] = float(sum(values) / max(len(values), 1))
        elif key in {"metering_target_infeasible", "offramp_storage_binding", "capacity_drop_active"}:
            out[key] = float(max(values))
        else:
            out[key] = float(sum(values))
    return out


def freeway_step(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
    offramp_capacity_veh_h: Dict[str, float] | None = None,
) -> Tuple[float, Dict[str, float]]:
    """기존 API 호환용 wrapper: 한 control interval 동안 `K_cf`개 freeway substep을 실행한다."""
    total_ttt = 0.0
    diagnostics: list[Dict[str, float]] = []
    for _ in range(cfg.simulation.K_cf):
        fw_ttt, fw_diag = freeway_substep(
            state,
            control,
            demand,
            cfg,
            offramp_capacity_veh_h=offramp_capacity_veh_h,
        )
        total_ttt += fw_ttt
        diagnostics.append(fw_diag)
    return float(total_ttt), _aggregate_freeway_diagnostics(diagnostics)
