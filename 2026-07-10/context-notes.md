# 2026-07-10 컨텍스트 노트

## 결정 1 — player 구조 이탈 발견과 옵션 3 채택
- 설계(docs/wu2022_distributed_reference.md §7) = urban 5 + freeway segment agent(현
  4-seg면 8) = 13. 구현 = link agent 2 = 7. 이탈 지점 2026-06-14 Option C(97bca51,
  "agent 분할" 대신 "결정변수 segment 벡터화", 무승인).
- 사용자 결정: 7-player 결과는 보험(main 동결 + feature/segment-agents-13p 브랜치),
  플래그십을 13-player로 재구축.
- 재발 방지: 구조 결정은 plan-13player-rebuild.md에 명시 후 승인받고 구현.

## 결정 2 — "N_UF dual이 13-player에서 살아나나?"에 대한 판단
- **아니오(metering 채널은)**: 모든 on-ramp가 seg2 merge라 ramp 소유 agent는 13-player
  에서도 link당 1개(F_L2) — 소유 토폴로지 불변. dual 4세대 기각의 병리(step 내 미집행
  → far-informed 수량 결정 증발, windup→incumbent 고착)는 시간스케일 문제라 입자도와
  무관하게 잔존. Weitzman 논리로도 metering=절벽 채널 → 수량 가드가 정답, 분해가
  가늘수록 per-agent 신호 SNR이 떨어져 수량 가드 가치가 오히려 상승.
- **예(VSL/green 가격은)**: link agent가 내부화하던 segment 간 외부성(상류 감속 →
  하류 이득)이 13-player에서 노출 → leader per-segment VSL 가격이 처음으로 load-bearing
  해질 것. 7-player에서 VSL 가격 중립이었던 이유 = 외부성이 이미 내부화돼 있었다는 가설.
- 절차: 입자도 변경(equality 유지) 먼저 → dual은 8단계 ablation. 변수 하나씩.

## 제약 — 3점런 오염 방지
- base/A-only/A+B 순차 체인이 도는 동안 src/ 수정 금지(후속 런이 시작 시점 디스크
  코드를 import). 수술은 체인 종료 후 브랜치에서.

## 기타
- 55dce56(SPSA 가격층, PRICE_SPSA gated)은 병렬 세션 커밋 — 기본 off라 3점런 무영향.
  leader 측 가격층이라 13-player 이식과도 직교.
