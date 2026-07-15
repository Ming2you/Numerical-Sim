# 최종 분석 계획 (2026-07-15 작성 — 실행은 price 분석 완료 후)

논문 마무리 분석 설계서. **아직 실행 아님** — 진행 중인 cross(vmtest/gotest)·부하적응 α
판정이 끝나 최종 구성이 동결된 뒤 이 계획대로 실행한다.

## 0. 전제 — 최종 구성 동결 (선행 조건)
- 동결 구성: FH3 · hinge OFF · regret k=3 · β̂ 계기 · 회랑(부하적응 α, c_lo0.7/c_hi1.0)
  · 플래그십 metering δ300/trust0.20.
- 선결 판정(진행 중):
  - 부하적응 α A/B — 경부하 회복 + 고부하 무회귀 확인 후 채택 여부.
  - cross 무대(vmtest_rampclose, gotest_skewrev) — §3 프레임 확정.
- 채점 규약: NC 웜업 20스텝(WARMUP_NC_STEPS=20), 분석창 [3600,10800] wTTT, T=10800.

## 1. 대상 4시나리오 (강도 넓게 벌림)
| 라벨 | 시나리오 | 축 |
|---|---|---|
| 중수요 | sweet_170_w | 강도 하단 |
| 고수요 | sweet_200_w | 강도 상단 |
| skew | sweet_170_skew_w | 공간 gradient |
| incident | sweet_170_incident_w (본선 seg6 폐색) | 문턱/capacity-drop |

컨트롤러 4종: NC / WU-CD-F(문헌 Wu, green+VSL) / PFO-link(국소 full-rollout+metering) / P-Stack(계층).

---

## §1. 거시 지표 (macro)
- **표**: 4시나리오 × 4컨트롤러 — wTTT, NC대비 개선%, 완주/잔존 대수, ATT(완주기준),
  mean/max step compute(s), 실시간(ci 180s) 대비 비율.
- **P-CENT 열**: 중앙집중 상한 병기(계층 vs 중앙 우위% + 계산 배율 ~1/13).
- 핵심 메시지: 계층 = 실시간 경계 내 + 중앙 상회 + 권한/조정 격차 분리.
- 산출: work/windowed_ttt.py + summary.csv 집계 스크립트.

## §2. 메커니즘 (어떻게 개선하나)
컨트롤러별 "무엇을 해서 이득이 나는가"를 event/시계열로 분해.
- **NC vs 제어**: 방류량 시계열(gridlock 붕괴 3.4k vs 관리 9.5k veh/h), 본선 밀도 궤적
  (임계 초과 여부), capacity-drop 이력.
- **WU-CD-F 무력의 원인**: metering 부재 → incident/과포화서 NC 근접(권한 격차).
- **PFO 메커니즘**: link full-rollout이 램프 차등(상류조임/하류개방)을 own-TTT서 발견.
- **P-Stack 추가분**: (a) u→f 이관(urban 큐를 freeway 여유로), (b) 임계선 운영(ρ~35 vs
  PFO ρ~30, 램프저장 완전활용), (c) 회랑+metering 가격의 링크내 배분 회복.
- 시나리오별 지배 메커니즘 지도: 중=재배분 / 고=임계선운영 / skew=공간이관 / incident=흡수보호.
- 산출: control_timeseries·state_timeseries 시계열 그림 + 이벤트 카운트.

## §3. 가격 채널의 의미 (price가 무엇을 나르나)
5채널(green / metering / vsl / green×offset cross / vsl×meter cross) 각각의
**고향 레짐**과 **의미**를 정량 제시.
- **채널별 감사표**: 소δ|값| / 대δ|값| / follower 행동 / 판정(정상·영역구속·진짜평탄).
  (이미 확보: green 강함1.9 / metering 영역구속→δ300회수 / vsl active·필터가림 /
   cross 2종 진행 중.)
- **가격의 물리적 의미**:
  - green = 신호 간 서비스 배분의 한계 외부성(상시 활성).
  - metering = 램프 유입의 문턱(breakdown) 한계비용 — δ가 문턱에 닿아야 발화(Weitzman).
  - **회랑(수량 하한) × δ(가격 반경) 짝** = 절벽에서 가격 단독은 나선, 수량이 안정화 →
    prices-vs-quantities-vs-hybrid(Roberts-Spence) 실측 3점.
  - vsl×meter cross = 램프 포화+하류 폐색서 metering·VSL 결합 필요(vmtest 판정).
  - green×offset cross = 시변 불균형서 offset 재조율 필요(gotest 판정).
- **cross 발화 안 하면**: primal joint 흡수 여부를 ablation(cross-OFF 재측정)으로 분리 —
  "가격 0 = 상호작용 없음"이 아니라 "primal이 이미 처리"일 수 있음. 정직하게 보고.
- 산출: decision_diagnostics 가격 시계열 + 대δ 프로브 + (필요시) cross-OFF ablation.

## §4. 네트워크 임계성 (어느 교차로/세그먼트가 critical한가)
**전체 21-agent 정확 Shapley는 2^21로 계산 불가 → 3층 처방.**

### 4a. Leave-one-out 임계성 (1차, O(n))
- agent i를 no-control/fixed로 고정하고 ΔwTTT 측정 = "i를 빼면 얼마나 나빠지나".
- 21 agent × 4시나리오 = 84런. Stage3 ablation 인프라(FIXED_ALL/player pin) 재사용.
- 산출: 교차로·세그먼트별 임계성 히트맵(시나리오별로 어디가 결정적인지).

### 4b. 그룹 Shapley (정확 분해, 해석 가능)
- 21개를 의미 단위 ~6그룹으로: {urban-W신호, urban-E신호, freeway-W세그, freeway-E세그,
  merge소유자(R_D/R_F), off-ramp소유자}.
- 2^6 = 64 연립 = **정확 Shapley 계산 가능**. 각 그룹의 조정 이득 기여분 φ_g.
- 산출: 서브시스템별 Shapley 기여 막대 + 시나리오 의존성.

### 4c. Coupling flux Φ (결합 방향, 이미 계산됨)
- agent 간 외부성 유량 Phi_{i→j}(예: Phi_F_to_U) — 어느 방향 결합이 지배적인가.
- 산출: 방향성 결합 그래프(u→f 주채널 정량).

### 통합 서사
"개별 임계성(4a) + 원리적 분해(4b) + 결합 방향(4c)" 3층으로 네트워크 구조의
임계 노드/링크를 정량화. 예상 결론: merge 소유 세그먼트 + 부하측 urban 신호가 critical,
u→f 방향 결합이 조정 가치의 운반체.

---

## 실행 순서 (동결 후)
1. §1·§2: 4셀 4컨트롤러 재집계(대부분 기존 런 재사용) — 반나절.
2. §3: 채널 감사표 완성 + cross 판정 반영 — cross 실험 종료 후 즉시.
3. §4: 임계성 매트릭스(4a 84런 + 4b 64런) 발주 — 하룻밤. 4c는 기존 진단서 추출.
