"""
Freeway follower for the Stackelberg controller.

Decision variables:
  - ramp metering rates b1..b4 for R1..R4, solved by SLSQP
  - advisory VSL per freeway, solved by enumeration over the discrete VSL set
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


@dataclass
class FreewayFollowerResponse:
    metering_by_ramp: Dict[str, float]
    vsl_by_freeway: Dict[str, float]
    total_metering_flow: float
    objective_value: float
    optimization_success: bool
    optimization_message: str
    preview_freeway_tts: float = 0.0
    solver_objective_value: float = 0.0


class FreewayFollower:
    def __init__(self, params, stackelberg_params):
        self.p = params
        self.sp = stackelberg_params
        self.last_vsl = {}

    def _ramp_pressure(self, sim, ramp_name: str) -> float:
        ramp = sim.ramp_by_name[ramp_name]
        queue = sim.onramp_q.get(ramp_name, 0.0)
        feeder = "A->D" if ramp.urban_node == "D" else "C->F"
        try:
            queue += sim.urban.queue_metric(feeder)
        except Exception:
            pass
        return float(max(queue, 1.0))

    def _urban_ramp_arrival_projection(self, sim, ramp_name: str, urban_green_by_signal) -> float:
        if not urban_green_by_signal:
            return 0.0
        ramp = sim.ramp_by_name[ramp_name]
        approach = "A" if ramp.urban_node == "D" else "C"
        feeder = f"{approach}->{ramp.urban_node}"
        try:
            feeder_pressure = sim.urban.queue_metric(feeder)
        except Exception:
            feeder_pressure = 0.0
        try:
            from network import TURNING
            ramp_share = TURNING[(ramp.urban_node, approach)].get(f"to_{ramp_name}", 0.0)
        except Exception:
            ramp_share = 0.0
        green = float(urban_green_by_signal.get(ramp.urban_node, 0.5))
        sat_veh = self.p.urban.Q_sat * self.p.time.Tc / 3600.0 * green
        return float(min(feeder_pressure, sat_veh) * ramp_share)

    def _green_aware_ramp_pressure(self, sim, ramp_name: str, urban_green_by_signal) -> float:
        return float(max(
            self._ramp_pressure(sim, ramp_name)
            + self._urban_ramp_arrival_projection(sim, ramp_name, urban_green_by_signal),
            1.0,
        ))

    def _rho_crit_from_vsl(self, vsl: float) -> float:
        vf = max(self.p.metanet.v_free, 1.0)
        ratio = np.clip(vf / max(vsl, 1.0), 1.0, self.sp.rho_crit_vsl_gain_cap)
        return float(np.clip(
            self.p.metanet.rho_crit * ratio,
            self.p.metanet.rho_crit,
            self.p.metanet.rho_max * self.sp.rho_crit_max_ratio,
        ))

    def _initial_metering(
        self,
        sim,
        ramp_order,
        capacities,
        total_metering_target,
        urban_green_by_signal=None,
    ):
        pressures = np.array([
            self._green_aware_ramp_pressure(sim, r, urban_green_by_signal)
            for r in ramp_order
        ], dtype=float)
        weights = pressures / max(np.sum(pressures), 1e-9)
        b0 = (weights * total_metering_target) / np.maximum(capacities, 1e-9)
        return np.clip(b0, self.sp.b_min, self.sp.b_max)

    def _objective(
        self,
        sim,
        ramp_order,
        capacities,
        vsl_by_freeway,
        b,
        target_rho_crit_by_freeway: Optional[Dict[str, float]] = None,
        urban_green_by_signal=None,
    ):
        Tc_h = self.p.time.Tc / 3600.0
        release_flow = b * capacities
        target_rho_crit_by_freeway = target_rho_crit_by_freeway or {}

        ramp_queue_cost = 0.0
        for i, ramp_name in enumerate(ramp_order):
            pressure = self._green_aware_ramp_pressure(
                sim,
                ramp_name,
                urban_green_by_signal,
            )
            predicted_queue = max(0.0, pressure - release_flow[i] * Tc_h)
            ramp_queue_cost += predicted_queue

        density_cost = 0.0
        freeway_tts_proxy = 0.0
        for fw_name, fs in sim.fw.items():
            fw_ramps = [
                idx for idx, ramp_name in enumerate(ramp_order)
                if sim.ramp_by_name[ramp_name].freeway == fw_name
            ]
            merge_flow = float(np.sum(release_flow[fw_ramps])) if fw_ramps else 0.0
            lane_km = max(fs.n * fs.L * fs.lanes, 1e-9)
            rho_pred = float(np.mean(fs.rho) + merge_flow * Tc_h / lane_km)
            rho_star = target_rho_crit_by_freeway.get(
                fw_name,
                self.p.metanet.rho_crit,
            )
            density_cost += max(0.0, rho_pred - rho_star) ** 2
            freeway_tts_proxy += float(np.sum(fs.rho) * fs.L * fs.lanes)

        smooth_cost = 0.0
        for fw_name, vsl in vsl_by_freeway.items():
            prev = self.last_vsl.get(fw_name, max(self.sp.vsl_values))
            smooth_cost += (vsl - prev) ** 2

        return (
            self.sp.freeway_tts_weight * freeway_tts_proxy * Tc_h
            + self.sp.ramp_queue_weight * ramp_queue_cost
            + self.sp.freeway_density_weight * density_cost
            + self.sp.vsl_smooth_weight * smooth_cost
        )

    def _preview_cost(
        self,
        sim,
        ramp_order,
        capacities,
        vsl_by_freeway,
        b,
        urban_green_by_signal=None,
    ):
        """Evaluate a candidate with the same dynamics used by the plant."""
        trial = copy.deepcopy(sim)
        trial.tts_freeway = 0.0
        trial.tts_urban = 0.0

        if urban_green_by_signal:
            from mpc import apply_control
            u = np.array([
                urban_green_by_signal.get("A", 0.5),
                urban_green_by_signal.get("C", 0.5),
                urban_green_by_signal.get("D", 0.5),
                urban_green_by_signal.get("F", 0.5),
                b[0], b[1], b[2], b[3],
                vsl_by_freeway.get("FW_W", self.p.mpc.vsl_max),
                vsl_by_freeway.get("FW_E", self.p.mpc.vsl_max),
            ], dtype=float)
            apply_control(trial, u)
        else:
            for i, ramp_name in enumerate(ramp_order):
                trial.set_metering(ramp_name, b[i])
            for fw_name, vsl in vsl_by_freeway.items():
                if fw_name in trial.fw:
                    trial.fw[fw_name].speed_limit = float(vsl)

        steps = max(1, int(self.sp.freeway_preview_control_steps))
        for _ in range(steps * self.p.time.K_cf):
            trial.step_freeway_period()

        smooth_cost = 0.0
        for fw_name, vsl in vsl_by_freeway.items():
            prev = self.last_vsl.get(fw_name, self.p.mpc.vsl_max)
            smooth_cost += (vsl - prev) ** 2

        ramp_queue_cost = sum(trial.onramp_q.get(ramp_name, 0.0) for ramp_name in ramp_order)
        return (
            self.sp.freeway_tts_weight * trial.tts_freeway
            + self.sp.ramp_queue_weight * ramp_queue_cost
            + self.sp.vsl_smooth_weight * smooth_cost
        ), trial.tts_freeway

    def _optimize_for_vsl(
        self,
        sim,
        ramp_order,
        capacities,
        target,
        vsl_by_freeway,
        target_rho_crit_by_freeway: Optional[Dict[str, float]] = None,
        urban_green_by_signal=None,
    ):
        from scipy.optimize import minimize

        eps = self.sp.freeway_metering_epsilon
        bounds = [(self.sp.b_min, self.sp.b_max) for _ in ramp_order]
        b0 = self._initial_metering(
            sim,
            ramp_order,
            capacities,
            target,
            urban_green_by_signal,
        )

        constraints = [
            {
                "type": "ineq",
                "fun": lambda b: eps - abs(float(np.dot(b, capacities)) - target),
            }
        ]

        def obj(b):
            tracking = self.sp.freeway_target_soft_weight * (
                float(np.dot(b, capacities)) - target
            ) ** 2
            return (
                self._objective(
                    sim,
                    ramp_order,
                    capacities,
                    vsl_by_freeway,
                    b,
                    target_rho_crit_by_freeway,
                    urban_green_by_signal,
                )
                + tracking
            )

        res = minimize(
            obj,
            b0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={
                "maxiter": self.sp.freeway_opt_maxiter,
                "ftol": self.sp.freeway_opt_ftol,
                "disp": False,
            },
        )
        if not res.success:
            # Keep a feasible, bounded fallback; the soft tracking term still
            # gives a defensible response when the hard target is infeasible.
            res2 = minimize(
                obj,
                b0,
                method="SLSQP",
                bounds=bounds,
                options={
                    "maxiter": self.sp.freeway_opt_maxiter,
                    "ftol": self.sp.freeway_opt_ftol,
                    "disp": False,
                },
            )
            if res2.fun < res.fun or not np.isfinite(res.fun):
                res = res2
        b = np.clip(res.x, self.sp.b_min, self.sp.b_max)
        solver_value = float(obj(b))
        preview_value, preview_freeway_tts = self._preview_cost(
            sim,
            ramp_order,
            capacities,
            vsl_by_freeway,
            b,
            urban_green_by_signal,
        )
        return (
            b,
            float(preview_value),
            bool(res.success),
            str(res.message),
            solver_value,
            float(preview_freeway_tts),
        )

    def respond(
        self,
        sim,
        total_metering_target: float,
        target_rho_crit_by_freeway: Optional[Dict[str, float]] = None,
        urban_green_by_signal=None,
    ) -> FreewayFollowerResponse:
        ramp_order: List[str] = ["R1", "R2", "R3", "R4"]
        capacities = {r.name: r.Q_cap for r in sim.net.ramps}
        cap_vec = np.array([capacities[r] for r in ramp_order], dtype=float)
        feasible_min = self.sp.b_min * float(np.sum(cap_vec))
        feasible_max = self.sp.b_max * float(np.sum(cap_vec))
        target = float(np.clip(total_metering_target, feasible_min, feasible_max))

        fw_names = list(sim.fw)
        base_vsl = {fw: float(self.p.mpc.vsl_max) for fw in fw_names}
        b, value, success, message, solver_value, preview_freeway_tts = self._optimize_for_vsl(
            sim,
            ramp_order,
            cap_vec,
            target,
            base_vsl,
            target_rho_crit_by_freeway,
            urban_green_by_signal,
        )
        best = (
            b,
            value,
            success,
            message,
            base_vsl,
            solver_value,
            preview_freeway_tts,
        )

        vsl_candidates = []
        for fw in fw_names:
            for vsl in self.sp.vsl_values:
                if vsl >= self.p.mpc.vsl_max:
                    continue
                candidate = dict(base_vsl)
                candidate[fw] = float(vsl)
                vsl_candidates.append(candidate)
        if self.last_vsl:
            previous = {
                fw: float(self.last_vsl.get(fw, self.p.mpc.vsl_max))
                for fw in fw_names
            }
            vsl_candidates.append(previous)

        seen = {tuple(sorted(base_vsl.items()))}
        for vsl_by_freeway in vsl_candidates:
            key = tuple(sorted(vsl_by_freeway.items()))
            if key in seen:
                continue
            seen.add(key)
            (
                candidate_b,
                value,
                candidate_success,
                candidate_message,
                candidate_solver_value,
                preview_freeway_tts,
            ) = self._optimize_for_vsl(
                sim,
                ramp_order,
                cap_vec,
                target,
                vsl_by_freeway,
                target_rho_crit_by_freeway,
                urban_green_by_signal,
            )
            if best is None or value < best[1]:
                best = (
                    candidate_b,
                    value,
                    candidate_success,
                    candidate_message,
                    vsl_by_freeway,
                    candidate_solver_value,
                    preview_freeway_tts,
                )

        metering, value, success, message, vsl_by_freeway, solver_value, preview_freeway_tts = best
        realized = metering * cap_vec
        self.last_vsl = dict(vsl_by_freeway)

        return FreewayFollowerResponse(
            metering_by_ramp={r: float(metering[i]) for i, r in enumerate(ramp_order)},
            vsl_by_freeway=vsl_by_freeway,
            total_metering_flow=float(np.sum(realized)),
            objective_value=value,
            optimization_success=success,
            optimization_message=message,
            preview_freeway_tts=preview_freeway_tts,
            solver_objective_value=solver_value,
        )
