# urban queue 궤적 그림 — 총 movement queue [veh]를 5컨트롤러 비교(축적·해소)
"""urban movement queue 총합 = Σ movement_queue_* [veh]. 대표 고부하 시나리오에서
NC(폭발)·Wu·PFO(box)·Centralized·P-Stack이 urban 큐를 어떻게 억제·배수하는지 단일 axes로 대조.
계층 컨트롤러가 freeway뿐 아니라 urban 저수지도 관리함을 보인다(사용자: urban 부재 보완)."""
import numpy as np
import pubstyle as ps

CELL = "sweet_190_w"   # 고부하 — urban 축적이 가장 극적


def urban_queue_series(arm):
    st = ps.load(arm, CELL, "state_timeseries")
    mq_cols = [c for c in st.columns if c.startswith("movement_queue_")]
    total = st[mq_cols].to_numpy(float).sum(axis=1)
    step = st["step"].to_numpy(float) if "step" in st.columns else np.arange(len(total))
    return step, total


def main():
    ps.sanity_gate()
    fig, ax = ps.new_fig(width=3.6, height=2.5)
    ps.shade_warmup(ax)
    for arm in ps.CONTROLLERS:
        step, q = urban_queue_series(arm)
        ax.plot(ps.minutes(step), q, **ps.style(arm))
    ps.time_axis(ax)
    ax.set_ylabel("Total urban queue (veh)")
    ax.legend(loc="upper left", ncol=1)
    ax.set_title(f"Urban queue trajectory — {ps.scen(CELL)}")
    ps.save(fig, "f_urban_queue")
    # 콘솔 요약: 최종 urban 큐
    for arm in ps.CONTROLLERS:
        _, q = urban_queue_series(arm)
        print(f"  {ps.LABEL[arm]:<20} peak={q.max():.0f} final={q[-1]:.0f} veh")


if __name__ == "__main__":
    main()
