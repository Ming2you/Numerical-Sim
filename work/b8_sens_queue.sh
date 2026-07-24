#!/bin/bash
# B8 민감도 소표(2026-07-18 밤): walk-MVG 기준, horizon {2,4} × 2셀 + METER_BOX R {225,375} × 2셀.
# 완결성 감사 P1-B8 — 컨트롤러 파라미터 민감도. 수요 민감도는 시나리오 격자가 담당.
# 기본값: horizon 3(default.yaml), R 300. SLSQP 6런과 병행(코어 여유 14).
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/b8_sens.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }
BASE="BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 NP_PD_ITER=4 NP_BIAS=1 CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20"
say "=== B8 민감도 8런 발주 ==="
for S in sweet_170_w sweet_190_w; do
  ( HORIZON=2 METER_BOX=300 BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 NP_PD_ITER=4 NP_BIAS=1 CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_sens_h2/$S" > "outputs/_logs/sens_h2_$S.log" 2>&1 ) &
  ( HORIZON=4 METER_BOX=300 BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 NP_PD_ITER=4 NP_BIAS=1 CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_sens_h4/$S" > "outputs/_logs/sens_h4_$S.log" 2>&1 ) &
  ( METER_BOX=225 BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 NP_PD_ITER=4 NP_BIAS=1 CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_sens_r225/$S" > "outputs/_logs/sens_r225_$S.log" 2>&1 ) &
  ( METER_BOX=375 BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 NP_PD_ITER=4 NP_BIAS=1 CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_sens_r375/$S" > "outputs/_logs/sens_r375_$S.log" 2>&1 ) &
done
wait
say "=== B8 민감도 완료 ==="
