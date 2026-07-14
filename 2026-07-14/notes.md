# 2026-07-14 작업 노트 (07-13 세션 연속)
세션 로그 본문은 2026-07-13/notes.md §12~17에 연속 기록(원복·Phase 0/1/2·155 추적).

## warm-up 제외 규약 채택 (사용자 지시)
- 표준 관행대로 T=10800 계열(warm 3600+이벤트+쿨다운)은 **분석창 [3600s,10800s]**로 집계.
  쿨다운은 미룬 혼잡이 청구되는 구간이라 포함 유지. 도구: work/windowed_ttt.py
  (run_log cumulative 차분, 재실행 불필요). 결과: results/windowed_ttt_T10800.txt.
- 창 분리 후에도 **모든 arm 간 Δ·순위 불변**(워밍업 몫 ~270 veh·h이 arm 간 동일 상쇄):
  dmid_w +63.8 / dhigh_w −22.3 / dhigh2_w +2,287.9 / dsust·dsym 동일.
- 원 프로그램(T=7200 sweet·T=3600 펄스)은 설계상 warm-up 구간이 없어 전 구간 집계 유지
  (빈 망 충전 과도는 실험의 일부, 전 arm 공유). delay 지표는 자유류 ref 차감이라
  워밍업 중립임을 병기.

## 155 귀속 판정 + 구성 매트릭스 (진행)
- hinge-off: 7,921.3 (−572, vs PFO −108 승) — hinge가 신 기하에서 만료(보험료 전액 회수).
- **INEQ: 7,585.0 (−909, vs PFO −444 승) — whipsaw가 더 큰 범인.** 등식 사영의 N_UF*
  1,500 추락 제거, f_dly·ton 최저. 두 수술 각각 독립으로 155 역전 회복.
- 구성 후보: ①locked+INEQ ②hinge-off ③combo(INEQ+hinge-off) → 3구성×3셀(155/155_skew/190)
  매트릭스 실행 중(_trace155). 완성 후 production 구성 승인 요청 예정.
- 사용자 방침: **구성 확정 전 표 채우기 중단**(sweet_w 체인 보류). 웜업은 NC로 돌리는
  구조(WARMUP_NC_STEPS 훅)를 구성 확정 후 러너에 추가하고 sweet_w 재발주.

## 층2+3 구현 + 파국 차단 실증 (워크트리 Numerical-Sim-l23, 병합 대기)
- 구현: β̂ 추정기(BETA_EST)·β̂-guard(GUARD_BETA)·trailing-regret(REGRET_K)·기하 지문 경고·
  재캘리브레이션 트리거·카나리아(work/component_canary.py, 기본 T=3600). OFF 비트동일(sha256).
- **파국 셀 실증(dhigh2_w PD4+FBOFF+REGRET_K=3): 6,966.6 → 5,046.6, 잔존 3,002 → 165**
  (PFO 4,678/161과 동급 청산) — regret 12스텝 발화·강제 incumbent. 하방 +49% → +7.9%.
- **핵심 발견 2건**: ① 이 코드베이스는 모델≡plant(1스텝 예측 비트일치)라 β̂≈1.0 —
  "낙관"의 실체는 held-plan 채점의 시간 비일관성(whipsaw)+far 근사이며 frozen coupling은
  예측 오차가 아니라 선택 오차(ε-gap의 몫). ② 병리는 자기예측으로는 불가시(β̂ max 1.006),
  **참조정책 regret(실현 vs incumbent 예측)만이 감지** — incumbent 앵커 guard와 실현-return
  학습(RL) 논거의 정밀한 형태.
