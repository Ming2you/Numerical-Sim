# 그림1: 190_w 램프별 metering 시계열 — pd4_ref(진동) vs walk_mvg(침착) 4장 (f_meter_<ramp>_190w)
import pubstyle as ps

CELL = "sweet_190_w"
RAMPS = ["R_D_E", "R_D_W", "R_F_E", "R_F_W"]
ARMS = ["pd4_ref", "walk_mvg"]


def main():
    ps.sanity_gate()
    for ramp in RAMPS:
        col = f"ramp_metering_{ramp}"
        fig, ax = ps.new_fig()
        ps.shade_warmup(ax)
        for arm in ARMS:
            ct = ps.load(arm, CELL, "control_timeseries", usecols=["step", col])
            ax.plot(ps.minutes(ct["step"]), ct[col], drawstyle="steps-post",
                    label=ps.LABEL[arm], **ps.STYLE[arm])
        ps.time_axis(ax)
        ax.set_ylabel("Ramp metering rate (veh/h)")
        ax.text(0.98, 0.03, ramp.replace("_", "–"), transform=ax.transAxes,
                ha="right", va="bottom", fontsize=8, color="0.3")
        ax.legend(loc="lower left")
        ps.save(fig, f"f_meter_{ramp}_190w")


if __name__ == "__main__":
    main()
