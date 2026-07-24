#!/bin/bash
# P-CENT SLSQP 오프라인 천장(2026-07-18 밤, 사용자 지시 "SCIPY 밤새 걸어둬").
# scipy 1.18.0 설치됨 → centralized_solver_mode=slsqp가 이제 실가동(폴백 아님).
# 실측 스텝당 ~426s → 셀당 40 결정스텝 ≈ 4.7~7h. 6셀 병렬(각 단일코어) = 동일 벽시계.
# 용도: grid 상한의 tightness 확인(오프라인 천장 — 실시간 위반이므로 본문 상한은 grid 유지).
# 판정: slsqp_success=1.0 확인 필수 — 0.0이면 그 셀 VOID.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
LOG="outputs/_logs/pcent_slsqp.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }
CELLS="sweet_155_w sweet_170_w sweet_170_skew15_w sweet_170_incident_w sweet_190_w sweet_200_w"
say "=== P-CENT SLSQP 6셀 병렬 발주 ==="
for S in $CELLS; do
  ( WARMUP_NC_STEPS=20 "$PY" work/run_claude_style_five_controller.py --scenario "$S" \
    --T-total 10800 --controllers P-CENT --output "outputs/_paper_pcent_slsqp/$S" \
    > "outputs/_logs/pslsqp_$S.log" 2>&1 ) &
done
wait
say "=== P-CENT SLSQP 완료 ==="
