#!/usr/bin/env bash
# Round 11 — nref_u calibration (승자 운영점 조준) (2026-07-25)
# ★발견: Inc 승패는 urban 축적(uAcc)을 400대로 묶느냐로 갈림.
#   승자 PFO 428→408→408→427→220 (bndQ 55~159) / camp 428→418→408→457→386 (bndQ 68~247)
#   패자 base 421→433→567→921→886 (bndQ→691) / spill(nref800) 423→434→474→728→860 (bndQ→840)
# 내 spillback은 nref_u=800이라 800 미만이 공짜 → 벌점이 너무 늦게 걸림.
# → nref_u를 400/500/600으로 낮춰 승자 운영점 조준. 감독자 없음(camp도 Inc 위임 0%였음).
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
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
  SPILLBACK=1 SPILLBACK_WF=0 SPILLBACK_WU=2 SPILLBACK_LEAD=0.5)
run_one() { local combo="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/nref_${combo}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# nref_u sweep on Inc(타깃) + High. 우선 400/500/600 × Inc, 400/500 × High
for cell in 170inc; do
  run_one n400 "$cell" SPILLBACK_NREF_U=400
  run_one n500 "$cell" SPILLBACK_NREF_U=500
  run_one n600 "$cell" SPILLBACK_NREF_U=600
done
for cell in 190; do
  run_one n400 "$cell" SPILLBACK_NREF_U=400
  run_one n500 "$cell" SPILLBACK_NREF_U=500
done
wait
echo "===== NREF R11 DONE ====="
for c in n400_170inc n500_170inc n600_170inc n400_190 n500_190; do
  out="outputs/_diag/nref_${c}"
  echo "  ${c} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null)"
done
