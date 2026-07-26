#!/usr/bin/env bash
# R16 — High(+21) 마무리 + 조합 검증 (2026-07-26)
# R15: Inc gt15+spillback = 5450(-47 WIN, 최초). High both+spillback = 5990(+21).
#   spillback은 가격채널과 직교·가산(-91씩). High 분해: bothsb fw2662/ur3328 vs PFO fw2622/ur3348
#   → urban은 이미 PFO보다 좋고 freeway가 +40 나쁨. freeway 쪽을 조금 회복하면 역전.
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
SB=(SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5)
run() { local tag="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/pr_${tag}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u SPILLBACK "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# High: freeway 회복 시도 6종
run mtoffsb    190 METER_PRICE=0 "${SB[@]}"
run bothsbwf   190 METER_PRICE=0 VSL_PRICE=0 SPILLBACK=1 SPILLBACK_WF=0.25 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
run bothsbwu4  190 METER_PRICE=0 VSL_PRICE=0 SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=4 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
run bothsbsup  190 METER_PRICE=0 VSL_PRICE=0 SUP_PFO=1 "${SB[@]}"
run bothsbld1  190 METER_PRICE=0 VSL_PRICE=0 SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=2 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=1.0
run bothsbn500 190 METER_PRICE=0 VSL_PRICE=0 SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=2 SPILLBACK_NREF_U=500 SPILLBACK_LEAD=0.5
# 조합 검증: Low는 gt15+sb, Inc는 더 밀기, Skew/Med는 sb 단독(중립 확인)
run gt15sb     155    GREEN_TRUST_SEC=1.5 "${SB[@]}"
run gt15sbwu4  170inc GREEN_TRUST_SEC=1.5 SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=4 SPILLBACK_NREF_U=800 SPILLBACK_LEAD=0.5
run sb         170skew "${SB[@]}"
run sb         170    "${SB[@]}"
wait
echo "===== R16 DONE ====="
