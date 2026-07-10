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

## 3점런 재해석 (병렬 세션 69443b9 OPT12 기본화와의 교차)
- 타임라인: base 시작 ~11:11 → base 종료 12:11:41(=a_only 시작, 구 runner import) →
  OPT12 기본화 편집 12:43:37 → 커밋 69443b9 12:44:06 → a_plus_b는 새 runner로 시작 예정.
- **base = 깨끗**(병렬 세션 독립 baseline 11458과 0.2 이내 일치), **a_only = 깨끗**(의도대로
  A-only), **a_plus_b = OPT12 기본 ON + A + B "풀스택"으로 재해석**(오염이 아니라 미래
  디폴트 구성의 측정으로 활용; A+B 단독 효과 필요 시 OPT12=0 런 1회 추가).
- 최종 비교틀: base 11458 / OPT12 11459@59.2(병렬, 솔로) / a_only(A단독) / a_plus_b(풀스택).
  주의: a_only 구간에 이 세션 테스트 스위트(~19분)가 겹쳐 solve 타이밍 소폭 오염 —
  TTT는 결정론이라 무영향, 타이밍은 ±10% 밴드로 해석.
- 병렬 세션 판정 수용: OPT2(early-stop)=내 A2와 동일 기제(±0 exact 입증), OPT3·SPSA 기각.
  내 체인의 신규 정보 = **A1(dedupe)·B(price-lite)** 효과.

## 미해결 — base 앵커 드리프트 (체인 종료 후 귀속)
- 3점런 base(코드 6e65991) = **11457.798, mean_solve 76.9s** vs 직전 측정(bjjl23hli, 코드
  ~948e331 추정) 11891.667/86.6s vs 공식 앵커 11893. −435 TTT + −11% solve.
- 배제 완료: SPSA(55dce56)는 price_spsa_enabled=False 게이트 확인, A/B(6e65991)는
  legacy 경로 diff 검사(depth_override=None 중립, refresh_count 증가는 lite 분기 안).
- 남은 용의: 948e331~55dce56 사이 커밋들(2f08e3b equality 복귀 등) 또는 직전 측정의
  env/코드 상태 불확실. **3점 비교 자체는 내부 일관(세 런 동일 코드) — A/B 판정 유효.**
  앵커 귀속은 체인 종료 후 짧은 bisect 런 1~2회로.

## 기타
- 55dce56(SPSA 가격층, PRICE_SPSA gated)은 병렬 세션 커밋 — 기본 off라 3점런 무영향.
  leader 측 가격층이라 13-player 이식과도 직교.
