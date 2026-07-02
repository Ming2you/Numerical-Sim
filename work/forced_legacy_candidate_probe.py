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
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.demand import DemandStep

BASE_PATH = ROOT / "work" / "forced_leader_response_probe.py"
spec = importlib.util.spec_from_file_location("forced_leader_response_probe_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load base probe helpers from {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class LegacyCandidateWuFaithfulFollower(WuFaithfulFollower):
    def __init__(
        self,
        cfg: ExperimentConfig,
        legacy_control: ControlAction,
        *,
        inject_green: bool,
        inject_offset: bool,
        disable_offset_guard: bool,
    ):
        super().__init__(cfg)
        self._legacy_control = legacy_control
        self._inject_green = bool(inject_green)
        self._inject_offset = bool(inject_offset)
        self.offset_enabled = bool(inject_offset)
        if disable_offset_guard:
            self.offset_keep_margin = -0.99
        if inject_offset:
            cycle = max(float(cfg.network.cycle_length), 1.0e-9)
            fractions = set(float(v) for v in self.offset_fractions)
            for signal in cfg.network.signals:
                fractions.add((float(legacy_control.offsets.get(signal, 0.0)) % cycle) / cycle)
            self.offset_fractions = tuple(sorted(fractions))

    def _urban_green_candidates(self, signal, state, coupling, snapshot):  # type: ignore[no-untyped-def]
        candidates = list(super()._urban_green_candidates(signal, state, coupling, snapshot))
        if self._inject_green:
            net = self.cfg.network
            legacy_p1 = float(
                self._legacy_control.green_times.get(f"{signal}_p1", net.effective_green_total / 2.0)
            )
            legacy_p1 = min(max(legacy_p1, net.green_min), net.green_max)
            legacy_p2 = net.effective_green_total - legacy_p1
            if legacy_p2 < net.green_min:
                legacy_p1 = net.effective_green_total - net.green_min
            if legacy_p2 > net.green_max:
                legacy_p1 = net.effective_green_total - net.green_max
            if not any(abs(legacy_p1 - existing) <= 1.0e-9 for existing in candidates):
                candidates.append(float(legacy_p1))
        return candidates


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def summarize(prefix: str, control: ControlAction, cfg: ExperimentConfig) -> dict[str, float]:
    net = cfg.network
    return {
        f"{prefix}_ramp_sum": float(sum(control.ramp_metering.get(r, 0.0) for r in net.ramps)),
        f"{prefix}_offset_active": float(
            sum(1 for s in net.signals if abs(control.offsets.get(s, 0.0)) > 1.0e-6)
        ),
        f"{prefix}_green_p1_sum": float(sum(control.green_times.get(f"{s}_p1", 0.0) for s in net.signals)),
        f"{prefix}_vsl_link_mean": float(
            sum(control.vsl.get(link, 100.0) for link in net.freeway_links)
            / max(len(net.freeway_links), 1)
        ),
    }


def signal_distances(control: ControlAction, legacy: ControlAction, cfg: ExperimentConfig) -> dict[str, float]:
    net = cfg.network
    return {
        "distance_green_p1_sum": float(
            sum(
                abs(control.green_times.get(f"{s}_p1", 0.0) - legacy.green_times.get(f"{s}_p1", 0.0))
                for s in net.signals
            )
        ),
        "distance_offset_sum": float(
            sum(abs(control.offsets.get(s, 0.0) - legacy.offsets.get(s, 0.0)) for s in net.signals)
        ),
        "distance_ramp_sum": float(
            sum(abs(control.ramp_metering.get(r, 0.0) - legacy.ramp_metering.get(r, 0.0)) for r in net.ramps)
        ),
        "distance_vsl_link_sum": float(
            sum(abs(control.vsl.get(link, 100.0) - legacy.vsl.get(link, 100.0)) for link in net.freeway_links)
        ),
    }


def with_legacy_parts(
    control: ControlAction,
    legacy: ControlAction,
    cfg: ExperimentConfig,
    *,
    green: bool,
    offset: bool,
) -> ControlAction:
    candidate = control.copy()
    if green:
        for signal in cfg.network.signals:
            candidate.green_times[f"{signal}_p1"] = float(legacy.green_times.get(f"{signal}_p1", 0.0))
            candidate.green_times[f"{signal}_p2"] = float(legacy.green_times.get(f"{signal}_p2", 0.0))
    if offset:
        for signal in cfg.network.signals:
            candidate.offsets[signal] = float(legacy.offsets.get(signal, 0.0))
    return candidate


def run_probe(
    cfg: ExperimentConfig,
    sim,
    forecast: list[DemandStep],
    step: int,
    state_source: str,
    legacy_current: ControlAction,
    saved_pfo_current: ControlAction,
    target_name: str,
    leader: LeaderAction,
    seed_name: str,
    previous: Optional[ControlAction],
    mode: str,
    inject_green: bool,
    inject_offset: bool,
    disable_offset_guard: bool,
) -> dict[str, Any]:
    solver = LegacyCandidateWuFaithfulFollower(
        cfg,
        legacy_current,
        inject_green=inject_green,
        inject_offset=inject_offset,
        disable_offset_guard=disable_offset_guard,
    )
    started = time.perf_counter()
    result = solver.solve(sim.state.copy(), leader, forecast, previous)
    solve_time = time.perf_counter() - started
    control = result.control
    response_ttt = base.rollout_ttt(cfg, sim, control, forecast)
    response_legacy_green = with_legacy_parts(control, legacy_current, cfg, green=True, offset=False)
    response_legacy_offset = with_legacy_parts(control, legacy_current, cfg, green=False, offset=True)
    response_legacy_both = with_legacy_parts(control, legacy_current, cfg, green=True, offset=True)
    legacy_full_ttt = base.rollout_ttt(cfg, sim, legacy_current, forecast)
    saved_pfo_ttt = base.rollout_ttt(cfg, sim, saved_pfo_current, forecast)
    row: dict[str, Any] = {
        "step": step,
        "time_sec": step * cfg.simulation.control_interval,
        "state_source": state_source,
        "target_name": target_name,
        "seed_name": seed_name,
        "mode": mode,
        "target_N_P_star": leader.N_P_star,
        "target_N_UF_star": leader.N_UF_star,
        "objective_value": result.objective_value,
        "response_rollout_ttt": response_ttt,
        "response_one_step_ttt": base.one_step_ttt(sim, control, forecast[0], step),
        "response_plus_legacy_green_ttt": base.rollout_ttt(cfg, sim, response_legacy_green, forecast),
        "response_plus_legacy_offset_ttt": base.rollout_ttt(cfg, sim, response_legacy_offset, forecast),
        "response_plus_legacy_green_offset_ttt": base.rollout_ttt(cfg, sim, response_legacy_both, forecast),
        "legacy_full_ttt": legacy_full_ttt,
        "saved_pfo_ttt": saved_pfo_ttt,
        "solve_time_sec": solve_time,
        "iterations": result.iterations,
        "converged": float(result.converged),
        "wu_faithful_offsets_searched_off_zero": float(
            control.diagnostics.get("wu_faithful_offsets_searched_off_zero", 0.0)
        ),
        "wu_faithful_offsets_off_zero": float(control.diagnostics.get("wu_faithful_offsets_off_zero", 0.0)),
        "wu_faithful_offset_evals": float(control.diagnostics.get("wu_faithful_offset_evals", 0.0)),
        **summarize("response", control, cfg),
        **summarize("legacy", legacy_current, cfg),
        **summarize("saved_pfo", saved_pfo_current, cfg),
        **signal_distances(control, legacy_current, cfg),
    }
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="sweet_190")
    parser.add_argument("--T-total", type=float, default=7200.0)
    parser.add_argument("--steps", default="20,21,26,35,39")
    parser.add_argument("--np-mode", choices=["cap", "equality"], default="cap")
    parser.add_argument("--output", default="outputs/forced_legacy_candidate_probe_sweet190_20260702")
    args = parser.parse_args()

    cfg, scenario = base.build_cfg(args.scenario, args.T_total, args.np_mode)
    pfo_rows = base.read_csv(
        ROOT / "outputs/sweet190_all_boundary_halfcap_7200_20260701/runs/sweet_190/PROPOSED-FOLLOWERS-ONLY/control_timeseries.csv"
    )
    legacy_rows = base.read_csv(
        ROOT / "outputs/legacy_pstack_sweet190_7200_20260702/runs/sweet_190/LEGACY-STACKELBERG/control_timeseries.csv"
    )
    steps = [int(s.strip()) for s in args.steps.split(",") if s.strip()]
    modes = [
        ("normal", False, False, False),
        ("inject_green", True, False, False),
        ("inject_offset_guard", False, True, False),
        ("inject_green_offset_guard", True, True, False),
        ("inject_green_offset_no_guard", True, True, True),
    ]
    rows: list[dict[str, Any]] = []

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
            targets = [
                ("legacy_target", legacy_current.N_P_star, legacy_current.N_UF_star),
                ("high_release_6000", legacy_current.N_P_star, 6000.0),
            ]
            for target_name, n_p_star, n_uf_star in targets:
                leader = LeaderAction(float(n_p_star), float(n_uf_star))
                for seed_name, previous in seeds:
                    for mode, inject_green, inject_offset, disable_guard in modes:
                        rows.append(
                            run_probe(
                                cfg,
                                sim,
                                forecast,
                                step,
                                state_source,
                                legacy_current,
                                saved_pfo_current,
                                target_name,
                                leader,
                                seed_name,
                                previous,
                                mode,
                                inject_green,
                                inject_offset,
                                disable_guard,
                            )
                        )

    out = ROOT / args.output
    write_csv(out / f"legacy_candidate_probe_{args.np_mode}.csv", rows)
    summary: list[dict[str, Any]] = []
    keys = sorted({(int(r["step"]), r["state_source"], r["target_name"], r["mode"]) for r in rows})
    for step, state_source, target_name, mode in keys:
        group = [
            r
            for r in rows
            if int(r["step"]) == step
            and r["state_source"] == state_source
            and r["target_name"] == target_name
            and r["mode"] == mode
        ]
        best = min(group, key=lambda r: float(r["response_rollout_ttt"]))
        summary.append(best)
    write_csv(out / f"legacy_candidate_probe_summary_{args.np_mode}.csv", summary)
    (out / f"legacy_candidate_probe_summary_{args.np_mode}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
