#!/usr/bin/env bash
# R35 — High 마무리: (MFD_FAR_W_FREEWAY × SPILLBACK_WF) 2D 격자
# R34 최고: farf0.5 × WF0.20 = +0.17 (기준 +0.57). 두 freeway 축 동시 하향이 유효.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
  METER_PRICE=0 VSL_PRICE=0 BUDGET_FAIR=1
  SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5)
run() { local tag="$1"; shift
  local out="outputs/_diag/G_${tag}_190"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u BUDGET_OFF \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario sweet_190_w --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
for f in 0.3 0.5 0.7; do
  for w in 0.12 0.15 0.18; do
    t="f${f/./}w${w/./}"
    run "$t" MFD_FAR_W_FREEWAY=$f SPILLBACK_WF=$w
  done
done
run f010w020 MFD_FAR_W_FREEWAY=0.1 SPILLBACK_WF=0.20
run f010w015 MFD_FAR_W_FREEWAY=0.1 SPILLBACK_WF=0.15
run f050w022 MFD_FAR_W_FREEWAY=0.5 SPILLBACK_WF=0.22
wait
echo "===== R35 GRID DONE ====="
