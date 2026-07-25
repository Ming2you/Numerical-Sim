#!/usr/bin/env bash
# Round 4 재설계 — always-on CLF (URBAN_CLF_GATED=0) + n_ref sweep (2026-07-25)
# gated가 High 후반(gate닫힌 49-75)을 못 잡을 때 대비. excess=max(0,n_u-n_ref)가 자체 urban
# 게이트라, always-on이어도 n_ref 아래 Med/Skew 정상구간은 통과(단 boundary peak는 건드림).
# depth 불변(공정). Inc/High + Med(비파괴 확인). n_ref {600,1000} 비교.
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
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2)

run_one() {  # $1=combo $2=cell $3...=extra env
  local combo="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/redesign_${combo}_${cell}"
  mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" \
    URBAN_CLF=1 URBAN_CLF_GATED=0 "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 &
}
# H6 = always-on, n_ref=600 | H10 = always-on, n_ref=1000. Med(비파괴)+Inc+High.
for cell in 170 170inc 190; do run_one H6  "$cell" URBAN_CLF_NREF=600;  done
for cell in 170 170inc 190; do run_one H10 "$cell" URBAN_CLF_NREF=1000; done
wait
echo "===== REDESIGN R4 DONE ====="
for combo in H6 H10; do for cell in 170 170inc 190; do
  out="outputs/_diag/redesign_${combo}_${cell}"
  echo "  ${combo} ${cell} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done; done
