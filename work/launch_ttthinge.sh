#!/usr/bin/env bash
# 실험 #1: leader objective = TTT + hinge (far OFF, LEADER_HINGE=1), 5셀 (2026-07-24)
# = far-off(pstack4faroff) 구성에 leader hinge만 추가. hinge가 리더를 PFO 위로 끌어올리나 검증.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([155]=sweet_155_w [170]=sweet_170_w [170skew]=sweet_170_skew15_w \
               [170inc]=sweet_170_incident_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 MFD_FAR=0 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 LEADER_HINGE=1 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 MKL_NUM_THREADS=3 NUMEXPR_NUM_THREADS=3)
for cell in 155 170 170skew 170inc 190; do
  out="outputs/_diag/ttthinge_${cell}"; mkdir -p "$out"
  env -u FAR_GATE -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 &
done
wait
echo "===== TTT+HINGE 5CELL DONE ====="
for cell in 155 170 170skew 170inc 190; do
  out="outputs/_diag/ttthinge_${cell}"
  echo "  ${cell} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done
