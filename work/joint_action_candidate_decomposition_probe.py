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

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.controllers.leader import LeaderAction
from src.controllers.relaxed_quantization import repair_green_pair
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig, TrafficState, segment_vsl

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


def build_cfg(scenario_name: str, t_total: float, np_mode: str) -> tuple[ExperimentConfig, Any]:
    overrides = {
        "mpc": {
            "relaxed_quantized_controls": True,
            "grid_parallel_backend": "serial",
            "leader_search_mode": "grid",
            "stackelberg_leader_parallel_backend": "serial",
            "wu_faithful_np_coordination_mode": np_mode,
            "wu_faithful_joint_freeway_rm_vsl": True,
            "wu_faithful_joint_urban_green_offset": True,
            "wu_faithful_metering_to_urban_ramp_space": True,
            "wu_faithful_joint_marginal_price": False,
        },
        "simulation": {"T_total": float(t_total)},
    }
    cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), overrides)
    scenario = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))[scenario_name]
    return apply_scenario_network_overrides(cfg, scenario), scenario


def legacy_green_p1(signal: str, legacy: ControlAction, cfg: ExperimentConfig) -> float:
    net = cfg.network
    p1 = float(legacy.green_times.get(f"{signal}_p1", net.effective_green_total / 2.0))
    if cfg.mpc.relaxed_quantized_controls:
        return float(repair_green_pair(p1, cfg).p1)
    p1 = min(max(p1, net.green_min), net.green_max)
    p2 = net.effective_green_total - p1
    if p2 < net.green_min:
        p1 = net.effective_green_total - net.green_min
    if p2 > net.green_max:
        p1 = net.effective_green_total - net.green_max
    return float(p1)


def circular_abs_delta(value: float, reference: float, cycle: float) -> float:
    return abs(((float(value) - float(reference) + cycle / 2.0) % cycle) - cycle / 2.0)


def summarize_control(prefix: str, control: ControlAction, cfg: ExperimentConfig) -> dict[str, float]:
    net = cfg.network
    segment_values = [
        segment_vsl(control, link, i, cfg)
        for link in net.freeway_links
        for i in range(net.freeway_segments_per_link)
    ]
    return {
        f"{prefix}_ramp_sum": float(sum(control.ramp_metering.get(ramp, 0.0) for ramp in net.ramps)),
        f"{prefix}_vsl_link_mean": float(mean(control.vsl.get(link, 100.0) for link in net.freeway_links)),
        f"{prefix}_vsl_segment_mean": float(mean(segment_values)) if segment_values else 0.0,
        f"{prefix}_green_p1_sum": float(
            sum(control.green_times.get(f"{signal}_p1", 0.0) for signal in net.signals)
        ),
        f"{prefix}_offset_active": float(
            sum(1 for signal in net.signals if abs(control.offsets.get(signal, 0.0)) > 1.0e-6)
        ),
    }


def distances(candidate: ControlAction, legacy: ControlAction, cfg: ExperimentConfig) -> dict[str, float]:
    net = cfg.network
    return {
        "distance_ramp_sum": float(
            sum(abs(candidate.ramp_metering.get(r, 0.0) - legacy.ramp_metering.get(r, 0.0)) for r in net.ramps)
        ),
        "distance_vsl_link_sum": float(
            sum(abs(candidate.vsl.get(link, 100.0) - legacy.vsl.get(link, 100.0)) for link in net.freeway_links)
        ),
        "distance_vsl_segment_sum": float(
            sum(
                abs(segment_vsl(candidate, link, i, cfg) - segment_vsl(legacy, link, i, cfg))
                for link in net.freeway_links
                for i in range(net.freeway_segments_per_link)
            )
        ),
        "distance_green_p1_sum": float(
            sum(
                abs(candidate.green_times.get(f"{s}_p1", 0.0) - legacy.green_times.get(f"{s}_p1", 0.0))
                for s in net.signals
            )
        ),
        "distance_offset_sum": float(
            sum(abs(candidate.offsets.get(s, 0.0) - legacy.offsets.get(s, 0.0)) for s in net.signals)
        ),
    }


class JointActionCandidateProbeFollower(WuFaithfulFollower):
    def __init__(self, cfg: ExperimentConfig, legacy_control: ControlAction, *, inject_legacy: bool) -> None:
        super().__init__(cfg)
        self._legacy_control = legacy_control
        self._inject_legacy = bool(inject_legacy)
        self.urban_candidate_records: list[dict[str, Any]] = []
        self.urban_summary_records: list[dict[str, Any]] = []
        self.vsl_candidate_records: list[dict[str, Any]] = []
        self.rm_candidate_records: list[dict[str, Any]] = []

    def _urban_green_candidates(
        self,
        signal: str,
        state: TrafficState,
        coupling: Mapping[str, float],
        snapshot: ControlAction,
    ) -> list[float]:
        candidates = list(super()._urban_green_candidates(signal, state, coupling, snapshot))
        if self._inject_legacy:
            legacy_p1 = legacy_green_p1(signal, self._legacy_control, self.cfg)
            if not any(abs(value - legacy_p1) <= 1.0e-9 for value in candidates):
                candidates.append(float(legacy_p1))
        return candidates

    def _urban_offset_candidates(self, signal: str, snapshot: ControlAction) -> list[float]:
        candidates = list(super()._urban_offset_candidates(signal, snapshot))
        if self._inject_legacy:
            cycle = max(float(self.cfg.network.cycle_length), 1.0e-9)
            legacy_offset = float(self._legacy_control.offsets.get(signal, 0.0)) % cycle
            if not any(circular_abs_delta(value, legacy_offset, cycle) <= 1.0e-9 for value in candidates):
                candidates.append(float(legacy_offset))
        return sorted(float(v) for v in candidates)

    def _score_green_offset_candidate(
        self,
        signal: str,
        p1: float,
        offset: float,
        state: TrafficState,
        coupling: Mapping[str, float],
        arr_movement: Mapping[str, float],
        s_eff_frozen: Mapping[str, float],
        reservoir_drain: Mapping[str, float],
        freeway_congestion: Mapping[str, float],
        previous: ControlAction,
        leader: Optional[object],
        lambda_p: float,
        forecast_arrivals: Optional[Mapping[str, float]],
        horizon_h: float,
        demand: Any,
    ) -> tuple[float, float, int, float]:
        selected_p1, obj, evals, nin = WuFaithfulFollower._solve_urban_agent_local(
            self,
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
            candidates_override=[float(p1)],
            offset_override=float(offset),
        )
        prev_offset = float(previous.offsets.get(signal, 0.0))
        prev_p1 = float(previous.green_times.get(
            f"{signal}_p1", self.cfg.network.effective_green_total / 2.0
        ))
        obj += self._offset_price_cost(signal, float(offset), prev_offset)
        obj += self._joint_urban_price_cost(signal, float(p1), float(offset), prev_p1, prev_offset)
        return float(selected_p1), float(obj), int(evals), float(nin)

    def _solve_urban_agent_green_offset_local(
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
        demand: Any = None,
    ) -> tuple[float, float, float, int, float]:
        cycle = max(float(self.cfg.network.cycle_length), 1.0e-9)
        legacy_p1 = legacy_green_p1(signal, self._legacy_control, self.cfg)
        legacy_offset = float(self._legacy_control.offsets.get(signal, 0.0)) % cycle
        base_p1 = list(WuFaithfulFollower._urban_green_candidates(self, signal, state, coupling, previous))
        actual_p1 = list(self._urban_green_candidates(signal, state, coupling, previous))
        base_offsets = list(WuFaithfulFollower._urban_offset_candidates(self, signal, previous))
        actual_offsets = list(self._urban_offset_candidates(signal, previous))
        base_has_p1 = any(abs(value - legacy_p1) <= 1.0e-9 for value in base_p1)
        actual_has_p1 = any(abs(value - legacy_p1) <= 1.0e-9 for value in actual_p1)
        base_has_offset = any(circular_abs_delta(value, legacy_offset, cycle) <= 1.0e-9 for value in base_offsets)
        actual_has_offset = any(circular_abs_delta(value, legacy_offset, cycle) <= 1.0e-9 for value in actual_offsets)

        best_p1 = float(previous.green_times.get(
            f"{signal}_p1", self.cfg.network.effective_green_total / 2.0
        ))
        best_offset = float(previous.offsets.get(signal, 0.0))
        best_obj = float("inf")
        best_nin = 0.0
        evals = 0
        for offset in actual_offsets:
            p1, obj, e, nin = WuFaithfulFollower._solve_urban_agent_local(
                self,
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
                offset_override=float(offset),
            )
            obj += self._offset_price_cost(signal, float(offset), float(previous.offsets.get(signal, 0.0)))
            obj += self._joint_urban_price_cost(
                signal,
                p1,
                float(offset),
                float(previous.green_times.get(f"{signal}_p1", self.cfg.network.effective_green_total / 2.0)),
                float(previous.offsets.get(signal, 0.0)),
            )
            evals += e
            is_legacy_offset = circular_abs_delta(offset, legacy_offset, cycle) <= 1.0e-9
            is_legacy_p1 = abs(p1 - legacy_p1) <= 1.0e-9
            self.urban_candidate_records.append({
                "agent_type": "urban",
                "signal": signal,
                "mode": "inject_legacy" if self._inject_legacy else "normal",
                "candidate_offset": float(offset),
                "candidate_best_p1": float(p1),
                "candidate_obj": float(obj),
                "candidate_nin": float(nin),
                "is_legacy_offset": float(is_legacy_offset),
                "is_legacy_best_p1": float(is_legacy_p1),
                "base_has_legacy_p1": float(base_has_p1),
                "base_has_legacy_offset": float(base_has_offset),
                "actual_has_legacy_p1": float(actual_has_p1),
                "actual_has_legacy_offset": float(actual_has_offset),
            })
            if obj < best_obj - 1.0e-9:
                best_p1, best_offset, best_obj, best_nin = float(p1), float(offset), float(obj), float(nin)

        _, legacy_obj, legacy_evals, legacy_nin = self._score_green_offset_candidate(
            signal,
            legacy_p1,
            legacy_offset,
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
        self.urban_summary_records.append({
            "agent_type": "urban",
            "signal": signal,
            "mode": "inject_legacy" if self._inject_legacy else "normal",
            "base_has_legacy_p1": float(base_has_p1),
            "base_has_legacy_offset": float(base_has_offset),
            "base_has_legacy_pair": float(base_has_p1 and base_has_offset),
            "actual_has_legacy_p1": float(actual_has_p1),
            "actual_has_legacy_offset": float(actual_has_offset),
            "actual_has_legacy_pair": float(actual_has_p1 and actual_has_offset),
            "selected_p1": float(best_p1),
            "selected_offset": float(best_offset),
            "selected_obj": float(best_obj),
            "legacy_p1": float(legacy_p1),
            "legacy_offset": float(legacy_offset),
            "legacy_obj": float(legacy_obj),
            "legacy_nin": float(legacy_nin),
            "legacy_evals": float(legacy_evals),
            "legacy_beats_selected": float(legacy_obj < best_obj - 1.0e-9),
            "selected_is_legacy_pair": float(
                abs(best_p1 - legacy_p1) <= 1.0e-9
                and circular_abs_delta(best_offset, legacy_offset, cycle) <= 1.0e-9
            ),
            "legacy_minus_selected_obj": float(legacy_obj - best_obj),
            "candidate_offset_count": float(len(actual_offsets)),
            "candidate_p1_count": float(len(actual_p1)),
            "evals": float(evals),
        })
        return best_p1, best_offset, best_obj, evals, best_nin

    def _freeway_vsl_sequence_candidates(
        self,
        link: str,
        n_seg: int,
        previous: ControlAction,
        base_candidates: list[list[float]],
        horizon: int,
    ) -> list[list[list[float]]]:
        sequences = list(super()._freeway_vsl_sequence_candidates(
            link, n_seg, previous, base_candidates, horizon
        ))
        legacy_vec = [
            float(self._legacy_control.vsl.get(
                f"{link}__seg{i}",
                self._legacy_control.vsl.get(link, self.cfg.network.v_free),
            ))
            for i in range(n_seg)
        ]

        def first_matches(sequence: list[list[float]]) -> bool:
            if not sequence:
                return False
            first = sequence[0]
            return len(first) >= n_seg and all(abs(float(first[i]) - legacy_vec[i]) <= 1.0e-9 for i in range(n_seg))

        base_contains = any(first_matches(sequence) for sequence in sequences)
        if self._inject_legacy and not base_contains:
            sequences.append([list(legacy_vec) for _ in range(max(1, int(horizon)))])
        actual_contains = any(first_matches(sequence) for sequence in sequences)
        self.vsl_candidate_records.append({
            "agent_type": "freeway_vsl",
            "link": link,
            "mode": "inject_legacy" if self._inject_legacy else "normal",
            "base_contains_legacy_vsl": float(base_contains),
            "actual_contains_legacy_vsl": float(actual_contains),
            "candidate_sequence_count": float(len(sequences)),
            "legacy_vsl_mean": float(mean(legacy_vec)),
        })
        return sequences

    def _solve_freeway_agent_metered(
        self,
        link: str,
        state: TrafficState,
        coupling: Mapping[str, float],
        demand: Any,
        previous: ControlAction,
        leader: Optional[object] = None,
    ) -> tuple[dict[str, float], dict[str, float], int]:
        net = self.cfg.network
        model = self._local_freeway_models[link]
        owned_ramps = list(model.owned_ramps)
        caps = {ramp: float(net.ramp_capacity_veh_h.get(ramp, 0.0)) for ramp in owned_ramps}
        n_uf_star = float(getattr(leader, "N_UF_star", 0.0)) if leader is not None else 0.0
        omega_f = float(self._wu._omega_f.get(link, 0.0))
        budget = float(np.clip(omega_f * n_uf_star, 0.0, sum(caps.values())))
        nuf_mode = str(getattr(self.cfg.mpc, "wu_faithful_nuf_coordination_mode", "equality"))
        legacy_meter = {
            ramp: float(self._legacy_control.ramp_metering.get(ramp, caps[ramp]))
            for ramp in owned_ramps
        }
        legacy_sum = sum(legacy_meter.values())
        grid_contains = False
        feasible_sum = abs(legacy_sum - budget) <= 1.0e-6
        if leader is None:
            feasible_sum = True
        elif nuf_mode == "cap":
            feasible_sum = legacy_sum <= budget + 1.0e-6
        if not owned_ramps:
            grid_contains = True
        elif leader is None:
            lattice = {
                ramp: {
                    float(np.clip(frac * caps[ramp], 0.0, caps[ramp]))
                    for frac in self.ramp_metering_fractions
                }
                | {float(np.clip(previous.ramp_metering.get(ramp, caps[ramp]), 0.0, caps[ramp]))}
                for ramp in owned_ramps
            }
            grid_contains = all(
                any(abs(value - legacy_meter[ramp]) <= 1.0e-6 for value in lattice[ramp])
                for ramp in owned_ramps
            )
        elif nuf_mode == "equality" and len(owned_ramps) == 1:
            grid_contains = feasible_sum
        elif nuf_mode == "equality" and len(owned_ramps) >= 2:
            r1, r2 = owned_ramps[0], owned_ramps[1]
            lo = max(0.0, budget - caps[r2])
            hi = min(caps[r1], budget)
            split_count = self.joint_metering_split_count if self.joint_freeway_rm_vsl else 7
            splits = [lo] if hi - lo <= 1.0e-9 else [float(v) for v in np.linspace(lo, hi, split_count)]
            grid_contains = feasible_sum and any(abs(value - legacy_meter[r1]) <= 1.0e-6 for value in splits)
        else:
            grid_contains = feasible_sum

        vsl_dict, meter_dict, evals = super()._solve_freeway_agent_metered(
            link, state, coupling, demand, previous, leader
        )
        selected_sum = sum(float(meter_dict.get(ramp, 0.0)) for ramp in owned_ramps)
        selected_vsl_mean = mean(
            float(vsl_dict.get(f"{link}__seg{i}", segment_vsl(previous, link, i, self.cfg)))
            for i in range(model.n_seg)
        )
        legacy_vsl_mean = mean(
            float(self._legacy_control.vsl.get(
                f"{link}__seg{i}",
                self._legacy_control.vsl.get(link, self.cfg.network.v_free),
            ))
            for i in range(model.n_seg)
        )
        self.rm_candidate_records.append({
            "agent_type": "freeway_rm",
            "link": link,
            "mode": "inject_legacy" if self._inject_legacy else "normal",
            "owned_ramp_count": float(len(owned_ramps)),
            "budget": float(budget),
            "legacy_ramp_sum": float(legacy_sum),
            "selected_ramp_sum": float(selected_sum),
            "legacy_sum_feasible": float(feasible_sum),
            "legacy_rm_grid_contains": float(grid_contains),
            "selected_vsl_mean": float(selected_vsl_mean),
            "legacy_vsl_mean": float(legacy_vsl_mean),
            "vsl_mean_delta_selected_minus_legacy": float(selected_vsl_mean - legacy_vsl_mean),
            "evals": float(evals),
        })
        return vsl_dict, meter_dict, evals


def run_solver(
    cfg: ExperimentConfig,
    sim: Any,
    forecast: list[Any],
    step: int,
    state_source: str,
    legacy_current: ControlAction,
    saved_pfo_current: ControlAction,
    previous: Optional[ControlAction],
    mode: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    leader = LeaderAction(float(legacy_current.N_P_star), float(legacy_current.N_UF_star))
    solver = JointActionCandidateProbeFollower(
        cfg,
        legacy_current,
        inject_legacy=(mode == "inject_legacy"),
    )
    start = time.perf_counter()
    result = solver.solve(sim.state.copy(), leader, forecast, previous)
    solve_time = time.perf_counter() - start
    control = result.control
    response_ttt = base.rollout_ttt(cfg, sim, control, forecast)
    legacy_ttt = base.rollout_ttt(cfg, sim, legacy_current, forecast)
    pfo_ttt = base.rollout_ttt(cfg, sim, saved_pfo_current, forecast)
    urban_summary = solver.urban_summary_records
    summary = {
        "step": step,
        "time_sec": step * cfg.simulation.control_interval,
        "state_source": state_source,
        "mode": mode,
        "target_N_P_star": float(leader.N_P_star),
        "target_N_UF_star": float(leader.N_UF_star),
        "objective_value": float(result.objective_value),
        "response_rollout_ttt": float(response_ttt),
        "legacy_rollout_ttt": float(legacy_ttt),
        "saved_pfo_rollout_ttt": float(pfo_ttt),
        "response_minus_legacy_ttt": float(response_ttt - legacy_ttt),
        "response_minus_pfo_ttt": float(response_ttt - pfo_ttt),
        "solve_time_sec": float(solve_time),
        "iterations": float(result.iterations),
        "converged": float(result.converged),
        "urban_signal_count": float(len(urban_summary)),
        "urban_base_has_legacy_pair_count": float(sum(r["base_has_legacy_pair"] for r in urban_summary)),
        "urban_actual_has_legacy_pair_count": float(sum(r["actual_has_legacy_pair"] for r in urban_summary)),
        "urban_selected_legacy_pair_count": float(sum(r["selected_is_legacy_pair"] for r in urban_summary)),
        "urban_legacy_beats_selected_count": float(sum(r["legacy_beats_selected"] for r in urban_summary)),
        "urban_legacy_minus_selected_obj_sum": float(
            sum(float(r["legacy_minus_selected_obj"]) for r in urban_summary)
        ),
        "vsl_link_call_count": float(len(solver.vsl_candidate_records)),
        "vsl_base_contains_legacy_count": float(
            sum(r["base_contains_legacy_vsl"] for r in solver.vsl_candidate_records)
        ),
        "vsl_actual_contains_legacy_count": float(
            sum(r["actual_contains_legacy_vsl"] for r in solver.vsl_candidate_records)
        ),
        "rm_link_call_count": float(len(solver.rm_candidate_records)),
        "rm_legacy_sum_feasible_count": float(sum(r["legacy_sum_feasible"] for r in solver.rm_candidate_records)),
        "rm_legacy_grid_contains_count": float(sum(r["legacy_rm_grid_contains"] for r in solver.rm_candidate_records)),
        **summarize_control("response", control, cfg),
        **summarize_control("legacy", legacy_current, cfg),
        **summarize_control("saved_pfo", saved_pfo_current, cfg),
        **distances(control, legacy_current, cfg),
    }
    context = {
        "step": step,
        "time_sec": step * cfg.simulation.control_interval,
        "state_source": state_source,
        "mode": mode,
    }
    return (
        summary,
        [dict(context, **row) for row in solver.urban_summary_records],
        [dict(context, **row) for row in solver.urban_candidate_records],
        [dict(context, **row) for row in solver.vsl_candidate_records],
        [dict(context, **row) for row in solver.rm_candidate_records],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="sweet_190")
    parser.add_argument("--T-total", type=float, default=7200.0)
    parser.add_argument("--steps", default="20,35")
    parser.add_argument("--np-mode", choices=["cap", "equality"], default="cap")
    parser.add_argument(
        "--data-root",
        default=r"C:\Users\alsrj\Documents\Numerical Simulation",
        help="Root containing historical outputs.",
    )
    parser.add_argument(
        "--current-run",
        default="outputs/joint_wu_faithful_sweet190_7200_20260706",
        help="Current joint-action run under data-root.",
    )
    parser.add_argument(
        "--legacy-run",
        default="outputs/legacy_pstack_sweet190_7200_20260702",
        help="Legacy P-Stack run under data-root.",
    )
    parser.add_argument(
        "--output",
        default="outputs/joint_action_candidate_decomposition_probe_sweet190_step20_35_20260706",
    )
    parser.add_argument("--state-source", choices=["legacy", "pfo", "both"], default="legacy")
    parser.add_argument("--seed", choices=["legacy_current", "default"], default="legacy_current")
    args = parser.parse_args()

    cfg, scenario = build_cfg(args.scenario, args.T_total, args.np_mode)
    data_root = Path(args.data_root)
    legacy_rows = base.read_csv(
        data_root / args.legacy_run / "runs" / args.scenario / "LEGACY-STACKELBERG" / "control_timeseries.csv"
    )
    pfo_rows = base.read_csv(
        data_root / args.current_run / "runs" / args.scenario / "PROPOSED-FOLLOWERS-ONLY" / "control_timeseries.csv"
    )
    steps = [int(value.strip()) for value in args.steps.split(",") if value.strip()]

    summary_rows: list[dict[str, Any]] = []
    urban_summary_rows: list[dict[str, Any]] = []
    urban_candidate_rows: list[dict[str, Any]] = []
    vsl_rows: list[dict[str, Any]] = []
    rm_rows: list[dict[str, Any]] = []
    for step in steps:
        pfo_sim, pfo_forecast, _ = base.replay_to_step(cfg, scenario, pfo_rows, step)
        legacy_sim, legacy_forecast, _ = base.replay_to_step(cfg, scenario, legacy_rows, step)
        sources = []
        if args.state_source in ("legacy", "both"):
            sources.append(("legacy_replayed_state", legacy_sim, legacy_forecast))
        if args.state_source in ("pfo", "both"):
            sources.append(("pfo_replayed_state", pfo_sim, pfo_forecast))
        for state_source, sim, forecast in sources:
            legacy_current = base.control_from_row(legacy_rows[step], cfg)
            saved_pfo_current = base.control_from_row(pfo_rows[step], cfg)
            previous = legacy_current if args.seed == "legacy_current" else ControlAction.uncontrolled(cfg)
            for mode in ("normal", "inject_legacy"):
                summary, urban_summary, urban_candidates, vsl, rm = run_solver(
                    cfg,
                    sim,
                    forecast,
                    step,
                    state_source,
                    legacy_current,
                    saved_pfo_current,
                    previous,
                    mode,
                )
                summary_rows.append(summary)
                urban_summary_rows.extend(urban_summary)
                urban_candidate_rows.extend(urban_candidates)
                vsl_rows.extend(vsl)
                rm_rows.extend(rm)

    out = data_root / args.output
    write_csv(out / "summary.csv", summary_rows)
    write_csv(out / "urban_summary.csv", urban_summary_rows)
    write_csv(out / "urban_candidates.csv", urban_candidate_rows)
    write_csv(out / "vsl_candidates.csv", vsl_rows)
    write_csv(out / "rm_candidates.csv", rm_rows)
    (out / "summary.json").write_text(json.dumps(summary_rows, indent=2), encoding="utf-8")
    print(json.dumps(summary_rows, indent=2), flush=True)


if __name__ == "__main__":
    main()
