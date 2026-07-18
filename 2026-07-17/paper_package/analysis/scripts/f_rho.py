# 그림10: 본선 평균 밀도[veh/km/lane] 시계열 — 임계선(ρ_crit=33.5) 근방 운영 증거, 링크 2 × 셀 2 = 4장
import pubstyle as ps

RHO_CRIT = 33.5  # veh/km/lane
LINKS = ["FW_E", "FW_W"]
CELLS = ["sweet_190_w"]
ARMS = ["farsa_ref", "pd4_ref", "walk_mvg"]


def main():
    ps.sanity_gate()
    for link in LINKS:
        col = f"rho_{link}_mean"
        for cell in CELLS:
            fig, ax = ps.new_fig()
            ps.shade_warmup(ax)
            ymax = RHO_CRIT
            for arm in ARMS:
                st = ps.load(arm, cell, "state_timeseries", usecols=["step", col])
                ax.plot(ps.minutes(st["step"]), st[col],
                        label=ps.LABEL[arm], **ps.STYLE[arm])
                ymax = max(ymax, float(st[col].max()))
            ax.axhline(RHO_CRIT, color="0.35", linewidth=0.8,
                       linestyle=(0, (4, 2)), zorder=1)
            # 범례(좌상단)와 겹치지 않도록 선 오른쪽 끝 위에 표기
            ax.text(177, RHO_CRIT + 0.015 * ymax, r"$\rho_{\mathrm{crit}}$",
                    fontsize=8, color="0.35", ha="right", va="bottom")
            ps.time_axis(ax)
            ax.set_ylim(0, ymax * 1.14)
            ax.set_ylabel("Mean density (veh/km/lane)")
            ax.text(0.98, 0.03, f"{link.replace('_', '–')}, {ps.scen(cell)}",
                    transform=ax.transAxes, ha="right", va="bottom",
                    fontsize=8, color="0.3")
            ax.legend(loc="upper left")
            ps.save(fig, f"f_rho_{link}_{cell}")


if __name__ == "__main__":
    main()
