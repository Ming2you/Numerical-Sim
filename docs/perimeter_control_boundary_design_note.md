# Perimeter/Leader Boundary Design Note

## 목적

이 메모는 `PROPOSED-STACKELBERG`에서 leader가 선택하는 `N_P_star`, `N_UF_star`의 후보 boundary와 의미론을 재검토하기 위한 논의 자료다.

현재 질문은 다음이다.

```text
Leader가 follower response를 보고 objective를 최소화하는데,
왜 closed-loop Total TTT가 follower-only보다 나빠지는가?
N_P / N_UF candidate boundary 또는 target semantics가 잘못된 것인가?
```

이 문서는 확정 spec이 아니라, perimeter control 문헌 조사 및 다른 AI/리뷰어 검토를 위한 working hypothesis다.

## 현재 관찰

최근 smoke run:

```text
scenario: low_demand
horizon: 360 s
controllers: PROPOSED-FOLLOWERS-ONLY, PROPOSED-STACKELBERG
relaxed_quantized_controls: true
relaxed_fast_mode: true
```

결과:

| Controller | Total TTT/TTS | Total Delay | Freeway TTT | Urban TTT |
|---|---:|---:|---:|---:|
| `PROPOSED-FOLLOWERS-ONLY` | 33.729 | 3.562 | 11.355 | 22.374 |
| `PROPOSED-STACKELBERG` | 36.293 | 6.126 | 9.754 | 26.540 |

해석:

- Stackelberg는 freeway TTT를 줄였다.
- 그러나 urban TTT가 더 크게 증가하여 total TTT가 악화되었다.
- 따라서 leader/allocation layer가 freeway를 보호하는 대신 urban 쪽에 더 큰 비용을 만든 것으로 보인다.

Stackelberg selected leader target:

```text
step 0: N_P_star = 500.47, N_UF_star = 6000
step 1: N_P_star = 500.47, N_UF_star = 6000
```

하지만 realized protected accumulation:

```text
step 0: N_P = 112.2
step 1: N_P = 181.7
```

즉 현재 `N_P_star` 후보 하한이 realized/current `N_P`보다 훨씬 높다.

## 현재 구현상 의심 지점

### 1. `N_P_star` candidate boundary가 `N_P_crit` 주변에 고정됨

현재 leader candidate는 대체로 calibrated `N_P_crit` 주변 band에서 생성된다.

```text
N_P_candidate_lower ~= 0.9 * N_P_crit
N_P_candidate_upper ~= 1.05 * N_P_crit
```

이 방식은 congestion regime에서는 자연스럽지만, low/medium demand처럼 현재 `N_P(k)`가 낮은 경우에는 문제가 된다.

예:

```text
current N_P ~= 112
candidate lower ~= 500
```

그러면 leader가 평가할 수 있는 모든 candidate가 "현재 도시 누적보다 훨씬 높은 target"이 된다.

### 2. `N_P_star`가 upper bound가 아니라 tracking target처럼 동작함

수식상 leader objective는 다음 구조에 가깝다.

```text
J_L = sum_horizon[
    n_P(t, follower response)
  + n_F(t, follower response)
  + w_P * positive_part(n_P(t) - n_P_crit)
  + w_F * density_exceedance
  + w_L * leader_smoothness
]
```

여기서 `n_P_crit` 또는 `N_P_star`는 "초과하면 안 되는 critical reference / upper bound"에 가까운 의미다.

그런데 urban follower의 feedback에서는 `N_P_star`가 다음처럼 tracking target 역할을 할 수 있다.

```text
error = N_P_star - current_N_P
target_net_inflow = error / feedback_horizon
```

이 경우:

```text
current_N_P < N_P_star
```

이면 positive net-inflow가 허용되거나 유도된다. 즉 도시가 이미 비어 있어도 leader target까지 도시를 채우는 방향이 생길 수 있다.

### 3. `N_UF_star` candidate가 freeway TTT 감소 쪽으로 치우칠 수 있음

smoke에서 Stackelberg는 `N_UF_star = 6000`을 선택했다.

이는 사실상 ramp metering을 강하게 풀어 freeway 유입을 많이 허용하는 쪽이다. 이 선택은 freeway TTT를 줄일 수 있지만, on-ramp 접근부 및 urban side queue를 증가시킬 수 있다.

따라서 `N_UF_star`도 단순 wide range `[0, max]`가 아니라:

```text
previous N_UF_star
current feasible release
no-meter release
queue-safe release
freeway-congestion-safe release
```

주변 후보를 포함해야 할 수 있다.

### 4. Nash convergence가 낮음

최근 smoke에서 Stackelberg의 solver convergence는 `0.0`이었다.

따라서 leader가 평가한 response는 완전한 Nash equilibrium이라기보다 non-converged best-so-far follower response에 가깝다. 이 경우 candidate ranking이 실제 closed-loop 성능과 어긋날 위험이 있다.

## 수정 방향 후보

## Option A: `N_P_star` candidate에 current state를 반드시 포함

가장 보수적인 수정이다.

후보 집합에 다음 값을 강제로 포함한다.

```text
current_N_P
previous_N_P_star
N_P_crit
current_N_P +/- local_margin
min(current_N_P + growth_cap, N_P_crit)
```

예시:

```text
N_P_lower = max(0, current_N_P - margin_down)
N_P_upper = min(1.05 * N_P_crit, current_N_P + growth_cap)
```

장점:

- 현재 상태와 동떨어진 target만 평가하는 문제를 막는다.
- low/medium demand에서 불필요하게 urban accumulation을 높이는 선택을 줄일 수 있다.
- 기존 leader structure를 크게 바꾸지 않는다.

단점:

- `N_P_star`가 tracking target처럼 남아 있으면, 여전히 일부 상황에서 도시를 채우는 동작이 생길 수 있다.

## Option B: `N_P_star`를 asymmetric ceiling으로 해석

더 본질적인 수정이다.

Urban follower feedback을 다음처럼 바꾼다.

```text
if current_N_P > N_P_star:
    target_net_inflow = negative value  # 도시 누적을 줄임
else:
    target_net_inflow = 0 or neutral    # 도시를 일부러 채우지 않음
```

즉 `N_P_star`는 "도달해야 하는 목표"가 아니라 "넘지 말아야 할 상한"이다.

장점:

- perimeter/MFD control의 critical accumulation 해석과 더 잘 맞을 가능성이 높다.
- low demand에서 도시를 일부러 채우는 비직관적 동작을 막는다.
- 수식의 `positive_part(n_P - n_P_crit)`와 잘 맞는다.

단점:

- 기존 allocation module이 `N_P_star` tracking을 전제로 작성되어 있다면, 관련 green/allocation heuristic을 같이 재검토해야 한다.
- 너무 보수적으로 만들면 freeway 유입 조절이 약해질 수 있다.

## Option C: `N_P_star`를 target과 ceiling으로 분리

변수를 분리한다.

```text
N_P_ref      : follower가 참고하는 soft target
N_P_ceiling  : leader objective의 critical upper bound
```

또는:

```text
N_P_star_semantics:
  - tracking_target
  - ceiling
```

장점:

- 수식/구현 의미 충돌을 줄인다.
- 실험적으로 tracking vs ceiling을 ablation하기 쉽다.

단점:

- leader decision dimension 또는 config complexity가 증가한다.
- 논문 설명이 복잡해질 수 있다.

## Option D: `N_UF_star` candidate를 operational release 중심으로 재구성

현재 `N_UF_star` 후보는 broad range에서 생성되며, 저수요 smoke에서 max candidate `6000`이 선택되었다.

후보를 다음 anchor 기반으로 구성할 수 있다.

```text
N_UF_candidates =
  previous_N_UF_star
  actual_no_meter_release
  current_feasible_release
  queue_safe_release
  congestion_safe_release
  small local perturbations around these anchors
```

해석:

- `N_UF_star`는 exact target이라기보다 ramp release ceiling 또는 aggregate metering ceiling으로 볼 수 있다.
- demand가 부족하거나 queue가 없으면 목표 미달은 infeasible이 아니라 자연스러운 결과다.

장점:

- unrealistic max release candidate가 leader objective를 장악하는 것을 줄인다.
- ramp/on-ramp queue와 freeway density 사이의 trade-off를 더 안정적으로 탐색할 수 있다.

단점:

- feasible release 추정이 틀리면 후보 공간이 너무 좁아질 수 있다.

## 추천 우선순위

현재 증거 기준으로는 다음 순서가 가장 안전해 보인다.

```text
1. N_P candidate에 current_N_P와 previous_N_P_star를 반드시 포함한다.
2. N_P lower bound를 0.9 * N_P_crit 고정에서 current-state-aware bound로 바꾼다.
3. Urban follower의 N_P feedback을 asymmetric ceiling 방식으로 바꾼다.
4. N_UF candidate를 no-meter/current-feasible/previous anchor 중심으로 재구성한다.
5. 새 leader objective term breakdown으로 360 s / 720 s smoke를 재검증한다.
```

## 문헌 조사 질문

다른 AI/리뷰어에게 다음을 확인시키면 좋다.

### Perimeter control / MFD

1. Perimeter control에서 critical accumulation `N_crit`은 일반적으로 tracking target인가, upper bound/operating point인가?
2. Low demand 또는 under-saturated regime에서 controller가 `N_crit`까지 accumulation을 증가시키는 것이 정당화되는가?
3. MFD-based gating에서 `N < N_crit`일 때 inflow를 적극적으로 늘리는 전략이 쓰이는가, 아니면 control을 neutral하게 두는가?
4. Accumulation control law가 symmetric feedback인지, asymmetric feedback인지 사례를 확인할 것.

### Integrated freeway-urban control

1. Freeway ramp metering target과 urban perimeter target을 동시에 쓰는 경우, urban accumulation target이 "desired setpoint"인지 "capacity/constraint"인지 확인할 것.
2. Ramp metering aggregate target `N_UF_star`는 exact equality target인가, ceiling constraint인가?
3. Freeway TTT 감소와 urban TTT 증가의 trade-off를 objective에서 어떻게 조정하는지 확인할 것.

### Stackelberg / bilevel control

1. Leader가 follower best response를 평가하더라도, follower response가 non-converged일 때 objective ranking이 어떻게 왜곡될 수 있는지 확인할 것.
2. Leader candidate set이 현재 state를 포함하지 않을 때 local MPC 성능이 악화되는 사례가 있는지 확인할 것.
3. Critical reference와 follower tracking target을 분리하는 것이 일반적인지 확인할 것.

## 검증 계획

각 option을 반영한 뒤 최소 다음 smoke를 비교한다.

```text
scenario: low_demand, medium_demand, peak_demand
horizon: 360 s and 720 s
controllers:
  - PROPOSED-FOLLOWERS-ONLY
  - PROPOSED-STACKELBERG
metrics:
  - Total TTT
  - Total Delay
  - Urban TTT
  - Freeway TTT
  - Throughput
  - Terminal total vehicles
  - N_P_star vs realized N_P
  - N_UF_star vs actual metering release
  - leader objective term breakdown
  - Nash convergence/residual
```

Pass 판단은 아직 하지 않는다. 먼저 다음 현상이 사라지는지 본다.

```text
low/medium demand에서:
  current_N_P << N_P_star
  urban TTT 증가
  freeway TTT 소폭 감소
  total TTT 악화
```

이 현상이 줄어들면 boundary/semantics 수정 방향이 타당하다고 볼 수 있다.
