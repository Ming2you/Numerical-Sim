"""
Urban follower for the Stackelberg controller.

This follower chooses the four signal green fractions [g_A, g_C, g_D, g_F]
by solving a constrained SLSQP problem. A nonnegative slack variable is included
so infeasible leader targets are penalized instead of crashing the controller.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


@dataclass
class UrbanFollowerResponse:
    green_by_signal: Dict[str, float]
    estimated_net_inflow: float
    slack: float
    objective_value: float
    optimization_success: bool
    optimization_message: str


class UrbanFollower:
    def __init__(self, params, stackelberg_params):
        self.p = params
        self.sp = stackelberg_params
        self.last_green = {"A": 0.5, "C": 0.5, "D": 0.5, "F": 0.5}

    def _approach_pressure(self, sim, approach: str, inter: str) -> float:
        link = f"{approach}->{inter}"
        pressure = 0.0
        if link in sim.urban.pipe:
            pressure += sim.urban.queue_metric(link)
        for (node, appr, _turn), q in sim.urban.x.items():
            if node == inter and appr == approach:
                pressure += q
        return float(max(pressure, 0.0))

    def _base_green(self, sim, inter: str, phase1_approaches, phase2_approaches) -> float:
        p1 = sum(self._approach_pressure(sim, a, inter) for a in phase1_approaches)
        p2 = sum(self._approach_pressure(sim, a, inter) for a in phase2_approaches)
        if p1 + p2 <= 1e-9:
            return 0.5
        return float(np.clip(p1 / (p1 + p2), self.sp.g_min, self.sp.g_max))

    def _estimate_net_inflow(self, greens: Dict[str, float]) -> float:
        # Positive value means net flow admitted into the protected urban area.
        # The current aggregate approximation treats higher phase-1 service at
        # vertical boundary-heavy intersections as admitting more flow, and
        # phase-2 as serving horizontal boundary exits.
        sat = self.p.urban.Q_sat
        return float(sat * (
            (greens["A"] - 0.5)
            + (greens["C"] - 0.5)
            + 0.5 * (greens["D"] - 0.5)
            + 0.5 * (greens["F"] - 0.5)
        ))

    def _phase_pressures(self, sim):
        return {
            "A": (
                sum(self._approach_pressure(sim, a, "A") for a in ["NA", "D"]),
                sum(self._approach_pressure(sim, a, "A") for a in ["O1", "B"]),
            ),
            "C": (
                sum(self._approach_pressure(sim, a, "C") for a in ["NC", "F"]),
                sum(self._approach_pressure(sim, a, "C") for a in ["B", "O2"]),
            ),
            "D": (
                self._approach_pressure(sim, "A", "D"),
                sum(self._approach_pressure(sim, a, "D") for a in ["O3", "E"]),
            ),
            "F": (
                self._approach_pressure(sim, "C", "F"),
                sum(self._approach_pressure(sim, a, "F") for a in ["O4", "E"]),
            ),
        }

    def _freeway_restriction_by_node(self, freeway_response):
        if freeway_response is None:
            return {"D": 0.0, "F": 0.0}

        metering = getattr(freeway_response, "metering_by_ramp", {}) or {}
        vsl = getattr(freeway_response, "vsl_by_freeway", {}) or {}
        ramp_to_fw = {"R1": "FW_W", "R2": "FW_W", "R3": "FW_E", "R4": "FW_E"}
        ramp_groups = {"D": ["R2", "R3"], "F": ["R1", "R4"]}
        restrictions = {}
        for node, ramps in ramp_groups.items():
            b_vals = [float(metering.get(r, 1.0)) for r in ramps]
            v_vals = [
                float(vsl.get(ramp_to_fw[r], self.p.mpc.vsl_max)) / max(self.p.mpc.vsl_max, 1.0)
                for r in ramps
            ]
            ramp_restriction = 1.0 - float(np.mean(b_vals))
            vsl_restriction = 1.0 - float(np.mean(v_vals))
            restrictions[node] = (
                self.sp.urban_ramp_restriction_weight * max(0.0, ramp_restriction)
                + self.sp.urban_vsl_restriction_weight * max(0.0, vsl_restriction)
            )
        return restrictions

    def _freeway_feedback_cost(self, greens, pressures, freeway_response):
        restrictions = self._freeway_restriction_by_node(freeway_response)
        cost = 0.0
        for node in ("D", "F"):
            p1, p2 = pressures[node]
            scale = max(p1 + p2, 1.0)
            phase1_service_share = greens[node] * max(p1, 1.0) / scale
            cost += restrictions[node] * phase1_service_share ** 2
        return cost

    def _objective(self, x, pressures, freeway_response=None):
        greens = {"A": x[0], "C": x[1], "D": x[2], "F": x[3]}
        slack = x[4]
        sat = self.p.urban.Q_sat * self.p.time.Tc / 3600.0
        balance = 0.0
        for node, (p1, p2) in pressures.items():
            scale = max(p1 + p2, 1.0)
            q1_after = max(0.0, p1 - greens[node] * sat)
            q2_after = max(0.0, p2 - (1.0 - greens[node]) * sat)
            balance += (q1_after / scale) ** 2 + (q2_after / scale) ** 2
        smooth = sum((greens[k] - self.last_green[k]) ** 2 for k in greens)
        return (
            self.sp.urban_balance_weight * balance
            + self.sp.green_smooth_weight * smooth
            + self.sp.urban_slack_weight * slack ** 2
            + self._freeway_feedback_cost(greens, pressures, freeway_response)
        )

    def respond(
        self,
        sim,
        protected_net_inflow_target: float,
        freeway_response=None,
    ) -> UrbanFollowerResponse:
        from scipy.optimize import minimize

        pressures = self._phase_pressures(sim)
        base = {
            "A": self._base_green(sim, "A", ["NA", "D"], ["O1", "B"]),
            "C": self._base_green(sim, "C", ["NC", "F"], ["B", "O2"]),
            "D": self._base_green(sim, "D", ["A"], ["O3", "E"]),
            "F": self._base_green(sim, "F", ["C"], ["O4", "E"]),
        }
        x0 = np.array([base["A"], base["C"], base["D"], base["F"], 0.0], dtype=float)
        bounds = [
            (self.sp.g_min, self.sp.g_max),
            (self.sp.g_min, self.sp.g_max),
            (self.sp.g_min, self.sp.g_max),
            (self.sp.g_min, self.sp.g_max),
            (0.0, self.sp.urban_slack_max),
        ]

        def net_from_x(x):
            return self._estimate_net_inflow({"A": x[0], "C": x[1], "D": x[2], "F": x[3]})

        eps = self.sp.urban_net_inflow_epsilon
        constraints = [
            {
                "type": "ineq",
                "fun": lambda x: eps + x[4] - abs(net_from_x(x) - protected_net_inflow_target),
            }
        ]

        res = minimize(
            lambda x: self._objective(x, pressures, freeway_response),
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={
                "maxiter": self.sp.urban_opt_maxiter,
                "ftol": self.sp.urban_opt_ftol,
                "disp": False,
            },
        )
        if not res.success:
            res2 = minimize(
                lambda x: self._objective(x, pressures, freeway_response),
                x0,
                method="SLSQP",
                bounds=bounds,
                options={
                    "maxiter": self.sp.urban_opt_maxiter,
                    "ftol": self.sp.urban_opt_ftol,
                    "disp": False,
                },
            )
            if res2.fun < res.fun or not np.isfinite(res.fun):
                res = res2

        x = np.array(res.x, dtype=float)
        greens = {
            "A": float(np.clip(x[0], self.sp.g_min, self.sp.g_max)),
            "C": float(np.clip(x[1], self.sp.g_min, self.sp.g_max)),
            "D": float(np.clip(x[2], self.sp.g_min, self.sp.g_max)),
            "F": float(np.clip(x[3], self.sp.g_min, self.sp.g_max)),
        }
        self.last_green = dict(greens)

        return UrbanFollowerResponse(
            green_by_signal=greens,
            estimated_net_inflow=self._estimate_net_inflow(greens),
            slack=float(max(x[4], 0.0)),
            objective_value=float(self._objective(x, pressures, freeway_response)),
            optimization_success=bool(res.success),
            optimization_message=str(res.message),
        )
