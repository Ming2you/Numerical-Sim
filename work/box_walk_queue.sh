#!/bin/bash
# BOX-WALK A/B(2026-07-17 3차): 300+vsl10 + BOX_WALK=1, 10셀.
# 판정: (1) 200_w — 회복기(step 40+) 리더 intent가 6000으로 올라가나(가설 확증) +
#   TTT −29.78% 복구되나. (2) 승리 셀들(중앙 +6.22%)이 유지되나 — walk가 전 셀의
#   V 채점을 바꾸므로 부작용 가능. (3) invariant 유지(내림≤300, VSL≤10).
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/box_walk.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }
CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"
say "=== BOX_WALK 10런 발주 ==="
for S in $CELLS; do
  ( BOX_WALK=1 VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
    CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_box_walk/$S" \
    > "outputs/_logs/boxwalk_$S.log" 2>&1 ) &
done
wait
say "=== BOX_WALK 종료: 10런 완료 ==="
