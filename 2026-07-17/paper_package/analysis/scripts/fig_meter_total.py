# 그림2: 200_w 총 metering(4램프 합) 시계열 — farsa_ref / box300_vsl10_ref / walk_mvg (f_meter_total_200w)
import pubstyle as ps

CELL = "sweet_200_w"
ARMS = ["farsa_ref", "box300_vsl10_ref", "walk_mvg"]
RAMP_COLS = [f"ramp_metering_R_{ab}_{d}" for ab in ("D", "F") for d in ("E", "W")]


def main():
    ps.sanity_gate()
    fig, ax = ps.new_fig()
    ps.shade_warmup(ax)
    for arm in ARMS:
        ct = ps.load(arm, CELL, "control_timeseries", usecols=["step"] + RAMP_COLS)
        total = ct[RAMP_COLS].sum(axis=1)
        ax.plot(ps.minutes(ct["step"]), total, drawstyle="steps-post",
                label=ps.LABEL[arm], **ps.STYLE[arm])
    ps.time_axis(ax)
    ax.set_ylabel("Total ramp metering, 4 ramps (veh/h)")
    ax.legend(loc="lower left")
    ps.save(fig, "f_meter_total_200w")


if __name__ == "__main__":
    main()
