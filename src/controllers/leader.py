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
        nuf_values = np.linspace(leader.N_UF_star_range[0], leader.N_UF_star_range[1], n_nuf)
        out = [LeaderAction(float(np_), float(nuf)) for np_ in np_values for nuf in nuf_values]
        if previous is not None:
            out.append(LeaderAction(previous.N_P_star, previous.N_UF_star))
        return out[:count + 1]

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
        density_weight = lc.w_F if lc.objective_mode != "follower_ttt" else 0.05 * lc.w_F
        for s in states:
            n_p = s.total_urban_vehicles()
            target_penalty += lc.w_P * max(0.0, n_p - action.N_P_star)
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
