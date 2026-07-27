#!/bin/bash
# NUF_PROJ A/B 러너 (2026-07-24)
set -u
MODE=$1; CELL=$2
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
case "$CELL" in
  155) SC=sweet_155_w60;; 170) SC=sweet_170_w60;; 170skew) SC=sweet_170_skew15_w60;;
  170inc) SC=sweet_170_incident_w60;; 190) SC=sweet_190_w60;; *) exit 1;;
esac
export WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111 \
       NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 PYTHONIOENCODING=utf-8 \
       BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=15 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 CROSS_OFF=1 \
       FAR_STATE_AWARE=1 SEG13=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 SUP_PFO=1 SUP_GATE=fargate \
       BIAS_SAMPLE=1 BIAS_POW=0.4 NASH_SMAX=10
[ "$MODE" = "on" ] && export NUF_PROJ=1
OUT="outputs/_nufproj/${MODE}_${CELL}"; mkdir -p "$OUT"
"$PY" -u work/run_claude_style_five_controller.py --scenario "$SC" --T-total 14400 \
      --controllers P-STACK-WU-FAITHFUL-ALLPRICE-JOINT --output "$OUT" > "$OUT.log" 2>&1
echo "[$(date +%H:%M)] done ${MODE}_${CELL} rc=$? rows=$(wc -l < "$OUT/P-STACK-WU-FAITHFUL-ALLPRICE-JOINT/run_log.csv" 2>/dev/null || echo 0)"
