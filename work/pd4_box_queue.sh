#!/bin/bash
# PD4 + METER-BOX(R=300) 10런(2026-07-17, 사용자 설계) — pd4_strict 완료 대기 후 발주.
#
# 설계: SEG13 metering 후보 = 고정 격자 대신 m_prev±300 이동 박스 5점 + 예산 사영도
#   같은 박스. 근거·검증은 커밋 0314db7 참조(비트동일/영수증/invariant 3중 통과).
# 판별 질문 2개:
#   (1) TTT — PD4의 190/200 손해(-2.79%/+0.92%)가 진동 때문이었나. 박스가 진동을
#       구조적으로 없앴으니(per-ramp |Δ| ≤ 300, 기존 1199) 살아나면 인과 확정.
#   (2) 끝점이 진짜냐 — wu_seg13_meter_box_edge/total. 정상상태에서 내부 정착이면
#       '진짜 최적은 내부, bang-bang은 선형 외삽의 산물'(사용자 가설) 확증.
#       계속 100% 끝이면 끝점이 실재고 박스는 그저 감속기.
# 주의: incident 셀 — 1500→375까지 4스텝(12분). 대응 지연 손해 가능, 그 셀들 주시.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/pd4_box.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"

say "=== PD4+METER_BOX(300) 큐 시작 — pd4_strict 10런 완료 대기 ==="
deadline=$(( $(date +%s) + 10800 ))
while true; do
  n=0
  for S in $CELLS; do
    [ -f "outputs/_pd4_strict1200/${S}/${CTRL}/run_log.csv" ] && n=$((n+1))
  done
  say "pd4_strict 대기: ${n}/10"
  [ "$n" -ge 10 ] && { say "pd4_strict 완료 — METER_BOX 발주"; break; }
  [ "$(date +%s)" -ge "$deadline" ] && { say "3시간 초과 — ${n}/10인 채로 진행"; break; }
  sleep 180
done

say "발주: PD4 + METER_BOX=300, 10셀"
for S in $CELLS; do
  ( METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
    CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_box300/$S" \
    > "outputs/_logs/pd4box_$S.log" 2>&1 ) &
done
wait
say "=== PD4+METER_BOX(300) 종료: 10런 완료 ==="
