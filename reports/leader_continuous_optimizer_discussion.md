# Leader Continuous Optimizer Discussion

작성일: 2026-06-21

## 배경

최근 진단의 핵심 질문은 `PROPOSED-STACKELBERG`가 global TTT-compatible
leader objective를 사용하면서도 왜 `PROPOSED-FOLLOWERS-ONLY`보다 나빠질 수
있는가였다. 특히 peak 1800 s fallback-off run에서 P-Stack은 초반 8개
control step 동안 반복적으로 `N_P_star ~= 3220`, `N_UF_star = 6000`을
선택했고, PFO보다 Total TTT가 커졌다.

이 현상은 단순히 allocation module 유무만으로 설명하기 어렵다. 논의와
진단 결과, 다음 원인이 동시에 작동할 가능성이 크다.

## 현재까지의 주요 결론

### 1. Follower objective alignment

Follower의 heuristic은 최종 선택 규칙이 아니라 후보 생성기로만 쓰는 것이
맞다. 최종 선택은 TTT/TTS-compatible objective argmin이어야 한다.

이 원칙은 freeway follower의 ramp metering/VSL, urban follower의 green
time/offset, WU-CD-F, PFO, P-Stack 모두에 적용되어야 한다.

### 2. Boundary queue와 hidden storage

Boundary queue, movement queue, urban link storage가 Total TTT 또는 leader
response objective 밖으로 빠지면 controller가 차량을 외부/경계에 숨기는
해를 고를 수 있다.

따라서 leader objective에는 final Total TTT accounting과 맞는 queue/storage
coverage가 필요하다. 최근 수정에서는 `all_urban_halfcap` MFD/storage guard를
추가해 boundary movement queue와 urban link occupancy가 50% reference cap을
넘는 경우 비용에 들어가도록 했다. 이때 `mfd_boundary_queue_capacity_veh`는
penalty reference일 뿐 plant queue clipping에는 사용하지 않는다.

### 3. MFD/storage penalty의 역할

기존 protected-exceed penalty는 critical accumulation 초과분만 보므로,
network가 비어 있고 demand가 클 때 내부 유입을 적극적으로 장려하지 못할 수
있다. 반대로 all-urban half-cap penalty는 boundary queue와 storage가 이미
절반 이상 차면 이를 비우도록 압력을 준다.

다만 이 term은 TTT 자체가 아니라 guard 성격의 penalty다. 따라서 성능 해석은
Total TTT, delay, throughput, average travel time을 같이 봐야 한다. Peak 1800 s
진단에서 fallback-off P-Stack은 PFO보다 TTT는 컸지만 throughput도 더 컸고,
average travel time 관점에서는 해석이 달라질 수 있음을 확인했다.

### 4. PFO와 P-Stack 차이

PFO는 follower local TTT/TTS-compatible 선택으로 직접 control을 정한다. P-Stack은
leader가 `(N_P_star, N_UF_star)`를 먼저 정하고, follower가 그 target을 반영한
feasible set에서 response를 고른다.

따라서 P-Stack이 PFO보다 나빠지는 경우는 크게 세 가지다.

1. leader target feasible set이 PFO가 고르는 control 영역을 충분히 포함하지 못함
2. PFO 영역은 포함하지만 leader objective 또는 proxy가 그 후보를 낮게 평가하지 못함
3. grid/prefilter/early-termination 경량화가 좋은 후보를 full evaluation 전에 잘라냄

최근 진단에서 `leader_candidate_proxy_objective_spread = 0.0`이 관측되었다.
이는 cheap proxy prefilter가 후보를 사실상 구분하지 못한다는 뜻이며, top-K와
candidate ordering이 full evaluation에 과도하게 영향을 줄 수 있다.

### 5. Grid coarseness 진단

Fallback-off direct P-Stack top-K4 peak 1800 s run은 다음과 같았다.

| Run | Total TTT | Delay | Throughput | Terminal vehicles | Computation sec |
|---|---:|---:|---:|---:|---:|
| No-control | 605.825 | 324.093 | 10002.1 | 2539.0 | 0.00 |
| PFO | 451.476 | 169.745 | 11849.9 | 1616.6 | 372.52 |
| P-Stack direct fallback off | 471.030 | 189.298 | 12183.9 | 1452.0 | 3374.79 |

Top-K를 16으로 넓힌 fine-grid partial 진단에서는 coarse step 0에서
`N_P_star ~= 1819.6` 후보가 objective `82.7732`로, upper-bound 후보
`N_P_star ~= 3220`의 objective `82.7214`에 매우 근접했다. 이는 기존 grid와
prefilter가 중간 영역을 충분히 평가하지 못했을 가능성을 보여준다.

그러나 `225/121 + top-K16` closed-loop run은 step 0 refined evaluation만으로도
계산비용이 지나치게 커졌다. 따라서 grid를 계속 세분화하는 방식은 진단에는
도움이 되지만 online controller 구조로는 한계가 있다.

## Continuous leader optimizer로 전환하는 이유

`N_P_star`와 `N_UF_star`는 본질적으로 discrete actuator가 아니라 continuous
leader target이다. Grid는 수학적 필수조건이 아니라 expensive black-box follower
response를 평가하기 위한 근사였다.

따라서 leader outer search는 다음 구조가 더 적합하다.

```text
1. continuous feasible bounds 계산
2. previous/default/center/corner seed 평가
3. best point 주변을 coordinate/pattern search로 연속 탐색
4. follower는 기존 feasible discrete/quantized candidate argmin 유지
5. optional fallback/no-control guard와 candidate diagnostics 유지
```

이 방식의 장점은 다음과 같다.

- coarse grid 간격 때문에 좋은 `N_P_star`, `N_UF_star` 영역을 놓치는 문제를 줄인다.
- cheap proxy prefilter가 무력할 때 top-K ordering에 의존하지 않는다.
- evaluation budget을 `max_evals`로 명시할 수 있어 dense grid보다 계산비용을 예측하기 쉽다.
- periodic global refresh와 previous-action local search 구조를 그대로 유지할 수 있다.

## 한계

Follower 내부에는 여전히 green, offset, ramp metering, VSL의 discrete/quantized
candidate 선택이 있다. 따라서 leader objective는 완전히 smooth하지 않고
piecewise-flat 또는 discontinuous하게 보일 수 있다.

그러므로 gradient 기반 optimizer보다는 deterministic derivative-free pattern
search가 적합하다. 추후 필요하면 SciPy differential evolution 또는 COBYLA를
optional backend로 추가할 수 있지만, 현재는 dependency-free deterministic
pattern search를 우선 구현한다.

## 다음 구현 방향

1. `mpc.leader_search_mode`를 추가한다.
   - `grid`: 기존 coarse/refined grid 경로
   - `continuous`: continuous derivative-free pattern search 경로
2. continuous mode는 다음 설정을 사용한다.
   - `leader_continuous_max_evals`
   - `leader_continuous_seed_count`
   - `leader_continuous_local_iterations`
   - `leader_continuous_initial_step_fraction`
   - `leader_continuous_shrink_factor`
   - `leader_continuous_min_np_step_veh`
   - `leader_continuous_min_nuf_step_veh_h`
3. fallback guard와 candidate progress logging은 유지한다.
4. dense grid diagnostic은 production 후보에 PFO 해를 주입하지 않고, 별도 report-only
   diagnostic으로만 유지한다.
5. smoke run 이후 medium/peak 1800 s부터 PFO와 P-Stack continuous mode를 비교한다.
