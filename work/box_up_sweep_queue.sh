#!/bin/bash
# 비대칭 박스 up 스윕(2026-07-17, 사용자 설계 2차): 내림 300 고정, 올림 {600, 900}.
# up300(대칭)은 기존 _pd4_box300 재사용 — 3점 스윕 {300,600,900} 완성.
# 판정 축:
#   (1) 파국 2셀(170_w/200_w) 복구되나 — '하방 고착'이 원인이면 올림 확대로 풀려야.
#   (2) 대칭의 승리 6셀·190 복구가 유지되나 — 올림 확대가 진동을 되살리면 깨질 수 있음.
#   (3) invariant: 내림 ≤300 전 셀 유지(안 지켜지면 VOID).
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/box_up_sweep.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"

say "=== up 스윕 발주: up600 10셀 + up900 10셀 (20코어 동시) ==="
for S in $CELLS; do
  ( METER_BOX=300 METER_BOX_UP=600 NP_PD_ITER=4 NP_BIAS=1 \
    CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_boxup600/$S" \
    > "outputs/_logs/boxup600_$S.log" 2>&1 ) &
  ( METER_BOX=300 METER_BOX_UP=900 NP_PD_ITER=4 NP_BIAS=1 \
    CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_boxup900/$S" \
    > "outputs/_logs/boxup900_$S.log" 2>&1 ) &
done
wait
say "=== up 스윕 종료: 20런 완료 ==="
