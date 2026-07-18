# 표1/1b/1c 자동 생성 — 5컨트롤러 × 5셀 실데이터(wTTT·urban/freeway 분해·N_end), 통용 시나리오명
"""출력: analysis/tables/t1_macro_full.md (덮어쓰기).
컨트롤러 = no control / wu / pfo (box) / centralized / p-stack(walk-MVG) (2026-07-18 확정).
채점: wTTT = cum_ttt[last] − cum_ttt[step==19]; 개선% = (NC−wTTT)/NC×100; 단위 veh·h.
N_end = 마지막 180s 스텝 TTT 증분 × 20 = 종단 시점 망 내 차량 수 [veh]."""
import pubstyle as ps

ORDER = ["nc", "wu", "pfo_box", "pcent", "walk_mvg"]


def wttt_split(arm, cell):
    rl = ps.load(arm, cell, "run_log",
                 usecols=["step", "cumulative_total_ttt",
                          "cumulative_urban_ttt", "cumulative_freeway_ttt",
                          "step_total_ttt"])
    b = rl["step"] == ps.WARM_ROW
    tot = float(rl["cumulative_total_ttt"].iloc[-1] - rl.loc[b, "cumulative_total_ttt"].iloc[0])
    urb = float(rl["cumulative_urban_ttt"].iloc[-1] - rl.loc[b, "cumulative_urban_ttt"].iloc[0])
    fw = float(rl["cumulative_freeway_ttt"].iloc[-1] - rl.loc[b, "cumulative_freeway_ttt"].iloc[0])
    n_end = float(rl["step_total_ttt"].iloc[-1]) * 20.0
    return tot, urb, fw, n_end


def main():
    ps.sanity_gate()
    data = {arm: {c: wttt_split(arm, c) for c in ps.CELLS} for arm in ORDER}

    L = []
    L.append("# 표 1 — 5컨트롤러 × 5시나리오 (2026-07-18 확정, WARM=20, wTTT [veh·h])\n")
    L.append("자동 생성: `analysis/scripts/make_table1.py`. 컨트롤러 = "
             + " / ".join(ps.LABEL[a] for a in ORDER) + ".\n")

    # 표1 wTTT
    L.append("## 표 1 — wTTT [veh·h] (괄호 = NC 대비 개선%)\n")
    L.append("| Scenario | " + " | ".join(ps.LABEL[a] for a in ORDER) + " |")
    L.append("|---|" + "---|" * len(ORDER))
    for c in ps.CELLS:
        cells = []
        for a in ORDER:
            tot = data[a][c][0]
            if a == "nc":
                cells.append(f"{tot:.0f}")
            else:
                imp = (data["nc"][c][0] - tot) / data["nc"][c][0] * 100.0
                cells.append(f"{tot:.0f} ({imp:+.1f}%)")
        L.append(f"| {ps.scen(c)} | " + " | ".join(cells) + " |")

    # 표1b urban/freeway 분해
    L.append("\n## 표 1b — wTTT의 urban / freeway 분해 [veh·h]\n")
    L.append("| Scenario | " + " | ".join(ps.LABEL[a] for a in ORDER) + " |")
    L.append("|---|" + "---|" * len(ORDER))
    for c in ps.CELLS:
        cells = [f"{data[a][c][1]:.0f} / {data[a][c][2]:.0f}" for a in ORDER]
        L.append(f"| {ps.scen(c)} | " + " | ".join(cells) + " |")
    L.append("\n표기 = urban / freeway. 합 = 표1 total.\n")

    # 표1c N_end
    L.append("## 표 1c — 종단 잔존 차량 N_end [veh] (보조행)\n")
    L.append("| Scenario | " + " | ".join(ps.LABEL[a] for a in ORDER) + " |")
    L.append("|---|" + "---|" * len(ORDER))
    for c in ps.CELLS:
        cells = [f"{data[a][c][3]:.0f}" for a in ORDER]
        L.append(f"| {ps.scen(c)} | " + " | ".join(cells) + " |")
    L.append("\nN_end = 마지막 180s 스텝 TTT 증분 × 20 = 종단 시점 망 내 차량 수.\n")

    L.append("## 메모\n")
    L.append("- 개선% = NC 대비 (NC_wTTT − wTTT)/NC_wTTT × 100. NC는 절대 wTTT만 표기.")
    L.append("- PFO는 이동 한계 부과(box) 버전만 사용 — 무제한 PFO는 논문 제외.")
    L.append("- P-CENT(centralized) = structured grid, 이동 한계 미부과(rate-limit-free 상한).")
    L.append("- sweet_200_w(초고부하)는 논문 제외.")

    out = ps.TABDIR / "t1_macro_full.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"saved {out}")
    for c in ps.CELLS:
        row = " | ".join(f"{data[a][c][0]:.0f}" for a in ORDER)
        print(f"  {ps.scen(c):<24} {row}")


if __name__ == "__main__":
    main()
