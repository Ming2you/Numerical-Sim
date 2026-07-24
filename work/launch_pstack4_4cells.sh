#!/usr/bin/env bash
# P-Stack(4) 나머지 4셀(155/170/170inc/190) 병렬 실행 — leader+4-agent, b13 base env + PFO_SPLIT=2 (2026-07-24)
# skew(pstack4_170skew)와 동일 env. PFO(4)와 base env 동일, 차이는 컨트롤러(leader 유무)뿐.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"

# b13 base에서 SEG13/METER_BOX/VSL_BOX/SUP_PFO/SUP_GATE 제거 + PFO_SPLIT=2 = P-Stack(4)
export WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111 \
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1 \
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1 \
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
unset SEG13 METER_BOX VSL_BOX SUP_PFO SUP_GATE
# BLAS 스레드 제한 — 4 병렬 × 4 = 16 ≤ 20 core
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4

declare -A SC=([155]=sweet_155_w [170]=sweet_170_w [170inc]=sweet_170_incident_w [190]=sweet_190_w)
CTRL=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT

for cell in 155 170 170inc 190; do
  OUT="outputs/_diag/pstack4_$cell"; mkdir -p "$OUT"
  "$PY" -u work/run_claude_style_five_controller.py \
    --scenario "${SC[$cell]}" --T-total 14400 --controllers "$CTRL" --output "$OUT" \
    > "$OUT.log" 2>&1 &
done
wait
echo "===== PSTACK4 4CELL DONE ====="
for cell in 155 170 170inc 190; do
  OUT="outputs/_diag/pstack4_$cell"
  rows=$(wc -l < "$OUT/$CTRL/run_log.csv" 2>/dev/null)
  err=$(grep -icE 'error|traceback' "$OUT.log" 2>/dev/null)
  echo "  $cell rows=$rows err=$err"
done
