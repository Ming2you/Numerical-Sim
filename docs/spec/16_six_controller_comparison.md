# Controller Comparison Specification

> 2026-06-13 개정(연구자 결정). 주 비교군을 여섯에서 넷으로 축소하고
> `PROPOSED-FOLLOWERS-ONLY`를 allocation module 없는 형태로 재정의했다.
> `WU-MATCHED-STACKELBERG`와 `WU-CC-F`는 보조 참고군으로 강등한다(구현·과거 결과 유지).

## 16.1 문서 목적

이 문서는 Wu et al. (2022) 기반 control authority와 본 연구의 full control authority를
분리하여 비교하기 위한 controller 사양이다.

주 비교군은 다음 네 controller다.

```text
1. WU-CD-F                  (Wu et al. distributed control)
2. PROPOSED-FOLLOWERS-ONLY  (follower 패키지: green 자유탐색 + offset + metering + VSL)
3. PROPOSED-STACKELBERG     (본 연구 full controller: Leader + allocation 포함)
4. PROPOSED-CENTRALIZED     (full-information centralized reference)
```

이 구조는 다음 효과를 구분한다.

- follower 패키지에 Leader와 allocation coordination layer를 추가한 결합 효과
- Distributed/Stackelberg 구조와 centralized 구조의 성능 및 계산량 차이
- Wu authority 대비 follower 패키지(offset/metering 추가)의 차이

보조 참고군(주 매트릭스에서 제외, 필요 시 별도 분석): `WU-MATCHED-STACKELBERG`,
`WU-CC-F`(16.5, 16.6).

참고 문헌:

> Wu, N., Li, D., and Xi, Y. (2022).
> "Distributed Integrated Control of a Mixed Traffic Network With Urban and Freeway Networks."
> IEEE Transactions on Control Systems Technology, 30(1), 57-69.
> DOI: `10.1109/TCST.2021.3055071`.

## 16.2 공통 Physical Plant

모든 controller가 다음 physical plant를 공유한다.

- urban movement queue와 storage dynamics
- METANET freeway dynamics
- `x_on -> w_r -> freeway` on-ramp conservation
- freeway-to-urban off-ramp transfer
- off-ramp receiving-space constraint
- Wu-style off-ramp spillback capacity drop
- 동일 topology, demand, turning ratio와 initial state
- 동일 `T_u`, `T_f`, `T_c` nested simulation order
- 동일 TTT/TTS queue 귀속과 terminal-cost 규칙
- 동일 controller-independent free-flow delay reference

Controller를 제거하거나 information edge를 제한하더라도 physical on/off-ramp 연결과 차량
보존식은 변경하지 않는다.

## 16.3 Control Authority

### 16.3.1 Wu authority

```text
U_WU = [
  green_time_i,p,
  vsl_m
]
```

- signal cycle, offset와 phase sequence는 fixed
- ramp metering은 사용하지 않음
- on-ramp outflow는 no-metering physical outflow
- inflow-outflow allocation module은 사용하지 않음
- route choice는 fixed/exogenous

### 16.3.2 Proposed full authority

```text
U_PROPOSED = [
  inflow_outflow_allocation,
  signal_offset,
  ramp_metering,
  vsl
]
```

`inflow_outflow_allocation`은 movement별 service target 또는 green setpoint를 생성한다. 실제
plant에 적용되는 signal actuator는 feasible phase green time이다. 따라서 green은 별도의 다섯
번째 package가 아니라 allocation decision의 signal implementation으로 기록한다.

```text
allocation
  -> movement/phase green setpoint
  -> feasible cycle projection
  -> actual phase green
```

Cycle length와 phase sequence는 proposed group에서도 fixed로 둔다.

## 16.4 Controller 1: `WU-CD-F`

Wu의 cooperative distributed control을 현재 plant에 재구성한다.

### Architecture

- urban agent: intersection 단위
- freeway agent: consecutive segment/link group
- urban control: phase green
- freeway control: VSL
- Leader 없음
- agent별 local TTS와 control variation objective
- neighbor coupling variable을 local solve 동안 fixed
- iteration 사이에 updated coupling variable 교환

### Coupling variables

```text
urban -> urban:
  upstream leaving flow, downstream vehicle/storage state

urban -> freeway:
  on-ramp approach discharge, source-side vehicle state

freeway -> urban:
  off-ramp inflow, off-ramp/storage pressure

freeway -> freeway:
  boundary density and speed
```

### Algorithm

```text
1. 직전 실제값으로 coupling prediction 초기화
2. neighbor coupling을 수신하고 local solve 동안 fixed
3. 각 agent가 자기 green 또는 VSL sequence 최적화
4. outgoing coupling prediction 갱신
5. coupling residual 검사
6. residual < epsilon 또는 iteration >= S_max이면 종료
7. 첫 control sample 적용
```

## 16.5 (보조) `WU-MATCHED-STACKELBERG` — 주 비교군 제외

Wu의 agent partition, green/VSL authority, local dynamics, base local objective와 coupling
iteration을 유지하면서 upper-level Leader-conditioning interface만 추가한다.

엄밀히 말하면 Wu 원문 controller 자체가 아니라 `Wu-authority-matched Stackelberg variant`다.

### Leader action

```text
U_L_WU = [
  N_P_star,
  N_F_star
]
```

- `N_P_star`: urban accumulation coordination target [veh]
- `N_F_star`: freeway accumulation coordination target [veh]

Ramp metering이 없으므로 기존 `[veh/h]` ramp-flow 의미의 `N_UF_star`는 사용하지 않는다.

### Conditioned local objective

Wu base objective는 유지하고 Leader target에 반응하는 최소 conditioning term만 추가한다.

```text
J_i_WU_stack =
    J_i_WU_local
  + w_P_target
    * positive_part(n_P_i_predicted - omega_P[i] * N_P_star)

J_p_WU_stack =
    J_p_WU_local
  + w_F_target
    * positive_part(n_F_p_predicted - omega_F[p] * N_F_star)
```

```text
sum_i omega_P[i] = 1
sum_p omega_F[p] = 1
```

Agent weights는 evaluation 전에 고정하며 결과를 보고 재조정하지 않는다.

### Leader evaluation

```text
for each (N_P_star, N_F_star) candidate:
  solve Wu distributed follower response
  predict coupled plant
  evaluate system objective

select candidate with minimum system objective
apply first green/VSL sample
```

Leader는 green/VSL을 직접 결정하지 않고 Wu follower response를 target으로 조정한다.

## 16.6 (보조) `WU-CC-F` — 주 비교군 제외

Wu의 centralized reference다.

```text
min J_WU_global
subject to:
  full coupled dynamics
  green constraints
  VSL constraints
```

```text
J_WU_global =
    T_u * sum_horizon urban_and_offramp_vehicles
  + T_f * sum_horizon (
      freeway_origin_queues
      + onramp_queues
      + sum_m sum_i L[m] * lambda_eff[m,i] * rho[m,i]
    )
  + control_variation_penalty(green, vsl)
```

Agent partition, coupling iteration과 Leader는 사용하지 않는다.

## 16.7 Controller 2: `PROPOSED-FOLLOWERS-ONLY`

> 2026-06-13 재정의. allocation module은 Leader의 net-inflow target을 입력으로 갖는
> coordination 기구이므로, Leader가 없는 mode에서는 module 자체를 제거한다.
> (구 정의 — module을 유지하고 objective를 균형+drain으로 퇴화 — 는 폐기.
> 구 정의 결과는 git 이력 6807ef4의 매트릭스에 보존.)

Distributed player 구조는 유지하되 upper-level Leader와 inflow-outflow allocation module을
모두 사용하지 않는다.

### Active controls

- phase green: allocation 기준점 없이 `[green_min, green_max]` 범위 자유 탐색
- signal offset
- ramp metering
- VSL

`inflow_outflow_allocation`은 결정하지 않는다. movement service는 plant 기본
saturation flow(green window 내)를 따른다 — Wu group과 동일한 비제어 fallback.

### Leaderless decision

- Leader candidate를 생성하지 않음
- `N_P_star`, `N_UF_star`를 전달하지 않음
- allocation module을 호출하지 않음 — green setpoint anchor 없음
- urban agents는 local objective(관측 큐·coupling 정보)로 phase green을
  `[green_min, green_max]`에서 직접 탐색하고 offset을 결정
- freeway agents는 local objective로 ramp metering 수준과 VSL을 결정
- remaining agent coordination loop(coupling 교환·iteration)는 proposed Stackelberg
  follower와 동일

이 mode는 fixed global state target을 가진 static coordinator가 아니라 genuinely leaderless
distributed controller로 정의한다.

## 16.8 Controller 3: `PROPOSED-STACKELBERG`

현재 제안한 full controller다.

### Leader

```text
U_L = [
  N_P_star,
  N_UF_star
]
```

- `N_P_star`: urban protected-network accumulation/coordination target
- `N_UF_star`: configured freeway/on-ramp coordination target
- 단위는 config와 report에서 명시

### Followers

- allocation module이 Leader target과 observed queue/storage를 movement service 및 green
  setpoint로 변환
- urban players가 green fine-tuning과 offset을 결정
- freeway players가 VSL과 ramp metering을 결정
- coupling variable을 교환하며 follower response를 갱신

### Leader objective

```text
J_L =
  sum_horizon[
      n_P(t)
    + n_F(t)
    + w_P * positive_part(n_P(t) - n_P_crit)
    + w_F * sum_m sum_i
        L[m] * lambda_eff[m,i](t)
        * positive_part(rho[m,i](t) - rho_crit[m])
  ]
  + w_L * L1_norm(U_L(t) - U_L(t-1))
```

Leader target 자체를 critical threshold로 사용하지 않는다. 각 target 후보에 대한 coupled
follower response를 위 system objective로 평가한다.

## 16.9 Controller 4: `PROPOSED-CENTRALIZED`

Proposed full authority를 하나의 centralized MPC에서 직접 최적화한다.

```text
U_CENTRALIZED = [
  movement_service_or_green,
  signal_offset,
  ramp_metering,
  vsl
]
```

```text
min J_PROPOSED_SYSTEM
subject to:
  full coupled urban-freeway dynamics
  movement/green feasibility
  offset bounds and smoothness
  ramp receiving and metering constraints
  VSL bounds and smoothness
  storage and vehicle conservation
```

이 controller에는:

- Leader target
- follower/player decomposition
- Nash/coupling iteration

이 없다. Full action sequence를 하나의 system objective에서 직접 결정한다.

`PROPOSED-CENTRALIZED`는 strict theoretical optimum이 아니라 현재 solver와 budget으로 얻은
centralized numerical reference로 표현한다.

## 16.10 핵심 Pairwise Comparison

Lower-is-better cost `J`에 대해 주 비교군 4개에서 다음 쌍을 본다.

```text
ProposedLeaderValue =
  J(PROPOSED-FOLLOWERS-ONLY)
  - J(PROPOSED-STACKELBERG)
```

Leader와 allocation coordination layer의 **결합** 추가 효과다. allocation module은
Leader target 없이는 정의되지 않으므로 이 쌍에서 둘은 분리되지 않는다 — 이 값을
"Leader 단독 효과"로 표현하지 않는다.

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

두 controller 모두 allocation이 없으므로 이 차이는 offset/ramp metering authority 추가와
agent 구현 차이를 함께 담는다. proposed control variable만의 순수 효과라고 부르지 않는다.

```text
FullPackageValue =
  J(WU-CD-F)
  - J(PROPOSED-STACKELBERG)
```

Wu distributed 대비 본 연구 full controller(Leader + allocation + offset + metering)의
전체 차이 — 주 headline 비교다.

보조 참고군을 실행한 경우의 쌍(`WuLeaderValue`, `WuCentralizationGap`,
`LeaderPackageDifference`)은 주 매트릭스에 포함하지 않고 별도 부록으로만 보고한다.

## 16.11 공정 비교 규칙

### Stage 1 성과지표와 delay accounting

Stage 1은 TTT/TTS만으로 controller 성능을 판정하지 않는다. 모든 controller에 대해 다음
성과지표 묶음을 함께 보고한다.

```text
TTT/TTS
total, urban and freeway delay
average delay per completed vehicle
network throughput and completed vehicles
terminal total vehicles and subsystem queues
```

Delay reference는 scenario와 seed별로 한 번만 계산하고 모든 controller에 공통으로 사용한다.
이는 no-control 또는 fixed-control simulation 결과가 아니라, 동일 demand, route, turning ratio와
free-flow travel time을 사용한 controller-independent reference다.

```text
total_delay(c) =
  total_ttt(c) - total_free_flow_reference_ttt

urban_delay(c) =
  urban_ttt(c) - urban_free_flow_reference_ttt

freeway_delay(c) =
  freeway_ttt(c) - freeway_free_flow_reference_ttt
```

Paired baseline `b`와 controller `c` 사이의 delay 개선은 다음과 같이 계산한다.

```text
delay_improvement_abs(b, c) =
  total_delay(b) - total_delay(c)

delay_improvement_pct(b, c) =
  100 * delay_improvement_abs(b, c) / total_delay(b)
```

`total_delay(b)`가 configured epsilon 이하인 low-delay case에서는 percentage를 `NA`로 두고
절대 delay 차이 `[veh*h]`를 주 지표로 사용한다. Aggregate accounting에서 음의 delay가 나오면
0으로 clamp하지 않고 free-flow reference 또는 queue accounting 오류로 판정한다.

```text
average_delay_per_completed_vehicle =
  total_delay / max(completed_vehicles, 1)
```

완료차량당 평균 delay는 throughput과 terminal queue를 반드시 함께 보고한다. Throughput을
낮추거나 terminal queue를 늘려 horizon 밖으로 지연을 미룬 결과는 delay 개선으로 인정하지
않는다.

### 모든 controller 공통

- plant, demand, initial state, seed와 simulation horizon
- control/prediction horizon
- available state information
- TTT/TTS와 terminal queue accounting
- free-flow reference와 delay accounting
- warm-up/evaluation interval

### Authority group 내부

Wu group 내부에서는 green/VSL bounds와 action set을 동일하게 사용한다.

Proposed group 내부에서는 공유하는 control(green, offset, metering, VSL)의 bounds와
action set을 동일하게 사용한다. `PROPOSED-FOLLOWERS-ONLY`는 정의상 allocation을
사용하지 않으며, `PROPOSED-STACKELBERG`/`PROPOSED-CENTRALIZED`는 동일한 allocation
bounds를 사용한다.

### Leader comparison

- `PROPOSED-FOLLOWERS-ONLY`와 `PROPOSED-STACKELBERG`의 차이는 Leader와
  allocation coordination layer 유무에 한정 — 그 외 plant·offset·metering·VSL 경로와
  agent coordination loop는 동일
- Leader가 없는 mode에서 숨은 fixed global target을 사용하지 않음
- evaluation 결과를 본 뒤 controller별 weight를 재튜닝하지 않음

### Centralized comparison

- centralized controller도 같은 physical authority와 constraints 사용
- solver evaluation budget과 convergence status를 함께 보고
- centralized 결과를 보장된 global optimum으로 표현하지 않음

## 16.12 Required Diagnostics

### Common

```text
controller_id
authority_group
leader_enabled
centralized
total_ttt
urban_ttt
freeway_ttt
free_flow_reference_total_ttt
free_flow_reference_urban_ttt
free_flow_reference_freeway_ttt
total_delay
urban_delay
freeway_delay
completed_vehicles
network_throughput
average_delay_per_completed_vehicle
terminal_total_vehicles
terminal_urban_vehicles
terminal_onramp_vehicles
terminal_freeway_vehicles
computation_time_sec
solver_evaluations
solver_converged
```

### Distributed

```text
agent_id
agent_local_objective
coupling_input
coupling_output
coupling_residual
coordination_iterations
```

### Leader

```text
leader_candidate_count
leader_selected_action
leader_objective
leader_action_smoothness
follower_response_objective
```

### Controls

```text
allocation_action
actual_phase_green
signal_offset
ramp_metering
vsl
```

## 16.13 Required Tests

```text
test_comparison_runner_exposes_primary_four_controllers
test_all_controllers_use_same_physical_plant

test_wu_group_uses_green_and_vsl_only
test_wu_cd_has_no_leader

test_proposed_followers_only_has_no_allocation_control
test_proposed_followers_only_has_no_hidden_global_target
test_proposed_followers_only_green_searched_within_bounds
test_proposed_pair_differs_by_leader_and_allocation_only
test_proposed_centralized_has_no_leader_or_agents

test_physical_on_offramp_coupling_remains_identical
test_first_mpc_action_only_is_applied
test_all_controllers_use_same_free_flow_delay_reference
test_delay_is_reported_for_total_urban_and_freeway
test_delay_improvement_is_paired_with_throughput_and_terminal_state
test_low_reference_delay_uses_absolute_difference
test_terminal_queue_is_reported
```

보조 참고군(`WU-MATCHED-STACKELBERG`, `WU-CC-F`) 관련 기존 테스트는 구현이 유지되는
동안 함께 유지한다.

## 16.14 Definition of Done

- 주 비교군 네 controller가 독립 mode로 실행됨
- `PROPOSED-FOLLOWERS-ONLY`가 allocation 없이 green 자유탐색 + offset + metering + VSL로
  동작함이 자동검사로 확인됨
- Wu group과 proposed group의 control authority가 명확히 분리됨
- centralized mode가 동일 authority와 plant를 사용함
- 모든 pairwise comparison의 해석 한계(특히 ProposedLeaderValue = Leader+allocation
  결합 효과)가 report에 기록됨
- TTT/TTS, delay, throughput과 terminal state가 하나의 성능 묶음으로 보고됨
- computation time과 convergence가 성능 지표와 함께 보고됨
