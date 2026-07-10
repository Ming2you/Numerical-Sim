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

# 13-player 3점 결과 (새 망 R_F merge seg3, sweet_190, OPT12 — 사용자 지시로 조기 실전 투입)

| 구성 | TTT | urban/freeway TTT | completed | 비고 |
|---|---:|---|---:|---|
| 7p 앵커(새 망) | 15717 | 13943 / 1774 | 27925 | 새 망은 구망(11458)보다 어려움 — 비교 분모 |
| 13p equality+joint | 17610 (+12%) | 15870 / 1741 | 26816 | 손실 전부 urban — 교환 배분 질 저하 |
| 13p dual(λ_UF) | 28242 (+80%) | 17042 / **11200** | 13838 | 본선 잔류 10430 — 절벽 잠금, **최종 기각** |

- dual 붕괴 메커니즘: λ 음수 국면 과방류 보조 → 본선 breakdown → capacity drop 잠금 →
  λ가 뒤늦게 조여도 비가역. 4세대 기각의 실험적 종결 + Weitzman 절벽 ablation 재료.
- 13p equality의 +1893은 urban 집중 — v0 단순화 용의 2건: ① 이웃 y hold-constant(owner의
  merge 밀도 예측 동결 → 배분 질 저하), ② vsl×meter cross ref가 link-binding 기준(own-seg
  정합 필요). 다음 수술 = 예측 궤적 교환 + cross-ref 정합 → 재측정.
- 코드: WuFaithfulFollower.segment_agents(SEG13=1), dual 배선(NUF_DUAL=1) —
  커밋 bb321be(2단계)·eed15ce(dual), 브랜치 feature/segment-agents-13p.

# PFO 사각형 (새 망, sweet_190) — 조정 가치 = 입자도의 함수 (논문 핵심 그림)

| | PFO(leader 없음) | APJOINT(leader) | leader 가치 |
|---|---:|---:|---:|
| 7p(link) | 15683 | 15717 | ≈0 (−34) |
| 13p(segment) | **29392** | 17610 | **+11782 (−40%)** |

- 7p: link own-TTS가 metering 내부화 → follower만으로 충분(leader 중립).
- 13p: merge-seg owner의 own-TTS에서 metering 유인 증발(receiving-bound 변위,
  test_segment_local_plant에 물리 고정) → follower-only 붕괴 → **leader 예산+가격이 40% 구조**.
- 결합 해석: 대규모망은 미세 분해가 강제되므로 "입자도↑ → 조정 가치↑"가 hierarchical
  control의 존재 증명. 단 7p leader≈0은 새 망·190 한정(구 망 190에선 P-Stack≫PFO —
  4×7 매트릭스), "거칠수록 가치 감소"까지만 주장.
- **NC(새 망) = 29611** — 13p PFO(29392)는 NC 대비 +0.7%로 사실상 동급.
  개선율: 13p equality +40.5%, 7p 계열 +47%.
- **[재정정 — 심야 최소정보 런으로 인과 확정]**: tie-break는 무영향이었음(내림차순
  no-ỹ 런 = 29391.505로 오름차순 구런과 비트 동일). 질식(29392)↔범람(25626)의 갈림은
  **전적으로 ỹ 교환 유무** — own-TTS가 방류에 거의 평탄(실측 1e-6 차)이라 argmin이
  정보 집합에 과민: 이웃 동결이면 질식이, ỹ면 범람이 "최적"으로 보임. 둘 다 참사.
  **정밀화된 정리: 국소 목적의 평탄성 → 운영점이 정보 의존적으로 불안정, 조정(유인
  정렬)만이 운영점을 고정.** tie-break 수정 커밋은 무해(7p 규약 정합)하나 인과 주장은
  폐기. PFO-13p 정보 사다리(4무대): 최소정보 29392/16494/18569/16693 → +ỹ
  25626/12855/14197/13540 → +nbr 15273/7358/7853/11012 → 계층 14936/7318/7416/11088.
  단차: 정보 +3.2~4.4k, **유인 +2.5~10.4k(지배적)**, 계층 +0~437(skew).
- 진행 중: seg13 v1(incumbent 가격-레벨, SEG13_V1=1) — 7p 플래핑 병리 재현 A/B.

# 13p 개선 ablation 최종 (새 망, sweet_190, 기준 = 13p equality v2 17610)

| 구성 | TTT | 판정 |
|---|---:|---|
| **13p + 궤적 교환(ỹ)** | **14938** | **7p(15717) 역전 −780** — 채택 |
| 13p + E1(far-in-price) | 17005 | −605, 7p 중립→13p 유효(입자도 반전 2호) — 채택 후보 |
| 13p v1(incumbent 가격-레벨) | 18173 | +563 — 기각(7p와 평행, v2 확정) |
| 13p dual(λ_UF) | 28242 | 기각(절벽 잠금) |
| 13p PFO | 25626~29392 | tie-break 비결정 — 조정=결정성 요건 |

- **궤적 교환이 재구축의 정당성을 성능으로 입증**: 이웃 (ρ,v,λ)+방류 스케줄 ỹ 교환
  (α=0.5, Jacobi)만으로 +1893 갭 전액 회수 + 7p 역전. "정보(ỹ)+유인(예산·가격)이
  갖춰지면 미세 분해가 거친 분해를 이긴다".
- E1 반전: 7p 중립(+47)→13p −605 — "가격에 실어야 하는 정보량 ∝ 분해 입자도"
  (VSL 가격 반전과 짝).
- 결합 판정 종결: combo(traj+E1+수정)=16464로 traj 단독 대비 +1528 역행 → 분리런
  (traj+수정, E1 제외)=**14936**(traj 단독 14938과 동일, 수정 중립) → **역행 범인=E1×traj
  이중계상**(follower가 ỹ로 보는 혼잡을 가격 tail이 재계상 → 과보수). E1 판정 3연속
  "base 의존" — 논문 재료: "가격 채널의 정보량은 follower 정보 채널과 상보적".
- **13p 플래그십 확정 = SEG13 + 궤적 교환 + tie-break 수정, E1 제외 → TTT 14936**
  (7p 15717 대비 −781/−5.0%, NC 대비 +49.6%). 다음 = 교차검증(sweet_155/128) → 풀매트릭스.

# 13p 계산비용 + 강화 PFO (심야 추가)

- **계산비용**: 13p 플래그십 mean 54.2s/max 85.5s(36분) vs 7p 60.7s/85.9s(40분) —
  **13p가 ~11% 빠름**(segment 국소 solve가 link 빔서치보다 저렴; per-agent 비용
  망 크기 무관 = follower 층 O(n)·자명 병렬 실증). 실시간 경계(180s) 여유 2배+.
- **PFO+nbr(radius-1 국소 rollout + 이웃 차량수 비용 w=1, SEG13_NBR=1) = 15273**
  (solve 5.9s) — 비결정 구간(25.6k~29.4k)에서 7p PFO(15683)·7p APJOINT(15717) 추월.
  이 시나리오의 정직한 leader 가치 = 15273→14936 = **+337(±300 경계)**.
  단 (a) PFO+nbr은 비-Wu 기준선(이웃 비용 = 부여된 조정 장치), (b) PFO엔 N_P 개념
  부재 — 190은 보호구역 무대가 약해 leader 변별 저평가 가능(구 망 190은 P-Stack≫PFO),
  (c) w=1 휴리스틱의 레짐 강건성 미보장. **판정은 교차검증(155/128/incident)으로.**
- 스펙트럼(논문 그림): Wu-충실 분산=비결정 → +이웃 공유=대부분 회수 → +계층 조정=최상단.
- **플래그십+NBR = 15492(+556 악화) — 이중계상 3호 확정.** 채널 배타성 원칙 확립(3 데이터):
  E1단독 −605(정보가 없으면 가격에 실으면 득) / E1×traj +1528 / price×NBR +556(겹치면 손).
  이론 근거 = C-4 정의(가격 = 전역 − follower 국소모델) — 국소모델 확장 시 가격 차감 기준을
  같이 줄이지 않으면 중복. **플래그십은 radius-0+가격 유지, NBR은 PFO 전용.**
- **legacy 새 망 = 23845 붕괴(urban 15758/freeway 8087)** — 천장이 아니라 바닥권.
  원인 = far 부재: N_UF 전 스텝 6000(최대) 고정 → 과잉 admission → 본선 breakdown.
  구 망(merge seg2)은 9분 창 안에 대가가 보였지만 새 망(경계 merge)은 창 밖 실현 —
  **"근시안 중앙 < 무조정 분산 < 원시야 계층" 3극 구도**(far 기계의 가치 소급 입증,
  13p 플래그십이 구 챔피언 대비 −37%로 새 망 SOTA). "11k 대비 14.9k" 우려 해소.
- 진행 중(심야 배치): 교차 매트릭스
  {NC, PFO+nbr, 13p flag} × {sweet_155, 155_incident, 155_skew} — leader 변별 무대 판정.
  PFO 기준선은 유지(빼면 baseline gaming — Wu 벤치마크 원칙의 거울상), 판정은 매트릭스로.

# 교차 매트릭스 최종 (새 망, {NC, PFO+nbr, 13p flag} × 4무대) — 하루 마감 판정

| 무대 | NC | PFO+nbr | flag | leader TTT | leader N_P초과(평균) |
|---|---:|---:|---:|---:|---|
| sweet_155 | 19844 | 7358 | 7318 | +40 | 169.7 vs 188.4 (소폭) |
| 155_incident | 20035 | **11012** | 11088 | **−76** | 199.1 vs 169.0 (열세) |
| **155_skew** | 19964 | 7853 | **7416** | **+437** | **108.0 vs 184.7 (−42%)** |
| sweet_190 | 29611 | 15273 | 14936 | +337 | — |

- incident 무변별로 "스트레스 단조" 중간 가설 철회(±300 교훈). **최종 판정: 계층의
  잔여 가치는 공간 불균형(skew) 레짐에 집중 — TTT·N_P 보호 동시 우위. 평온/용량상실
  레짐은 강화 분산과 동급.** 계층의 나머지 논거 = 비용 구조(가격 0× vs rollout (2r+1)×,
  radius는 파동속도×horizon으로 유계라 n 무관) + 근시안 중앙 붕괴 대비 강건성 + 비결정성 해소.
- 논문 결과절 뼈대(전부 오늘 실측): ①비결정성 정리 ②절벽 수량우위(dual) ③입자도 사각형
  ④채널 배타성(3증거) ⑤far 필수성(legacy 붕괴) ⑥레짐 조건부 계층 가치(skew) ⑦O(n) 비용.
- 잔여 TODO: 매트릭스에 WU-CD-F 열 추가, N_P 준수 그림(궤적), 원고 결과절 집필,
  플래그십 구성 재현런 2회(±300 방어), notes의 190 xval 표는 outputs/_13p/xval/ 참조.

# 천장 탐색 종결 — P-CENT+far도 계층에 패배 (심야 최종)

- far를 모듈 함수 승격(stackelberg_mpc.mfd_far_cost_to_go) 후 CentralizedMPC(proposed)
  채점 2경로에 이식 + runner P-CENT ID(커밋). **P-CENT+far = 20889**(completed 18813,
  mean_solve 33.0s) — legacy(23845)보다 −2956(원시야 가치 재확인)이나 플래그십(14936)에
  −5953 열세. **새 망에서 계층(14936)이 모든 중앙집중 구현을 상회 = 경험적 프런티어.**
- 논문 주장(신규): 계층 분해는 중앙의 근사가 아니라 동등 예산에서 중앙을 이김 —
  분해가 탐색 prior(follower 저차원 국소해 + leader 2-D 탐색 vs 중앙의 고차원 격자 낭비).
  단서: P-CENT는 scipy 부재로 grid fallback·구망 튜닝 — "실용 예산의 중앙 구현들 대비"로 한정.
- 병렬성 정리(원고 scalability용): PFO도 Jacobi라 agent-병렬(직렬 주장 금지). P-Stack
  증가분(후보 25-way·가격 30-way)이 전부 독립 축 → 병렬 벽시계 같은 자릿수·n-무관,
  잔여 격차 = 전역 rollout 시간축 직렬성. P-CENT는 병렬 최용이(무상태 후보)나 총연산
  O(n²)라 W∝n² 필요 — n=13은 교차점 아래. 병렬 인프라는 base에 기존재(backend flag),
  플래그십은 worker가 base follower를 재구성하는 문제로 serial 강제 — 수선 계획: worker
  payload에 follower 상태 직렬화 + wave 병렬(웨이브 간 incumbent 공유) + dedupe 사전 그룹핑.

# POLISH 붕괴 + optimizer's curse 메커니즘 (심야 2차)

- **P-CENT-POLISH = 20975 ≈ 맨 P-CENT(20889)** — "구성상 ≥플래그십" 보장은 per-step·
  proxy(9분+far) 기준까지만; 폐루프에서 grid가 매 스텝 proxy-편향 이웃으로 이탈, 누적 붕괴.
  좋은 중심을 줘도 같은 어트랙터 수렴 = grid argmin이 중심 무관하게 proxy 편향을 따름.
- **핵심 발견(분해=prior의 메커니즘)**: 같은 9분+far proxy로 d0 플래그십은 14901(정상),
  polish는 20975(붕괴) — 차이는 탐색 폭. 2-D leader 공간은 거친 proxy에 순위-강건,
  ~300 per-lever 이웃 argmin은 proxy 오차에 과적합(optimizer's curse). 동일 예산에서
  중앙은 proxy 거칠게(→curse) 또는 탐색 좁게(→커버리지 상실) 중 택일 강제.
- 잔여 카드: DEEP-POLISH(채점 18분, ~200s/step 오프라인 상한) — 회수 기대 낮아 보류 권고.
- **depth 스윕 종합(13p)**: d0+far 14901/31.8s · d1 14750/39.0s · d2 14956/44.5s ·
  d3 14936/54.2s · d4 15512(요철) · d5 14563/63.9s — d4 제외 고원. **권고: 플래그십 d1**
  (동률 중 최저비용−28%, d5 우위는 비단조 구간 단일런이라 보류). CAND81 15115 기각.
  발견: 7p d0 붕괴 vs 13p d0 동률 = **ỹ 교환이 leader 원시야(deep V) 의존 제거**.
- 진행 중: H 스윕(H1d1/H2d1/H1d0 — 7p에선 H단축 손해였으나 13p는 ỹ가 받침 가설).

# 13-player 재구축 진행 (feature/segment-agents-13p, worktree 격리)

- 1단계 완료(34db7de): segment_local_plant.py(비트 일치 보장 설계) + R_F merge 2→3 +
  기하·stale 테스트 정리, 관련 스위트 138/138. 상세는 plan-13player-rebuild.md·checklist.md.
- 발견: build_agent_specs(distributed_coordinator.py)가 이미 13-agent 파티션 구현 —
  새 기하에서 R_D→F_W2/R_F→F_W3 자동 배정 확인(2단계 골격).
- 물리 발견(테스트로 고정): receiving-bound 레짐에서 자기 램프 방류가 본선 유입을 1:1
  변위 → 자기 seg 밀도 불변, metering 이득은 상류 agent로 가는 cross-agent externality.
  예산 equality + g_ext 가격의 존재 이유가 보존식 수준에서 입증됨(논문 재료).
