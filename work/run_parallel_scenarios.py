from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


DEFAULT_SCENARIOS = [
    "sweet_155_w",
    "sweet_170_w",
    "sweet_170_skew15_w",
    "sweet_170_incident_w",
    "sweet_190_w",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_one(
    scenario: str,
    *,
    runner: Path,
    output_root: Path,
    controllers: str,
    t_total: float,
    python_exe: str,
    force: bool,
) -> tuple[str, int, float, Path]:
    scenario_out = output_root / scenario
    summary_path = scenario_out / "summary.csv"
    scenario_out.mkdir(parents=True, exist_ok=True)
    if summary_path.exists() and not force:
        return scenario, 0, 0.0, summary_path

    stdout_path = scenario_out / "_parallel.stdout.log"
    stderr_path = scenario_out / "_parallel.stderr.log"
    cmd = [
        python_exe,
        "-u",
        str(runner),
        "--scenario",
        scenario,
        "--T-total",
        str(t_total),
        "--controllers",
        controllers,
        "--output",
        str(scenario_out),
    ]
    started = time.perf_counter()
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.run(
            cmd,
            cwd=str(_repo_root()),
            env=os.environ.copy(),
            stdout=stdout,
            stderr=stderr,
            text=True,
        )
    return scenario, int(proc.returncode), time.perf_counter() - started, summary_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Numerical-Sim scenarios in parallel.")
    parser.add_argument("--scenarios", default=",".join(DEFAULT_SCENARIOS))
    parser.add_argument(
        "--controllers",
        default="WU-FAITHFUL-FOLLOWER,P-STACK-WU-FAITHFUL-ALLPRICE-JOINT",
    )
    parser.add_argument("--T-total", type=float, default=14400.0)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=len(DEFAULT_SCENARIOS))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    root = _repo_root()
    runner = root / "work" / "run_claude_style_five_controller.py"
    output_root = Path(args.output)
    if not output_root.is_absolute():
        output_root = root / output_root
    output_root.mkdir(parents=True, exist_ok=True)

    scenarios = [item.strip() for item in args.scenarios.split(",") if item.strip()]
    workers = max(1, min(int(args.workers), len(scenarios)))
    print(f"parallel scenarios={len(scenarios)} workers={workers} output={output_root}", flush=True)

    failures: list[tuple[str, int, Path]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                _run_one,
                scenario,
                runner=runner,
                output_root=output_root,
                controllers=args.controllers,
                t_total=args.T_total,
                python_exe=args.python,
                force=bool(args.force),
            )
            for scenario in scenarios
        ]
        for future in as_completed(futures):
            scenario, rc, elapsed, summary_path = future.result()
            if rc != 0:
                failures.append((scenario, rc, summary_path))
                print(f"FAIL {scenario} rc={rc} elapsed={elapsed:.1f}s", flush=True)
            elif elapsed <= 0.0:
                print(f"SKIP {scenario} summary={summary_path}", flush=True)
            else:
                print(f"DONE {scenario} elapsed={elapsed:.1f}s summary={summary_path}", flush=True)

    if failures:
        for scenario, rc, summary_path in failures:
            print(f"failure detail: {scenario} rc={rc} stderr={summary_path.parent / '_parallel.stderr.log'}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
