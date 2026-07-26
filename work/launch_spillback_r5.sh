#!/usr/bin/env bash
# Round 5 — 대칭 성장-투영 spillback 항 1차 calibration (2026-07-25)
# A=urban-only(w_f=0), B=대칭(w_f=1). Med(보존확인)/Inc/High. depth 불변. nref_u=800.
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
  SPILLBACK=1 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5)
run_one() { local combo="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/spill_${combo}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# A = urban-only(w_f=0) | B = 대칭(w_f=1)
for cell in 170 170inc 190; do run_one A "$cell" SPILLBACK_WU=1 SPILLBACK_WF=0; done
for cell in 170 170inc 190; do run_one B "$cell" SPILLBACK_WU=1 SPILLBACK_WF=1; done
wait
echo "===== SPILLBACK R5 DONE ====="
for combo in A B; do for cell in 170 170inc 190; do
  out="outputs/_diag/spill_${combo}_${cell}"
  echo "  ${combo} ${cell} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done; done
