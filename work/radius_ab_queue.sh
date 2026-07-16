#!/bin/bash
# 반경 A/B 자동 큐(2026-07-16) — 리뷰어 에이전트가 코어를 비우면 2파로 40런.
# 파1: STRICT r=1500 × {cross OFF, ON} × 10셀
# 파2: STRICT r=1200 × {cross OFF, ON} × 10셀   (trust 산수 복원치)
# 대조군은 이미 확보: 반경현행×crossOFF=③(_farsa), 반경현행×crossON=④(_farsa_crosson)
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/radius_ab.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"

say "=== 반경 A/B 큐 시작 ==="

# ---- 리뷰어 에이전트가 코어를 비울 때까지 대기(최대 60분) ----
deadline=$(( $(date +%s) + 3600 ))
while true; do
  n=$(powershell.exe -NoProfile -Command \
      "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\").Count" 2>/dev/null | tr -d '\r')
  n=${n:-0}
  say "코어 대기: python ${n}개 실행중"
  [ "$n" -le 4 ] && { say "코어 확보 — 파1 발주"; break; }
  [ "$(date +%s)" -ge "$deadline" ] && { say "60분 초과 — 그대로 진행"; break; }
  sleep 120
done

wave() {  # $1=radius  $2=출력접두
  local R="$1" TAG="$2"
  say "발주: ${TAG} (STRICT r=${R}) — cross OFF/ON 각 10셀"
  for S in $CELLS; do
    ( NUF_RADIUS_STRICT=1 NUF_RADIUS="$R" CROSS_OFF=1 SEG13=1 WARMUP_NC_STEPS=20 \
      "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
      --controllers "$CTRL" --output "outputs/_${TAG}_off/$S" \
      > "outputs/_logs/${TAG}_off_$S.log" 2>&1 ) &
    ( NUF_RADIUS_STRICT=1 NUF_RADIUS="$R" CROSS_ON=1 SEG13=1 WARMUP_NC_STEPS=20 \
      "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
      --controllers "$CTRL" --output "outputs/_${TAG}_on/$S" \
      > "outputs/_logs/${TAG}_on_$S.log" 2>&1 ) &
  done
  wait
  say "${TAG} 완료"
}

wave 1500 "r1500"
wave 1200 "r1200"
say "=== 반경 A/B 큐 종료: 40런 완료 ==="
