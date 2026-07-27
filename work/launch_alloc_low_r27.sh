#!/usr/bin/env bash
# R27 — Low를 trust 6에서 이기게 할 수 있나 (통합 충돌 제거용). 감독자 없음·예산 켬.
# Low는 현재 trust 1.5로만 이김(-6). trust 6에선 +5. 배분 레버로 trust 6에서도 이기면
# Low/High의 trust 충돌이 사라져 단일 규칙이 훨씬 단순해진다.
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
  local out="outputs/_diag/lo_${tag}_155"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u AUTH_ADAPT -u BUDGET_OFF \
    "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario sweet_155_w --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
run t6base                                  # trust 6 기본(비교군, 기대 +5)
run t6bfair    BUDGET_FAIR=1
run t6lprice   LINK_SHARE=price
run t6lpricebf LINK_SHARE=price BUDGET_FAIR=1
run t6lsearch  LINK_SHARE=search
run t6npit8    NP_PD_ITER=8
wait
echo "===== R27 LOW DONE ====="
