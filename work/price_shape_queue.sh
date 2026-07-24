#!/bin/bash
# 가격 형상 A/B(2026-07-17, 사용자 제안 2종): 채택 구성(300+vsl10) 위에
#   arm C: +CROSS_ON  — cross 2종 부활. 쌍선형이라 m 내부 최적은 못 만들지만(구조),
#     기각 사유였던 외삽(±300 측정→1125 이동)이 박스로 소멸했으므로 재시험 정당.
#   arm W: +METER_PRICE_W=0.5 — price 지배 완화, own-TTS 곡률로 내부 최적 유도.
# 판별: 박스 끝 선택률(현 89~100% → 내부 선택 등장?), Σ|Δ| 진동, TTT 패널.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/price_shape.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }
CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"
say "=== 가격 형상 A/B: crossON 10 + pw0.5 10 발주 ==="
for S in $CELLS; do
  ( CROSS_ON=1 VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
    FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_bv_crosson/$S" \
    > "outputs/_logs/bvcross_$S.log" 2>&1 ) &
  ( METER_PRICE_W=0.5 CROSS_OFF=1 VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
    FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_bv_pw05/$S" \
    > "outputs/_logs/bvpw05_$S.log" 2>&1 ) &
done
wait
say "=== 가격 형상 A/B 종료: 20런 완료 ==="
