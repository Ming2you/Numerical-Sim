# 2026-07-09 체크리스트 — Joint bilinear price (green×offset, vsl×metering)

사용자 결정: per-lever 선형가격이 못 담는 **lever쌍 교차곡률**을 bilinear cross-term 가격
`h_ext = ∂²(TTT+V)/∂a∂b − ∂²(own_TTS)/∂a∂b`(4-corner 스텐실)로 하달 + follower 2D 공동탐색.
기존 per-lever(g_ext = g_i − d_local) 규약을 2차로 확장. 기본 OFF = 비트동일.

## green×offset (도시 신호쌍 — 진짜 gap: 현재 coordinate descent)
- [x] follower: cross 속성(green_offset_cross_price/ref/weight, joint_green_offset_enabled)
- [x] follower: `_solve_urban_agent_joint` — non-ramp 신호 2D(green_p1 × offset) 공동탐색
- [x] follower: orchestration 배선 — joint ON이면 non-ramp 신호는 green+offset 통째 재최적화
- [x] follower: probe `local_green_offset_costs`(4-corner own_TTS, 가격 OFF)
- [x] leader: `_global_rollout_ttt_with_green_offset` + cross-price 계산(non-ramp만)
- [x] leader: 게이트 `green_offset_cross_price_enabled`
- [x] 단위검증: defaults dormant + probe 일관성 + refresh 하달

## vsl×metering (freeway 합류쌍 — primal joint은 follower가 이미 포착, 가격만 추가)
- [x] follower: cross 속성(vsl_meter_cross_price/ref/weight)
- [x] follower: `_solve_freeway_agent_local` vsl 채점에 cross term(base+F1)
- [x] follower: probe `local_vsl_meter_costs`(4-corner own_TTS, vsl_override)
- [x] leader: `_global_rollout_ttt_with_vsl_meter` + cross-price 계산(ramp별)
- [x] leader: 게이트 `vsl_meter_cross_price_enabled`
- [x] 단위검증: vsl_override 유한값

## 통합
- [x] runner: `P-STACK-WU-FAITHFUL-ALLPRICE-JOINT`(ALLPRICE + 두 cross + joint search)
- [x] 전체 단위테스트 회귀 0(before/after 실패 동일 14건, 전부 기존)
- [~] sweet_190 7200s d3/d4 + far 실행 → 진행중(bxhhvh0x3/bt3mzb3re)
- [x] 로컬 커밋(push는 결과 확인 후)
