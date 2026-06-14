# Wu et al.(2022) 분산 통합제어 — 구현 참조 가이드

출처: Na Wu, Dewei Li, Yugeng Xi, "Distributed Integrated Control of a Mixed Traffic
Network With Urban and Freeway Networks," IEEE T-CST, vol.30, no.1, 2022.

이 문서는 Codex가 현재 중앙집중(2블록) 컨트롤러를 **공간 분산(agent 단위)** 으로
재구성할 때 따라 짤 수 있도록, 논문 §II~V를 구현 관점으로 정리한 것이다. 식 번호는
논문 기준. 마지막 절에 이 repo 네트워크로의 매핑을 둔다.

---

## 0. 왜 가벼운가 (핵심 한 줄)

중앙집중(CC)은 전체 망의 단일 비선형 최적화라 무겁다(논문 §V-C: 최대 CPU >400s).
분산(CD)은 **망을 agent로 쪼개 각 agent가 자기 변수만 푸는 작은 문제**로 만들고,
**이웃과의 결합변수는 풀이 동안 상수로 고정**한 채 iteration 사이에만 교환한다
(최대 CPU <40s, 100배). 핵심은 "결합을 이웃 재시뮬로 반영"하지 않고
"**경계변수 고정 + 반복 합의**"로 반영한다는 점이다. → 현재 코드처럼 후보마다
전체 결합 plant를 재시뮬하면 안 된다.

---

## 1. 예측 모델 (§II)

- 도시: S-model. 링크 `(u,d)` 차량수 `n_{u,d}`, 스트림 큐 `l_{u,d,o}`를 식(1)~(4)로 갱신.
  방출률 `α^leave_{u,d,o}`는 green·포화유율·하류 수용공간의 min(식3).
- 고속: 비목적지 METANET. 밀도/속도/유출 식(5)~(10). 합류(식9)·분기(식10) 경계항.
- on-ramp: 큐 보존 식(14), 유입 `α^enter_{u,m}`은 **상류 도시 교차로 방출률과 동기화**
  (식15), 유출 `α^leave_{u,m}`은 하류 freeway 밀도로 제한(식16,13).
- off-ramp: 큐 보존 식(17), 유출은 하류 교차로 신호로 제어(식3), 유입은 상류 freeway
  세그먼트 유출(식18~20).
- **off-ramp spillback(식22, 핵심 확장)**: off-ramp `(m,d)` 차량수가 임계 초과 시
  상류 freeway 세그먼트 `(m,N_m)`의 **차로수 `λ_{m,N_m}`를 λ_m→λ_m−1로 감소**시켜
  용량 저하·spillback을 표현. 혼잡 해소 시 복원.

> 현재 repo는 이미 METANET·movement-queue·2저수지 on-ramp·off-ramp storage를 갖췄으니
> 모델은 대체로 대응됨. (식22 차로수 감소형 spillback은 현재 storage-cap 방식과 다르나
> 효과는 유사.)

---

## 2. 중앙집중 MPC (§III) — 분산화의 출발점

- 목적함수 J(식24) = TTS(origin·mainline·urban·on/off-ramp 차량수 합) + 제어변화 패널티
  `Σ (Δu)^T R (Δu)`. 제어 `u = [vlim_1..vlim_|L|, g_1..g_|V|]`.
- 제약: 차량수/큐/밀도/속도 범위(식25,26), green 범위(식27), VSL 범위·변화율(식28,
  **VSL 감소만 제한, 증가는 무제한**).
- 제어주기 `T_c = N_c · lcm(T_u,T_f)`(식23).
- 이 단일 문제를 SQP로 풀면 무겁다 → §IV에서 분해.

---

## 3. 분할 규칙 (§IV-A) — "어떻게 쪼개나"

**Urban agent i** (= 교차로 단위):
- agent i = 교차로 i + i로 들어오는 링크들. **i로 들어오는 off-ramp `(m,i)`도 agent i 소속.**
- 이웃: urban 이웃 `N^u_i` = 교차로 j→i 도로가 있는 j. freeway 이웃 `N^f_i` = i에서
  나가는 on-ramp가 향하는 링크를 가진 freeway agent p, 또는 p의 링크에서 나오는
  off-ramp가 i로 향하는 p.

**Freeway agent p** (= 연속 링크 묶음):
- agent p = **연속된 freeway 링크들 + 인접 on-ramp들**, 단 **off-ramp는 p당 최대 1개**.
  origin 링크가 인접하면 포함.
- 이웃: freeway 이웃 `N^f_p` = p의 링크의 상/하류 링크를 가진 agent h. urban 이웃
  `N^u_p` = p를 이웃으로 갖는 urban agent.

> 분할 원칙: 한 agent가 푸는 변수 수를 작게(교차로 1개분 green / 링크 몇 개분 VSL),
> agent 간 결합은 on/off-ramp와 freeway 링크 경계로 국한.

---

## 4. agent별 상태·제어·상태방정식 (§IV-B)

**Urban agent i**:
- 상태 `x^u_i = [n_i^T, l_i^T]^T` (링크 차량수, 스트림 큐), 제어 `u^u_i = g_i` (green).
- 상태식 `x^u_i(k+1) = f^u_i(x^u_i, u^u_i, y^u_{ji}, y^f_{pi}, d_i)` (식30).
  - `y^u_{ji}` = 이웃 urban agent j의 방출률 `α^leave_j` + 차량수 `n_j`.
  - `y^f_{pi}` = 이웃 freeway agent p의 유출 `q_p` (off-ramp로 들어오는 흐름).
  - `d_i` = 외부 수요.

**Freeway agent p**:
- 상태 `x^f_p = [ρ_p^T, v_p^T, n_{i,m}^T, n_o]^T` (밀도, 속도, on-ramp 큐, origin 큐),
  제어 `u^f_p = vlim_p` (VSL).
- 상태식 `x^f_p(k+1) = f^f_p(x^f_p, u^f_p, y^f_{qp}, y^u_{ip}, d_o)` (식33).
  - `y^f_{qp}` = 이웃 freeway agent q의 밀도 `ρ_q`·속도 `v_q` (링크 경계).
  - `y^u_{ip}` = 상류 urban agent i의 방출률 `α^leave_i` + 차량수 `n_i` (on-ramp 유입원).

> **결합변수 = `y` 들이다.** 분산화의 전부는 "이 `y`를 매 후보마다 재계산(재시뮬)하지 말고,
> iteration 시작 시 이웃에게 받은 값으로 고정한다"는 것.

---

## 5. agent별 local 최적화 (§IV-C)

**Urban agent i** (MILP, CPLEX):
```
min_{ũ^u_i}  J_{i,local} = T_u Σ_{k=k0u}^{k1u} e_i^T n_i(k+1)
                          + Σ_k (u^u_i(k+1) − u^u_i(k))^T R_i (u^u_i(k+1) − u^u_i(k))
s.t.  식(25), (27), (30)        # 차량수/큐 범위, green 범위, 자기 상태식
```

**Freeway agent p** (NLP, SQP, 초기점 5개):
```
min_{ũ^f_p}  J_{p,local} = T_f Σ_{k=k0f}^{k1f} [ n_o(k+1) + Σ_{(i,m)} n_{i,m}(k+1)
                                               + Σ_{m∈Lp} Σ_t L_m λ_m ρ_{m,t}(k+1) ]
                          + Σ_k (u^f_p(k+1) − u^f_p(k))^T R_p (u^f_p(k+1) − u^f_p(k))
s.t.  식(26), (28), (33)        # 밀도/속도 범위, VSL 범위·변화율, 자기 상태식
```

각 agent는 **자기 목적·자기 제약·자기 상태식**만 푼다. 이웃 결합변수는 다음 절에서
고정값으로 들어간다.

---

## 6. 분산 MPC 알고리즘 (§IV-D) — "어떻게 합의하나"

agent i가 시각 `k_c`에 제어를 정하는 절차(모든 agent 병렬 수행):

```
1) 현재 local 상태 x_i(k_c) 취득. iteration s=0.
   이웃 결합변수 초기화: ỹ_ij^(0) := 직전 제어시각의 실제값 ỹ_ij(k_c−1).
2) 이웃 j와 통신: ỹ_ij^(s) 송신, ỹ_ji^(s) 수신.
3) 추정 결합변수 고정: z̃_ji^(s) := ỹ_ji^(s).          # ← 풀이 동안 상수
4) local 최적화:
     (ũ_i^(s+1), ỹ_ij^(s+1)) = argmin  J_{i,local}(x_i, ũ_i, ỹ_ij^(s+1), z̃_ji^(s))
                                        + J_{i,inter}
   J_{i,inter} = ‖ỹ_ij^(s+1) − ỹ_ij^(s)‖²_{P_i}        # 수렴 가속항 (식34)
5) 종료판정: ‖ỹ_ij^(s+1) − ỹ_ij^(s)‖ < ε  또는  s > S_max(=5).
   미충족이면 s←s+1, 2)로. 충족이면 6).
6) ũ_i*(k_c)의 첫 샘플을 적용. 다음 시각으로.
```

요점:
- **step3에서 이웃 결합변수를 고정**한 뒤 step4에서 자기 문제만 푼다 → 전체망 재시뮬 없음.
- agent 간에는 **결합변수 `ỹ`(몇 개 흐름/밀도/큐 값)만 교환**한다.
- 수렴 안 되면 `S_max=5`에서 끊고 suboptimal 적용(실시간성 보장).
- Nash 균형: 수렴 시 균형, 미수렴 시 각 agent가 자기 목적을 최소화한 준최적해.

---

## 7. 이 repo 네트워크로의 매핑 (구현 지시)

현재 망: freeway 링크 FW_W·FW_E, 신호 A·B·C·D·F(E는 비신호), on-ramp R_D_W·R_F_W·R_D_E·R_F_E,
off-ramp OR_D_W·OR_F_W·OR_D_E·OR_F_E.

**제안 분할**:
- **Urban agent 5개** = {A, B, C, D, F} 각 1개. 각 agent = 그 신호 + 진입/유출 movement +
  D/F의 경우 자기 교차로 on-ramp movement와 그 교차로로 들어오는 off-ramp movement.
- **Freeway segment agent 6개** = {F_W0, F_W1, F_W2, F_E0, F_E1, F_E2}.
  F_W1/F_E1은 on-ramp merge segment, F_W2/F_E2는 off-ramp boundary segment를 담당한다.

**결합변수 `y` (agent 간 교환할 것)**:
- urban i → freeway p: on-ramp로 보내는 방출률 `α^leave_i`(=현재 2저수지의 `u_on`),
  교차로 차량수.
- freeway p → urban i: off-ramp 유출 `q_off`(현재 `offramp_flow_*`), 경계 수용용량.
- freeway p ↔ freeway q: 링크 경계 밀도/속도(FW_W 마지막 세그먼트 ↔ FW_E 첫 세그먼트,
  연결돼 있다면).

**현재 코드 구조 변경 지점**:
1. `FreewayFollower`/`UrbanFollower`를 "전체 한 solve"에서 **agent별 solve**로 분리.
   각 agent solve는 자기 링크/교차로 변수만, 이웃 결합변수는 인자로 받은 고정값 사용.
2. `_transition_node`의 **full `run_coupled_interval` 호출 제거** → 자기 서브망만
   전진하는 local plant(freeway agent는 freeway_substep + 고정된 off-ramp용량·on-ramp
   유입; urban agent는 urban_substep + 고정된 off-ramp 유입·freeway 유출).
3. `nash_solver`를 §IV-D 6단계 루프로 교체: 결합변수 고정→agent별 local solve(병렬 가능)
   →`ỹ` 교환→`‖Δỹ‖<ε ∨ s>S_max` 종료. 현재의 control-value relaxation 대신
   **결합변수 합의**로 수렴 정의.
4. 리더(N_P_star/N_UF_star)는 유지하되, 후보 열거 비용이 크면 agent 합의 후 평가하는
   구조로 축소.

> 이렇게 하면 한 decision의 비용이 (현재) 리더×Nash×빔×전체망재시뮬 ≈ 2만+ coupled 호출
> 에서, (Wu식) agent수×S_max×local solve(작음) 수준으로 떨어진다.

---

## 8. 주의 / 현재 모델과의 차이

- Wu의 off-ramp spillback은 차로수 감소(식22), 현재 repo는 off-ramp storage cap 방식.
  둘 다 "off-ramp 혼잡 → freeway 유출 제한"을 표현하므로 호환되나, 문서에 명시.
- Wu는 VSL 변화 제약이 **감소 방향만**(증가 무제한, 식28). 현재 repo는 양방향
  `max_vsl_step`. 의도적 차이면 리포트에 기록.
- Wu의 local solver는 MILP/SQP(gradient). 현재 repo의 freeway 빔서치는 유지해도 되나,
  **이웃 결합변수를 고정**하고 **자기 서브망만** 평가하도록 바꾸는 게 비용 절감의 핵심.
- **freeway local objective는 Wu 순수 TTS**(`Σ L·λ_eff·ρ`=segment 차량수 + ramp 큐)
  + Δvsl 패널티로 정렬한다. 직전 구현에 있던 `density_penalty×pos(ρ−ρ_crit)` 항은
  Wu objective에 없는 비-Wu 항이라 제거했다(`FreewayFollowerConfig.density_penalty`
  config 키는 다른 proposed controller가 쓰므로 유지, WU-CD-F 코드에서만 미사용).
- **storage-aware probe**: freeway agent의 probe horizon 각 substep에서 off-ramp
  storage 점유를 off-ramp 유출(유입) + 하류 신호 drain(유출, 도시 receiving link
  가용공간으로 제약)으로 갱신해 `effective_lane_profile`이 capacity-drop(식22 등가
  차로수 감소)을 반영하게 한다. 이로써 VSL↓→다운스트림 유입↓→capacity-drop 회피→
  λ_eff 회복→본선 차량수↓가 TTS에 내생화되어, 별도 penalty 없이 혼잡 시 VSL이
  작동한다(직전 구현은 probe에서 storage 미갱신이라 VSL이 항상 max로 고정됐다).
- **per-segment VSL + 다운스트림 결합 (Option C)**: storage-aware probe만으로는 부족했다.
  link당 VSL 1값을 전 segment에 uniform 적용하면 병목 segment까지 같이 늦춰 mainstream
  metering이 불가능했고, 측정 결과 강한 capacity-drop(98% storage, λ_eff≈1.70)에서도
  VSL↓의 ΔTTS가 **정확히 0**이었다. 해결: (1) plant가 `segment_vsl(control, link, i)`로
  segment별 VSL을 읽도록 입자도 세분화(segment 키 없으면 link 키 fallback → 타 컨트롤러
  무변경), (2) `_solve_freeway_agent`가 segment 벡터를 탐색(병목 seg는 {max, prev}로
  제한해 q_out 회복 보존, 상류는 max_vsl_step 내 후보), (3) coupling `p_down_{link}`로
  병목 임계 초과 시에만 상류 metering(누적 seg1→seg2 유입)을 보상(메커니즘 B). 이 결과
  상류 segment VSL↓의 ΔTTS가 음수가 됐다(seg0 100→80에서 −5.2, 100→50에서 −24.9; 직전
  0.00000). 단, VSL은 free-flow 가지(ρ<ρ_crit)에서만 metering이 성립하므로(congested
  가지는 q≈보존) 본선 전체가 과포화되면 이득은 다시 0으로 수렴한다 — 이는 정직한 물리
  한계이며, capacity_drop 시나리오(점유 ~22%, λ_eff≈1.98)는 이 망이 심한 capacity-drop을
  잘 만들지 않음을 보이는 정직 근거이고, VSL 작동 실증은 test_c의 강제 98% 상태로 한다.
