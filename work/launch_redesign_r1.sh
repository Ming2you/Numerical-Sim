#!/usr/bin/env bash
# Round 1a 재설계 — env 콤보 A/B/C × 5셀 (2026-07-24, 자율 재설계, 코드 변경 없이)
# A=앵커조임, B=A+green감쇠, C=B+far재조정. base=P-Stack(4). PFO 5셀 이기는지 검증.
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

extra_for() {  # echoes the combo-specific env
  case "$1" in
    A) echo "PFO_ANCHOR=1 PFO_ANCHOR_NUF=400 PFO_ANCHOR_NP=400" ;;
    B) echo "PFO_ANCHOR=1 PFO_ANCHOR_NUF=400 PFO_ANCHOR_NP=400 GREEN_TRUST_SEC=3" ;;
    C) echo "PFO_ANCHOR=1 PFO_ANCHOR_NUF=400 PFO_ANCHOR_NP=400 GREEN_TRUST_SEC=3 FAR_NCRIT=400 MFD_FAR_W_URBAN=0.75 MFD_FAR_W_FREEWAY=0.25" ;;
  esac
}
run_one() {  # $1=combo $2=cell
  local combo="$1" cell="$2"
  local out="outputs/_diag/redesign_${combo}_${cell}"
  mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" $(extra_for "$combo") \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 &
}
for combo in A B C; do for cell in 155 170 170skew 170inc 190; do run_one "$combo" "$cell"; done; done
wait
echo "===== REDESIGN R1 (A/B/C × 5) DONE ====="
for combo in A B C; do for cell in 155 170 170skew 170inc 190; do
  out="outputs/_diag/redesign_${combo}_${cell}"
  echo "  ${combo} ${cell} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done; done
