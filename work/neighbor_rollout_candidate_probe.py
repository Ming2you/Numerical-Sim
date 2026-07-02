from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.controllers.leader import LeaderAction
from src.controllers.local_signal_plant import (
    rollout_local_tts,
    rollout_local_tts_phased,
    rollout_local_tts_ramp_aware,
)
from src.controllers.relaxed_quantization import repair_green_pair
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import _urban_step_index

BASE_PATH = ROOT / "work" / "forced_leader_response_probe.py"
spec = importlib.util.spec_from_file_location("forced_leader_response_probe_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load base probe helpers from {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def clean_legacy_green(signal: str, legacy: ControlAction, cfg: ExperimentConfig) -> float:
    net = cfg.network
    legacy_p1 = float(legacy.green_times.get(f"{signal}_p1", net.effective_green_total / 2.0))
    if cfg.mpc.relaxed_quantized_controls:
        legacy_p1 = repair_green_pair(legacy_p1, cfg).p1
    else:
        legacy_p1 = min(max(legacy_p1, net.green_min), net.green_max)
        legacy_p2 = net.effective_green_total - legacy_p1
        if legacy_p2 < net.green_min:
            legacy_p1 = net.effective_green_total - net.green_min
        if legacy_p2 > net.green_max:
            legacy_p1 = net.effective_green_total - net.green_max
    return float(legacy_p1)


def distances(candidate: ControlAction, legacy: ControlAction, cfg: ExperimentConfig) -> dict[str, float]:
    net = cfg.network
    green = sum(
        abs(candidate.green_times.get(f"{signal}_p1", 0.0) - legacy.green_times.get(f"{signal}_p1", 0.0))
        for signal in net.signals
    )
    offset = sum(
        abs(candidate.offsets.get(signal, 0.0) - legacy.offsets.get(signal, 0.0))
        for signal in net.signals
    )
    ramp = sum(
        abs(candidate.ramp_metering.get(ramp_id, 0.0) - legacy.ramp_metering.get(ramp_id, 0.0))
        for ramp_id in net.ramps
    )
    vsl = sum(
        abs(candidate.vsl.get(link, 100.0) - legacy.vsl.get(link, 100.0))
        for link in net.freeway_links
    )
    return {
        "distance_green_p1_sum": float(green),
        "distance_offset_sum": float(offset),
        "distance_ramp_sum": float(ramp),
        "distance_vsl_link_sum": float(vsl),
        "distance_green_offset_sum": float(green + offset),
    }


def summarize_control(prefix: str, control: ControlAction, cfg: ExperimentConfig) -> dict[str, float]:
    net = cfg.network
    return {
        f"{prefix}_green_p1_sum": float(
            sum(control.green_times.get(f"{signal}_p1", 0.0) for signal in net.signals)
        ),
        f"{prefix}_offset_sum": float(sum(control.offsets.get(signal, 0.0) for signal in net.signals)),
        f"{prefix}_offset_active": float(
            sum(1 for signal in net.signals if abs(control.offsets.get(signal, 0.0)) > 1.0e-6)
        ),
        f"{prefix}_ramp_sum": float(sum(control.ramp_metering.get(ramp, 0.0) for ramp in net.ramps)),
        f"{prefix}_vsl_mean": float(mean(control.vsl.get(link, 100.0) for link in net.freeway_links)),
    }


def latest_choice_rows(records: list[dict[str, Any]], control_kind: str) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("control_kind") == control_kind:
            latest[str(record.get("signal", ""))] = record
    return [latest[signal] for signal in sorted(latest)]


def with_legacy_green_offset(control: ControlAction, legacy: ControlAction, cfg: ExperimentConfig) -> ControlAction:
    candidate = control.copy()
    for signal in cfg.network.signals:
        candidate.green_times[f"{signal}_p1"] = float(legacy.green_times.get(f"{signal}_p1", 0.0))
        candidate.green_times[f"{signal}_p2"] = float(legacy.green_times.get(f"{signal}_p2", 0.0))
        candidate.offsets[signal] = float(legacy.offsets.get(signal, 0.0))
    return candidate


class LegacyInjectedWuFollower(WuFaithfulFollower):
    def __init__(
        self,
        cfg: ExperimentConfig,
        legacy_control: ControlAction,
        *,
        disable_offset_guard: bool,
    ) -> None:
        super().__init__(cfg)
        self._legacy_control = legacy_control
        self.offset_enabled = True
        if disable_offset_guard:
            self.offset_keep_margin = -0.99
        cycle = max(float(cfg.network.cycle_length), 1.0e-9)
        fractions = set(float(v) for v in self.offset_fractions)
        for signal in cfg.network.signals:
            fractions.add((float(legacy_control.offsets.get(signal, 0.0)) % cycle) / cycle)
        self.offset_fractions = tuple(sorted(fractions))
        self.green_choice_records: list[dict[str, Any]] = []
        self.offset_choice_records: list[dict[str, Any]] = []

    def _urban_green_candidates(
        self,
        signal: str,
        state: TrafficState,
        coupling: Mapping[str, float],
        snapshot: ControlAction,
    ) -> list[float]:
        candidates = list(super()._urban_green_candidates(signal, state, coupling, snapshot))
        legacy_p1 = clean_legacy_green(signal, self._legacy_control, self.cfg)
        if not any(abs(legacy_p1 - existing) <= 1.0e-9 for existing in candidates):
            candidates.append(float(legacy_p1))
        return candidates

    def _solve_urban_agent_local(self, *args: Any, **kwargs: Any) -> tuple[float, float, int, float]:
        signal = str(args[0]) if args else str(kwargs.get("signal", ""))
        best_p1, best_obj, evals, best_nin = super()._solve_urban_agent_local(*args, **kwargs)
        legacy_p1 = clean_legacy_green(signal, self._legacy_control, self.cfg)
        self.green_choice_records.append(
            {
                "scoring_mode": "local",
                "control_kind": "green",
                "signal": signal,
                "selected_value": float(best_p1),
                "legacy_value": float(legacy_p1),
                "legacy_chosen": float(abs(best_p1 - legacy_p1) <= 1.0e-6),
                "selected_score": float(best_obj),
                "evals": int(evals),
            }
        )
        return best_p1, best_obj, evals, best_nin

    def _solve_offset_local(self, *args: Any, **kwargs: Any) -> tuple[float, int]:
        signal = str(args[0]) if args else str(kwargs.get("signal", ""))
        best_off, evals = super()._solve_offset_local(*args, **kwargs)
        legacy_off = float(self._legacy_control.offsets.get(signal, 0.0))
        self.offset_choice_records.append(
            {
                "scoring_mode": "local",
                "control_kind": "offset",
                "signal": signal,
                "selected_value": float(best_off),
                "legacy_value": float(legacy_off),
                "legacy_chosen": float(abs(best_off - legacy_off) <= 1.0e-6),
                "selected_score": "",
                "evals": int(evals),
            }
        )
        return best_off, evals


class NeighborScoredWuFollower(LegacyInjectedWuFollower):
    def __init__(
        self,
        cfg: ExperimentConfig,
        legacy_control: ControlAction,
        *,
        scope: str,
        disable_offset_guard: bool,
    ) -> None:
        super().__init__(cfg, legacy_control, disable_offset_guard=disable_offset_guard)
        self.scope = scope
        self._neighbors = self._build_signal_neighbors()

    def _build_signal_neighbors(self) -> dict[str, list[str]]:
        net = self.cfg.network
        signal_set = set(net.signals)
        neighbors: dict[str, set[str]] = {signal: set() for signal in net.signals}
        for signal, by_leg in net.grid_node_legs.items():
            if signal not in signal_set or not isinstance(by_leg, Mapping):
                continue
            for leg in by_leg.values():
                if not isinstance(leg, Mapping):
                    continue
                if leg.get("type") == "grid":
                    node = str(leg.get("node", ""))
                    if node in signal_set and node != signal:
                        neighbors[signal].add(node)
                        neighbors[node].add(signal)
        interface_by_freeway: dict[str, set[str]] = {}
        for movement, spec in self._specs.items():
            signal = str(spec.get("signal", ""))
            if signal not in signal_set:
                continue
            ramp = str(spec.get("ramp", ""))
            if ramp:
                link = net.ramp_to_freeway.get(ramp, "")
                if link:
                    interface_by_freeway.setdefault(link, set()).add(signal)
            off_ramp = str(spec.get("off_ramp", ""))
            if off_ramp:
                link = net.off_ramp_from_freeway.get(off_ramp, "")
                if link:
                    interface_by_freeway.setdefault(link, set()).add(signal)
        for signals in interface_by_freeway.values():
            for signal in signals:
                neighbors[signal].update(s for s in signals if s != signal)
        return {signal: sorted(values) for signal, values in neighbors.items()}

    def _scored_signals(self, signal: str) -> list[str]:
        if self.scope == "corridor":
            return list(self.cfg.network.signals)
        return [signal] + [neighbor for neighbor in self._neighbors.get(signal, []) if neighbor != signal]

    def _candidate_control_with_green(self, snapshot: ControlAction, signal: str, p1: float) -> ControlAction:
        candidate = snapshot.copy()
        candidate.green_times[f"{signal}_p1"] = float(p1)
        candidate.green_times[f"{signal}_p2"] = float(self.cfg.network.effective_green_total - p1)
        candidate.inflow_outflow_allocation = {}
        return candidate

    def _candidate_control_with_offset(self, snapshot: ControlAction, signal: str, offset: float) -> ControlAction:
        candidate = snapshot.copy()
        candidate.offsets[signal] = float(offset)
        candidate.inflow_outflow_allocation = {}
        return candidate

    def _local_score_for_signal(
        self,
        score_signal: str,
        state: TrafficState,
        candidate: ControlAction,
        demand: DemandStep,
        s_eff_frozen: Mapping[str, float],
        reservoir_drain: Mapping[str, float],
        freeway_congestion: Mapping[str, float],
    ) -> float:
        sim = self.cfg.simulation
        model = self._local_models[score_signal]
        substeps = max(1, self.cfg.mpc.horizon_steps) * max(1, sim.K_cu)
        dt_h = sim.T_u_h
        coupling = self._wu._coupling(state, candidate, demand)
        arr_movement = self._per_movement_arrivals(score_signal, state, candidate, demand)
        q0 = {m: max(0.0, state.urban_movement_queue.get(m, 0.0)) for m in model.movements}
        arr_phase = {pid: float(coupling.get(f"arr_{score_signal}_{pid}", 0.0)) for pid in ("p1", "p2")}

        offramp_inflow: dict[str, float] = {}
        offramp_contrib_phase = {"p1": 0.0, "p2": 0.0}
        if model.has_ramps:
            for off_ramp, movements in model.offramp_movements.items():
                inflow = self._frozen_offramp_inflow(off_ramp, state)
                offramp_inflow[off_ramp] = inflow
                for movement in movements:
                    offramp_contrib_phase[model.phase_of[movement]] += model.beta_of[movement] * inflow

        arr_mv: dict[str, float] = {}
        for phase_id in ("p1", "p2"):
            phase_movements = [
                movement
                for movement in model.movements
                if model.phase_of[movement] == phase_id and model.kind_of[movement] != "off_ramp"
            ]
            raw_sum = sum(max(0.0, float(arr_movement.get(movement, 0.0))) for movement in phase_movements)
            target = max(0.0, arr_phase[phase_id] - offramp_contrib_phase[phase_id])
            if raw_sum > 1.0e-12:
                scale = target / raw_sum
                for movement in phase_movements:
                    arr_mv[movement] = max(0.0, float(arr_movement.get(movement, 0.0))) * scale
            else:
                for movement in phase_movements:
                    arr_mv[movement] = 0.0

        s_eff0 = {
            model.receiving_of[movement]: float(s_eff_frozen.get(model.receiving_of[movement], 0.0))
            for movement in model.movements
            if model.receiving_of[movement]
        }
        green_p1 = float(candidate.green_times.get(f"{score_signal}_p1", self.cfg.network.effective_green_total / 2.0))
        green_p2 = float(candidate.green_times.get(f"{score_signal}_p2", self.cfg.network.effective_green_total - green_p1))

        if model.has_ramps:
            offramp_occ0 = {
                off_ramp: self._offramp_occupancy(off_ramp, state)
                for off_ramp in model.offramp_movements
            }
            ramp_queue0 = {
                ramp: max(0.0, float(state.ramp_queue.get(ramp, 0.0)))
                for ramp in model.onramp_movements
            }
            return float(
                rollout_local_tts_ramp_aware(
                    model,
                    q0,
                    arr_mv,
                    s_eff0,
                    offramp_inflow,
                    offramp_occ0,
                    ramp_queue0,
                    reservoir_drain,
                    freeway_congestion,
                    self.ramp_metering_weight,
                    green_p1,
                    green_p2,
                    substeps,
                    dt_h,
                )
            )

        start_idx = _urban_step_index(state, self.cfg)
        arr_by_substep = self._platoon_arrival_profiles(
            score_signal,
            state,
            candidate,
            demand,
            arr_mv,
            substeps,
            start_idx,
        )
        gf_by_substep = self._offset_green_fractions(
            score_signal,
            green_p1,
            float(candidate.offsets.get(score_signal, 0.0)),
            substeps,
            start_idx,
        )
        return float(
            rollout_local_tts_phased(
                model,
                q0,
                arr_by_substep,
                gf_by_substep,
                s_eff0,
                substeps,
                dt_h,
            )
        )

    def _neighbor_score(
        self,
        signal: str,
        state: TrafficState,
        candidate: ControlAction,
        demand: DemandStep,
        s_eff_frozen: Mapping[str, float],
        reservoir_drain: Mapping[str, float],
        freeway_congestion: Mapping[str, float],
    ) -> float:
        return float(
            sum(
                self._local_score_for_signal(
                    scored_signal,
                    state,
                    candidate,
                    demand,
                    s_eff_frozen,
                    reservoir_drain,
                    freeway_congestion,
                )
                for scored_signal in self._scored_signals(signal)
            )
        )

    def _solve_urban_agent_local(
        self,
        signal: str,
        state: TrafficState,
        coupling: Mapping[str, float],
        arr_movement: Mapping[str, float],
        s_eff_frozen: Mapping[str, float],
        reservoir_drain: Mapping[str, float],
        freeway_congestion: Mapping[str, float],
        previous: ControlAction,
        leader: Optional[object] = None,
        lambda_p: float = 0.0,
        forecast_arrivals: Optional[Mapping[str, float]] = None,
        horizon_h: float = 1.0,
        demand: Optional[DemandStep] = None,
    ) -> tuple[float, float, int, float]:
        if demand is None:
            return super()._solve_urban_agent_local(
                signal,
                state,
                coupling,
                arr_movement,
                s_eff_frozen,
                reservoir_drain,
                freeway_congestion,
                previous,
                leader,
                lambda_p,
                forecast_arrivals,
                horizon_h,
                demand,
            )

        net = self.cfg.network
        total = net.effective_green_total
        smooth_w = self.cfg.urban_follower.green_smoothness_weight
        prev_p1 = float(previous.green_times.get(f"{signal}_p1", total / 2.0))
        candidates = self._urban_green_candidates(signal, state, coupling, previous)
        fa = forecast_arrivals if forecast_arrivals is not None else {}
        dual_mode = leader is not None and self.use_dual_np
        legacy_mode = leader is not None and not self.use_dual_np
        n_p_star = float(getattr(leader, "N_P_star", 0.0)) if leader is not None else 0.0
        w_p = float(self.cfg.leader.w_P)
        omega_p = float(self._wu._omega_p.get(signal, 0.0))
        np_setpoint = omega_p * n_p_star
        cost_norm = max(
            1.0e-9,
            float(max(1, self.cfg.mpc.horizon_steps) * max(1, self.cfg.simulation.K_cu))
            * self.cfg.simulation.T_u_h,
        )

        best_p1 = prev_p1
        best_obj = float("inf")
        best_nin = 0.0
        evals = 0
        legacy_p1 = clean_legacy_green(signal, self._legacy_control, self.cfg)
        candidate_records: list[dict[str, Any]] = []
        for p1 in candidates:
            p2 = total - p1
            if p2 < net.green_min - 1.0e-9 or p2 > net.green_max + 1.0e-9:
                continue
            candidate = self._candidate_control_with_green(previous, signal, p1)
            score = self._neighbor_score(
                signal,
                state,
                candidate,
                demand,
                s_eff_frozen,
                reservoir_drain,
                freeway_congestion,
            )
            score += smooth_w * abs(p1 - prev_p1)
            nin = self._agent_net_inflow_veh(signal, p1, state, fa, horizon_h)
            if dual_mode:
                score += lambda_p * nin
            elif legacy_mode and w_p > 0.0:
                mean_accum = score / cost_norm
                score += w_p * max(0.0, mean_accum - np_setpoint) * cost_norm
            evals += 1
            candidate_records.append(
                {
                    "scoring_mode": f"neighbor_{self.scope}",
                    "control_kind": "green_candidate",
                    "signal": signal,
                    "candidate_value": float(p1),
                    "legacy_value": float(legacy_p1),
                    "is_legacy_candidate": float(abs(p1 - legacy_p1) <= 1.0e-6),
                    "candidate_score": float(score),
                    "scored_signal_count": len(self._scored_signals(signal)),
                }
            )
            if score < best_obj - 1.0e-9:
                best_obj = float(score)
                best_p1 = float(p1)
                best_nin = float(nin)

        legacy_score = next(
            (
                float(record["candidate_score"])
                for record in candidate_records
                if float(record["is_legacy_candidate"]) > 0.5
            ),
            "",
        )
        self.green_choice_records.append(
            {
                "scoring_mode": f"neighbor_{self.scope}",
                "control_kind": "green",
                "signal": signal,
                "selected_value": float(best_p1),
                "legacy_value": float(legacy_p1),
                "legacy_chosen": float(abs(best_p1 - legacy_p1) <= 1.0e-6),
                "selected_score": float(best_obj),
                "legacy_score": legacy_score,
                "evals": int(evals),
                "scored_signals": ",".join(self._scored_signals(signal)),
            }
        )
        self.green_choice_records.extend(candidate_records)
        return best_p1, best_obj, evals, best_nin

    def _solve_offset_local(
        self,
        signal: str,
        green_p1: float,
        state: TrafficState,
        coupling: Mapping[str, float],
        arr_movement: Mapping[str, float],
        s_eff_frozen: Mapping[str, float],
        snapshot: ControlAction,
        demand: DemandStep,
    ) -> tuple[float, int]:
        model = self._local_models[signal]
        legacy_off = float(self._legacy_control.offsets.get(signal, 0.0))
        if model.has_ramps:
            self.offset_choice_records.append(
                {
                    "scoring_mode": f"neighbor_{self.scope}",
                    "control_kind": "offset",
                    "signal": signal,
                    "selected_value": 0.0,
                    "legacy_value": legacy_off,
                    "legacy_chosen": float(abs(legacy_off) <= 1.0e-6),
                    "selected_score": "",
                    "legacy_score": "",
                    "evals": 0,
                    "scored_signals": ",".join(self._scored_signals(signal)),
                }
            )
            return 0.0, 0

        cycle = max(self.cfg.network.cycle_length, 1.0e-9)
        reservoir_drain = self._frozen_reservoir_drain(state, snapshot, demand)
        freeway_congestion = self._frozen_freeway_congestion(state)
        best_off = 0.0
        best_obj = float("inf")
        evals = 0
        candidate_records: list[dict[str, Any]] = []
        for frac in self.offset_fractions:
            offset = (float(frac) * cycle) % cycle
            candidate = self._candidate_control_with_offset(snapshot, signal, offset)
            score = self._neighbor_score(
                signal,
                state,
                candidate,
                demand,
                s_eff_frozen,
                reservoir_drain,
                freeway_congestion,
            )
            evals += 1
            candidate_records.append(
                {
                    "scoring_mode": f"neighbor_{self.scope}",
                    "control_kind": "offset_candidate",
                    "signal": signal,
                    "candidate_value": float(offset),
                    "legacy_value": legacy_off,
                    "is_legacy_candidate": float(abs(offset - legacy_off) <= 1.0e-6),
                    "candidate_score": float(score),
                    "scored_signal_count": len(self._scored_signals(signal)),
                }
            )
            if score < best_obj - 1.0e-9:
                best_obj = float(score)
                best_off = float(offset)

        legacy_score = next(
            (
                float(record["candidate_score"])
                for record in candidate_records
                if float(record["is_legacy_candidate"]) > 0.5
            ),
            "",
        )
        self.offset_choice_records.append(
            {
                "scoring_mode": f"neighbor_{self.scope}",
                "control_kind": "offset",
                "signal": signal,
                "selected_value": float(best_off),
                "legacy_value": legacy_off,
                "legacy_chosen": float(abs(best_off - legacy_off) <= 1.0e-6),
                "selected_score": float(best_obj),
                "legacy_score": legacy_score,
                "evals": int(evals),
                "scored_signals": ",".join(self._scored_signals(signal)),
            }
        )
        self.offset_choice_records.extend(candidate_records)
        return best_off, evals


def run_solver(
    cfg: ExperimentConfig,
    sim: Any,
    forecast: list[DemandStep],
    step: int,
    state_source: str,
    legacy_current: ControlAction,
    saved_pfo_current: ControlAction,
    leader: LeaderAction,
    seed_name: str,
    previous: Optional[ControlAction],
    scoring_mode: str,
    score_scope: str,
    disable_offset_guard: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if scoring_mode == "local":
        solver: LegacyInjectedWuFollower = LegacyInjectedWuFollower(
            cfg,
            legacy_current,
            disable_offset_guard=disable_offset_guard,
        )
    else:
        solver = NeighborScoredWuFollower(
            cfg,
            legacy_current,
            scope=score_scope,
            disable_offset_guard=disable_offset_guard,
        )

    start = time.perf_counter()
    result = solver.solve(sim.state.copy(), leader, forecast, previous)
    solve_time = time.perf_counter() - start
    control = result.control
    response_ttt = base.rollout_ttt(cfg, sim, control, forecast)
    response_plus_legacy = with_legacy_green_offset(control, legacy_current, cfg)
    legacy_ttt = base.rollout_ttt(cfg, sim, legacy_current, forecast)
    saved_pfo_ttt = base.rollout_ttt(cfg, sim, saved_pfo_current, forecast)
    green_choices = latest_choice_rows(solver.green_choice_records, "green")
    offset_choices = latest_choice_rows(solver.offset_choice_records, "offset")
    final_green_match_count = sum(
        abs(control.green_times.get(f"{signal}_p1", 0.0) - legacy_current.green_times.get(f"{signal}_p1", 0.0))
        <= 1.0e-6
        for signal in cfg.network.signals
    )
    final_offset_match_count = sum(
        abs(control.offsets.get(signal, 0.0) - legacy_current.offsets.get(signal, 0.0)) <= 1.0e-6
        for signal in cfg.network.signals
    )
    row: dict[str, Any] = {
        "step": step,
        "time_sec": step * cfg.simulation.control_interval,
        "state_source": state_source,
        "scoring_mode": scoring_mode,
        "score_scope": score_scope if scoring_mode == "neighbor" else "local",
        "seed_name": seed_name,
        "target_name": "legacy_target",
        "target_N_P_star": float(leader.N_P_star),
        "target_N_UF_star": float(leader.N_UF_star),
        "objective_value": float(result.objective_value),
        "response_rollout_ttt": float(response_ttt),
        "response_one_step_ttt": float(base.one_step_ttt(sim, control, forecast[0], step)),
        "response_plus_legacy_green_offset_ttt": float(base.rollout_ttt(cfg, sim, response_plus_legacy, forecast)),
        "legacy_full_rollout_ttt": float(legacy_ttt),
        "saved_pfo_full_rollout_ttt": float(saved_pfo_ttt),
        "solve_time_sec": float(solve_time),
        "iterations": float(result.iterations),
        "converged": float(result.converged),
        "green_legacy_chosen_count": float(sum(float(r.get("legacy_chosen", 0.0)) for r in green_choices)),
        "green_choice_count": float(len(green_choices)),
        "offset_legacy_chosen_count": float(sum(float(r.get("legacy_chosen", 0.0)) for r in offset_choices)),
        "offset_choice_count": float(len(offset_choices)),
        "final_green_legacy_match_count": float(final_green_match_count),
        "final_offset_legacy_match_count": float(final_offset_match_count),
        "legacy_green_offset_would_be_chosen": float(
            len(green_choices) > 0
            and len(offset_choices) > 0
            and all(float(r.get("legacy_chosen", 0.0)) > 0.5 for r in green_choices)
            and all(float(r.get("legacy_chosen", 0.0)) > 0.5 for r in offset_choices)
        ),
        "wu_faithful_offsets_searched_off_zero": float(
            control.diagnostics.get("wu_faithful_offsets_searched_off_zero", 0.0)
        ),
        "wu_faithful_offsets_off_zero": float(control.diagnostics.get("wu_faithful_offsets_off_zero", 0.0)),
        "wu_faithful_offset_evals": float(control.diagnostics.get("wu_faithful_offset_evals", 0.0)),
        **summarize_control("response", control, cfg),
        **summarize_control("legacy", legacy_current, cfg),
        **summarize_control("saved_pfo", saved_pfo_current, cfg),
        **distances(control, legacy_current, cfg),
    }

    choice_rows: list[dict[str, Any]] = []
    for record in solver.green_choice_records + solver.offset_choice_records:
        enriched = {
            "step": step,
            "time_sec": step * cfg.simulation.control_interval,
            "state_source": state_source,
            "seed_name": seed_name,
            "target_name": "legacy_target",
            **record,
        }
        choice_rows.append(enriched)
    return row, choice_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="sweet_190")
    parser.add_argument("--T-total", type=float, default=7200.0)
    parser.add_argument("--steps", default="20,35")
    parser.add_argument("--np-mode", choices=["cap", "equality"], default="cap")
    parser.add_argument("--score-scope", choices=["ego_neighbor", "corridor"], default="ego_neighbor")
    parser.add_argument("--keep-offset-guard", action="store_true")
    parser.add_argument(
        "--output",
        default="outputs/neighbor_rollout_candidate_probe_sweet190_cap_20260702",
    )
    args = parser.parse_args()

    cfg, scenario = base.build_cfg(args.scenario, args.T_total, args.np_mode)
    pfo_rows = base.read_csv(
        ROOT / "outputs/sweet190_all_boundary_halfcap_7200_20260701/runs/sweet_190/PROPOSED-FOLLOWERS-ONLY/control_timeseries.csv"
    )
    legacy_rows = base.read_csv(
        ROOT / "outputs/legacy_pstack_sweet190_7200_20260702/runs/sweet_190/LEGACY-STACKELBERG/control_timeseries.csv"
    )
    steps = [int(value.strip()) for value in args.steps.split(",") if value.strip()]
    summary_rows: list[dict[str, Any]] = []
    choice_rows: list[dict[str, Any]] = []

    for step in steps:
        pfo_sim, pfo_forecast, _ = base.replay_to_step(cfg, scenario, pfo_rows, step)
        legacy_sim, legacy_forecast, _ = base.replay_to_step(cfg, scenario, legacy_rows, step)
        for state_source, sim, forecast in (
            ("pfo_replayed_state", pfo_sim, pfo_forecast),
            ("legacy_replayed_state", legacy_sim, legacy_forecast),
        ):
            legacy_current = base.control_from_row(legacy_rows[step], cfg)
            saved_pfo_current = base.control_from_row(pfo_rows[step], cfg)
            seeds = [
                ("default_uncontrolled", ControlAction.uncontrolled(cfg)),
                ("legacy_current", legacy_current),
            ]
            leader = LeaderAction(float(legacy_current.N_P_star), float(legacy_current.N_UF_star))
            for seed_name, previous in seeds:
                for scoring_mode in ("local", "neighbor"):
                    row, choices = run_solver(
                        cfg,
                        sim,
                        forecast,
                        step,
                        state_source,
                        legacy_current,
                        saved_pfo_current,
                        leader,
                        seed_name,
                        previous,
                        scoring_mode,
                        args.score_scope,
                        disable_offset_guard=not args.keep_offset_guard,
                    )
                    summary_rows.append(row)
                    choice_rows.extend(choices)

    out = ROOT / args.output
    write_csv(out / f"neighbor_rollout_choice_details_{args.np_mode}_{args.score_scope}.csv", choice_rows)
    write_csv(out / f"neighbor_rollout_summary_{args.np_mode}_{args.score_scope}.csv", summary_rows)
    (out / f"neighbor_rollout_summary_{args.np_mode}_{args.score_scope}.json").write_text(
        json.dumps(summary_rows, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary_rows, indent=2), flush=True)


if __name__ == "__main__":
    main()
