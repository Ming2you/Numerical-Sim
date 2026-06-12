from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import estimate_onramp_green_release_flows


@dataclass(frozen=True)
class LeaderAction:
    N_P_star: float
    N_UF_star: float


class Leader:
    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg

    def candidates(
        self,
        state: TrafficState,
        previous: Optional[ControlAction] = None,
        demand: Optional[DemandStep] = None,
    ) -> List[LeaderAction]:
        leader = self.cfg.leader
        count = max(3, self.cfg.mpc.leader_candidate_count)
        n_np = max(2, int(round(np.sqrt(count))))
        n_nuf = max(2, int(np.ceil(count / n_np)))
        np_lower, np_upper = self._np_candidate_bounds(state)
        np_values = set(float(v) for v in np.linspace(np_lower, np_upper, n_np))
        np_values.add(float(np.clip(leader.N_P_crit_veh, np_lower, np_upper)))
        feasible_nuf = self._feasible_nuf_capacity(state, previous, demand)
        # 자유류(평균밀도 ≤ metering 활성화 임계)에서는 T_f 단위 feasible 추정이
        # metering을 강제하지 않도록 후보 상한을 ramp 총용량까지 열어둔다.
        # (feasible은 다음 T_f에 추적가능한 유량 추정이라 지속 수요를 과소평가 —
        # 이를 ceiling으로 쓰면 본선이 한가해도 w_r에 순수 대기손실이 쌓인다.)
        if self._density_ratio(state) <= leader.metering_activation_density_ratio:
            feasible_nuf = max(feasible_nuf, self.cfg.network.total_ramp_capacity)
        nuf_upper = min(leader.N_UF_star_range[1], feasible_nuf)
        nuf_upper = max(leader.N_UF_star_range[0], nuf_upper)
        nuf_values = set(float(v) for v in np.linspace(leader.N_UF_star_range[0], nuf_upper, n_nuf))
        heuristic_nuf = min(self._heuristic_nuf_target(state, previous, demand), nuf_upper)
        # Include local candidates around a congestion-aware target so the
        # leader can find meaningful metering even when the coarse grid is weak.
        for scale in (0.75, 1.0, 1.25):
            nuf_values.add(float(np.clip(
                heuristic_nuf * scale,
                leader.N_UF_star_range[0],
                nuf_upper,
            )))
        nuf_values = sorted(nuf_values)
        np_values = sorted(np_values)
        grid = [LeaderAction(float(np_), float(nuf)) for np_ in np_values for nuf in nuf_values]
        required = [
            LeaderAction(np_values[0], nuf_values[0]),
            LeaderAction(np_values[0], nuf_values[-1]),
            LeaderAction(np_values[-1], nuf_values[0]),
            LeaderAction(np_values[-1], nuf_values[-1]),
            LeaderAction(
                float(np.clip(leader.N_P_crit_veh, np_lower, np_upper)),
                float(min(nuf_values, key=lambda value: abs(value - heuristic_nuf))),
            ),
        ]
        if previous is not None:
            required.append(LeaderAction(
                float(np.clip(previous.N_P_star, np_lower, np_upper)),
                float(np.clip(previous.N_UF_star, nuf_values[0], nuf_values[-1])),
            ))
        # 단순 Cartesian 앞부분 절단은 낮은 N_P 후보만 남긴다. 필수 corner/직전
        # action을 먼저 보존하고, 남은 budget은 정규화된 (N_P,N_UF) 공간의
        # farthest-point 순서로 채워 전체 후보 영역을 균형 있게 덮는다.
        budget = min(len(grid), count + 1)
        selected: List[LeaderAction] = []

        def add_unique(action: LeaderAction) -> None:
            if action not in selected and len(selected) < budget:
                selected.append(action)

        for action in required:
            add_unique(action)

        np_span = max(np_values[-1] - np_values[0], 1.0e-9)
        nuf_span = max(nuf_values[-1] - nuf_values[0], 1.0e-9)
        while len(selected) < budget:
            remaining = [action for action in grid if action not in selected]
            if not remaining:
                break

            def coverage_distance(action: LeaderAction) -> tuple[float, float, float]:
                if not selected:
                    return (float("inf"), action.N_P_star, action.N_UF_star)
                min_distance = min(
                    ((action.N_P_star - other.N_P_star) / np_span) ** 2
                    + ((action.N_UF_star - other.N_UF_star) / nuf_span) ** 2
                    for other in selected
                )
                return (float(min_distance), action.N_P_star, action.N_UF_star)

            add_unique(max(remaining, key=coverage_distance))
        return selected

    def _np_candidate_bounds(self, state: TrafficState) -> tuple[float, float]:
        """Calibration된 n_P_crit 주변으로 leader의 도시 누적 목표 후보를 제한한다."""
        leader = self.cfg.leader
        crit = float(leader.N_P_crit_veh)
        lower = crit * float(leader.N_P_candidate_lower_factor)
        upper = crit * float(leader.N_P_candidate_upper_factor)
        if state.protected_accumulation_veh(self.cfg.network) >= crit:
            upper = crit
        lower = max(0.0, min(lower, upper))
        return float(lower), float(upper)

    def _ramp_merge_index(self, ramp: str, n_segments: int) -> int:
        configured = getattr(self.cfg.network, "ramp_merge_segment_index", {})
        if isinstance(configured, dict) and ramp in configured:
            return int(np.clip(float(configured[ramp]), 0.0, float(n_segments - 1)))
        return n_segments // 2

    def _feasible_nuf_capacity(
        self,
        state: TrafficState,
        previous: Optional[ControlAction] = None,
        demand: Optional[DemandStep] = None,
    ) -> float:
        """현재 경계 상태에서 첫 T_f 동안 추적 가능한 ramp 유입 상한(veh/h)을 계산한다."""
        net = self.cfg.network
        sim = self.cfg.simulation
        control = previous or ControlAction.fixed(self.cfg)
        if demand is not None:
            green_inflow = estimate_onramp_green_release_flows(
                state.copy(),
                control,
                demand,
                self.cfg,
                interval_h=sim.T_f_h,
            )
            cap_factor = getattr(demand, "incident_capacity_factor", 1.0)
        else:
            green_inflow = {ramp: 0.0 for ramp in net.ramps}
            cap_factor = 1.0
        q_cap = net.freeway_capacity_veh_h * cap_factor
        feasible = 0.0
        for ramp in net.ramps:
            link = net.ramp_to_freeway[ramp]
            merge_idx = self._ramp_merge_index(ramp, len(state.freeway_density[link]))
            rho_merge = state.freeway_density[link][merge_idx]
            receiving_factor = float(np.clip(
                (net.rho_max - rho_merge) / max(net.rho_max - net.rho_crit, 1.0e-9),
                0.0,
                1.0,
            ))
            density_headroom = max(0.0, net.rho_crit - rho_merge)
            headroom_flow = (
                density_headroom
                * net.freeway_segment_length_km
                * net.freeway_lanes
                / max(sim.T_f_h, 1.0e-9)
            )
            available = (
                state.ramp_queue.get(ramp, 0.0) / max(sim.T_f_h, 1.0e-9)
                + green_inflow.get(ramp, 0.0)
            )
            feasible += min(
                net.ramp_capacity_veh_h[ramp],
                max(0.0, available),
                q_cap * receiving_factor,
                max(0.0, headroom_flow),
            )
        return float(max(0.0, feasible * self.cfg.leader.N_UF_feasible_margin))

    def _heuristic_nuf_target(
        self,
        state: TrafficState,
        previous: Optional[ControlAction] = None,
        demand: Optional[DemandStep] = None,
    ) -> float:
        net = self.cfg.network
        lc = self.cfg.leader
        density_ratio = self._density_ratio(state)
        queue_pressure = self._ramp_queue_pressure(state)
        feasible = self._feasible_nuf_capacity(state, previous, demand)
        if density_ratio <= lc.metering_activation_density_ratio:
            frac = 1.0
        else:
            congestion = min(1.0, max(0.0, density_ratio - lc.metering_activation_density_ratio))
            frac = 1.0 - 0.18 * congestion + 0.25 * queue_pressure
        frac = float(np.clip(frac, 0.82, 1.0))
        return min(frac * net.total_ramp_capacity, feasible)

    def _density_ratio(self, state: TrafficState) -> float:
        values = [
            rho / max(self.cfg.network.rho_crit, 1.0e-9)
            for rhos in state.freeway_density.values()
            for rho in rhos
        ]
        return float(np.mean(values)) if values else 0.0

    def _ramp_queue_pressure(self, state: TrafficState) -> float:
        if not state.ramp_queue:
            return 0.0
        return float(np.mean([
            min(1.0, q / max(self.cfg.network.ramp_queue_max_veh, 1.0e-9))
            for q in state.ramp_queue.values()
        ]))

    def objective(
        self,
        predicted_states: Iterable[TrafficState],
        action: ControlAction,
        previous: Optional[ControlAction],
        follower_objective: float,
        nash_converged: bool,
    ) -> float:
        net = self.cfg.network
        lc = self.cfg.leader
        states = list(predicted_states)
        if lc.objective_mode == "follower_ttt":
            base = follower_objective
        else:
            base = sum(s.total_freeway_vehicles(net) + s.total_urban_vehicles(net) for s in states)
        target_penalty = 0.0
        density_penalty = 0.0
        for s in states:
            n_p = s.protected_accumulation_veh(net)
            target_penalty += lc.w_P * max(0.0, n_p - lc.N_P_crit_veh)
            density_penalty += lc.w_F * sum(
                net.freeway_segment_length_km * net.freeway_lanes * max(0.0, rho - net.rho_crit)
                for values in s.freeway_density.values()
                for rho in values
            )
        smooth = 0.0
        if previous is not None:
            smooth = lc.w_L * (
                abs(action.N_P_star - previous.N_P_star)
                + abs(action.N_UF_star - previous.N_UF_star)
            )
        conv = 0.0 if nash_converged else lc.non_convergence_penalty
        return float(base + target_penalty + density_penalty + smooth + conv)


def leader_metadata(actions: Iterable[LeaderAction]) -> Dict[str, float]:
    actions = list(actions)
    return {
        "leader_candidate_count": float(len(actions)),
        "N_P_min": min((a.N_P_star for a in actions), default=0.0),
        "N_P_max": max((a.N_P_star for a in actions), default=0.0),
        "N_UF_min": min((a.N_UF_star for a in actions), default=0.0),
        "N_UF_max": max((a.N_UF_star for a in actions), default=0.0),
    }
