from __future__ import annotations

import csv
import json
from pathlib import Path


def load_summaries(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["summaries"]


sources = {
    "sweet_155": {
        "base": "outputs/sweet155_current_wufaithful_7200_20260701/summary.json",
        "current_stack": "outputs/sweet155_pstack_all_boundary_halfcap_7200_20260701/summary.json",
        "legacy": "outputs/legacy_pstack_sweet155_7200_20260702/summary.json",
    },
    "sweet_190": {
        "base": "outputs/sweet190_all_boundary_halfcap_7200_20260701/summary.json",
        "current_stack": "outputs/sweet190_all_boundary_halfcap_7200_20260701/summary.json",
        "legacy": "outputs/legacy_pstack_sweet190_7200_20260702/summary.json",
    },
}

rows = []
for scenario, paths in sources.items():
    base = load_summaries(paths["base"])
    current_stack = load_summaries(paths["current_stack"])
    legacy = load_summaries(paths["legacy"])
    legacy_summary = legacy[scenario]
    metrics = {
        "NO-CONTROL": base["NO-CONTROL"],
        "PFO current": base["PROPOSED-FOLLOWERS-ONLY"],
        "P-Stack Wu-faithful current": current_stack["PROPOSED-STACKELBERG"],
        "P-Stack legacy pre-WuFaithful": legacy_summary,
    }
    no_ttt = metrics["NO-CONTROL"]["total_ttt"]
    pfo_ttt = metrics["PFO current"]["total_ttt"]
    current_stack_ttt = metrics["P-Stack Wu-faithful current"]["total_ttt"]
    for controller, summary in metrics.items():
        total_ttt = float(summary["total_ttt"])
        rows.append(
            {
                "scenario": scenario,
                "controller": controller,
                "total_ttt": total_ttt,
                "urban_ttt": float(summary["urban_ttt"]),
                "freeway_ttt": float(summary["freeway_ttt"]),
                "completed_vehicles": float(summary.get("completed_vehicles", 0.0)),
                "terminal_total_vehicles": float(summary.get("terminal_total_vehicles", 0.0)),
                "computation_time_sec": float(summary.get("computation_time_sec", 0.0)),
                "improvement_vs_no_control_pct": 100.0 * (no_ttt - total_ttt) / max(no_ttt, 1e-9),
                "delta_ttt_vs_pfo": total_ttt - pfo_ttt,
                "delta_ttt_vs_current_stack": total_ttt - current_stack_ttt,
            }
        )

out_dir = Path("outputs/legacy_pstack_sweet155_sweet190_7200_20260702")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "comparison_summary.csv"
with out_path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

for row in rows:
    print(
        f"{row['scenario']} | {row['controller']} | "
        f"TTT={row['total_ttt']:.3f} | U={row['urban_ttt']:.3f} | F={row['freeway_ttt']:.3f} | "
        f"completed={row['completed_vehicles']:.1f} | terminal={row['terminal_total_vehicles']:.1f} | "
        f"compute={row['computation_time_sec']:.2f} | "
        f"impr_no={row['improvement_vs_no_control_pct']:.2f}% | "
        f"d_pfo={row['delta_ttt_vs_pfo']:.3f} | d_cur_stack={row['delta_ttt_vs_current_stack']:.3f}"
    )
print(f"wrote {out_path}")
