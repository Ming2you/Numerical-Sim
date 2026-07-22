from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

FINAL_SCENARIOS = [
    "sweet_155_w",
    "sweet_170_w",
    "sweet_190_w",
    "sweet_170_skew15_w",
    "sweet_170_incident_w",
]

FINAL_CONTROLLERS = [
    "NO-CONTROL",
    "WU-CD-F",
    "WU-FAITHFUL-FOLLOWER",
    "P-STACK-WU-FAITHFUL-APJOINT-FINAL",
    "P-CENT-SLSQP",
]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_csv_list(value: str, allowed: list[str]) -> list[str]:
    if value.strip().lower() == "all":
        return list(allowed)
    selected = [item.strip() for item in value.split(",") if item.strip()]
    unknown = sorted(set(selected) - set(allowed))
    if unknown:
        raise ValueError(f"Unknown values: {', '.join(unknown)}")
    return selected


def case_done(output_dir: Path, controller: str) -> bool:
    summary_path = output_dir / "summary.csv"
    if not summary_path.exists():
        return False
    try:
        with summary_path.open(newline="", encoding="utf-8") as handle:
            return any(row.get("controller_id") == controller for row in csv.DictReader(handle))
    except Exception:
        return False


def run_case(
    scenario: str,
    controller: str,
    t_total: float,
    output_root: Path,
    case_timeout_sec: float | None,
    skip_existing: bool,
) -> dict[str, object]:
    scenario_output = output_root / scenario
    scenario_output.mkdir(parents=True, exist_ok=True)
    log_path = scenario_output / f"{controller}.log"
    if skip_existing and case_done(scenario_output, controller):
        return {
            "scenario": scenario,
            "controller": controller,
            "status": "skipped_existing",
            "returncode": 0,
            "elapsed_sec": 0.0,
            "log_path": str(log_path),
        }

    cmd = [
        sys.executable,
        str(REPO_ROOT / "work" / "run_claude_style_five_controller.py"),
        "--scenario",
        scenario,
        "--T-total",
        str(float(t_total)),
        "--output",
        str(scenario_output),
        "--controllers",
        controller,
    ]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log:
        log.write(" ".join(cmd) + "\n\n")
        log.flush()
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=case_timeout_sec,
            )
            status = "ok" if completed.returncode == 0 else "failed"
            returncode = int(completed.returncode)
        except subprocess.TimeoutExpired:
            status = "timeout"
            returncode = -1
    return {
        "scenario": scenario,
        "controller": controller,
        "status": status,
        "returncode": returncode,
        "elapsed_sec": round(time.perf_counter() - started, 3),
        "log_path": str(log_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default="all")
    parser.add_argument("--controllers", default="all")
    parser.add_argument("--T-total", type=float, default=10800.0)
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "outputs" / "final_5x5_10800"),
    )
    parser.add_argument("--max-workers", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--case-timeout-sec", type=float, default=0.0)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    scenarios = parse_csv_list(args.scenarios, FINAL_SCENARIOS)
    controllers = parse_csv_list(args.controllers, FINAL_CONTROLLERS)
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    timeout = None if args.case_timeout_sec <= 0 else float(args.case_timeout_sec)

    cases = [(scenario, controller) for scenario in scenarios for controller in controllers]
    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, int(args.max_workers))) as pool:
        future_to_case = {
            pool.submit(
                run_case,
                scenario,
                controller,
                float(args.T_total),
                output_root,
                timeout,
                bool(args.skip_existing),
            ): (scenario, controller)
            for scenario, controller in cases
        }
        for future in as_completed(future_to_case):
            row = future.result()
            rows.append(row)
            write_csv(output_root / "case_status.csv", rows)
            print(
                f"{row['status']}: {row['scenario']} / {row['controller']} "
                f"elapsed={row['elapsed_sec']}s",
                flush=True,
            )

    failed = [row for row in rows if row["status"] not in {"ok", "skipped_existing"}]
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
