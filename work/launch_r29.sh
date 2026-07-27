#!/usr/bin/env bash
# R29 — (A) 가격 켠 채 가격이 배분(LINK_SHARE=price) : "가격을 끌 필요가 없는가" 정면 검증
#       (B) 현재 최고(가격off+spillback WF.25+BUDGET_FAIR, +0.57) 미세 마감
# 조건: 감독자 없음 · 예산 켬 (사용자 요구)
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
  SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5)
run() { local tag="$1"; shift
  local out="outputs/_diag/r29_${tag}_190"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u BUDGET_OFF \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario sweet_190_w --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# (A) 가격 ON + 가격기반 배분 (VSL만 off — VSL은 별개로 High에 해로웠음)
run onprice_b200  VSL_PRICE=0 LINK_SHARE=price BUDGET_FAIR=1 SPILLBACK_WF=0.25
run onprice_b50   VSL_PRICE=0 LINK_SHARE=price LINK_SHARE_BETA=50 BUDGET_FAIR=1 SPILLBACK_WF=0.25
run onprice_b1000 VSL_PRICE=0 LINK_SHARE=price LINK_SHARE_BETA=1000 BUDGET_FAIR=1 SPILLBACK_WF=0.25
run onprice_pf16  VSL_PRICE=0 LINK_SHARE=price BUDGET_FAIR=1 SPILLBACK_WF=0.25 PREFILTER_TOPK=16 PREFILTER_LOCAL_TOPK=16
# (B) 현재 최고 미세 마감 (가격 off + BUDGET_FAIR, WF 미세)
OFFP=(METER_PRICE=0 VSL_PRICE=0 BUDGET_FAIR=1)
run bf_wf020 "${OFFP[@]}" SPILLBACK_WF=0.20
run bf_wf022 "${OFFP[@]}" SPILLBACK_WF=0.22
run bf_wf028 "${OFFP[@]}" SPILLBACK_WF=0.28
run bf_wf030 "${OFFP[@]}" SPILLBACK_WF=0.30
run bf_nref600 "${OFFP[@]}" SPILLBACK_WF=0.25 SPILLBACK_NREF_U=600
run bf_lead075 "${OFFP[@]}" SPILLBACK_WF=0.25 SPILLBACK_LEAD=0.75
wait
echo "===== R29 DONE ====="
