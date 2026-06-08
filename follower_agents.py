"""
Distributed follower game for the Stackelberg controller.

Wu et al. (2022) decompose the lower-level integrated-control problem into
subproblems solved by local urban and freeway agents, then iterate local
best-responses toward a Nash equilibrium. This module maps that idea onto the
current simplified network:

  - urban agents: signalized intersections A, C, D, F
  - freeway agents: direction-level freeway links FW_W, FW_E

The current simulator does not expose the full MILP/SQP formulations used in
Wu et al., so each agent solves a bounded local candidate search with the same
control variables available to the plant. The local scores include TTS-like
vehicle-hour terms, smoothness, leader-target soft tracking, and neighbor
coupling through ramp queues/VSLs/green splits.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

import numpy as np

from follower_freeway import FreewayFollowerResponse
from follower_urban import UrbanFollowerResponse
from freeway import freeway_vehicles
from mpc import apply_control
from network import TURNING, turn_destination


SIGNAL_ORDER: Tuple[str, ...] = ("A", "C", "D", "F")
RAMP_ORDER: Tuple[str, ...] = ("R1", "R2", "R3", "R4")

PHASE_BY_APPROACH = {
    "A": {"NA": 1, "D": 1, "O1": 2, "B": 2},
    "C": {"NC": 1, "F": 1, "B": 2, "O2": 2},
    "D": {"A": 1, "O3": 2, "E": 2},
    "F": {"C": 1, "O4": 2, "E": 2},
}

PHASE_APPROACHES = {
    "A": (("NA", "D"), ("O1", "B")),
    "C": (("NC", "F"), ("B", "O2")),
    "D": (("A",), ("O3", "E")),
    "F": (("C",), ("O4", "E")),
}


@dataclass
class LocalDecision:
    agent: str
    objective_value: float
    payload: Dict[str, float]
    diagnostics: Dict[str, float]

    def as_log(self) -> Dict[str, object]:
        out: Dict[str, object] = {
            "agent": self.agent,
            "objective_value": float(self.objective_value),
        }
        out.update(self.payload)
        out.update(self.diagnostics)
        return out


class DistributedFollowerGame:
    """Iterative local best-response game for Stackelberg followers."""

    def __init__(self, params, stackelberg_params):
        self.p = params
        self.sp = stackelberg_params
        self.last_green = {node: 0.5 for node in SIGNAL_ORDER}
        self.last_metering = {ramp: 1.0 for ramp in RAMP_ORDER}
        self.last_vsl = {}

    # ------------------------------------------------------------------ urban
    def _approach_pressure(self, sim, approach: str, inter: str) -> float:
        link = f"{approach}->{inter}"
        pressure = 0.0
        if link in sim.urban.pipe:
            pressure += sim.urban.queue_metric(link)
        for (node, appr, _turn), q in sim.urban.x.items():
            if node == inter and appr == approach:
                pressure += q
        return float(max(pressure, 0.0))

    def _phase_pressures(self, sim) -> Dict[str, Tuple[float, float]]:
        out: Dict[str, Tuple[float, float]] = {}
        for node, (phase1, phase2) in PHASE_APPROACHES.items():
            p1 = sum(self._approach_pressure(sim, appr, node) for appr in phase1)
            p2 = sum(self._approach_pressure(sim, appr, node) for appr in phase2)
            out[node] = (float(p1), float(p2))
        return out

    def _base_green(self, pressures, node: str) -> float:
        p1, p2 = pressures[node]
        if p1 + p2 <= 1e-9:
            return 0.5
        return float(np.clip(p1 / (p1 + p2), self.sp.g_min, self.sp.g_max))

    def _estimate_net_inflow(self, greens: Dict[str, float]) -> float:
        sat = self.p.urban.Q_sat
        return float(sat * (
            (greens["A"] - 0.5)
            + (greens["C"] - 0.5)
            + 0.5 * (greens["D"] - 0.5)
            + 0.5 * (greens["F"] - 0.5)
        ))

    def _phase_green(self, node: str, approach: str, greens: Dict[str, float]) -> float:
        g1 = float(greens.get(node, 0.5))
        phase = PHASE_BY_APPROACH.get(node, {}).get(approach, 2)
        return g1 if phase == 1 else 1.0 - g1

    def _freeway_restriction_by_node(
        self,
        metering_by_ramp: Dict[str, float],
        vsl_by_freeway: Dict[str, float],
    ) -> Dict[str, float]:
        ramp_to_fw = {"R1": "FW_W", "R2": "FW_W", "R3": "FW_E", "R4": "FW_E"}
        ramp_groups = {"D": ("R2", "R3"), "F": ("R1", "R4")}
        restrictions = {"A": 0.0, "C": 0.0}
        for node, ramps in ramp_groups.items():
            b_vals = [float(metering_by_ramp.get(r, 1.0)) for r in ramps]
            v_vals = [
                float(vsl_by_freeway.get(ramp_to_fw[r], self.p.mpc.vsl_max))
                / max(self.p.mpc.vsl_max, 1.0)
                for r in ramps
            ]
            ramp_restriction = 1.0 - float(np.mean(b_vals))
            vsl_restriction = 1.0 - float(np.mean(v_vals))
            restrictions[node] = (
                self.sp.urban_ramp_restriction_weight * max(0.0, ramp_restriction)
                + self.sp.urban_vsl_restriction_weight * max(0.0, vsl_restriction)
            )
        return restrictions

    def _unique_candidates(self, values: Iterable[float], lo: float, hi: float) -> List[float]:
        clipped = [float(np.clip(v, lo, hi)) for v in values]
        return sorted({round(v, 8): v for v in clipped}.values())

    def _urban_green_candidates(self, node: str, current_green, pressures) -> List[float]:
        values: List[float] = list(getattr(self.sp, "urban_agent_green_candidates", ()))
        values.extend([
            current_green.get(node, 0.5),
            self.last_green.get(node, 0.5),
            self._base_green(pressures, node),
        ])
        return self._unique_candidates(values, self.sp.g_min, self.sp.g_max)

    def _green_boundary_cost(self, green: float) -> float:
        buffer = float(getattr(self.sp, "green_boundary_buffer", 0.0))
        if buffer <= 0.0:
            return 0.0
        low_gap = max(0.0, self.sp.g_min + buffer - green)
        high_gap = max(0.0, green - (self.sp.g_max - buffer))
        return float(low_gap ** 2 + high_gap ** 2)

    def _urban_rollout_score(
        self,
        sim,
        green_by_signal: Dict[str, float],
        metering_by_ramp: Dict[str, float],
        vsl_by_freeway: Dict[str, float],
        rollout_cache: Dict[Tuple[float, ...], Dict[str, float]],
        max_queue_link=None,
        max_queue_val=None,
    ) -> Dict[str, float]:
        u = self._control_vector(green_by_signal, metering_by_ramp, vsl_by_freeway)
        key = (
            tuple(round(float(x), 6) for x in u),
            max_queue_link,
            None if max_queue_val is None else round(float(max_queue_val), 6),
        )
        if key in rollout_cache:
            return rollout_cache[key]

        trial = copy.deepcopy(sim)
        trial.tts_freeway = 0.0
        trial.tts_urban = 0.0
        apply_control(trial, u)

        steps = max(1, int(getattr(self.sp, "urban_agent_preview_freeway_steps", 3)))
        turn_queue_tts = 0.0
        max_total_queue = trial.urban.total_queue()
        managed_queue_max = 0.0
        if max_queue_link is not None:
            managed_queue_max = trial.urban.queue_metric(max_queue_link)
        for _ in range(steps):
            trial.step_freeway_period()
            total_queue = trial.urban.total_queue()
            turn_queue_tts += total_queue * self.p.time.Tf_h
            max_total_queue = max(max_total_queue, total_queue)
            if max_queue_link is not None:
                managed_queue_max = max(
                    managed_queue_max,
                    trial.urban.queue_metric(max_queue_link),
                )

        managed_queue_violation = 0.0
        if max_queue_link is not None and max_queue_val is not None:
            managed_queue_violation = max(0.0, managed_queue_max - float(max_queue_val))

        out = {
            "preview_urban_tts": float(trial.tts_urban),
            "preview_turn_queue_tts": float(turn_queue_tts),
            "preview_max_total_queue": float(max_total_queue),
            "preview_managed_queue_max": float(managed_queue_max),
            "preview_managed_queue_violation": float(managed_queue_violation),
        }
        rollout_cache[key] = out
        return out

    def _managed_link_inflow_projection(
        self,
        sim,
        managed_link: str,
        green_by_signal: Dict[str, float],
    ) -> float:
        if not managed_link or "->" not in managed_link:
            return 0.0
        link_from, link_to = managed_link.split("->", 1)
        if link_from not in SIGNAL_ORDER:
            return 0.0

        sat_base = self.p.urban.Q_sat * self.p.time.Tc / 3600.0
        projected = 0.0
        for (inter, approach), turns in TURNING.items():
            if inter != link_from:
                continue
            pressure = self._approach_pressure(sim, approach, inter)
            green = self._phase_green(inter, approach, green_by_signal)
            service = min(pressure, sat_base * green)
            for turn, ratio in turns.items():
                try:
                    dest_type, dest = turn_destination(inter, approach, turn)
                except Exception:
                    continue
                if dest_type == "urban" and dest == link_to:
                    projected += service * ratio
        return float(max(projected, 0.0))

    def _urban_agent_score(
        self,
        sim,
        node: str,
        green: float,
        current_green: Dict[str, float],
        pressures: Dict[str, Tuple[float, float]],
        protected_net_inflow_target: float,
        metering_by_ramp: Dict[str, float],
        vsl_by_freeway: Dict[str, float],
        rollout_cache: Dict[Tuple[float, ...], Dict[str, float]],
        max_queue_link=None,
        max_queue_val=None,
    ) -> Tuple[float, Dict[str, float]]:
        trial_green = dict(current_green)
        trial_green[node] = float(green)

        p1, p2 = pressures[node]
        sat_veh = self.p.urban.Q_sat * self.p.time.Tc / 3600.0
        q1_after = max(0.0, p1 - green * sat_veh)
        q2_after = max(0.0, p2 - (1.0 - green) * sat_veh)
        local_tts_proxy = (self.p.time.Tc / 3600.0) * (q1_after + q2_after)

        scale = max(p1 + p2, 1.0)
        balance = (q1_after / scale) ** 2 + (q2_after / scale) ** 2
        smooth = (green - self.last_green.get(node, 0.5)) ** 2
        boundary = self._green_boundary_cost(green)

        estimated_net = self._estimate_net_inflow(trial_green)
        target_gap = max(
            0.0,
            abs(estimated_net - protected_net_inflow_target)
            - self.sp.urban_net_inflow_epsilon,
        )
        target_soft_weight = self.sp.urban_target_soft_weight
        if max_queue_link is not None:
            target_soft_weight = max(
                target_soft_weight,
                getattr(self.sp, "urban_queue_target_soft_weight", target_soft_weight),
            )

        restrictions = self._freeway_restriction_by_node(metering_by_ramp, vsl_by_freeway)
        phase1_service_share = green * max(p1, 1.0) / scale
        freeway_feedback = restrictions.get(node, 0.0) * phase1_service_share ** 2
        rollout = self._urban_rollout_score(
            sim,
            trial_green,
            metering_by_ramp,
            vsl_by_freeway,
            rollout_cache,
            max_queue_link=max_queue_link,
            max_queue_val=max_queue_val,
        )
        managed_inflow_penalty = 0.0
        managed_inflow = 0.0
        if max_queue_link is not None:
            managed_inflow = self._managed_link_inflow_projection(
                sim,
                max_queue_link,
                trial_green,
            )
            pressure_factor = 1.0
            if max_queue_val is not None and max_queue_val > 0:
                current_q = sim.urban.queue_metric(max_queue_link)
                pressure_factor += max(0.0, current_q - 0.5 * max_queue_val) / max_queue_val
            pressure_factor += rollout["preview_managed_queue_violation"]
            managed_inflow_penalty = managed_inflow * pressure_factor

        objective = (
            self.sp.urban_tts_weight * rollout["preview_urban_tts"]
            + self.sp.urban_queue_weight * rollout["preview_turn_queue_tts"]
            + self.sp.urban_managed_queue_weight * rollout["preview_managed_queue_violation"] ** 2
            + self.sp.urban_managed_inflow_weight * managed_inflow_penalty
            + self.sp.urban_balance_weight * balance
            + self.sp.green_smooth_weight * smooth
            + self.sp.green_boundary_weight * boundary
            + target_soft_weight * target_gap ** 2
            + freeway_feedback
        )
        return float(objective), {
            "local_tts_proxy": float(local_tts_proxy),
            "preview_urban_tts": rollout["preview_urban_tts"],
            "preview_turn_queue_tts": rollout["preview_turn_queue_tts"],
            "preview_max_total_queue": rollout["preview_max_total_queue"],
            "preview_managed_queue_max": rollout["preview_managed_queue_max"],
            "preview_managed_queue_violation": rollout["preview_managed_queue_violation"],
            "managed_link_inflow_projection": float(managed_inflow),
            "managed_link_inflow_penalty": float(managed_inflow_penalty),
            "balance_cost": float(balance),
            "smooth_cost": float(smooth),
            "green_boundary_cost": float(boundary),
            "target_gap": float(target_gap),
            "target_soft_weight": float(target_soft_weight),
            "estimated_net_inflow": float(estimated_net),
            "freeway_feedback_cost": float(freeway_feedback),
            "pressure_phase1": float(p1),
            "pressure_phase2": float(p2),
        }

    def _choose_urban_agent(
        self,
        sim,
        node: str,
        current_green: Dict[str, float],
        pressures: Dict[str, Tuple[float, float]],
        protected_net_inflow_target: float,
        metering_by_ramp: Dict[str, float],
        vsl_by_freeway: Dict[str, float],
        rollout_cache: Dict[Tuple[float, ...], Dict[str, float]],
        max_queue_link=None,
        max_queue_val=None,
    ) -> LocalDecision:
        best = None
        for green in self._urban_green_candidates(node, current_green, pressures):
            objective, diagnostics = self._urban_agent_score(
                sim,
                node,
                green,
                current_green,
                pressures,
                protected_net_inflow_target,
                metering_by_ramp,
                vsl_by_freeway,
                rollout_cache,
                max_queue_link=max_queue_link,
                max_queue_val=max_queue_val,
            )
            decision = LocalDecision(
                agent=f"urban_{node}",
                objective_value=objective,
                payload={"green": float(green)},
                diagnostics=diagnostics,
            )
            if best is None or decision.objective_value < best.objective_value:
                best = decision
        return best

    # ---------------------------------------------------------------- freeway
    def _ramp_groups(self, sim) -> Dict[str, List[str]]:
        groups = {fw: [] for fw in sim.fw}
        for ramp in RAMP_ORDER:
            if ramp in sim.ramp_by_name:
                fw_name = sim.ramp_by_name[ramp].freeway
                groups.setdefault(fw_name, []).append(ramp)
        return groups

    def _urban_ramp_arrival_projection(
        self,
        sim,
        ramp_name: str,
        urban_green_by_signal: Dict[str, float],
    ) -> float:
        ramp = sim.ramp_by_name[ramp_name]
        node = ramp.urban_node
        projected = 0.0
        sat_base = self.p.urban.Q_sat * self.p.time.Tc / 3600.0
        for (inter, approach), turns in TURNING.items():
            if inter != node:
                continue
            ramp_share = turns.get(f"to_{ramp_name}", 0.0)
            if ramp_share <= 0.0:
                continue
            pressure = self._approach_pressure(sim, approach, node)
            green = self._phase_green(node, approach, urban_green_by_signal)
            projected += min(pressure, sat_base * green) * ramp_share
        return float(max(projected, 0.0))

    def _ramp_available_vehicles(
        self,
        sim,
        ramp_name: str,
        urban_green_by_signal: Dict[str, float],
    ) -> float:
        queue = float(sim.onramp_q.get(ramp_name, 0.0))
        projected = self._urban_ramp_arrival_projection(
            sim,
            ramp_name,
            urban_green_by_signal,
        )
        return float(max(queue + projected, 0.0))

    def _green_aware_ramp_pressure(
        self,
        sim,
        ramp_name: str,
        urban_green_by_signal: Dict[str, float],
    ) -> float:
        return float(max(
            self._ramp_available_vehicles(sim, ramp_name, urban_green_by_signal),
            1.0,
        ))

    def _predicted_ramp_release_flow(
        self,
        sim,
        ramp_name: str,
        metering_rate: float,
        urban_green_by_signal: Dict[str, float],
    ) -> float:
        ramp = sim.ramp_by_name[ramp_name]
        available_veh = self._ramp_available_vehicles(
            sim,
            ramp_name,
            urban_green_by_signal,
        )
        demand_flow = available_veh / max(self.p.time.Tc / 3600.0, 1e-9)
        cap_flow = float(np.clip(metering_rate, self.sp.b_min, self.sp.b_max)) * ramp.Q_cap
        return float(max(0.0, min(cap_flow, demand_flow)))

    def _local_metering_target(
        self,
        sim,
        fw_name: str,
        total_metering_target: float,
        ramp_groups: Dict[str, List[str]],
    ) -> float:
        capacities = {r.name: r.Q_cap for r in sim.net.ramps}
        total_capacity = sum(capacities[r] for r in RAMP_ORDER if r in capacities)
        local_capacity = sum(capacities[r] for r in ramp_groups.get(fw_name, ()))
        feasible_total = float(np.clip(
            total_metering_target,
            self.sp.b_min * total_capacity,
            self.sp.b_max * total_capacity,
        ))
        if total_capacity <= 1e-9:
            return 0.0
        return float(feasible_total * local_capacity / total_capacity)

    def _metering_candidates(
        self,
        sim,
        fw_name: str,
        ramps: List[str],
        local_target: float,
        current_metering: Dict[str, float],
        urban_green_by_signal: Dict[str, float],
    ) -> List[Dict[str, float]]:
        capacities = {r.name: r.Q_cap for r in sim.net.ramps}
        available = np.array([
            self._ramp_available_vehicles(sim, r, urban_green_by_signal)
            for r in ramps
        ], dtype=float)
        weights = np.maximum(available, 1.0)
        weights = weights / max(float(np.sum(weights)), 1e-9)
        local_capacity = sum(capacities[r] for r in ramps)
        local_demand_flow = sum(
            available[i] / max(self.p.time.Tc / 3600.0, 1e-9)
            for i, _r in enumerate(ramps)
        )
        scales = getattr(self.sp, "freeway_agent_metering_scales", (0.75, 1.0, 1.25))

        candidates: List[Dict[str, float]] = []
        for scale in scales:
            flow_target = float(np.clip(
                local_target * scale,
                self.sp.b_min * local_capacity,
                min(self.sp.b_max * local_capacity, local_demand_flow),
            ))
            flows = weights * flow_target
            candidates.append({
                r: float(np.clip(flows[i] / max(capacities[r], 1e-9), self.sp.b_min, self.sp.b_max))
                for i, r in enumerate(ramps)
            })

        candidates.append({r: self.sp.b_max for r in ramps})
        candidates.append({
            r: float(np.clip(current_metering.get(r, 1.0), self.sp.b_min, self.sp.b_max))
            for r in ramps
        })

        seen = set()
        unique = []
        for cand in candidates:
            key = tuple((r, round(cand[r], 8)) for r in ramps)
            if key in seen:
                continue
            seen.add(key)
            unique.append(cand)
        return unique

    def _rho_crit_from_vsl(self, vsl: float) -> float:
        vf = max(self.p.metanet.v_free, 1.0)
        ratio = np.clip(vf / max(vsl, 1.0), 1.0, self.sp.rho_crit_vsl_gain_cap)
        return float(np.clip(
            self.p.metanet.rho_crit * ratio,
            self.p.metanet.rho_crit,
            self.p.metanet.rho_max * self.sp.rho_crit_max_ratio,
        ))

    def _freeway_vsl_candidates(self, fw_name: str, current_vsl) -> List[float]:
        values = list(getattr(self.sp, "vsl_values", (self.p.mpc.vsl_max,)))
        values.extend([
            current_vsl.get(fw_name, self.p.mpc.vsl_max),
            self.last_vsl.get(fw_name, self.p.mpc.vsl_max),
            self.p.mpc.vsl_max,
        ])
        return self._unique_candidates(values, self.p.mpc.vsl_min, self.p.mpc.vsl_max)

    def _freeway_agent_score(
        self,
        sim,
        fw_name: str,
        ramps: List[str],
        local_metering: Dict[str, float],
        vsl: float,
        local_target: float,
        target_rho_crit_by_freeway: Dict[str, float],
        urban_green_by_signal: Dict[str, float],
    ) -> Tuple[float, Dict[str, float]]:
        capacities = {r.name: r.Q_cap for r in sim.net.ramps}
        Tc_h = self.p.time.Tc / 3600.0
        release_flow = {}
        available_by_ramp = {}
        for ramp_name in ramps:
            available_by_ramp[ramp_name] = self._ramp_available_vehicles(
                sim,
                ramp_name,
                urban_green_by_signal,
            )
            release_flow[ramp_name] = self._predicted_ramp_release_flow(
                sim,
                ramp_name,
                local_metering[ramp_name],
                urban_green_by_signal,
            )

        ramp_queue_after = 0.0
        for ramp_name in ramps:
            ramp_queue_after += max(0.0, available_by_ramp[ramp_name] - release_flow[ramp_name] * Tc_h)

        fs = sim.fw[fw_name]
        local_veh = freeway_vehicles(fs)
        local_tts_proxy = Tc_h * (local_veh + ramp_queue_after)

        merge_flow = sum(release_flow.values())
        lane_km = max(fs.n * fs.L * fs.lanes, 1e-9)
        rho_pred = float(np.mean(fs.rho) + merge_flow * Tc_h / lane_km)
        rho_star = target_rho_crit_by_freeway.get(fw_name, self.p.metanet.rho_crit)
        if getattr(self.sp, "apply_rho_crit_to_plant", False):
            rho_star = max(rho_star, self._rho_crit_from_vsl(vsl))
        density_cost = max(0.0, rho_pred - rho_star) ** 2

        target_gap = merge_flow - local_target
        vsl_smooth = (vsl - self.last_vsl.get(fw_name, self.p.mpc.vsl_max)) ** 2
        metering_smooth = sum(
            (local_metering[r] - self.last_metering.get(r, 1.0)) ** 2
            for r in ramps
        )
        speed_delay_proxy = local_tts_proxy * max(0.0, self.p.mpc.vsl_max / max(vsl, 1.0) - 1.0)

        objective = (
            self.sp.freeway_tts_weight * (local_tts_proxy + speed_delay_proxy)
            + self.sp.ramp_queue_weight * ramp_queue_after
            + self.sp.freeway_density_weight * density_cost
            + self.sp.vsl_smooth_weight * vsl_smooth
            + self.sp.metering_smooth_weight * metering_smooth
            + self.sp.freeway_target_soft_weight * target_gap ** 2
        )
        return float(objective), {
            "local_tts_proxy": float(local_tts_proxy),
            "speed_delay_proxy": float(speed_delay_proxy),
            "ramp_queue_after": float(ramp_queue_after),
            "density_cost": float(density_cost),
            "rho_pred": float(rho_pred),
            "rho_target": float(rho_star),
            "target_gap": float(target_gap),
            "vsl_smooth_cost": float(vsl_smooth),
            "metering_smooth_cost": float(metering_smooth),
            "realized_metering_flow": float(merge_flow),
            "nominal_metering_capacity": float(sum(local_metering[r] * capacities[r] for r in ramps)),
            "available_ramp_flow": float(sum(available_by_ramp[r] / max(Tc_h, 1e-9) for r in ramps)),
            "local_metering_target": float(local_target),
        }

    def _choose_freeway_agent(
        self,
        sim,
        fw_name: str,
        current_metering: Dict[str, float],
        current_vsl: Dict[str, float],
        urban_green_by_signal: Dict[str, float],
        total_metering_target: float,
        target_rho_crit_by_freeway: Dict[str, float],
        ramp_groups: Dict[str, List[str]],
    ) -> LocalDecision:
        ramps = ramp_groups.get(fw_name, [])
        local_target = self._local_metering_target(
            sim,
            fw_name,
            total_metering_target,
            ramp_groups,
        )
        metering_candidates = self._metering_candidates(
            sim,
            fw_name,
            ramps,
            local_target,
            current_metering,
            urban_green_by_signal,
        )

        best = None
        for vsl in self._freeway_vsl_candidates(fw_name, current_vsl):
            for local_metering in metering_candidates:
                objective, diagnostics = self._freeway_agent_score(
                    sim,
                    fw_name,
                    ramps,
                    local_metering,
                    vsl,
                    local_target,
                    target_rho_crit_by_freeway,
                    urban_green_by_signal,
                )
                payload = {"vsl": float(vsl)}
                for ramp_name in ramps:
                    payload[f"b_{ramp_name}"] = float(local_metering[ramp_name])
                decision = LocalDecision(
                    agent=f"freeway_{fw_name}",
                    objective_value=objective,
                    payload=payload,
                    diagnostics=diagnostics,
                )
                if best is None or decision.objective_value < best.objective_value:
                    best = decision
        return best

    # --------------------------------------------------------------- game loop
    def _control_vector(
        self,
        green_by_signal: Dict[str, float],
        metering_by_ramp: Dict[str, float],
        vsl_by_freeway: Dict[str, float],
    ) -> np.ndarray:
        return np.array([
            green_by_signal["A"],
            green_by_signal["C"],
            green_by_signal["D"],
            green_by_signal["F"],
            metering_by_ramp["R1"],
            metering_by_ramp["R2"],
            metering_by_ramp["R3"],
            metering_by_ramp["R4"],
            vsl_by_freeway.get("FW_W", self.p.mpc.vsl_max),
            vsl_by_freeway.get("FW_E", self.p.mpc.vsl_max),
        ], dtype=float)

    def solve(
        self,
        sim,
        candidate,
        reference_vsl=None,
        reference_green=None,
        max_queue_link=None,
        max_queue_val=None,
    ) -> Dict[str, object]:
        reference_vsl = reference_vsl or {}
        reference_green = reference_green or {}
        green_by_signal = {
            node: float(np.clip(
                reference_green.get(node, self.last_green.get(node, 0.5)),
                self.sp.g_min,
                self.sp.g_max,
            ))
            for node in SIGNAL_ORDER
        }
        metering_by_ramp = dict(self.last_metering)
        vsl_by_freeway = {
            fw: float(reference_vsl.get(fw, self.last_vsl.get(fw, self.p.mpc.vsl_max)))
            for fw in sim.fw
        }

        ramp_groups = self._ramp_groups(sim)
        last_u = None
        iteration_log = []
        converged = False
        final_urban_decisions: List[LocalDecision] = []
        final_freeway_decisions: List[LocalDecision] = []

        for iteration in range(max(1, int(self.sp.follower_game_max_iter))):
            pressures = self._phase_pressures(sim)
            rollout_cache: Dict[Tuple[float, ...], Dict[str, float]] = {}
            urban_decisions: List[LocalDecision] = []
            for _round in range(max(1, int(getattr(self.sp, "urban_agent_best_response_rounds", 1)))):
                for node in SIGNAL_ORDER:
                    decision = self._choose_urban_agent(
                        sim,
                        node,
                        green_by_signal,
                        pressures,
                        candidate.protected_net_inflow,
                        metering_by_ramp,
                        vsl_by_freeway,
                        rollout_cache,
                        max_queue_link=max_queue_link,
                        max_queue_val=max_queue_val,
                    )
                    green_by_signal[node] = float(decision.payload["green"])
                    urban_decisions.append(decision)

            freeway_decisions: List[LocalDecision] = []
            for fw_name in sim.fw:
                decision = self._choose_freeway_agent(
                    sim,
                    fw_name,
                    metering_by_ramp,
                    vsl_by_freeway,
                    green_by_signal,
                    candidate.total_metering,
                    candidate.rho_crit_by_freeway,
                    ramp_groups,
                )
                vsl_by_freeway[fw_name] = float(decision.payload["vsl"])
                for ramp_name in ramp_groups.get(fw_name, []):
                    metering_by_ramp[ramp_name] = float(decision.payload[f"b_{ramp_name}"])
                freeway_decisions.append(decision)

            u = self._control_vector(green_by_signal, metering_by_ramp, vsl_by_freeway)
            delta = np.inf if last_u is None else float(np.max(np.abs(u - last_u)))
            iteration_log.append({
                "iteration": iteration + 1,
                "control_delta": None if not np.isfinite(delta) else delta,
                "urban_agents": [d.as_log() for d in urban_decisions],
                "freeway_agents": [d.as_log() for d in freeway_decisions],
                "g_A": u[0], "g_C": u[1], "g_D": u[2], "g_F": u[3],
                "b1": u[4], "b2": u[5], "b3": u[6], "b4": u[7],
                "v_FW_W": u[8], "v_FW_E": u[9],
            })

            final_urban_decisions = urban_decisions
            final_freeway_decisions = freeway_decisions
            if last_u is not None and delta <= self.sp.follower_game_tol:
                converged = True
                break
            last_u = u.copy()

        estimated_net = self._estimate_net_inflow(green_by_signal)
        urban_slack = max(
            0.0,
            abs(estimated_net - candidate.protected_net_inflow)
            - self.sp.urban_net_inflow_epsilon,
        )
        urban_response = UrbanFollowerResponse(
            green_by_signal=green_by_signal,
            estimated_net_inflow=float(estimated_net),
            slack=float(urban_slack),
            objective_value=float(sum(d.objective_value for d in final_urban_decisions)),
            optimization_success=True,
            optimization_message=(
                "distributed best-response over intersection agents A/C/D/F"
            ),
        )

        total_metering_flow = sum(
            self._predicted_ramp_release_flow(sim, r, metering_by_ramp[r], green_by_signal)
            for r in RAMP_ORDER
            if r in sim.ramp_by_name
        )
        freeway_objective = float(sum(d.objective_value for d in final_freeway_decisions))
        preview_freeway_tts = float(sum(
            d.diagnostics.get("local_tts_proxy", 0.0)
            for d in final_freeway_decisions
        ))
        freeway_response = FreewayFollowerResponse(
            metering_by_ramp=metering_by_ramp,
            vsl_by_freeway=vsl_by_freeway,
            total_metering_flow=float(total_metering_flow),
            objective_value=freeway_objective,
            optimization_success=True,
            optimization_message=(
                "distributed best-response over freeway link agents FW_W/FW_E"
            ),
            preview_freeway_tts=preview_freeway_tts,
            solver_objective_value=freeway_objective,
        )

        return {
            "urban_response": urban_response,
            "freeway_response": freeway_response,
            "log": iteration_log,
            "iterations": len(iteration_log),
            "converged": converged,
            "final_delta": iteration_log[-1]["control_delta"] if iteration_log else None,
        }

    def commit(self, urban_response, freeway_response) -> None:
        self.last_green = dict(urban_response.green_by_signal)
        self.last_metering = dict(freeway_response.metering_by_ramp)
        self.last_vsl = dict(freeway_response.vsl_by_freeway)

    def responses_from_control(self, sim, u, message: str):
        u = np.asarray(u, dtype=float)
        green_by_signal = {
            "A": float(u[0]),
            "C": float(u[1]),
            "D": float(u[2]),
            "F": float(u[3]),
        }
        metering_by_ramp = {
            "R1": float(u[4]),
            "R2": float(u[5]),
            "R3": float(u[6]),
            "R4": float(u[7]),
        }
        vsl_by_freeway = {
            "FW_W": float(u[8]) if len(u) > 8 else self.p.mpc.vsl_max,
            "FW_E": float(u[9]) if len(u) > 9 else self.p.mpc.vsl_max,
        }
        total_metering_flow = sum(
            self._predicted_ramp_release_flow(sim, r, metering_by_ramp[r], green_by_signal)
            for r in RAMP_ORDER
            if r in sim.ramp_by_name
        )
        urban_response = UrbanFollowerResponse(
            green_by_signal=green_by_signal,
            estimated_net_inflow=self._estimate_net_inflow(green_by_signal),
            slack=0.0,
            objective_value=0.0,
            optimization_success=True,
            optimization_message=message,
        )
        freeway_response = FreewayFollowerResponse(
            metering_by_ramp=metering_by_ramp,
            vsl_by_freeway=vsl_by_freeway,
            total_metering_flow=float(total_metering_flow),
            objective_value=0.0,
            optimization_success=True,
            optimization_message=message,
            preview_freeway_tts=0.0,
            solver_objective_value=0.0,
        )
        return urban_response, freeway_response
