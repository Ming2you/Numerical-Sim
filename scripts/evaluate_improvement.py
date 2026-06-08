"""Evaluate baseline/proposed runs saved by the structured runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation.metrics import improvement_rate
from src.models.state import ExperimentConfig


def _load_total(path: Path) -> float:
    raw = json.loads((path / "metrics_raw.json").read_text(encoding="utf-8"))
    return float(raw["total_ttt"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="src/config/default.yaml")
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--proposed-dir", required=True)
    args = parser.parse_args()

    cfg = ExperimentConfig.from_file(args.config)
    baseline = _load_total(Path(args.baseline_dir))
    proposed = _load_total(Path(args.proposed_dir))
    rate = improvement_rate(
        baseline,
        proposed,
        cfg.evaluation.main_metric_direction,
        cfg.evaluation.eps,
    )
    print(json.dumps({
        "baseline_total_ttt": baseline,
        "proposed_total_ttt": proposed,
        "improvement_pct": rate,
        "pass": rate >= cfg.evaluation.min_improvement_pct,
    }, indent=2))


if __name__ == "__main__":
    main()

