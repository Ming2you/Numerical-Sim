# 3단계 사후분석 리포트 (smoke 기준선)

기준: spec `docs/spec/16_six_controller_comparison.md` + `docs/literature_grounded_post_analysis_plan.md`
+ `docs/spec/11_reporting.md`. 코드 HEAD: Stage 1~3 구현 커밋(2026-06-12).
**본 리포트의 수치는 smoke 조건(peak_demand, T=1800s, seed 42)이다** — 풀 매트릭스
(시나리오 ×seed ×7200s)는 후속 실행 대상이며, 모든 해석은 plan §18 주장 범위를 따른다.

## Stage 1: Six-Controller Comparison (`post_analysis/stage1_smoke`)

공통 free-flow reference(시나리오·seed당 1회, β 흡수 체인 기반):
total 1080.8 / urban 890.6 / freeway 190.3 veh·h. authority 자동검사 6/6 통과.

| controller | TTT | delay | throughput[veh/h] | terminal | comp[s] | evals | conv |
|---|---|---|---|---|---|---|---|
| WU-CD-F | 792.4 | 526.2 | 8,885 | 3,070 | 0.0 | 410 | 1.0 |
| WU-MATCHED-STACKELBERG | 792.4 | 526.2 | 8,885 | 3,070 | 13.4 | 3,960 | 1.0 |
| WU-CC-F | 615.4 | 349.3 | 10,243 | 2,391 | 113.2 | 800 | 0.8 |
| PROPOSED-FOLLOWERS-ONLY | 801.9 | 535.8 | 8,790 | 3,117 | 5.3 | 550 | 1.0 |
| PROPOSED-STACKELBERG | 617.2 | 351.0 | 11,176 | 1,924 | 110.9 | 10,688 | 1.0 |
| PROPOSED-CENTRALIZED | 562.8 | 296.7 | 11,740 | 1,642 | 115.2 | 800 | 0.8 |

paired (TTT/delay/throughput/terminal 한 묶음, 16.11 규칙):

- **ProposedLeaderValue = +184.7 veh·h (+34.5%)** — throughput +2,386, terminal −1,193 동반
  → throughput 감소·terminal 전가 없는 정직한 개선.
- **WuLeaderValue = 0.0** — 이 smoke horizon에서 conditioning 미binding(단위테스트로 영향
  경로 자체는 검증됨). 고부하 풀런에서 재평가 필요. 0을 "leader 무가치"로 일반화하지 않음.
- WuCentralizationGap +177.0 / ProposedCentralizationGap +54.4 — 두 group 모두 중앙화 이득
  존재하나, 분산解 품질은 local 모델 충실도에 의존(fidelity_matrix.md). centralized는
  보장된 최적이 아닌 동일 budget 수치 참조.
- FollowerPackageDifference −9.5 — Wu 분산 vs proposed leaderless 분산은 사실상 동급
  (authority 차이의 순수 효과로 해석 금지, 16.10).
- LeaderPackageDifference +175.2 — leader 있는 상태에서 full package의 전체 차이.
- 계산량: 분산(WU-CD 0.04s/decision, FOLLOWERS-ONLY 0.5s) ≪ leader 평가 포함(11~12s/decision).

## Stage 2: Control Mechanism Validation (`post_analysis/stage2_smoke`)

Trigger→Action→Mediator→Outcome, frozen-control replay counterfactual(6-interval outcome 창):

| control | challenged | 응답지연[int] | 방향정확도 | mechanism 재현율 | 평균 outcome 이득[veh·h] |
|---|---|---|---|---|---|
| allocation/green | 2 | 0 | 1.0 | **1.0** | **+15.85** |
| offset | 1 | 0 | 1.0 | **1.0** | +0.27 |
| vsl | 2 | 0 | 0.0 | 0.0 | −0.88 |
| metering | 2 | 0 | 0.0 | 0.0 | −0.37 |

- allocation/green: 경계 불균형 trigger에서 B_in 감소+방출 증가 mediator, counterfactual 대비
  명확한 이득 — **메커니즘 재현**.
- offset: 회랑 방향성 trigger에서 정렬 action, 소폭 양의 이득 — 재현(이득 규모는 작음;
  직전 라운드 ablation +346.7 veh·h는 7200s 전체 기준).
- vsl/metering: smoke(1800s)에서는 수요 상승기 trigger에 활성화됐으나 counterfactual 대비
  이득이 중립~소폭 음수 — **본선 혼잡이 충분히 발달하지 않은 구간에서의 조기 활성화**로
  분류(ACTIVATED_BUT_INEFFECTIVE/WRONG_DIRECTION). 풀런·oversat 시나리오에서 재평가 필요.
  mediator 방향 판정은 pre/post 원시 차분이라 수요 상승 추세와 혼동될 수 있음(한계 명시).

## Stage 3: Player and Coupling-Information Ablation (`post_analysis/stage3_smoke`)

8개 case 전부 physical 결합 유지 + 잔여 player·leader 재최적화(구조적 보장, 테스트로 검증).
J = total TTT(낮을수록 좋음), FULL = 617.2:

| case | TTT | Δ vs FULL |
|---|---|---|
| NO_U_TO_F_INFO | 700.9 | +83.7 |
| NO_F_TO_U_INFO | 617.5 | +0.3 |
| NO_CROSS_NETWORK_INFO | 701.4 | +84.2 |
| LOCAL_ONLY_COUPLING_PLAYERS | 701.4 | +84.2 |
| FIXED_URBAN_COUPLING_PLAYERS | 643.7 | +26.5 |
| FIXED_FREEWAY_COUPLING_PLAYERS | 676.1 | +58.9 |
| FIXED_ALL_COUPLING_PLAYERS | 636.9 | +19.7 |

- **Value_U_to_F = +83.7 / Value_F_to_U = +0.3** — urban→freeway 예측 정보(접근 방출·x_on
  압력)가 지배적 채널. freeway→urban 예측 압력은 이 조건에서 거의 무가치.
- **BidirectionalSynergy = +0.18 ≈ 0** — 두 채널 효과는 가산적(상호 증폭 없음).
- Phi_U_to_F = 83.8 / Phi_F_to_U = 0.4 (Shapley형 순서 평균).
- LOCAL_ONLY == NO_CROSS — cross-network 정보의 소비자는 사실상 coupling player뿐.
- player 한계가치: Urban +26.5, Freeway +58.9, **All +19.7 < Freeway 단독** —
  둘 다 고정하면 손실이 합보다 작음(부분 대체/상충 가능성, plan §12의 "중복·설계 결함
  허용" 해석 대상; 풀런 반복으로 확인 필요).

## 주장 한계 (plan §18)

- 전 수치는 단일 seed·단축 horizon smoke — 통계적 불확실성(bootstrap CI, seed winner count)
  없이 일반화하지 않는다.
- Wu 분산 local solver는 원문 MILP/SQP의 경량 근사(fidelity_matrix.md) — WU-CD-F의 절대
  성능은 보수적일 수 있고, WuCentralizationGap에는 solver 품질 차이가 섞여 있다.
- vsl/metering Stage 2 음수 이득은 warmup 구간 한정 관찰이며 mechanism 부정이 아니다
  (이전 라운드 oversat 풀런에서 freeway TTT 10배 방어 확인).
- centralized 결과는 보장된 전역 최적이 아니다.

## 산출물 구조

```text
post_analysis/
  stage1_smoke/  six_controller_summary.csv, paired_comparisons.csv,
                 free_flow_reference.csv, fidelity_matrix.md, optimization_diagnostics.csv,
                 runs/<scenario>/<controller>/...
  stage2_smoke/  control_event_catalog.csv, {allocation_green,offset,vsl,metering}_events.csv,
                 mechanism_summary.csv
  stage3_smoke/  information_ablation_summary.csv, player_ablation_summary.csv,
                 directional_coupling_value.csv, coupling_synergy.csv, runs/...
  final_post_analysis_report.md (본 파일)
```

풀 매트릭스 실행 명령(후속):

```text
python -B -m src.experiments.six_controller_comparison --scenario <s> --output post_analysis/stage1
python -B -m src.experiments.stage2_mechanism_validation --scenario <s> --output post_analysis/stage2
python -B -m src.experiments.stage3_coupling_ablation --scenario <s> --output post_analysis/stage3
```
