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
        out = [LeaderAction(float(np_), float(nuf)) for np_ in np_values for nuf in nuf_values]
        if previous is not None:
            out.append(LeaderAction(
                float(np.clip(previous.N_P_star, np_lower, np_upper)),
                previous.N_UF_star,
            ))
        return out[:count + 1]

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
            base = sum(s.total_freeway_vehicles(net) + s.total_urban_vehicles() for s in states)
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
