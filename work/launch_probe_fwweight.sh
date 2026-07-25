#!/usr/bin/env bash
# Probe — freeway far 하향가중 가설 독립 실측 (2026-07-25, 워크플로우 병렬 ground truth)
# 진단: PS4가 freeway 과보호. far_fw 가중을 낮추면 리더가 freeway 혼잡을 수용 → urban 보호할까?
# base far(old, CLF 아님) + MFD_FAR_W_FREEWAY만 변경. Inc/High. depth 불변(공정).
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([170inc]=sweet_170_incident_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2)
run_one() { local combo="$1"; local cell="$2"; shift 2
  local out="outputs/_diag/probe_${combo}_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE "${BASE_ENV[@]}" "$@" \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 & }
# FW03 = far_fw 가중 0.3 | FW00 = far_fw 완전 off(극단, pure urban 보호)
for cell in 170inc 190; do run_one FW03 "$cell" MFD_FAR_W_FREEWAY=0.3; done
for cell in 170inc 190; do run_one FW00 "$cell" MFD_FAR_W_FREEWAY=0.0; done
wait
echo "===== PROBE FW-WEIGHT DONE ====="
for combo in FW03 FW00; do for cell in 170inc 190; do
  out="outputs/_diag/probe_${combo}_${cell}"
  echo "  ${combo} ${cell} rows=$(wc -l < "$out/$PS/run_log.csv" 2>/dev/null)"
done; done
