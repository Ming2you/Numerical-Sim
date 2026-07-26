#!/usr/bin/env bash
# R14 — 가격 채널 스크린 (2026-07-26). 레버 전환: terminal cost → 가격 채널/권한.
# 근거: Inc에서 리더 N_UF가 PFO incumbent와 다른 스텝이 5/80(6%)뿐인데 +255~328 짐
#   → 손실은 예산이 아니라 **가격 채널**로 들어온다(가격 |max|: meter 1500·VSL 115·offset 1.0 전부 활성).
# 손실방향: Inc = freeway 좋고 urban 나쁨(metering 과잉 서명), High = urban 나쁨.
# spillback은 이번 스크린서 제외(직교 항 — 채널 이득을 깨끗이 귀속한 뒤 합산 검토).
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([170inc]=sweet_170_incident_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1)
run() { local tag="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/pr_${tag}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u SPILLBACK "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
for cell in 170inc 190; do
  run mtoff  "$cell" METER_PRICE=0
  run vsloff "$cell" VSL_PRICE=0
  run both   "$cell" METER_PRICE=0 VSL_PRICE=0
  run gpoff  "$cell" GREEN_PRICE=0
  run mtd60  "$cell" METER_PRICE_DELTA=60
  run gt15   "$cell" GREEN_TRUST_SEC=1.5
done
wait
echo "===== PRICE SCREEN R14 DONE ====="
