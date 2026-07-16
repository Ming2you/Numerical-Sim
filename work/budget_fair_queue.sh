#!/bin/bash
# BUDGET_FAIR A/B 큐(2026-07-16) — 반경 A/B(40런) 완료 대기 후 20런.
# 대조군은 이미 확보: fair=OFF × crossOFF = ③(_farsa), fair=OFF × crossON = ④(_farsa_crosson)
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/budget_fair.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"

say "=== BUDGET_FAIR 큐 시작 — 반경 A/B(r1500·r1200 각 20런) 완료 대기 ==="

# ---- 반경 A/B 40런이 다 끝날 때까지 대기(최대 4시간) ----
# 파일 존재로 판정한다(powershell 프로세스 카운트는 git bash에서 빈 값이 나와 못 씀 — 오늘 실패).
deadline=$(( $(date +%s) + 14400 ))
while true; do
  n=0
  for TAG in r1500 r1200; do
    for D in off on; do
      for S in $CELLS; do
        [ -f "outputs/_${TAG}_${D}/${S}/${CTRL}/run_log.csv" ] && n=$((n+1))
      done
    done
  done
  say "반경 A/B 대기: ${n}/40 완료"
  [ "$n" -ge 40 ] && { say "반경 A/B 완료 — BUDGET_FAIR 발주"; break; }
  [ "$(date +%s)" -ge "$deadline" ] && { say "4시간 초과 — ${n}/40인 채로 진행"; break; }
  sleep 180
done

say "발주: BUDGET_FAIR=1 × {cross OFF, ON} × 10셀"
for S in $CELLS; do
  ( BUDGET_FAIR=1 CROSS_OFF=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_fair_off/$S" \
    > "outputs/_logs/fair_off_$S.log" 2>&1 ) &
  ( BUDGET_FAIR=1 CROSS_ON=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_fair_on/$S" \
    > "outputs/_logs/fair_on_$S.log" 2>&1 ) &
done
wait
say "=== BUDGET_FAIR 큐 종료: 20런 완료 ==="
