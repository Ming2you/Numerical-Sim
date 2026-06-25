# Context Notes — leader↔follower setpoint 일치 작업 (2026-06-25)

작업 중 내린 결정과 근거를 누적 기록. 다음 세션이 재유도 없이 이어가도록.

## 배경 / 발단
- 사용자가 이전 결과 Fig 3A(Leader Targets and Realized Response)를 보다가
  **follower가 leader target을 못 따라간다**(특히 urban)고 지적. "hard constraint 아니었나?"
- 조사 결과 N_P*/N_UF* 모두 hard constraint가 아님이 확인됨.

## 코드 사실(검증 완료)
- N_P*는 urban follower에 **soft lexicographic 위반항**으로만 전달.
  `net_violation_veh = max(0, |projected_net_inflow − N_P*| − eps_U)`, eps_U=100.
  선택은 feasible 우선 → 안 되면 least-violating (hard 필터 아님).
  ([distributed_coordinator.py](../src/controllers/distributed_coordinator.py) 803-805, 586-619)
- leader objective는 **realized rollout(predicted_states)의 TTT/누적/밀도**로 채점.
  추종오차 항 없음 → N_P*는 "약속"이 아니라 "제어입력(setpoint)".
  ([leader.py](../src/controllers/leader.py) 594-660)
- N_P* 후보 박스 = `_movement_net_flow_bounds`의 **디커플 over-approx** `[-Σout_servable, +Σin_servable]`.
  inflow max와 outflow zero를 동시 가정 → green 공유 때문에 결합 불가능. 박스가 느슨.
  ([leader.py](../src/controllers/leader.py) 331-384, 주석 382-384가 "디커플 over-approx" 명시)
- N_UF*는 **한쪽 ceiling**. 실현 = `min(N_UF*, ramp 가용대수, 하류 merge 수용)`.
  ([freeway_follower.py](../src/controllers/freeway_follower.py) 171-176, 234)
  → 조이는 방향(아래)으론 정확 추종, 푸는 방향(위)으론 공급한계까지만. 게이트지 펌프 아님.
  Fig 3A의 6000→4500 gap은 "풀개방 + 공급 4500" 실현이지 추종 실패 아님.

## 왜 urban(N_P) gap이 freeway(N_UF)보다 큰가
- N_UF는 액추에이터(ramp metering) 명령 → 단일 박스 사영, 충실 추종.
- N_P는 수많은 green에서 창발하는 net-balance → 직접 액추에이터 없음 + 디커플 over-approx 박스
  + 두 큰 유량의 차라 민감. 양방향 모두 약함.
- 기존 메모리와 일치: nash-coupling-gap(follower 분리형), setpoint-leader-design(f→u 재설계).

## authority probe (진행/판정 도구)
- `2026-06-25/diag_scripts/np_authority_probe.py`: PFO로 warmup→혼잡 state에서
  N_UF* 고정·N_P* 도달박스 스윕→각 후보 realized rollout_ttt/urban 기록.
- 검증런(warmup=2, 3점): intent [-530,936] → realized net inflow [295,550] (기울기 ~17%),
  total rollout 106.5→99.2. **권한 0 아님, 그러나 강하게 감쇠.**
- 본런: warmup=6(urban 448/freeway 255), 13×3. 결과로 층2(N_P 박스) 가치 확정.

## 설계 결정 (확정)
- 목표 = leader commit값이 follower 실현값과 일치(self-consistent Stackelberg).
- **층 1 출력 폐쇄**: best_eval의 realized 값을 commit. 커밋=realized 정확 일치. 무조건 적용.
- **층 2 박스 타이트닝**: 탐색박스를 도달집합으로. saturation 평원 제거 + intent 잔차 축소.
- **정정(중요)**: 층2가 intent=realized를 *eps까지* 맞추진 못함. 매핑이 감쇠라
  좁힌 박스 안에서도 잔차 ~수십~수백 veh. 정확 일치는 층1 몫. (앞서 "eps급"은 과장이었음)
- eps급 intent 일치(fixed-point/hard equality)는 leader 지렛대를 깎아 **불채택**.

## 층2 결과 (구현→반증→롤백, 2026-06-25)
- 2-probe 실측 도달범위로 N_P 박스 타이트닝을 구현(leader transient slot + orchestrator
  2-probe + `leader_empirical_np_box` flag)하고 sweet_128 검증.
- 박스는 정상 적용되나 **컨트롤러 동작/ TTT 비트 동일(454.6068)** → 무익. **전부 롤백.**
- **핵심 반증**: N_P가 안 쓰이는 건 평원 때문이 아니라 **leader가 PFO fallback(N_P=0)을 고르기**
  때문. authority probe의 N_P 권한은 `fallback=False` 조건의 산물. 실제(fallback ON)에선 PFO 우위.
- N_P 활용의 진짜 관문 = **fallback guard / leader objective 정렬**(박스 아님). 다음 후보.

## 미해결/주의
- 층2 N_P 박스 교체 시 단순 echo(권한 소멸) 되지 않게 — probe 권한 확인이 전제.
- capacity drop default ON(anticipation, nu_cong=250)은 미커밋 상태. leader 활성 regime이라 유지 중.
- sweet spot 결과(sweet_128 +17.6%)는 leader 가치가 전부 N_UF 채널에서 나옴(N_P*=0).
  → setpoint 일치 작업 후 sweet_128/135 정밀 재실행으로 재확인 필요.
