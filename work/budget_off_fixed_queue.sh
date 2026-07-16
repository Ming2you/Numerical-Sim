#!/bin/bash
# BUDGET_OFF 재실행(2026-07-17) — 2026-07-16 wave2가 무효였던 것을 고치고 다시.
#
# 무효 사유: BUDGET_OFF는 wu_faithful_follower.py L2886(비-SEG13 링크별 분기)만 막았는데,
#   플래그십은 SEG13=1이라 L2592의 **별도 SEG13 예산 경로**를 탄다. 거긴 게이트가 없었다.
#   증거: ③ vs _budgetoff에서 wu_seg13_budget_FW_E/W(비영 17/40)가 **완전 동일**,
#   전 컬럼 중 다른 건 computation_time_sec뿐 → 30/30 bit-identical. 20런이 ③ 재실행이었다.
# 수정: L2592에 `not _budget_off_seg13` 추가. 검증: BUDGET_OFF=1이면 wu_seg13_budget_* 키가
#   진단에서 소멸(분기 미진입), BUDGET_OFF=0이면 2647/2678로 존재.
#
# arm B(_pricesonly = BUDGET_OFF+NP_OFF)는 **뺀다** — NP_OFF가 ③에서 무효임이 두 경로로
#   확인됐다: (1) wu_faithful_lambda_P ≡ 0.0 (10셀 400스텝, 리뷰어 독립 재현),
#   (2) _pricesonly ≡ _budgetoff bit-identical 10/10. λ_P를 꺼도 바뀔 게 없다.
#   ⇒ N_P dual은 플래그십에서 inert. 남은 질문은 N_UF 예산뿐이므로 10런이면 족하다.
#
# 질문: ③의 +4.78%(vs PFO)가 **예산 몫인가 가격 몫인가**.
#   BUDGET_OFF = N_UF hard budget 제거, λ_UF·가격 전부 유지.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/budget_off_fixed.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"

say "=== BUDGET_OFF 재실행(게이트 수정 후) 10런 발주 — pd_gain 10런과 병렬(20코어) ==="
for S in $CELLS; do
  ( BUDGET_OFF=1 CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_budgetoff_fix/$S" \
    > "outputs/_logs/budgetofffix_$S.log" 2>&1 ) &
done
wait
say "=== BUDGET_OFF 재실행 종료: 10런 완료 ==="
