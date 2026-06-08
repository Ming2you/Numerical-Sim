"""Run the proposed Stackelberg MPC controller."""

from __future__ import annotations

import argparse

from src.models.demand import load_scenarios
from src.models.state import ExperimentConfig
from src.simulation.closed_loop_runner import run_closed_loop


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="src/config/default.yaml")
    parser.add_argument("--scenarios-config", default="src/config/scenarios.yaml")
    parser.add_argument("--scenario", default="peak_demand")
    parser.add_argument("--baseline", default="fixed_signal_fixed_speed")
    parser.add_argument("--output", default="outputs/proposed")
    parser.add_argument("--T-total", type=float, default=None)
    args = parser.parse_args()

    overrides = {"simulation": {"T_total": args.T_total}} if args.T_total is not None else None
    cfg = ExperimentConfig.from_file(args.config, overrides)
    scenario = load_scenarios(args.scenarios_config)[args.scenario]
    result = run_closed_loop(cfg, scenario, "stackelberg_mpc", args.output, baseline_mode=args.baseline)
    print(f"proposed total_ttt={result['total_ttt']:.6f} output={args.output}")


if __name__ == "__main__":
    main()

