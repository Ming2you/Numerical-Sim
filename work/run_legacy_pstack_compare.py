from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.free_flow_reference import compute_free_flow_reference
from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.experiments.six_controller_comparison import _write_csv, summarize_controller
from src.models.demand import (
    DemandProfile,
    apply_scenario_network_overrides,
    load_scenarios,
)
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator, control_row, state_row


def _light_control(action: ControlAction | None) -> ControlAction | None:
    if action is None:
        return None
    return ControlAction(
        N_P_star=float(action.N_P_star),
        N_UF_star=float(action.N_UF_star),
        ramp_metering=dict(action.ramp_metering),
        vsl=dict(action.vsl),
        green_times=dict(action.green_times),
        offsets=dict(action.offsets),
        inflow_outflow_allocation=dict(action.inflow_outflow_allocation),
        infeasibility=dict(action.infeasibility),
        diagnostics={},
    )


def run_legacy_stackelberg(
    cfg: ExperimentConfig,
    scenario,
    scenario_name: str,
    output_dir: Path,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    decision_progress_path = output_dir / "decision_progress.jsonl"
    decision_progress_path.unlink(missing_ok=True)
    decision_progress_path.with_suffix(".csv").unlink(missing_ok=True)

    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    controller = StackelbergMPCController(cfg)
    controller.nash_solver = DistributedCoordinator(cfg)
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))

    run_rows: List[Dict[str, Any]] = []
    control_rows: List[Dict[str, Any]] = []
    state_rows: List[Dict[str, Any]] = []
    decision_rows: List[Dict[str, Any]] = []
    progress_rows: List[Dict[str, Any]] = []

    for step in range(steps):
        step_start = time.perf_counter()
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        old_progress_file = os.environ.get("NUMSIM_STACKELBERG_PROGRESS_FILE")
        old_progress_step = os.environ.get("NUMSIM_STACKELBERG_PROGRESS_STEP")
        os.environ["NUMSIM_STACKELBERG_PROGRESS_FILE"] = str(decision_progress_path)
        os.environ["NUMSIM_STACKELBERG_PROGRESS_STEP"] = str(step)
        try:
            decide_start = time.perf_counter()
            control = controller.decide(sim.state.copy(), forecast)
            compute_sec = time.perf_counter() - decide_start
        finally:
            if old_progress_file is None:
                os.environ.pop("NUMSIM_STACKELBERG_PROGRESS_FILE", None)
            else:
                os.environ["NUMSIM_STACKELBERG_PROGRESS_FILE"] = old_progress_file
            if old_progress_step is None:
                os.environ.pop("NUMSIM_STACKELBERG_PROGRESS_STEP", None)
            else:
                os.environ["NUMSIM_STACKELBERG_PROGRESS_STEP"] = old_progress_step

        log = sim.step(control, forecast[0], step)
        run_row = {
            "step": step,
            "time_sec": sim.state.time_sec,
            **{
                k: v
                for k, v in log.diagnostics.items()
                if isinstance(v, (int, float, bool))
            },
            "freeway_ttt": log.freeway_ttt,
            "urban_ttt": log.urban_ttt,
        }
        diag = {
            "step": step,
            "computation_time_sec": compute_sec,
            "solver_evaluations": float(control.diagnostics.get("leader_candidate_full_evaluated_count", 0.0)),
            "solver_converged": float(control.diagnostics.get("nash_converged", 0.0)),
            "leader_candidate_count": float(control.diagnostics.get("leader_candidate_count", 0.0)),
            "leader_candidate_full_evaluated_count": float(
                control.diagnostics.get("leader_candidate_full_evaluated_count", 0.0)
            ),
            "leader_selected_objective": float(control.diagnostics.get("leader_selected_objective", 0.0)),
            "legacy_stackelberg_distributed_follower": 1.0,
        }
        decision_rows.append(diag)
        control_rows.append(control_row(control, cfg, step, sim.state.time_sec))
        state_rows.append(state_row(sim.state, cfg, step))
        run_rows.append(run_row)
        progress_rows.append(
            {
                "step": step,
                "time_sec": sim.state.time_sec,
                "controller_id": "LEGACY-STACKELBERG",
                "step_total_ttt": log.freeway_ttt + log.urban_ttt,
                "step_urban_ttt": log.urban_ttt,
                "step_freeway_ttt": log.freeway_ttt,
                "cumulative_total_ttt": sim.total_ttt,
                "cumulative_urban_ttt": sim.urban_ttt,
                "cumulative_freeway_ttt": sim.freeway_ttt,
                "N_P_star": control.N_P_star,
                "N_UF_star": control.N_UF_star,
                "wall_time_sec": time.perf_counter() - step_start,
                "controller_compute_time_sec": compute_sec,
                "mean_B_sum_step": float(run_row.get("B_in", 0.0)) + float(run_row.get("B_out", 0.0)),
                "terminal_total_vehicles": (
                    sim.state.total_urban_vehicles(cfg.network)
                    + sim.state.total_freeway_vehicles(cfg.network)
                ),
            }
        )
        _write_csv(output_dir / "run_log.csv", run_rows)
        _write_csv(output_dir / "control_timeseries.csv", control_rows)
        _write_csv(output_dir / "state_timeseries.csv", state_rows)
        _write_csv(output_dir / "decision_diagnostics.csv", decision_rows)
        _write_csv(output_dir / "progress_summary.csv", progress_rows)
        controller.previous_control = _light_control(controller.previous_control)
        controller._pfo_fallback_previous_control = _light_control(
            getattr(controller, "_pfo_fallback_previous_control", None)
        )
        controller.last_decision = None
        control.diagnostics = {}
        print(
            f"LEGACY-STACKELBERG {scenario_name} step {step + 1}/{steps} "
            f"cum_ttt={sim.total_ttt:.3f} step_ttt={log.freeway_ttt + log.urban_ttt:.3f} "
            f"N_P={control.N_P_star:.1f} N_UF={control.N_UF_star:.1f}",
            flush=True,
        )

    return {
        "run_rows": run_rows,
        "control_rows": control_rows,
        "state_rows": state_rows,
        "decision_rows": decision_rows,
        "progress_rows": progress_rows,
        "final_state": sim.state,
        "total_ttt": sim.total_ttt,
        "urban_ttt": sim.urban_ttt,
        "freeway_ttt": sim.freeway_ttt,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="src/config/default.yaml")
    parser.add_argument("--scenarios-config", default="src/config/scenarios.yaml")
    parser.add_argument("--scenarios", default="sweet_155,sweet_190")
    parser.add_argument("--T-total", type=float, default=7200.0)
    parser.add_argument("--leader-backend", default="thread")
    parser.add_argument("--output", default="outputs/legacy_pstack_sweet155_sweet190_7200_20260702")
    args = parser.parse_args()

    overrides: Dict[str, Any] = {
        "simulation": {"T_total": args.T_total},
        "mpc": {"stackelberg_leader_parallel_backend": args.leader_backend},
    }
    base_cfg = ExperimentConfig.from_file(args.config, overrides)
    scenarios = load_scenarios(args.scenarios_config)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    summaries: Dict[str, Dict[str, Any]] = {}

    for scenario_name in [s.strip() for s in args.scenarios.split(",") if s.strip()]:
        scenario = scenarios[scenario_name]
        cfg = apply_scenario_network_overrides(base_cfg.with_updates({}), scenario)
        reference = compute_free_flow_reference(cfg, scenario)
        result = run_legacy_stackelberg(
            cfg,
            scenario,
            scenario_name,
            out / "runs" / scenario_name / "LEGACY-STACKELBERG",
        )
        summary = summarize_controller(cfg, "PROPOSED-STACKELBERG", result, reference)
        summary["controller_id"] = "LEGACY-STACKELBERG"
        summary["legacy_stackelberg_distributed_follower"] = 1.0
        summaries[scenario_name] = summary
        print(
            f"LEGACY-STACKELBERG {scenario_name}: "
            f"ttt={summary['total_ttt']:.3f} urban={summary['urban_ttt']:.3f} "
            f"freeway={summary['freeway_ttt']:.3f} compute={summary['computation_time_sec']:.2f}",
            flush=True,
        )

    rows = [{"scenario": scenario, **summary} for scenario, summary in summaries.items()]
    _write_csv(out / "legacy_stackelberg_summary.csv", rows)
    (out / "summary.json").write_text(
        json.dumps({"summaries": summaries}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
