#!/usr/bin/env bash
# R28 — 예산 배분 병목 후보: prefilter 개방 (2026-07-26)
# 실측: 리더는 후보 ~48개 중 proxy로 고른 **4.2개만** full 평가(stackelberg_prefilter_top_k=4).
#   → 예산 축(N_P/N_UF) 조합을 사실상 탐색하지 못한다. BUDGET_FAIR가 무력했던 이유이기도 함.
# 조건: 감독자 없음(SUP_PFO 미사용) · 예산 켬(BUDGET_OFF 미사용) — 사용자 요구.
# base = 가격채널off + spillback(WF=0.25) = High +2.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([155]=sweet_155_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
  SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5)
run() { local tag="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/pf_${tag}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u BUDGET_OFF \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# High: 가격채널 off + spillback WF=0.25 기반, prefilter 개방
HI=(METER_PRICE=0 VSL_PRICE=0 SPILLBACK_WF=0.25)
run pf8   190 "${HI[@]}" PREFILTER_TOPK=8  PREFILTER_LOCAL_TOPK=8
run pf16  190 "${HI[@]}" PREFILTER_TOPK=16 PREFILTER_LOCAL_TOPK=16
run pf32  190 "${HI[@]}" PREFILTER_TOPK=32 PREFILTER_LOCAL_TOPK=32
run pf16bf 190 "${HI[@]}" PREFILTER_TOPK=16 PREFILTER_LOCAL_TOPK=16 BUDGET_FAIR=1
# Low: trust 6(기본)에서 prefilter 개방으로 이길 수 있나 (통합 충돌 제거)
run pf16  155 PREFILTER_TOPK=16 PREFILTER_LOCAL_TOPK=16
run pf32  155 PREFILTER_TOPK=32 PREFILTER_LOCAL_TOPK=32
wait
echo "===== R28 PREFILTER DONE ====="
