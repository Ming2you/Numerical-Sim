# Codex 실행 리포트

## 2026-06-10 15:45:11 +09:00

### 이번 수정 요약

- Wu et al. Eq.(22) 계열의 off-ramp spill-back capacity drop을 `lambda_eff` 형태로 구현했습니다.
- 2차로 네트워크에서 `lane_reduction=1`은 과격하므로 기본값은 분수 감소 `0.35`로 두었습니다.
- `TrafficState`에 `freeway_effective_lanes`를 추가하고, flow/TTT/state timeseries가 유효 차로 수를 일관되게 쓰도록 정리했습니다.
- λ가 바뀌는 순간 차량이 사라지지 않도록 density를 직접 보존량으로 두지 않고, `N = rho * L * lambda`를 보존량으로 사용했습니다.
- 속도식도 저장 density가 아니라 `rho_for_flow = N / (L * lambda_eff)`를 사용하게 수정했습니다. desired speed, VSL effective speed, anticipation 모두 이 보정 density를 봅니다.
- `rho_max * L * lambda_eff` 상한 projection으로 차량이 삭제될 수 있어, 차량 수는 음수만 막고 상한 초과는 congestion diagnostic으로 남기는 방식으로 바꿨습니다.
- controller prediction, coupling aggregate diagnostics, simulator state logging도 `capacity_drop_active`, `lambda_eff_*`, `capacity_drop_lane_loss_*`를 전달하도록 맞췄습니다.
- 10번 튜닝 단계는 제외했습니다. horizon, penalty, `N_UF_star` 후보 범위는 이번 커밋에서 조정하지 않았습니다.

### 검증 결과

| 항목 | 결과 | 메모 |
|---|---:|---|
| `py_compile` | PASS | state/metanet/freeway_follower/coupling/simulator/tests |
| METANET unit tests | PASS | 18 tests OK |
| 전체 unit tests | PASS | 49 tests OK |
| `peak_demand`, 360 s | PASS | Total TTT `30.974 -> 26.763`, improvement `13.60%` |
| `peak_demand`, 1800 s | FAIL | Total TTT `455.517 -> 302.195`, improvement `33.66%`, validation 일부 실패 |

### Capacity Drop 진단

- 강제 spill-back 단위 테스트에서는 `lambda_eff` 경계값, λ 변화 시 차량 보존, `rho_for_flow` 기반 속도 저하, VSL 속도 반응을 모두 확인했습니다.
- 기본 `peak_demand` 360초 run에서는 `capacity_drop_active=0`, `lambda_eff_FW_W_last=2.0`, `lambda_eff_FW_E_last=2.0`였습니다.
- 기본 `peak_demand` 1800초 run에서도 `capacity_drop_active=0`, `lambda_eff_FW_W_last=2.0`, `lambda_eff_FW_E_last=2.0`였습니다.
- 즉, 이번 구현은 capacity-drop 메커니즘을 심은 상태이고, 기본 시나리오에서는 off-ramp storage가 spill-back 임계까지 차지 않아 실제 차로 감소가 발화하지 않았습니다.

### 1800초 run 잔여 실패

- Total TTT improvement는 `33.66%`로 8% 기준을 넘었습니다.
- Ramp metering은 활성화됐습니다: `metering_active_steps=10`.
- VSL은 활성화되지 않았습니다: `vsl_active_steps=0`, `density_exceedance_duration=4`.
- Boundary balance는 아직 실패입니다: `urban_net_inflow_tracking_error_veh_h=493.3`, `urban_accumulation_abs_error_veh=289.9`.
- 현재 결과만 보면 VSL 미활성은 capacity-drop 코드 오류라기보다, 기본 부하/저장공간/목적함수 조합에서 spill-back 메커니즘이 실제 plant에서 켜지지 않는 문제에 가깝습니다.

### 다음 단계

1. 10번 튜닝 단계에서 VSL 메커니즘을 켜는 방향으로 horizon, freeway density penalty, `N_UF_star` 후보 범위, spill-back 민감도(`gamma`, `lane_reduction`)를 분리 실험합니다.
2. 기본 시나리오가 아니라 forced spill-back 또는 high off-ramp demand scenario를 하나 추가해 `lambda_eff < lanes`가 실제 closed-loop run에서 관측되는지 확인합니다.
3. VISSIM 연동을 염두에 두고 `lambda_eff`, off-ramp storage occupancy, VSL activation, ramp metering residual을 외부 plant adapter에서 읽기 쉬운 diagnostic schema로 고정합니다.
