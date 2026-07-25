#!/usr/bin/env bash
# Round 3 재설계 — Mod1 URBAN_CLF(gated) 공정 목적함수 수정 (2026-07-25)
# depth 불변(공정). CLF는 far gate 동조 → Low/Med/Skew(gate닫힘) base와 비트동일 보존,
# Inc/High(gate열림)만 old far_urban(n²)을 볼록 CLF+기울기외삽으로 교체 → 과-metering 벌점.
# far 가중 1.0/1.0(기본)로 CLF 효과만 격리. 성공기준: PFO 5셀 전부 이김.
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
# G = gated CLF, far 가중 기본, 기본 CLF 파라미터(n_ref450/ncrit550/njam1540/pmax640/gmin60/ttail0.5)
CLF_ENV=(URBAN_CLF=1)

run_one() {  # $1=combo $2=cell $3...=extra env
  local combo="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/redesign_${combo}_${cell}"
  mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" "${CLF_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 &
}
# G = gated CLF, 5셀 전부(Low/Med/Skew 비트동일 확인 + Inc/High 효과)
for cell in 155 170 170skew 170inc 190; do run_one G "$cell"; done
wait
echo "===== REDESIGN R3 DONE ====="
for cell in 155 170 170skew 170inc 190; do
  out="outputs/_diag/redesign_G_${cell}"
  echo "  G ${cell} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null) err=$(grep -icE 'error|traceback' "$out.log" 2>/dev/null) fargate=$(grep -c 'FAR_GATE' "$out.log" 2>/dev/null)"
done
