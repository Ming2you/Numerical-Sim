# 그림7: 190_w λ_P step plot — pd4_ref의 {0,10} bang-bang, farsa_ref는 평평한 0 참조 (f_lambda_190w)
import pubstyle as ps

CELL = "sweet_190_w"
COL = "wu_faithful_lambda_P"  # ★진짜 λ — leader_lambda_np_committed는 boolean이라 금지


def main():
    ps.sanity_gate()
    fig, ax = ps.new_fig()
    ps.shade_warmup(ax)
    for arm in ("pd4_ref", "farsa_ref"):
        rl = ps.load(arm, CELL, "run_log", usecols=["step", COL])
        ax.plot(ps.minutes(rl["step"]), rl[COL], drawstyle="steps-post",
                label=ps.LABEL[arm], **ps.STYLE[arm])
    ps.time_axis(ax)
    ax.set_ylabel(r"$\lambda_P$")
    ax.set_ylim(-0.6, 11.2)
    ax.legend(loc="center left")
    ps.save(fig, "f_lambda_190w")


if __name__ == "__main__":
    main()
