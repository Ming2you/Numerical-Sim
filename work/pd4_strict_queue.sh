#!/bin/bash
# PD4 + 리더 반경 STRICT(2026-07-17, 사용자 제안) — "PD4 기반으로 trust region 안에서만 움직이게"
#
# 배경: PD4의 λ가 bang-bang{0,10}이고, λ 점프 스텝에서 Σmetering이 2,217.9 움직인다
#   (평시 516.9의 4.3배 / metering 총량 ~4,959의 45%). 190·200에서 진동 +34%.
#   가설: 이동을 묶으면 PD4의 190 손해(−2.79% vs PFO)가 사라질 수 있다.
#
# ★주의 1 — 이건 절반만 묶는다. NUF_RADIUS_STRICT는 **리더 반경**만 구속한다
#   (refined_candidates의 앵커 우회 차단). metering을 2,218씩 던지는 건 **팔로워**이고,
#   팔로워엔 이동 rate limit이 **존재하지 않는다**(metering_price_trust_frac은
#   가격 FD 탐침 폭이지 이동 제약이 아님 — stackelberg_wu_metered.py:1222-1226).
#
# ★주의 2 — ③ 기반 STRICT 1500은 이미 파국이었다(평균 −19.99%, 최악 −120.42% @170_w,
#   190_w +14.87%→−76.73%). 반경을 더 조인 1200은 그보다 나쁠 개연성이 크다.
#   그래도 PD4 기반은 미검증이고 10런이면 되므로 측정한다(예측 금지 — 기록 1/22).
#
# 반경 1200 근거(사용자): 4램프 × trust_frac 0.20 × cap 1500 = 1200.
#   단 위 주의1대로 그 1200은 FD 폭이라 물리적 짝은 명목상이다.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/pd4_strict.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"

say "=== PD4 + NUF_RADIUS_STRICT(r=1200) 10런 발주 ==="
for S in $CELLS; do
  ( NUF_RADIUS_STRICT=1 NUF_RADIUS=1200 NP_PD_ITER=4 NP_BIAS=1 \
    CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_strict1200/$S" \
    > "outputs/_logs/pd4strict_$S.log" 2>&1 ) &
done
wait
say "=== PD4 + STRICT(1200) 종료: 10런 완료 ==="
