# 원고 수정안 — APALL(ALLPRICE-JOINT) 기반 Intro ~ Methodology
(2026-07-09 작성. 각 블록은 "교체" 또는 "신설"로 표시. 수식은 Word 수식편집기로 옮기기 쉽게 평문+LaTeX 혼용으로 표기. [확인 필요] 표시는 인용 서지 확정 필요.)

---

## 표기 정리 (전 섹션 공통 — 먼저 결정 권장)

현행 원고는 prediction horizon과 net inflow target에 같은 기호(N_P)를 쓰고 있고(§3.2 line "NP is the length of prediction horizon" vs leader 결정변수 N_P), B_NU/B_UF와 N_P/N_UF가 혼용된다. 다음으로 통일할 것을 제안한다.

| 기호 | 의미 |
|---|---|
| H | follower prediction horizon (control interval 단위) |
| H + D | leader evaluation horizon (D ≥ 0, leader 전용 확장 깊이) |
| N_P(k_c) | protected urban network의 net inflow target [veh] |
| N_UF(k_c) | urban-to-freeway total exchange target [veh/h] |
| λ_P | N_P 조정용 dual price |
| g_ext,u | control input u의 marginal externality price |
| h_ab | lever쌍 (a,b)의 bilinear cross-term price |
| ω_l | freeway link l의 exchange budget 분배 비율 |

---

# A. §1 INTRODUCTION 수정

## A-1. [Research Gap] 문단 끝에 추가 (기존 문단 유지, 아래 삽입)

> 나아가 계층적 구조에서 leader의 조정 의도를 follower에게 전달하는 방식, 즉 coordination instrument의 선택 자체가 제어 성능을 좌우한다. 동일한 aggregate target이라도 이를 hard constraint(수량)로 전달할 것인지, 목적함수의 가격 항(price)으로 전달할 것인지에 따라 follower의 반응 특성과 구현 가능성이 달라진다. 규제경제학에서 Weitzman (1974)은 불확실성 하에서 가격 도구와 수량 도구의 우열이 한계비용·한계편익 곡선의 상대적 곡률에 의해 결정됨을 보였으며, 이 논리는 서로 다른 물리적 특성을 갖는 교통제어 lever들에 대한 instrument 선택 문제로 자연스럽게 확장된다. 그러나 기존 mixed network integrated control 연구는 특정 coordination 방식을 소여로 두었을 뿐, lever별 특성에 따른 instrument 선택을 체계적으로 다루지 않았다.

## A-2. [Contribution] 문단 전체 교체

> 본 연구의 주요 기여는 다음과 같다. 첫째, mixed urban-freeway network를 대상으로 상위 leader가 aggregate coordination target을 결정하고 하위 urban/freeway followers의 equilibrium response를 명시적으로 평가하는 Stackelberg game-based MPC framework를 제안한다. Leader는 개별 제어입력이 아닌 network-level coordination variable을 결정하며, follower response를 통해 해당 target의 implementability와 network performance cost를 함께 평가한다.
>
> 둘째, followers가 local information만으로 의사결정을 수행하면서도 network-level externality를 내면화하도록 하는 unified externality-pricing coordination mechanism을 제안한다. Leader는 전역 예측모형의 유한차분으로부터 각 local control input(green time, offset, ramp metering, VSL)에 대한 marginal externality price를 산정하여 하달하며, 이 가격은 전역 한계비용에서 follower가 자체 목적함수로 이미 인지하는 국소 한계비용을 차감한 순수 externality 성분으로 정의된다. 나아가 단일 lever 가격이 표현하지 못하는 lever 간 교차효과를 반영하기 위해, green-offset 및 VSL-ramp metering 쌍에 대한 bilinear cross-term price와 이에 상응하는 follower의 joint search 구조를 제시한다.
>
> 셋째, coordination instrument를 lever의 물리적 기하에 정합하도록 설계한다. Urban-to-freeway exchange는 ramp metering rate라는 직접적 수량 액추에이터로 구현되며 capacity drop이라는 비가역적 임계 현상에 노출되므로 수량 도구(equality budget과 mainline headroom 비례 배분)로 전달하고, protected network net inflow는 다수 신호교차로의 green time에 비선형적으로 의존하여 수량 강제가 분산 구현 불가능하므로 가격 도구(dual price)로 전달한다. 이러한 비대칭 설계는 Weitzman (1974)의 prices-versus-quantities 논리를 네트워크 교통제어의 instrument 선택에 적용한 것이다.
>
> 넷째, follower의 국소성과 leader의 전역 조정을 분리하는 비대칭 예측구조를 제안한다. Followers는 짧은 horizon의 국소 MPC를 유지하여 계산 효율성을 확보하는 반면, leader는 더 깊은 전역 rollout과 해석적 terminal cost — 잔여 accumulation과 ramp queue의 배수 시간을 근사하는 MFD-tail cost-to-go — 로 candidate target을 평가함으로써 horizon 밖의 장기 효과를 의사결정에 반영한다.
>
> 마지막으로, on-ramp와 off-ramp interface에서 발생하는 flow-based coupling을 중심으로, 각 coordination 채널이 urban/freeway TTT, ramp queue, spillback, freeway density에 미치는 영향을 정량적으로 분석하고, 채널별 ablation을 통해 가격·수량·joint 도구의 유효 영역을 실증적으로 제시한다.

---

# B. §2 Literature Review 수정

## B-1. 소제목 교체

"2.1 Crowd management" → **"2.1 Game-theoretic traffic control"**

## B-2. 신설 소절 (2.2 또는 [Stackelberg game연구] 문단 뒤 삽입)

### 2.x Coordination instruments: prices versus quantities

> 계층적·분산적 제어 구조에서 상위 계층의 조정 의도를 하위 계층에 전달하는 방식은 크게 수량 도구(quantity instrument)와 가격 도구(price instrument)로 구분할 수 있다. 수량 도구는 하위 제어기의 행동량을 제약(budget, cap, equality constraint)으로 직접 지정하며, 가격 도구는 하위 목적함수에 조정 신호를 가격 항으로 부가하여 행동을 유도한다. 두 도구는 확실성 하에서는 쌍대성에 의해 등가이지만, 모형 오차와 불확실성이 존재하면 등가성이 깨진다. Weitzman (1974)은 시스템 한계손실 곡선이 하위 주체의 한계비용 곡선보다 상대적으로 가파를수록 수량 도구가, 그 반대일수록 가격 도구가 우월함을 보였으며, Roberts and Spence (1976)는 불확실성 하에서 수량 제약과 가격 신호를 결합한 혼합 도구가 순수 도구를 약지배함을 보였다.
>
> 교통제어 분야에서도 두 계열의 도구가 병존해 왔다. Coordinated ramp metering에서는 상위 조정기가 개별 ramp의 metering rate 또는 그 총량을 직접 배분하는 수량형 접근이 주를 이루며(Papamichail and Papageorgiou, 2008 [확인 필요: HERO 계열 서지]), 배분 기준으로 본선 occupancy나 queue 상태를 활용한다. 반면 dual decomposition에 기반한 분산 MPC는 결합 제약의 Lagrange multiplier를 가격으로 삼아 하위 문제를 분리한다 [확인 필요: dual decomposition 기반 분산 MPC 서지 1-2편]. 그러나 mixed urban-freeway network의 통합제어에서 서로 다른 물리적 특성을 갖는 lever들 — 매끄러운 국소 비용구조를 갖는 green time, capacity drop 절벽에 노출된 ramp metering, 순수 조정 변수인 offset — 에 대해 어떤 도구가 정합한지를 체계적으로 비교한 연구는 부족하다. 본 연구는 lever별 비용 기하와 구현 가능성에 근거하여 수량·가격·joint 도구를 배정하고, 그 선택을 ablation으로 검증한다.

---

# C. §3.2 수정 — 비대칭 예측구조 추가

## C-1. 기존 "Prediction horizon은 control interval 단위로 정의한다." 문단을 다음으로 교체

> Prediction horizon은 control interval 단위로 정의하되, 본 연구는 leader와 followers에 서로 다른 평가 깊이를 부여한다. Followers는 H개 control interval에 대한 국소 MPC 문제를 해결한다. 이는 각 follower의 계산량을 국소 문제 크기로 제한하기 위함이다. 반면 leader는 candidate target을 평가할 때 전역 예측모형을 H+D개 interval까지 전개(rollout)하며, 그 종점 상태에 대해 해석적 terminal cost를 부가한다(3.4.1절). 즉 leader의 평가 horizon은 followers의 결정 horizon보다 깊다.
>
> 이러한 비대칭 구조의 근거는 두 가지이다. 첫째, followers의 horizon을 늘리면 모든 국소 문제의 계산량이 동시에 증가하는 반면, leader의 평가 깊이 D는 candidate 평가 시의 전역 simulation 횟수에만 영향을 미치므로 계산 부담의 증가가 제한적이다. 둘째, horizon 내에 완료되지 않는 차량들의 잔여 통행시간은 주로 aggregate accumulation과 queue의 배수 과정으로 결정되므로, 세부 제어반응보다는 leader 수준의 aggregate 평가로 근사하는 것이 적절하다. 각 MPC step에서는 첫 번째 control interval에 해당하는 control input만 적용하며, 다음 step에서 새로 관측된 상태로 절차를 반복하는 receding-horizon 구조는 기존과 동일하다.

---

# D. §3.4 재작성

## D-1. §3.4 도입부 (기존 "제안 제어 문제는 상위 leader problem과..." 문단 교체)

> 제안 제어 문제는 상위 leader problem과 하위 follower game으로 구성된다. 시간 k_c에서 전체 network state x(k_c)는 freeway density and speed, freeway origin queue, on-ramp/off-ramp queue, urban link accumulation, movement queue를 포함한다. Leader의 결정변수는 두 개의 aggregate coordination variable이다.
>
> U_L(k_c) = ( N_P(k_c), N_UF(k_c) )
>
> 여기서 N_P(k_c)는 protected urban network에서 허용되는 net inflow target이고, N_UF(k_c)는 urban-to-freeway total exchange target이다. Followers의 결정변수는 실제 현장 제어수단인 green time, offset, ramp metering rate, VSL이다.
>
> Leader와 followers를 연결하는 coordination 채널은 세 층으로 구성된다. 첫째, N_UF는 수량 도구로 전달된다. Leader가 결정한 총 exchange budget이 freeway link별로 분배되고, 각 freeway follower는 배분된 budget을 등식 제약으로 하여 소유 ramp들의 metering rate를 결정한다. 둘째, N_P는 가격 도구로 전달된다. 각 urban follower의 목적함수에 dual price λ_P가 부가되며, λ_P는 실현된 net inflow와 target의 오차에 따라 control step 간 적분 갱신된다. 셋째, 모든 local control input에 대해 leader가 전역 예측모형으로부터 산정한 marginal externality price와 lever쌍 bilinear cross-term price가 하달되어, followers가 국소 정보만으로 의사결정하면서도 network-level externality를 내면화하도록 한다. 각 채널의 정식화와 설계 근거는 3.4.2절에서 제시한다.

## D-2. §3.4.1 Upper-level leader problem (기존 leader 절 전체 교체)

> **3.4.1 Upper-level leader problem**
>
> Leader의 목적은 followers의 equilibrium response를 고려하면서 전체 네트워크의 total time spent (TTS)를 최소화하는 aggregate target을 선택하는 것이다. 각 control step에서 leader는 candidate target 집합 {U_L^(1), ..., U_L^(M)}을 생성한다. Candidate의 범위는 현재 큐의 배수 가능량과 예측 도착량으로부터 산정되는 수요-기반 구간으로 제한한다. 각 candidate U_L에 대해 followers의 equilibrium response u*(U_L)을 계산한 뒤(3.4.3절), leader는 그 response 하에서 전역 예측모형을 H+D개 interval까지 전개하여 다음 objective를 평가한다.
>
> J_L(U_L) = Σ_{τ=k_c}^{k_c+H+D−1} TTS(τ; u*(U_L)) + V_far( x(k_c+H+D) )    (식 L-1)
>
> 첫 항은 유한 rollout 구간의 실현 TTS이고, V_far는 rollout 종점에 잔류하는 차량들의 잔여 통행시간을 근사하는 terminal cost(cost-to-go)이다. Horizon 내에 완료되지 않는 차량이 많은 혼잡 조건에서 terminal cost가 없으면, 방류·배수의 장기 이득이 목적함수에 반영되지 않아 leader가 과도하게 보수적인 target을 선택하는 경향이 발생한다. V_far는 urban 성분과 freeway 성분의 합으로 구성한다.
>
> V_far = V_far^U + V_far^F    (식 L-2)
>
> Urban 성분은 protected network의 잔여 accumulation(경계 대기 차량 포함)을 유효 배수율로 해소하는 데 필요한 총 대기시간의 삼각형 근사로 정의한다.
>
> V_far^U = ( n_P + n_B )² · T_c / ( 2 · G_U(n_P) )    (식 L-3)
>
> 여기서 n_P는 rollout 종점의 protected accumulation, n_B는 boundary에서 진입 대기 중인 큐(게이팅으로 보호구역 밖에 적체된 차량을 포함해야 accumulation을 경계 밖으로 밀어내는 것이 무비용으로 평가되는 왜곡을 방지한다), G_U는 accumulation 수준에 의존하는 배수율로서 임계 accumulation을 초과하면 감소한다. 이 형태는 고정 서비스율로 큐를 해소할 때 잔여 총 대기시간이 N²/(2G)로 주어지는 queueing 근사에 해당한다.
>
> Freeway 성분은 본선 잔여 차량의 배수와 ramp queue의 합류 대기를 구분하여 근사한다.
>
> V_far^F = N_main² · T_c / ( 2 · G_F ) + Σ_r [ q_r² · T_c / ( 2 · μ_r^merge ) + q_r · t_r ]    (식 L-4)
>
> μ_r^merge = C_r · φ( ρ_merge,r )    (식 L-5)
>
> 여기서 N_main은 본선 잔여 차량 수, G_F는 본선 유효 배출률, q_r은 ramp r의 잔여 큐, C_r은 ramp capacity, t_r은 합류 후 잔여 통과시간이며, φ(ρ)는 합류부 본선 밀도에 따른 receiving factor이다. 식 (L-5)는 본선이 혼잡할수록 ramp queue의 배수가 느려져 동일한 큐라도 잔여 비용이 커지는 효과, 즉 본선 상태와 ramp queue 간의 결합을 terminal cost 안에 명시적으로 표현한다. 이 결합 때문에 leader의 평가에서 본선 공간 확보(VSL, 유입 억제)와 ramp 방류(metering)의 상호보완성이 포착된다.
>
> Leader는 J_L을 최소화하는 candidate를 선택하고, 그에 대응하는 followers의 첫 번째 control interval 입력만 실제 네트워크에 적용한다.
>
> B*(k_c) = argmin_{U_L} J_L( x(k_c), U_L, u*(U_L) ),  subject to u*(U_L) ∈ NE( G_lower(U_L) )    (식 L-6)
>
> 선택된 N_UF는 freeway link별 budget으로 분배된다. 분배 비율 ω_l은 각 link 본선의 잔여 수용량(headroom)에 비례하도록 상태 피드백으로 산정한다.
>
> ω_l ∝ Σ_{i∈link l} max( 0, ρ_crit − ρ_l,i ) · L_l · λ_l,i^eff,  Σ_l ω_l = 1    (식 L-7)
>
> 즉 임계밀도까지 여유가 큰 link가 더 많은 exchange budget을 받으며, off-ramp spillback 등으로 유효 차로수 λ^eff가 감소한 link의 몫은 자동으로 축소된다. 이는 coordinated ramp metering에서 본선 상태 기반으로 metering을 연동하는 접근(Papamichail and Papageorgiou, 2008 [확인 필요])과 같은 계열이되, 배분 대상이 개별 metering rate가 아니라 leader가 결정한 aggregate budget이라는 점에서 구별된다. 모든 link의 headroom이 0이면 균등 분배로 대체한다.

## D-3. §3.4.2 Coordination channels (신설 절)

> **3.4.2 Coordination channels: quantity, dual price, and externality pricing**
>
> **(1) Quantity channel for N_UF.** 각 freeway follower l은 배분된 budget ω_l·N_UF를 등식 제약으로 하여 소유 ramp들의 metering rate를 결정한다.
>
> Σ_{r∈R_l} μ_r(k_c) = ω_l(k_c) · N_UF(k_c)    (식 C-1)
>
> Budget 내에서의 ramp 간 배분은 follower의 국소 최적화(3.4.3절)에 맡긴다. Metering rate는 유량의 상한이므로, ramp 수요가 budget에 미달하면 실현 exchange flow는 자동으로 수요 수준으로 제한되며 등식 제약은 존재하지 않는 수요를 강제하지 않는다.
>
> N_UF를 수량 도구로 전달하는 근거는 두 가지이다. 첫째, ramp metering rate는 exchange flow라는 조정 대상 수량을 직접 지정하는 액추에이터이므로, leader의 결정이 지연과 오차 없이 구현된다. 둘째, 합류부 하류의 capacity drop은 임계밀도 근방에서 비가역적 임계 현상으로 나타나므로, 시스템 한계손실 곡선이 follower의 국소 한계비용 곡선에 비해 극단적으로 가파르다. Weitzman (1974)의 비교 논리에 따르면 이러한 조건에서는 수량 도구가 가격 도구를 지배한다. 실제로 국소 목적함수가 방류량에 대해 임계점 이전까지 평탄한 구조에서는, 선형 가격에 대한 follower의 최적반응이 계단형(bang-bang)이 되어 가격으로는 목표 수량을 정밀하게 유도할 수 없다.
>
> **(2) Dual price channel for N_P.** Protected network의 net inflow는 다수 신호교차로의 green time에 비선형적으로 의존하는 파생량이므로, 등식 제약으로 강제하려면 교차로 간 결합 역문제를 중앙에서 풀어야 하며 이는 분산 구조와 양립하지 않는다. 따라서 N_P는 결합제약 Σ_i nin_i = N_P의 dual price로 전달한다. 각 urban follower i의 목적함수에 다음 항이 부가된다.
>
> λ_P(k_c) · nin_i( g_i )    (식 C-2)
>
> 여기서 nin_i는 follower i의 green 결정이 유발하는 protected network net inflow 기여분이다. λ_P는 control step 간에 적분 갱신된다.
>
> λ_P(k_c+1) = clip( λ_P(k_c) + γ_P · ( Σ_i nin_i − Ñ_P(k_c) ), 0, λ_P^max )    (식 C-3)
>
> 여기서 Ñ_P는 followers가 실제로 실현 가능한 범위로 투영된 target이다. λ_P는 실현 유입이 target을 초과할수록 증가하여 유입을 억제하는 방향으로 작동하며, 하나의 control step 내에서는 상수로 유지된다. Step 내에서 λ_P를 반복 갱신하여 등식을 정확히 만족시키는 방식은 채택하지 않는다. 국소 문제의 비볼록성으로 인해 follower 최적반응이 λ_P에 불연속적으로 반응하여 정확한 dual 해가 존재하지 않을 수 있고, 반복 중 결합변수의 재수렴 없이 제어가 확정되는 off-equilibrium 문제가 발생하기 때문이다.
>
> **(3) Marginal externality prices.** 위 두 채널이 aggregate 수준의 조정을 담당하는 반면, 개별 lever 수준의 externality는 marginal price로 전달한다. Control input u(green time, ramp metering rate, VSL)에 대한 externality price는 다음과 같이 정의한다.
>
> g_ext,u = ∂J_global/∂u − ∂J_local/∂u    (식 C-4)
>
> 첫 항은 leader의 전역 예측모형을 현재 운영점 u_ref 주위에서 ±δ_u만큼 섭동하여 얻는 전역 TTS의 유한차분 기울기이고, 둘째 항은 동일 운영점에서 해당 follower의 국소 목적함수를 같은 방식으로 섭동하여 얻는 국소 기울기이다. 국소 성분을 차감하는 이유는 follower가 자체 목적함수로 이미 인지하는 비용을 가격이 중복 부과하지 않도록, 즉 가격이 순수하게 "자신의 행동이 타 구역에 미치는 한계비용"만을 담도록 하기 위함이다. Follower의 목적함수에는 선형 가격 항이 부가된다.
>
> w_u · g_ext,u · ( u − u_ref )    (식 C-5)
>
> 가격은 국소 선형 근사이므로 두 가지 안전장치를 둔다. 첫째, trust region으로서 후보 탐색을 선형화가 측정된 이웃 |u − u_ref| ≤ Δ_u 내로 제한한다(green ±δ_g, metering ±0.25·capacity, VSL ±10 km/h). 둘째, 운영점이 기준점에서 문턱 이상 이동하면 가격을 재선형화하는 event-triggered refresh를 적용한다. 아울러 followers의 control variation penalty(smoothness)는 가격 활성 시에도 유지한다. 이 항은 가격 추정 오차 대비 신호가 약한 경우 행동을 억제하는 암묵적 문턱으로 작동하여, 저신호 구간에서 노이즈성 가격에 의한 과잉 반응을 방지한다.
>
> **(4) Bilinear cross-term prices and joint response.** 단일 lever의 선형 가격은 lever쌍의 교차효과(예: 상류 offset 변화가 green 재배분의 한계가치를 바꾸는 효과, 본선 VSL이 ramp 방류의 한계비용을 바꾸는 효과)를 표현하지 못한다. 이를 위해 두 lever쌍 (green, offset)과 (VSL, ramp metering)에 대해 bilinear cross-term price를 도입한다.
>
> h_ab = [ J(a⁺,b⁺) − J(a⁺,b⁻) − J(a⁻,b⁺) + J(a⁻,b⁻) ]_global / (4 δ_a δ_b) − [ · ]_local / (4 δ_a δ_b)    (식 C-6)
>
> 즉 전역·국소 목적의 혼합 2차 편미분을 4-corner 유한차분으로 추정하고 국소 성분을 차감한다. Follower 목적함수에는 다음 항이 부가된다.
>
> h_ab · ( a − a_ref ) · ( b − b_ref )    (식 C-7)
>
> Cross-term이 실효를 갖기 위한 필요조건은 follower가 두 lever를 동시에 탐색하는 것이다. 한 lever를 고정하고 다른 lever를 탐색하는 coordinate descent 구조에서는 bilinear 항이 상수 계수의 선형 항으로 퇴화하기 때문이다. 따라서 비-ramp 신호교차로의 follower는 (green, offset)을 2차원 격자에서 공동 탐색하며(3.4.3절), freeway follower는 metering 후보마다 VSL 최적반응을 재계산하는 기존 중첩 구조가 이미 joint 탐색에 해당하므로 가격 항만 추가한다.

## D-4. §3.4.3 Lower-level follower problems (기존 3.4.2 교체)

> **3.4.3 Lower-level follower MPC problems**
>
> **Urban followers.** 각 신호교차로 i는 하나의 urban follower로서, 자신의 movement queue와 도착류에 대한 국소 예측모형을 갖는다. 도착류는 상류 교차로의 (직전 합의된) green과 offset으로부터 재구성한 platoon 도착 프로파일로 표현하며, 서비스는 cycle 내 위상을 해상하는 phase-resolved 형태로 채점한다. 이는 cycle 평균 유량만을 사용하는 경우 offset의 조정 효과가 목적함수에 나타나지 않기 때문이다. Follower i의 문제는 다음과 같다.
>
> min_{g_i, o_i}  J_i^local( g_i, o_i ) + w_g |g_i − g_i(k_c−1)| + λ_P · nin_i(g_i) + w_g · g_ext,g_i · ( g_i − g_ref,i ) + h_go,i · ( g_i − g_ref,i )( o_i − o_ref,i )    (식 F-1)
>
> subject to  g_min ≤ g_i ≤ g_max,  Σ_{phases} g + L_i = C,  0 ≤ o_i < C,  |g_i − g_ref,i| ≤ Δ_g,  storage/receiving constraints
>
> 여기서 J_i^local은 국소 rollout에 의한 자기 TTS(움직임 큐 대기 포함)이고, 둘째 항은 control variation penalty이다. 비-ramp 교차로는 (g_i, o_i)를 2차원 격자에서 공동 탐색하고, on-ramp/off-ramp와 접한 교차로는 ramp reservoir와 off-ramp storage 동역학을 포함하는 ramp-aware rollout으로 green을 탐색한다.
>
> **Freeway followers.** 각 freeway link l은 하나의 freeway follower로서, 소유 on-ramp들의 metering rate와 segment별 VSL을 결정한다. 국소 목적은 link 관할 차량의 총 체류로 정의한다.
>
> J_l^local = Σ_τ Δt [ Σ_i ρ_l,i(τ) L_l λ_l,i + Σ_{r∈R_l} w_r(τ) + Σ_{s∈S_l} n_s^store(τ) + b_l(τ) ] + w_ρ Σ_τ Σ_i max(0, ρ_l,i(τ) − ρ_crit) + variation penalties    (식 F-2)
>
> 본선 차량수와 on-ramp queue에 더해, off-ramp storage 점유 n^store와 상류 도시부에서 reservoir 포화로 진입하지 못한 가상 대기 b_l을 포함하여 follower가 자기 결정의 상류 externality를 국소적으로 인지하도록 한다. 다섯째 항은 임계밀도 초과에 대한 hinge penalty로서 capacity drop 임계 접근을 연속 비용으로 표현한다. 결정 구조는 budget 제약 (식 C-1) 하의 ramp 간 배분 탐색과, 각 배분 후보에 대한 segment별 VSL 최적반응 계산의 중첩으로 구성되며, VSL 후보에는 (식 C-5)의 VSL 가격 항과 (식 C-7)의 VSL-metering cross 항이 부가되고 탐색은 trust region |v − v_ref| ≤ 10 km/h 내로 제한된다.
>
> **Equilibrium computation.** Followers 간 결합(경계 유량, 상류 도착, off-ramp 유입)은 결합변수의 snapshot을 동결한 Jacobi best-response 반복으로 처리한다. 각 반복에서 모든 followers가 동일한 동결 결합변수 하에서 최적반응을 계산하고, 결합변수를 재산정하여 under-relaxation(α = 0.5)으로 합성하며, 상대 잔차가 허용오차 미만이거나 최대 반복수 S_max에 도달하면 종료한다. 이 반복의 고정점을 lower-level Nash-type equilibrium response로 정의한다.

## D-5. Algorithm 1 교체

> **Algorithm 1. Stackelberg Game-Based MPC with Externality Pricing**
>
> Step 1. 시간 k_c에서 mixed-network state x(k_c)를 관측한다.
> Step 2. Leader 평가 horizon [k_c, k_c+H+D)에 대한 external demand를 예측한다.
> Step 3. 운영점(직전 적용 제어) u_ref에서 marginal externality price g_ext,u (식 C-4)와 cross-term price h_ab (식 C-6)를 산정하여 followers에 하달한다. 운영점이 직전 기준점에서 문턱 이상 이동한 경우에만 재산정한다(event-triggered refresh).
> Step 4. Leader가 수요-기반 구간에서 candidate target 집합 {(N_P, N_UF)}을 생성하고, headroom 비례 규칙 (식 L-7)로 link별 budget 분배 ω를 산정한다.
> Step 5. 각 candidate에 대해 followers가 Jacobi best-response 반복으로 equilibrium response를 계산한다(3.4.3절).
> Step 6. Leader가 각 (candidate, response) 쌍을 H+D-step 전역 rollout과 terminal cost로 평가하고(식 L-1), J_L을 최소화하는 candidate를 선택한다.
> Step 7. 선택된 response의 첫 번째 control interval 입력 μ(k_c), v^lim(k_c), g(k_c), o(k_c)를 적용한다.
> Step 8. 실현 net inflow로 λ_P를 적분 갱신하고(식 C-3), k_c ← k_c+1로 이동하여 반복한다.

---

# E. 기타 정리 항목 (원고 내 직접 수정)

1. **§3.4 앞부분 "Game Theory" 개조식 설명과 표** — 학술지 원고에는 과도한 기초 설명이므로 §2로 흡수하거나 대폭 축약 권장(2-3문장).
2. **line 186-192 수식 중복** — 동일 leader objective가 두 번 등장. (식 L-1)~(식 L-6)으로 대체.
3. **§3.4.2 기존 urban follower 제약** `|Σ(q_in − q_out) − N_P| ≤ ε_U` **삭제** — (식 C-2)~(식 C-3)의 dual price로 대체됨.
4. **freeway follower 제약** `|Σ r_r − N_F*| ≤ ε_F` → 등식 (식 C-1)로 교체하고 링크별 분해(ω) 명시.
5. **표기 충돌** — prediction horizon 기호를 H로 변경(N_P는 net inflow target 전용).
6. **§3.3.3에 추가 권장(2-3문장)** — freeway 세그먼트 간 receiving/supply 제약(하류 수용량이 상류 유출을 제한), urban 유한 출구용량(boundary outflow capacity). Plant에 실제 포함된 요소로서 spillback 전파의 완결성을 위해 언급.
7. **인용 추가 목록** — Weitzman, M.L. (1974). Prices vs. quantities. *Review of Economic Studies*, 41(4), 477–491. / Roberts, M.J., Spence, M. (1976). Effluent charges and licenses under uncertainty. *Journal of Public Economics*, 5(3–4), 193–208. / Papamichail, I., Papageorgiou, M. (2008). Traffic-responsive linked ramp-metering control. *IEEE Trans. ITS*, 9(1) [확인 필요]. / Carlson, R.C., Papamichail, I., Papageorgiou, M., Messmer, A. (2010). Optimal mainstream traffic flow control of large-scale motorway networks. *Transportation Research Part C*, 18(2) [확인 필요 — VSL/mainstream 제어 언급 시].
