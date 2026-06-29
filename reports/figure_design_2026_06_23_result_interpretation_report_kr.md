# Figure-Design 2026-06-23 Redraw 한국어 해석 리포트

작성일: 2026-06-25

이 문서는 `reports/figure_design_2026_06_23_result_interpretation_report.md`의 한국어 해석판이다. 단순 번역이라기보다는, 논문 본문과 figure caption 작성에 바로 활용할 수 있도록 각 그림의 핵심 메시지와 주의점을 한국어로 정리했다.

## 분석 범위

이 리포트는 2026-06-23 Desktop raw output을 `docs/figure_design/*.md` 기준으로 새로 그린 figure set에 대한 해석 기록이다. 새 simulation은 수행하지 않았고, 기존 3600초 결과를 재가공했다.

- Figure root: `reports/figures/figure_design_2026_06_23_redraw/`
- Source raw 1: `C:\Users\alsrj\Desktop\Numerical-Sim\outputs\analysis_matrix_3600`
- Source raw 2: `C:\Users\alsrj\Desktop\Numerical-Sim\outputs\analysis_matrix_3600_extra`
- 생성 결과: PNG 37개 + PDF 37개
- QA contact sheet: `reports/figures/figure_design_2026_06_23_redraw/_qa_contact_sheets/`

## Figure 생성 가정

### Scenario 매핑

| Raw scenario id | Figure label | 해석 |
|---|---:|---|
| `medium_demand` | Median | 제어 여지가 있는 중간 수요 |
| `peak_demand` | Peak | spillback 위험이 있는 고수요 |
| `skew_peak` | Peak skew | 공간적으로 편향된 고수요 |
| `incident_or_capacity_drop` | Incident | capacity-drop 또는 incident 위험 |

현재 canonical scenario set은 이후에 다시 수정되었으므로, 이 figure set은 최신 six-scenario definition의 최종 증거가 아니라 6월 23일 raw result에 대한 사후분석으로 해석해야 한다.

### Controller 매핑

| Controller | Figure label | 해석 |
|---|---:|---|
| `NO-CONTROL` | No control | fixed-time signal, RM 없음, VSL 없음 |
| `WU-CD-F` | WU-CD-F | Wu-authority-matched distributed benchmark, signal + VSL 권한 |
| `PROPOSED-FOLLOWERS-ONLY` | PFO | leader 없는 proposed distributed follower package |
| `PROPOSED-STACKELBERG` | P-Stack | leader-follower 위계 구조 |

`PROPOSED-CENTRALIZED`는 이 raw output set에 없으므로 본 리포트에서는 비교하지 않는다.

### Metric 가정

- Macro 값은 `analysis/summary_with_no_control.csv`에서 읽었다.
- `Average travel-time proxy`는 `total_ttt / completed_vehicles * 3600`으로 계산했다.
- 이 값은 실제 trajectory 기반 average travel time이 아니라, TTT를 완료 차량 수로 나눈 proxy이다.
- Time-series figure는 `progress_summary.csv`를 사용했다.
- Control mechanism figure는 `control_timeseries.csv`와 `run_log.csv`를 사용했다.
- VSL activation은 posted VSL이 99 km/h보다 낮을 때로 계산했다.
- RM activation은 logged metering rate 중 하나라도 1499 veh/h보다 낮을 때로 계산했다.
- Green activation은 green time이 nominal 56초에서 1초 이상 벗어날 때로 계산했다.
- Offset activation은 step-to-step offset 변화량이 1초를 넘을 때로 계산했다.

### 진단상 주의점

- 6월 23일 raw output에는 `decision_progress.csv`가 없어서 rejected leader candidate 전체 objective surface는 복원할 수 없다.
- 따라서 Fig. 4D는 selected action에 대해서만 leader objective와 다음 step realized plant TTT를 비교한다.
- Fig. 4D는 objective fidelity sanity check이지, 모든 rejected candidate가 올바르게 rank되었다는 증거는 아니다.
- Boundary queue/load exposure는 사용 가능한 logged proxy column을 기반으로 했다.
- 이 raw set에서는 P-Stack의 leader-side boundary/load proxy가 다른 controller보다 더 명확히 logged되어 있다.
- 따라서 Fig. 2B의 boundary panel은 harmonized cross-controller accounting이라기보다 diagnostic warning으로 해석해야 한다.
- P-Stack fallback, allocation mode, search budget metadata는 raw table에서 부분적으로만 확인된다.

## Layout QA 결과

생성된 figure는 개별 PNG preview와 QA contact sheet를 통해 시각적으로 확인했다. 다음 수정이 반영되었다.

- Macro와 congestion-transfer multi-panel figure에서 축 내부 legend를 figure-level top legend로 이동했다.
- Fig. 6C의 per-point text label을 제거하고, controller는 색상, scenario는 marker shape으로 표시했다.
- Fig. 4E objective coverage audit의 여백과 tick label 크기를 조정했다.
- Fig. 2C off-ramp acceptance ratio는 desired off-ramp flow를 veh/h에서 vehicle 단위로 시간 적분한 뒤 accepted/desired ratio를 계산하도록 수정했다.
- Figure set과 QA contact sheet를 다시 생성했다.

## 거시적 해석

### Total TTT 개선율

| Scenario | WU-CD-F | PFO | P-Stack |
|---|---:|---:|---:|
| Median | 7.8% | 8.7% | 8.7% |
| Peak | 33.8% | 39.7% | 53.4% |
| Peak skew | 34.4% | 38.1% | 49.7% |
| Incident | 37.2% | 39.9% | 47.2% |

핵심 패턴은 분명하다. Median에서는 P-Stack과 PFO가 거의 동일하지만, Peak, Peak skew, Incident에서는 P-Stack의 leader layer가 추가적인 성능 향상을 만든다. 따라서 leader layer의 가치는 평상시 중간 수요보다, urban-freeway coupling과 storage pressure가 강해지는 stress scenario에서 더 잘 드러난다.

### Throughput과 terminal burden

P-Stack은 congested scenario에서 TTT를 줄이면서 동시에 더 많은 차량을 처리한다.

| Scenario | No-control completed | P-Stack completed | No-control terminal | P-Stack terminal |
|---|---:|---:|---:|---:|
| Median | 11229.9 | 11632.3 | 830.3 | 430.9 |
| Peak | 9025.6 | 12886.6 | 5789.6 | 1929.8 |
| Peak skew | 8867.9 | 12403.1 | 5947.3 | 2415.6 |
| Incident | 9071.0 | 11911.1 | 5292.2 | 2457.2 |

즉, 이 aggregate summary만 놓고 보면 P-Stack의 개선은 단순히 차량을 evaluation 밖으로 숨겼기 때문이라고 보기 어렵다. Peak, Peak skew, Incident에서 P-Stack은 cumulative vehicle-hours를 줄이고, completed vehicles를 늘리고, terminal vehicles도 줄인다.

### Travel-time proxy

`TTT/completed` proxy 역시 active controller에서 크게 낮아진다.

| Scenario | No control | PFO | P-Stack |
|---|---:|---:|---:|
| Median | 171.9 s/veh | 151.5 s/veh | 151.6 s/veh |
| Peak | 1006.4 s/veh | 473.2 s/veh | 328.7 s/veh |
| Peak skew | 1054.8 s/veh | 508.4 s/veh | 379.6 s/veh |
| Incident | 898.6 s/veh | 428.9 s/veh | 361.1 s/veh |

이는 throughput 증가가 travel-time proxy 악화로 이어진 것이 아니라는 점을 보여준다. 다만 이 값은 실제 개별 차량 trajectory 기반 average travel time이 아니라 aggregate proxy라는 점을 명시해야 한다.

## Congestion Transfer 해석

TTT decomposition을 보면 congested scenario에서 가장 큰 절대 개선은 freeway TTT 감소에서 나온다. 동시에 urban TTT도 no control 대비 대체로 감소한다. 따라서 이 raw summary에서는 P-Stack이 freeway만 보호하고 urban 쪽으로 모든 burden을 밀어낸다고 단정하기 어렵다.

다만 queue exposure figure에서는 P-Stack이 일부 ramp queue exposure를 감수하는 모습이 보인다.

- Peak에서는 P-Stack ramp queue exposure가 PFO와 no control보다 높다.
- Incident에서는 P-Stack ramp queue exposure가 no control보다는 낮지만 WU-CD-F/PFO보다는 높다.
- Off-ramp storage exposure는 절대값이 작다.
- Boundary/load exposure는 controller별 logging proxy가 harmonized되어 있지 않으므로 최종 fairness metric으로 쓰기 어렵다.

해석상으로는, P-Stack이 모든 local queue를 없애는 controller라기보다 일부 local storage burden을 감수하면서 전체 network TTT, throughput, terminal burden을 개선하는 controller라고 보는 것이 더 정확하다.

## Leader Feasibility 해석

Fig. 3A와 Fig. 3C는 P-Stack leader가 단순히 PFO/no-control fallback만 선택한 것이 아니라 실제 target을 선택하고 있음을 보여준다.

주요 관찰은 다음과 같다.

- Fallback selection은 거의 0이다.
- `N_UF_star`와 actual metering flow는 초기 transient 이후 대체로 같은 범위에서 움직인다.
- 반면 `N_P_star`와 actual net inflow는 tight하게 tracking되지 않는다.

따라서 freeway/ramp target은 follower behavior에 영향을 주지만, perimeter net-inflow target은 physical feasibility, target definition, 또는 logging/sign convention 문제를 추가로 확인해야 한다.

## Game Coupling 해석

Fig. 4B는 control action proxy와 response proxy 사이의 correlation을 보여준다.

- Green service는 freeway TTT, ramp queue, urban TTT, urban queue와 음의 상관관계를 가진다.
- RM 역시 freeway TTT와 ramp queue와 음의 상관관계를 보인다.
- Offset proxy는 상대적으로 약하고 혼합된 correlation을 보인다.

이 결과는 urban-freeway coupling이 존재한다는 descriptive evidence로 사용할 수 있다. 다만 correlation이므로 causal sensitivity나 game-theoretic derivative라고 주장하면 안 된다. 더 강한 주장을 위해서는 candidate-level perturbation 또는 ablation이 필요하다.

Fig. 4D는 selected leader objective와 next-step realized TTT 사이에 monotone한 관계가 있음을 보여준다. 이는 objective fidelity 측면에서는 긍정적이지만, rejected candidate가 없으므로 leader가 항상 최적 candidate를 골랐다는 증거는 아니다.

## Micro-Control 해석

Micro-control figure들은 controller authority와 잘 맞는다.

- WU-CD-F는 signal green과 VSL을 조정하지만 RM과 offset 권한은 없다.
- PFO와 P-Stack은 Peak, Peak skew, Incident에서 RM을 자주 사용한다.
- P-Stack은 congested scenario에서 PFO보다 더 공격적인 RM과 offset 변화를 보인다.
- VSL activation은 주로 Incident에서 WU-CD-F와 PFO에서 나타난다.
- 이 raw set에서 P-Stack의 개선은 VSL보다는 RM, signal, offset, leader target coordination 쪽에 더 강하게 연결되어 보인다.

## Computation 해석

3600초 run은 180초 control interval에서 20 control step으로 구성된다. Mean wall time per control step은 대략 다음과 같다.

| Scenario | WU-CD-F | PFO | P-Stack |
|---|---:|---:|---:|
| Median | 4.9 s | 6.6 s | 64.1 s |
| Peak | 4.9 s | 8.2 s | 64.0 s |
| Peak skew | 5.4 s | 8.2 s | 67.1 s |
| Incident | 4.9 s | 8.1 s | 60.9 s |

세 active controller 모두 180초 control interval 안에는 들어온다. 하지만 P-Stack은 PFO와 WU-CD-F보다 훨씬 비싸다. 따라서 실시간성에 대한 주장은 다음처럼 조심스럽게 해야 한다.

- 이 raw experiment budget에서는 P-Stack도 real-time feasible하다.
- 그러나 computation cost는 여전히 핵심 trade-off이다.
- Centralized comparison이 있어야 P-Stack이 centralized 대비 어떤 performance-computation 위치를 갖는지 말할 수 있다.

## 그림별 해석 노트

이 절은 각 figure별로 본문 또는 caption에 바로 연결할 수 있는 해석 메모이다.

### 01 Macro Performance

#### `Fig1A_total_ttt_cross_scenario`

이 그림은 전체 성능 비교의 핵심 figure이다. 모든 active controller가 no control보다 Total TTT를 줄이지만, P-Stack의 추가 이득은 stress scenario에서 가장 크게 나타난다. Median에서는 PFO와 P-Stack이 거의 동일하므로 leader layer의 우월성을 강하게 주장하기 어렵다. Peak, Peak skew, Incident에서는 P-Stack이 WU-CD-F와 PFO보다 큰 개선을 보인다.

논문 해석: Stackelberg leader는 평상시 수요보다 congestion, spillback, capacity drop이 강해지는 상황에서 가치가 커진다.

#### `Fig1B_urban_freeway_ttt_decomposition`

이 그림은 total TTT 개선이 urban과 freeway 중 어디에서 발생하는지 보여준다. 가장 큰 절대 개선은 freeway TTT 감소에서 나타난다. 동시에 congested scenario에서 urban TTT도 no control 대비 줄어든다.

논문 해석: P-Stack은 freeway breakdown을 줄이는 효과가 크지만, 이 raw summary에서는 urban TTT를 희생해서 freeway만 보호한다고 보기 어렵다.

#### `Fig1C_delay_att_throughput`

이 그림은 total delay, TTT/completed proxy, throughput을 함께 보여준다. P-Stack은 stress scenario에서 delay와 travel-time proxy를 낮추면서 throughput을 증가시킨다.

논문 해석: P-Stack의 TTT 개선은 차량을 덜 처리해서 생긴 결과가 아니다. 오히려 더 많은 차량을 처리하면서 aggregate travel-time proxy를 낮춘다.

#### `Fig1D_terminal_state_burden`

이 그림은 horizon 끝에 남아 있는 차량 부담을 보여준다. No control은 stress scenario에서 terminal vehicles가 크게 증가한다. P-Stack은 terminal total vehicles를 크게 낮춘다.

논문 해석: P-Stack은 evaluation horizon 끝으로 congestion을 미루는 것이 아니라, horizon-end clearance도 개선한다.

#### `Fig2_timeseries_medium_demand`

Median time-series에서는 active controller들의 궤적이 대부분 비슷하다. No control은 후반부에 악화되지만, PFO와 P-Stack의 차이는 작다.

논문 해석: Median은 leader layer의 강점을 보여주는 scenario라기보다, 불필요한 과제어 없이 안정적으로 작동하는지 확인하는 sanity case이다.

#### `Fig2_timeseries_peak_demand`

Peak에서는 congestion이 쌓인 뒤 controller 간 궤적 차이가 커진다. No control은 TTT와 terminal vehicles가 빠르게 증가하고, P-Stack은 cumulative TTT와 terminal burden을 가장 낮게 유지한다.

논문 해석: 높은 수요에서는 local follower만으로 부족한 coupling 문제가 생기고, leader-follower 구조가 추가 이득을 만든다.

#### `Fig2_timeseries_skew_peak`

Skew peak는 전체 수요뿐 아니라 공간적 불균형이 있는 경우를 보여준다. P-Stack은 이 경우에도 PFO와 WU-CD-F보다 cumulative TTT와 terminal burden을 더 낮춘다.

논문 해석: leader layer는 단순한 high demand뿐 아니라 spatial imbalance가 있는 경우에도 도움이 된다.

#### `Fig2_timeseries_incident_or_capacity_drop`

Incident/capacity-drop scenario에서는 no control의 누적 TTT와 terminal burden이 지속적으로 증가한다. Active controller들은 이를 완화하고, P-Stack이 가장 강한 성능을 보인다.

논문 해석: freeway capacity가 줄어드는 상황에서 RM, signal, leader coordination이 congestion propagation을 완화한다.

### 02 Congestion Transfer

#### `Fig2A_spillback_summary`

이 그림에서는 logged hard overflow 또는 binding step이 0으로 나타난다. 즉, 성능 차이는 binary hard spillback event보다 queue exposure와 TTT dynamics에서 발생한다.

논문 해석: 이 figure는 성능 figure라기보다 hard-constraint diagnostic으로 사용해야 한다.

#### `Fig2B_queue_exposure_summary`

Ramp, off-ramp, boundary/load exposure를 보여준다. P-Stack은 Peak에서 상당한 ramp queue exposure를 감수한다. Off-ramp storage exposure는 절대값이 작다. Boundary/load panel은 logging proxy가 controller별로 동일하지 않으므로 final fairness claim으로 쓰면 안 된다.

논문 해석: P-Stack은 모든 local queue를 줄이는 controller가 아니라, local queue 부담을 일부 감수하면서 network-level 성능을 개선하는 controller이다.

#### `Fig2C_offramp_acceptance_ratio`

단위 보정 이후 accepted/designed off-ramp flow ratio는 대부분 1에 가깝다. 즉, 이 raw set에서 off-ramp flow가 대규모로 거부되고 있다고 보기는 어렵다.

논문 해석: 주요 성능 차이는 off-ramp starvation 때문이라기보다 freeway/ramp/urban coordination 차이에서 발생한 것으로 보는 것이 타당하다.

#### `Fig2D_onramp_mechanism_incident_or_capacity_drop`

Incident case에서 ramp queue, metering flow, urban on-ramp queue, ramp releases의 시간 변화를 보여준다. P-Stack은 no control과 다른 metering/release pattern을 보이며 freeway entry를 조절한다.

논문 해석: Incident 상황에서 P-Stack은 단순히 no-control inflow를 따라가는 것이 아니라, controlled release를 통해 더 큰 freeway deterioration을 막는다.

#### `Fig2D_onramp_mechanism_peak_demand`

Peak case에서 P-Stack은 PFO와 WU-CD-F보다 강한 ramp-metering behavior를 보인다. Ramp queue exposure는 커질 수 있지만, aggregate terminal burden과 TTT는 개선된다.

논문 해석: Peak 성능 개선은 VSL만으로 설명되기 어렵고, RM과 signal/offset/leader target의 조합으로 해석하는 것이 적절하다.

### 03 Leader Feasibility

#### `Fig3A_leader_targets_response_medium_demand`

Median에서도 leader target은 선택되지만, PFO 대비 성능 차이는 작다. `N_UF_star`와 actual metering flow는 어느 정도 같은 범위에서 움직이지만, `N_P_star`와 actual net inflow는 tight하게 맞지 않는다.

논문 해석: Median에서는 leader가 작동하지만 marginal value가 작다.

#### `Fig3A_leader_targets_response_peak_demand`

Peak에서는 `N_P_star`와 `N_UF_star`가 모두 적극적으로 조정된다. `N_UF_star`는 actual metering flow와 어느 정도 연결되어 보이지만, `N_P_star` tracking은 불완전하다.

논문 해석: freeway/ramp target은 follower behavior에 영향을 주지만, perimeter net-inflow target realization은 추가 검증이 필요하다.

#### `Fig3A_leader_targets_response_skew_peak`

Skew peak에서도 leader target이 변화한다. 이 경우 역시 `N_UF_star`의 영향은 보이지만 `N_P_star` tracking은 완벽하지 않다.

논문 해석: spatially skewed demand에서 leader가 target을 조정하지만, target-response mismatch는 feasibility 또는 logging issue로 남는다.

#### `Fig3A_leader_targets_response_incident_or_capacity_drop`

Incident case에서는 시간이 지날수록 leader objective가 증가하고, target-response mismatch가 더 두드러진다.

논문 해석: Incident 조건은 leader target tracking의 한계를 드러낸다. active leader behavior는 확인되지만 perfect tracking을 주장하면 안 된다.

#### `Fig3B_logged_best_candidate_locations`

이 그림은 full objective surface가 아니라 logged best leader candidate 위치를 보여준다. 선택된 candidate는 특정 `N_P_star`와 `N_UF_star` 영역에 분포한다.

논문 해석: leader가 항상 같은 target만 고른 것은 아니지만, rejected candidate surface가 없으므로 global optimality를 주장할 수 없다.

#### `Fig3CD_fallback_tracking_error`

Fallback selection은 거의 0에 가깝다. 따라서 이 raw set에서 P-Stack 결과는 PFO fallback 때문에 나온 것이 아니라 active leader target selection 결과로 봐야 한다. 다만 tracking error는 여전히 존재한다.

논문 해석: P-Stack은 active하게 leader target을 선택하지만, target tracking fidelity는 별도 분석 대상으로 남는다.

### 04 Game Coupling

#### `Fig4A_nash_response_diagnostics`

Follower response iteration diagnostics를 보여준다. WU-CD-F와 PFO는 iteration range가 더 넓고, P-Stack은 더 좁게 분포한다.

논문 해석: logged run에서 response procedure는 수치적으로 안정적이지만, iteration count만으로 equilibrium quality를 증명할 수는 없다.

#### `Fig4B_coupling_response_matrix`

Action proxy와 response proxy 사이의 correlation heatmap이다. Green service, RM, VSL proxy는 대체로 TTT/queue response와 음의 상관관계를 보인다. Offset proxy는 약하고 혼합된 상관을 보인다.

논문 해석: urban-freeway coupling의 descriptive evidence로 사용할 수 있다. 다만 causal sensitivity로 해석하면 안 된다.

#### `Fig4D_predicted_vs_realized_selected`

Selected leader objective와 next-step realized plant TTT 사이에 단조적인 관계가 있다.

논문 해석: selected-action objective fidelity는 긍정적이다. 하지만 rejected candidate가 없으므로 leader ranking 전체가 맞았다는 증거는 아니다.

#### `Fig4E_objective_coverage_audit`

Freeway follower, urban follower, leader, plant TTT가 어떤 state group을 보는지 정리한 audit figure이다. Local follower들은 전체 state를 모두 보지 않고, leader와 plant TTT가 더 넓은 coverage를 갖는다.

논문 해석: 이 figure는 hierarchy 구조를 설명하는 데 유용하다. Local objective와 global accounting의 차이를 명시하는 용도로 써야 한다.

### 05 Micro Control Behavior

#### `Fig5_mechanism_panel_incident_or_capacity_drop`

Incident mechanism panel에서는 P-Stack이 강한 RM과 offset 변화를 사용하고, WU-CD-F/PFO는 VSL activation이 뚜렷하다.

논문 해석: P-Stack의 incident 개선은 단일 actuator가 아니라 RM, signal, offset, leader target coordination의 결과로 보는 것이 적절하다.

#### `Fig5_mechanism_panel_peak_demand`

Peak mechanism panel에서 P-Stack은 급격한 RM과 offset 조정을 보인다. PFO는 더 부드럽고, WU-CD-F는 RM/offset 권한이 없다.

논문 해석: leader layer는 peak congestion에서 local follower action의 강도와 timing을 변화시킨다.

#### `Fig5_mechanism_panel_skew_peak`

Skew peak에서는 P-Stack의 sustained RM action과 강한 offset activity가 나타난다.

논문 해석: spatial imbalance가 있을 때 offset과 RM이 함께 중요해진다.

#### `Fig5A_RM_mean_metering_rate`

Stress scenario에서 P-Stack의 mean metering rate가 더 낮다. 이는 더 강한 metering을 의미한다.

논문 해석: P-Stack의 congested-scenario gain은 더 적극적인 freeway-entry regulation과 연결된다.

#### `Fig5A_RM_activation_fraction`

PFO와 P-Stack은 Peak, Peak skew, Incident에서 RM을 자주 activate한다. P-Stack은 Median에서도 PFO보다 RM activation이 더 높다.

논문 해석: RM은 proposed controller와 WU-CD-F를 구분하는 핵심 authority이다.

#### `Fig5B_VSL_reduction`

Mean VSL reduction은 주로 Incident에서 WU-CD-F와 PFO에 나타난다. P-Stack은 이 raw set에서 VSL reduction이 크지 않다.

논문 해석: P-Stack의 성능 향상을 VSL 중심으로 설명하면 안 된다.

#### `Fig5B_VSL_activation`

VSL activation은 Incident에 집중되어 있다.

논문 해석: VSL은 모든 scenario의 보편적 개선 메커니즘이라기보다, capacity-drop 또는 incident 상황에서 의미 있는 actuator로 해석해야 한다.

#### `Fig5C_green_adjustment`

WU-CD-F, PFO, P-Stack 모두 green time을 조정한다. P-Stack은 Peak skew와 Incident에서 더 큰 green adjustment를 보인다.

논문 해석: signal control은 urban-freeway boundary condition을 관리하는 핵심 요소이다.

#### `Fig5C_green_activation`

Green activation은 active controller 전반에서 자주 나타난다.

논문 해석: controller 차이는 green control의 유무만이 아니라, green control이 RM, offset, leader target과 어떻게 결합되는지에서 발생한다.

#### `Fig5D_offset_change`

Offset change는 PFO와 P-Stack에만 존재한다. P-Stack은 stress scenario에서 더 큰 offset change를 보인다.

논문 해석: offset은 단독 핵심 메커니즘이라기보다, RM 및 green-time coordination과 결합될 때 의미 있는 보조 조정 수단이다.

#### `Fig5D_offset_activation`

Offset activation은 PFO/P-Stack에서 나타나고, WU-CD-F/no-control에서는 authority상 나타나지 않는다.

논문 해석: 이 figure는 성능 차이의 직접 증명이라기보다 controller authority 차이를 문서화하는 용도에 가깝다.

### 06 Computation Cost

#### `Fig6A_runtime_per_control_step`

P-Stack은 WU-CD-F와 PFO보다 훨씬 느리지만, 이 3600초 run에서는 180초 control interval 아래에 있다.

논문 해석: P-Stack은 tested budget에서 real-time feasible하지만, computation cost trade-off가 크다.

#### `Fig6B_candidate_evaluation_budget`

P-Stack의 계산 비용은 leader candidate evaluation과 follower response work 때문에 커진다. PFO는 follower-grid cost가 있지만 leader layer가 없다.

논문 해석: P-Stack의 practical issue는 stressed-scenario 성능 이득을 유지하면서 evaluation cost를 줄이는 것이다.

#### `Fig6C_performance_compute_tradeoff`

Performance improvement와 mean wall time per step의 trade-off를 보여준다. P-Stack은 stress scenario에서 성능이 가장 좋지만 계산 비용도 가장 크다. Median에서는 PFO 대비 성능 이득이 거의 없는데 계산 비용만 크다.

논문 해석: P-Stack의 주장은 universal dominance가 아니라 stress-dependent trade-off이다. Peak, Peak skew, Incident에서는 더 큰 계산 비용이 큰 성능 이득으로 이어지지만, Median에서는 그렇지 않다.

## 주요 결론

1. PFO는 proposed distributed follower layer 자체의 효과를 보여준다. WU-CD-F보다 대부분 stress scenario에서 개선되고 계산도 빠르다.
2. P-Stack은 Peak, Peak skew, Incident에서 명확한 추가 이득을 보인다.
3. Median에서는 P-Stack과 PFO가 거의 같으므로 leader layer의 필요성을 Median으로 주장하면 약하다.
4. P-Stack은 TTT 개선과 함께 completed vehicles 증가, terminal burden 감소, TTT/completed proxy 감소를 동시에 보인다.
5. Boundary/load exposure는 harmonized logging 없이 final fairness 또는 queue-hiding claim으로 쓰면 위험하다.
6. 현재 figure set은 macro, micro, game-coupling discussion에는 적합하지만, 최종 causal claim을 위해서는 ablation과 candidate-level fidelity 분석이 더 필요하다.

