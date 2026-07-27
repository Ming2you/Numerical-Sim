#!/usr/bin/env bash
# R46 — 동일 lookahead(리더6 vs PFO6) 조건에서 High(+91.4) 잡기. 파라미터만.
# 기저: FIN2 구성(이산 3분기, 감독자X, 예산O, depth 기본 3). High 분기 파라미터 위주로 스윕.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
  LEADER_V_DEPTH=3 FAR_D0=1
  SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
  AUTH_ADAPT=1 AUTH_DEM_LOW=22500 AUTH_DEM_HIGH=23900 AUTH_TRUST_BIG=6.0 AUTH_TRUST_SMALL=1.5)
run() { local tag="$1"; shift
  local out="outputs/_diag/H6_${tag}_190"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u BUDGET_OFF \
    -u METER_PRICE -u VSL_PRICE -u OFFSET_PRICE -u SPILLBACK_WF -u MFD_FAR_W_FREEWAY \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py --scenario sweet_190_w --T-total 14400 \
      --controllers "$PS" --output "$out" > "$out.log" 2>&1 & }
run base
run wf012 AUTH_WF_LOADED=0.12
run wf030 AUTH_WF_LOADED=0.30
run farf03 AUTH_FARF_LOADED=0.3
run farf07 AUTH_FARF_LOADED=0.7
run wu15 SPILLBACK_WU=1.5
run wu25 SPILLBACK_WU=2.5
run nref600 SPILLBACK_NREF_U=600
run lead075 SPILLBACK_LEAD=0.75
run dem235 AUTH_DEM_HIGH=23500
wait
echo "===== R46 DONE ====="
