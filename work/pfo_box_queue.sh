#!/bin/bash
# PFO + BASELINE_BOX 6셀(2026-07-17 밤) — 공정비교 기준선 재생산.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
LOG="outputs/_logs/pfo_box.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }
CELLS="sweet_155_w sweet_170_w sweet_170_skew15_w sweet_170_incident_w sweet_190_w sweet_200_w"
say "=== PFO+BASELINE_BOX 6런 발주 ==="
for S in $CELLS; do
  ( BASELINE_BOX=1 WARMUP_NC_STEPS=20 "$PY" work/run_claude_style_five_controller.py \
    --scenario "$S" --T-total 10800 --controllers WU-FAITHFUL-FOLLOWER \
    --output "outputs/_paper_pfo_box/$S" > "outputs/_logs/ppfobox_$S.log" 2>&1 ) &
done
wait
say "=== PFO+BASELINE_BOX 완료 ==="
