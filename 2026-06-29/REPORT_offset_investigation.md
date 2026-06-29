# [리포트] offset 조사 — phase-resolved+platoon 충실화 + "offset은 leader-coordinated 양" 결론

2026-06-29. PFO follower에 offset을 충실히 모델링하려 시도. 결론: **per-signal offset은 무가치/해롭고, offset은 본질적으로 joint·leader-coordinated 양.** per-signal offset은 끄고(`offset_enabled=False`), phase-resolved+platoon 인프라는 향후 leader 레버용으로 보존.

## 동기 (사용자 지적)
초기 offset 구현이 잘못됨 — 메인 국소 rollout `rollout_local_tts`가 `green_fraction=green/cycle`(cycle 평균)이라 매 substep "지금 green/red"를 안 봐서 **offset이 inert**. 사용자 지적: phase-resolved(`is_green(time, offset)`) + corridor progression(상류 platoon→travel time→하류 정렬)을 모델링해야 offset이 의미 있음.

## (b) 구현 — phase-resolved + platoon (충실화 성공)
- `local_signal_plant.py`: phase-resolved 서비스(`_phase_green_fraction(urban_step_index)`, plant의 유일한 offset 진입점).
- `wu_faithful_follower.py` `_platoon_arrival_profiles`: 상류 신호 green+offset(snapshot)→방출 프로파일→`_link_delay_steps`(travel time τ) 지연→β분배. **예산 보존**(시간만 재분배). platoon이 τ-지연 집중 버스트(CV=1.30)로 재구성됨. offset이 platoon에 실제 정렬(A≈30,C≈30,B≈85~105).
- 메커니즘은 충실해짐.

## 결론 — per-signal offset은 무가치 (정직, 실측)
phase-resolved 메커니즘에도 **per-signal selfish offset은 closed-loop서 음수**(가드 끔, raw 측정):

| 수요 | offset 가치(on−off) |
|---|---|
| sweet_128 (대칭) | −0.10pp |
| west_skew 2:1 (경부하, 주류) | **−1.53pp** |
| west_skew 3:1 (고부하) | −0.10pp |
| **one-way 8:1 (고부하)** | **−0.166pp** |

**주류(main stream) 있어도 음수.** 사용자 "대칭이라 그런가" 가설 반증. 고른 offset이 green wave를 안 이룸(one-way서도 B=D=F=0).

**진짜 원인**: offset(green wave)은 **여러 신호가 일관되게 맞춰야 하는 joint 양**. per-signal selfish best-response는 각자 자기 큐만 봐서 corridor를 **de-coordinate**(오히려 해롭다). "main stream 빨리 내보내기"=green SPLIT(국소·작동)와 "corridor progression"=offset WAVE(joint·per-signal 불가)는 다르다.

## leader면 되나 — 된다, 단 이 망에선 미미
offset을 **global TTT로 *joint* coordinate-descent**(= leader가 할 일): one-way 8:1서 **+0.213%(horizon)** — 양수. 즉 global-scored joint면 offset이 양전환(사용자 직관 맞음). 단 **이 망은 corridor 짧고 metering 지배(+47~56%)라 ~+0.2%로 미미.** arterial 많은 큰 망에서 의미. (주의: leader가 *평가만* 하는 현 구조론 부족 — global TTT가 offset *탐색 안에* joint로 들어가야 함. 가드가 이미 평가는 하나 per-signal 생성의 de-coordination은 못 고침.)

## 최종 결정
- **per-signal offset 끔**(`offset_enabled=False`) → PFO sweet_128 = **+56.63%**(metering follower, offset 0).
- **phase-resolved 서비스 + platoon 인프라 보존** → 향후 leader-coordinated offset 레버용.
- offset = **follower 레버 아님, leader-coordinated 후속과제**(이 망 가치 작음, arterial서 의미).
- 메인 green rollout이 cycle-평균→phase-resolved로 충실도↑(수치 동일 +56.63%).
