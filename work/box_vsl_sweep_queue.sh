#!/bin/bash
# 박스 최종 스윕(2026-07-17, 사용자 지시): VSL_BOX=10(previous 앵커) 고정 +
# metering 박스 3팔 — up300(대칭)/up600/up900 (내림은 전부 300).
#
# 이전 up 스윕(12:04 발주)은 VSL 미수정 상태라 사용자 지시로 중단·폐기.
# 이번엔 세 팔 모두 VSL_BOX=10을 얹어 다시 — 대칭 up300도 재실행해야 비교가 맞다
# (기존 _pd4_box300은 VSL 앵커 구멍이 열린 채였음).
#
# 배치: 20코어라 (up300+up600) 20런 먼저, 완료 후 up900 10런.
# 판정: (1) 파국 2셀(170_w/200_w) 복구 (2) 6셀 1등·190 복구 유지 (3) invariant
#   metering 내림≤300 / VSL ≤10 전 셀 — 깨지면 해당 arm VOID.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/box_vsl_sweep.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"

say "=== 배치 1: up300+up600 (VSL_BOX=10) 20런 발주 ==="
for S in $CELLS; do
  ( VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
    CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_box300_vsl10/$S" \
    > "outputs/_logs/bv300_$S.log" 2>&1 ) &
  ( VSL_BOX=10 METER_BOX=300 METER_BOX_UP=600 NP_PD_ITER=4 NP_BIAS=1 \
    CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_boxup600_vsl10/$S" \
    > "outputs/_logs/bv600_$S.log" 2>&1 ) &
done
wait
say "=== 배치 1 완료 — 배치 2: up900 10런 발주 ==="
for S in $CELLS; do
  ( VSL_BOX=10 METER_BOX=300 METER_BOX_UP=900 NP_PD_ITER=4 NP_BIAS=1 \
    CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_boxup900_vsl10/$S" \
    > "outputs/_logs/bv900_$S.log" 2>&1 ) &
done
wait
say "=== 스윕 종료: 30런 완료 ==="
