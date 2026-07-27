#!/usr/bin/env bash
# R36 — High: 미탐색 노브 (freeway 축은 +0.17서 정체)
# 진단: 배수구간(52-54)에 N_UF가 6000(최대) 고정 → 리더가 전혀 조이지 않음. PFO는 taper.
#   리더의 탐색/정련 경로와 이동 반경을 바꾸는 노브를 투입.
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
  SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_WF=0.20 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
  MFD_FAR_W_FREEWAY=0.5)
run() { local tag="$1"; shift
  local out="outputs/_diag/K_${tag}_190"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u BUDGET_OFF \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario sweet_190_w --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# 리더 탐색/정련 경로
run opt12off OPT12=0
run priceit2 PRICE_ITER=2
run priceit3 PRICE_ITER=3
# 이동 반경(6000 고정 완화)
run rad1500 NUF_RADIUS=1500
run rad800  NUF_RADIUS=800
run radstrict NUF_RADIUS=1500 NUF_RADIUS_STRICT=1
# 나머지 가격 채널
run gpoff  GREEN_PRICE=0
run offoff OFFSET_PRICE=0
run rampoff RAMP_OFFSET=0
# hinge(이 조합선 미시험)
run hinge  LEADER_HINGE=1
run hinge05 LEADER_HINGE=1 LEADER_HINGE_W=0.5
# 링크배분 search(가격off 상태이므로 density vs 균등 차이)
run lsearch LINK_SHARE=search
wait
echo "===== R36 DONE ====="
