# urban green split 반응 그림 — 대표 신호의 phase-1 green split을 5컨트롤러 비교(조정 능동성)
"""green split = green_p1/(green_p1+green_p2) — 교차로가 phase1 방향에 배분하는 green 비율.
skewed 시나리오(비대칭 부하)에서 5컨트롤러 중 변동이 가장 큰 신호를 자동 선택해,
NC(고정)·PFO(box)·Wu·Centralized·P-Stack의 배분 능동성을 단일 axes로 대조."""
import numpy as np
import pubstyle as ps

CELL = "sweet_170_skew15_w"   # 비대칭 부하 — green 배분 차이가 가장 드러남
SIGNALS = ["A", "B", "C", "D", "F"]


def split_series(arm, sig):
    ct = ps.load(arm, CELL, "control_timeseries",
                 usecols=["step", f"green_{sig}_p1", f"green_{sig}_p2"])
    p1 = ct[f"green_{sig}_p1"].to_numpy(float)
    p2 = ct[f"green_{sig}_p2"].to_numpy(float)
    tot = np.clip(p1 + p2, 1e-9, None)
    return ct["step"].to_numpy(float), p1 / tot


def main():
    ps.sanity_gate()
    # 5컨트롤러 합산 변동이 최대인 신호 선택
    best_sig, best_var = SIGNALS[0], -1.0
    for sig in SIGNALS:
        v = sum(float(np.std(split_series(a, sig)[1])) for a in ps.CONTROLLERS)
        if v > best_var:
            best_sig, best_var = sig, v
    sig = best_sig

    fig, ax = ps.new_fig(width=3.6, height=2.5)
    ps.shade_warmup(ax)
    for arm in ps.CONTROLLERS:
        step, sp = split_series(arm, sig)
        ax.plot(ps.minutes(step), sp * 100.0, **ps.style(arm))
    ps.time_axis(ax)
    ax.set_ylabel(f"Signal {sig} phase-1 green split (%)")
    ax.set_ylim(30, 75)
    ax.legend(loc="upper right", ncol=1)
    ax.set_title(f"Green split response — {ps.scen(CELL)}")
    ps.save(fig, "f_urban_green_split")
    print(f"  선택 신호 = {sig} (5컨트롤러 합산 std={best_var:.3f})")


if __name__ == "__main__":
    main()
