#!/usr/bin/env bash
# R26 — High 돌파: 예산 "배분" 레버 (감독자 없음·예산 켠 상태) (2026-07-26, 사용자 요구)
# 조건: SUP_PFO 미사용, BUDGET_OFF 미사용. base = 가격채널off + spillback(WF=0.25) = +2.
# 배분 레버:
#   LINK_SHARE=search : N_UF 총량의 링크 간 분배를 밀도휴리스틱 대신 탐색 (핵심)
#   BUDGET_FAIR=1     : 후보 격자 축별 균등 표본(N_P 축 기아 해소, state.py:402)
#   NUF_RADIUS_STRICT : 리더 국소 반경 실제 구속
#   NP_PD_ITER=8      : N_P primal-dual 반복 증가(배분 수렴)
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
  METER_PRICE=0 VSL_PRICE=0
  SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_WF=0.25 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5)
run() { local tag="$1"; shift
  local out="outputs/_diag/al_${tag}_190"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u BUDGET_OFF \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario sweet_190_w --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
run lprice     LINK_SHARE=price
run lprice50   LINK_SHARE=price LINK_SHARE_BETA=50
run lprice500  LINK_SHARE=price LINK_SHARE_BETA=500
run lsearch    LINK_SHARE=search
run bfair      BUDGET_FAIR=1
run lpricebf   LINK_SHARE=price BUDGET_FAIR=1
run lsbf       LINK_SHARE=search BUDGET_FAIR=1
run strict     NUF_RADIUS_STRICT=1
run npit8      NP_PD_ITER=8
run lsbfstrict LINK_SHARE=search BUDGET_FAIR=1 NUF_RADIUS_STRICT=1
wait
echo "===== R26 ALLOC DONE ====="
