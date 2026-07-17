# 그림5: 셀별 per-step TTT 궤적(누적 TTT의 차분) — 4팔 비교, 6셀 각 1장 (f_ttt_traj_<cell>)
import numpy as np

import pubstyle as ps


def main():
    ps.sanity_gate()
    for cell in ps.CELLS:
        fig, ax = ps.new_fig()
        ps.shade_warmup(ax)
        for arm in ps.ARMS:
            rl = ps.load(arm, cell, "run_log", usecols=["step", "cumulative_total_ttt"])
            cum = rl["cumulative_total_ttt"].to_numpy()
            step_ttt = np.diff(cum, prepend=0.0)  # 첫 행 = step 0의 TTT
            ax.plot(ps.minutes(rl["step"]), step_ttt, label=ps.LABEL[arm], **ps.STYLE[arm])
        ps.time_axis(ax)
        ax.set_ylabel("TTT per step (veh·h)")
        short = cell.replace("sweet_", "").replace("_w", "")
        ax.text(0.98, 0.03, short, transform=ax.transAxes, ha="right", va="bottom",
                fontsize=8, color="0.3")
        ax.legend(loc="upper left")
        ps.save(fig, f"f_ttt_traj_{cell}")


if __name__ == "__main__":
    main()
