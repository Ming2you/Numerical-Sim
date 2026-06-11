# Next-Step Spillback-Aware Controller Proposal

## 0. 문서 상태

이 문서는 **현재 controller 구현과 검증이 끝난 뒤 수행할 차기 연구 단계**를 정리한 제안서다.

- 현재 controller의 사양이나 acceptance criteria를 변경하지 않는다.
- 현재 분석과 simulation을 먼저 완료하고 결과를 기준선으로 동결한다.
- 아래 controller는 별도 config/실험군으로 구현하여 현재 controller와 비교한다.
- 초기 구현부터 기존 controller를 덮어쓰지 않고 feature flag 또는 별도 class로 병행한다.

## 1. 연구 동기

현재 Leader는 도시 protected network의 목표 accumulation `N_P_star`와 freeway 유입 목표
`N_UF_star`를 결정한다. Leader objective는 `N_P_crit` 초과량을 penalty로 사용한다.

그러나 도시 network의 critical accumulation은 signal control, 수요의 공간 분포, 경로 분포,
network heterogeneity에 따라 달라질 수 있다. 따라서 하나의 고정된 `N_P_crit`를 모든 signal
control 방식에 공통으로 적용하면 재보정이 필요하거나 실제 spillback 위치를 늦게 발견할 수 있다.

Elouni et al. (2021)은 decentralized Nash bargaining controller의 disagreement point를
**링크 길이 절반에 수용할 수 있는 차량 수**로 설정하여 queue가 upstream intersection으로
spillback되는 것을 방지했다. 이 연구는 half-link storage 기준의 local phase control만으로도
protected network 전체 성능이 개선될 수 있음을 보였다.

본 제안은 이 기준을 그대로 재현하는 것이 아니라 다음 두 계층에 확장 적용한다.

1. Leader는 도시와 freeway 사이의 externality를 고려하여 도시의 aggregate inflow/outflow
   service target을 결정한다.
2. PSO allocation module은 movement flow를 간접적으로 green으로 환산하지 않고 phase green을
   직접 결정하며, half-link storage 초과와 queue 축적을 최소화한다.

참고 문헌:

> Elouni, M., Abdelghaffar, H. M., and Rakha, H. A. (2021).
> "Adaptive Traffic Signal Control: Game-Theoretic Decentralized vs. Centralized Perimeter Control."
> Sensors, 21(1), 274.

인용 시에는 Elouni et al.이 본 제안의 penalty 식이나 PSO를 직접 제안한 것이 아니라,
**half-link queue storage를 disagreement point로 사용한 설계 원칙**을 제공했다는 점을 명시한다.

## 2. Controller 역할 재정의

### 2.1 Leader: urban-freeway externality coordinator

Freeway에서 urban으로 이동하는 off-ramp demand는 route choice의 결과이므로 본 연구에서는
직접 제어하지 않는다.

```text
q_off = 측정 또는 예측되는 외생 disturbance
```

Leader는 예측된 `q_off`를 도시가 수용할 수 있도록 도시 network의 controllable inflow와
outflow service target을 결정한다.

```text
U_L = [
    Q_ext_in_star,
    Q_ext_out_star,
    N_UF_star
]
```

- `Q_ext_in_star [veh/h]`: 외부에서 urban으로 들어오는 controllable boundary inflow target
- `Q_ext_out_star [veh/h]`: urban에서 외부로 나가는 boundary outflow service target
- `N_UF_star [veh/h]`: urban에서 freeway로 진입시키는 총 metering target
- `q_off [veh/h]`: freeway에서 urban으로 들어오는 외생 off-ramp inflow

`N_UF_star`와 urban on-ramp outflow를 별도 목표로 중복 제어하지 않는다. Urban allocation과
freeway ramp-metering follower가 동일한 `N_UF_star`를 공유하도록 coupling한다.

### 2.2 Urban follower 및 PSO allocation module

Urban follower는 Leader가 결정한 aggregate target을 실제 phase green으로 구현한다.

```text
Leader aggregate flow targets
    -> PSO phase-green optimization
    -> movement service flows
    -> predicted link queues and storage
    -> final signal control
```

PSO가 만든 phase green을 다시 평균하거나 큰 폭으로 변경하지 않는다. Offset controller가
필요한 경우 green을 고정한 뒤 별도 단계에서 결정한다.

### 2.3 Freeway follower

Freeway follower는 기존과 같이 VSL과 ramp metering을 결정한다. 단, `N_UF_star`의 실현 가능성과
off-ramp receiving-space feedback을 Leader 및 urban follower와 공유한다.

## 3. Leader Objective 변경안

기본 objective에서 `N_P_star`와 고정 `N_P_crit` 초과 penalty를 제거한다. 대신 예측 horizon의
각 urban link에 대해 half-link storage 초과 차량을 직접 계산한다.

```text
C_l_storage = link l의 storage capacity [veh]
x_l(t)      = link l의 예측 차량 또는 queue [veh]

spill_l(t) = positive_part(x_l(t) - theta_l * C_l_storage)
theta_l    = 0.5  # 초기값
```

기본 Leader objective 후보:

```text
J_L = sum_over_horizon[
        n_P(t) + n_F(t)
        + w_spill * sum_l spill_l(t)
        + w_F * freeway_density_excess(t)
        + w_track * flow_target_infeasibility_veh(t)
        + w_L * leader_action_smoothness_veh(t)
      ]
```

기본 spillback 항은 `[veh]` 단위를 유지하도록 선형 positive-part를 사용한다. 제곱 penalty를
사용할 경우 단위가 `[veh^2]`가 되므로 별도 정규화와 weight 정의가 필요하다.

모든 movement queue를 단순 합산하면 같은 physical link의 storage가 중복 계상될 수 있다.
따라서 penalty는 movement별이 아니라 **physical link 또는 approach별로 한 번만** 계산한다.

Off-ramp receiving link는 freeway spillback과 직접 연결되므로 별도 가중치를 둘 수 있다.

```text
w_spill,l = w_offramp_receiving  if l is an off-ramp receiving link
            w_spill              otherwise
```

## 4. PSO 기반 Phase-Green Optimization

### 4.1 결정변수

현재 PSO의 movement service flow 대신 교차로별 phase green을 직접 결정변수로 사용한다.

```text
g = [g_1,p1, g_1,p2, ..., g_I,p1, g_I,p2]
```

각 교차로 `i`에서:

```text
sum_p g_i,p = cycle_i - lost_time_i
g_min_i,p <= g_i,p <= g_max_i,p
```

합계 제약을 항상 만족하도록 독립변수를 phase 수보다 하나 적게 두거나, 입자를 평가하기 전에
feasible simplex로 projection한다.

### 4.2 Movement service 예측

각 PSO particle의 phase green으로 movement별 service flow와 다음 queue를 계산한다.

```text
service_m(g) = min(
    saturation_m * g_phase(m) / cycle,
    available_queue_m / T_pred,
    downstream_receiving_m / T_pred
)

x_hat_m(k+1) = max(
    0,
    x_m(k) + T_pred * (arrival_m - service_m(g))
)
```

현재 queue에서 service만 차감하지 않고 prediction horizon 동안의 예상 arrival를 반드시
포함한다. `arrival_m`은 측정값, demand forecast, upstream delayed release를 사용하며 미래 정보를
사용할 수 없으면 직전 측정값을 hold한다.

Movement queue는 physical link/approach 단위로 집계한 뒤 storage capacity와 비교한다.

### 4.3 PSO objective

PSO의 기본 목적은 queue를 단순히 균등화하는 것이 아니라:

1. queue 축적을 줄이고,
2. half-link storage 초과를 우선 방지하며,
3. Leader의 aggregate inflow/outflow target을 구현하고,
4. green의 급변을 억제하는 것이다.

단위를 vehicle-equivalent로 맞춘 기본 objective 후보:

```text
J_PSO =
    w_queue * sum_l x_hat_l
  + w_spill * sum_l positive_part(x_hat_l - theta_l * C_l_storage)
  + w_in * T_pred * abs(Q_ext_in(g) - Q_ext_in_star)
  + w_out * T_pred * abs(Q_ext_out(g) - Q_ext_out_star)
  + w_UF * T_pred * abs(Q_on(g) - N_UF_star)
  + w_green * T_pred
      * sum_p [s_phase(p) / cycle] * abs(g_p - g_p_previous)
  + w_balance * J_balance
```

`J_balance`는 기존 `B_in/B_out`을 보조항으로 유지할 수 있다. 모든 queue가 동일하게 높은
상태를 좋은 해로 판단하지 않도록 queue 및 spillback 항보다 낮은 우선순위를 둔다.

Half-link 기준은 hard constraint가 아니라 soft constraint로 구현한다.

```text
x_hat_l <= theta_l * C_l_storage + slack_l
slack_l >= 0
```

과포화 상태에서는 모든 링크를 50% 이하로 유지하는 feasible solution이 존재하지 않을 수 있다.
이때 PSO는 총 slack과 spillback 위치를 최소화해야 하며, infeasible 상태를 숨기지 않고 진단한다.

## 5. 구현 원칙

1. 현재 controller 결과를 commit/tag와 재현 가능한 config로 먼저 동결한다.
2. `LeaderAction`의 변경은 별도 action type 또는 controller mode로 구현한다.
3. 기존 allocation module을 즉시 제거하지 않고 새 `PhaseGreenPSOAllocation`과 병행한다.
4. `q_off`는 decision variable이 아닌 forecast disturbance로 유지한다.
5. signal phase 합계, min/max green, demand availability, downstream receiving capacity를 particle
   평가 과정에서 모두 적용한다.
6. PSO 최종 green이 plant에 그대로 적용되는지 검증한다.
7. link storage를 movement마다 중복 계산하지 않는다.
8. 모든 flow는 `[veh/h]`, horizon 변환량과 queue는 `[veh]`, green은 `[s]`로 명시한다.
9. `theta=0.5`를 기본값으로 두되 `0.5/0.6/0.7` 민감도 분석을 수행한다.

## 6. 구현 순서

### Step 1. 현재 controller 기준선 동결

- 현재 controller의 최종 simulation과 review를 완료한다.
- 사용 config, random seed, demand, 결과 artifact를 고정한다.
- current architecture와 next-step architecture의 경계를 문서화한다.

### Step 2. Link-storage forecast 계층 추가

- physical link별 `C_l_storage`, `x_l`, predicted arrival/service를 정의한다.
- movement queue를 physical link로 중복 없이 집계한다.
- half-link exceedance와 off-ramp receiving-space metric을 추가한다.

### Step 3. 새 Leader mode 구현

- `N_P_star` 대신 `Q_ext_in_star`, `Q_ext_out_star`, `N_UF_star` 후보를 생성한다.
- predicted `q_off`를 disturbance로 넣어 coupled horizon을 평가한다.
- `N_P_crit` 없이 link-storage spillback objective를 계산한다.

### Step 4. Direct phase-green PSO 구현

- phase green을 PSO particle로 정의한다.
- green별 movement service와 arrival 포함 queue forecast를 계산한다.
- spillback, queue, target tracking, smoothness objective를 적용한다.
- 기존 flow-to-green 변환과 same-phase movement 평균 단계를 제거한다.

### Step 5. Coupled follower 연결

- urban PSO와 freeway follower가 동일한 `N_UF_star` 및 receiving-space 정보를 사용한다.
- urban/freeway response가 Leader horizon 안에서 실제 coupled plant를 통해 평가되는지 확인한다.

### Step 6. 단위 및 불변식 테스트

- phase green 합계와 min/max green 보존
- vehicle conservation
- movement-to-link 집계 중복 없음
- `q_off`가 제어변수로 변경되지 않음
- arrival 증가 시 predicted queue가 증가함
- green 증가 시 해당 movement service가 비감소함
- half-link 초과 링크에 green을 더 배정할 유인이 생김
- PSO 출력 green과 plant 적용 green이 동일함

### Step 7. 비교 simulation

동일 demand, random seed, horizon, plant model을 사용하여 다음 실험군을 비교한다.

| Case | Leader | Urban allocation |
|---|---|---|
| A | 현재 `N_P_star`, `N_UF_star` | 현재 movement-flow PSO + balance |
| B | 새 aggregate `Q_in/Q_out`, `N_UF_star` | 현재 allocation |
| C | 현재 Leader | 새 direct phase-green spillback PSO |
| D | 새 aggregate `Q_in/Q_out`, `N_UF_star` | 새 direct phase-green spillback PSO |
| E | Leader 없음 | Elouni-inspired local half-link phase controller |

Case B와 C는 개선 원인이 Leader 변경인지 PSO 변경인지 분리한다. Case E는 urban-freeway
externality를 조정하는 Leader가 실제로 추가 이득을 만드는지 검증한다.

## 7. 평가 지표

### System performance

- total TTT/TTS
- urban TTT/TTS
- freeway TTT/TTS
- throughput
- controller computation time

### Spillback 및 storage

- `sum_l positive_part(x_l - 0.5*C_l_storage)`의 시간 누적값
- half-link threshold 초과 link 수와 step 수
- maximum storage occupancy ratio
- off-ramp receiving-link occupancy
- off-ramp blocked/rejected vehicles

### Leader target tracking

- `Q_ext_in_actual - Q_ext_in_star`
- `Q_ext_out_actual - Q_ext_out_star`
- `Q_on_actual - N_UF_star`
- target infeasible step 수

### Control activation

- signal green 변화량
- ramp metering active steps
- VSL active steps
- urban/freeway coupling residual

## 8. 연구 가설

1. Direct phase-green PSO는 current balance-only PSO보다 half-link exceedance와 spillback을 줄인다.
2. Aggregate `Q_in/Q_out` Leader는 off-ramp inflow 증가 전에 urban receiving space를 확보한다.
3. Leader의 추가 효과는 urban-only demand보다 urban-freeway coupling이 강한 scenario에서 크다.
4. Case D가 Case E보다 개선되지 않는다면 Leader의 externality coordination 효과가 입증되지
   않은 것이므로 Leader 구조를 단순화하거나 제거하는 결론도 허용한다.

## 9. 완료 기준

차기 controller는 다음 조건을 모두 만족할 때 구현 완료로 판단한다.

- 기존 controller를 재현 가능하게 유지한다.
- route choice 또는 off-ramp demand를 직접 제어하지 않는다.
- vehicle conservation과 signal feasibility test를 통과한다.
- PSO가 선택한 phase green이 변환 손실 없이 plant에 적용된다.
- 현재 controller 대비 total TTT/TTS와 spillback 지표를 동일 조건에서 비교한다.
- total TTT/TTS 개선과 spillback 감소가 서로 trade-off인 경우 두 결과를 모두 보고한다.
- Leader가 없는 Case E를 포함하여 Leader의 필요성을 정량적으로 평가한다.

