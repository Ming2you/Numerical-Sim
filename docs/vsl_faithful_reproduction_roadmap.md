# Wu VSL 충실 재현 로드맵 (2026-06-15)

## 0. 목적

4-controller 비교(WU-CD-F / PROPOSED-FOLLOWERS-ONLY / PROPOSED-STACKELBERG / PROPOSED-CENTRALIZED)에서
**Wu et al.(2022) 벤치마크의 VSL이 정당하게 작동**하도록 plant·controller·시나리오를 충실하게 갖춘 뒤,
풀 매트릭스를 재실행한다. 본 문서는 지금까지의 조사 결과와 남은 작업(=Option A″)을 정리한다.

---

## 1. 핵심 발견 — Wu 원문에서 VSL은 작동한다 (메커니즘 확정)

원문(IEEE TCST 30(1), 2022) case study(scenario 2)를 직접 읽고 확인:

- off-ramp 큐가 쌓이면 freeway **VSL이 활성화**(v_min=30까지 하강).
- VSL이 **freeway→urban 유입(off-ramp 방출)을 제한** → **urban 혼잡 완화** → off-ramp 드레인 →
  capacity-drop λ_eff(식22) 회복 → freeway+urban 혼잡 완화.
- urban 신호(off-ramp phase green↑)와 **협조적**, **Np=10 horizon의 multi-step** 효과.
- 결과: 협조분산(CD)이 비협조(NCD) 대비 TTS −26.5%.

즉 VSL의 역할은 "off-ramp 큐 발생 시 본선 metering으로 전체 TTT를 줄이는 것"이며, 이는
**urban 혼잡의 주원인이 off-ramp transfer flow일 때** 성립한다(VSL이 그 유입을 끊어 urban을 푼다).

Wu의 capacity drop = off-ramp 차량수 트리거(식22, 차로수 감소), 밀도-트리거 아님 — 우리와 동일 구조.
Wu 제약 (26): `0 ≤ ρ ≤ ρ_max`(밀도 jam 한계).

---

## 2. 완료된 plant correctness 수정 (전부 spec/Wu 충실, 커밋됨)

조사 과정에서 발견·수정한 3대 plant 결함. 모두 혼잡 시나리오 물리 신뢰도를 올린다.

1. **Wu 식3 off-ramp 배출 게이트** — off-ramp storage 배출을 하류 receiving 공간에 제약
   (`min(green·sat, downstream receiving)`). 하류 정체 시 off-ramp 큐 backup → 식22 발동.
2. **S_eff(링크 유효 가용공간)** — movement 점큐 x[o,s,d]를 origin 링크 점유로 반영
   (spec §3.3 397행). 이전엔 점큐가 어느 링크에도 안 잡혀 backup이 상류로 전파 안 됨.
   (+ `_origin_storage_movements` 캐시 stale 버그 수정.)
3. **freeway CTM receiving/supply 제약** — 세그먼트 간 흐름 `min(sending, downstream supply)`,
   진입 못한 차량은 `mainline_origin_queue`에 보관(보존). 밀도가 rho_max(180)에서 묶임
   (이전 ρ=339 무한상승 해소). Wu 제약(26) 정합. **커밋 b1540f3.**

검증: 차량보존 항등식 residual≈0, 밀도 176≤180, 113 단위테스트 통과.

---

## 3. 진단 — 왜 아직 VSL이 우리 모델에서 안 작동하나

전체 컨트롤러(VSL+신호)로 spillback 시나리오를 돌려도 WU-CD-F의 VSL이 **0/10 interval 활성**:

- **λ-recovery 채널이 닫힘**: spillback이 생기려면 off-ramp 하류 urban이 포화돼야 하는데,
  포화되면 off-ramp drain이 near-zero → VSL로 유입을 줄여도 storage가 horizon 내 회복 불가.
- **우리 urban이 Wu regime을 못 만듦**: (a) urban을 자기 수요로 포화시키면 off-ramp를 끊어도
  안 풀림(drain-blocked). (b) off-ramp 홍수만으로 포화시키려 하면 **boundary_out 자유 sink +
  넉넉한 grid green**이 홍수를 다 빼내서 포화 안 됨(occ<15%).
- 즉 Wu의 회복 채널("urban 혼잡 주원인=off-ramp 홍수 → VSL이 끊어 urban relief")이 성립하려면
  **urban 네트워크가 유한 용량**이어야 한다. 현 idealized 자유-sink 그리드는 그 regime을 못 만든다.

(참고: HEAD의 메커니즘 B(`p_down` 인위적 결합 페널티)는 VSL을 억지로 내리던 항으로, 충실 재현에선
제거 대상이다. 현재는 test_c가 그것에 의존하므로 A″에서 메커니즘 교체와 함께 제거한다.)

---

## 4. 남은 작업 — Option A″ (urban 유한 출구용량 + Wu VSL 활성화)

순서대로. 각 단계는 **코딩 서브에이전트 → 리뷰 서브에이전트 → 메인 3자 대조(spec·코드·리뷰)**.

### A″-1. urban 유한 출구용량 (boundary_out)
- `boundary_out` 유출을 유한 용량으로 제약(모델 밖 하류 도로 용량) — 현재 자유 sink(시간지연만)에서
  유한 용량 게이트로. 그래야 off-ramp transfer flow가 urban을 포화시키고, VSL이 끊으면 urban이 풀린다.
- 차량보존 유지(못 나간 차량은 출구 movement 큐/링크에 보관). Wu의 유한용량 실제망에 충실.
- (부수: `grid_link_storage_veh` override가 자동유도 내부 링크에 미반영되는 버그도 같이 점검.)

### A″-2. 메커니즘 B 제거
- `wu_distributed.py`의 `p_down`/`downstream_coupling_*` 인위적 결합 제거. VSL 활성화는 순수 TTS
  예측(λ 회복)에서만 나오게.

### A″-3. WU freeway agent 예측에 λ-recovery coupling
- `_solve_freeway_agent` probe가 horizon(Np≈10)에 걸쳐 "VSL↓ → off-ramp 유입↓ → urban drain으로
  storage 배출 → λ_eff 회복 → freeway TTS↓"를 정확히 예측하게. urban drain은 coupling 변수로.
- plant 불변(예측만 정확히 모사). 후보수·S_max로 비용 관리.

### A″-4. 시나리오
- off-ramp transfer flow가 (유한용량) urban을 포화시키는 시나리오 + transient surge(Wu scenario 2 류).
- 고freeway·고off-ramp split·중간 urban으로 "urban 혼잡 주원인=off-ramp 홍수" regime 구성.

### A″-5. n_crit 재calibration + 회귀
- plant 변경(A″-1) 반영해 n_crit 재산출, config·테스트 갱신. 전체 단위테스트 통과.

### A″-6. 게이트(payoff)
- **G1**: spillback 시나리오에서 VSL이 max 미만으로 활성화되는 interval 존재.
- **G2**: VSL 활성 vs VSL 무력(max 고정) **total TTT 비교 — VSL 활성이 total을 줄임**(Wu CD vs NCD 정신).
- 둘 다 통과해야 "Wu VSL 충실 재현" 인정. test_c도 자연 spillback 기반으로 갱신.

### A″-7. 4-controller 풀 매트릭스 재실행
- 수정된 plant 위에서 no-control + WU-CD-F + P-FO + P-STACK + P-CENT, 5 시나리오 ×s42 + peak s123/s7.
- 집계(bootstrap CI·winner)·최종 리포트 전면 갱신.

---

## 5. 작업 원칙

- 매 단계 **단계 게이트**(보존·payoff). 막히면 중단·정직 보고(억지 통과 금지).
- plant 차량보존식 불변(게이팅/예측만 수정). 인위적 항(메커니즘 B) 재도입 금지.
- 코딩/리뷰 서브에이전트 분리 + 메인 3자 대조. 단계별 커밋, push는 검토 후.
- dummy 스크립트·결과는 즉시 정리(누적 금지).
