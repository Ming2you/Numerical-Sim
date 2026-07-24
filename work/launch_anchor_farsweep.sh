#!/usr/bin/env bash
# PFO anchor + global refresh OFF + box-walk ON, far weight {0,0.25,0.5,1.0} × 5셀 = 20런 (2026-07-24)
# 사용자 설계. 10+10 배치: batch1={0,0.25}, batch2={0.5,1.0}. 각 배치 5셀×2가중 = 10런 병렬.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([155]=sweet_155_w [170]=sweet_170_w [170skew]=sweet_170_skew15_w \
               [170inc]=sweet_170_incident_w [190]=sweet_190_w)
declare -A WT=([0]=0.0 [025]=0.25 [05]=0.5 [1]=1.0)

BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 LINK_BOX_WALK=1 PFO_ANCHOR=1 GLOBAL_REFRESH_SEC=1000000000
  PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2)

run_one() {  # $1=cell $2=wtag
  local cell="$1" wt="$2"
  local out="outputs/_diag/anchor_fw${wt}_${cell}"
  mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" MFD_FAR_W="${WT[$wt]}" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 &
}
run_batch() {  # $@=wtags
  for wt in "$@"; do for cell in 155 170 170skew 170inc 190; do run_one "$cell" "$wt"; done; done
  wait
}

echo "===== BATCH1 {0, 0.25} 시작 ====="
run_batch 0 025
echo "===== BATCH1 DONE, BATCH2 {0.5, 1.0} 시작 ====="
run_batch 05 1
echo "===== ANCHOR FARSWEEP 20RUN DONE ====="
for wt in 0 025 05 1; do for cell in 155 170 170skew 170inc 190; do
  out="outputs/_diag/anchor_fw${wt}_${cell}"
  echo "  fw${wt} ${cell} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done; done
