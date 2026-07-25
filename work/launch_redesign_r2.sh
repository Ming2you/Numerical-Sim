#!/usr/bin/env bash
# Round 2 재설계 — D=far재조정만(5셀), E=far+지평확대(inc/high) (2026-07-25)
# 앵커·green 제외(R1서 무효/역효과). far로 incident, 지평(LEADER_V_DEPTH)으로 High 시도.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([155]=sweet_155_w [170]=sweet_170_w [170skew]=sweet_170_skew15_w \
               [170inc]=sweet_170_incident_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2)
FAR_RESHAPE=(FAR_NCRIT=400 MFD_FAR_W_URBAN=0.75 MFD_FAR_W_FREEWAY=0.25)

run_one() {  # $1=combo $2=cell $3...=extra env
  local combo="$1" cell="$2"; shift 2
  local out="outputs/_diag/redesign_${combo}_${cell}"
  mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" "${FAR_RESHAPE[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 &
}
# D = far-only, 5셀
for cell in 155 170 170skew 170inc 190; do run_one D "$cell"; done
# E = far + 지평확대, incident/high만 (느림)
for cell in 170inc 190; do run_one E "$cell" LEADER_V_DEPTH=6; done
wait
echo "===== REDESIGN R2 DONE ====="
for spec in "D 155" "D 170" "D 170skew" "D 170inc" "D 190" "E 170inc" "E 190"; do
  set -- $spec; out="outputs/_diag/redesign_${1}_${2}"
  echo "  ${1} ${2} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done
