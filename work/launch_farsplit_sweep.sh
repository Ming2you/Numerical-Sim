#!/usr/bin/env bash
# 실험 #2: TTT + freeway_far + urban_far 분리가중 sweep (2026-07-24, 사용자 설계)
# off-diagonal 6쌍 (freeway_w, urban_w) × 5셀 = 30런. 대각선(=global MFD_FAR_W)은 기존 런.
# base=pstack4(FAR_GATE=3). 15+15 배치.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([155]=sweet_155_w [170]=sweet_170_w [170skew]=sweet_170_skew15_w \
               [170inc]=sweet_170_incident_w [190]=sweet_190_w)
declare -A WV=([025]=0.25 [05]=0.5 [075]=0.75)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1)

run_pair_cell() {  # $1=wf $2=wu $3=cell
  local wf="$1" wu="$2" cell="$3"
  local out="outputs/_diag/farsplit_f${wf}u${wu}_${cell}"
  mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" \
    MFD_FAR_W_FREEWAY="${WV[$wf]}" MFD_FAR_W_URBAN="${WV[$wu]}" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 &
}
run_batch() {  # $@ = "wf:wu" pairs
  for pair in "$@"; do
    local wf="${pair%%:*}" wu="${pair##*:}"
    for cell in 155 170 170skew 170inc 190; do run_pair_cell "$wf" "$wu" "$cell"; done
  done
  wait
}
echo "===== BATCH1 (3 pairs × 5) ====="
run_batch 025:05 025:075 05:025
echo "===== BATCH1 DONE, BATCH2 (3 pairs × 5) ====="
run_batch 05:075 075:025 075:05
echo "===== FARSPLIT SWEEP 30RUN DONE ====="
for pair in 025:05 025:075 05:025 05:075 075:025 075:05; do
  wf="${pair%%:*}"; wu="${pair##*:}"
  for cell in 155 170 170skew 170inc 190; do
    out="outputs/_diag/farsplit_f${wf}u${wu}_${cell}"
    echo "  f${wf}u${wu} ${cell} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
  done
done
