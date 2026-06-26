# fallback guard 수정 + deep 과포화 over-metering 진단 — 체크리스트

발견(2026-06-25): fallback guard가 **penalized leader objective**로 PFO와 비교해 sweet_128에서
TTT 좋은 leader(+13.5%)를 기각. 또 deep 과포화(sweet_190)는 leader가 freeway는 돕지만
boundary 큐 폭증(+186)으로 net 손해.

## (a) guard를 rollout-TTT 비교로 수정  ← 즉효(sweet_128 +13.5% 해금)
- [ ] `_evaluation_rollout_ttt(eval)` 추가 (`distributed_response_rollout_ttt`).
- [ ] MpcConfig + default.yaml에 `stackelberg_fallback_guard_use_rollout_ttt: bool=True`.
- [ ] `_fallback_guard_rejects`: flag on이면 1차 기각을 `leader_ttt > fallback_ttt + margin`로.
      terminal_severe/completed_severe는 throughput 안전장치로 유지. rollout_ttt 결측 시 기존
      objective 로직으로 fallback(안전).
- [ ] 검증: compare_fallback_ttt 재실행 — sweet_128 fb-ON이 ~320(leader 채택), sweet_115/190은
      ~PFO(defer)로 나오는지. 즉 fb-ON ≈ min(PFO, fb-OFF).
- [ ] 회귀: 관련 unittest(six_controller/closed_loop_smoke) — 사전 3실패 외 신규 0.

## (b) deep 과포화 over-metering 진단/완화
- [ ] sweet_190 leader가 freeway −20 얻자고 boundary +186 만드는 트레이드오프 원인:
      N_UF 과metering인지 N_P 과admit인지 분리(N_UF만/ N_P만 활성 비교).
- [ ] leader objective의 boundary_in vs freeway/density 가중(w_boundary_in, w_F, mfd weights)
      점검 — boundary 정체가 과소평가되는지.
- [ ] 가중 조정 후 sweet_190 leader가 PFO 이상이 되는지(또는 최소 동률) 확인.
- [ ] (a)의 TTT-guard와 상호작용: (b) 성공 시 guard가 sweet_190 leader도 채택해야 함.

## 불변/주의
- (a)는 flag로 ablation 가능하게. 기본 True(개선 적용)지만 off로 기존 재현.
- rollout-TTT 예측이 closed-loop과 정합한지 compare_fallback로 실증(예측≈실측 가정 검증).
- 차량보존/plant 식 불변. 변경은 guard 비교척도 + (b) objective 가중에 한정.
