#!/usr/bin/env bash
# Round 6 — urban-only spillback w_u calibration (2026-07-25)
# R5서 A(urban-only)가 High +161→+32·Inc +328→+257 개선 확인. w_u 키워 밀어본다.
# B(대칭)는 freeway 과보호 심화로 기각 → freeway 항 안씀(base가 이미 freeway 과대평가).
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
  SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5)
run_one() { local combo="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/spill_${combo}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# w_u sweep on 타깃(Inc/High) + Med 보존확인(최강 wu4에서)
for cell in 170inc 190; do run_one wu2 "$cell" SPILLBACK_WU=2; done
for cell in 170inc 190; do run_one wu3 "$cell" SPILLBACK_WU=3; done
for cell in 170inc 190; do run_one wu4 "$cell" SPILLBACK_WU=4; done
run_one wu4 170 SPILLBACK_WU=4
wait
echo "===== SPILLBACK R6 DONE ====="
for c in wu2_170inc wu2_190 wu3_170inc wu3_190 wu4_170inc wu4_190 wu4_170; do
  out="outputs/_diag/spill_${c}"
  echo "  ${c} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done
