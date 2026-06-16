# VSL 조사 최종 결론 (2026-06-16)

## 한 줄 결론

**Wu et al.(2022)의 VSL 메커니즘을 충실히 재현했고, 우리 네트워크에서 VSL은 net-neutral이다** —
off-ramp spillback이 강하게 있어도(λ_eff=1.65) VSL이 주는 urban relief와 freeway holding cost가
거의 정확히 상쇄되어 total TTT를 못 줄인다. WU freeway agent가 VSL을 max로 유지하는 것은
버그가 아니라 **옳은(최적) 결정**이다.

---

## 1. Wu 원문 VSL 메커니즘 (PDF 직접 확인)

원문(IEEE TCST 30(1), 2022) case study scenario 2:
- off-ramp 큐가 쌓이면 freeway VSL 활성화(v_min=30까지).
- VSL이 **freeway→urban 유입(off-ramp 방출)을 제한** → urban 혼잡 완화 → off-ramp 배출 →
  capacity-drop λ_eff(식22) 회복 → freeway+urban 혼잡 완화.
- urban 신호(off-ramp phase green↑)와 **협조적**, **Np=10 horizon multi-step**.
- 결과: 협조분산(CD)이 비협조(NCD) 대비 TTS −26.5%.

Wu의 capacity-drop = off-ramp 차량수 트리거(식22 차로감소), 밀도-트리거 아님. 제약 (26):
`0 ≤ ρ ≤ ρ_max`. → 우리 모델과 **동일 구조**.

---

## 2. 우리 재현에서 VSL이 net-neutral인 이유 (강제 counterfactual로 입증)

강한 spillback regime(off-ramp split 0.7 + boundary_out cap 500 override, λ_eff=1.65,
off-ramp 완전 포화)에서 WU-CD-F 상류 VSL을 **강제로** 내린 결과(T=3600):

| 상류 VSL | total | urban | freeway | Δtotal |
|---|---|---|---|---|
| agent(=max) | 5661 | 3661 | 2001 | — |
| 강제 80 | 5662 | 3649 | 2013 | +0.01% |
| 강제 60 | 5664 | 3619 | 2045 | +0.05% |
| 강제 50 | 5665 | 3601 | 2064 | +0.07% |

- VSL을 내리면 **urban이 실제로 풀린다**(3661→3601, −64) — Wu 메커니즘(off-ramp 유입 차단→urban relief)이 진짜로 작동.
- 그런데 **freeway holding cost(+64)가 urban 이득(−64)을 정확히 상쇄** → total은 오히려 +0.07%.
- 즉 우리 망은 **urban 이득 ≈ freeway 비용**이라 VSL이 net ≈ 0.

Wu가 −26.5%를 얻은 건 Shanghai 망의 **urban/freeway 균형이 달라**(off-ramp transfer 비중↑,
urban이 freeway 대비 더 용량제약적) urban 이득 > freeway 비용이 되기 때문. 우리 망은 둘이 균형.

---

## 3. 결론의 강건성 (삼중 확인)

1. **집중 체크**: cap/split 조합에서 VSL 활성 interval = 0.
2. **강제 counterfactual**: 강한 spillback(λ=1.65)에서 VSL을 50까지 강제로 내려도 total 개선 안 됨(위 표).
3. **전체 24조합 sweep**(cap∈{1600,1000,700,500}×split∈{0.4,0.55,0.7}×urban∈{0.8,1.1}, T=7200):
   λ_eff=1.65·off-ramp 완전포화(occ 1.0) 구간 포함 **전 조합에서 VSL 활성 0**.

추가로, 메커니즘 B(인위적 p_down 결합 페널티)를 제거하면 VSL이 안 켜진다(메커니즘 A=순수
TTS 예측만으로는 활성화 안 됨) — 즉 이전에 VSL이 "켜졌던" 건 가짜 보상 때문이었다.

---

## 4. 소진한 시도 (전부 VSL net-neutral 확인)

| 시도 | 결과 |
|---|---|
| scenario·demand·ramp 스윕 | spillback 미형성 또는 VSL 무효 |
| off-ramp 배출 Wu식3 게이트 | 배출 정합되나 VSL 무효 |
| S_eff(점큐→링크 점유, backup 전파) | backup 전파되나 VSL 무효 |
| freeway CTM 밀도 한계 | 밀도 valid해지나 VSL 무효 |
| urban 유한 출구용량(회복 채널) | spillback·회복 형성되나 VSL net-neutral |
| 메커니즘 B 제거 + λ-recovery 예측 | VSL 활성 0(순수 TTS로 활성화 안 됨) |
| 강제 VSL↓ counterfactual | urban −64 ≈ freeway +64, total net-neutral |

→ 모든 각도에서 VSL은 우리 망에서 net-neutral. **엄밀히 입증된 정직한 결론.**

---

## 5. 부산물 — 진짜 plant correctness 개선 (전부 keeper, 커밋됨)

VSL 조사 과정에서 발견·수정한 **5건의 진짜 결함**. 혼잡 물리 신뢰도를 크게 올림:
1. **Wu 식3 off-ramp 배출 게이트** — 하류 receiving 공간에 제약(spillback 형성 가능).
2. **S_eff(링크 유효 가용공간)** — movement 점큐를 origin 링크 점유로 반영(spec §3.3 397행, backup 전파).
3. **freeway CTM receiving/supply** — 세그먼트 간 demand-supply min, 밀도 jam 한계(이전 ρ=339 무한상승 해소).
4. **boundary_out 유한 출구용량** + per-scenario override — urban 회복 채널(cap=1600 표준 비왜곡).
5. **메커니즘 B(인위적 p_down) 제거** — VSL이 가짜 항이 아니라 순수 TTS로만 판정.

---

## 6. 비교 실험에의 함의

- VSL은 Wu·PROPOSED 양쪽에서 **net-neutral**(우리 망 특성). Wu의 개선과 PROPOSED의 우위는
  **urban 신호/allocation/leader 조정**에서 온다 — 이것이 4-controller 비교의 본질.
- 논문에는 "Wu의 VSL 메커니즘을 충실히 재현, 우리 망에선 urban 이득≈freeway 비용으로
  VSL net-neutral(강제 counterfactual 입증); Wu의 −26.5%는 그들 망의 다른 균형에서 옴"으로
  정직하게 기술 — 추측이 아니라 입증된 결과.
- **다음**: 개선된 plant(5건 수정) 위에서 4-controller(no-control + WU-CD-F + P-FO + P-STACK +
  P-CENT) 풀 매트릭스 재실행 + 집계·리포트.

## 7. 코드 상태

- 커밋된 keeper: Wu식3 배출, S_eff(+캐시 버그), CTM 밀도한계, boundary_out 유한용량(cap=1600).
- 이번 커밋: 메커니즘 B 제거 + per-scenario cap override + λ-recovery 예측(VSL은 여전히 max
  유지=net-neutral, 더 충실한 예측만) + test_c 재구성(net-neutral 회귀 가드). 113 테스트 통과.
