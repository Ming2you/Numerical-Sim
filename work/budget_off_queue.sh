#!/bin/bash
# "예산 없이 가격만" A/B 큐(2026-07-16, 사용자 제안) — NP_BIAS 20런 완료 대기 후 20런.
#
# 질문: +4.78%(③ vs PFO)가 예산 몫인가 가격 몫인가?
#   arm A: BUDGET_OFF        — N_UF hard budget 제거. λ_UF·λ_P·가격 전부 유지
#   arm B: BUDGET_OFF+NP_OFF — N_P dual(λ_P)까지 제거 = **순수 가격 조정**
# 대조군: ③(_farsa) = 예산+가격 전부 ON.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/budget_off.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"

say "=== '가격만' 큐 시작 — NP_BIAS 20런(npbias 10 + npbias_pd4 10) 완료 대기 ==="

deadline=$(( $(date +%s) + 10800 ))   # 3시간 안전장치
while true; do
  n=0
  for D in _npbias _npbias_pd4; do
    for S in $CELLS; do
      [ -f "outputs/${D}/${S}/${CTRL}/run_log.csv" ] && n=$((n+1))
    done
  done
  say "NP_BIAS 대기: ${n}/20 완료"
  [ "$n" -ge 20 ] && { say "NP_BIAS 완료 — '가격만' 발주"; break; }
  [ "$(date +%s)" -ge "$deadline" ] && { say "3시간 초과 — ${n}/20인 채로 진행"; break; }
  sleep 180
done

say "발주: arm A(BUDGET_OFF) 10셀 + arm B(BUDGET_OFF+NP_OFF) 10셀 — 전부 ③ 기반(FAR_STATE_AWARE, cross OFF)"
for S in $CELLS; do
  ( BUDGET_OFF=1 CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_budgetoff/$S" \
    > "outputs/_logs/budgetoff_$S.log" 2>&1 ) &
  ( BUDGET_OFF=1 NP_OFF=1 CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pricesonly/$S" \
    > "outputs/_logs/pricesonly_$S.log" 2>&1 ) &
done
wait
say "=== '가격만' 큐 종료: 20런 완료 ==="
