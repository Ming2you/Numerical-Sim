# per-step TTT 궤적 — 5컨트롤러 비교, 5시나리오 각 1장 (f_ttt_traj_<cell>)
"""각 시나리오에서 no control / wu / pfo (box) / centralized / p-stack(walk-MVG)의
스텝별 TTT(누적 차분) 궤적을 단일 axes로 대조. §1 거시성능 핵심 그림."""
import numpy as np

import pubstyle as ps


def main():
    ps.sanity_gate()
    for cell in ps.CELLS:
        fig, ax = ps.new_fig()
        ps.shade_warmup(ax)
        for arm in ps.CONTROLLERS:
            rl = ps.load(arm, cell, "run_log", usecols=["step", "cumulative_total_ttt"])
            cum = rl["cumulative_total_ttt"].to_numpy()
            step_ttt = np.diff(cum, prepend=0.0)  # 첫 행 = step 0의 TTT
            ax.plot(ps.minutes(rl["step"]), step_ttt, **ps.style(arm))
        ps.time_axis(ax)
        ax.set_ylabel("TTT per step (veh·h)")
        ax.text(0.98, 0.03, ps.scen(cell), transform=ax.transAxes, ha="right", va="bottom",
                fontsize=8, color="0.3")
        ax.legend(loc="upper left")
        ps.save(fig, f"f_ttt_traj_{cell}")


if __name__ == "__main__":
    main()
