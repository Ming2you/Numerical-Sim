#!/bin/bash
# 기준선 5종 런(2026-07-17 밤, 논문 §1~2용): NC/WU-CD-F/PFO × 6셀 → P-CENT × 6셀.
# 6셀 = 논문 5셀 + 190/200 양쪽 확보(고수요 셀 선택 미확정이라 둘 다).
# ★PFO에 SEG13 절대 금지(주면 5배 악화). 기준선 env는 WARMUP_NC_STEPS만.
# 검증: PFO 완료 후 §0.4 기준선(155_w=1776 등)과 재현 대조 필요.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
LOG="outputs/_logs/baseline5.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }
CELLS="sweet_155_w sweet_170_w sweet_170_skew15_w sweet_170_incident_w sweet_190_w sweet_200_w"
say "=== 배치 1: NC + WU-CD-F + PFO x 6셀 (18런) ==="
for S in $CELLS; do
  ( WARMUP_NC_STEPS=20 "$PY" work/run_claude_style_five_controller.py --scenario "$S" \
    --T-total 10800 --controllers NO-CONTROL --output "outputs/_paper_nc/$S" \
    > "outputs/_logs/pnc_$S.log" 2>&1 ) &
  ( WARMUP_NC_STEPS=20 "$PY" work/run_claude_style_five_controller.py --scenario "$S" \
    --T-total 10800 --controllers WU-CD-F --output "outputs/_paper_wucdf/$S" \
    > "outputs/_logs/pwucdf_$S.log" 2>&1 ) &
  ( WARMUP_NC_STEPS=20 "$PY" work/run_claude_style_five_controller.py --scenario "$S" \
    --T-total 10800 --controllers WU-FAITHFUL-FOLLOWER --output "outputs/_paper_pfo/$S" \
    > "outputs/_logs/ppfo_$S.log" 2>&1 ) &
done
wait
say "=== 배치 1 완료 — 배치 2: P-CENT x 6셀 ==="
for S in $CELLS; do
  ( WARMUP_NC_STEPS=20 "$PY" work/run_claude_style_five_controller.py --scenario "$S" \
    --T-total 10800 --controllers P-CENT --output "outputs/_paper_pcent/$S" \
    > "outputs/_logs/ppcent_$S.log" 2>&1 ) &
done
wait
say "=== 기준선 5종 전체 완료 ==="
