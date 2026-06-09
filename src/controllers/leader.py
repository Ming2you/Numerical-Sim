from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from src.models.state import ControlAction, ExperimentConfig, TrafficState


@dataclass(frozen=True)
class LeaderAction:
    N_P_star: float
    N_UF_star: float


class Leader:
    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg

    def candidates(self, state: TrafficState, previous: Optional[ControlAction] = None) -> List[LeaderAction]:
        leader = self.cfg.leader
        count = max(3, self.cfg.mpc.leader_candidate_count)
        n_np = max(2, int(round(np.sqrt(count))))
        n_nuf = max(2, int(np.ceil(count / n_np)))
        np_values = np.linspace(leader.N_P_star_range[0], leader.N_P_star_range[1], n_np)
        nuf_values = set(float(v) for v in np.linspace(leader.N_UF_star_range[0], leader.N_UF_star_range[1], n_nuf))
        heuristic_nuf = self._heuristic_nuf_target(state)
        # Include local candidates around a congestion-aware target so the
        # leader can find meaningful metering even when the coarse grid is weak.
        for scale in (0.75, 1.0, 1.25):
            nuf_values.add(float(np.clip(
                heuristic_nuf * scale,
                leader.N_UF_star_range[0],
                leader.N_UF_star_range[1],
            )))
        nuf_values = sorted(nuf_values)
        out = [LeaderAction(float(np_), float(nuf)) for np_ in np_values for nuf in nuf_values]
        if previous is not None:
            out.append(LeaderAction(previous.N_P_star, previous.N_UF_star))
        return out[:count + 1]

    def _heuristic_nuf_target(self, state: TrafficState) -> float:
        net = self.cfg.network
        lc = self.cfg.leader
        density_ratio = self._density_ratio(state)
        queue_pressure = self._ramp_queue_pressure(state)
        if density_ratio <= lc.metering_activation_density_ratio:
            frac = 1.0
        else:
            congestion = min(1.0, max(0.0, density_ratio - lc.metering_activation_density_ratio))
            frac = 1.0 - 0.18 * congestion + 0.25 * queue_pressure
        frac = float(np.clip(frac, 0.82, 1.0))
        return frac * net.total_ramp_capacity

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
        metering_penalty = 0.0
        density_weight = lc.w_F if lc.objective_mode != "follower_ttt" else 0.05 * lc.w_F
        for s in states:
            n_p = s.total_urban_vehicles()
            target_penalty += lc.w_P * max(0.0, n_p - action.N_P_star)
            density_ratio = self._density_ratio(s)
            queue_pressure = self._ramp_queue_pressure(s)
            recommended_nuf = self._heuristic_nuf_target(s)
            nuf_excess = max(0.0, action.N_UF_star - recommended_nuf)
            nuf_shortage = max(0.0, recommended_nuf - action.N_UF_star)
            congestion_term = max(0.0, density_ratio - lc.metering_activation_density_ratio)
            metering_penalty += lc.metering_congestion_weight * congestion_term * nuf_excess
            metering_penalty += lc.metering_queue_weight * queue_pressure * nuf_shortage
            density_penalty += density_weight * sum(
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
        return float(base + target_penalty + density_penalty + metering_penalty + smooth + conv)


def leader_metadata(actions: Iterable[LeaderAction]) -> Dict[str, float]:
    actions = list(actions)
    return {
        "leader_candidate_count": float(len(actions)),
        "N_P_min": min((a.N_P_star for a in actions), default=0.0),
        "N_P_max": max((a.N_P_star for a in actions), default=0.0),
        "N_UF_min": min((a.N_UF_star for a in actions), default=0.0),
        "N_UF_max": max((a.N_UF_star for a in actions), default=0.0),
    }
