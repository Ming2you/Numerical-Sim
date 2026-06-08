"""
Leader layer for the Stackelberg controller.

The leader chooses two aggregate targets from the user's formulation:
  - N_P*: protected-network net inflow target
  - N_UF*: total metering flow from urban roads to freeway ramps

The adaptive critical targets are implemented as stochastic-approximation style
updates. They are intentionally local to this controller so the existing
Numerical Sim plant files remain unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np


@dataclass
class CriticalTargetState:
    n_crit: Optional[float] = None
    production_prev: Optional[float] = None
    accumulation_prev: Optional[float] = None
    rho_crit_by_freeway: Dict[str, float] = None

    def __post_init__(self):
        if self.rho_crit_by_freeway is None:
            self.rho_crit_by_freeway = {}


@dataclass
class LeaderTargets:
    protected_net_inflow: float
    total_metering: float
    n_crit: float
    rho_crit_by_freeway: Dict[str, float]


class StackelbergLeader:
    """Computes leader targets and maintains adaptive critical values."""

    def __init__(self, params, stackelberg_params):
        self.p = params
        self.sp = stackelberg_params
        self.state = CriticalTargetState()

    def accumulation(self, sim) -> float:
        """Protected urban accumulation proxy, in vehicles."""
        return sim.urban.vehicles_on_links() + sim.urban.total_queue()

    def production(self, sim) -> float:
        """Urban production proxy, veh*km/h from link occupancies and v_avg."""
        total = 0.0
        for name, link in sim.net.urban_links.items():
            occ = sim.urban.link_occupancy(name)
            total += occ * link.v_avg
        return float(total)

    def update_n_crit(self, sim) -> float:
        """Update protected-network critical accumulation.

        This follows the stochastic-approximation idea used in MFD critical
        accumulation estimation: move the estimate in the observed direction of
        increasing production, using a bounded noisy-gradient step.
        """
        n = self.accumulation(sim)
        prod = self.production(sim)
        if self.state.n_crit is None:
            storage = sum(sim.urban.storage.values())
            self.state.n_crit = self.sp.n_crit_init_ratio * storage
            self.state.accumulation_prev = n
            self.state.production_prev = prod
            return float(self.state.n_crit)

        dn = n - self.state.accumulation_prev
        dp = prod - self.state.production_prev
        if abs(dn) > self.sp.sa_eps:
            grad = dp / dn
            storage = max(sum(sim.urban.storage.values()), 1.0)
            step = self.sp.n_crit_step * storage * np.tanh(grad / self.sp.production_grad_scale)
            lo = self.sp.n_crit_min_ratio * storage
            hi = self.sp.n_crit_max_ratio * storage
            self.state.n_crit = float(np.clip(self.state.n_crit + step, lo, hi))

        self.state.accumulation_prev = n
        self.state.production_prev = prod
        return float(self.state.n_crit)

    def update_rho_crit(self, sim, vsl_by_freeway: Dict[str, float]) -> Dict[str, float]:
        """Update freeway critical densities implied by VSL decisions.

        By default the plant applies VSL as a speed cap only, so the leader must
        not count an unmodeled critical-density benefit. If the experimental
        apply_rho_crit_to_plant flag is enabled, a bounded VSL-to-rho_crit
        approximation is used for target generation.
        """
        out = {}
        base = self.p.metanet.rho_crit
        if not getattr(self.sp, "apply_rho_crit_to_plant", False):
            for name in sim.fw:
                self.state.rho_crit_by_freeway[name] = float(base)
                out[name] = float(base)
            return out

        vf = max(self.p.metanet.v_free, 1.0)
        for name in sim.fw:
            vsl = vsl_by_freeway.get(name, vf)
            ratio = np.clip(vf / max(vsl, 1.0), 1.0, self.sp.rho_crit_vsl_gain_cap)
            rho_star = base * ratio
            rho_star = float(np.clip(rho_star, base, self.p.metanet.rho_max * self.sp.rho_crit_max_ratio))
            prev = self.state.rho_crit_by_freeway.get(name, rho_star)
            smoothed = (
                self.sp.rho_crit_smoothing * prev
                + (1.0 - self.sp.rho_crit_smoothing) * rho_star
            )
            self.state.rho_crit_by_freeway[name] = float(smoothed)
            out[name] = float(smoothed)
        return out

    def choose_targets(self, sim, vsl_by_freeway: Optional[Dict[str, float]] = None) -> LeaderTargets:
        vsl_by_freeway = vsl_by_freeway or {}
        n_crit = self.update_n_crit(sim)
        rho_crit = self.update_rho_crit(sim, vsl_by_freeway)
        return self.targets_from_critical(sim, n_crit, rho_crit)

    def targets_from_critical(self, sim, n_crit: float, rho_crit: Dict[str, float]) -> LeaderTargets:
        """Convert candidate critical values into leader signals."""
        n_now = self.accumulation(sim)
        Tc_h = self.p.time.Tc / 3600.0
        protected_net = (n_crit - n_now) / max(Tc_h, 1e-9)
        protected_net = float(np.clip(
            protected_net,
            -self.sp.protected_net_inflow_cap,
            self.sp.protected_net_inflow_cap,
        ))

        ramp_capacity = sum(r.Q_cap for r in sim.net.ramps)
        avg_excess = np.mean([
            np.mean(fs.rho) - rho_crit.get(name, self.p.metanet.rho_crit)
            for name, fs in sim.fw.items()
        ])
        congestion_factor = 1.0 / (1.0 + np.exp(self.sp.freeway_density_gain * avg_excess))
        total_metering = ramp_capacity * (
            self.sp.metering_min_fraction
            + (self.sp.metering_max_fraction - self.sp.metering_min_fraction) * congestion_factor
        )
        total_metering = float(np.clip(total_metering, 0.0, ramp_capacity))

        return LeaderTargets(
            protected_net_inflow=protected_net,
            total_metering=total_metering,
            n_crit=n_crit,
            rho_crit_by_freeway=rho_crit,
        )

    def critical_candidates(self, sim, base: LeaderTargets):
        """Yield candidate critical values for response-aware leader search."""
        storage = max(sum(sim.urban.storage.values()), 1.0)
        n_lo = self.sp.n_crit_min_ratio * storage
        n_hi = self.sp.n_crit_max_ratio * storage
        rho_hi = self.p.metanet.rho_max * self.sp.rho_crit_max_ratio

        seen = set()
        for n_scale in self.sp.leader_n_crit_candidate_scales:
            n_crit = float(np.clip(base.n_crit * n_scale, n_lo, n_hi))
            for rho_scale in self.sp.leader_rho_crit_candidate_scales:
                rho_crit = {
                    name: float(np.clip(value * rho_scale, self.p.metanet.rho_crit, rho_hi))
                    for name, value in base.rho_crit_by_freeway.items()
                }
                key = (
                    round(n_crit, 6),
                    tuple(sorted((name, round(value, 6)) for name, value in rho_crit.items())),
                )
                if key in seen:
                    continue
                seen.add(key)
                yield self.targets_from_critical(sim, n_crit, rho_crit)
