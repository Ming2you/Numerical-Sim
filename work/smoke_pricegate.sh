#!/usr/bin/env bash
# 가격 채널 토글 훅 검증 — 켜고 끌 때 0이 되어야 할 진단으로 확인(훅 불발 방지)
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
COMMON=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=2)
run() { local tag="$1"; shift
  mkdir -p "outputs/_diag/smoke_${tag}"
  env -u SEG13 "${COMMON[@]}" "$@" "$PY" -u work/run_claude_style_five_controller.py \
    --scenario sweet_170_incident_w --T-total 5400 --controllers "$PS" \
    --output "outputs/_diag/smoke_${tag}" > "outputs/_diag/smoke_${tag}.log" 2>&1 & }
run pgbase
run pgmeteroff METER_PRICE=0
run pgvsloff VSL_PRICE=0
run pgmw2 METER_PRICE_W=2.0
wait
echo "SMOKE DONE"
