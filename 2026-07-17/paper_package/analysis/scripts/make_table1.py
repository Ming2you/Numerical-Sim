# 표1 골격: 6셀 × 5컨트롤러 macro 표 — walk_mvg 열만 채움, 나머지는 "런 대기" (t1_macro_skeleton.csv/.md)
"""컬럼 정의 (walk_mvg 열):
  wTTT_veh_h        : cum_total_ttt[끝] − cum_total_ttt[step==19] (pubstyle.wttt, veh·h)
  pct_vs_PFO_ref    : (PFO_ref − wTTT)/PFO_ref × 100, PFO_ref = §0.4 수치 기준선
  comp_mean_sec/max : run_log computation_time_sec, 채점창(step≥20)만 (웜업 NC는 ~0이라 제외).
                      벽시계 시간 — 같은 머신 런끼리만 비교 가능.
  completed_veh     : Σ boundary_out_sink_veh (run_log, per-step), 채점창 step 20..59.
                      ★urban 경계 sink 유출량 프록시 — 전 네트워크 완주 대수 컬럼은 부재.
"""
import pandas as pd

import pubstyle as ps

CONTROLLERS = ["NC", "WU-CD-F", "PFO", "P-CENT", "walk-MVG"]
PENDING = "런 대기"


def walk_row(cell):
    rl = ps.load("walk_mvg", cell, "run_log",
                 usecols=["step", "cumulative_total_ttt", "computation_time_sec",
                          "boundary_out_sink_veh"])
    post = rl[rl["step"] >= ps.WARM_STEPS]
    w = ps.wttt(rl)
    return {
        "wTTT_veh_h": round(w, 2),
        "pct_vs_PFO_ref": round((ps.PFO_REF[cell] - w) / ps.PFO_REF[cell] * 100.0, 2),
        "comp_mean_sec": round(post["computation_time_sec"].mean(), 2),
        "comp_max_sec": round(post["computation_time_sec"].max(), 2),
        "completed_veh": round(post["boundary_out_sink_veh"].sum(), 1),
    }


def main():
    ps.sanity_gate()
    metrics = ["wTTT_veh_h", "pct_vs_PFO_ref", "comp_mean_sec", "comp_max_sec", "completed_veh"]
    rows = []
    for cell in ps.CELLS:
        wm = walk_row(cell)
        for ctrl in CONTROLLERS:
            row = {"cell": cell, "controller": ctrl}
            row.update(wm if ctrl == "walk-MVG" else {m: PENDING for m in metrics})
            rows.append(row)
    df = pd.DataFrame(rows)
    csv_path = ps.TABDIR / "t1_macro_skeleton.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  saved {csv_path}")

    # Markdown: wTTT 본표 + walk-MVG 상세표
    lines = ["# 표1 골격 — 6셀 × 5컨트롤러 (wTTT, veh·h)", ""]
    lines.append("| cell | " + " | ".join(CONTROLLERS) + " |")
    lines.append("|" + "---|" * (len(CONTROLLERS) + 1))
    for cell in ps.CELLS:
        vals = []
        for ctrl in CONTROLLERS:
            r = df[(df.cell == cell) & (df.controller == ctrl)].iloc[0]
            vals.append(str(r["wTTT_veh_h"]))
        lines.append(f"| {cell} | " + " | ".join(vals) + " |")
    lines += ["", "## walk-MVG 상세", ""]
    lines.append("| cell | wTTT (veh·h) | % vs PFO ref | comp mean (s) | comp max (s) | completed (veh) |")
    lines.append("|---|---|---|---|---|---|")
    for cell in ps.CELLS:
        r = df[(df.cell == cell) & (df.controller == "walk-MVG")].iloc[0]
        lines.append(f"| {cell} | {r.wTTT_veh_h} | {r.pct_vs_PFO_ref} | {r.comp_mean_sec} "
                     f"| {r.comp_max_sec} | {r.completed_veh} |")
    lines += [
        "",
        "주석.",
        "- wTTT = cumulative_total_ttt[끝] − cumulative_total_ttt[step==19 행] (0-인덱스; 웜업 20스텝 누적치, 채점창 step 20..59).",
        "- % vs PFO ref: §0.4 수치 기준선 (155_w 1776 / 170_w 3021 / 170_skew15 2957 / 170_incident 2367 / 190_w 5689 / 200_w 7196).",
        "- comp = run_log `computation_time_sec`, 채점창만. 벽시계라 같은 머신 런끼리만 비교.",
        "- completed = Σ `boundary_out_sink_veh` (채점창) — urban 경계 sink 유출 프록시. 전 네트워크 완주 컬럼 부재.",
        "- 200_w는 §5 한계 전용 — 본문 표 편입 금지.",
        f"- NC/WU-CD-F/PFO/P-CENT: {PENDING} (§6 런 큐).",
    ]
    md_path = ps.TABDIR / "t1_macro_skeleton.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  saved {md_path}")


if __name__ == "__main__":
    main()
