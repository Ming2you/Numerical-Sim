#!/bin/bash
# PD 스텝게인 A/B(2026-07-17) — "190은 왜 dual 재계산에서 나빠지나"의 유일한 직접 시험.
#
# 실측 근거(서브에이전트 3인 교차확인):
#   * leader_lambda_np_committed는 λ가 아니라 boolean 플래그(stackelberg_wu_metered.py:2399).
#     기존 "λ 0.425→0.450" 판독은 커밋 duty cycle 17/40→18/40 오독이었음.
#   * 진짜 λ(wu_faithful_lambda_P)는 10셀 400스텝에서 값이 {0.0, 10.0} 둘뿐 — 중간값 0개.
#     ③은 λ≡0(dual 완전 비활성). 즉 비교는 'dual 없음 vs cap 포화 bang-bang'.
#   * 산수: gain_pd = lambda_np_step_gain(0.01) × np_pd_gain_mult(25.0) = 0.25.
#     잔차 실측 324~580 → Δλ 81~145 → cap(10) 약 12배 초과 → 한 방에 포화.
#     25배는 "표준 gain은 K≤5 내 수렴 불가"(follower L3692) 때문에 넣은 값 = 수렴을 사고 내부 dual을 죽임.
#   * 가설 (c)(위반 게이팅)는 기각·부호 반대: 190이 위반 최대(505.6)·PD 발동 최다(18/40).
#
# 시험: NP_PD_GAIN=1.0 → 유효 gain 0.01 → 잔차 500에서 Δλ=5.0 → [0,10] 내부 착지.
# 반증 대기 중인 구멍: 190의 손해가 cap 스텝에 안 몰림(λ=10 +10.15/step vs λ=0 +31.53/step)
#   → 후폭풍 효과. 게인을 낮춰도 안 고쳐질 수 있음. 그래서 '측정'이지 '수정'이 아님.
# 위험: skew 이득(170_skew15 +12.5%p, 170_skew +6.5%p)이 bang-bang λ 덕이면 같이 사라질 수 있음.
#   → 10셀 전부 돌려 손익 양쪽을 동시에 본다.
set -u
cd "C:/Users/alsrj/Desktop/Numerical-Sim-offiter" || exit 1
PY="C:/Users/alsrj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
CTRL="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
LOG="outputs/_logs/pd_gain.log"
mkdir -p outputs/_logs
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }

CELLS="sweet_155_w sweet_155_skew15_w sweet_155_skew_w sweet_155_incident_w sweet_170_w \
sweet_170_skew15_w sweet_170_skew_w sweet_170_incident_w sweet_190_w sweet_200_w"

say "=== PD 게인 A/B 시작 — wave2('가격만' 20런) 완료 대기 ==="

deadline=$(( $(date +%s) + 14400 ))   # 4시간 안전장치
while true; do
  n=0
  for D in _budgetoff _pricesonly; do
    for S in $CELLS; do
      [ -f "outputs/${D}/${S}/${CTRL}/run_log.csv" ] && n=$((n+1))
    done
  done
  say "wave2 대기: ${n}/20 완료"
  [ "$n" -ge 20 ] && { say "wave2 완료 — PD 게인 발주"; break; }
  [ "$(date +%s)" -ge "$deadline" ] && { say "4시간 초과 — ${n}/20인 채로 진행"; break; }
  sleep 180
done

say "발주: PD4 + NP_PD_GAIN=1.0, 10셀 (③ 기반: FAR_STATE_AWARE, cross OFF, SEG13)"
for S in $CELLS; do
  ( NP_PD_GAIN=1.0 NP_PD_ITER=4 NP_BIAS=1 CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20 \
    "$PY" work/run_claude_style_five_controller.py --scenario "$S" --T-total 10800 \
    --controllers "$CTRL" --output "outputs/_pd4_gain1/$S" \
    > "outputs/_logs/pd4gain1_$S.log" 2>&1 ) &
done
wait
say "=== PD 게인 A/B 종료: 10런 완료 ==="
