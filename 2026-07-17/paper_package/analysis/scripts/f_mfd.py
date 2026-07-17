# 그림11: 190w MFD 산점도 — 채점창(step≥20) ρ–flow 운영점, walk_mvg(채움) vs pd4_ref(속빈), 링크별 2장
import pubstyle as ps

CELL = "sweet_190_w"
LINKS = ["FW_E", "FW_W"]
SCORE_START = ps.WARM_STEPS  # 채점창 시작: step 20 (0..19 = NC 웜업)
# (팔, 마커, 채움 여부) — 스타일맵 색상 유지, 마커/채움으로 추가 구분
SERIES = [("walk_mvg", "o", True), ("pd4_ref", "s", False)]


def main():
    ps.sanity_gate()
    for link in LINKS:
        xcol = f"rho_{link}_mean"
        ycol = f"flow_{link}_mean"
        fig, ax = ps.new_fig()
        for arm, marker, filled in SERIES:
            st = ps.load(arm, CELL, "state_timeseries",
                         usecols=["step", xcol, ycol])
            m = st["step"] >= SCORE_START
            c = ps.STYLE[arm]["color"]
            ax.scatter(st.loc[m, xcol], st.loc[m, ycol], s=14, marker=marker,
                       facecolors=(c if filled else "none"), edgecolors=c,
                       linewidths=0.8, label=ps.LABEL[arm], zorder=3)
        ax.set_xlabel("Mean density (veh/km/lane)")
        ax.set_ylabel("Mean flow (veh/h)")
        ax.text(0.98, 0.03, link.replace("_", "–"), transform=ax.transAxes,
                ha="right", va="bottom", fontsize=8, color="0.3")
        ax.legend(loc="best")
        ps.save(fig, f"f_mfd_{link}_190w")


if __name__ == "__main__":
    main()
