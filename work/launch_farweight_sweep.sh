#!/usr/bin/env bash
# far weight sweep — MFD_FAR_W ∈ {0.25,0.5,0.75} × {incident,high} (2026-07-24)
# near/far 스케일 보정. 양끝: w=0(far-off, pstack4faroff_) / w=1(pstack4_ 기존). gate는 유지(FAR_GATE=3).
# PS4 no-sup. Med/Skew는 far-gate off라 weight 무관 → 제외.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([170inc]=sweet_170_incident_w [190]=sweet_190_w)

BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1)

run_one() {  # $1=cell $2=wtag(025|05|075) $3=wval
  local cell="$1" wt="$2" wv="$3"
  local out="outputs/_diag/pstack4fw${wt}_${cell}"
  mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" MFD_FAR_W="$wv" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 &
}
for cell in 170inc 190; do
  run_one "$cell" 025 0.25
  run_one "$cell" 05  0.5
  run_one "$cell" 075 0.75
done
wait
echo "===== FAR WEIGHT SWEEP DONE ====="
for cell in 170inc 190; do for wt in 025 05 075; do
  out="outputs/_diag/pstack4fw${wt}_${cell}"
  echo "  w${wt} ${cell} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done; done
