#!/bin/bash
# walk-MVG 단독(2026-07-17, 사용자 지시: walk-M 중단·MVG만).
# 비교 기준: 300+vsl10(walk 없음, 완료) vs walk-MVG(metering 목표추적 + VSL/green 끝지속).
# 판정: (1) 200_w 회복기 intent 3,300 고착이 풀리나 + TTT -29.78% 복구 (2) 승리 셀 유지
#   (3) invariant(내림<=300, VSL<=10) — 커밋 무결성은 사전 검증 통과(green 합 112 보존).
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/mvg_only.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }
CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"
say "=== walk-MVG 10런 발주 ==="
for S in $CELLS; do
  ( BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
    CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_box_walk_vg/$S" \
    > "outputs/_logs/boxwalkvg_$S.log" 2>&1 ) &
done
wait
say "=== walk-MVG 종료: 10런 완료 ==="
