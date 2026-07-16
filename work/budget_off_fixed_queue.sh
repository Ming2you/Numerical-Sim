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
# 질문(2026-07-17 정정): ③의 +4.78%(vs PFO)에 **N_UF hard budget 채널이 필요한가**.
#   BUDGET_OFF = N_UF hard budget 제거, marginal price(green/meter/vsl) 유지.
#   ※ 원래 "예산 몫 vs 가격 몫"이라 썼고 "λ_UF는 가격이라 유지"라고 적었으나 **공허**했다:
#     λ_UF는 ③에서 항상 0이다(leader_lambda_uf_committed 비영 0/40). nuf_dual_active가 보는
#     wu_faithful_nuf_coordination_mode 기본값이 "equality"라 dual 모드가 아니고 λ_UF는 갱신조차
#     안 된다(L3898·L2732). λ_P도 0(비영 0/40). ⇒ ③에 살아있는 dual 가격은 하나도 없고,
#     실제 조정 수단은 hard budget + marginal price(58컬럼 전부 비영) 둘뿐이다.
#     따라서 이 arm은 "가격만 남기고 hard budget을 뺀다"가 맞는 서술이다.
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
