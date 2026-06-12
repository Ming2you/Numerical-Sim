# 3단계 사후분석 리포트 (풀 매트릭스)

기준: spec `docs/spec/16_six_controller_comparison.md` + `docs/literature_grounded_post_analysis_plan.md`
+ `docs/spec/11_reporting.md`. 실행 조건: **풀 7200s**, Stage 1 = 5 시나리오 ×seed 42 + peak
×seed{123,7}(7콤보 42쌍), Stage 2·3 = peak·oversaturated. demand는 deterministic이라 seed는
solver 탐색 재현성만 제어한다. 불확실성은 interval-paired ΔTTT의 bootstrap CI(2,000회)로
표현(시간 의존성 단순 재표집 근사 — 한계 명시). smoke 기준선은 git 이력(7b219b1) 참조.

## Stage 1: Six-Controller Comparison (`post_analysis/stage1/`)

### 시나리오별 Total TTT [veh·h] (seed 42)

| controller | low | medium | peak | oversat | incident |
|---|---|---|---|---|---|
| WU-CD-F | 879 | 4,989 | 11,255 | 16,061 | 10,702 |
| WU-MATCHED-STACKELBERG | 879 | 4,989 | 11,253 | 16,058 | 10,698 |
| WU-CC-F | **873** | **1,845** | 8,583 | 15,161 | 7,375 |
| PROPOSED-FOLLOWERS-ONLY | 1,010 | 5,484 | 11,157 | 16,399 | 10,611 |
| PROPOSED-STACKELBERG | 1,207 | 3,136 | 6,481 | 13,013 | 6,084 |
| PROPOSED-CENTRALIZED | 982 | 3,039 | **5,349** | **10,652** | **4,993** |

winner count(7콤보): PROPOSED-CENTRALIZED 5, WU-CC-F 2. peak seed{42,123,7} 순위 동일(robust).
authority 자동검사 42/42 런 전부 통과. delay·throughput·terminal·계산량 전체 표는
`matrix_all_controllers.csv`.

### Paired comparison (pooled, n=7; CI는 interval-paired bootstrap)

| comparison | mean ΔTTT | positive | CI(0 제외) |
|---|---|---|---|
| **ProposedLeaderValue** | **+3,354.8** | 6/7 | 7/7 |
| WuLeaderValue | +2.1 | 5/7 | 5/7 |
| WuCentralizationGap | +2,205.9 | 7/7 | 7/7 |
| ProposedCentralizationGap | +1,112.3 | 7/7 | 7/7 |
| FollowerPackageDifference | −74.7 | 4/7 | 7/7 |
| LeaderPackageDifference | +3,278.0 | 6/7 | 7/7 |

핵심 해석(주장 가능 범위, plan §18 준수):

1. **Proposed authority에서 Leader의 가치는 크고 일관적**(+3,355, 6/7 양수; 유일한 음수는
   low_demand — 자유류에서 perimeter 기계가 마찰). Wu authority에서 leader-conditioning의
   가치는 ≈0(+2.1) — green/VSL만으로는 leader가 조정할 지렛대가 없다.
2. **Regime 의존성**: low/medium에서는 WU-CC-F(green+VSL 중앙화)가 최강 — 경부하에서는
   단순 authority의 정밀 운용이 풀패키지보다 낫다. peak/oversat/incident(혼잡)에서는
   PROPOSED 그룹이 압도(P-CENT가 WU-CD 대비 −53~−58% TTT).
3. 중앙화 이득은 양 그룹 모두 7/7 양수. 단 PROPOSED-CENTRALIZED는 동일 budget 수치
   참조(보장 최적 아님)이고, Wu 분산 local 모델은 경량 근사라 WuCentralizationGap에는
   solver 충실도 차이가 섞여 있다(fidelity_matrix.md).
4. FollowerPackageDifference ≈ 0 — leader 없는 full package는 Wu 분산과 동급. **proposed
   full authority의 가치는 Leader 조정과 결합될 때만 발현된다**(LeaderPackageDifference
   +3,278과 대조).

## Stage 2: Control Mechanism Validation (`post_analysis/stage2/`)

frozen-control replay counterfactual, 6-interval outcome 창:

| control | peak: mech/dir/gain | oversat: mech/dir/gain |
|---|---|---|
| allocation/green | **1.0 / 1.0 / +14.2** | 0.0 / 1.0 / −12.3 |
| offset | 0.5 / 1.0 / +2.4 | **0.75 / 1.0 / +1.3** |
| vsl | 0.0 / 0.0 / −0.45 | 0.0 / 0.25 / −0.62 |
| metering | 0.0 / 0.25 / −0.54 | 0.0 / 0.75 / −0.97 |

- allocation/green: peak에서 메커니즘 완전 재현. oversat 단일 event는 6-interval 창에서
  중립 대비 음수 — 심혼잡 창에서는 어떤 배분도 큐 총량을 줄이지 못함(고통 보존).
- offset: 양 시나리오에서 방향 정확·양의 이득 — progression 메커니즘 재현(시스템 기여는
  별도 closed-loop ablation +346.7 veh·h로 입증).
- **vsl/metering: 6-interval frozen 창에서는 이득이 중립~소폭 음수**. 이는 메커니즘 부정이
  아니라 측정 창의 한계다 — 이들의 가치는 "수십 interval 뒤 capacity drop 예방"으로
  Stage 1(oversat에서 P-STACK이 freeway TTT 341 vs Wu류 3,600+)과 Stage 3
  (FIXED_ALL → freeway 3,632 붕괴)의 closed-loop 증거가 시스템 기여를 보여준다.
  frozen 창 평가의 단기 비용(감속/제한)만 잡히는 구조적 비대칭을 한계로 명시한다.

## Stage 3: Coupling Ablation (`post_analysis/stage3/`)

물리 결합·차량 이동 유지 + 잔여 player·leader 재최적화(테스트로 검증). J = total TTT:

| case | peak | oversat |
|---|---|---|
| FULL_COUPLING | 6,481 | 13,013 |
| NO_U_TO_F_INFO | 6,865 | 12,904 |
| NO_F_TO_U_INFO | 6,486 | 12,722 |
| NO_CROSS_NETWORK_INFO | 6,687 | 12,955 |
| LOCAL_ONLY_COUPLING_PLAYERS | 6,687 | 12,955 |
| FIXED_URBAN_COUPLING_PLAYERS | 7,183 | 13,088 |
| FIXED_FREEWAY_COUPLING_PLAYERS | 6,819 | 12,914 |
| FIXED_ALL_COUPLING_PLAYERS | 7,970 | **17,087** |

| metric | peak | oversat |
|---|---|---|
| Value_U_to_F | **+383.9** | −109.5 |
| Value_F_to_U | +4.4 | −291.6 |
| BidirectionalSynergy | −182.1 | +342.8 |
| Phi_U_to_F | +292.9 | +61.9 |
| Phi_F_to_U | −86.7 | −120.2 |
| UrbanCouplingPlayerValue | +702.2 | +74.5 |
| FreewayCouplingPlayerValue | +338.3 | −99.6 |
| AllCouplingPlayersValue | **+1,489.1** | **+4,073.1** |

해석(부호·불확실성 함께, plan §17/§18):

1. **u→f 채널(접근 방출·x_on 예측)이 주 정보 채널**(peak +383.9, Phi 기준 양 시나리오
   +292.9/+61.9). f→u 예측 압력은 Phi 기준 양 시나리오 음수 — 현 휴리스틱의 f→u 신호
   ("가짜 압력" 계열)는 오히려 해로울 수 있음(설계 개선 후보).
2. **심혼잡에서 단방향 차단값이 음수**(−109/−292) — receiving이 interval 내 붕괴하는
   조건에서 예측 정보가 오조정 유발(기존 "심과포화 추정 한계" 결론과 정합). 단 synergy는
   +342.8로, 양방향을 모두 끊으면 단방향 차단의 '이득'이 사라진다.
3. **player 한계가치의 초가산성**: 개별 고정은 완만한 손실(또는 oversat freeway −99.6의
   소폭 이득)이지만 **모두 고정하면 파국**(peak +1,489, oversat +4,073 — freeway TTT 3,632
   본선 붕괴 재현). coupling player들은 상호 대체 가능하나 최소 한 그룹의 전략적 운용이
   시스템 안정의 필요조건이다.
4. LOCAL_ONLY = NO_CROSS 정확 일치(양 시나리오) — cross-network 정보의 소비자는
   coupling player뿐이라는 구조적 사실의 재확인.

## 주장 불가/한계

- 시나리오 demand는 deterministic — seed 분산은 solver 탐색에 한정되며(peak 3 seed 순위
  동일), demand 확률성 하의 일반화는 본 데이터로 주장하지 않는다.
- Wu 분산 local 모델은 원문 MILP/SQP의 경량 근사 — WU-CD-F 절대 성능은 보수적 추정.
- vsl/metering의 frozen 창 음수는 측정 창 비대칭(단기 비용만 포착)의 영향 — closed-loop
  증거와 함께 읽어야 한다.
- centralized는 보장된 전역 최적이 아니다. cross-authority 차이를 단일 control의 순수
  효과로 해석하지 않는다.

## 산출물

```text
post_analysis/
  stage1/  <scenario>_s<seed>/(six_controller_summary, paired, runs/...) ×7
           matrix_all_controllers.csv, matrix_paired_with_ci.csv,
           matrix_paired_pooled.csv, matrix_winner_counts.csv, matrix_pooled_summary.csv
  stage2/  peak_demand/, oversaturated_demand/ (event catalog + mechanism_summary)
  stage3/  peak_demand/, oversaturated_demand/ (8케이스 runs + directional/synergy CSV)
  final_post_analysis_report.md (본 파일)
```
