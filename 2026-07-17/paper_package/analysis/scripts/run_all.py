# 전체 파이프라인 드라이버 — sanity gate 후 5컨트롤러 비교·urban·메커니즘 그림 + 표1 생성
# (200_w 회복서사 3종 fig_intent/fig_meter_total/fig_tttgap은 200 제외로 파이프라인에서 제거)
import f_mfd
import f_rampq
import f_rho
import fig_lambda
import fig_meter_ramps
import fig_rung_hist
import fig_ttt_traj
import fig_urban_green
import fig_urban_queue
import fig_vsl_seg
import make_table1
import pubstyle as ps

MODULES = [fig_ttt_traj,                       # §1 5컨트롤러 거시비교
           fig_urban_green, fig_urban_queue,   # §2 urban 메커니즘(신규)
           fig_meter_ramps, fig_vsl_seg, fig_lambda, fig_rung_hist,
           f_rampq, f_rho, f_mfd,              # §2/§3 freeway 메커니즘
           make_table1]


def main():
    ps.sanity_gate()  # 한 번은 명시적으로 (각 모듈도 자체 호출하나 캐시로 비용 없음)
    for m in MODULES:
        print(f"== {m.__name__} ==")
        m.main()
    print("done.")


if __name__ == "__main__":
    main()
