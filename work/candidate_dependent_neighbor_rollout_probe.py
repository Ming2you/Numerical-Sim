from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.controllers.leader import LeaderAction
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    _urban_step_index,
    sync_onramp_queues_from_freeway,
    urban_substep,
)

NEIGHBOR_PATH = ROOT / "work" / "neighbor_rollout_candidate_probe.py"
spec = importlib.util.spec_from_file_location("neighbor_rollout_candidate_probe_base", NEIGHBOR_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load neighbor probe helpers from {NEIGHBOR_PATH}")
neighbor_base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(neighbor_base)

base = neighbor_base.base


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


class CandidateDependentNeighborWuFollower(neighbor_base.NeighborScoredWuFollower):
    """Diagnostic Wu-faithful follower with candidate-dependent neighbor scoring.

    This intentionally stays outside production code.  For each ego signal
    candidate, it freezes all controls except that candidate, rolls a copy of
    the urban plant, and scores the ego + one-hop neighbor vehicle TTS from the
    resulting state trajectory.  Neighbor controls are fixed, but neighbor
    queues/storage are allowed to change under the ego candidate.
    """

    def __init__(
        self,
        cfg: ExperimentConfig,
        legacy_control: ControlAction,
        *,
        scope: str,
        disable_offset_guard: bool,
    ) -> None:
        super().__init__(
            cfg,
            legacy_control,
            scope=scope,
            disable_offset_guard=disable_offset_guard,
        )
        self.actual_scope = scope
        self.scope = f"candidate_dependent_{scope}"

    def _scored_signals(self, signal: str) -> list[str]:
        if self.actual_scope == "corridor":
            return list(self.cfg.network.signals)
        return [signal] + [neighbor for neighbor in self._neighbors.get(signal, []) if neighbor != signal]

    def _scope_sets(self, scored_signals: list[str]) -> tuple[set[str], set[str], set[str]]:
        net = self.cfg.network
        movements: set[str] = set()
        storage_links: set[str] = set()
        ramps: set[str] = set()
        for scored_signal in scored_signals:
            model = self._local_models[scored_signal]
            movements.update(model.movements)
            ramps.update(model.onramp_movements.keys())
            for off_ramp in model.offramp_movements:
                storage = net.off_ramp_storage_link.get(off_ramp, "")
                if storage:
                    storage_links.add(storage)
            for movement in model.movements:
                origin = str(model.origin_of.get(movement, ""))
                receiving = str(model.receiving_of.get(movement, ""))
                if origin in net.urban_link_storage_veh:
                    storage_links.add(origin)
                if receiving in net.urban_link_storage_veh:
                    storage_links.add(receiving)
        return movements, storage_links, ramps

    def _scoped_vehicle_count(
        self,
        state: TrafficState,
        movements: set[str],
        storage_links: set[str],
        ramps: set[str],
    ) -> float:
        net = self.cfg.network
        total = sum(max(0.0, float(state.urban_movement_queue.get(movement, 0.0))) for movement in movements)
        for link in storage_links:
            cap = float(net.urban_link_storage_veh.get(link, 0.0))
            total += max(0.0, cap - float(state.urban_link_storage.get(link, cap)))
        for ramp in ramps:
            total += max(0.0, float(state.ramp_queue.get(ramp, 0.0)))
        return float(total)

    def _candidate_dependent_neighbor_tts(
        self,
        signal: str,
        state: TrafficState,
        candidate: ControlAction,
        demand: DemandStep,
        reservoir_drain: Mapping[str, float],
    ) -> float:
        sim = self.cfg.simulation
        scored_signals = self._scored_signals(signal)
        movements, storage_links, ramps = self._scope_sets(scored_signals)
        probe_state = state.copy()
        sync_onramp_queues_from_freeway(probe_state, self.cfg)
        start_idx = _urban_step_index(probe_state, self.cfg)
        substeps = max(1, self.cfg.mpc.horizon_steps) * max(1, sim.K_cu)
        cost = 0.0
        for sub in range(substeps):
            urban_substep(
                probe_state,
                candidate,
                demand,
                self.cfg,
                urban_step_index=start_idx + sub,
                ramp_release_veh_h=reservoir_drain,
            )
            cost += self._scoped_vehicle_count(probe_state, movements, storage_links, ramps) * sim.T_u_h
        return float(cost)

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
        del s_eff_frozen, freeway_congestion
        return self._candidate_dependent_neighbor_tts(signal, state, candidate, demand, reservoir_drain)


def latest_choice_rows(records: list[dict[str, Any]], control_kind: str) -> list[dict[str, Any]]:
    return neighbor_base.latest_choice_rows(records, control_kind)


def with_legacy_green_offset(control: ControlAction, legacy: ControlAction, cfg: ExperimentConfig) -> ControlAction:
    return neighbor_base.with_legacy_green_offset(control, legacy, cfg)


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
        solver = neighbor_base.LegacyInjectedWuFollower(
            cfg,
            legacy_current,
            disable_offset_guard=disable_offset_guard,
        )
    elif scoring_mode == "candidate_dependent_neighbor":
        solver = CandidateDependentNeighborWuFollower(
            cfg,
            legacy_current,
            scope=score_scope,
            disable_offset_guard=disable_offset_guard,
        )
    else:
        raise ValueError(f"unknown scoring_mode: {scoring_mode}")

    start = time.perf_counter()
    result = solver.solve(sim.state.copy(), leader, forecast, previous)
    solve_time = time.perf_counter() - start
    control = result.control
    response_plus_legacy = with_legacy_green_offset(control, legacy_current, cfg)
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
        "score_scope": score_scope if scoring_mode != "local" else "local",
        "seed_name": seed_name,
        "target_name": "legacy_target",
        "target_N_P_star": float(leader.N_P_star),
        "target_N_UF_star": float(leader.N_UF_star),
        "objective_value": float(result.objective_value),
        "response_rollout_ttt": float(base.rollout_ttt(cfg, sim, control, forecast)),
        "response_one_step_ttt": float(base.one_step_ttt(sim, control, forecast[0], step)),
        "response_plus_legacy_green_offset_ttt": float(base.rollout_ttt(cfg, sim, response_plus_legacy, forecast)),
        "legacy_full_rollout_ttt": float(base.rollout_ttt(cfg, sim, legacy_current, forecast)),
        "saved_pfo_full_rollout_ttt": float(base.rollout_ttt(cfg, sim, saved_pfo_current, forecast)),
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
        **neighbor_base.summarize_control("response", control, cfg),
        **neighbor_base.summarize_control("legacy", legacy_current, cfg),
        **neighbor_base.summarize_control("saved_pfo", saved_pfo_current, cfg),
        **neighbor_base.distances(control, legacy_current, cfg),
    }

    choice_rows: list[dict[str, Any]] = []
    for record in solver.green_choice_records + solver.offset_choice_records:
        choice_rows.append(
            {
                "step": step,
                "time_sec": step * cfg.simulation.control_interval,
                "state_source": state_source,
                "seed_name": seed_name,
                "target_name": "legacy_target",
                **record,
            }
        )
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
        default="outputs/candidate_dependent_neighbor_rollout_probe_sweet190_cap_20260702",
    )
    args = parser.parse_args()

    cfg, scenario = base.build_cfg(args.scenario, args.T_total, args.np_mode)
    pfo_rows = base.read_csv(
        ROOT
        / "outputs/sweet190_all_boundary_halfcap_7200_20260701/runs/sweet_190/PROPOSED-FOLLOWERS-ONLY/control_timeseries.csv"
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
            leader = LeaderAction(float(legacy_current.N_P_star), float(legacy_current.N_UF_star))
            seeds = [
                ("default_uncontrolled", ControlAction.uncontrolled(cfg)),
                ("legacy_current", legacy_current),
            ]
            for seed_name, previous in seeds:
                for scoring_mode in ("local", "candidate_dependent_neighbor"):
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
    write_csv(out / f"candidate_dependent_neighbor_choice_details_{args.np_mode}_{args.score_scope}.csv", choice_rows)
    write_csv(out / f"candidate_dependent_neighbor_summary_{args.np_mode}_{args.score_scope}.csv", summary_rows)
    (out / f"candidate_dependent_neighbor_summary_{args.np_mode}_{args.score_scope}.json").write_text(
        json.dumps(summary_rows, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary_rows, indent=2), flush=True)


if __name__ == "__main__":
    main()
