#!/usr/bin/env bash
# R22 — AUTH_ADAPT High 분기 파라미터 튜닝 (2026-07-26)
# v4: High +37(래치 urban 조건으로 +240→+37). 잔여 원인 = high 모드 진입이 step22로 늦어
#   초기 구간이 승리구성(wf025sup, 전 구간 고정)과 달라짐 → 격차가 step42부터 점진 누적.
# 조치: (a) 진입 임계를 Med/Skew 피크(23886) 바로 위로 낮춰 조기 진입, (b) WF 미세, (c) 해제 지연.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
  SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
  AUTH_ADAPT=1 SUP_PFO=1)
run() { local tag="$1"; shift
  local out="outputs/_diag/a22_${tag}_190"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_GATE "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario sweet_190_w --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# 진입 임계: Med/Skew 피크 23886 바로 위(23900) → 조기 진입, 그 아래 셀은 영향 없음
run d239wf025 AUTH_DEM_HIGH=23900 AUTH_HIGH_WF=0.25
run d239wf020 AUTH_DEM_HIGH=23900 AUTH_HIGH_WF=0.20
run d239wf030 AUTH_DEM_HIGH=23900 AUTH_HIGH_WF=0.30
run d239nu150 AUTH_DEM_HIGH=23900 AUTH_HIGH_WF=0.25 AUTH_RECOVER_NU=150
run d245wf025 AUTH_DEM_HIGH=24500 AUTH_HIGH_WF=0.25
run d239t15   AUTH_DEM_HIGH=23900 AUTH_HIGH_WF=0.25 AUTH_TRUST_BIG=6.0 AUTH_DEM_LOW=0
wait
echo "===== R22 DONE ====="
