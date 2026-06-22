# Checklist — leader N_P_star reachability 경계 수요-aware 수정 (퇴화 근본수정 옵션 1)

## 목표
leader N_P_star 후보범위를 capacity 기반 → **수요/큐-aware reachability**로 교정해 2-plateau 퇴화 제거.
성공기준: 혼잡 state에서 N_P 후보가 distinct 응답을 내고(현재 2→여러), 탐색범위가 달성범위 근처로 좁아짐.

## 작업
- [ ] urban_queue_model.py: `movement_forecast_arrivals_veh(cfg, forecast)` 공유 함수 추가(boundary_in·on_ramp 도착, coordinator 로직과 동일).
- [ ] leader.py: 위 함수 import.
- [ ] leader.py `_movement_net_flow_bounds(nuf_upper)` → `(state, forecast, nuf_upper)`: movement별 `available = queue + arrivals`, `servable = min(available/horizon_h, cap_flow)`; max_net=Σinflow servable, min_net=−Σoutflow servable.
- [ ] leader.py `_movement_np_bounds`: 호출부에 state/forecast 전달.
- [ ] 검증 probe: 혼잡 state N_P sweep → distinct 응답 수↑ + bounds 로그 확인.
- [ ] 단위테스트 전체 실행(기존 8F+1E 외 신규 회귀 없음 확인).
- [ ] (선택) bounds 타이트닝 단위테스트 추가.

## 비범위
- green inflow↔outflow 커플링 정확 반영(옵션 2)은 보류.
- 플랜트/보존식 불변. hard trigger 금지.
