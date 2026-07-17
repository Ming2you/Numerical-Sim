# 그림9: 램프 대기행렬[veh] 시계열 — 190w(pd4 vs walk) 4장 + 200w(회복 스토리의 비용측) 4장, 저장한계 180 수평선
import pubstyle as ps

RAMPS = ["R_D_E", "R_D_W", "R_F_E", "R_F_W"]
STORAGE_LIMIT = 180.0  # veh — 램프 저장 한계
# (셀, 팔 목록, 파일명 접미사)
FAMILIES = [
    ("sweet_190_w", ["pd4_ref", "walk_mvg"], "190w"),
    ("sweet_200_w", ["farsa_ref", "box300_vsl10_ref", "walk_mvg"], "200w"),
]


def main():
    ps.sanity_gate()
    for cell, arms, tag in FAMILIES:
        for ramp in RAMPS:
            col = f"ramp_queue_{ramp}"
            fig, ax = ps.new_fig()
            ps.shade_warmup(ax)
            ymax = STORAGE_LIMIT
            for arm in arms:
                st = ps.load(arm, cell, "state_timeseries", usecols=["step", col])
                ax.plot(ps.minutes(st["step"]), st[col],
                        label=ps.LABEL[arm], **ps.STYLE[arm])
                ymax = max(ymax, float(st[col].max()))
            ax.axhline(STORAGE_LIMIT, color="0.35", linewidth=0.8,
                       linestyle=(0, (4, 2)), zorder=1)
            # 범례(좌상단)와 겹치지 않도록 선 오른쪽 끝 위에 표기
            ax.text(177, STORAGE_LIMIT + 0.015 * ymax, "storage limit",
                    fontsize=7.5, color="0.35", ha="right", va="bottom")
            ps.time_axis(ax)
            ax.set_ylim(0, ymax * 1.14)
            ax.set_ylabel("Ramp queue (veh)")
            ax.text(0.98, 0.03, ramp.replace("_", "–"), transform=ax.transAxes,
                    ha="right", va="bottom", fontsize=8, color="0.3")
            ax.legend(loc="upper left")
            ps.save(fig, f"f_rampq_{ramp}_{tag}")


if __name__ == "__main__":
    main()
