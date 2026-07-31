#!/bin/bash
# 단일 셀 실험 러너 — 플래그십 env 고정 + 실험별 env를 인자로 덧붙인다.
#   usage: run_job.sh <out-subpath> <cell> [KEY=VAL ...]
#   예) run_job.sh _adapt/t10h5w0.013_170skew 170skew MS_ADAPT=1 MS_THR=10 MS_HOLD=5 MS_W=0.013
#       run_job.sh _budgetoff/170            170     BUDGET_OFF=1
#       run_job.sh _ms/w0.013_170            170     METER_SMOOTH=0.013
set -u
[ $# -ge 2 ] || { echo "usage: $0 <out-subpath> <cell> [KEY=VAL ...]" >&2; exit 2; }
OUTSUB=$1; CELL=$2; shift 2
cd "$(dirname "$0")/.." || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT

case "$CELL" in
  155)     SC=sweet_155_w60 ;;
  170)     SC=sweet_170_w60 ;;
  170skew) SC=sweet_170_skew15_w60 ;;
  170inc)  SC=sweet_170_incident_w60 ;;
  190)     SC=sweet_190_w60 ;;
  *) echo "unknown cell: $CELL" >&2; exit 1 ;;
esac

# 플래그십 plant + 컨트롤러 env (2026-07-27 확정)
export WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 TAU_H=0.0056111 \
       NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 PYTHONIOENCODING=utf-8 \
       BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=15 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 CROSS_OFF=1 \
       FAR_STATE_AWARE=1 SEG13=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 SUP_PFO=1 SUP_GATE=fargate \
       BIAS_SAMPLE=1 BIAS_POW=0.4 NASH_SMAX=10
[ $# -gt 0 ] && export "$@"   # 실험별 override

OUT="outputs/$OUTSUB"
mkdir -p "$OUT"
"$PY" -u work/run_claude_style_five_controller.py --scenario "$SC" --T-total 14400 \
      --controllers "$CTRL" --output "$OUT" > "$OUT.log" 2>&1
RC=$?   # ★ python 종료코드를 먼저 잡는다(과거 러너는 $(date) 뒤에 읽어 date의 코드를 보고했다)
ROWS=$(wc -l < "$OUT/$CTRL/run_log.csv" 2>/dev/null || echo 0)
echo "[$(date +%H:%M)] done $OUTSUB rc=$RC rows=$ROWS"
exit $RC
