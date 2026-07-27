#!/usr/bin/env bash
# R45 — PFO@H6 보완(Low/Skew): 동일 lookahead 비교표 완성
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
FF=WU-FAITHFUL-FOLLOWER
declare -A SC=([155]=sweet_155_w [170skew]=sweet_170_skew15_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1)
for cell in 155 170skew; do
  out="outputs/_diag/fh_pfo_H6_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u SPILLBACK \
    "${BASE_ENV[@]}" HORIZON=6 \
    "$PY" -u work/run_claude_style_five_controller.py --scenario "${SC[$cell]}" --T-total 14400 \
      --controllers "$FF" --output "$out" > "$out.log" 2>&1 &
done
wait
echo "===== R45 PFO@H6 DONE ====="
