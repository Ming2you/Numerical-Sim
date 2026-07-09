# 2026-07-09 작업 노트 — Joint bilinear cross-term 가격

## 무엇을 / 왜

per-lever 선형가격(`own_TTS(a) + w·g_a·(a−a_ref)`)이 못 담는 **lever쌍 교차곡률**
∂²(TTT+V)/∂a∂b를 bilinear cross-term 가격으로 하달하고, follower가 해당 쌍을 2D 공동탐색.
사용자 결정("신규 bilinear 가격 대공사"). 두 쌍:
- **green×offset**(도시 신호쌍, non-ramp): 현재 coordinate descent(green은 offset 동결
  1D, offset은 green 동결 1D)라 cross가 퇴화 → 진짜 gap. follower를 2D 공동탐색으로 전환.
- **vsl×metering**(freeway 합류쌍): primal joint은 follower가 이미 포착
  (metering 후보마다 VSL best-response) → 탐색 구조 불변, cross 가격만 추가.

cross 규약은 per-lever와 동일한 externality 차감: `h_ext = h_global − h_local`(4-corner
스텐실). 가격 rollout은 기존 per-lever와 동일하게 `_predict`(leader_value_depth로 3+d 깊이,
analytic far 미포함) TTT 사용.

## 변경 파일
- `src/controllers/wu_faithful_follower.py`: cross 속성 + `_solve_urban_agent_joint`(2D
  공동탐색) + orchestration 배선 + `local_green_offset_costs`/`local_vsl_meter_costs` probe
  + `_solve_freeway_agent_local`에 `vsl_override` param & vsl×metering cross항.
- `src/controllers/f1_wu_faithful_follower.py`: F1 override에도 `vsl_override` + cross항.
- `src/controllers/stackelberg_wu_metered.py`: gate 플래그 2종 + `_global_rollout_ttt_with_
  green_offset`/`_global_rollout_ttt_with_vsl_meter` + 두 cross-price 계산 블록.
- `work/run_claude_style_five_controller.py`: `P-STACK-WU-FAITHFUL-ALLPRICE-JOINT`.
- `src/tests/test_joint_cross_price.py`: 신규 4테스트.

## 검증
- 전체 단위테스트 회귀 0: before/after 실패목록 완전 동일(14건, 전부 기존 Wu 작업 진행중
  실패 — metanet/constraints/forecast/post_analysis/six_controller). 내 변경 회귀 없음.
- 신규 4테스트 통과: defaults dormant, green×offset probe=offset probe 일관성, vsl_override
  유한, controller refresh가 non-ramp 신호·ramp에 cross 하달(유한).
- 스모크(sweet_190 4스텝, d3+far): green×offset cross A/B/C 모두 nonzero, vsl×metering
  cross 초기 저부하라 0(metering/vsl ±δ 밀도무변 → externality 0, 피크서 nonzero 가능),
  joint 탐색 정상 작동.

## 비교 baseline (sweet_190 7200s, +far)
| controller | d3 | d4 |
|---|---:|---:|
| G1DF (green price만) +far | 11283 | **11230** |
| ALLPRICE per-lever +far | 12279 | 12036 |
| **ALLPRICE-JOINT +far** | (실행중 bxhhvh0x3) | (실행중 bt3mzb3re) |
| legacy(ceiling) | — | 10729 |

관전: per-lever ALLPRICE(전방위 가격)는 green-only G1DF보다 일관되게 나쁨. joint cross가
그 손해를 회복하는지가 핵심 판정.

## E1+E2 (bda8b49) — 사용자 지시: "price에 far도 모두, own TTT는 빼서 externality만"

진단(사용자 질문 "freeway는 externality 고려 terminal cost 넣었는데도 나빠지냐"에 대한 답):
far는 leader **후보 채점에만** 있었고 follower에 하달되는 **가격 rollout엔 없었다** —
"far는 수량 신호(N_UF_star)만 똑똑하게 하고, G1DF는 수량(hard 예산)을 전송해 far를 100%
상속하는데, ALLPRICE는 gradient를 전송하고 gradient엔 far가 없다". 격차가 d6 no-far ~300
→ d3/d4+far ~1000으로 벌어진 것과 정합(가격이 보는 깊이는 줄고 예산 채널만 far 보상).

- **E1**: `price_far_enabled`(runner `MFD_FAR_PRICE=1`) — 모든 가격·cross rollout이
  `_price_ttt` = TTT + far(terminal state)로 채점. far는 leader 전용 항이라 d_local 차감
  없음(B4 barrier와 동일 규약). 기본 OFF=비트동일.
- **E2**: VSL 가격 g_ext화 — `local_vsl_costs`(vsl_override 고정벡터 own-TTS probe)로
  d_local을 차감. 기존 raw g_i의 own 성분 이중계상 결함(코드에 "선행 과제"로 명시돼
  있었음) 해소. vsl_price_enabled 자체가 기본 OFF라 기본 비트동일.
- E3(barrier)는 사용자 질문으로 정리: leader payoff 항이 아니라 **가격에 합산되는 hinge
  gradient 채널**(이미 구현, ALLPRICE 미사용). E1과 철학 동일(leader 전용 항의 gradient를
  가격에). 선택지로 보류.
- 검증: 신규 2테스트(E1 가산 확인, E2 유한·키 정합) + 가격채널/follower 회귀 30/30.

## 결과 (sweet_190 7200s, leader far ON)

| 구성 | d3 | d4 |
|---|---:|---:|
| G1DF (수량 equality) | 11283 | **11230** |
| ALLPRICE per-lever (raw VSL, far-in-price 없음) | 12279 | 12036 |
| ALLPRICE-JOINT (cross 추가, E1/E2 없음) | 11854 | 11879 |
| ALLPRICE per-lever + E1E2 (dual 없음) | — | **12376(악화!)** |
| legacy | — | 10729 |

판정 중간값.
- joint cross 실효: per-lever 대비 d3 −425, d4 −157 회복. 그러나 G1DF에 아직 뒤짐.
- E1E2 단독(수량 가드 없는 far-in-price): 12036→12376 **악화**. far가 gradient를 방류로
  세게 밀지만 선형 가격이라 절벽 가드 부재 → 사용자 지시의 N_UF dual(수량 적분 피드백)이
  정확히 이 빠진 조각이라는 가설과 정합.

## 표준 구성 전환 (2026-07-09, 사용자 지시)

"terminal cost(urban+freeway far) 기본 + price에 far 포함 + N_UF dual"을 **디폴트**로.
- state.py: `leader_mfd_far_enabled: bool = True`(정식 필드 선언), `leader_mfd_far_weight=1.0`,
  `wu_faithful_nuf_coordination_mode = "dual"`.
- default.yaml: `wu_faithful_nuf_coordination_mode: dual`.
- stackelberg_wu_metered: `price_far_enabled = True` 기본.
- **DUAL×PRICE 결합(신규)**: 가격 분기(`_price_metering_cost`)에서 dual 모드면 soft
  anchor(|Σ−budget|, w≈0.05, 사실상 무력) 대신 **λ_UF·Σmeter** — ALLPRICE 계열에서도
  leader의 수량 target을 λ_UF(적분 피드백)로 추적. λ_UF commit 경로는 기존(1398-1401).
- 스모크: far가 가격에 들어가자 **vm_cross(vsl×metering)가 nonzero로 살아남**(이전 0) —
  ramp 큐 배수 효과가 gradient에 잡히기 시작.
- 검증: 타깃 회귀 41/41(E1 테스트만 새 기본값 반영해 OFF 기준선 명시로 수정).

## 실행 중 런 (새 디폴트: far+pricefar+dual, d3)
- G1DF d3 (btqteov88) — 수량 equality→dual 전환 효과. vs 11283(equality).
- ALLPRICE-JOINT d3 (b6w0cc24n) — cross+E1E2+dual 총결합. vs 11854(cross만).

## TODO
- [ ] 새 디폴트 d3 2런 판정 — dual이 far-informed 수량을 가격 구조에 복원하는가
- [ ] 결과 정리 후 push
