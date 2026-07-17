# 그림6: 190_w VSL 시계열 — farsa_ref에서 이동량 최대 세그먼트 자동 선택, farsa vs walk (f_vsl_seg_190w)
import numpy as np

import pubstyle as ps

CELL = "sweet_190_w"
SEG_COLS = [f"vsl_FW_{d}_seg{i}" for d in ("E", "W") for i in range(8)]


def main():
    ps.sanity_gate()
    far = ps.load("farsa_ref", CELL, "control_timeseries", usecols=["step"] + SEG_COLS)
    # 이동량 = Σ|Δ| (farsa_ref 기준) — 가장 많이 움직인 세그먼트 선택
    movement = {c: float(np.abs(np.diff(far[c].to_numpy())).sum()) for c in SEG_COLS}
    seg = max(movement, key=movement.get)
    rank = sorted(movement.items(), key=lambda kv: -kv[1])
    print("VSL movement ranking (farsa_ref, sum|diff| km/h):")
    for c, m in rank[:5]:
        print(f"  {c}: {m:.0f}")
    print(f"selected segment: {seg}")

    fig, ax = ps.new_fig()
    ps.shade_warmup(ax)
    for arm in ("farsa_ref", "walk_mvg"):
        ct = ps.load(arm, CELL, "control_timeseries", usecols=["step", seg])
        ax.plot(ps.minutes(ct["step"]), ct[seg], drawstyle="steps-post",
                label=ps.LABEL[arm], **ps.STYLE[arm])
    ps.time_axis(ax)
    ax.set_ylabel("VSL (km/h)")
    ax.text(0.98, 0.03, seg.replace("vsl_", "").replace("_", "–"),
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="0.3")
    ax.legend(loc="lower left")
    ps.save(fig, "f_vsl_seg_190w")


if __name__ == "__main__":
    main()
