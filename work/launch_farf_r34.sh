#!/usr/bin/env bash
# R34 — High: MFD_FAR_W_FREEWAY 축 스윕 (R33서 유일하게 live: 1.0→+0.57, 0.5→+0.51)
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
  local out="outputs/_diag/F_${tag}_190"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u BUDGET_OFF \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario sweet_190_w --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
run f000 MFD_FAR_W_FREEWAY=0.0
run f010 MFD_FAR_W_FREEWAY=0.1
run f025 MFD_FAR_W_FREEWAY=0.25
run f040 MFD_FAR_W_FREEWAY=0.4
run f060 MFD_FAR_W_FREEWAY=0.6
run f075 MFD_FAR_W_FREEWAY=0.75
# 조합: farf 낮춤 + spillback WF 미세 (freeway 축 두 개 동시)
run f025wf020 MFD_FAR_W_FREEWAY=0.25 SPILLBACK_WF=0.20
run f025wf030 MFD_FAR_W_FREEWAY=0.25 SPILLBACK_WF=0.30
run f050wf020 MFD_FAR_W_FREEWAY=0.5  SPILLBACK_WF=0.20
run f050wf030 MFD_FAR_W_FREEWAY=0.5  SPILLBACK_WF=0.30
# urban 가중 상향(1.5/3.0) — 0.5는 나빴으므로 반대방향
run u15 MFD_FAR_W_URBAN=1.5 MFD_FAR_W_FREEWAY=0.5
run u30 MFD_FAR_W_URBAN=3.0 MFD_FAR_W_FREEWAY=0.5
wait
echo "===== R34 FARF DONE ====="
