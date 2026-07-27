#!/bin/bash
# _w60 재실행 러너 — 컨트롤러별 논문 env 적용, 셀 병렬 실행용 (2026-07-24)
# usage: run_w60_job.sh <tag> <cell>
set -u
TAG=$1; CELL=$2
cd /c/Users/alsrj/Desktop/Numerical-Sim-offiter || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"

case "$CELL" in
  155)     SC=sweet_155_w60 ;;
  170)     SC=sweet_170_w60 ;;
  170skew) SC=sweet_170_skew15_w60 ;;
  170inc)  SC=sweet_170_incident_w60 ;;
  190)     SC=sweet_190_w60 ;;
  *) echo "unknown cell $CELL"; exit 1 ;;
esac

# 공통 plant env (논문 job 라인과 동일)
export WARMUP_NC_STEPS=5 FW_BUFFER=8 TERM_ZG=1 VFREE=115 RHO_CRIT=31.5 \
       TAU_H=0.0056111 NU_BASE=22.5 KAPPA=10 MERGE_DELTA=0.9 PYTHONIOENCODING=utf-8

case "$TAG" in
  nc)    CTRL=NO-CONTROL ;;
  wu)    CTRL=WU-CD-F ;;
  pfo)   CTRL=WU-FAITHFUL-FOLLOWER; export BASELINE_BOX=1 ;;
  pcent) CTRL=P-CENT; export CENT_REFRESH_SEC=180 CENT_DENSE=1 FAR_REAL_V=1 ;;
  pstack|pstackoff)
    CTRL=P-STACK-WU-FAITHFUL-ALLPRICE-JOINT
    export BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=15 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
           CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 FAR_REAL_V=1 FAR_GATE=3 BASELINE_BOX=1 \
           SUP_PFO=1 SUP_GATE=fargate BIAS_SAMPLE=1 BIAS_POW=0.4 NASH_SMAX=10
    [ "$TAG" = "pstackoff" ] && export ALLPRICE_OFF=1
    # showcase(skew, price-ON)만 알고리즘검증 로깅
    if [ "$TAG" = "pstack" ] && [ "$CELL" = "170skew" ]; then
      export LEADER_GRID_SWEEP="outputs/_w60seq/${TAG}_${CELL}/grid" LEADER_GRID_STEP=17 GRID_N=9 \
             RESIDUAL_LOG="outputs/_w60seq/${TAG}_${CELL}/resid" LEADER_CAND_LOG="outputs/_w60seq/${TAG}_${CELL}/cand"
    fi ;;
  *) echo "unknown tag $TAG"; exit 1 ;;
esac

OUT="outputs/_w60seq/${TAG}_${CELL}"
mkdir -p "$OUT"
"$PY" -u work/run_claude_style_five_controller.py --scenario "$SC" --T-total 14400 \
      --controllers "$CTRL" --output "$OUT" > "$OUT.log" 2>&1
RC=$?
ROWS=$(wc -l < "$OUT/$CTRL/run_log.csv" 2>/dev/null || echo 0)
echo "[$(date +%H:%M)] done ${TAG}_${CELL} rc=$RC rows=$ROWS"
