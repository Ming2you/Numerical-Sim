#!/usr/bin/env bash
# Round 7 — spillback + control-move penalty (whipsaw 억제) (2026-07-25)
# 진단: Inc 포화 원인=metering 진동(|Δ|~600 vs 오라클 300). move penalty로 평활.
# 기반=spillback(wu2, wf0, nref800). MOVE_W ∈ {0.5,1,2}. Inc/High + Med 보존.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([170]=sweet_170_w [170inc]=sweet_170_incident_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
  SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
  MOVE=1)
run_one() { local combo="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/move_${combo}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# MOVE_W sweep
for cell in 170inc 190; do run_one m05 "$cell" MOVE_W=0.5; done
for cell in 170inc 190 170; do run_one m10 "$cell" MOVE_W=1.0; done
run_one m20 170inc MOVE_W=2.0
wait
echo "===== MOVE R7 DONE ====="
for c in m05_170inc m05_190 m10_170inc m10_190 m10_170 m20_170inc; do
  out="outputs/_diag/move_${c}"
  echo "  ${c} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done
