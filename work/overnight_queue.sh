#!/bin/bash
# 야간 자동 큐(2026-07-16): 현재 16런 완료 대기 → 다음 2배치(16런) 자동 발주.
# 구성 결정은 하지 않는다 — 데이터만 확보하고 판정은 사용자가 아침에.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/overnight.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

say "=== 야간 큐 시작 ==="

# ---- 1) 현재 16런 완료 대기 (최대 3시간) ----
WAIT_FOR=(
  "outputs/_gref180_crosson/sweet_155_incident_w" "outputs/_gref180_crosson/sweet_170_incident_w"
  "outputs/_skew15_crosson/sweet_155_skew15_w"    "outputs/_skew15_crosson/sweet_170_skew15_w"
  "outputs/_noterm/sweet_170_w"        "outputs/_noterm/sweet_155_skew_w"
  "outputs/_noterm/sweet_170_skew_w"   "outputs/_noterm/sweet_155_incident_w"
  "outputs/_noterm/sweet_170_incident_w"
  "outputs/_farsa/sweet_155_w"         "outputs/_farsa/sweet_155_skew_w"
  "outputs/_farsa/sweet_155_incident_w" "outputs/_farsa/sweet_170_w"
  "outputs/_farsa/sweet_170_skew_w"    "outputs/_farsa/sweet_170_incident_w"
  "outputs/_farsa/sweet_200_w"
)
deadline=$(( $(date +%s) + 10800 ))
while true; do
  n=0
  for d in "${WAIT_FOR[@]}"; do
    [ -f "$d/$CTRL/run_log.csv" ] && n=$((n+1))
  done
  say "대기 중: ${n}/${#WAIT_FOR[@]} 완료"
  [ "$n" -ge "${#WAIT_FOR[@]}" ] && { say "1차 16런 전부 완료"; break; }
  [ "$(date +%s)" -ge "$deadline" ] && { say "3시간 초과 — ${n}/${#WAIT_FOR[@]}인 채로 진행"; break; }
  sleep 120
done

CELLS="sweet_155_w sweet_155_skew_w sweet_155_incident_w sweet_170_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"

# ---- 2) ③ E1: state-aware terminal + 가격 far (cross OFF) — 태스크 #44 ----
say "발주: _farsa_price (state-aware + 가격far, cross OFF) 8셀"
for S in $CELLS; do
  CROSS_OFF=1 FAR_STATE_AWARE=1 MFD_FAR_PRICE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_farsa_price/$S" > "outputs/_logs/farsaprice_$S.log" 2>&1 &
done

# ---- 3) state-aware terminal × cross ON — 채택 시 매트릭스 재구성에 필요 ----
say "발주: _farsa_crosson (state-aware, cross ON) 8셀"
for S in $CELLS; do
  FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_farsa_crosson/$S" > "outputs/_logs/farsaon_$S.log" 2>&1 &
done

say "16런 발주 완료 — 대기"
wait
say "=== 야간 큐 종료: 전부 완료 ==="
