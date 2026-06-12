# 풀 매트릭스 집계 — Stage 1 paired bootstrap CI/winner count, Stage 2·3 시나리오 취합 (plan §2.7)
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

PAIRS = [
    ("WuLeaderValue", "WU-CD-F", "WU-MATCHED-STACKELBERG"),
    ("ProposedLeaderValue", "PROPOSED-FOLLOWERS-ONLY", "PROPOSED-STACKELBERG"),
    ("WuCentralizationGap", "WU-CD-F", "WU-CC-F"),
    ("ProposedCentralizationGap", "PROPOSED-STACKELBERG", "PROPOSED-CENTRALIZED"),
    ("FollowerPackageDifference", "WU-CD-F", "PROPOSED-FOLLOWERS-ONLY"),
    ("LeaderPackageDifference", "WU-MATCHED-STACKELBERG", "PROPOSED-STACKELBERG"),
]


def _read(path: Path) -> List[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({k for row in rows for k in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _interval_ttt(run_dir: Path) -> np.ndarray:
    rows = _read(run_dir / "run_log.csv")
    return np.asarray([float(r["urban_ttt"]) + float(r["freeway_ttt"]) for r in rows], dtype=float)


def bootstrap_ci(diff: np.ndarray, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """interval-paired ΔTTT 합의 bootstrap CI — interval index를 복원추출 후 합산.

    demand가 deterministic이라 seed 간 분산이 작으므로, run 내 interval 차이의
    재표집으로 불확실성을 표현한다(시간 의존성은 단순 재표집 근사 — 한계 명시)."""
    rng = np.random.default_rng(seed)
    n = len(diff)
    sums = np.asarray([
        diff[rng.integers(0, n, size=n)].sum() for _ in range(n_boot)
    ])
    return float(np.percentile(sums, 2.5)), float(np.percentile(sums, 97.5))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1-root", default="post_analysis/stage1")
    parser.add_argument("--output", default="post_analysis/stage1")
    args = parser.parse_args()
    root = Path(args.stage1_root)
    out = Path(args.output)

    # <scenario>_s<seed>/ 디렉토리 수집.
    combos = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or "_s" not in d.name:
            continue
        if not (d / "six_controller_summary.csv").exists():
            continue
        scenario, _, seed = d.name.rpartition("_s")
        combos.append((scenario, seed, d))
    if not combos:
        print("no completed stage1 combos found")
        return

    all_rows: List[Dict[str, Any]] = []
    paired_rows: List[Dict[str, Any]] = []
    winner_rows: List[Dict[str, Any]] = []
    for scenario, seed, d in combos:
        summary = {r["controller_id"]: r for r in _read(d / "six_controller_summary.csv")}
        for cid, row in summary.items():
            all_rows.append({"scenario": scenario, "seed": seed, **row})
        # winner = 최소 TTT controller.
        winner = min(summary.values(), key=lambda r: float(r["total_ttt"]))
        winner_rows.append({"scenario": scenario, "seed": seed, "winner": winner["controller_id"],
                            "winner_ttt": winner["total_ttt"]})
        runs_root = d / "runs" / scenario
        for name, base_id, other_id in PAIRS:
            if base_id not in summary or other_id not in summary:
                continue
            base_ts = _interval_ttt(runs_root / base_id)
            other_ts = _interval_ttt(runs_root / other_id)
            n = min(len(base_ts), len(other_ts))
            diff = base_ts[:n] - other_ts[:n]  # 양수=other가 그 interval에서 우위.
            lo, hi = bootstrap_ci(diff)
            paired_rows.append({
                "scenario": scenario,
                "seed": seed,
                "comparison": name,
                "baseline": base_id,
                "other": other_id,
                "ttt_difference": round(float(diff.sum()), 3),
                "boot_ci_low": round(lo, 3),
                "boot_ci_high": round(hi, 3),
                "ci_excludes_zero": bool(lo > 0.0 or hi < 0.0),
                "delay_improvement_abs": round(
                    float(summary[base_id]["total_delay"]) - float(summary[other_id]["total_delay"]), 3
                ),
                "throughput_difference": round(
                    float(summary[other_id]["network_throughput_veh_h"])
                    - float(summary[base_id]["network_throughput_veh_h"]), 1
                ),
                "terminal_total_difference": round(
                    float(summary[other_id]["terminal_total_vehicles"])
                    - float(summary[base_id]["terminal_total_vehicles"]), 1
                ),
            })

    _write_csv(out / "matrix_all_controllers.csv", all_rows)
    _write_csv(out / "matrix_paired_with_ci.csv", paired_rows)
    _write_csv(out / "matrix_winner_counts.csv", winner_rows)

    # pooled: controller별 시나리오 평균(같은 seed 42 풀 매트릭스 + peak 추가 seed 포함).
    pooled: Dict[str, Dict[str, float]] = {}
    counts: Dict[str, int] = {}
    for row in all_rows:
        cid = row["controller_id"]
        pooled.setdefault(cid, {"total_ttt": 0.0, "total_delay": 0.0,
                                "network_throughput_veh_h": 0.0, "computation_time_sec": 0.0})
        for key in pooled[cid]:
            pooled[cid][key] += float(row[key])
        counts[cid] = counts.get(cid, 0) + 1
    pooled_rows = [
        {"controller_id": cid, "n_runs": counts[cid],
         **{f"mean_{k}": round(v / counts[cid], 2) for k, v in vals.items()}}
        for cid, vals in pooled.items()
    ]
    _write_csv(out / "matrix_pooled_summary.csv", pooled_rows)

    # paired pooled: comparison별 시나리오 합/평균 + 부호 일관성(positive count).
    pair_pool: Dict[str, List[float]] = {}
    for row in paired_rows:
        pair_pool.setdefault(row["comparison"], []).append(float(row["ttt_difference"]))
    pair_pool_rows = [
        {"comparison": name, "n": len(vals), "mean_ttt_difference": round(float(np.mean(vals)), 3),
         "positive_count": int(sum(1 for v in vals if v > 0)),
         "min": round(min(vals), 3), "max": round(max(vals), 3)}
        for name, vals in pair_pool.items()
    ]
    _write_csv(out / "matrix_paired_pooled.csv", pair_pool_rows)
    print(json.dumps({"combos": len(combos), "pairs": len(paired_rows)}, ensure_ascii=False))
    for row in pair_pool_rows:
        print(f"{row['comparison']}: mean={row['mean_ttt_difference']} positive {row['positive_count']}/{row['n']}")


if __name__ == "__main__":
    main()
