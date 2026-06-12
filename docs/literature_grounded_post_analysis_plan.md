# Three-Stage Controller Post-Analysis Plan

## 0. 문서 목적

이 문서는 controller 구현이 완료된 뒤 수행할 사후분석을 다음 세 단계로 정의한다.

```text
Stage 1
  여섯 controller의 성능 및 계산량 비교

Stage 2
  제안 control이 필요한 상황에서 올바른 action과 물리효과를 만드는지 검증

Stage 3
  coupling player와 exchanged information의 추가 가치를 ablation으로 정량화
```

분석 순서는 고정한다. Conservation과 control feasibility가 검증되지 않은 상태에서 성능이나
player 가치를 해석하지 않는다.

## 1. 전체 연구 질문

### Stage 1

1. Wu의 green/VSL authority에서 Leader를 추가하면 성능이 개선되는가?
2. Proposed full authority에서 Leader를 추가하면 성능이 개선되는가?
3. Distributed Stackelberg 구조는 centralized controller와 비교해 어떤 성능-계산량 trade-off를
   가지는가?
4. Proposed full control package는 Wu authority보다 urban-freeway exchange를 더 잘 관리하는가?

### Stage 2

1. Allocation, offset, VSL과 ramp metering은 필요한 traffic condition에서 활성화되는가?
2. 선택된 action은 예상한 물리 mediator를 실제로 변화시키는가?
3. 개선이 다른 subsystem으로 congestion을 이전한 결과는 아닌가?

### Stage 3

1. Urban-freeway coupling player가 존재하는 것 자체가 추가 가치를 만드는가?
2. `urban -> freeway`와 `freeway -> urban` 정보 중 어느 방향이 더 중요한가?
3. 양방향 information exchange가 각 단방향 효과의 합을 초과하는 synergy를 만드는가?
4. Player 제거 후 remaining players와 Leader가 재최적화해도 기여가 유지되는가?

## 2. Stage 1: Six-Controller Comparison

### 2.1 비교 Controller

| ID | Architecture | Leader | Control authority |
|---|---|---:|---|
| `WU-CD-F` | Wu cooperative distributed control | 없음 | green, VSL |
| `WU-MATCHED-STACKELBERG` | Wu follower + Leader conditioning | 있음 | green, VSL |
| `WU-CC-F` | Wu centralized control | 없음 | green, VSL |
| `PROPOSED-FOLLOWERS-ONLY` | Proposed distributed followers | 없음 | allocation/green, offset, VSL, metering |
| `PROPOSED-STACKELBERG` | Proposed distributed followers + Leader | 있음 | allocation/green, offset, VSL, metering |
| `PROPOSED-CENTRALIZED` | Proposed centralized MPC | 없음 | allocation/green, offset, VSL, metering |

구현 세부사항은 [16_six_controller_comparison.md](spec/16_six_controller_comparison.md)를 따른다.

### 2.2 Authority Group

Wu group:

```text
WU-CD-F
WU-MATCHED-STACKELBERG
WU-CC-F
```

- green과 VSL만 최적화
- fixed cycle, phase sequence와 offset
- no-metering on-ramp outflow
- allocation module 없음

Proposed group:

```text
PROPOSED-FOLLOWERS-ONLY
PROPOSED-STACKELBERG
PROPOSED-CENTRALIZED
```

- inflow-outflow allocation과 resulting phase green
- signal offset
- ramp metering
- VSL

### 2.3 핵심 Pairwise Comparison

Lower-is-better cost `J`에 대해:

```text
WuLeaderValue =
  J(WU-CD-F)
  - J(WU-MATCHED-STACKELBERG)
```

Wu authority에서 Leader-conditioning을 추가한 가치다.

```text
ProposedLeaderValue =
  J(PROPOSED-FOLLOWERS-ONLY)
  - J(PROPOSED-STACKELBERG)
```

Proposed authority에서 Leader의 한계가치다.

```text
WuCentralizationBenefit =
  J(WU-CD-F)
  - J(WU-CC-F)
```

```text
ProposedCentralizationGap =
  J(PROPOSED-STACKELBERG)
  - J(PROPOSED-CENTRALIZED)
```

```text
FollowerPackageDifference =
  J(WU-CD-F)
  - J(PROPOSED-FOLLOWERS-ONLY)
```

```text
LeaderPackageDifference =
  J(WU-MATCHED-STACKELBERG)
  - J(PROPOSED-STACKELBERG)
```

마지막 두 차이에는 control authority뿐 아니라 follower objective와 implementation 차이도 포함될
수 있다. 이를 특정 control 하나의 순수 효과라고 표현하지 않는다.

### 2.4 공정 비교 조건

모든 controller는 다음을 공유한다.

- physical plant와 conservation equations
- topology, demand, turning ratio, initial state와 seed
- simulation/control/prediction horizon
- detector와 available state information
- TTT/TTS queue 귀속과 terminal cost
- warm-up과 evaluation interval

Authority group 내부에서는 control bounds, action set과 solver evaluation budget을 가능한 한
동일하게 맞춘다.

각 controller는 다음 fidelity matrix를 작성한다.

| 항목 | 기준 문헌/제안식 | 실제 구현 | 차이의 영향 |
|---|---|---|---|
| plant |  |  |  |
| authority |  |  |  |
| objective |  |  |  |
| horizon |  |  |  |
| solver |  |  |  |
| coupling iteration |  |  |  |

### 2.5 Scenario

| Scenario | 목적 |
|---|---|
| low demand | 불필요한 activation과 control variation 확인 |
| freeway bottleneck | VSL과 metering 반응 확인 |
| on-ramp surge | mainline 보호와 urban/ramp queue trade-off 확인 |
| urban blockage | urban congestion의 freeway 전파 확인 |
| off-ramp blockage | Wu green-VSL 및 proposed exchange response 확인 |
| high transfer flow | 강한 on/off-ramp coupling 조건 확인 |
| urban boundary imbalance | allocation과 offset 효과 확인 |
| combined exchange stress | Leader의 urban-freeway externality 조정 확인 |

### 2.6 Primary Metrics

- total, urban과 freeway TTT/TTS
- terminal total vehicles
- terminal urban, on-ramp와 freeway queue
- accepted/blocked off-ramp flow
- actual on-ramp transfer
- urban receiving-link minimum headroom
- capacity-drop duration과 density-exceedance AUC
- network throughput
- computation time, solver evaluations와 convergence rate

Total TTT만 낮추고 terminal queue를 horizon 밖으로 미루면 개선으로 인정하지 않는다.

### 2.7 Statistical Analysis

동일 scenario와 seed를 paired sample로 사용한다.

- mean, median, standard deviation
- paired absolute difference와 improvement percentage
- bootstrap confidence interval
- scenario별 및 pooled result
- seed별 winner count
- computation-time distribution

LeaderValue는 반드시 같은 authority group 내부의 paired difference로 계산한다.

## 3. Stage 2: Control Mechanism Validation

### 3.1 공통 판정 사슬

각 control은 다음 인과사슬로 분석한다.

```text
Trigger
  -> Action
  -> Physical mediator
  -> Outcome
```

Control event 상태:

```text
NOT_CHALLENGED
CORRECTLY_INACTIVE
MECHANISM_REPRODUCED
ACTIVATED_BUT_INEFFECTIVE
WRONG_DIRECTION
CONGESTION_SHIFT
```

### 3.2 Event Window

Trigger가 threshold를 처음 넘은 시점을 `t0`로 정의한다.

```text
pre-window       = [t0 - W_pre, t0)
response-window  = [t0, t0 + W_response]
outcome-window   = (t0 + W_response, t0 + W_outcome]
```

각 event에서:

- action response delay
- trigger-action directional accuracy
- action-mediator lead/lag
- mediator peak, duration과 AUC
- matched counterfactual 대비 outcome

를 계산한다.

### 3.3 Counterfactual

```text
Frozen-control replay:
  동일 t0 state에서 대상 control만 neutral action으로 바꾸고 다른 action은 고정

Closed-loop ablation:
  대상 control을 비활성화하고 다른 controller decision은 다시 최적화
```

첫 번째는 직접 물리효과, 두 번째는 system-level contribution을 분석한다.

## 4. Inflow-Outflow Allocation and Green

Allocation과 green은 하나의 control path로 분석한다.

```text
allocation decision
  -> movement service/green setpoint
  -> feasible phase green
  -> actual accepted departure
```

### Trigger

- boundary movement 간 normalized queue/storage imbalance 증가
- 특정 urban receiving link의 headroom 감소
- off-ramp inflow 증가 또는 predicted blockage
- protected-network accumulation 증가

### Expected Action

- normalized queue가 높은 movement에 더 큰 service/green 배정
- urban headroom이 부족하면 controllable inflow 억제
- off-ramp를 받아야 하면 compatible outflow/off-ramp discharge service 증가
- competing movement starvation 제약 준수

### Mediator

- `B_in`, `B_out` 감소
- movement occupancy dispersion 감소
- actual accepted departure 증가
- urban headroom 증가
- off-ramp blocking 감소

### Required Metrics

```text
allocation_challenged_events
allocation_directional_accuracy
green_setpoint_to_actual_green_error
green_to_actual_departure_gain
delta_B_in
delta_B_out
urban_headroom_change
offramp_acceptance_change
starvation_event_count
```

## 5. Signal Offset

### Trigger

- corridor에 directional platoon 존재
- link travel time이 비교적 안정적
- downstream signal에 receiving space 존재
- 과포화 spillback이 progression을 완전히 붕괴시키지 않은 상태

### Expected Action

- adjacent signal offset difference를 estimated travel time modulo cycle과 정렬
- dominant direction 변화 시 progression 방향 조정
- wraparound와 maximum offset-step constraint 준수

### Mediator

- arrival-on-green 증가
- red arrival과 stops 감소
- corridor delay와 platoon dispersion 감소

### Required Metrics

```text
offset_challenged_events
travel_time_alignment_error
arrival_on_green_change
red_arrival_change
stops_proxy_change
corridor_delay_change
minor_direction_delay_change
offset_green_conflict_events
```

Offset이 freeway 평균속도만 사용하고 urban link travel time을 반영하지 않으면 progression
mechanism이 검증된 것으로 판정하지 않는다.

## 6. Variable Speed Limit

### Trigger

- downstream density가 `rho_crit`에 접근 또는 초과
- off-ramp queue로 `lambda_eff` 감소
- density gradient가 upstream으로 전파
- bottleneck discharge collapse 위험

### Expected Action

- bottleneck upstream의 적절한 segment에서 VSL 감소
- congestion 해소 후 VSL 회복
- low-demand/no-bottleneck 상태에서 maximum VSL 유지

### Mediator

- bottleneck sending flow 완화
- speed difference와 density gradient 완화
- density-exceedance peak/duration 감소
- upstream shockwave propagation 감소

### Required Metrics

```text
vsl_challenged_events
vsl_correctly_inactive_events
vsl_response_delay
vsl_location_accuracy
upstream_sending_flow_change
density_exceedance_auc_change
shockwave_extent_change
bottleneck_discharge_change
unnecessary_vsl_activation_rate
```

## 7. Ramp Metering

### Trigger

- merge density가 `rho_crit`에 접근
- downstream receiving factor 감소
- mainline capacity-drop risk 증가
- 여러 ramp 사이에서 limited receiving capacity 배분 필요

### Expected Action

- no-metering flow보다 release 제한
- receiving condition이 나쁜 ramp를 더 강하게 제한
- ramp queue overflow 위험 시 mainline 보호와 upstream spillback을 trade-off

### Mediator

- merge inflow와 density peak 감소
- mainline speed/discharge 안정화
- 비용으로서 `w_r` 및 `x_on` queue 일시 증가

### Required Metrics

```text
metering_challenged_events
metering_response_delay
metering_restriction_strength
receiving_to_metering_correlation
merge_density_change
capacity_drop_duration_change
mainline_discharge_change
ramp_queue_cost_change
urban_onramp_queue_change
metering_congestion_shift_events
```

## 8. Control Interaction Chains

### Off-ramp response

```text
off-ramp/urban receiving pressure 증가
  -> allocation/green이 receiving space와 discharge를 확보
  -> VSL이 upstream inflow를 일시 완화
  -> capacity drop과 upstream density propagation 감소
```

### On-ramp response

```text
freeway receiving factor 감소
  -> ramp metering 강화
  -> x_on/w_r pressure 증가
  -> urban allocation/green이 on-ramp approach를 관리
  -> freeway 회복 후 metering 완화
```

### Corridor response

```text
urban flow allocation 변화
  -> green pattern 변화
  -> offset이 progression을 재정렬
  -> stops와 internal queue 감소
  -> off-ramp receiving headroom 확보
```

각 chain은 action 순서와 mediator 방향이 모두 맞아야 통과한다.

## 9. Stage 3: Player and Coupling-Information Value

### 9.1 분석 원칙

Stage 3의 기본 controller는 `PROPOSED-STACKELBERG`다.

Player ablation에서도 다음 physical elements는 유지한다.

- intersection, freeway segment와 ramp
- physical queue와 storage
- on/off-ramp vehicle transfer
- conservation equation과 receiving constraint

제거하거나 제한하는 것은:

- player의 strategic decision
- player objective
- exchanged predicted information
- communication edge

뿐이다.

각 ablation에서 remaining players와 Leader는 변경된 game을 기준으로 다시 최적화한다.

### 9.2 Coupling Players

Urban coupling players:

```text
U_D, U_F
```

- on-ramp approach `x_on`
- off-ramp receiving/discharge movement
- adjacent urban storage

Freeway coupling players:

```text
merge-segment agents
off-ramp-boundary agents
```

- ramp queue `w_r`
- merge density와 receiving factor
- off-ramp flow와 capacity-drop state

실제 ID는 topology config에서 자동 추출한다.

## 10. Information Ablation Cases

### `FULL_COUPLING`

모든 physical coupling과 strategic information exchange를 유지한다.

### `NO_U_TO_F_INFO`

Urban player가 freeway player에 보내는 다음 predicted information을 제거한다.

- on-ramp approach release
- `x_on` queue/pressure
- predicted green-driven ramp arrival

Freeway player는 measured current value 또는 zero-order-hold boundary만 사용한다.

### `NO_F_TO_U_INFO`

Freeway player가 urban player에 보내는 다음 predicted information을 제거한다.

- predicted off-ramp inflow
- freeway density/capacity-drop pressure
- ramp receiving factor와 metering pressure

Urban player는 measured current off-ramp arrival만 disturbance로 사용한다.

### `NO_CROSS_NETWORK_INFO`

두 방향의 predicted strategic information을 모두 제거한다. Physical transfer는 유지한다.

### `LOCAL_ONLY_COUPLING_PLAYERS`

Coupling player는 존재하고 action도 결정하지만 자기 local queue/state만 사용한다. Neighbor
prediction과 cross-network objective term은 사용하지 않는다.

## 11. Player Ablation Cases

### `FIXED_URBAN_COUPLING_PLAYERS`

`U_D`, `U_F`의 strategic optimization을 제거하고 green/offset을 calibrated fixed policy로
대체한다. Other players와 Leader는 재최적화한다.

### `FIXED_FREEWAY_COUPLING_PLAYERS`

Merge/off-ramp freeway players의 strategic optimization을 제거하고 VSL/metering을 neutral 또는
calibrated fixed policy로 대체한다. Other players와 Leader는 재최적화한다.

### `FIXED_ALL_COUPLING_PLAYERS`

Urban 및 freeway coupling players를 모두 fixed policy로 대체한다.

이를 physical player 삭제라고 표현하지 않는다. Physical subsystem은 그대로 있고 strategic
controller role만 제거된다.

## 12. Coupling Value Quantification

Lower-is-better cost를 다음처럼 정의한다.

```text
J_full = J(FULL_COUPLING)
J_no_uf = J(NO_U_TO_F_INFO)
J_no_fu = J(NO_F_TO_U_INFO)
J_none = J(NO_CROSS_NETWORK_INFO)
```

### Directional marginal value

```text
Value_U_to_F_given_F_to_U =
  J_no_uf - J_full

Value_F_to_U_given_U_to_F =
  J_no_fu - J_full
```

양수이면 해당 information channel이 상대 방향 정보가 존재할 때 cost를 줄인다.

### Bidirectional interaction

```text
BidirectionalSynergy =
  J_none
  - J_no_uf
  - J_no_fu
  + J_full
```

양수이면 양방향 exchange의 결합효과가 두 단방향 효과의 단순 합보다 크다.

### Order-averaged channel contribution

```text
Phi_U_to_F =
  0.5 * [
      (J_none - J_no_fu)
    + (J_no_uf - J_full)
  ]

Phi_F_to_U =
  0.5 * [
      (J_none - J_no_uf)
    + (J_no_fu - J_full)
  ]
```

이는 두 information channel의 activation order를 평균한 Shapley-style contribution이다.

### Player marginal value

```text
UrbanCouplingPlayerValue =
  J(FIXED_URBAN_COUPLING_PLAYERS)
  - J(FULL_COUPLING)

FreewayCouplingPlayerValue =
  J(FIXED_FREEWAY_COUPLING_PLAYERS)
  - J(FULL_COUPLING)
```

성능 차이가 작거나 음수이면 해당 player/objective가 중복되거나 잘못 설계되었을 가능성을
허용한다.

## 13. Stage 3 Metrics

- total, urban과 freeway TTT/TTS
- accepted off-ramp flow
- off-ramp blocked flow와 spillback duration
- urban receiving-link headroom
- actual on-ramp transfer
- `x_on`, `w_r` queue peak와 terminal value
- merge density와 upstream density propagation
- capacity-drop duration
- Leader selected action과 objective
- coupling residual과 convergence
- computation and communication cost

Subsystem cost뿐 아니라 total cost와 terminal state를 함께 사용한다.

## 14. Required Logs

### Stage 1

- controller ID와 authority group
- objective components
- all control timeseries
- terminal state
- solver/convergence diagnostics

### Stage 2

- trigger score와 threshold
- neutral action과 selected action
- predicted objective difference
- mediator timeseries
- event ID와 response/outcome window

### Stage 3

- active player와 communication edge 목록
- transmitted, blocked와 substituted coupling value
- local objective before/after ablation
- remaining-player reoptimization flag
- Leader reoptimization flag
- communication volume와 iteration count

## 15. Output Structure

```text
post_analysis/
  stage1/
    six_controller_summary.csv
    paired_comparisons.csv
    fidelity_matrix.md
    optimization_diagnostics.csv

  stage2/
    control_event_catalog.csv
    allocation_green_events.csv
    offset_events.csv
    vsl_events.csv
    metering_events.csv
    interaction_chain_events.csv

  stage3/
    information_ablation_summary.csv
    player_ablation_summary.csv
    directional_coupling_value.csv
    coupling_synergy.csv

  plots/
  final_post_analysis_report.md
```

## 16. 실행 순서

1. Conservation, units, queue accounting과 control constraints 검증
2. 여섯 controller 구현 및 authority 자동검사
3. 동일 scenario/seed로 Stage 1 실행
4. Paired performance와 computation comparison
5. Proposed control별 trigger event catalog 생성
6. Frozen replay와 closed-loop ablation으로 Stage 2 검증
7. Stage 2 mechanism이 통과한 뒤 Stage 3 ablation 실행
8. Information direction별 marginal value와 synergy 계산
9. Player marginal value와 reoptimization 결과 계산
10. 주장, 실패 원인과 fidelity limitation 보고

## 17. PASS/FAIL 기준

### Stage 1 PASS

- authority group 내부 fair comparison 성립
- Leader pair에서 follower action이 실제로 달라짐
- terminal queue를 포함해 개선이 반복됨
- centralized/distributed computation 차이가 함께 보고됨

### Stage 2 PASS

- challenged event에서 expected action이 발생
- action 이후 mediator가 expected direction으로 변화
- counterfactual보다 outcome 개선
- unnecessary activation과 congestion shift가 허용 범위 이하

### Stage 3 PASS

- physical coupling을 유지한 채 strategic effect만 분리
- ablation 이후 remaining players가 재최적화됨
- information 또는 player contribution이 여러 coupling-stress scenario에서 반복
- directional value와 bidirectional synergy의 부호 및 불확실성이 함께 보고됨

## 18. 주장 범위

주장 가능:

- Wu authority와 proposed authority 각각에서 Leader의 추가 가치
- distributed/Stackelberg와 centralized control의 성능-계산량 trade-off
- proposed control이 특정 traffic trigger에서 만드는 물리효과
- coupling information direction 및 coupling player의 한계기여
- 양방향 information exchange의 interaction/synergy

주장 불가:

- authority가 다른 controller 차이를 특정 control 하나의 순수 효과로 해석
- control value 변화만으로 mechanism을 검증했다고 주장
- physical network를 삭제한 ablation을 player contribution으로 해석
- evaluation result에 맞춘 사후 tuning을 fair comparison으로 주장
- 통계적 불확실성 없이 단일 run을 일반적 coupling value로 주장

## 19. 참고 문헌

- Wu, N., Li, D., and Xi, Y. (2022). "Distributed Integrated Control of a Mixed Traffic
  Network With Urban and Freeway Networks." IEEE Transactions on Control Systems Technology,
  30(1), 57-69. DOI: `10.1109/TCST.2021.3055071`.
