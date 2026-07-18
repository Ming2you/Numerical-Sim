#!/bin/bash
# 터미널 자유출구 경계 수정(2026-07-18) 후 논문 매트릭스 재실행: 4컨트롤러 x 5셀 -> _paper2_*
# 레시피는 구 논문런(baseline_queue.sh, pfo_box_queue.sh, box_walk_vg_queue.sh)과 동일, 출력만 _paper2_.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CELLS="sweet_155_w sweet_170_w sweet_170_skew15_w sweet_170_incident_w sweet_190_w"
mkdir -p outputs/_logs

for S in $CELLS; do
  ( WARMUP_NC_STEPS=20 "$PY" work/run_claude_style_five_controller.py --scenario "$S" \
    --T-total 10800 --controllers WU-CD-F --output "outputs/_paper2_wucdf/$S" \
    > "outputs/_logs/p2_wucdf_$S.log" 2>&1 ) &
  ( BASELINE_BOX=1 WARMUP_NC_STEPS=20 "$PY" work/run_claude_style_five_controller.py --scenario "$S" \
    --T-total 10800 --controllers WU-FAITHFUL-FOLLOWER --output "outputs/_paper2_pfo_box/$S" \
    > "outputs/_logs/p2_pfobox_$S.log" 2>&1 ) &
  ( WARMUP_NC_STEPS=20 "$PY" work/run_claude_style_five_controller.py --scenario "$S" \
    --T-total 10800 --controllers P-CENT --output "outputs/_paper2_pcent/$S" \
    > "outputs/_logs/p2_pcent_$S.log" 2>&1 ) &
  ( BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 \
    CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" \
    --T-total 10800 --controllers P-STACK-WU-FAITHFUL-ALLPRICE-JOINT \
    --output "outputs/_paper2_walkmvg/$S" > "outputs/_logs/p2_walkmvg_$S.log" 2>&1 ) &
done
wait
echo "PAPER2 MATRIX DONE"
