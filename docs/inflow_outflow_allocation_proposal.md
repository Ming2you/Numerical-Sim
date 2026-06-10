# Inflow-Outflow Allocation 재구현 제안 — density-balancing (논문 §3.2)

대상: Codex. 목적: 현재 `urban_follower._allocation`이 **큐비례 휴리스틱**으로 되어 있어, 의도한
**density-balancing 최적 배분**(참고문헌: "Perimeter Control by Simultaneously Regulating Inflow
and Outflow in Urban Network", §3.2)을 구현하지 못한다. spec `docs/spec/04_controller.md §4.4`에는
이미 올바른 목적(B_in/B_out)이 명세돼 있으나 **코드가 그걸 구현 안 함**(spec≠code). 이를 §3.2대로
재구현한다. **확장 토폴로지/distributed 재작업과 함께 진행** 권장.

## 현재 문제 (요약)
`urban_follower._allocation`: 순유입 목표를 in/out으로 쪼개고 각 그룹 안에서 `w = q/Σq`(큐 길이 비례)
분배. → (a) density가 아니라 raw queue, (b) sparsity 최소화가 아니라 단순 비례, (c) 최적화/PSO 없음,
(d) 순누적 제약은 clip뿐. 결과적으로 §3.2의 density-balancing 최적해를 못 찾는다.

## 논문 §3.2 정식 (구현 기준)

체인: §3.1 desired net accumulation `N_des` 추정(SMC) → **§3.2 그걸 inflow/outflow movement에
density-balancing으로 배분** → §3.3 dual-ring 신호 변환.
- 우리 시스템에서 `N_des` = 리더의 누적 피드백 `urban_accumulation_feedback_flow(state,cfg,N_P_star)`
  (이미 존재). §3.2는 그 `N_des`를 **어떻게 배분하느냐**의 문제.

**목적함수 (Eq 9, minimize over q^inflow, q^outflow)**:
```text
J = ( ||k_inflow||_2^2 / ||k_inflow||_1^2  -  1/dim(k_inflow) )^2
  + ( ||k_outflow||_2^2 / ||k_outflow||_1^2 -  1/dim(k_outflow) )^2
```
- `k_inflow`, `k_outflow` = 각 inflow/outflow movement의 **density 벡터**(= 링크 점유율, 용량 정규화.
  raw queue 아님). 모든 원소가 같으면 `||k||_2^2/||k||_1^2 = 1/dim` → 항=0 → density 균등.
- inflow끼리, outflow끼리 **density를 균등화**(sparsity 최소화).

**제약 (Eq 10, 순누적)**:
```text
| Σ ( q_inflow - q_outflow )  -  N_des | <= eps
```

**제약 (Eq 11-14, green time)**: movement 배분량 q는 green/cycle·saturation으로 환산되며 min/max green 범위.
```text
(g_min[l,m] / Cl[l]) * s[l,m]  <=  q[l,m]  <=  (g_max[l,m] / Cl[l]) * s[l,m]
```
(`g_min/max`=movement min/max green, `Cl`=cycle length, `s`=saturation flow rate.)

**Solver**: PSO(Particle Swarm Optimization, Kennedy & Eberhart 1995). 목적함수가 norm 비율이라
비볼록 → 메타휴리스틱. (구현 비용이 크면 동등 목적의 소규모 최적화/좌표하강 등 대체 가능하나,
**큐비례 1회식은 부적합** — 반드시 J(Eq 9)를 *최소화*하는 탐색이어야 함.)

## 코드 변경 지시

1. **density 벡터 정의**: 각 movement m의 density `k_m = (해당 링크 차량수) / (링크 저장용량)`
   (점유율). inflow movement 집합·outflow movement 집합을 토폴로지에서 도출(확장망: gate 교차로의
   진입=inflow, 보호망 이탈=outflow — `extended_network_proposal.md` 기준으로 재정의).
2. **`urban_follower._allocation` 재작성**: 큐비례 분배 제거. 대신
   - 결정변수 = movement별 배분량 q(=green 환산), 탐색 = PSO,
   - 목적 = Eq 9(B_in² + B_out²), 제약 = Eq 10(N_des, `eps_U`) + Eq 11-14(green 범위),
   - `N_des` = `urban_accumulation_feedback_flow(...)`(기존 재사용).
3. **출력**: spec대로 `inflow_outflow_allocation`(movement→배분량)과, §3.3 연계 시 green time.
   plant 소비부(`urban_queue_model._movement_capacity_flow`)와 단위 일관.
4. spec `04_controller.md §4.4`의 B_in/B_out·J_balance가 이미 Eq 9이므로 그걸 기준으로(spec 정정 불필요).

## 검증
- density balance 지표(`B_in`,`B_out`, `CV_boundary`)가 **실제로 감소**(큐비례 대비). 모든 movement
  density가 균등에 수렴하는지.
- Eq 10 만족: `|Σ(in−out) − N_des| ≤ eps_U` (현재 큰 net_inflow tracking error가 줄어드는지).
- green 범위(Eq 11-14) 위반 0.
- 단위 테스트: 인위적 density 불균형 입력 → 배분 후 B_in/B_out 감소 + 제약 충족.
- 통합: 확장 토폴로지에서 boundary balance(CV/Overflow)가 baseline 대비 개선되는지.

## 주의
- 현재 큐비례가 round-6에서 CV를 0.064까지 낮춘 건 사실이나, 이는 N_P_crit 수정 덕이지 §3.2 구현이
  아니다. §3.2(density sparsity + PSO + Eq 10 제약)는 별개이며 net inflow tracking을 정식 제약으로 잡는다.
- PSO는 매 제어주기 호출되므로 입자수·iteration을 작게(소규모 movement 수) 잡아 비용 관리.
