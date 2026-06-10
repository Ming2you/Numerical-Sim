# Follower 공간 분산화 제안 — 교차로/세그먼트 단위 agent (확장 네트워크 기준)

대상: Codex. 목적: 모놀리식 "1 freeway + 1 urban follower"를 Wu et al.(2022) §IV식 **교차로/세그먼트
단위 agent 분산**으로 재구현한다. **전제: 먼저 [extended_network_proposal.md](extended_network_proposal.md)의
확장 6-교차로 grid 토폴로지가 반영돼 있어야 한다**(현재 4-신호 config 기준의 기존 구현은 폐기).
배경·식은 [wu2022_distributed_reference.md](wu2022_distributed_reference.md) §3~7 참조.

## ★ 현재 구현(`distributed_coordinator.py`)의 문제 (재구현 필요)
- `build_agent_specs`가 movement를 `signal` 필드로 묶는데 on-ramp movement의 `signal`이 "R1".."R4"라
  on-ramp가 고아가 되고 freeway agent가 유령 `U_R1`..`U_R4`를 참조. → partition 깨짐.
- agent 수도 틀림(4-신호 config 기준). 확장망은 **urban 5 + freeway 6**.
- local solve가 모놀리식 follower에서 자기 변수만 추출 — 진짜 local 최적화 아님.
→ 토폴로지 정정 후 아래 배치로 **재구현**.

## 1. agent 배치 (확장 네트워크)

**Urban agent 5개** (통제 교차로당 1개): `U_A, U_B, U_C, U_D, U_F`. **E는 agent 없음**(비통제 통과 노드).
**Freeway agent 6개** (세그먼트당 1개): `F_W0, F_W1, F_W2, F_E0, F_E1, F_E2`.

- on-ramp는 중간 세그먼트(W1,E1) merge, off-ramp는 마지막(W2,E2) 분기. D·F 램프는 FW_W·FW_E 둘 다 연결.

## 2. agent별 결정 / 상태 / 목적

**Urban agent U_i** (i ∈ {A,B,C,D,F})
- 결정: 신호 i의 green split·offset φ_i·movement allocation.
- 상태: 자기 교차로 movement 큐(grid 진입/통과/회전) + 자기 접근부 storage + (D/F면) x_on(on-ramp 회전 큐)·off-ramp storage.
- 목적(자기 TTS): 자기 movement 큐 + **x_on**(접근부) + **off-ramp storage/배출** + 제어 평활.
- 제약: green 범위·cycle 합, 경계/순유입 몫.

**Freeway agent F_{m,s}** (세그먼트 s of link m)
- 결정: 세그먼트 VSL. (merge 세그먼트 W1/E1: + 램프 metering. off-ramp 세그먼트 W2/E2: + off-ramp 경계.)
- 상태: 자기 세그먼트 ρ/v/q(차량수 N), (merge면) **w_r**(자기 램프 큐), (off-ramp면) off-ramp 수용용량.
- 목적(자기 TTS): 자기 세그먼트 N + **w_r(자기 램프 큐)** + density 초과 penalty + VSL/metering 평활.
- 제약: VSL set·변화율, metering 범위, 차량 보존(N=ρ·L·λ).

> delay 귀속(확정): x_on→urban, **w_r→freeway**, off-ramp→urban. 총 TTT 불변, 귀속만 재배분.
> (현 코드는 w_r을 urban에 넣음 → freeway agent로 이동해야 metering 유인이 생김, Wu §IV-C와 일치.)

## 3. 결합변수 (`CouplingVars`, 교환·고정 대상)

```text
# urban ↔ freeway (램프) — D·F가 양 freeway에 붙으므로 양쪽과 결합
U_D, U_F → F_W1, F_E1 :  u_on   # x_on에서 green이 보내는 on-ramp 유입(→ w_r)
F_W2, F_E2 → U_D, U_F :  q_off  # off-ramp 유출(→ 교차로 도착) + off-ramp 수용용량
# freeway 세그먼트 간 (intra-link, 강결합)
F_{m,s} ↔ F_{m,s+1} :  boundary ρ, v  # METANET convection(상류 v)·anticipation(하류 ρ)
# urban grid 인접 (교차로 간 흐름; E는 비통제라 단순 전달)
U_A↔U_B, U_B↔U_C, U_A↔U_D, U_C↔U_F,  (U_D–E–U_F, U_B–E–…: E 경유 흐름)
                      :  인접 교차로 간 movement 유출/큐
```
각 agent는 **이웃 결합변수를 풀이 동안 상수로 고정**하고 자기 문제만 푼다.

## 4. 조율 루프 — `DistributedCoordinator` (Wu §IV-D 6단계, `NashSolver` 대체)
```text
ỹ ← 직전 제어주기 값으로 초기화
for s in 1..S_max:
    for agent in (U_A..U_F, F_W0..F_E2)  (병렬 가능):
        z̃ = 이웃에게 받은 ỹ (고정)
        (control_agent, ỹ_out) = agent.local_solve(state_agent, z̃)   # 자기 변수만 최적화
    ỹ ← 모든 agent ỹ_out 교환
    if ‖Δỹ‖ < eps  or  s > S_max: break
각 agent first-step control 적용
```
- 수렴은 control diff가 아니라 **결합변수 변화 ‖Δỹ‖** 기준. 미수렴 시 best-so-far + `nash_converged=false`.
- 주의(세그먼트 강결합): 한 freeway 링크의 세 세그먼트는 매 METANET 스텝마다 강결합 → 6 agent가
  경계 ρ/v를 교환하면 정보 전파에 반복이 더 필요할 수 있음. S_max·tol 적절히, 필요 시 링크 내 세그먼트는
  순차 sweep(가우스-자이델)로.

## 5. 재사용 / 신규
- 재사용: 경량 freeway 예측(`_lightweight_transition`)을 **세그먼트 1개로 제한**해 freeway-agent local solve로;
  urban green/offset/alloc 로직을 **교차로 1개로 제한**해 urban-agent local solve로. 2저수지(x_on/w_r)는 plant에 이미 있음.
- 신규: `build_agent_specs` **재작성**(on-ramp를 제어신호=phase 기준으로 묶고, E 제외, 세그먼트 agent 생성),
  `CouplingVars` 인터페이스, `DistributedCoordinator`.
- 리더: N_P_star(누적목표)·N_UF_star를 agent별 몫으로 분배.

## 6. 진단 / 검증
- 진단: `nash_per_agent_active`, agent별 `local_objective`, `coupling_residual`(‖Δỹ‖), `s_iterations`,
  "U_D/U_F가 q_off에, F_W1/F_E1이 u_on에 실제 반응했는지" 플래그, partition 자동검사(고아 movement 0,
  유령 이웃 0, 이웃 대칭).
- 검증: (a) coordinator가 agent별 local solve+ỹ 교환으로 도는지, (b) 2-블록 대비 동등 이상(TTT 악화 없음),
  (c) genuine 상호 best-response(U가 q_off에/F가 u_on에 반응), (d) delay 귀속(freeway TTT에 w_r, urban에 x_on·off-ramp).
- partition 자동검사 단위 테스트 필수(현 버그 재발 방지): 모든 on-ramp가 정확한 urban agent에 귀속,
  freeway agent 이웃이 실재 urban agent(U_A..U_F), 이웃 대칭.

## ★ 솔직한 전제 (유지)
이 망 크기에선 분산화로 속도 이득 거의 없음. 가치 = genuine per-agent Nash(shallow Nash 해소) +
Wu 충실도 + 확장성. 성능(FAIL 지표)을 직접 고치는 작업은 아님 — 구조 정합성·연구 충실도를 위한 것.
