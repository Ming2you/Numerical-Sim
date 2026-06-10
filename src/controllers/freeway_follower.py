from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Dict, Iterable, Optional

import numpy as np

from src.controllers.leader import LeaderAction
from src.models.demand import DemandStep
from src.models.metanet import compute_ramp_release_flows, freeway_substep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    ensure_urban_state,
    estimate_onramp_green_release_flows,
    off_ramp_capacity_by_freeway_link,
)


@dataclass
class FreewayFollowerResult:
    ramp_metering: Dict[str, float]
    vsl: Dict[str, float]
    objective_value: float
    infeasibility: Dict[str, float]


@dataclass
class _HorizonEvaluation:
    score: float
    freeway_ttt: float
    metering_error: float
    queue_overflow: float
    density_excess: float
    min_receiving_factor: float
    steps: int
    expanded_nodes: int


@dataclass
class _SequenceNode:
    state: TrafficState
    last_control: ControlAction
    first_ramp_metering: Dict[str, float]
    first_vsl: Dict[str, float]
    score: float = 0.0
    freeway_ttt: float = 0.0
    metering_error_sum: float = 0.0
    queue_overflow: float = 0.0
    density_excess: float = 0.0
    min_receiving_factor: float = 1.0
    steps: int = 0
    first_projection: Optional[Dict[str, float]] = None


def _aggregate_prediction_diagnostics(rows: list[Dict[str, float]]) -> Dict[str, float]:
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
        values = [float(row.get(key, 0.0)) for row in rows]
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


class FreewayFollower:
    """Freeway follower solved by sequence-scored feasible projection.

    Ramp metering is projected onto per-ramp capacities and the aggregate
    `N_UF_star` target. Candidate ramp allocations and VSL values are expanded
    over the MPC forecast with beam search and the same METANET plant used by
    the simulator. The returned action is the first control interval action of
    the best predicted sequence.
    """

    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg

    def _as_forecast(self, demand: DemandStep | Iterable[DemandStep]) -> list[DemandStep]:
        if isinstance(demand, DemandStep):
            return [demand]
        forecast = list(demand)
        if not forecast:
            raise ValueError("FreewayFollower requires at least one demand step.")
        return forecast[: max(1, self.cfg.mpc.horizon_steps)]

    def _nuf_target_flow(self, leader: LeaderAction) -> float:
        if self.cfg.leader.N_UF_star_unit == "veh_per_control_interval":
            return float(leader.N_UF_star / max(self.cfg.simulation.T_c_h, 1.0e-9))
        return float(leader.N_UF_star)

    def _ramp_merge_index(self, ramp: str, n_segments: int) -> int:
        configured = getattr(self.cfg.network, "ramp_merge_segment_index", {})
        if isinstance(configured, dict) and ramp in configured:
            return int(np.clip(float(configured[ramp]), 0.0, float(n_segments - 1)))
        return n_segments // 2

    def _ramp_upper_bounds(
        self,
        state: TrafficState,
        demand: DemandStep,
        previous_control: Optional[ControlAction],
    ) -> tuple[np.ndarray, Dict[str, float]]:
        net = self.cfg.network
        dt_h = self.cfg.simulation.T_f_h
        cap_factor = getattr(demand, "incident_capacity_factor", 1.0)
        downstream_cap = net.freeway_capacity_veh_h * cap_factor
        urban_control = previous_control or ControlAction.fixed(self.cfg)
        green_inflow = estimate_onramp_green_release_flows(
            state.copy(),
            urban_control,
            demand,
            self.cfg,
            interval_h=dt_h,
        )
        upper = []
        receiving: Dict[str, float] = {}
        for ramp in net.ramps:
            link = net.ramp_to_freeway[ramp]
            merge_idx = self._ramp_merge_index(ramp, len(state.freeway_density[link]))
            rho_merge = state.freeway_density[link][merge_idx]
            factor = float(np.clip(
                (net.rho_max - rho_merge) / max(net.rho_max - net.rho_crit, 1.0e-9),
                0.0,
                1.0,
            ))
            receiving[ramp] = factor
            available = state.ramp_queue.get(ramp, 0.0) / max(dt_h, 1.0e-9) + green_inflow.get(ramp, 0.0)
            upper.append(min(
                net.ramp_capacity_veh_h[ramp],
                max(0.0, available),
                downstream_cap * factor,
            ))
        return np.asarray(upper, dtype=float), receiving

    @staticmethod
    def _allocate_to_target(target: float, upper: np.ndarray, weights: np.ndarray) -> np.ndarray:
        release = np.zeros_like(upper, dtype=float)
        remaining = float(np.clip(target, 0.0, float(np.sum(upper))))
        active = upper > 1.0e-9
        while remaining > 1.0e-9 and bool(np.any(active)):
            w = np.where(active, np.maximum(weights, 1.0e-9), 0.0)
            w_sum = float(np.sum(w))
            if w_sum <= 1.0e-9:
                break
            proposed = remaining * w / w_sum
            spare = upper - release
            capped = active & (proposed >= spare - 1.0e-9)
            if not bool(np.any(capped)):
                release += proposed
                remaining = 0.0
                break
            add = np.where(capped, np.maximum(spare, 0.0), 0.0)
            release += add
            remaining -= float(np.sum(add))
            active = active & ~capped
        return np.minimum(release, upper)

    def _ramp_candidates(
        self,
        state: TrafficState,
        leader: LeaderAction,
        forecast: list[DemandStep],
        previous_control: Optional[ControlAction],
    ) -> tuple[list[Dict[str, float]], Dict[str, float]]:
        net = self.cfg.network
        upper, receiving = self._ramp_upper_bounds(state, forecast[0], previous_control)
        target = self._nuf_target_flow(leader)
        projected_total = float(np.clip(target, 0.0, float(np.sum(upper))))

        future_queue_pressure = np.asarray([
            state.ramp_queue.get(r, 0.0)
            + state.urban_movement_queue.get(net.on_ramp_to_movement.get(r, ""), 0.0)
            + sum(d.ramp_arrival.get(r, 0.0) * self.cfg.simulation.T_c_h for d in forecast)
            for r in net.ramps
        ], dtype=float)
        receiving_weights = np.asarray([receiving.get(r, 1.0) + 0.05 for r in net.ramps], dtype=float)
        weight_sets = [
            future_queue_pressure + 1.0,
            np.ones(len(net.ramps), dtype=float),
            receiving_weights,
        ]
        if previous_control is not None:
            weight_sets.append(np.asarray([
                previous_control.ramp_metering.get(r, 0.0) + 1.0
                for r in net.ramps
            ], dtype=float))

        candidates: list[Dict[str, float]] = []
        seen: set[tuple[float, ...]] = set()
        for weights in weight_sets:
            release = self._allocate_to_target(projected_total, upper, weights)
            key = tuple(round(float(v), 6) for v in release)
            if key in seen:
                continue
            seen.add(key)
            candidates.append({r: float(release[i]) for i, r in enumerate(net.ramps)})
            if len(candidates) >= max(1, int(self.cfg.freeway_follower.horizon_ramp_candidate_limit)):
                break

        if not candidates:
            candidates.append({r: 0.0 for r in net.ramps})

        return candidates, {
            "target": float(target),
            "projected_total": projected_total,
            "target_infeasible": float(abs(projected_total - target) > self.cfg.freeway_follower.eps_F),
            "min_receiving_factor": float(min(receiving.values()) if receiving else 1.0),
            "step_capacity": float(np.sum(upper)),
        }

    def _vsl_candidates(self, previous_control: Optional[ControlAction]) -> Dict[str, list[float]]:
        fc = self.cfg.freeway_follower
        vsl_set = sorted(float(v) for v in fc.vsl_set)
        previous = previous_control.vsl if previous_control else {}
        out: Dict[str, list[float]] = {}
        for link in self.cfg.network.freeway_links:
            prev = previous.get(link, max(vsl_set))
            feasible = [v for v in vsl_set if abs(v - prev) <= fc.max_vsl_step + 1.0e-9]
            feasible = feasible or vsl_set
            limit = max(1, int(fc.horizon_vsl_candidate_limit_per_link))
            out[link] = sorted(feasible, key=lambda v: (abs(v - prev), v))[:limit]
        return out

    def _apply_onramp_boundary_forecast(
        self,
        state: TrafficState,
        control: ControlAction,
        demand: DemandStep,
    ) -> Dict[str, float]:
        """고정된 urban control에서 x_on -> w_r boundary 유입을 한 T_f만큼 예측/반영한다."""
        ensure_urban_state(state, self.cfg)
        net = self.cfg.network
        dt_h = self.cfg.simulation.T_f_h
        green_flow = estimate_onramp_green_release_flows(
            state,
            control,
            demand,
            self.cfg,
            interval_h=dt_h,
        )
        for ramp, movement in net.on_ramp_to_movement.items():
            arrival_veh = max(0.0, demand.ramp_arrival.get(ramp, 0.0)) * dt_h
            available_x_on = max(0.0, state.urban_movement_queue.get(movement, 0.0)) + arrival_veh
            ramp_before = max(0.0, state.ramp_queue.get(ramp, 0.0))
            ramp_space = max(0.0, net.ramp_queue_max_veh - ramp_before)
            green_veh = min(
                max(0.0, green_flow.get(ramp, 0.0)) * dt_h,
                available_x_on,
                ramp_space,
            )
            state.urban_movement_queue[movement] = max(0.0, available_x_on - green_veh)
            state.ramp_queue[ramp] = min(net.ramp_queue_max_veh, ramp_before + green_veh)
        return green_flow

    def _actual_metering_release(
        self,
        state: TrafficState,
        control: ControlAction,
        demand: DemandStep,
    ) -> tuple[Dict[str, float], Dict[str, float]]:
        """w_r에 실제 존재하는 차량만 metering release로 인정한다."""
        dt_h = self.cfg.simulation.T_f_h
        requested_release, requested_diag = compute_ramp_release_flows(
            state,
            control,
            demand,
            self.cfg,
            include_current_arrivals=False,
        )
        actual_release: Dict[str, float] = {}
        request_veh_total = 0.0
        actual_veh_total = 0.0
        shortfall_veh_total = 0.0
        diag = dict(requested_diag)
        for ramp in self.cfg.network.ramps:
            requested_veh = max(0.0, requested_release.get(ramp, 0.0)) * dt_h
            before = max(0.0, state.ramp_queue.get(ramp, 0.0))
            actual_veh = min(before, requested_veh)
            shortfall_veh = max(0.0, requested_veh - actual_veh)
            state.ramp_queue[ramp] = max(0.0, before - actual_veh)
            actual_release[ramp] = actual_veh / max(dt_h, 1.0e-9)
            request_veh_total += requested_veh
            actual_veh_total += actual_veh
            shortfall_veh_total += shortfall_veh
            diag[f"ramp_metering_release_request_{ramp}_veh"] = float(requested_veh)
            diag[f"ramp_metering_release_actual_{ramp}_veh"] = float(actual_veh)
            diag[f"ramp_metering_release_shortfall_{ramp}_veh"] = float(shortfall_veh)
        diag["total_metering_flow"] = float(sum(actual_release.values()))
        diag["total_no_meter_flow"] = float(max(
            requested_diag.get("total_no_meter_flow", 0.0),
            diag["total_metering_flow"],
        ))
        diag["ramp_metering_release_request_veh"] = float(request_veh_total)
        diag["ramp_metering_releases_veh"] = float(actual_veh_total)
        diag["ramp_metering_release_shortfall_veh"] = float(shortfall_veh_total)
        return actual_release, diag

    def _consume_lightweight_offramp_storage(
        self,
        state: TrafficState,
        fw_diag: Dict[str, float],
    ) -> None:
        """경량 예측에서도 off-ramp storage가 계속 비워지지 않는 착시를 막는다."""
        net = self.cfg.network
        dt_h = self.cfg.simulation.T_f_h
        for off_ramp in net.off_ramps:
            link = net.off_ramp_from_freeway[off_ramp]
            link_ratio_total = sum(
                ratio
                for candidate, ratio in net.off_ramp_split_ratio.items()
                if net.off_ramp_from_freeway.get(candidate) == link
            )
            share = net.off_ramp_split_ratio.get(off_ramp, 0.0) / max(link_ratio_total, 1.0e-9)
            vehicles = fw_diag.get(f"offramp_flow_{link}", 0.0) * share * dt_h
            storage_link = net.off_ramp_storage_link[off_ramp]
            before = max(0.0, state.urban_link_storage.get(storage_link, 0.0))
            state.urban_link_storage[storage_link] = max(0.0, before - vehicles)

    def _lightweight_transition(
        self,
        state: TrafficState,
        control: ControlAction,
        demand: DemandStep,
    ) -> tuple[TrafficState, float, Dict[str, float]]:
        """후보 평가용 경량 plant: urban 전체 재시뮬레이션 없이 freeway와 boundary만 전진한다."""
        probe = state.copy()
        ensure_urban_state(probe, self.cfg)
        sim = self.cfg.simulation
        total_ttt = 0.0
        rows: list[Dict[str, float]] = []
        onramp_green_flow_total = 0.0

        for _ in range(sim.K_cf):
            green_flow = self._apply_onramp_boundary_forecast(probe, control, demand)
            onramp_green_flow_total += sum(green_flow.values())
            actual_release, ramp_diag = self._actual_metering_release(probe, control, demand)
            offramp_capacity = off_ramp_capacity_by_freeway_link(
                probe.copy(),
                self.cfg,
                interval_h=sim.T_f_h,
            )
            fw_ttt, fw_diag = freeway_substep(
                probe,
                control,
                demand,
                self.cfg,
                offramp_capacity_veh_h=offramp_capacity,
                ramp_release_veh_h=actual_release,
                ramp_release_diagnostics=ramp_diag,
                update_ramp_queues=False,
                include_ramp_queue_ttt=False,
            )
            self._consume_lightweight_offramp_storage(probe, fw_diag)
            total_ttt += fw_ttt
            rows.append(fw_diag)

        diag = _aggregate_prediction_diagnostics(rows)
        diag["freeway_follower_lightweight_prediction"] = 1.0
        diag["freeway_follower_coupled_prediction"] = 0.0
        diag["freeway_follower_boundary_forecast_active"] = 1.0
        diag["onramp_green_forecast_flow"] = float(onramp_green_flow_total / max(sim.K_cf, 1))
        return probe, float(total_ttt), diag

    def _transition_node(
        self,
        node: _SequenceNode,
        leader: LeaderAction,
        demand: DemandStep,
        ramp_metering: Dict[str, float],
        vsl: Dict[str, float],
        projection: Dict[str, float],
    ) -> _SequenceNode:
        net = self.cfg.network
        fc = self.cfg.freeway_follower
        probe = node.state.copy()
        control = ControlAction(
            N_P_star=leader.N_P_star,
            N_UF_star=leader.N_UF_star,
            ramp_metering=dict(ramp_metering),
            vsl=dict(vsl),
            green_times=dict(node.last_control.green_times),
            offsets=dict(node.last_control.offsets),
            inflow_outflow_allocation=dict(node.last_control.inflow_outflow_allocation),
        )
        probe, fw_ttt, diag = self._lightweight_transition(probe, control, demand)
        probe.time_sec += self.cfg.simulation.control_interval
        metering_error = float(diag.get("total_metering_error", 0.0))
        receiving = float(diag.get("mean_ramp_receiving_factor", 1.0))
        queue_overflow = sum(max(0.0, q - net.ramp_queue_max_veh) for q in probe.ramp_queue.values())
        density_excess = sum(
            max(0.0, rho - net.rho_crit)
            for values in probe.freeway_density.values()
            for rho in values
        )
        smooth_ramp = sum(
            abs(ramp_metering[r] - node.last_control.ramp_metering.get(r, ramp_metering[r]))
            for r in net.ramps
        )
        smooth_vsl = sum(
            abs(vsl[l] - node.last_control.vsl.get(l, vsl[l]))
            for l in net.freeway_links
        )
        increment = (
            fw_ttt
            + fc.ramp_queue_penalty * queue_overflow * self.cfg.simulation.T_c_h
            + fc.density_penalty * density_excess * self.cfg.simulation.T_c_h
            + fc.metering_smoothness_weight * smooth_ramp
            + fc.vsl_smoothness_weight * smooth_vsl
            + 0.01 * metering_error
        )
        return _SequenceNode(
            state=probe,
            last_control=control,
            first_ramp_metering=dict(ramp_metering) if node.steps == 0 else node.first_ramp_metering,
            first_vsl=dict(vsl) if node.steps == 0 else node.first_vsl,
            score=float(node.score + increment),
            freeway_ttt=float(node.freeway_ttt + fw_ttt),
            metering_error_sum=float(node.metering_error_sum + metering_error),
            queue_overflow=float(node.queue_overflow + queue_overflow),
            density_excess=float(node.density_excess + density_excess),
            min_receiving_factor=float(min(node.min_receiving_factor, receiving)),
            steps=node.steps + 1,
            first_projection=dict(projection) if node.steps == 0 else node.first_projection,
        )

    def _choose_horizon_sequence(
        self,
        state: TrafficState,
        leader: LeaderAction,
        forecast: list[DemandStep],
        previous_control: Optional[ControlAction],
    ) -> tuple[Dict[str, float], Dict[str, float], _HorizonEvaluation, Dict[str, float]]:
        initial_previous = previous_control or ControlAction.fixed(self.cfg)
        beam = [
            _SequenceNode(
                state=state.copy(),
                last_control=initial_previous,
                first_ramp_metering={},
                first_vsl={},
            )
        ]
        expanded_nodes = 0
        beam_width = max(1, int(self.cfg.freeway_follower.horizon_beam_width))
        links = list(self.cfg.network.freeway_links)

        for step_idx, demand in enumerate(forecast[: max(1, self.cfg.mpc.horizon_steps)]):
            next_beam: list[_SequenceNode] = []
            remaining_forecast = forecast[step_idx:]
            for node in beam:
                ramp_candidates, projection = self._ramp_candidates(
                    node.state,
                    leader,
                    remaining_forecast,
                    node.last_control,
                )
                candidates_by_link = self._vsl_candidates(node.last_control)
                for ramp_metering in ramp_candidates:
                    for values in product(*(candidates_by_link[link] for link in links)):
                        vsl = {link: float(value) for link, value in zip(links, values)}
                        next_beam.append(self._transition_node(
                            node,
                            leader,
                            demand,
                            ramp_metering,
                            vsl,
                            projection,
                        ))
                        expanded_nodes += 1
            next_beam.sort(key=lambda item: item.score)
            beam = next_beam[:beam_width]
            if not beam:
                break

        if not beam:
            raise RuntimeError("Freeway follower sequence search produced no candidates.")

        best = min(beam, key=lambda item: item.score)
        projection = best.first_projection or {
            "target": self._nuf_target_flow(leader),
            "projected_total": 0.0,
            "target_infeasible": 1.0,
            "min_receiving_factor": 0.0,
            "step_capacity": 0.0,
        }
        evaluation = _HorizonEvaluation(
            score=float(best.score),
            freeway_ttt=float(best.freeway_ttt),
            metering_error=float(best.metering_error_sum / max(best.steps, 1)),
            queue_overflow=float(best.queue_overflow),
            density_excess=float(best.density_excess),
            min_receiving_factor=float(best.min_receiving_factor),
            steps=best.steps,
            expanded_nodes=expanded_nodes,
        )
        return best.first_ramp_metering, best.first_vsl, evaluation, projection

    def solve(
        self,
        state: TrafficState,
        leader: LeaderAction,
        demand: DemandStep | Iterable[DemandStep],
        previous_control: Optional[ControlAction] = None,
    ) -> FreewayFollowerResult:
        fc = self.cfg.freeway_follower
        forecast = self._as_forecast(demand)
        ramp_metering, vsl, evaluation, projection = self._choose_horizon_sequence(
            state,
            leader,
            forecast,
            previous_control,
        )

        metering_target_infeasible = (
            evaluation.metering_error > fc.eps_F
            or projection["target_infeasible"] > 0.0
        )
        return FreewayFollowerResult(
            ramp_metering=ramp_metering,
            vsl=vsl,
            objective_value=float(evaluation.score),
            infeasibility={
                "metering_residual": float(max(0.0, evaluation.metering_error - fc.eps_F)),
                "metering_tracking_residual": float(evaluation.metering_error),
                "metering_target_infeasible": float(metering_target_infeasible),
                "ramp_queue_overflow": float(evaluation.queue_overflow),
                "density_excess": float(evaluation.density_excess),
                "min_ramp_receiving_factor": float(min(
                    evaluation.min_receiving_factor,
                    projection["min_receiving_factor"],
                )),
                "freeway_follower_horizon_steps": float(evaluation.steps),
                "freeway_follower_sequence_optimized": 1.0,
                "freeway_follower_beam_width": float(fc.horizon_beam_width),
                "freeway_follower_expanded_nodes": float(evaluation.expanded_nodes),
                "ramp_projection_first_step_capacity": float(projection["step_capacity"]),
                "freeway_follower_coupled_prediction": 0.0,
                "freeway_follower_lightweight_prediction": 1.0,
            },
        )
