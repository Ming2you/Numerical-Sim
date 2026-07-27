#!/usr/bin/env bash
# R33 — High: "살아있는 노브" 탐색 (2026-07-27)
# R31/R28에서 WU·nref·lead·GREEN_TRUST·PREFILTER 전부 bit-identical(+0.57 정체).
# 이전에 실제로 결과를 바꾼 노브만 재투입: SPILLBACK_WF(0.10→+21/0.25→+2/0.50→+129 = live),
#   far 가중(MFD_FAR_W_*), FAR_GATE 모드, NASH_SMAX, BIAS_POW/NP_BIAS.
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
  SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_WF=0.25 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5)
run() { local tag="$1"; shift
  local out="outputs/_diag/L_${tag}_190"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u BUDGET_OFF \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario sweet_190_w --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# WF 미세(live 확인된 축)
run wf023 SPILLBACK_WF=0.23
run wf024 SPILLBACK_WF=0.24
run wf026 SPILLBACK_WF=0.26
run wf027 SPILLBACK_WF=0.27
# far 가중(이전에 live)
run faru05 MFD_FAR_W_URBAN=0.5
run faru20 MFD_FAR_W_URBAN=2.0
run farf05 MFD_FAR_W_FREEWAY=0.5
# 게이트/솔버 노브
run fg2    FAR_GATE=2
run smax20 NASH_SMAX=20
run bias02 BIAS_POW=0.2
run npb0   NP_BIAS=0
run md095  MERGE_DELTA=0.95
wait
echo "===== R33 LIVE-KNOB DONE ====="
