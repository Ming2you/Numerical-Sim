# Codex 실행 리포트

## 2026-06-10 13:06:17 +09:00

### 이번 수정 요약

- `docs/spec/04_controller.md`의 수정된 leader objective를 기준으로 `src/controllers/leader.py`를 재작성했다.
- 기본 leader objective mode를 `state_accumulation`으로 변경했다.
- `N_P_star` 후보를 임의 `[0, 500]` 격자가 아니라 `N_P_crit_veh` 주변 band로 생성하도록 수정했다.
- leader objective의 urban penalty는 `max(n_P - N_P_crit, 0)` 기준으로 계산하도록 고쳤다.
- `N_P_crit_veh`와 candidate band 설정을 config/dataclass validation에 추가했다.
- urban follower가 on-ramp movement allocation까지 직접 결정하도록 연결했다.
- p2 green이 짧을 때도 `N_UF_star`를 받칠 수 있도록 on-ramp saturation flow를 green fraction 기준으로 역산했다.
- off-ramp discharge phase가 최소 green에 고정되어 urban outflow가 굶지 않도록 D/F 계열 p1 green floor를 추가했다.
- boundary/urban net inflow 진단은 follower가 allocation을 만들 때 사용한 control-interval target과 비교하도록 정리했다.

### 검증 결과

| 실행 | 결과 | 주요 수치 |
|---|---|---|
| Unit tests | PASS | `python -B -m unittest discover -s src\tests -v`, 44 tests OK |
| `peak_demand`, 360 s | PASS | Total TTT `30.974 -> 26.763`, improvement `13.60%` |
| `peak_demand`, 1800 s | FAIL | Total TTT `455.517 -> 308.027`, improvement `32.38%` |

### 360초 acceptance 상세

- Total TTT improvement: `13.60%`로 기준 `8%`를 통과했다.
- Ramp metering validation: PASS
  - mean error `73.35 veh/h`
  - max violation `94.97 veh/h`
- Boundary balance validation: PASS
  - Boundary CV `0.160 -> 0.098`
  - boundary queue balance improvement `38.71%`
  - urban net inflow tracking error `62.41 veh/h`

### 1800초 장기 run 잔여 진단

장기 run은 Total TTT 관점에서는 크게 개선되지만 아직 acceptance는 실패한다.

- VSL/density validation 실패:
  - `vsl_active_steps = 0`
  - `density_exceedance_duration = 2`
  - 일부 freeway segment가 `rho_crit`를 넘는 순간이 있는데 VSL 또는 N_UF 억제가 충분히 반응하지 못한다.
- Boundary tracking validation 실패:
  - urban net inflow tracking error `545.3 veh/h`
  - 후반부에 `net_inflow_target = -800 veh/h`까지 내려가지만 실제 net inflow가 양수로 튀는 구간이 남아 있다.

### 다음 수정 후보

1. Leader의 congestion 판단을 평균 density가 아니라 max 또는 percentile density 기준으로 바꿔 일부 segment 병목에도 `N_UF_star`가 줄어들게 한다.
2. `w_F` 또는 freeway follower density penalty를 키워 장기 run에서 rho_crit 초과를 더 강하게 회피한다.
3. Urban follower의 후반부 과포화 상황에서 boundary-in green과 off-ramp/on-ramp discharge 우선순위를 더 직접적으로 최적화한다.
4. VSL compliance `alpha_vsl`가 0인 현재 설정에서 VSL activation 검증을 어떻게 해석할지 별도 정책을 정한다.
