#!/usr/bin/env bash
# P-Stack(4) + 감독자 변형 5셀×2방식 = 10런 병렬 — 최적 flagship 탐색 (2026-07-24)
# C(sup fargate=b13 방식): SUP_PFO=1 SUP_GATE=fargate → pstack4sup_<cell>
# D(sup always=b11 방식):  SUP_PFO=1 (게이트 없음)    → pstack4supall_<cell>
# base = P-Stack(4) env(SEG13/METER_BOX/VSL_BOX 제거, PFO_SPLIT=2). 감독자 PFO 위임도 PFO_SPLIT 읽어 4-agent.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([155]=sweet_155_w [170]=sweet_170_w [170skew]=sweet_170_skew15_w \
               [170inc]=sweet_170_incident_w [190]=sweet_190_w)

# 공통 base (P-Stack(4)) + BLAS 캡 — 10 병렬 × 2 = 20 core
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2)

run_one() {  # $1=cell  $2=variant(sup|supall)
  local cell="$1" var="$2" out
  out="outputs/_diag/pstack4${var}_${cell}"; mkdir -p "$out"
  local extra=(SUP_PFO=1)
  [ "$var" = "sup" ] && extra+=(SUP_GATE=fargate)   # fargate-gated
  # (supall = SUP_GATE 미설정 = always-on)
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_GATE "${BASE_ENV[@]}" "${extra[@]}" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$CTRL" --output "$out" \
      > "$out.log" 2>&1 &
}

for cell in 155 170 170skew 170inc 190; do
  run_one "$cell" sup
  run_one "$cell" supall
done
wait
echo "===== PSTACK4 SUPERVISOR 10RUN DONE ====="
for var in sup supall; do for cell in 155 170 170skew 170inc 190; do
  out="outputs/_diag/pstack4${var}_${cell}"
  rows=$(wc -l < "$out/$CTRL/run_log.csv" 2>/dev/null)
  err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)
  echo "  ${var} ${cell} rows=$rows err=$err"
done; done
