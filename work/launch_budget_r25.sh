#!/usr/bin/env bash
# R25 — 예산: "제거(BUDGET_OFF)" vs "잘 배분(BUDGET_FAIR)" 직접 대결 (2026-07-26, 사용자 제안)
# 근거: state.py:402 주석 — 후보 격자를 np-major로 자르면 N_P 축이 굶는다
#   (실측 고유 N_P 4 / N_UF 19, 하한 앵커 2개가 38/49 독식). 즉 예산이 무력해 보인 건
#   '수량 채널이 쓸모없어서'가 아니라 **후보 표본이 편향돼서**일 수 있다.
# 코덱스는 BUDGET_OFF=1(예산 삭제)로 Inc -198/High -152를 얻었으나, 그러면 리더가
#   순수 가격신호기가 되어 논문의 계층적 예산+가격 구조가 사라진다.
# 대안: BUDGET_FAIR=1(축별 균등 표본)로 배분을 고쳐 같은 이득을 얻을 수 있는가?
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([170]=sweet_170_w [170skew]=sweet_170_skew15_w \
               [170inc]=sweet_170_incident_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
  SPILLBACK=1 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
  AUTH_ADAPT=1 SUP_PFO=1 AUTH_DEM_HIGH=23900 AUTH_HIGH_WF=0.25 AUTH_TRUST_BIG=6.0 AUTH_DEM_LOW=0)
run() { local tag="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/bg_${tag}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_GATE "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
for cell in 170inc 190 170skew; do
  run bfair "$cell" BUDGET_FAIR=1          # 잘 배분(축별 균등 표본)
  run boff  "$cell" BUDGET_OFF=1           # 제거(코덱스 방식)
done
# 배분 강화 조합(반경 구속까지)
run bfairstrict 170inc BUDGET_FAIR=1 NUF_RADIUS_STRICT=1
run bfairstrict 190    BUDGET_FAIR=1 NUF_RADIUS_STRICT=1
wait
echo "===== R25 BUDGET DONE ====="
