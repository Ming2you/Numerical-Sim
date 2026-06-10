# Follower 공간 분산화 제안 — 교차로/링크 단위 agent

대상: Codex. 목적: 현재 "1 freeway follower + 1 urban follower" 모놀리식 2-블록을 Wu et al.(2022)
§IV식 **교차로/링크 단위 agent 분산**으로 바꾼다. 상세 배경·식은 `docs/wu2022_distributed_reference.md`
§3~7 참조. 이 문서는 그걸 **현재 코드 기준 구현-스펙으로 확장**한 것.

## 현재 상태 vs 목표
- 현재: `FreewayFollower`(R1~R4·FW_W·FW_E 합동) + `UrbanFollower`(A·C·D·F 합동), `NashSolver`가
  relaxation으로 반복. freeway는 경량 예측(고정 경계), urban은 pressure 스칼라 소비.
- 목표: **urban agent 4 + freeway agent 2**, 각자 자기 변수만 local solve + 경계변수 교환(Wu §IV-D).

## ★ 솔직한 전제 (구현 전 인지)
이 망 크기(4신호+2링크)에선 경량화 이후 이미 ~17초/decision이라 **분산화로 속도는 안 빨라진다.**
가치는 ① **genuine per-agent Nash**(서로의 응답을 실제로 반영 — 기존 shallow Nash 해소),
② **Wu 분산 아키텍처 충실도(연구 본질)**, ③ **확장성 시연**. 현재 FAIL 중인 freeway 성능을 고치는
건 capacity-drop(별도 제안)이며, **구현 우선순위는 capacity-drop이 먼저**.

## 1) agent 분할 (config 주도)
```yaml
agents:
  urban:   # 각 agent = 자기 신호 + 진입 movement + 그 교차로로 들어오는 off-ramp
    - id: U_A   signal: A   movements: [in_A_to_out_D, R1_onramp]
    - id: U_C   signal: C   movements: [in_C_to_out_F, R2_onramp]
    - id: U_D   signal: D   movements: [OR_W_to_out_D, R3_onramp]
    - id: U_F   signal: F   movements: [OR_E_to_out_F, R4_onramp]
  freeway: # 각 agent = 연속 링크 + 인접 on-ramp + off-ramp(≤1)
    - id: F_W   link: FW_W  ramps: [R1, R2]   off_ramps: [OR_W]
    - id: F_E   link: FW_E  ramps: [R3, R4]   off_ramps: [OR_E]
  neighbors:   # 이웃맵 (경계변수 교환 대상) — 상호 대칭이어야 함(X∈N[Y] ⇔ Y∈N[X])
    # urban -> freeway
    U_A: [F_W]            # R1 -> FW_W
    U_C: [F_W]            # R2 -> FW_W
    U_D: [F_W, F_E]       # R3 -> FW_E(on-ramp) + OR_W from FW_W(off-ramp 수취)
    U_F: [F_E]            # R4 -> FW_E + OR_E from FW_E(off-ramp 수취)
    # freeway -> urban
    F_W: [U_A, U_C, U_D]  # R1<-A, R2<-C, OR_W->D
    F_E: [U_D, U_F]       # R3<-D, R4<-F, OR_E->F
    # urban<->urban: 이 topology엔 신호 간 직접 연결 도로 없음 → 생략
```
(매핑은 현재 `urban_movements`/`on_ramp_to_movement`/`off_ramp_*` config에서 자동 유도 가능.)

## 2) agent별 결정변수 / 상태 / local 목적
- **Urban agent U_i**: 결정 = 신호 i green(`i_p1`,`i_p2`)·offset i·자기 movement allocation.
  상태 = 자기 movement 큐 + 진입 storage. 목적 = 자기 TTS 기여(누적) + 제어 평활 + 자기 경계 잔차.
- **Freeway agent F_p**: 결정 = 링크 VSL·자기 램프 metering. 상태 = 자기 3세그먼트 ρ/v/q + 램프 큐
  + off-ramp storage. 목적 = 자기 freeway TTS + density 초과 penalty + 평활.

## 3) 결합변수 인터페이스 (교환·고정 대상) — `CouplingVars` dataclass
```text
U_i -> F_p : u_on[r]     # 신호 i의 on-ramp phase 방출 = 램프 r 유입 (veh/h 또는 veh/step)
F_p -> U_i : q_off[r]    # off-ramp r 유출 = 교차로 i 도착
U_i <-> U_j: 인접 교차로 간 흐름(A->D, C->F)  # 현재 topology의 through movement
F_p <-> F_q: 링크 경계 밀도/속도              # 현재 FW_W·FW_E 독립이라 비어 있음(직렬 결합 시 채움)
```
각 agent는 **이웃 결합변수를 풀이 동안 상수로 고정**하고 자기 문제만 푼다.

## 4) 조율 루프 — `NashSolver` → `DistributedCoordinator` (Wu §IV-D 6단계)
```text
ỹ <- 직전 제어주기 값으로 초기화
for s in 1..S_max:
    for agent in all (병렬 가능):
        z̃ = 이웃에게 받은 ỹ (고정)
        (control_agent, ỹ_out_agent) = agent.local_solve(state_agent, z̃)   # 자기 변수만
    ỹ <- 모든 agent의 ỹ_out 교환
    if ‖Δỹ‖ < eps  or  s > S_max: break
각 agent의 first-step control 적용
```
- 수렴은 control diff가 아니라 **결합변수 변화 ‖Δỹ‖** 기준으로(기존 mixed-unit residual 문제 해소).
- 미수렴 시 best-so-far 적용 + `nash_converged=false`.

## 5) 재사용 / 리팩토링 범위
- **재사용**: 경량 예측(`_lightweight_transition` + `_apply_onramp_boundary_forecast` +
  `off_ramp_capacity_by_freeway_link`)이 이미 "이웃 경계 고정" 구조 = freeway-agent local solve의 뼈대.
  `FreewayFollower`를 **링크 1개로 제한**해 호출. `urban_follower._green_times`는 이미 신호별 계산이라
  **신호 1개로 제한**해 urban-agent local solve로.
- **신규**: `CouplingVars` 인터페이스, `DistributedCoordinator`(현 `nash_solver.py` 대체),
  agent 분할/이웃맵 config 로더.
- **리더**: N_P_star/N_UF_star 유지하되 agent별 타겟으로 분배(urban agent엔 자기 몫 누적목표,
  freeway agent엔 자기 램프 N_UF 몫).

## 6) 진단 (구현 검증용)
`nash_per_agent_active`, agent별 `local_objective`, `coupling_residual`(‖Δỹ‖), `s_iterations`,
그리고 "freeway가 urban의 u_on을, urban이 freeway의 q_off를 실제로 반영했는지" 플래그.

## 검증 (구현 후, 다음 라운드)
1. coordinator가 agent별 local solve + ỹ 교환으로 도는지(진단 플래그).
2. 결과가 2-블록 대비 **동등 이상**(TTT 악화 없어야 — 분산화는 성능 개선이 아니라 구조 변경).
3. per-agent best-response가 실제 상호 반영되는지(U_i가 q_off에, F_p가 u_on에 반응).
4. (선택) 더 큰 합성망에서 agent 수 늘렸을 때 decision 비용이 전체망 재시뮬보다 완만히 증가하는지.

## 구현 상태 — 2026-06-10

- `src/controllers/distributed_coordinator.py`에 1차 distributed player가 구현됐다.
- `mpc.follower_solver_mode: distributed`로 활성화한다. 기본값은 이전 결과 보존을 위해 `two_block`이다.
- agent partition은 현재 topology에서 자동 유도한다.
  - urban agents: `U_A`, `U_C`, `U_D`, `U_F`
  - freeway agents: `F_W`, `F_E`
- coordinator는 coupling variables를 교환하고 normalized coupling residual로 반복 종료를 판단한다.
- diagnostics:
  - `distributed_player_active`
  - `nash_per_agent_active`
  - `distributed_coupling_residual`
  - `distributed_urban_agent_count`
  - `distributed_freeway_agent_count`
  - `agent_*_objective`

남은 차이:

- Urban agent는 아직 MILP가 아니며, 기존 `UrbanFollower` 휴리스틱 결과에서 자기 signal/movement 변수만 추출한다.
- Freeway agent는 아직 SQP/NLP가 아니며, 링크별 local heuristic으로 ramp metering/VSL을 산정한다.
- agent별 `N_P_star` 분담이 약해 distributed smoke에서 boundary net inflow tracking은 아직 실패한다.
