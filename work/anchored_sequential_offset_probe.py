from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.controllers.leader import LeaderAction
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState

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


class OffsetEnabledWuFollower(WuFaithfulFollower):
    """Diagnostic copy: enable sequential offset best-response without legacy guide."""

    def __init__(
        self,
        cfg: ExperimentConfig,
        *,
        offset_anchor: str = "",
        disable_offset_guard: bool = True,
    ) -> None:
        super().__init__(cfg)
        self.offset_enabled = True
        self.offset_anchor = offset_anchor
        self.offset_choice_records: list[dict[str, Any]] = []
        if disable_offset_guard:
            self.offset_keep_margin = -0.99

    def _solve_offset_local(
        self,
        signal: str,
        green_p1: float,
        state: TrafficState,
        coupling: dict[str, float],
        arr_movement: dict[str, float],
        s_eff_frozen: dict[str, float],
        snapshot: ControlAction,
        demand: DemandStep,
    ) -> tuple[float, int]:
        if self.offset_anchor and signal == self.offset_anchor:
            self.offset_choice_records.append(
                {
                    "signal": signal,
                    "selected_offset": 0.0,
                    "evals": 0,
                    "anchor_fixed": 1.0,
                    "model_has_ramps": float(self._local_models[signal].has_ramps),
                }
            )
            return 0.0, 0
        offset, evals = super()._solve_offset_local(
            signal,
            green_p1,
            state,
            coupling,
            arr_movement,
            s_eff_frozen,
            snapshot,
            demand,
        )
        self.offset_choice_records.append(
            {
                "signal": signal,
                "selected_offset": float(offset),
                "evals": int(evals),
                "anchor_fixed": 0.0,
                "model_has_ramps": float(self._local_models[signal].has_ramps),
            }
        )
        return offset, evals


def make_solver(cfg: ExperimentConfig, mode: str, anchor: str) -> WuFaithfulFollower:
    if mode == "offset_off":
        return WuFaithfulFollower(cfg)
    if mode == "offset_free":
        return OffsetEnabledWuFollower(cfg, offset_anchor="", disable_offset_guard=True)
    if mode == "offset_anchor":
        return OffsetEnabledWuFollower(cfg, offset_anchor=anchor, disable_offset_guard=True)
    raise ValueError(f"Unknown mode {mode!r}")


def run_solver(
    cfg: ExperimentConfig,
    sim: Any,
    forecast: list[Any],
    step: int,
    state_source: str,
    legacy_current: ControlAction,
    saved_pfo_current: ControlAction,
    leader: LeaderAction,
    previous: ControlAction,
    mode: str,
    anchor: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    solver = make_solver(cfg, mode, anchor)
    start = time.perf_counter()
    result = solver.solve(sim.state.copy(), leader, forecast, previous)
    solve_time = time.perf_counter() - start
    control = result.control
    response_ttt = base.rollout_ttt(cfg, sim, control, forecast)
    legacy_ttt = base.rollout_ttt(cfg, sim, legacy_current, forecast)
    saved_pfo_ttt = base.rollout_ttt(cfg, sim, saved_pfo_current, forecast)
    row = {
        "step": step,
        "time_sec": step * cfg.simulation.control_interval,
        "state_source": state_source,
        "mode": mode,
        "offset_anchor": anchor if mode == "offset_anchor" else "",
        "target_N_P_star": float(leader.N_P_star),
        "target_N_UF_star": float(leader.N_UF_star),
        "objective_value": float(result.objective_value),
        "response_rollout_ttt": float(response_ttt),
        "response_one_step_ttt": float(base.one_step_ttt(sim, control, forecast[0], step)),
        "legacy_full_rollout_ttt": float(legacy_ttt),
        "saved_pfo_full_rollout_ttt": float(saved_pfo_ttt),
        "solve_time_sec": float(solve_time),
        "iterations": float(result.iterations),
        "converged": float(result.converged),
        "offset_active_count": float(sum(1 for signal in cfg.network.signals if abs(control.offsets.get(signal, 0.0)) > 1.0e-6)),
        **neighbor_base.summarize_control("response", control, cfg),
        **neighbor_base.summarize_control("legacy", legacy_current, cfg),
        **neighbor_base.summarize_control("saved_pfo", saved_pfo_current, cfg),
        **neighbor_base.distances(control, legacy_current, cfg),
    }
    choices: list[dict[str, Any]] = []
    for record in getattr(solver, "offset_choice_records", []):
        choices.append(
            {
                "step": step,
                "time_sec": step * cfg.simulation.control_interval,
                "state_source": state_source,
                "mode": mode,
                "offset_anchor": anchor if mode == "offset_anchor" else "",
                **record,
            }
        )
    return row, choices


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="sweet_190")
    parser.add_argument("--T-total", type=float, default=7200.0)
    parser.add_argument("--steps", default="20,35")
    parser.add_argument("--np-mode", choices=["cap", "equality"], default="cap")
    parser.add_argument(
        "--state-sources",
        default="pfo_replayed_state",
        help="Comma-separated replayed states: pfo_replayed_state,legacy_replayed_state.",
    )
    parser.add_argument(
        "--modes",
        default="offset_off,offset_free,offset_anchor",
        help="Comma-separated modes: offset_off,offset_free,offset_anchor.",
    )
    parser.add_argument("--anchors", default="A", help="Comma-separated anchors for offset_anchor mode.")
    parser.add_argument("--seed", choices=["default_uncontrolled", "legacy_current"], default="default_uncontrolled")
    parser.add_argument("--output", default="outputs/anchored_sequential_offset_probe_sweet190_cap_20260702")
    args = parser.parse_args()

    cfg, scenario = base.build_cfg(args.scenario, args.T_total, args.np_mode)
    pfo_rows = base.read_csv(
        ROOT / "outputs/sweet190_all_boundary_halfcap_7200_20260701/runs/sweet_190/PROPOSED-FOLLOWERS-ONLY/control_timeseries.csv"
    )
    legacy_rows = base.read_csv(
        ROOT / "outputs/legacy_pstack_sweet190_7200_20260702/runs/sweet_190/LEGACY-STACKELBERG/control_timeseries.csv"
    )
    enabled_states = {value.strip() for value in args.state_sources.split(",") if value.strip()}
    modes = [value.strip() for value in args.modes.split(",") if value.strip()]
    anchors = [value.strip() for value in args.anchors.split(",") if value.strip()]
    summary_rows: list[dict[str, Any]] = []
    choice_rows: list[dict[str, Any]] = []
    for step in [int(value.strip()) for value in args.steps.split(",") if value.strip()]:
        pfo_sim, pfo_forecast, _ = base.replay_to_step(cfg, scenario, pfo_rows, step)
        legacy_sim, legacy_forecast, _ = base.replay_to_step(cfg, scenario, legacy_rows, step)
        for state_source, sim, forecast in (
            ("pfo_replayed_state", pfo_sim, pfo_forecast),
            ("legacy_replayed_state", legacy_sim, legacy_forecast),
        ):
            if state_source not in enabled_states:
                continue
            legacy_current = base.control_from_row(legacy_rows[step], cfg)
            saved_pfo_current = base.control_from_row(pfo_rows[step], cfg)
            previous = ControlAction.uncontrolled(cfg) if args.seed == "default_uncontrolled" else legacy_current
            leader = LeaderAction(float(legacy_current.N_P_star), float(legacy_current.N_UF_star))
            for mode in modes:
                mode_anchors = anchors if mode == "offset_anchor" else [""]
                for anchor in mode_anchors:
                    row, choices = run_solver(
                        cfg,
                        sim,
                        forecast,
                        step,
                        state_source,
                        legacy_current,
                        saved_pfo_current,
                        leader,
                        previous,
                        mode,
                        anchor,
                    )
                    summary_rows.append(row)
                    choice_rows.extend(choices)

    out = ROOT / args.output
    write_csv(out / "anchored_sequential_offset_summary.csv", summary_rows)
    write_csv(out / "anchored_sequential_offset_choices.csv", choice_rows)
    (out / "anchored_sequential_offset_summary.json").write_text(
        json.dumps(summary_rows, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary_rows, indent=2), flush=True)


if __name__ == "__main__":
    main()
