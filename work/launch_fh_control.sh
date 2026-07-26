#!/usr/bin/env bash
# 대조군 — P-Stack base(spillback 없음) @ H6: "깊이가 리더에 해로운가" vs "spillback이 H6서 miscalibrated인가" 분리
# spillback의 lead_h=0.5h·nref=800은 H3 말단 기준 calibration이라 H6 말단(1080s)선 과투영 가능.
set -u
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PS=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
declare -A SC=([170]=sweet_170_w [170inc]=sweet_170_incident_w [190]=sweet_190_w)
BASE_ENV=(WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111
  NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 BOX_WALK=1 BOX_WALK_VG=1 NP_PD_ITER=4 NP_BIAS=1
  CROSS_OFF=1 FAR_STATE_AWARE=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 BIAS_SAMPLE=1
  BIAS_POW=0.4 NASH_SMAX=10 PFO_SPLIT=2 PYTHONIOENCODING=utf-8
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2)
# A: base(no spillback) @H6  |  B: spillback with lead_h scaled to horizon (0.25h) @H6
for cell in 170inc 190 170; do
  out="outputs/_diag/fh_psbase_H6_${cell}"; mkdir -p "$out"
  env -u SEG13 -u METER_BOX -u VSL_BOX -u SUP_PFO -u SUP_GATE -u SPILLBACK "${BASE_ENV[@]}" HORIZON=6 \
    "$PY" -u work/run_claude_style_five_controller.py \
      --scenario "${SC[$cell]}" --T-total 14400 --controllers "$PS" --output "$out" \
      > "$out.log" 2>&1 &
done
wait
echo "===== FH CONTROL (base@H6) DONE ====="
for cell in 170inc 190 170; do
  echo "  psbase H6 ${cell} rows=$(wc -l < "outputs/_diag/fh_psbase_H6_${cell}/$PS/run_log.csv" 2>/dev/null)"
done
