# Future Flow-Based Coupling Analysis Data Requirements

작성일: 2026-06-25

## 목적

현재 6/23 figure set은 controller별 성능과 actuator activation을 보여주지만, coordinated control의 핵심인 "urban-freeway interface에서 제어가 실제 교통류와 queue propagation을 어떻게 바꾸었는가"를 충분히 설명하지 못한다.

향후 분석에서는 다음 문장을 직접 검증할 수 있는 데이터를 simulation output에 남겨야 한다.

> On-ramp와 off-ramp interface에서 발생하는 flow-based coupling을 중심으로, 각 제어전략이 urban-freeway 간 교통류, queue propagation, spillback, freeway density, 그리고 urban/freeway TTT에 미치는 영향을 정량적으로 분석한다.

사용자가 최종적으로 의도한 더 간결한 분석 문장은 다음과 같다.

> On-ramp와 off-ramp interface에서 발생하는 coupling을 중심으로, 각 제어전략이 urban-freeway 간 교통류, queue propagation, spillback, freeway density, 그리고 urban/freeway TTT에 미치는 영향을 정량적으로 분석함.

즉, 단순히 "RM이 켜졌다", "green이 바뀌었다", "offset이 조정되었다"를 보여주는 것이 아니라, 제어 입력이 interface flow, queue, storage, spillback, density, TTT에 어떤 연쇄 효과를 만들었는지를 데이터로 추적해야 한다.

## 왜 추가 데이터가 필요한가

현재 raw output만으로는 다음과 같은 한계가 있다.

- `NO-CONTROL`, `WU-CD-F`, `PFO`, `P-Stack` 비교는 가능하지만, `RM only`, `signal only`, `RM + signal`, `RM + signal + offset`, `full coordination` 같은 clean ablation 결과가 없다.
- 따라서 "coordination synergy"를 엄밀하게 분해하기 어렵다.
- 일부 queue/load proxy는 controller별 logging coverage가 다르기 때문에 boundary/load exposure를 final fairness metric으로 쓰기 어렵다.
- Current figure는 activation 중심이라, actuator가 켜진 뒤 state와 performance가 어떻게 바뀌었는지 보여주는 effect chain이 약하다.

향후에는 controller 비교와 별도로 ablation-based coordination run을 설계하고, 모든 run에서 동일한 interface-level schema를 저장해야 한다.

## Required Ablation Variants

최소한 다음 controller variant를 같은 plant, 같은 demand, 같은 seed, 같은 horizon에서 저장해야 한다.

| Variant | 목적 |
|---|---|
| `NO-CONTROL` | 기준 |
| `SIGNAL-ONLY` | urban signal 단독 효과 |
| `RM-ONLY` | ramp metering 단독 효과 |
| `VSL-ONLY` | VSL 단독 효과 |
| `SIGNAL-RM` | signal과 RM의 interface coupling 효과 |
| `SIGNAL-RM-OFFSET` | offset coordination 추가 효과 |
| `PFO` | leader 없는 proposed distributed follower package |
| `P-STACK` | leader-follower hierarchy 전체 효과 |

가능하면 `P-STACK-ALLOCATION-ON/OFF`, `P-STACK-FALLBACK-ON/OFF`, `P-STACK-VSL-OFF`, `PFO-OFFSET-OFF`도 추가하면 coordination mechanism을 더 정확히 분해할 수 있다.

## Required Output Tables

### 1. `interface_flow_timeseries.csv`

On-ramp와 off-ramp interface에서 실제 흐름이 어떻게 결정되었는지 저장하는 핵심 table이다. 각 row는 `scenario-controller-seed-step-interface_id` 단위가 되어야 한다.

필수 column:

| Column | 설명 |
|---|---|
| `scenario` | scenario id |
| `controller_id` | controller 또는 ablation variant |
| `seed` | random seed |
| `step` | control step |
| `time_sec` | simulation time |
| `dt_sec` | step length |
| `interface_id` | 예: `R_D_E`, `R_F_W`, `OR_D_E`, `OR_F_W` |
| `interface_type` | `onramp` 또는 `offramp` |
| `direction` | `E` 또는 `W` |
| `urban_node` | 연결된 urban intersection |
| `freeway_segment` | 연결된 freeway segment |
| `desired_flow_veh_h` | demand 또는 desired off-ramp/on-ramp flow |
| `requested_flow_veh` | control 또는 plant가 요청한 vehicle count |
| `accepted_flow_veh` | 실제 interface를 통과한 vehicle count |
| `rejected_flow_veh` | storage/receiving 제약 등으로 거부된 vehicle count |
| `actual_flow_veh_h` | accepted flow를 veh/h로 환산한 값 |
| `flow_acceptance_ratio` | `accepted_flow_veh / requested_flow_veh` |
| `flow_shortfall_veh` | `requested_flow_veh - accepted_flow_veh` |
| `flow_shortfall_ratio` | shortfall ratio |

이 table은 "control이 flow를 조절했다"는 주장과 "off-ramp rejection 또는 on-ramp metering이 실제로 얼마나 발생했는가"를 직접 보여주기 위한 기본 자료이다.

### 2. `onramp_coupling_timeseries.csv`

On-ramp interface에서 urban queue, ramp queue, metering release, freeway receiving condition을 연결해서 저장한다.

필수 column:

| Column | 설명 |
|---|---|
| `ramp_id` | on-ramp id |
| `urban_approach_queue_start_veh` | control step 시작 시 on-ramp 접근 urban queue |
| `urban_approach_queue_end_veh` | step 종료 시 on-ramp 접근 urban queue |
| `urban_green_service_capacity_veh` | 해당 movement가 제공할 수 있는 service |
| `urban_green_release_request_veh` | urban side에서 ramp로 보내려 한 차량 |
| `urban_green_release_actual_veh` | 실제 ramp로 이동한 차량 |
| `urban_green_shortfall_veh` | urban side service shortfall |
| `ramp_queue_start_veh` | ramp queue 시작값 |
| `ramp_queue_end_veh` | ramp queue 종료값 |
| `ramp_storage_capacity_veh` | ramp storage capacity |
| `ramp_storage_headroom_veh` | 남은 storage |
| `metering_rate_selected_veh_h` | 선택된 metering rate |
| `metering_release_request_veh` | metering 기준 방출 요청 차량 |
| `metering_release_actual_veh` | 실제 freeway로 방출된 차량 |
| `metering_shortfall_veh` | metering request 대비 방출 부족 |
| `merge_receiving_capacity_veh` | freeway merge receiving capacity |
| `merge_receiving_factor` | receiving factor |
| `upstream_freeway_density` | ramp upstream density |
| `downstream_freeway_density` | ramp downstream density |
| `freeway_speed_near_ramp` | ramp 인근 freeway speed |
| `freeway_flow_near_ramp` | ramp 인근 freeway flow |
| `vsl_near_ramp_km_h` | ramp 인근 VSL |
| `onramp_spillback_violation_veh` | ramp/urban spillback violation |
| `spillback_flag` | spillback 발생 여부 |

이 table은 다음 효과 chain을 그리기 위한 것이다.

```text
metering / green service
 -> ramp release
 -> ramp queue and urban approach queue
 -> freeway density / speed / flow
 -> freeway TTT and total TTT
```

### 3. `offramp_coupling_timeseries.csv`

Off-ramp interface에서 freeway outflow, off-ramp storage, downstream urban receiving condition, freeway spillback을 연결해서 저장한다.

필수 column:

| Column | 설명 |
|---|---|
| `offramp_id` | off-ramp id |
| `offramp_desired_arrival_veh` | freeway에서 off-ramp로 빠지려는 차량 |
| `offramp_selected_arrival_veh` | controller 또는 plant가 선택/허용한 arrival |
| `offramp_arrival_accepted_veh` | 실제 off-ramp storage로 들어간 차량 |
| `offramp_arrival_rejected_veh` | storage/receiving 문제로 거부된 차량 |
| `offramp_storage_start_veh` | off-ramp storage 시작 occupancy |
| `offramp_storage_end_veh` | off-ramp storage 종료 occupancy |
| `offramp_storage_capacity_veh` | storage capacity |
| `offramp_storage_headroom_veh` | storage headroom |
| `offramp_occupancy_ratio` | occupancy/capacity |
| `downstream_urban_receiving_capacity_veh` | urban side receiving capacity |
| `downstream_urban_service_actual_veh` | urban으로 실제 빠져나간 차량 |
| `downstream_urban_queue_veh` | 연결 movement queue |
| `offramp_blocked_flow_veh` | blocked flow |
| `mainline_held_or_blocked_veh` | off-ramp storage 때문에 본선에 남은 차량 |
| `upstream_freeway_density` | off-ramp upstream density |
| `downstream_freeway_density` | off-ramp downstream density |
| `offramp_spillback_flag` | off-ramp spillback 발생 여부 |
| `offramp_spillback_violation_veh` | spillback violation vehicle count |

이 table은 "off-ramp가 urban receiving 부족으로 막혀 freeway로 spillback을 유발하는가"를 직접 분석하기 위한 것이다.

### 4. `control_action_timeseries_normalized.csv`

제어 입력을 actuator별로 통일된 long format으로 저장한다.

필수 column:

| Column | 설명 |
|---|---|
| `scenario` | scenario |
| `controller_id` | controller/ablation |
| `step` | control step |
| `time_sec` | time |
| `agent_id` | freeway segment 또는 urban intersection agent |
| `actuator_type` | `rm`, `vsl`, `green`, `offset`, `leader_target` |
| `actuator_id` | ramp id, segment id, phase id 등 |
| `value` | 제어값 |
| `default_value` | no-control/default value |
| `delta_from_default` | default 대비 변화량 |
| `activation_flag` | activation 여부 |
| `lower_bound` | feasible lower bound |
| `upper_bound` | feasible upper bound |
| `binding_flag` | bound binding 여부 |

이 table은 actuator별 activation이 아니라, actuator 변화가 state response와 연결되도록 long-format merge를 쉽게 하기 위한 것이다.

### 5. `state_response_timeseries_normalized.csv`

제어 효과를 해석하기 위한 주요 state를 long format으로 저장한다.

필수 state group:

| State group | Required variables |
|---|---|
| freeway | segment density, speed, flow, lane count, receiving factor |
| on-ramp | ramp queue, release, storage headroom, spillback flag |
| off-ramp | storage occupancy, accepted/rejected arrival, blocked flow |
| urban | movement queue, storage occupancy, departure/service |
| boundary | boundary queue/load, accepted/rejected boundary inflow if applicable |
| global | urban TTT, freeway TTT, total TTT, completed vehicles, terminal vehicles |

최소 column:

```text
scenario, controller_id, seed, step, time_sec,
entity_type, entity_id, variable, value, unit
```

### 6. `coupling_effect_summary.csv`

Run 종료 후 interface별, controller별 effect metric을 요약한다.

필수 metric:

| Metric | 설명 |
|---|---|
| `total_ttt_saved_vs_no_control_veh_h` | no-control 대비 TTT saving |
| `freeway_ttt_saved_vs_no_control_veh_h` | freeway TTT saving |
| `urban_ttt_saved_vs_no_control_veh_h` | urban TTT saving |
| `completed_gain_vs_no_control_veh` | completed vehicle 증가 |
| `terminal_reduction_vs_no_control_veh` | terminal vehicle 감소 |
| `ramp_queue_exposure_veh_h` | ramp queue exposure |
| `urban_onramp_queue_exposure_veh_h` | on-ramp approach urban queue exposure |
| `offramp_storage_exposure_veh_h` | off-ramp storage exposure |
| `boundary_queue_exposure_veh_h` | boundary queue exposure |
| `onramp_shortfall_veh` | on-ramp release/service shortfall |
| `offramp_rejection_veh` | off-ramp rejected vehicles |
| `spillback_duration_sec` | spillback duration |
| `mean_freeway_density_near_interface` | interface 인근 density |
| `max_freeway_density_near_interface` | interface 인근 max density |

## Required Figures Enabled by These Data

### 1. Interface Effect Chain Figure

문헌에서 자주 쓰는 time-aligned control-response 구조이다.

```text
panel 1: RM / VSL / green / offset control input
panel 2: accepted/rejected interface flow
panel 3: ramp queue / off-ramp storage / urban approach queue
panel 4: freeway density / speed near interface
panel 5: urban TTT, freeway TTT, total TTT saving
```

이 figure는 "control이 activate되었다"가 아니라 "activate된 control이 interface flow와 queue propagation을 어떻게 바꾸었는가"를 보여준다.

### 2. On-Ramp Coupling Effect Figure

On-ramp별로 다음 흐름을 보여준다.

```text
urban green service
 -> on-ramp approach queue
 -> ramp metering release
 -> ramp queue
 -> freeway density/speed near merge
 -> freeway TTT
```

PFO와 P-Stack의 차이를 보여줄 때 특히 중요하다.

### 3. Off-Ramp Coupling Effect Figure

Off-ramp별로 다음 흐름을 보여준다.

```text
freeway off-ramp demand
 -> off-ramp accepted/rejected arrival
 -> off-ramp storage occupancy
 -> downstream urban receiving/service
 -> mainline blocked/held vehicles
 -> freeway density and TTT
```

이 figure는 off-ramp spillback이 freeway breakdown에 미치는 영향을 설명하기 위해 필요하다.

### 4. FD/MFD Operating-Point Shift Figure

Freeway FD 또는 urban MFD 평면에서 no-control, ablation variants, PFO, P-Stack trajectory를 비교한다.

```text
freeway: density-flow trajectory
urban: accumulation-production trajectory
```

이는 control이 system operating point를 더 좋은 영역으로 이동시켰는지 보여준다.

### 5. Ablation-Based Coordination Effect Figure

각 actuator 조합의 incremental effect를 보여준다.

```text
No control
Signal only
RM only
VSL only
Signal + RM
Signal + RM + Offset
PFO
P-Stack
```

추천 metric:

- Total TTT saved
- Freeway TTT saved
- Urban TTT saved
- Completed vehicle gain
- Terminal vehicle reduction
- Ramp/on-ramp/off-ramp queue exposure
- Spillback duration

이 figure가 있어야 "coordination이 단일 actuator보다 더 낫다"는 주장을 엄밀하게 할 수 있다.

### 6. Synergy Index Figure

다음과 같은 coordination synergy index를 계산한다.

```text
Synergy(Signal, RM)
  = Gain(Signal + RM) - Gain(Signal only) - Gain(RM only)

Synergy(full)
  = Gain(full coordination) - sum(single-actuator gains)
```

이 값이 양수이면 actuator 조합이 단순 합 이상의 효과를 만든다는 근거로 사용할 수 있다. 단, 이 분석은 반드시 같은 scenario/seed/horizon에서 수행해야 한다.

## Marginal Cost / Shadow Price Analysis

Coupling 분석은 단순히 "어느 방향으로 flow가 움직였는가"에서 끝나면 약하다. Interface별로 차량 1대를 더 통과시키거나 억제했을 때 network objective가 얼마나 변하는지 계산하면, coordinated control이 왜 특정 on-ramp/off-ramp flow를 선택했는지 더 설득력 있게 설명할 수 있다.

### 기본 정의

각 interface `i`와 control step `t`에 대해 marginal cost를 다음처럼 정의한다.

```text
MC_i(t) = Delta J(t) / Delta q_i(t)
```

여기서:

- `J(t)`는 rollout objective, global TTT, 또는 TTT-compatible objective이다.
- `q_i(t)`는 interface `i`에서 추가로 통과시킨 차량 수, 방출 차량 수, 또는 accepted flow이다.
- 단위는 `veh-h / veh` 또는 `sec / veh`로 표현할 수 있다.

예를 들어 on-ramp에서 metering release를 `Delta q`만큼 늘렸을 때 objective가 `Delta J`만큼 변하면:

```text
MC_onramp_i(t) = [J(q_i + Delta q) - J(q_i)] / Delta q
```

이 값이 양수이면 해당 interface에서 차량을 추가로 방출하는 것이 network cost를 증가시키는 방향이고, 음수이면 추가 방출이 queue/throughput 관점에서 이득일 수 있다.

### On-ramp marginal cost

On-ramp에서는 다음 marginal cost를 저장하거나 계산해야 한다.

| Quantity | 의미 |
|---|---|
| `mc_ramp_release_veh_h_per_veh` | ramp에서 freeway로 차량 1대를 더 방출할 때 objective 변화 |
| `mc_urban_to_ramp_veh_h_per_veh` | urban approach에서 ramp로 차량 1대를 더 넘길 때 objective 변화 |
| `mc_metering_hold_veh_h_per_veh` | metering으로 차량 1대를 더 holding할 때 objective 변화 |
| `mc_ramp_queue_delay_sec_per_veh` | ramp queue에 차량 1대가 더 남을 때 delay cost |
| `mc_freeway_density_sec_per_veh` | 추가 ramp release가 freeway density/excess를 통해 만드는 cost |

이 분석이 있으면 다음 질문에 답할 수 있다.

- ramp queue가 큰데도 metering을 유지한 이유가 freeway density marginal cost 때문인가?
- 반대로 freeway density가 여유 있는데도 metering이 강하면 objective/search가 잘못된 것인가?
- P-Stack leader는 PFO보다 낮은 marginal-cost interface를 우선적으로 열고 있는가?

### Off-ramp marginal cost

Off-ramp에서는 다음 marginal cost가 필요하다.

| Quantity | 의미 |
|---|---|
| `mc_offramp_accept_veh_h_per_veh` | off-ramp 차량 1대를 urban side로 받아들일 때 objective 변화 |
| `mc_offramp_reject_veh_h_per_veh` | off-ramp 차량 1대를 거부하거나 본선에 남길 때 objective 변화 |
| `mc_offramp_storage_veh_h_per_veh` | off-ramp storage에 차량 1대가 더 쌓일 때 objective 변화 |
| `mc_mainline_blocking_veh_h_per_veh` | off-ramp spillback으로 본선 차량 1대가 영향을 받을 때 cost |
| `mc_urban_receiving_veh_h_per_veh` | downstream urban receiving을 1대 늘릴 때 objective 변화 |

이 분석이 있으면 off-ramp가 urban receiving 부족으로 freeway breakdown을 유발하는지, 또는 urban side를 보호하기 위해 off-ramp를 막는 것이 오히려 freeway TTT를 악화시키는지 정량적으로 볼 수 있다.

### Leader-level marginal cost

현재 6/23 raw output의 `decision_progress.csv`에는 P-Stack leader candidate별 `N_P_star`, `N_UF_star`, `objective`가 저장되어 있다. 따라서 현 데이터만으로도 coarse leader-level marginal cost는 계산할 수 있다.

```text
MC_NP(t)  ~= partial J / partial N_P_star
MC_NUF(t) ~= partial J / partial N_UF_star
```

해석:

- `MC_NP`는 protected network net inflow target 또는 accumulation-related target을 한 단위 바꿀 때 objective가 얼마나 변하는지 보여준다.
- `MC_NUF`는 freeway/on-ramp metering target을 한 단위 바꿀 때 objective가 얼마나 변하는지 보여준다.

단, 이것은 interface-level marginal cost가 아니라 leader target space에서의 coarse finite-difference 또는 local regression 값이다. Candidate 수가 적고 rejected candidate surface가 완전하지 않으므로, 논문에서는 "diagnostic marginal slope" 정도로 표현해야 한다.

### Required candidate-level logging for true marginal cost

True marginal cost를 계산하려면 각 decision step에서 선택 후보뿐 아니라 perturbation 후보들을 저장해야 한다.

필수 column:

| Column | 설명 |
|---|---|
| `scenario` | scenario id |
| `controller_id` | controller/ablation variant |
| `seed` | seed |
| `step` | control step |
| `candidate_id` | candidate id |
| `base_candidate_id` | perturbation 기준 candidate |
| `perturbed_entity_type` | `onramp`, `offramp`, `green`, `offset`, `vsl`, `leader_target` |
| `perturbed_entity_id` | ramp/offramp/intersection/segment id |
| `delta_flow_veh` | accepted/released flow perturbation |
| `delta_metering_rate_veh_h` | metering perturbation |
| `delta_green_sec` | green perturbation |
| `delta_offset_sec` | offset perturbation |
| `delta_vsl_km_h` | VSL perturbation |
| `objective_base` | base objective |
| `objective_candidate` | perturbed objective |
| `delta_objective_veh_h` | objective difference |
| `marginal_cost_veh_h_per_veh` | `delta_objective / delta_flow_veh` |
| `marginal_cost_sec_per_veh` | `3600 * marginal_cost_veh_h_per_veh` |
| `feasible_flag` | feasibility |
| `binding_constraint` | binding constraint if any |
| `spillback_violation_veh` | spillback violation |
| `terminal_vehicle_delta` | terminal vehicle change |
| `throughput_delta` | completed vehicle change |

### Recommended marginal cost figures

1. `Interface marginal cost heatmap`

```text
x-axis: time
y-axis: interface id
color: marginal_cost_sec_per_veh
```

이 figure는 어느 시점에 어떤 on-ramp/off-ramp interface가 비싼지 보여준다.

2. `Marginal cost vs queue pressure scatter`

```text
x-axis: ramp queue or off-ramp storage occupancy
y-axis: marginal cost
color: controller
marker: scenario
```

이 figure는 queue가 커질수록 marginal holding cost가 커지는지, 또는 freeway density가 높아질수록 release cost가 커지는지 보여준다.

3. `Selected control vs marginal cost`

```text
x-axis: marginal cost of release/admission
y-axis: selected release/admission flow
```

좋은 controller라면 marginal cost가 높은 interface를 덜 열고, marginal cost가 낮거나 queue holding cost가 큰 interface를 더 열어야 한다.

4. `On-ramp/off-ramp marginal cost decomposition`

```text
MC_total = MC_freeway_density + MC_ramp_queue + MC_urban_queue + MC_spillback + MC_terminal
```

이 decomposition은 "왜 metering을 줄였는가" 또는 "왜 off-ramp receiving을 늘렸는가"를 설명하기 위해 필요하다.

5. `Leader marginal slope over time`

현재 `decision_progress.csv`만으로도 만들 수 있는 diagnostic figure이다.

```text
panel 1: partial J / partial N_P_star
panel 2: partial J / partial N_UF_star
panel 3: selected N_P_star, N_UF_star
panel 4: realized TTT / terminal vehicles
```

이 figure는 leader가 어느 방향으로 target을 움직이는 것이 objective상 비싼지 보여준다.

## Logging Consistency Rules

1. 모든 controller와 ablation variant는 동일한 schema를 출력해야 한다.
2. 값이 없는 controller라도 column은 유지하고 `0`, `NaN`, 또는 `not_applicable` 규칙을 명확히 해야 한다.
3. Flow는 반드시 `veh`와 `veh/h`를 구분해서 저장해야 한다.
4. Queue와 storage는 start/end 값을 모두 저장해야 한다.
5. Accepted/rejected/shortfall은 vehicle count 기준으로 저장해야 한다.
6. TTT는 interval value와 cumulative value를 모두 저장해야 한다.
7. Boundary queue/load는 모든 controller에서 같은 정의로 저장해야 한다.
8. Interface id는 on-ramp/off-ramp/control/state table에서 동일해야 한다.
9. No-control baseline과 active controller는 같은 demand, seed, horizon을 사용해야 한다.
10. Figure용 post-processing에서 임의 proxy를 만들지 않도록, plant에서 직접 계산한 quantity를 저장해야 한다.

## Recommended First Experiment

처음에는 모든 scenario를 돌리기보다 Peak와 Incident에 대해 1800초 ablation smoke run을 수행하는 것이 좋다.

추천 순서:

1. `peak_demand`, 1800 s, fixed seed
2. `incident_or_capacity_drop`, 1800 s, fixed seed
3. 위 required tables 출력 확인
4. Interface effect chain figure 생성
5. Ablation incremental benefit figure 생성
6. 결과가 안정적이면 3600 s 또는 7200 s로 확장

## Final Note

앞으로 coordinated control의 핵심 주장은 단순 activation 비율이 아니라 다음 질문에 답해야 한다.

- On-ramp metering이 freeway density를 낮추는 동시에 ramp/urban queue를 얼마나 증가시켰는가?
- Signal green과 offset 조정이 ramp queue 또는 off-ramp storage를 실제로 얼마나 완화했는가?
- Off-ramp receiving failure가 freeway density와 TTT를 얼마나 악화시켰는가?
- P-Stack leader target이 PFO 대비 interface flow를 어떤 방향으로 이동시켰는가?
- Full coordination의 효과가 single-actuator 효과의 합보다 큰가?

이 질문들에 답할 수 있도록 위 table들을 future simulation output에 반드시 남겨야 한다.
