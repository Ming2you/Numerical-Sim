# Context Notes — leader 퇴화 근본수정

## 왜 이 수정인가 (진단 근거)
- P-STACK이 P-FO에 패배(+17 veh·h). fidelity·candidate-ranking은 정상(상관 0.9999) → 구현버그 아님.
- 근본 = **leader N_P_star 핸들 퇴화**: `direct` 모드에서 N_P_star는 follower 비용에 안 들어가고, green을 조정해 목표 net-inflow를 맞춘 후보를 추가할 뿐(`_augment_leader_target_net_inflow_candidates`). green은 [green_min,green_max]로 묶여 달성 net-inflow 범위가 좁음.
- 측정: 혼잡 state(t=360)에서 달성 net-inflow ~[260,380] veh인데 탐색범위 N_P_star∈[−3500,3500]. >98% 도달불가 → saturation 2-plateau → 선택이 임의로 양끝 튐.
- 코드는 이미 movement reachability로 클램프하려 했으나(`np_upper=min(base, movement_np_upper)`), 그 경계(`_movement_net_flow_bounds`)가 **capacity 기반(`flow_max=green_max/cycle×movement_capacity`)** 이라 실제 달성치보다 수천 veh 넓게 잡힘 → 클램프 무력화.

## 결정
- 옵션 1 채택(사용자 승인): `_movement_net_flow_bounds`를 수요/큐-aware로. movement별 `available=queue+arrivals`로 servable 캡.
- 도착 헬퍼는 coordinator `_movement_forecast_arrivals_veh`와 동일 로직(boundary_in·on_ramp만, off_ramp/boundary_out는 큐만). divergence 방지 위해 `urban_queue_model`에 공유 함수로 두고 leader가 호출.
- 경계는 디커플 over-approx: max_net=Σinflow servable, min_net=−Σoutflow servable. 달성집합을 배제하지 않으면서 [−3500,3500]보다 압도적으로 타이트.

## 주의/리스크
- spec 필드(origin/beta)는 `net.urban_movements` 대신 `movement_specs(cfg)` 사용(coordinator와 동일 보장).
- horizon_h는 `_np_target_horizon_h(forecast)`로 통일(이중계산 방지).
- 이 수정은 해상도 회복이 목적. P-STACK이 P-FO를 실제로 이기는지는 이후 별도 런으로 확인(필요시 옵션 2 타이트닝).
