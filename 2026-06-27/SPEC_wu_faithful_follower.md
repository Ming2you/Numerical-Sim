# 명세: Wu(2022) 충실 분산 follower 구현 (새 코드만, 기존 미변경)

근거: Wu et al.(2022) §IV-D "Multiagent MPC" 최적화-통신 절차. 목표는 proposed Stackelberg leader는
그대로 두고, follower를 **Wu에 충실한 진짜 국소 분산**으로 새로 짠다. 기존 코드는 일절 수정하지 않고
새 파일로만 만든다.

## 0. 지난 실패의 원인(Wu와의 결정적 차이 3가지) — 이번엔 반드시 지킬 것
이전 시도가 느리고/무력했던 건 아래를 안 지켜서다.
1. **진짜 local이 아니었다.** 후보 채점을 `urban_step`/`run_coupled_interval`(전체망 전진)으로 했다.
   Wu는 agent i가 **자기 교차로 상태 x_i만** 국소동역학 f_i로 전진시킨다(이웃은 고정 입력). → O(n)의 핵심.
2. **목적이 global TTT였다.** Wu의 J_i,local은 **자기 agent 차량수 e_i^T n_i(자기 TTS)만**이다.
3. **결합 동결/반복(Jacobi+communication)을 안 했다.** Wu는 이웃 interaction 변수 z̃_ji를 고정해 풀고,
   교환→갱신을 S_max회 반복(Nash 추구).

## 1. Wu 알고리즘 (§IV-D, 그대로 구현)
각 control step k_c, 각 agent i:
1. 국소 상태 x_i(k_c) 취득. s=0. **interaction 변수 warm-start**: ỹ_ij^(0)(k_c) = ỹ_ij(k_c−1)
   (직전 step 수렴값).
2. 이웃 j와 통신: ỹ_ij^(s) 송신, ỹ_ji^(s) 수신.
3. 고정 결합변수 z̃_ji^(s) = ỹ_ji^(s) (이번 iteration 동안 **고정**).
4. agent i 국소 최적화:
   (ũ_i^(s+1), ỹ_ij^(s+1)) = argmin J_i,local(x_i, ũ_i, ỹ_ij, z̃_ji) + J_i,inter
   - **J_i,local = T_u Σ_{k} e_i^T n_i(k+1)  +  (Δu_i)^T R_i (Δu_i)**  ← 자기 차량수 합 + 제어변화 penalty.
   - J_i,inter = (ỹ_ij^(s+1) − ỹ_ij^(s))^T P_i (ỹ_ij^(s+1) − ỹ_ij^(s))  ← 수렴가속(자기 출력결합 급변 억제). 옵션.
5. 종료: ||ỹ_ij^(s+1) − ỹ_ij^(s)|| < ε  또는 s > S_max(=5). 아니면 s++, 2)로.
6. u_i* = ũ_i^(s+1), 첫 샘플 적용, 다음 step.
- **Jacobi**: iteration s 내 모든 agent가 동일 s값 결합을 입력으로 동시 풀이→동시 갱신.
- 파라미터: N_p=10, S_max=5, T_c=60s (우리 cfg값 사용).

## 2. 진짜 local rollout = per-signal plant stepper (핵심 신규 구현물)
agent i(=신호)에 대해, **신호 i의 movement 큐만** N_p×K_cu substep 전진:
- 상태: q_m  (m ∈ 신호 i의 movements; `state.urban_movement_queue`에서 복사).
- 도착 arr_m (고정 결합):
  - boundary_in movement: demand(`demand.urban_boundary[origin]`)×β.
  - 내부 movement(이웃 신호가 먹임): **이웃의 leaving flow(고정 z̃) × β**. 우리 `_coupling`의
    `arr_{signal}_{pid}`가 이미 이 결합량(이웃→신호 i 도착)을 phase 단위로 준다 → movement로 분배.
  - off-ramp/on-ramp 도착도 동일 취급(freeway 결합은 고정).
- 서비스 service_m = min(q_m,  green_fraction(phase(m))·cap_flow_m),  **하류 receiving 링크 S_eff로 cap**
  (spillback). 신호 i 자기 내부 링크 S_eff는 전진 중 갱신, **이웃 경계 링크 S_eff는 고정**(z̃).
  - green_fraction·cap_flow·S_eff·_effective_available_space 로직은 `urban_substep`(877–964행)을 참조해
    per-signal로 복제(전체망 호출 금지).
- 비용 J_i,local = Σ_substep (Σ_{m∈i} q_m) · dt  + R_i·|g_i − g_i,prev|.
- **반드시 신호 i 분량만 돈다**(B,C,D,F·freeway 전진 금지). 이게 검증 포인트 1.

## 3. partition / 이웃 / interaction 변수 (우리 망: 신호 A,B,C,D,F + FW_W,FW_E)
- urban agent = 신호 1개 + 그 신호로 들어오는 movements(+off-ramp).
- 이웃(urban): 신호 i로 가는 road의 upstream 신호 j. (토폴로지에서 도출; D_to_A 등 링크명으로.)
- 이웃(freeway): on/off-ramp로 i와 연결된 freeway agent.
- interaction 변수 y_ji = 이웃 j의 leaving flow(우리 `_coupling`의 arr 항) [+ 필요시 n_j]. freeway는 q_p(outflow).
- freeway agent: 1차 구현은 기존 VSL 방식 차용 가능(핵심은 urban local). 단 결합은 동일 규약으로 고정·교환.

## 4. 통합(기존 미변경 원칙)
- 새 파일: `src/controllers/wu_faithful_follower.py`(국소 stepper + agent solve + Jacobi 루프 + solve→NashResult),
  필요시 `src/controllers/local_signal_plant.py`(per-signal stepper 분리).
- proposed leader가 쓰게 하려면 어댑터/모드 등록이 필요하나 **기존 파일 수정 금지** 조건이므로,
  **검증은 새 standalone closed-loop 러너**(six_controller_comparison.run_controller를 복제한 새 스크립트)로 한다.
  - 러너는 cfg에 `relaxed_quantized_controls=True`(하네스와 동일) 필수.
  - leader=None(PFO 모드)부터 검증: follower 단독이 56 탈출 + 자기 TTS 감소.

## 5. 검증 기준 (서브에이전트 2가 확인)
- (V1) **진짜 local인가**: agent i solve가 신호 i movements만 전진시키는가? 전체망 plant 호출 없는가?
- (V2) **Jacobi/통신 맞나**: 한 iteration 내 결합 z̃_ji 고정·동시갱신, warm-start, S_max=5 종료조건.
- (V3) **목적이 자기 TTS인가**: J_i,local = Σ 자기 차량수(global TTT 아님). 제어변화 penalty R_i.
- (V4) **결과**: 하네스(또는 검증 러너)에서 green 56 탈출 + impr>0 + **eval/time이 per-agent라 실제로 적은가**
  (후보당 전체망 rollout이 아니라 신호1개 rollout → DistributedCoordinator보다 확연히 쌈).
- (V5) plant 충실도: per-signal stepper의 service/spillback이 `urban_substep`과 정성적으로 일치(하류 막힘→backup).

## 6. 불변
- 기존 코드 미변경(복제/참조만). plant 차량보존·단위 일관. 결정성(seed). 반드시 하네스/검증러너로 측정.
