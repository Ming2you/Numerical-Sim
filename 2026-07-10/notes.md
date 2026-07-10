# 2026-07-10 작업노트 — 계산비용 저감 A/B 패키지

## 목표

p-stack(APJOINT 플래그십)의 per-step 계산비용 저감. 사용자 최종 목적은 n=13 절대시간이
아니라 **player 수 n에 대한 확장성 주장**(더 큰 네트워크 적용 가능성)의 실증 근거 확보.

## 구현 (커밋 6e65991)

### A 패키지 — leader 후보 평가 비용

- **A1 N_UF dedupe** (`candidate_dedupe_enabled`, env `LEADER_DEDUPE=1`).
  근거: step 내 follower 반응은 N_UF에만 의존(λ_P warm-start 고정, N_P는 dual 경유만).
  → 같은 N_UF 후보는 follower solve+rollout 공유. `_evaluate_full_candidate` 오버라이드,
  key = round(N_UF*, 6), abort(inf) 결과는 캐시 제외. N_P 의존 진단만
  `_clone_nash_for_candidate`로 패치(wu_faithful_lambda_next, np target,
  urban_net_inflow_target). 스모크에서 step0 히트 3회 확인.
- **A2 early-stop** (env `EARLY_STOP=1` → `cfg.mpc.leader_rollout_early_stop`).
  partial TTT > running best → inf 반환. exact pruning(argmin 불변) — 기존 코드에
  이미 있던 기능, env 훅만 추가.
- A3(병렬화)는 구현 제외 — 논문에서 "trivially parallel" 분석 논거로만.

### B 패키지 — 가격 refresh 비용 (`price_lite`, env `PRICE_LITE=1`)

`_compute_prices_lite`: 공용 baseline J0 1회 + lever당 one-sided FD 1회(2n→n+1)
+ cross 스텐실 J0/단독점 재사용(쌍당 4점→신규 1~2점) + rollout depth H+1
(legacy는 H+D=H+3; 배분 신호는 국소·단기라는 근거).

- **실측: refresh당 rollout 62회 → 30회(−52%), rollout당 깊이 6→4스텝 → rollout·seconds 약 −68%.**
- lite 미지원(플래그십에 무관): B4 barrier 항, B3 metering release cert.

### 계측

- `_price_rollout_count` → 진단 `wu_price_rollout_count` (legacy 경로에도 부착).

## 검증

- 회귀 29/29 + 신규 lite 키셋 테스트(`test_price_lite_hands_down_same_key_sets`) 통과.
- 스모크(sweet_190 d3, A+B on, 3 steps): solve 51.8/36.0/30.6s, dedupe 히트 3/0/1,
  rollout 30/refresh, 가격 전부 유한, 키셋 g/go/vm = 5/3/4 (legacy 동일).

## 진행 중 — 3점 비교런 (순차 단독, 타이밍 순도)

sweet_190, T=7200, APJOINT 디폴트(SPLIT-v2 d3, link-share density), 앵커 TTT 11893.

| run | env | 판정 기준 |
|---|---|---|
| base | (없음) | TTT ≈ 11893 재현 + 단독 mean_solve 기준선 |
| A-only | LEADER_DEDUPE=1 EARLY_STOP=1 | TTT 변화 ±300 이내(노이즈 밴드), solve 감소 |
| A+B | + PRICE_LITE=1 | 동상 + rollout 카운트 62→30 확인 |

출력: `outputs/_compute_ab/{base,a_only,a_plus_b}`. 성능 무손실 + 비용 감소 확인 시
디폴트 채택 여부 결정.

## 확장성 논거 (논문 scalability 절 예약)

- 현 가격 refresh = lever 수 O(n) × 전역 rollout O(n) = **O(n²)/refresh**.
  B는 상수배(×0.32)만 저감 — 점근 차수는 불변.
- O(n) 경로(설계 수준, 미구현): ① adjoint(역방향 1패스로 전 lever gradient),
  ② localized rollout(유한 파동속도 → 영향반경 유계). 리뷰어 방어 텍스트 초안 있음.
- A1은 후보 격자 중복도에 비례한 저감, A2는 exact pruning — 둘 다 argmin 보존이라
  성능 중립이 이론 보장(수치 확인은 3점런).

## TODO

- [ ] 3점런 결과표 → 성능 무손실 판정 → 디폴트 채택 결정
- [ ] 채택 시 runner 디폴트 반영 + push
- [ ] 이후: APJOINT 교차검증(sweet_155/128) → 풀매트릭스 → 집필(§3.4.2 SPLIT-v2 반영)
# 2026-07-10 작업 노트 (별도 세션)

## 1. 4-컨트롤러 × 7-시나리오 최종 지표
- `2026-07-10/results/final4_7scenario_metrics.csv` — NC/PFO/P-Stack(=APJOINT v2)/Centralized(=legacy),
  TTT·completed·terminal·ATT(min/veh)·compute(s/step). P-Stack: 190에서 ATT 27.6→21.4분(vs PFO),
  completed +2483. 유일 약점 170_incident(PFO와 동률, Centralized만 −661 회수).
- Centralized 122/155/155_inc/190 행은 구트리 실행분 caveat.

## 2. P-Stack 경량화 최종 판정 (APJOINT v2, sweet_190, baseline 11458 @ 81.7s/step)
| 구성 | TTT | Δ | s/step |
|---|---:|---:|---:|
| **OPT1+2** | **11459** | **+1(무손실)** | **59.2(−28%)** |
| OPT1+2+3 | 11767 | +309 | 50.3 |
| SPSA(k=4) | 13691 | +2233 | 71.3 |
| SPSA+OPT123 | 12760 | +1302 | 45.0 |
- **OPT12 채택 → APJOINT 기본값 승격**(runner, OPT12=0으로 해제). OPT3는 G1DF선 중립이나
  APJOINT선 유해(컨트롤러 의존). **SPSA 기각**: k=4 gradient 노이즈가 price 오염(+2233), 절감도
  −13%뿐(refresh가 event-trigger로 이미 상각). 논문 라인: "가격층 O(n)화는 SPSA/adjoint로 원리적
  가능, n=7에선 exact FD가 우월 — 대규모 n의 점근 옵션"으로 복잡도 주장과 실전 구성 분리.
- 복잡도 정리: legacy O(n²)(joint grid×plant), P-Stack 수량층 O(K·d·n)=O(n), 가격층 유한차분
  O(n²)/refresh(상각)→SPSA/adjoint 시 O(n). early-termination은 legacy엔 원래 있음 — P-Stack은
  비용이 follower nash(후보당 ~5s)에 지배돼 rollout 절단 효과 미미(OPT2 ±0, exact 입증).

# 3점런 최종 판정 (A/B 패키지, sweet_190, 순차 체인 완료 13:xx)

| run | 구성 | TTT | Δ vs base | mean_solve |
|---|---|---:|---:|---:|
| base | 디폴트(구 runner) | 11457.798 | — | 76.9s |
| a_only | A1 dedupe + A2 early-stop | 11415.698 | **−42 (무손실)** | 72.9s |
| a_plus_b | **OPT12 기본 ON** + A + B price-lite | 13070.923 | **+1613 (기각)** | 44.0s |

- **판정: A1(N_UF dedupe) 검증 — 단독 무손실(−42는 warm-start 순서 드리프트, ±300 밴드 내),
  절감 ~5%(테스트 스위트 동시실행 오염 감안 시 소폭 상회 추정). B(price-lite) 기각** —
  OPT12(+1)·A(−42)로는 +1613을 설명 못 하므로 손상은 B(또는 B×OPT1 상호작용) 귀속.
  얕은(H+1)·one-sided 가격 추정이 price를 오염 — SPSA 기각(+2233)과 동일 패턴,
  "가격층은 exact FD가 답, 근사는 n=7에서 손해" 결론 재확인. 필요 시 OPT12=0 A+B 런으로
  상호작용 분리 가능하나 채택 경로가 없어 보류.
- **A1 디폴트 승격 보류**: OPT1(skip refinement)×A1 결합 미측정 — 무측정 결합 금지 교훈
  (FIXED_ALL·E1 전례). 필요 시 OPT12+A1 1런으로 확정. 현행 디폴트 = OPT12(병렬 세션 승격).
- a_plus_b는 runner 교체(69443b9, 12:43)가 시작 전에 디스크 반영돼 OPT12 기본 ON으로 돎 —
  오염이 아니라 "풀스택" 측정으로 재해석(타임라인 검증은 context-notes 참조).
- 앵커 이동(11893→11458)은 병렬 세션과 교차 확인된 사실 — 7/9 표준구성 커밋(8c9f3b2/2f08e3b)
  유력, 논문 수치 확정 전 커밋 귀속 1런 권장.

# 13-player 재구축 진행 (feature/segment-agents-13p, worktree 격리)

- 1단계 완료(34db7de): segment_local_plant.py(비트 일치 보장 설계) + R_F merge 2→3 +
  기하·stale 테스트 정리, 관련 스위트 138/138. 상세는 plan-13player-rebuild.md·checklist.md.
- 발견: build_agent_specs(distributed_coordinator.py)가 이미 13-agent 파티션 구현 —
  새 기하에서 R_D→F_W2/R_F→F_W3 자동 배정 확인(2단계 골격).
- 물리 발견(테스트로 고정): receiving-bound 레짐에서 자기 램프 방류가 본선 유입을 1:1
  변위 → 자기 seg 밀도 불변, metering 이득은 상류 agent로 가는 cross-agent externality.
  예산 equality + g_ext 가격의 존재 이유가 보존식 수준에서 입증됨(논문 재료).
