# Wu(2022) authority(green+VSL) 분산 컨트롤러 — WU-CD-F와 WU-MATCHED-STACKELBERG (spec 16.4~16.5)
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional

import numpy as np

from src.models.demand import DemandStep
from src.models.metanet import effective_desired_speed_kmh, segment_flow_veh_h
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import movement_specs


@dataclass(frozen=True)
class WuLeaderAction:
    """WU-MATCHED-STACKELBERG leader action (spec 16.5) — 둘 다 [veh] 단위 누적 목표."""

    n_p_star: float
    n_f_star: float


@dataclass
class WuDecisionInfo:
    control: ControlAction
    iterations: int
    converged: bool
    coupling_residual: float
    solver_evaluations: int
    computation_time_sec: float
    leader_candidates: int = 0
    leader_selected: Optional[WuLeaderAction] = None
    leader_objective: float = 0.0


def _wu_fixed_control(cfg: ExperimentConfig) -> ControlAction:
    """Wu authority의 고정 요소 — offset 고정 0, metering=용량(no-metering 물리 유출),
    allocation 미사용(빈 dict → plant가 movement 포화유율 1400으로 fallback)."""
    net = cfg.network
    green = {}
    phase_green = net.effective_green_total / 2.0
    for signal in net.signals:
        green[f"{signal}_p1"] = phase_green
        green[f"{signal}_p2"] = phase_green
    return ControlAction(
        ramp_metering={r: net.ramp_capacity_veh_h[r] for r in net.ramps},
        vsl={link: max(cfg.freeway_follower.vsl_set) for link in net.freeway_links},
        green_times=green,
        offsets={signal: 0.0 for signal in net.signals},
        inflow_outflow_allocation={},
    )


class WuDistributedController:
    """Wu §IV-D 6단계 합의 루프의 경량 재구성.

    - urban agent(신호 단위): green p1 후보 탐색, 이웃 결합변수(도착유량) 고정.
    - freeway agent(링크 단위): VSL 후보 탐색, on-ramp 유입(urban 결합) 고정.
    - local 예측은 경량 큐/밀도 모델(원문 MILP/SQP 대신 결정적 후보 탐색 —
      wu2022_distributed_reference §8의 허용 근사, fidelity matrix에 기록).
    - leader_enabled=True면 (N_P_star, N_F_star)[veh] conditioning 항을 local objective에
      추가하고, leader가 후보별 coupled 예측으로 system objective를 평가한다(spec 16.5).
    """

    def __init__(self, cfg: ExperimentConfig, leader_enabled: bool = False):
        self.cfg = cfg
        self.leader_enabled = leader_enabled
        self.previous_control: Optional[ControlAction] = None
        self._specs = movement_specs(cfg)
        net = cfg.network
        # 신호별 phase 소속 movement와 포화유율 합(서비스율 = green비율 × Σ포화).
        self._phase_movements: Dict[str, Dict[str, list[str]]] = {}
        for signal in net.signals:
            self._phase_movements[signal] = {
                "p1": [m for m, s in self._specs.items() if s.get("phase") == f"{signal}_p1"],
                "p2": [m for m, s in self._specs.items() if s.get("phase") == f"{signal}_p2"],
            }
        # Leader conditioning 고정 가중 ω (spec 16.5: 평가 전에 고정, Σ=1).
        protected_kinds = {"internal", "boundary_out", "off_ramp"}
        cap_by_signal = {}
        for signal in net.signals:
            cap_by_signal[signal] = sum(
                1.0 for m, s in self._specs.items()
                if s.get("signal") == signal and str(s.get("kind")) in protected_kinds
            )
        total_cap = max(sum(cap_by_signal.values()), 1.0e-9)
        self._omega_p = {s: cap_by_signal[s] / total_cap for s in net.signals}
        self._omega_f = {link: 1.0 / max(len(net.freeway_links), 1) for link in net.freeway_links}

    # ---------- 결합변수 y (Wu §IV-B) ----------

    def _coupling(self, state: TrafficState, control: ControlAction, demand: DemandStep) -> Dict[str, float]:
        """agent 간 교환하는 결합변수 — local solve 동안 고정된다.

        urban→urban: 신호별 접근 도착유량 추정(상류 링크 점유/통과시간).
        urban→freeway: ramp별 no-metering 접근 방출 추정.
        freeway→urban: off-ramp 유입 유량(현재 본선 유량 × 분기율)."""
        net = self.cfg.network
        y: Dict[str, float] = {}
        t_link_h = (
            float(net.grid_link_storage_veh) * net.urban_avg_vehicle_length_m / 1000.0
            / max(net.urban_avg_speed_km_h, 1.0e-9)
        )
        # 신호·phase별 도착유량 추정: 게이트 수요(β분할) + off-ramp 유입 + 상류 링크
        # in-transit 점유의 방출률 — local solve 동안 고정되는 결합변수다.
        for signal in net.signals:
            arr = {"p1": 0.0, "p2": 0.0}
            for phase_id in ("p1", "p2"):
                for movement in self._phase_movements[signal][phase_id]:
                    spec = self._specs[movement]
                    kind = str(spec.get("kind", ""))
                    beta = float(spec.get("beta", 0.0))
                    origin = str(spec.get("origin", ""))
                    if kind == "boundary_in":
                        arr[phase_id] += beta * max(0.0, demand.urban_boundary.get(origin, 0.0))
                    elif kind == "off_ramp":
                        # freeway→urban 결합: 해당 off-ramp의 현재 유입 추정.
                        off_ramp = str(spec.get("off_ramp", ""))
                        link = net.off_ramp_from_freeway.get(off_ramp, "")
                        flow = state.freeway_flow.get(link, [0.0])[-1] if state.freeway_flow.get(link) else 0.0
                        ratio = net.off_ramp_split_ratio.get(off_ramp, 0.0)
                        arr[phase_id] += beta * max(0.0, flow * ratio)
                    else:
                        # 내부 movement: 상류 링크 점유가 통과시간에 걸쳐 도착.
                        cap = net.urban_link_storage_veh.get(origin, 0.0)
                        occupied = max(0.0, cap - state.urban_link_storage.get(origin, cap))
                        arr[phase_id] += beta * occupied / max(t_link_h, 1.0e-9) * 0.5
            y[f"arr_{signal}_p1"] = float(arr["p1"])
            y[f"arr_{signal}_p2"] = float(arr["p2"])
        # urban→freeway: ramp별 접근(x_on) no-metering 방출 추정 = min(대기+수요, green×포화).
        for ramp, movements in net.on_ramp_to_movement.items():
            queue = sum(max(0.0, state.urban_movement_queue.get(m, 0.0)) for m in movements)
            arrival = max(0.0, demand.ramp_arrival.get(ramp, 0.0))
            green_frac = 0.5
            sat = len(movements) * net.movement_capacity_veh_h
            y[f"u_on_{ramp}"] = float(min(queue / max(self.cfg.simulation.T_c_h, 1e-9) + arrival, green_frac * sat))
        # freeway boundary 상태(진단·잔차용).
        for link in net.freeway_links:
            rhos = state.freeway_density.get(link, [])
            y[f"rho_{link}"] = float(np.mean(rhos)) if rhos else 0.0
        return y

    # ---------- urban agent local solve ----------

    def _solve_urban_agent(
        self,
        signal: str,
        state: TrafficState,
        coupling: Mapping[str, float],
        previous: ControlAction,
        leader: Optional[WuLeaderAction],
    ) -> tuple[float, float, int]:
        """green p1 후보 탐색 — 반환 (p1*, local objective, evaluations).

        local 모델: phase별 집계 큐 q_p가 도착유량(결합변수 고정) − 서비스율로 진화.
        서비스율 = (green/cycle) × Σ포화유율(plant의 cycle 평균과 동일 회계).
        J = T_c Σ_k (q_p1+q_p2) + R(Δp1)² (+ leader conditioning)."""
        net = self.cfg.network
        sim = self.cfg.simulation
        horizon = max(1, self.cfg.mpc.horizon_steps)
        dt_h = sim.T_c_h
        total = net.effective_green_total
        sat = {
            pid: max(
                sum(
                    min(net.movement_capacity_veh_h, net.movement_capacity_veh_h)
                    for _ in self._phase_movements[signal][pid]
                ),
                1.0e-9,
            )
            for pid in ("p1", "p2")
        }
        q0 = {
            pid: sum(
                max(0.0, state.urban_movement_queue.get(m, 0.0))
                for m in self._phase_movements[signal][pid]
            )
            for pid in ("p1", "p2")
        }
        arr = {pid: float(coupling.get(f"arr_{signal}_{pid}", 0.0)) for pid in ("p1", "p2")}
        prev_p1 = float(previous.green_times.get(f"{signal}_p1", total / 2.0))
        smooth_w = self.cfg.urban_follower.green_smoothness_weight

        candidates = np.linspace(net.green_min, net.green_max, 7)
        best_p1, best_obj = prev_p1, float("inf")
        evals = 0
        for p1 in candidates:
            p2 = total - p1
            if p2 < net.green_min - 1.0e-9 or p2 > net.green_max + 1.0e-9:
                continue
            q = dict(q0)
            cost = 0.0
            for _ in range(horizon):
                for pid, g in (("p1", p1), ("p2", p2)):
                    service = (g / max(net.cycle_length, 1e-9)) * sat[pid] * dt_h
                    q[pid] = max(0.0, q[pid] + arr[pid] * dt_h - service)
                cost += (q["p1"] + q["p2"]) * dt_h
            cost += smooth_w * abs(p1 - prev_p1)
            if leader is not None:
                # spec 16.5 conditioning: 예측 국소 누적이 ω×N_P_star를 넘으면 패널티.
                n_pred = q["p1"] + q["p2"]
                cost += self.cfg.leader.w_P * max(0.0, n_pred - self._omega_p[signal] * leader.n_p_star)
            evals += 1
            if cost < best_obj:
                best_obj, best_p1 = cost, float(p1)
        return best_p1, best_obj, evals

    # ---------- freeway agent local solve ----------

    def _solve_freeway_agent(
        self,
        link: str,
        state: TrafficState,
        coupling: Mapping[str, float],
        previous: ControlAction,
        leader: Optional[WuLeaderAction],
    ) -> tuple[float, float, int]:
        """VSL 후보 탐색 — 반환 (vsl*, local objective, evaluations).

        local 모델: 링크 평균 밀도 1-구획 근사 — ρ' = ρ + (q_in − q_out(ρ, vsl))dt/(LλN).
        q_in = 본선수요 + 이 링크 ramp들의 no-metering 유입(결합변수 고정).
        J = T_c Σ L λ ρ + R(Δvsl)² (+ leader conditioning)."""
        net = self.cfg.network
        sim = self.cfg.simulation
        horizon = max(1, self.cfg.mpc.horizon_steps)
        dt_h = sim.T_c_h
        n_seg = net.freeway_segments_per_link
        length = net.freeway_segment_length_km * n_seg
        lanes = float(net.freeway_lanes)
        rho0 = float(np.mean(state.freeway_density.get(link, [0.0])))
        ramp_in = sum(
            float(coupling.get(f"u_on_{ramp}", 0.0))
            for ramp in net.ramps
            if net.ramp_to_freeway.get(ramp) == link
        )
        mainline_in = 1650.0  # 결합변수에 본선 수요가 없으므로 공칭값(진단용 경량 모델).
        prev_vsl = float(previous.vsl.get(link, max(self.cfg.freeway_follower.vsl_set)))
        smooth_w = self.cfg.freeway_follower.vsl_smoothness_weight
        vsl_set = sorted(float(v) for v in self.cfg.freeway_follower.vsl_set)
        step = self.cfg.freeway_follower.max_vsl_step
        candidates = [v for v in vsl_set if abs(v - prev_vsl) <= step + 1e-9] or vsl_set

        best_vsl, best_obj = prev_vsl, float("inf")
        evals = 0
        for vsl in candidates:
            rho = rho0
            cost = 0.0
            for _ in range(horizon):
                vsl_active = vsl < max(vsl_set) - 0.5
                v_eff = effective_desired_speed_kmh(
                    rho, net.v_free, net.rho_crit, vsl, net.alpha_vsl, vsl_active, net.metanet_a_m,
                )
                q_out = segment_flow_veh_h(rho, min(v_eff, vsl if vsl_active else net.v_free), lanes)
                rho = max(0.0, rho + (mainline_in + ramp_in - q_out) * dt_h / max(length * lanes, 1e-9))
                cost += length * lanes * rho * dt_h
                cost += self.cfg.freeway_follower.density_penalty * max(0.0, rho - net.rho_crit) * dt_h
            cost += smooth_w * abs(vsl - prev_vsl)
            if leader is not None:
                n_pred = rho * length * lanes
                cost += self.cfg.leader.w_F * max(0.0, n_pred - self._omega_f[link] * leader.n_f_star)
            evals += 1
            if cost < best_obj:
                best_obj, best_vsl = cost, float(vsl)
        return best_vsl, best_obj, evals

    # ---------- 합의 루프 (Wu §IV-D) ----------

    def _solve_followers(
        self,
        state: TrafficState,
        demand: DemandStep,
        previous: ControlAction,
        leader: Optional[WuLeaderAction],
    ) -> tuple[ControlAction, int, bool, float, int]:
        net = self.cfg.network
        control = _wu_fixed_control(self.cfg)
        control.green_times = dict(previous.green_times)
        control.vsl = dict(previous.vsl)
        coupling = self._coupling(state, control, demand)
        s_max = max(1, self.cfg.mpc.max_nash_iter)
        evals = 0
        residual = float("inf")
        converged = False
        iteration = 0
        for iteration in range(1, s_max + 1):
            # step3~4: 결합변수 고정 후 agent별 local solve(green/VSL만 — Wu authority).
            for signal in net.signals:
                p1, _, e = self._solve_urban_agent(signal, state, coupling, control, leader)
                control.green_times[f"{signal}_p1"] = p1
                control.green_times[f"{signal}_p2"] = net.effective_green_total - p1
                evals += e
            for link in net.freeway_links:
                vsl, _, e = self._solve_freeway_agent(link, state, coupling, control, leader)
                control.vsl[link] = vsl
                evals += e
            new_coupling = self._coupling(state, control, demand)
            residual = max(
                (
                    abs(new_coupling[k] - coupling.get(k, 0.0)) / max(1.0, abs(coupling.get(k, 0.0)))
                    for k in new_coupling
                ),
                default=0.0,
            )
            coupling = new_coupling
            if residual < self.cfg.mpc.distributed_coupling_tol:
                converged = True
                break
        return control, iteration, converged, float(residual), evals

    # ---------- leader 평가 (WU-MATCHED-STACKELBERG) ----------

    def _leader_candidates(self, state: TrafficState) -> List[WuLeaderAction]:
        net = self.cfg.network
        n_p_now = state.protected_accumulation_veh(net)
        n_f_now = state.total_freeway_vehicles(net)
        # 후보 밴드: 현재 누적과 임계 부근 — 평가 전 고정(결과 보고 후 재조정 금지).
        p_values = [0.8 * max(n_p_now, 50.0), max(n_p_now, 50.0), self.cfg.leader.N_P_crit_veh]
        f_values = [0.8 * max(n_f_now, 50.0), max(n_f_now, 50.0), 1.2 * max(n_f_now, 50.0)]
        return [WuLeaderAction(float(p), float(f)) for p in p_values for f in f_values]

    def _system_objective(self, states: List[TrafficState]) -> float:
        """spec 16.8형 system objective(공통 비교 비용) — n_P+n_F+초과 패널티."""
        net = self.cfg.network
        lc = self.cfg.leader
        total = 0.0
        for s in states:
            n_p = s.total_urban_vehicles(net)
            n_f = s.total_freeway_vehicles(net)
            total += n_p + n_f
            total += lc.w_P * max(0.0, s.protected_accumulation_veh(net) - lc.N_P_crit_veh)
            total += lc.w_F * sum(
                net.freeway_segment_length_km * net.freeway_lanes * max(0.0, rho - net.rho_crit)
                for values in s.freeway_density.values()
                for rho in values
            )
        return float(total)

    def decide_with_info(
        self,
        state: TrafficState,
        demand_forecast: Iterable[DemandStep],
        previous_control: Optional[ControlAction] = None,
    ) -> WuDecisionInfo:
        from src.simulation.coupling import run_coupled_interval

        start = time.perf_counter()
        forecast = list(demand_forecast)
        previous = previous_control or self.previous_control or _wu_fixed_control(self.cfg)
        total_evals = 0

        if not self.leader_enabled:
            control, iters, converged, residual, evals = self._solve_followers(
                state, forecast[0], previous, leader=None,
            )
            total_evals += evals
            info = WuDecisionInfo(
                control=control,
                iterations=iters,
                converged=converged,
                coupling_residual=residual,
                solver_evaluations=total_evals,
                computation_time_sec=time.perf_counter() - start,
            )
            self.previous_control = control
            return info

        # WU-MATCHED-STACKELBERG: 후보별 follower 응답 → coupled 예측 → system objective.
        best: tuple[float, ControlAction, WuLeaderAction, int, bool, float] | None = None
        candidates = self._leader_candidates(state)
        for action in candidates:
            control, iters, converged, residual, evals = self._solve_followers(
                state, forecast[0], previous, leader=action,
            )
            total_evals += evals
            sim_state = state.copy()
            states: List[TrafficState] = []
            for demand in forecast[: self.cfg.mpc.horizon_steps]:
                run_coupled_interval(sim_state, control, demand, self.cfg)
                sim_state.time_sec += self.cfg.simulation.control_interval
                states.append(sim_state.copy())
            obj = self._system_objective(states)
            total_evals += len(states)
            if best is None or obj < best[0]:
                best = (obj, control, action, iters, converged, residual)
        assert best is not None
        obj, control, action, iters, converged, residual = best
        info = WuDecisionInfo(
            control=control,
            iterations=iters,
            converged=converged,
            coupling_residual=residual,
            solver_evaluations=total_evals,
            computation_time_sec=time.perf_counter() - start,
            leader_candidates=len(candidates),
            leader_selected=action,
            leader_objective=obj,
        )
        self.previous_control = control
        return info
