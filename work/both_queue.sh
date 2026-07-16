#!/bin/bash
# 파4: STRICT r=1200 + BUDGET_FAIR 조합 A/B — 파3(BUDGET_FAIR 단독) 완료 대기 후 20런.
# 별도 파일로 둔 이유: 실행 중인 budget_fair_queue.sh를 편집하면 bash가 증분 읽기라 깨진다.
#
# 상호작용 검정. 단일 인자가 각각 무해해도 둘 다 켜야 효과가 나는 경우를 잡는다:
#   STRICT 단독 = 좁은 범위인데 np-major 절단으로 여전히 N_P 축이 굶음
#   FAIR   단독 = 고르게 보지만 반경 밖으로 멀리 튐
#   조합       = **좁은 범위를 고르게**  (사용자 지적 2026-07-16)
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/both_ab.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"

say "=== 파4(STRICT r1200 + FAIR) 큐 시작 — 파3(_fair_*) 20런 완료 대기 ==="

deadline=$(( $(date +%s) + 21600 ))   # 6시간 안전장치
while true; do
  n=0
  for D in off on; do
    for S in $CELLS; do
      [ -f "outputs/_fair_${D}/${S}/${CTRL}/run_log.csv" ] && n=$((n+1))
    done
  done
  say "파3 대기: ${n}/20 완료"
  [ "$n" -ge 20 ] && { say "파3 완료 — 파4 발주"; break; }
  [ "$(date +%s)" -ge "$deadline" ] && { say "6시간 초과 — ${n}/20인 채로 진행"; break; }
  sleep 180
done

say "발주 파4: NUF_RADIUS_STRICT=1 NUF_RADIUS=1200 BUDGET_FAIR=1 × {cross OFF, ON} × 10셀"
for S in $CELLS; do
  ( NUF_RADIUS_STRICT=1 NUF_RADIUS=1200 BUDGET_FAIR=1 CROSS_OFF=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_both_off/$S" \
    > "outputs/_logs/both_off_$S.log" 2>&1 ) &
  ( NUF_RADIUS_STRICT=1 NUF_RADIUS=1200 BUDGET_FAIR=1 CROSS_ON=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_both_on/$S" \
    > "outputs/_logs/both_on_$S.log" 2>&1 ) &
done
wait
say "=== 파4 종료: 20런 완료 (전체 80런 완료) ==="
