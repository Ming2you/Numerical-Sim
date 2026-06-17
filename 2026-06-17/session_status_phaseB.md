# 2026-06-17 세션 상태 — off-ramp 재귀속(B) 완료 / forecast-aware(Phase B) WIP

## ✅ 완료·커밋됨 (main, ab6e5f3)
- **변경 B — off-ramp 램프 큐 freeway 재귀속(plant 공통)**: 램프 storage(OR_*_storage)를
  urban→freeway TTT/agent로 이동, leg(off_ramp movement 점큐)는 urban·N_P 유지. 보존 1e-14,
  이중계상 0(리뷰어 독립검증), 131 tests OK.
- **`_agent_vsl` off-ramp 트리거 제거**(dead-branch + trigger 스타일 폐기). objective의
  `+offramp_storage_veh` 가산은 유지.
- 변경 2(leader boundary_in 비용)는 그대로 둠(추가 작업 보류, follower forecast-aware 후 재해석).
- 설계 문서: `docs/offramp_queue_reattribution_design.md`.

## 🚧 진행 중 (WIP, 이 커밋에 포함 — 테스트 2개 실패)
**Phase B — 분산 follower 전체 forecast-aware化** (근거: `docs/proposed_forecast_awareness_diagnosis.md`).
코더가 구현했고 제가 리뷰/마감 전에 세션 종료. **미완성 상태로 커밋**(다음 세션 재개용).

구현된 것(작동 추정):
- `DistributedCoordinator.solve`가 freeway·urban agent에 **full forecast 전달**.
- freeway VSL: 휴리스틱 `_agent_vsl` → **`_search_agent_vsl`(VSL 후보 탐색 + objective 최소화)**.
  objective에 horizon off-ramp 예측(`_forecast_offramp_arrivals`, admitted/held_mainline) 반영 →
  off-ramp backup 시 VSL emergent (트리거 아님).
- urban green: horizon arrival pressure(`urban_follower` +77).
- allocation target: forecast-호환(`inflow_outflow_allocation` +11).
- leader 후보: forecast 요약 kwarg(`leader.candidates(..., forecast=)`, leader +30).
- 신규 `src/tests/test_forecast_awareness.py` 5개.

### ❌ 남은 일 (2개 테스트 실패 — 다음 세션 시작점)
1. **`test_freeway_vsl_uses_future_offramp_inflow` 실패**: off-ramp storage가 거의 가득한 state라
   미래 off-ramp 예측을 바꿔도 VSL이 둘 다 80(prev=100에서 ±max_vsl_step=20의 바닥)에 붙어
   구분 안 됨. → VSL 후보범위/objective 가중을 손봐 forecast 민감도가 드러나게 하거나, 테스트
   state를 덜 채워 forecast가 결정요인이 되게 조정 필요.
2. **`test_leader_candidates_reflect_forecast_summary` 실패**: `candidates(..., forecast=)`
   kwarg는 받지만 **N_UF 후보 생성이 forecast 요약을 아직 안 씀**(big-future vs first-demand가
   동일 후보). → N_UF 후보 placement를 horizon 요약(예측 ramp/boundary 수요 합)으로 만들고,
   `stackelberg_mpc.py`가 `candidates`에 forecast를 넘기도록 wiring.
3. 위 둘 통과 후: 리뷰어 독립검증 → peak/heavy-transfer 재측정으로 **emergence 관찰**.

## 📌 그 외 미결(이전부터)
- **N_P_crit_veh 재calibration 필수**(N_P 정의 변경, 현 556.081 무효, probe ≈210 관측).
- heavy-transfer 시나리오(off-ramp 실제 충전) — emergence 검정용.
- 변경 2(leader boundary 비용) follower forecast-aware 후 재해석/튜닝.
- (이전) 4-controller 풀 매트릭스 재실행은 위 전부 정리 후.

## 재개 방법
1. `python -B -m unittest src.tests.test_forecast_awareness -v`로 실패 2개 재현.
2. 위 ❌ 1·2 수정 → 전체 테스트 → 리뷰어 → 재측정.
