# 그림4: 200_w 누적 TTT 격차(vs farsa_ref) — box300_vsl10_ref−farsa, walk_mvg−farsa 두 곡선 (f_tttgap_200w)
import pubstyle as ps

CELL = "sweet_200_w"
BASE = "farsa_ref"
ARMS = ["box300_vsl10_ref", "walk_mvg"]


def main():
    ps.sanity_gate()
    base = ps.load(BASE, CELL, "run_log", usecols=["step", "cumulative_total_ttt"])
    fig, ax = ps.new_fig()
    ps.shade_warmup(ax)
    ax.axhline(0.0, color="0.6", linewidth=0.6, zorder=1)
    for arm in ARMS:
        rl = ps.load(arm, CELL, "run_log", usecols=["step", "cumulative_total_ttt"])
        gap = rl["cumulative_total_ttt"].to_numpy() - base["cumulative_total_ttt"].to_numpy()
        ax.plot(ps.minutes(rl["step"]), gap, label=f"{ps.LABEL[arm]} − {ps.LABEL[BASE]}",
                **ps.STYLE[arm])
    ps.time_axis(ax)
    ax.set_ylabel("Cumulative TTT difference (veh·h)")
    ax.legend(loc="upper left")
    ps.save(fig, "f_tttgap_200w")


if __name__ == "__main__":
    main()
