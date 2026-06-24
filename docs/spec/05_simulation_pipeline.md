# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 5. Simulation and Experiment Pipeline

### 5.1 Baseline cases

Implement at least the following baseline modes:

```yaml
baseline_modes:
  - no_control
  - fixed_signal_fixed_speed
  - local_control_only
```

Definitions:

- `no_control`: no active ramp metering, no VSL, fixed green time and offset. Do not apply an additional inflow-outflow allocation cap; movement service is `saturation flow × actual green fraction`.
- `fixed_signal_fixed_speed`: fixed signal plans and fixed speed limit; ramp flow follows demand/capacity only. Its neutral movement service semantics must match `no_control`.
- `local_control_only`: freeway and urban controls operate independently without leader coordination

The primary improvement rate should compare the proposed controller to `fixed_signal_fixed_speed` unless configured otherwise.

### 5.2 Proposed-controller case

Run the closed-loop Stackelberg MPC controller over the same demand, initial state, and simulation horizon as the baseline.

Use fixed random seeds for reproducibility.

### 5.3 Ablation cases

Implement ablation runs to diagnose which control component contributes to performance:

```yaml
ablation_modes:
  - proposed_without_ramp_metering
  - proposed_without_vsl
  - proposed_without_offset_control
  - proposed_without_green_time_allocation
  - proposed_without_inflow_outflow_allocation
```

These are required for diagnosis when the proposed controller fails the 8% improvement criterion.

### 5.4 Scenario set

Support multiple demand scenarios:

```yaml
scenarios:
  - name: low_demand
  - name: medium_demand
  - name: peak_demand
  - name: medium_incident_east
  - name: medium_urban_west_skew
  - name: medium_surge
```

`low_demand`, `medium_demand`, `peak_demand`의 canonical 배율은
`src/config/scenarios.yaml`을 source of truth로 사용한다. 이 세 시나리오의
regime calibration은 `rho_max=95.019642 veh/km/lane`인 storage receiving-cap
plant를 기준으로 하며, 이 값은 `src/config/default.yaml`의 canonical plant
설정이다. 각 시나리오는 다음 상태를 의도한다.

| 시나리오 | Urban scale | Freeway scale | Ramp scale | 의도한 no-control 상태 |
|---|---:|---:|---:|---|
| `low_demand` | 1.0000 | 1.0000 | 1.0000 | canonical scenario 중 가장 낮은 base load; 장기 run에서는 국부 혼잡 가능 |
| `medium_demand` | 1.0375 | 1.0300 | 1.0375 | 더 많은 구간에서 FD loading/congested branch가 나타나는 제어 평가 상태 |
| `peak_demand` | 1.2500 | 1.2000 | 1.2500 | 여러 구간에서 지속적인 혼잡과 storage 제약이 나타나는 상태 |
| `medium_incident_east` | 1.0375 | 1.0300 | 1.0375 | medium 수요 중 E 방향 최하류부 1개 차로 폐쇄 |
| `medium_urban_west_skew` | 1.0375 | 1.0300 | 1.0375 | 전체 urban 수요를 보존하면서 서측 진입 합이 동측의 2배 |
| `medium_surge` | 1.0375 | 1.0300 | 1.0375 | medium 수요에 일시적인 공통 demand surge 적용 |

이 정의는 2026-06-24 no-control FD screening에서 기존 `medium_demand`를
새 low로, 기존 medium-to-peak 선형 구간의 15% 지점을 새 medium으로
재보정한 결과다. 과거 출력에서 같은 시나리오 이름으로 기록된 결과는 당시
설정을 사용한 historical provenance이며 새 run과 직접 혼합하지 않는다.

특수 시나리오의 canonical 정의는 다음과 같다.

- `medium_incident_east`: `2400 <= t < 4800 s` 동안 `FW_E`의 마지막
  segment(index 3) effective lane을 2개에서 1개로 줄인다. `FW_W`는 폐쇄하지
  않는다. 단일방향 incident를 사용해 단순한 전 네트워크 용량 축소가 아니라
  비대칭 freeway-urban coupling response를 평가한다.
- `medium_urban_west_skew`: 서측 진입
  (`in_A_left`, `in_D_left`) 합을 동측 진입
  (`in_C_right`, `in_F_right`) 합의 정확히 2배로 만든다. 두 측면 진입의 합,
  북측 진입, 전체 urban boundary demand 합은 `medium_demand`와 동일하다.
- `medium_surge`: 모든 freeway, ramp, urban demand에 같은 삼각형 surge
  배율을 적용한다. `t=1800 s`에서 1.0으로 시작해 `t=3000 s`에 1.15,
  `t=4200 s`에 1.0으로 복귀한다. 현재 storage-cap plant는 작은 surge에도
  혼잡 attractor로 전이될 수 있으므로, 이는 demand가 복귀해도 state가 반드시
  회복되는 시나리오가 아니라 tipping-point robustness 시나리오다.

The controller passes only if it satisfies the acceptance criteria on the primary evaluation scenario. If multiple scenarios are configured as required, use the mean improvement and also report scenario-specific pass/fail results.

---
