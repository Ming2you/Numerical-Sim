# 전체 파이프라인 드라이버 — sanity gate 후 그림(1차 8종 + 2차 ramp큐/밀도/MFD) + 표1 골격을 순차 생성
import f_mfd
import f_rampq
import f_rho
import fig_intent
import fig_lambda
import fig_meter_ramps
import fig_meter_total
import fig_rung_hist
import fig_ttt_traj
import fig_tttgap
import fig_vsl_seg
import make_table1
import pubstyle as ps

MODULES = [fig_meter_ramps, fig_meter_total, fig_intent, fig_tttgap,
           fig_ttt_traj, fig_vsl_seg, fig_lambda, fig_rung_hist,
           f_rampq, f_rho, f_mfd, make_table1]


def main():
    ps.sanity_gate()  # 한 번은 명시적으로 (각 모듈도 자체 호출하나 캐시로 비용 없음)
    for m in MODULES:
        print(f"== {m.__name__} ==")
        m.main()
    print("done.")


if __name__ == "__main__":
    main()
