#!/usr/bin/env bash
# R31 — High 마감 파라미터 스윕 (구조변경 없음, 기존 노브만) (2026-07-27)
# 현재 최고: 가격off + spillback(WU2,WF0.25,nref800,lead0.5) + BUDGET_FAIR = +0.57 (PFO 5969.58 vs 5970.15)
# 0.6만 넘기면 5/5. 조건: 감독자 없음 · 예산 켬.
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
  local out="outputs/_diag/T_${tag}_190"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u BUDGET_OFF \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario sweet_190_w --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# spillback urban 가중 미세
run wu175  SPILLBACK_WU=1.75
run wu225  SPILLBACK_WU=2.25
# nref 미세
run nref700  SPILLBACK_NREF_U=700
run nref900  SPILLBACK_NREF_U=900
run nref1000 SPILLBACK_NREF_U=1000
# lead 미세
run lead040 SPILLBACK_LEAD=0.40
run lead060 SPILLBACK_LEAD=0.60
# green trust (가격off라도 green 가격은 살아있음)
run gt4  GREEN_TRUST_SEC=4
run gt8  GREEN_TRUST_SEC=8
run gt12 GREEN_TRUST_SEC=12
# prefilter 개방(기존 cfg 필드)
run pf8  PREFILTER_TOPK=8  PREFILTER_LOCAL_TOPK=8
run pf16 PREFILTER_TOPK=16 PREFILTER_LOCAL_TOPK=16
wait
echo "===== R31 TUNE DONE ====="
