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

## TODO
- [ ] d3/d4 joint 결과 확인 → 판정
- [ ] (필요시) green_offset_cross_weight / vsl_meter_cross_weight 튜닝
- [ ] 결과 좋으면 push, notes/report 정리
