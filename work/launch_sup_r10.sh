#!/usr/bin/env bash
# Round 9 — spillback + SUP_PFO 감독자 조합, 전 5셀 (2026-07-25)
# 가설: spillback이 4셀 확보 + SUP_PFO가 Inc의 PFO전략 확보. spillback이 P-Stack Med/Skew를
# 강화하면 감독자 whipsaw가 줄어들 수도. 성공기준 PFO 5셀 전부 이김. (SUP_PFO는 unset 안함)
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
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
  SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
  SUP_PFO=1)
run_one() { local cell="$1"
  local out="outputs/_diag/sup2_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_GATE "${BASE_ENV[@]}" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
for cell in 155 170 170skew 170inc 190; do run_one "$cell"; done
wait
echo "===== SUP R10 DONE ====="
for cell in 155 170 170skew 170inc 190; do
  out="outputs/_diag/sup2_${cell}"
  echo "  ${cell} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null) sup=$(grep -c 'SUP_PFO' "$out.log" 2>/dev/null)"
done
