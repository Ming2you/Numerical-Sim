# 그림8: 190_w 커밋 metering 값 분포(채점창 step 20..59, 4램프 풀링) — pd4_ref 끝점 집중 vs walk_mvg 박스워크 (f_rung_hist_190w)
import numpy as np

import pubstyle as ps

CELL = "sweet_190_w"
RAMP_COLS = [f"ramp_metering_R_{ab}_{d}" for ab in ("D", "F") for d in ("E", "W")]


def pooled(arm):
    ct = ps.load(arm, CELL, "control_timeseries", usecols=["step"] + RAMP_COLS)
    post = ct[ct["step"] >= ps.WARM_STEPS]  # 채점창만 (웜업 NC 값 제외)
    return post[RAMP_COLS].to_numpy().ravel()


def main():
    ps.sanity_gate()
    pd4 = pooled("pd4_ref")
    walk = pooled("walk_mvg")
    lo = np.floor(min(pd4.min(), walk.min()) / 25) * 25
    hi = np.ceil(max(pd4.max(), walk.max()) / 25) * 25
    bins = np.arange(lo, hi + 25, 25)  # 25 veh/h 빈

    fig, ax = ps.new_fig()
    ax.hist(pd4, bins=bins, color=ps.STYLE["pd4_ref"]["color"], alpha=0.45,
            label=ps.LABEL["pd4_ref"], edgecolor="none")
    ax.hist(walk, bins=bins, histtype="step", color=ps.STYLE["walk_mvg"]["color"],
            linewidth=1.2, label=ps.LABEL["walk_mvg"])
    ax.set_xlabel("Committed ramp metering rate (veh/h)")
    ax.set_ylabel("Count (ramp×step)")
    ax.legend(loc="upper left")
    print(f"pd4 endpoints: min {pd4.min():.1f} max {pd4.max():.1f} | "
          f"share at max-bin {np.mean(pd4 >= bins[-2]) * 100:.1f}%")
    ps.save(fig, "f_rung_hist_190w")


if __name__ == "__main__":
    main()
