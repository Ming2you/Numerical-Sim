#!/bin/bash
# BOX-WALK-VG A/B(2026-07-17 4차): walk-M(_pd4_box_walk) 완료 대기 후 walk-MVG 10런.
# 3점 비교가 성립: 300+vsl10(walk 없음) vs walk-M(metering만) vs walk-MVG(M+VSL+green)
#   → 200_w 복구에 어느 레버의 rollout 시야가 필요한지 절연(ablation).
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/box_walk_vg.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }
CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"
say "=== walk-M 10런 완료 대기 ==="
deadline=$(( $(date +%s) + 7200 ))
while true; do
  n=0
  for S in $CELLS; do
    [ -f "outputs/_pd4_box_walk/${S}/${CTRL}/run_log.csv" ] && n=$((n+1))
  done
  say "walk-M 대기: ${n}/10"
  [ "$n" -ge 10 ] && { say "walk-M 완료 — walk-MVG 발주"; break; }
  [ "$(date +%s)" -ge "$deadline" ] && { say "2시간 초과 — ${n}/10인 채로 진행"; break; }
  sleep 120
done
for S in $CELLS; do
  ( BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
    CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_box_walk_vg/$S" \
    > "outputs/_logs/boxwalkvg_$S.log" 2>&1 ) &
done
wait
say "=== walk-MVG 종료: 10런 완료 ==="
