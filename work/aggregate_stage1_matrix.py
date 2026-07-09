# Stage1 집계기 — literature_grounded_post_analysis_plan §2.6/§15 규격으로 5컨트롤러×4시나리오 요약/짝비교 생성
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T_C_H = 0.05

# run 소스: (controller, scenario) -> summary.json 경로 또는 legacy CSV 디렉토리
RUNS = {
    ("NO-CONTROL", "sweet_122"): "outputs/_4x3/sweet_122_NO-CONTROL/summary.json",
    ("NO-CONTROL", "sweet_155"): "outputs/_4x3/sweet_155_NO-CONTROL/summary.json",
    ("NO-CONTROL", "sweet_155_incident"): "outputs/_4x3/sweet_155_incident_v2_NO-CONTROL/summary.json",
    ("NO-CONTROL", "sweet_190"): "outputs/_3way/nocontrol/summary.json",
    ("PFO", "sweet_122"): "outputs/_4x3/sweet_122_WU-FAITHFUL-FOLLOWER-NOP1/summary.json",
    ("PFO", "sweet_155"): "outputs/_4x3/sweet_155_WU-FAITHFUL-FOLLOWER-NOP1/summary.json",
    ("PFO", "sweet_155_incident"): "outputs/_4x3/sweet_155_incident_v2_WU-FAITHFUL-FOLLOWER-NOP1/summary.json",
    ("PFO", "sweet_190"): "outputs/_3way/pfo/summary.json",
    ("PSTACK-G1DF", "sweet_122"): "outputs/_4x3/sweet_122_PSTACK/summary.json",
    ("PSTACK-G1DF", "sweet_155"): "outputs/_4x3/sweet_155_PSTACK/summary.json",
    ("PSTACK-G1DF", "sweet_155_incident"): "outputs/_4x3/sweet_155_incident_v2_PSTACK/summary.json",
    ("PSTACK-G1DF", "sweet_190"): "outputs/_vdepth_far/g1df_d3_far/summary.json",
    ("APJOINT", "sweet_122"): "outputs/_apjoint/sweet_122/summary.json",
    ("APJOINT", "sweet_155"): "outputs/_apjoint/sweet_155/summary.json",
    ("APJOINT", "sweet_155_incident"): "outputs/_apjoint/sweet_155_incident/summary.json",
    ("APJOINT", "sweet_190"): "outputs/_apjoint/sweet_190/summary.json",
    ("LEGACY", "sweet_122"): "outputs/legacy_pstack_sweet155_sweet190_7200_20260702/runs/sweet_122/LEGACY-STACKELBERG",
    ("LEGACY", "sweet_155"): "outputs/legacy_pstack_sweet155_sweet190_7200_20260702/runs/sweet_155/LEGACY-STACKELBERG",
    ("LEGACY", "sweet_155_incident"): "outputs/legacy_pstack_sweet155_sweet190_7200_20260702/runs/sweet_155_incident/LEGACY-STACKELBERG",
    ("LEGACY", "sweet_190"): "outputs/legacy_pstack_sweet190_7200_20260703/runs/sweet_190/LEGACY-STACKELBERG",
}
SCENARIOS = ["sweet_122", "sweet_155", "sweet_155_incident", "sweet_190"]
CONTROLLERS = ["NO-CONTROL", "PFO", "PSTACK-G1DF", "APJOINT", "LEGACY"]


def load_summary(path: Path) -> dict | None:
    if not path.exists():
        return None
    data = json.load(open(path))
    row = data if isinstance(data, dict) else data[0]
    return row


def load_legacy(dirpath: Path, reference: dict) -> dict | None:
    rl_path = dirpath / "run_log.csv"
    ps_path = dirpath / "progress_summary.csv"
    if not rl_path.exists() or not ps_path.exists():
        return None
    rl = list(csv.DictReader(open(rl_path, newline="")))
    ps = list(csv.DictReader(open(ps_path, newline="")))
    cu = sum(float(r.get("boundary_out_sink_veh", 0)) for r in rl)
    cf = sum(float(r.get("mainline_exit_flow_total", 0)) * T_C_H for r in rl)
    last = ps[-1]
    total = float(last["cumulative_total_ttt"])
    urban = float(last["cumulative_urban_ttt"])
    freeway = float(last["cumulative_freeway_ttt"])
    compute = sum(float(r.get("controller_compute_time_sec", 0)) for r in ps)
    return {
        "total_ttt": total,
        "urban_ttt": urban,
        "freeway_ttt": freeway,
        "free_flow_reference_total_ttt": reference.get("free_flow_reference_total_ttt", 0.0),
        "total_delay": total - reference.get("free_flow_reference_total_ttt", 0.0),
        "completed_vehicles": cu + cf,
        "completed_urban_vehicles": cu,
        "completed_freeway_vehicles": cf,
        "terminal_total_vehicles": float(last["terminal_total_vehicles"]),
        "computation_time_sec": compute,
        "mean_step_compute_sec": compute / max(len(ps), 1),
    }


def main() -> None:
    outdir = ROOT / "2026-07-09" / "results" / "stage1_matrix"
    outdir.mkdir(parents=True, exist_ok=True)
    rows = []
    table: dict[tuple, dict] = {}
    for sc in SCENARIOS:
        # 공통 free-flow reference: 같은 시나리오의 PFO summary에서(러너가 계산·저장, 컨트롤러 무관 동일)
        ref = load_summary(ROOT / RUNS[("PFO", sc)]) or {}
        for ctrl in CONTROLLERS:
            src = ROOT / RUNS[(ctrl, sc)]
            row = load_legacy(src, ref) if ctrl == "LEGACY" else load_summary(src)
            if row is None:
                print(f"[미완] {ctrl} {sc}")
                continue
            ref_ttt = float(row.get("free_flow_reference_total_ttt", ref.get("free_flow_reference_total_ttt", 0.0)))
            d_total = float(row["total_ttt"]) - ref_ttt
            completed = float(row.get("completed_vehicles", 0.0))
            rec = {
                "scenario": sc,
                "controller": ctrl,
                "total_ttt": round(float(row["total_ttt"]), 1),
                "urban_ttt": round(float(row.get("urban_ttt", 0)), 1),
                "freeway_ttt": round(float(row.get("freeway_ttt", 0)), 1),
                "free_flow_reference_ttt": round(ref_ttt, 1),
                "D_total_delay": round(d_total, 1),
                "completed_vehicles": round(completed, 1),
                "terminal_total_vehicles": round(float(row.get("terminal_total_vehicles", 0)), 1),
                "avg_delay_per_completed_h": round(d_total / max(completed, 1.0), 5),
                "compute_total_sec": round(float(row.get("computation_time_sec", 0)), 1),
                "compute_per_step_sec": round(float(row.get("mean_step_compute_sec", 0)), 2),
            }
            rows.append(rec)
            table[(ctrl, sc)] = rec
    with open(outdir / "stage1_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    # 짝비교(§2.6): Delta_D_abs/pct — baseline PFO 및 LEGACY 갭 회수율
    pairs = []
    for sc in SCENARIOS:
        pfo = table.get(("PFO", sc))
        leg = table.get(("LEGACY", sc))
        for ctrl in ("PSTACK-G1DF", "APJOINT"):
            c = table.get((ctrl, sc))
            if not (pfo and c):
                continue
            d_abs = pfo["D_total_delay"] - c["D_total_delay"]
            d_pct = 100.0 * d_abs / pfo["D_total_delay"] if pfo["D_total_delay"] > 1e-9 else float("nan")
            gap = (pfo["D_total_delay"] - leg["D_total_delay"]) if leg else float("nan")
            recov = 100.0 * d_abs / gap if leg and abs(gap) > 1e-9 else float("nan")
            pairs.append({
                "scenario": sc, "controller": ctrl, "baseline": "PFO",
                "Delta_D_abs": round(d_abs, 1), "Delta_D_pct": round(d_pct, 2),
                "legacy_gap": round(gap, 1) if gap == gap else "NA",
                "gap_recovery_pct": round(recov, 1) if recov == recov else "NA",
                "throughput_delta": round(c["completed_vehicles"] - pfo["completed_vehicles"], 1),
                "terminal_delta": round(c["terminal_total_vehicles"] - pfo["terminal_total_vehicles"], 1),
            })
    if pairs:
        with open(outdir / "paired_comparisons.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(pairs[0].keys()))
            w.writeheader()
            w.writerows(pairs)
    print(f"저장: {outdir}")
    hdr = f"{'scenario':>18} {'controller':>12} {'TTT':>8} {'delay':>8} {'completed':>10} {'terminal':>9} {'s/step':>7}"
    print(hdr)
    for r in rows:
        print(f"{r['scenario']:>18} {r['controller']:>12} {r['total_ttt']:>8.0f} {r['D_total_delay']:>8.0f} {r['completed_vehicles']:>10.0f} {r['terminal_total_vehicles']:>9.0f} {r['compute_per_step_sec']:>7.1f}")


if __name__ == "__main__":
    main()
