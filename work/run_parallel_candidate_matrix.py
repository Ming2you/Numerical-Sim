from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable


DEFAULT_SCENARIOS = [
    "sweet_155_w",
    "sweet_170_w",
    "sweet_170_skew15_w",
    "sweet_170_incident_w",
    "sweet_190_w",
]

PFO_CONTROLLER = "WU-FAITHFUL-FOLLOWER"
PSTACK_CONTROLLER = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_kv_items(items: Iterable[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in items:
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Expected KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Empty environment key in {item!r}")
        parsed[key] = value.strip()
    return parsed


def _parse_candidate(raw: str) -> tuple[str, dict[str, str]]:
    name, sep, rest = raw.partition(":")
    name = name.strip()
    if not name:
        raise ValueError(f"Empty candidate name in {raw!r}")
    if not sep:
        return name, {}
    delimiter = ";" if ";" in rest else ","
    items = [item.strip() for item in rest.split(delimiter) if item.strip()]
    return name, _parse_kv_items(items)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
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


def _read_summary_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _summary_has_controller(path: Path, controller: str) -> bool:
    return any(row.get("controller_id") == controller for row in _read_summary_rows(path))


def _controller_ttt(path: Path, controller: str) -> float | None:
    rows = _read_summary_rows(path)
    exact = [row for row in rows if row.get("controller_id") == controller]
    if exact:
        return float(exact[0]["total_ttt"])
    if len(rows) == 1 and controller == PSTACK_CONTROLLER:
        return float(rows[0]["total_ttt"])
    if controller == PSTACK_CONTROLLER:
        pstack_rows = [row for row in rows if "P-STACK" in row.get("controller_id", "")]
        if pstack_rows:
            return float(pstack_rows[0]["total_ttt"])
    return None


def _load_pfo_baselines(root: Path | None, overrides: list[str]) -> dict[str, float]:
    baselines: dict[str, float] = {}
    if root is not None:
        for scenario in DEFAULT_SCENARIOS:
            summary = root / scenario / "summary.csv"
            value = _controller_ttt(summary, PFO_CONTROLLER)
            if value is not None:
                baselines[scenario] = float(value)
    for item in overrides:
        key, value = _parse_kv_items([item]).popitem()
        baselines[key] = float(value)
    return baselines


def _run_case(
    *,
    candidate_name: str,
    candidate_env: dict[str, str],
    scenario: str,
    runner: Path,
    output_root: Path,
    controllers: str,
    t_total: float,
    python_exe: str,
    force: bool,
    case_timeout_sec: float | None,
    common_env: dict[str, str],
) -> dict[str, object]:
    case_out = output_root / candidate_name / scenario
    summary_path = case_out / "summary.csv"
    case_out.mkdir(parents=True, exist_ok=True)
    if summary_path.exists() and not force and _summary_has_controller(summary_path, PSTACK_CONTROLLER):
        return {
            "candidate": candidate_name,
            "scenario": scenario,
            "status": "skipped_existing",
            "returncode": 0,
            "elapsed_sec": 0.0,
            "summary_path": str(summary_path),
        }

    stdout_path = case_out / "_matrix.stdout.log"
    stderr_path = case_out / "_matrix.stderr.log"
    cmd = [
        python_exe,
        "-u",
        str(runner),
        "--scenario",
        scenario,
        "--T-total",
        str(float(t_total)),
        "--controllers",
        controllers,
        "--output",
        str(case_out),
    ]
    env = os.environ.copy()
    env.update(common_env)
    env.update(candidate_env)
    env["PYTHONUNBUFFERED"] = "1"
    started = time.perf_counter()
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(_repo_root()),
                env=env,
                stdout=stdout,
                stderr=stderr,
                text=True,
                timeout=case_timeout_sec,
            )
            status = "ok" if proc.returncode == 0 else "failed"
            returncode = int(proc.returncode)
        except subprocess.TimeoutExpired:
            status = "timeout"
            returncode = -1
    return {
        "candidate": candidate_name,
        "scenario": scenario,
        "status": status,
        "returncode": returncode,
        "elapsed_sec": round(time.perf_counter() - started, 3),
        "summary_path": str(summary_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _score_rows(rows: list[dict[str, object]], pfo_baselines: dict[str, float]) -> list[dict[str, object]]:
    scored: list[dict[str, object]] = []
    for row in rows:
        summary_path = Path(str(row["summary_path"]))
        ps_ttt = _controller_ttt(summary_path, PSTACK_CONTROLLER)
        pfo_ttt = _controller_ttt(summary_path, PFO_CONTROLLER)
        if pfo_ttt is None:
            pfo_ttt = pfo_baselines.get(str(row["scenario"]))
        gap = None if ps_ttt is None or pfo_ttt is None else ps_ttt - pfo_ttt
        scored.append(
            {
                **row,
                "pstack_ttt": "" if ps_ttt is None else round(float(ps_ttt), 6),
                "pfo_ttt": "" if pfo_ttt is None else round(float(pfo_ttt), 6),
                "gap_vs_pfo": "" if gap is None else round(float(gap), 6),
                "win_vs_pfo": "" if gap is None else int(gap < 0.0),
            }
        )
    return scored


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run candidate x scenario Numerical-Sim cases in parallel."
    )
    parser.add_argument("--scenarios", default=",".join(DEFAULT_SCENARIOS))
    parser.add_argument(
        "--controllers",
        default=PSTACK_CONTROLLER,
        help="Controller list passed through to run_claude_style_five_controller.py.",
    )
    parser.add_argument(
        "--candidate",
        action="append",
        required=True,
        help="NAME or NAME:KEY=VALUE,KEY=VALUE. Use semicolons when a value contains commas.",
    )
    parser.add_argument("--common-env", action="append", default=[], help="KEY=VALUE applied to every case")
    parser.add_argument("--T-total", type=float, default=14400.0)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--case-timeout-sec", type=float, default=0.0)
    parser.add_argument("--pfo-root", default="")
    parser.add_argument("--pfo", action="append", default=[], help="SCENARIO=TTT baseline override")
    parser.add_argument("--quiet", action="store_true", help="Do not print progress; CSV status files are still updated.")
    args = parser.parse_args()

    root = _repo_root()
    runner = root / "work" / "run_claude_style_five_controller.py"
    output_root = Path(args.output)
    if not output_root.is_absolute():
        output_root = root / output_root
    output_root.mkdir(parents=True, exist_ok=True)

    scenarios = [item.strip() for item in args.scenarios.split(",") if item.strip()]
    candidates = [_parse_candidate(item) for item in args.candidate]
    duplicate_names = [name for name, _ in candidates if sum(1 for other, _ in candidates if other == name) > 1]
    if duplicate_names:
        raise ValueError(f"Duplicate candidate names: {', '.join(sorted(set(duplicate_names)))}")

    common_env = _parse_kv_items(args.common_env)
    timeout = None if float(args.case_timeout_sec) <= 0.0 else float(args.case_timeout_sec)
    pfo_root = Path(args.pfo_root) if args.pfo_root else None
    if pfo_root is not None and not pfo_root.is_absolute():
        pfo_root = root / pfo_root
    pfo_baselines = _load_pfo_baselines(pfo_root, args.pfo)

    cases = [
        (candidate_name, candidate_env, scenario)
        for candidate_name, candidate_env in candidates
        for scenario in scenarios
    ]
    workers = max(1, min(int(args.workers), len(cases)))
    if not args.quiet:
        print(
            f"parallel candidate-matrix cases={len(cases)} workers={workers} output={output_root}",
            flush=True,
        )

    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_case = {
            executor.submit(
                _run_case,
                candidate_name=candidate_name,
                candidate_env=candidate_env,
                scenario=scenario,
                runner=runner,
                output_root=output_root,
                controllers=str(args.controllers),
                t_total=float(args.T_total),
                python_exe=str(args.python),
                force=bool(args.force),
                case_timeout_sec=timeout,
                common_env=common_env,
            ): (candidate_name, scenario)
            for candidate_name, candidate_env, scenario in cases
        }
        for future in as_completed(future_to_case):
            row = future.result()
            rows.append(row)
            _write_csv(output_root / "case_status.csv", rows)
            scored = _score_rows(rows, pfo_baselines)
            _write_csv(output_root / "score_summary.csv", scored)
            if not args.quiet:
                print(
                    f"{row['status']} {row['candidate']} / {row['scenario']} "
                    f"elapsed={row['elapsed_sec']}s",
                    flush=True,
                )

    scored_rows = _score_rows(rows, pfo_baselines)
    _write_csv(output_root / "score_summary.csv", scored_rows)
    failures = [row for row in rows if row["status"] not in {"ok", "skipped_existing"}]
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
