# RL 코드 검토 (src/rl/ Stackelberg RL) — 2026-06-23

Codex가 추가한 `src/rl/` (Stackelberg RL environment, spec 19) 감사 결과.

## 요약 판정

- **구조·통합은 정확하고, 테스트도 통과한다.** import OK, `src/tests/test_rl_environment.py` 10/10 pass.
- **leader·follower 모두 RL agent다** (follower-only 아님 — 아래 1번).
- **단, leader N_P★ action grid가 너무 넓고(거의 도달 불가) 거칠다** — 보완 권고(아래 3번).

---

## 1. 아키텍처: leader·follower 모두 RL agent (중요 정정)

- **follower agents**: `build_rl_agent_specs`가 freeway segment actor + urban intersection actor를 topology에서
  유도(`src/rl/agents.py`). 각자 로컬 green/VSL/ramp metering 이산 action space.
- **leader agent**: 별도 `LeaderDiscreteActionSpace`(`src/rl/action_space.py`) — `(N_P★, N_UF★)`를 이산 격자로.
  spec 19도 "use DDQN as an initial leader policy learner"(§DDQN guidance), "train follower agents with
  scripted or sampled leader targets"(curriculum)로 **leader+follower 둘 다 RL**임을 명시.
- `env.step(leader_action_index, follower_action_indices)`가 **두 계층의 action을 동시에** 받는다 →
  multi-agent Stackelberg RL **환경**(leader 1 + follower N).
- 현재 milestone은 spec대로 **"DDQN-ready action-space 정의·매핑"까지**이고 신경망 학습은 아직(§milestone).
  즉 환경+행동 인터페이스는 완성, 학습 루프는 다음 단계.

→ "follower만 RL"이 아니라 **leader도 RL agent**다. (앞선 구두 설명의 부정확함을 정정.)

## 2. 정확하게 구현된 부분

| 항목 | 확인 |
|---|---|
| `env.step` 순서 | Stackelberg(leader target → follower local obs/action → plant) 보존 |
| plant | 기존 `MixedTrafficSimulator.step`(=`run_coupled_interval`) 그대로 — 별도 물리 없음 |
| 글로벌 TTT | `global_step_ttt = freeway_ttt + urban_ttt` (시스템 공통 정의와 동일) |
| **reward 분해** | leader = −(global TTT + freeway 밀도초과 + urban half-cap TTS) = **MPC leader objective와 동일 항**; follower = **로컬 TTS만**(freeway: 자기 segment/ramp/origin/off-ramp; urban: 자기 movement/link/boundary) → Stackelberg 게임 분해 정확 |
| half-cap | 0.5·cap 초과분(MPC `mfd_penalty_mode=all_urban_halfcap`와 동일 기준) |
| observation | leader=global, follower=local(테스트 `follower_observations_are_local` 통과) |
| `nash_probe` | ε-Nash = max_follower(일방 일탈 best − 실현, ≥0); 매 probe마다 `sim.copy()`로 상태 저장·복원(오염 없음, 테스트 통과) |
| E 노드 | controlled actor에서 제외(plant/이웃요약에는 유지) — spec 준수 |

## 3. 보완 권고: leader N_P★ action grid (퇴화 주제 재등장)

`LeaderDiscreteActionSpace._build_actions`는 `cfg.leader.N_P_star_range = [−3500, 3500]`을 균일 5등분한다
→ bins **{−3500, −1750, 0, 1750, 3500}**.

- 그러나 **물리적으로 달성 가능한 horizon-net-inflow는 훨씬 좁다**: 혼잡 state에서 uniform-green 스냅샷
  기준 ≈ **[260, 380] veh**, 수요-aware reachability(MPC leader가 쓰는 값) 기준 ≈ **[−528, 921] veh**.
  즉 bins −3500/−1750/1750/3500은 **도달 불가 net-inflow를 타겟**한다.
- **단, RL 맥락에서 N_P★는 plant 직접 입력이 아니라 follower의 *관측 신호*다**(`compose_control_action`는
  N_P★를 control에 붙이지만 plant는 green/VSL/metering만 소비). 따라서 "물리적 saturation 퇴화"는
  MPC(여기선 N_P★가 *추종 setpoint*라 강하게 퇴화)보다 **약하다** — N_P★는 follower가 학습해 반응하는
  coordination vocabulary다.
- 그럼에도 우려: (a) 5 bin이 7000 veh 폭을 1750 간격으로 → **유용한 운전영역(수백 veh) 부근 해상도가
  거의 없음**, (b) follower가 어떤 N_P★ 신호를 받아도 *물리적으로 실현 가능한 net-inflow는 bounded*라
  극단 bin들은 비슷한 follower 응답을 유도할 가능성 → **outcome 수준 유효-퇴화**.
- **현재로선 경험적 확정 불가**: follower 학습 정책이 아직 없어(random/scripted) N_P★ 신호 반응을 측정할
  수 없다. 학습 후라야 bin 붕괴 여부를 실측 가능.

**권고**:
1. N_P★ bin **범위/밀도를 유용 영역에 맞춘다** — 정적 [−3500,3500] 균일 대신 reachability 영역
   (예: [−600, 1000]) 또는 per-state reachability(MPC leader 수정과 일관)로 bin 배치.
2. 또는 bin 수를 늘려(예: 7–9) 유용 영역 해상도 확보.
3. N_UF★ bin([0,6000])은 leverage가 있어 그대로 두어도 됨.

## 4. "achievable net-inflow [260,380]을 넓힐 수 있나?"

net-inflow = Σ(inflow service) − Σ(outflow service)이고, urban green으로만 조절되므로 **green 권한 폭**에
물리적으로 묶인다.
- [260,380]은 *uniform-green 스냅샷*의 좁은 값. **수요-aware reachability는 이미 더 넓다([−528,921])** —
  큐+예측 도착을 반영하기 때문(이게 더 현실적인 상한). 혼잡/큐가 커질수록 자연히 넓어진다.
- 더 넓히려면 물리적 권한을 키워야 한다: (a) green_min/green_max 폭 확대(현 [20,92]/cycle 120),
  (b) 경계 게이트 metering을 green 외 별도 자유도로(현재 green 매개), (c) 더 높은 수요/큐 regime.
- **단 무리하게 넓히면 도달 불가 영역만 늘어** RL action(또는 MPC 탐색) 효율이 떨어진다. 권장은
  "물리 권한을 늘려 *진짜* 도달범위를 넓히되, action grid는 그 도달범위에 맞춰 배치"다.

## 부록: 검증 명령

```
python -B -c "import src.rl.env, src.rl.action_space, src.rl.agents, src.rl.observations, src.rl.rewards, src.rl.nash_probe"
python -B -m unittest src.tests.test_rl_environment -v   # 10/10 pass
```

## Follow-up Fix

The N_P action-grid recommendation above was addressed after this review. The
Stackelberg-RL DDQN pilot grid now uses compact `N_P_star` values
`[-100, 175, 450, 725, 1000]` while preserving the broader configured MPC
physical clipping range.
