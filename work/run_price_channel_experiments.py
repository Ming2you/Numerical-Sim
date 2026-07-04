from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.free_flow_reference import compute_free_flow_reference
from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.baseline import baseline_control
from src.simulation.simulator import MixedTrafficSimulator, control_row, state_row


VARIANTS = [
    "NO-CONTROL",
    "PFO-PURE",
    "PFO-TAX-B3",
    "PSTACK-B2-OFF",
    "PSTACK-B2-ON",
    "PSTACK-B3",
]


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_cfg(scenario_name: str, t_total: float) -> tuple[ExperimentConfig, Any]:
    overrides = {
        "mpc": {
            "relaxed_quantized_controls": True,
            "grid_parallel_backend": "serial",
            "leader_search_mode": "grid",
            "stackelberg_leader_parallel_backend": "serial",
        },
        "simulation": {"T_total": float(t_total)},
    }
    cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), overrides)
    scenarios = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))
    scenario = scenarios[scenario_name]
    cfg = apply_scenario_network_overrides(cfg, scenario)
    return cfg, scenario


class PriceOnlyFollower:
    """PFO response with leader-computed price channels but no leader target search."""

    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg
        self.helper = StackelbergWuMeteredController(cfg)
        self.helper.green_price_enabled = True
        self.helper.metering_price_enabled = True
        self.helper.vsl_price_enabled = True
        self.follower = WuFaithfulFollower(cfg)
        self.follower.count_blocked_ramp_inflow = False

    def decide(self, state, forecast, previous: Optional[ControlAction]) -> ControlAction:
        prev = previous.copy() if previous is not None else ControlAction.uncontrolled(self.cfg)
        self.follower.green_price = self.helper._compute_green_marginal_price(state, forecast, prev)
        self.follower.metering_price = self.helper._compute_metering_marginal_price(state, forecast, prev)
        self.follower.vsl_price = self.helper._compute_vsl_marginal_price(state, forecast, prev)
        try:
            return self.follower.solve(state.copy(), None, forecast, prev).control
        finally:
            self.follower.green_price = None
            self.follower.metering_price = None
            self.follower.vsl_price = None

    def close(self) -> None:
        if hasattr(self.helper, "close"):
            self.helper.close()


def make_controller(variant: str, cfg: ExperimentConfig):
    if variant == "NO-CONTROL":
        return None
    if variant == "PFO-PURE":
        follower = WuFaithfulFollower(cfg)
        follower.count_blocked_ramp_inflow = False
        return follower
    if variant == "PFO-TAX-B3":
        return PriceOnlyFollower(cfg)
    if variant in {"PSTACK-B2-OFF", "PSTACK-B2-ON", "PSTACK-B3"}:
        controller = StackelbergWuMeteredController(cfg)
        controller.green_price_enabled = variant in {"PSTACK-B2-ON", "PSTACK-B3"}
        controller.metering_price_enabled = variant == "PSTACK-B3"
        controller.vsl_price_enabled = variant == "PSTACK-B3"
        if variant == "PSTACK-B3":
            controller.nash_solver.count_blocked_ramp_inflow = False
        return controller
    raise ValueError(f"Unknown variant: {variant}")


def decide(variant: str, controller, sim: MixedTrafficSimulator, forecast, previous, cfg):
    if variant == "NO-CONTROL":
        return baseline_control("no_control", cfg, sim.state, forecast[0])
    if variant in {"PFO-PURE"}:
        return controller.solve(sim.state.copy(), None, forecast, previous).control
    if variant == "PFO-TAX-B3":
        return controller.decide(sim.state.copy(), forecast, previous)
    return controller.decide(sim.state.copy(), forecast, previous, cfg)


def summarize(
    variant: str,
    cfg: ExperimentConfig,
    sim: MixedTrafficSimulator,
    decision_rows: List[Dict[str, Any]],
    run_rows: List[Dict[str, Any]],
    reference,
) -> Dict[str, Any]:
    net = cfg.network
    horizon_h = cfg.simulation.T_total / 3600.0
    t_c_h = cfg.simulation.T_c_h
    completed_urban = sum(float(r.get("boundary_out_sink_veh", 0.0)) for r in run_rows)
    completed_freeway = sum(float(r.get("mainline_exit_flow_total", 0.0)) * t_c_h for r in run_rows)
    completed = completed_urban + completed_freeway
    final = sim.state
    compute_times = [float(row.get("computation_time_sec", 0.0)) for row in decision_rows]
    total_delay = sim.total_ttt - reference.total_ttt
    return {
        "controller_id": variant,
        "total_ttt": round(sim.total_ttt, 3),
        "urban_ttt": round(sim.urban_ttt, 3),
        "freeway_ttt": round(sim.freeway_ttt, 3),
        "total_delay": round(total_delay, 3),
        "urban_delay": round(sim.urban_ttt - reference.urban_ttt, 3),
        "freeway_delay": round(sim.freeway_ttt - reference.freeway_ttt, 3),
        "completed_vehicles": round(completed, 1),
        "network_throughput_veh_h": round(completed / max(horizon_h, 1e-9), 1),
        "terminal_total_vehicles": round(
            final.total_urban_vehicles(net) + final.total_freeway_vehicles(net), 1
        ),
        "computation_time_sec": round(sum(compute_times), 3),
        "mean_step_compute_sec": round(float(np.mean(compute_times)) if compute_times else 0.0, 3),
        "max_step_compute_sec": round(float(np.max(compute_times)) if compute_times else 0.0, 3),
    }


def run_one(variant: str, scenario_name: str, t_total: float, output_root: Path, reference) -> Dict[str, Any]:
    cfg, scenario = build_cfg(scenario_name, t_total)
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    controller = make_controller(variant, cfg)
    previous: Optional[ControlAction] = None
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    out_dir = output_root / variant
    run_rows: List[Dict[str, Any]] = []
    control_rows: List[Dict[str, Any]] = []
    state_rows: List[Dict[str, Any]] = []
    decision_rows: List[Dict[str, Any]] = []

    print(f"=== {variant} ===", flush=True)
    for step in range(steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        t0 = time.perf_counter()
        control = decide(variant, controller, sim, forecast, previous, cfg)
        compute_time = time.perf_counter() - t0
        log = sim.step(control, forecast[0], step)
        previous = control.copy()
        diag = control.diagnostics
        decision_rows.append({
            "step": step,
            "computation_time_sec": compute_time,
            "N_P_star": float(control.N_P_star),
            "N_UF_star": float(control.N_UF_star),
            "wu_faithful_local_evals": float(diag.get("wu_faithful_local_evals", 0.0)),
            "leader_green_price_active": float(diag.get("leader_green_price_active", 0.0)),
            "leader_metering_price_active": float(diag.get("leader_metering_price_active", 0.0)),
            "leader_vsl_price_active": float(diag.get("leader_vsl_price_active", 0.0)),
            "leader_pfo_incumbent_selected": float(diag.get("leader_pfo_incumbent_selected", 0.0)),
        })
        control_rows.append(control_row(control, cfg, step, sim.state.time_sec))
        state_rows.append(state_row(sim.state, cfg, step))
        row = {
            "step": step,
            "time_sec": sim.state.time_sec,
            "step_total_ttt": log.freeway_ttt + log.urban_ttt,
            "step_urban_ttt": log.urban_ttt,
            "step_freeway_ttt": log.freeway_ttt,
            "cumulative_total_ttt": sim.total_ttt,
            "cumulative_urban_ttt": sim.urban_ttt,
            "cumulative_freeway_ttt": sim.freeway_ttt,
            "computation_time_sec": compute_time,
        }
        row.update({k: v for k, v in log.diagnostics.items() if isinstance(v, (int, float, bool))})
        run_rows.append(row)
        print(
            f"{variant} step {step + 1}/{steps} "
            f"cum_ttt={sim.total_ttt:.3f} step_ttt={row['step_total_ttt']:.3f} "
            f"solve={compute_time:.2f}s",
            flush=True,
        )

    if hasattr(controller, "close"):
        controller.close()
    write_csv(out_dir / "run_log.csv", run_rows)
    write_csv(out_dir / "control_timeseries.csv", control_rows)
    write_csv(out_dir / "state_timeseries.csv", state_rows)
    write_csv(out_dir / "decision_diagnostics.csv", decision_rows)
    return summarize(variant, cfg, sim, decision_rows, run_rows, reference)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="sweet_190")
    parser.add_argument("--T-total", type=float, default=3600.0)
    parser.add_argument("--output", default="outputs/price_channel_experiment")
    parser.add_argument("--variants", default=",".join(VARIANTS))
    args = parser.parse_args()

    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    cfg, scenario = build_cfg(args.scenario, args.T_total)
    reference = compute_free_flow_reference(cfg, scenario)
    selected = [item.strip() for item in args.variants.split(",") if item.strip()]
    summaries = [run_one(v, args.scenario, args.T_total, output_root, reference) for v in selected]

    no_control = next((row for row in summaries if row["controller_id"] == "NO-CONTROL"), None)
    for row in summaries:
        if no_control and row["controller_id"] != "NO-CONTROL":
            row["ttt_improvement_vs_no_control_pct"] = round(
                100.0 * (no_control["total_ttt"] - row["total_ttt"]) / max(no_control["total_ttt"], 1.0e-9),
                3,
            )
        else:
            row["ttt_improvement_vs_no_control_pct"] = 0.0

    write_csv(output_root / "summary.csv", summaries)
    (output_root / "summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print("\n========== SUMMARY ==========", flush=True)
    for row in summaries:
        print(
            f"{row['controller_id']}: total_ttt={row['total_ttt']:.3f} "
            f"impr={row['ttt_improvement_vs_no_control_pct']:+.2f}% "
            f"completed={row['completed_vehicles']:.1f} terminal={row['terminal_total_vehicles']:.1f} "
            f"mean_solve={row['mean_step_compute_sec']:.2f}s",
            flush=True,
        )


if __name__ == "__main__":
    main()
