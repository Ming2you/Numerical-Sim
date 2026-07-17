# 그림3: 200_w 리더 의도 N_UF* 시계열 — 3190 고착(box) vs 5805 해방(walk) 서사 (f_intent_200w)
import pubstyle as ps

CELL = "sweet_200_w"
ARMS = ["farsa_ref", "box300_vsl10_ref", "walk_mvg"]
COL = "leader_candidate_best_intent_N_UF_star"  # ★의도 컬럼 — run_log의 N_UF_star는 realized라 금지


def main():
    ps.sanity_gate()
    fig, ax = ps.new_fig()
    ps.shade_warmup(ax)
    for arm in ARMS:
        rl = ps.load(arm, CELL, "run_log", usecols=["step", COL])
        ax.plot(ps.minutes(rl["step"]), rl[COL], drawstyle="steps-post",
                label=ps.LABEL[arm], **ps.STYLE[arm])
    ps.time_axis(ax)
    ax.set_ylabel(r"Leader intent $N_{UF}^{\ast}$ (veh)")
    ax.legend(loc="lower left")
    ps.save(fig, "f_intent_200w")


if __name__ == "__main__":
    main()
