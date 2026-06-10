# Inflow-Outflow Allocation 재구현 제안 — 독립 Allocation Module + density-balancing (논문 §3.2)

대상: Codex. 목적: 현재 `urban_follower._allocation`이 **큐비례 휴리스틱**으로 되어 있어, 의도한
**density-balancing 최적 배분**(참고문헌: "Perimeter Control by Simultaneously Regulating Inflow
and Outflow in Urban Network", §3.2)을 구현하지 못한다. 더 중요한 건 **배치**다 — §3.2 균등화는
gate들 **사이**의 density를 고르게 하는 **perimeter 전체 1회 최적화**라, 교차로별 agent 안에 쪼개
넣으면 안 된다(교차로 1개의 movement dim≈1~2라 균등화 무의미). 아래 아키텍처 그림대로
**독립 Allocation Module**(N_P → movement별 green 기준값)을 두고, 그 뒤 **교차로별 urban agent가
±band 미세조정 + offset**을 하는 2단계로 재구현한다. **확장 토폴로지/distributed 재작업과 함께 진행.**

## 0. 목표 아키텍처 (사용자 확정 — 컨트롤러 블록도)

```
[Leader]  U_L = [N_P, N_{U→F}]
   │ N_P (net inflow 목표)                         │ N_{U→F} (total metering rate)
   ▼                                               ▼
[Inflow-Outflow Allocation Module]            [Freeway Agent (링크별)]
  R_U(N_P) = [g_{i,m}]                           R_F = [r*_r, v*_l]
  목적 = Queue/Density Balance (§3.2)             목적 = min TTT
  perimeter 전체 movement에 green 기준값 1회 산출        ▲
   │ R_U                                              │ Nash (given N_P, N_{U→F})
   ▼                                                  ▼
[Urban Agent (교차로별)]  ◀───────── Follower-level Nash ─────────▶
  R_S(R_U) = [g*_{i,m}, φ*_i]
  목적 = min local TTT  (g는 g_{i,m}±band 미세조정, offset φ 결정)
```

**두 블록은 분리**다.
- **Allocation Module** = N_P 받아 **전 gate movement의 green 기준값 `g_{i,m}`을 한 번에** 산출
  (§3.2 density balance). 각 교차로가 자기끼리 못 푸는 network-wide 균등화를 여기서 해결.
- **Urban Agent(교차로별)** = 그 기준값을 받아 **±band 안에서 green 미세조정 + offset φ 결정**,
  local TTT 최소화, freeway agent와 Nash. 이게 진짜 per-agent local solve.

## 1. 현재 문제 (요약)
`urban_follower._allocation`: 순유입 목표를 in/out으로 쪼개고 각 그룹 안에서 `w = q/Σq`(큐 길이 비례)
분배. → (a) density가 아니라 raw queue, (b) sparsity 최소화가 아니라 단순 비례, (c) 최적화/PSO 없음,
(d) 순누적 제약은 clip뿐, (e) **배치도 틀림** — 균등화를 monolithic urban follower 안에서 1회로 푸는데,
distributed로 가면 교차로별 agent로 쪼개져 균등화가 깨진다. → **독립 모듈로 분리**해야 한다.

## 2. density 벡터 정의 — gate별 movement 열거가 필수

Eq 9의 `k_inflow`, `k_outflow`는 **스칼라가 아니라 벡터**이고, 각 원소 = **개별 boundary movement
하나의 density**(점유율)다. `||k||₂²/||k||₁² → 1/dim`은 **모든 원소가 같을 때** 달성 → "어느 gate의
어느 movement"를 원소로 나열했는지가 정해져야 정의된다. 따라서 **gate별 inflow/outflow movement를
명시 열거**한다(확장망 A·B·C·D·F gate, E는 비통제 제외).

| gate | inflow movement (보호영역 進入) | outflow movement (보호영역 離脱) |
|------|------|------|
| A | top_in→grid, left_in→grid | grid→top_out, grid→left_out |
| B | top_in→grid | grid→top_out |
| C | top_in→grid, right_in→grid | grid→top_out, grid→right_out |
| D | left_in→grid, **off-ramp 도착→grid** | grid→left_out, **grid→on-ramp(x_on)** |
| F | right_in→grid, **off-ramp 도착→grid** | grid→right_out, **grid→on-ramp(x_on)** |

- `k_inflow` = 위 inflow 칸 전부의 density 벡터(dim ≈ 8), `k_outflow` = outflow 칸 전부(dim ≈ 8).
- density `k_m = (해당 링크 차량수) / (링크 저장용량)` (점유율, raw queue 아님).
- off-ramp 도착=inflow, on-ramp 진입(x_on)=outflow로 넣는 건 delay 귀속(urban)과 일관
  (`extended_network_proposal.md` §3 확정 귀속과 일치).
- movement 집합은 **토폴로지에서 도출**하되 위 표를 canonical 근거로 박을 것.

## 3. 논문 §3.2 정식 (Allocation Module이 푸는 문제)

체인: §3.1 desired net accumulation `N_des`(=리더 N_P) → **§3.2 그걸 inflow/outflow movement에
density-balancing으로 배분** → movement별 green `g_{i,m}` 출력 → 교차로 agent가 §3.3(미세조정+offset).
- `N_des` = 리더 N_P (= `urban_accumulation_feedback_flow(state,cfg,N_P_star)`, 기존 재사용).

**목적함수 (Eq 9, minimize over q^inflow, q^outflow)**:
```text
J = ( ||k_inflow||_2^2 / ||k_inflow||_1^2  -  1/dim(k_inflow) )^2
  + ( ||k_outflow||_2^2 / ||k_outflow||_1^2 -  1/dim(k_outflow) )^2
```
- inflow끼리, outflow끼리 **density를 균등화**(sparsity 최소화). 모든 원소 동일 → 항=0.

**제약 (Eq 10, 순누적)**:
```text
| Σ ( q_inflow - q_outflow )  -  N_des | <= eps
```

**제약 (Eq 11-14, green time)**: 배분량 q를 green/cycle·saturation으로 환산, min/max green 범위.
```text
(g_min[l,m] / Cl[l]) * s[l,m]  <=  q[l,m]  <=  (g_max[l,m] / Cl[l]) * s[l,m]
```
(`g_min/max`=movement min/max green, `Cl`=cycle length, `s`=saturation flow rate.)

**출력**: movement별 green 기준값 `g_{i,m}` (= R_U). 이게 교차로 agent의 setpoint가 된다.

**Solver**: PSO(Kennedy & Eberhart 1995). 목적이 norm 비율(비볼록) → 메타휴리스틱.
- **호출 위치 = leader decision당 1회** (N_P 고정이니 Nash 안에서 재실행 안 함). → 입자수·iteration을
  작게(movement ~16개, 저차원) 잡으면 비용 작음. Nash 매 iteration PSO 재실행 없음(비용 걱정 해소).
- (구현 비용이 더 크면 동등 목적의 좌표하강 등 대체 가능하나 **큐비례 1회식은 부적합** — 반드시
  J(Eq 9)를 *최소화*하는 탐색.)

## 4. 코드 변경 지시

1. **신규 Allocation Module** (예: `urban/inflow_outflow_allocation.py` 또는 follower 내 독립 함수):
   - 입력 = N_des(리더 N_P), 전 gate movement의 현재 density(§2 표), green 범위/cycle/saturation.
   - 결정변수 = movement별 배분량 q(=green 환산), 탐색 = PSO,
   - 목적 = Eq 9(B_in² + B_out²), 제약 = Eq 10(N_des, `eps_U`) + Eq 11-14(green 범위),
   - 출력 = movement별 green 기준값 `g_{i,m}` (R_U). **decision당 1회 호출.**
2. **`urban_follower._allocation`의 큐비례 분배 제거.** 균등화는 위 모듈로 이관.
3. **Urban agent(교차로별) fine-tune** (`distributed_followers_proposal.md`와 연계):
   - R_U의 `g_{i,m}`를 setpoint로 받아 `g* ∈ [g_{i,m}−δ, g_{i,m}+δ]` (밴드폭 δ 파라미터) 안에서만 조정,
     **offset φ_i**를 결정. 목적 = local TTT.
   - **순누적 보존**: offset φ는 net inflow를 안 바꾸고 진행대만 조정 → agent는 **offset 위주 + green은
     작은 δ**로 움직여 Eq 10이 보존되게. (green 총량은 allocation이 정함, agent는 offset이 주무기.)
4. **단위 일관**: 출력 green/배분량과 plant 소비부(`urban_queue_model._movement_capacity_flow`) 단위 일치.
5. spec `04_controller.md §4.4`의 B_in/B_out·J_balance가 이미 Eq 9이므로 그걸 기준으로(spec 정정 불필요).
   단 spec에 "**독립 Allocation Module(perimeter 1회) → 교차로 agent fine-tune(band+offset)**" 2단계 구조를 반영.

## 5. 검증
- density balance 지표(`B_in`,`B_out`, `CV_boundary`)가 **실제로 감소**(큐비례 대비). 모든 movement
  density가 균등에 수렴하는지.
- Eq 10 만족: `|Σ(in−out) − N_des| ≤ eps_U`. agent fine-tune **후에도** net 보존되는지(offset 위주 검증).
- green 범위(Eq 11-14) 위반 0. agent의 `g*`가 `g_{i,m}±δ` 밖으로 안 나가는지.
- PSO 호출이 **decision당 1회**인지(Nash iteration마다 재실행 안 함) — compute 회귀 방지 카운터.
- 단위 테스트: 인위적 density 불균형 입력 → allocation 후 B_in/B_out 감소 + 제약 충족.
- 통합: 확장 토폴로지에서 boundary balance(CV/Overflow)가 baseline 대비 개선되는지.

## 6. 주의
- 현재 큐비례가 round-6에서 CV를 0.064까지 낮춘 건 사실이나, 이는 N_P_crit 수정 덕이지 §3.2 구현이
  아니다. §3.2(density sparsity + PSO + Eq 10 제약)는 별개이며 net inflow tracking을 정식 제약으로 잡는다.
- **배치 핵심**: allocation은 조율 기준(g_{i,m}) 생성(perimeter, decision당 1회), agent는 그 기준의
  국소 미세조정(band+offset, Nash). 둘을 섞지 말 것.
