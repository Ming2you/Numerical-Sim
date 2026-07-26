#!/usr/bin/env bash
# R15 — R14 돌파 확장 (2026-07-26)
# R14: Inc는 GREEN_TRUST_SEC=1.5가 +328→+44 (fw2673/ur2868, P-CENT 균형 방향)
#      High는 METER+VSL price off(both)가 +161→+112, gt15는 오히려 +292 악화.
# → GPT가 보고한 패턴 재현: Inc/저부하는 작은 green authority, High는 큰 authority.
# 이번: (a) Inc 마지막 44 줄이기(조합·trust 미세), (b) High 개선(큰 trust + 채널 off),
#       (c) gt15가 Low/Med/Skew 승리를 깨는지 보존 확인.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([155]=sweet_155_w [170]=sweet_170_w [170skew]=sweet_170_skew15_w \
               [170inc]=sweet_170_incident_w [190]=sweet_190_w)
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
# (a) Inc: 남은 +44 줄이기
run gt15mt   170inc GREEN_TRUST_SEC=1.5 METER_PRICE=0
run gt15both 170inc GREEN_TRUST_SEC=1.5 METER_PRICE=0 VSL_PRICE=0
run gt10     170inc GREEN_TRUST_SEC=1.0
run gt30     170inc GREEN_TRUST_SEC=3.0
run gt15sb   170inc GREEN_TRUST_SEC=1.5 SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=2 SPILLBACK_NREF_U=800
# (b) High: 큰 authority + 채널 off
run gt12both 190 GREEN_TRUST_SEC=12 METER_PRICE=0 VSL_PRICE=0
run gt12     190 GREEN_TRUST_SEC=12
run bothsb   190 METER_PRICE=0 VSL_PRICE=0 SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=2 SPILLBACK_NREF_U=800
run gt24both 190 GREEN_TRUST_SEC=24 METER_PRICE=0 VSL_PRICE=0
# (c) gt15 보존 확인
for cell in 155 170 170skew; do run gt15 "$cell" GREEN_TRUST_SEC=1.5; done
wait
echo "===== R15 DONE ====="
