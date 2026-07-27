#!/usr/bin/env bash
# R48 — 3v3 조건 재튜닝 1차: Low(+25.4)·Skew(+12.0) 뒤집기
# 기존 파라미터는 전부 depth-6 기준 최적값이므로 3스텝 기준으로 다시 훑는다.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([155]=sweet_155_w [170skew]=sweet_170_skew15_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
  LEADER_V_DEPTH=0 FAR_D0=1
  SPILLBACK=1 SPILLBACK_LEAD=0.5)
run() { local tag="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/T3_${tag}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u AUTH_SMOOTH \
    -u BUDGET_OFF -u METER_PRICE -u VSL_PRICE -u OFFSET_PRICE \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py --scenario "${SC[$cell]}" --T-total 14400 \
      --controllers "$PS" --output "$out" > "$out.log" 2>&1 & }
for cell in 155 170skew; do
  run sbw2   "$cell" SPILLBACK_WU=2 SPILLBACK_WF=1.0 SPILLBACK_NREF_U=800   # 현재값(대조)
  run sbw1   "$cell" SPILLBACK_WU=1 SPILLBACK_WF=1.0 SPILLBACK_NREF_U=800
  run sbw4   "$cell" SPILLBACK_WU=4 SPILLBACK_WF=1.0 SPILLBACK_NREF_U=800
  run sbwf05 "$cell" SPILLBACK_WU=2 SPILLBACK_WF=0.5 SPILLBACK_NREF_U=800
  run sbn400 "$cell" SPILLBACK_WU=2 SPILLBACK_WF=1.0 SPILLBACK_NREF_U=400
  run offp   "$cell" SPILLBACK_WU=2 SPILLBACK_WF=1.0 SPILLBACK_NREF_U=800 METER_PRICE=0 VSL_PRICE=0 OFFSET_PRICE=0
done
wait
echo "===== R48 DONE ====="
