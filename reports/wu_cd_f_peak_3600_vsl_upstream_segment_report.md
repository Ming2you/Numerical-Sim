# WU-CD-F 3600s VSL Activation Diagnosis After Upstream Segment Topology

## Purpose

`FW_W`/`FW_E`의 기존 segment 0 앞에 동일 길이 `0.5 km` 단순 상류 segment를 추가한 뒤, Wu controller가 병목 상류에서 VSL을 activate하는지 확인했다.

## Topology Review

- `freeway_segments_per_link`: `3 -> 4`
- `freeway_segment_length_km`: `0.5 km` 유지
- 새 `seg0`: on-ramp/off-ramp 없음
- D off-ramp: `seg1`
- F off-ramp: `seg2`
- D/F on-ramp merge: `seg2`
- Wu VSL 후보 예시:
  - `FW_W`: `[80,100,100,80]`, `[80,100,100,90]`, `[80,100,100,100]`, ...
  - `FW_E`: `[80,100,100,80]`, `[80,100,100,90]`, `[80,100,100,100]`, ...

Review 결론: 새 `seg0`은 ramp 없는 상류부로 구성되었고, Wu 후보 집합이 off-ramp 병목 segment를 max VSL로 보존하면서 상류 `seg0` VSL을 낮출 수 있게 되었다.

## Run Command

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --scenario peak_demand --T-total 3600 --controllers WU-CD-F --output outputs\wu_cd_f_peak_3600_vsl_upstream_segment
```

## Result Summary

| Metric | WU-CD-F |
|---|---:|
| Total TTT | 2474.384 veh-h |
| Freeway TTT | 1525.292 veh-h |
| Urban TTT | 949.092 veh-h |
| Total Delay | 1905.065 veh-h |
| Freeway Delay | 1398.459 veh-h |
| Urban Delay | 506.607 veh-h |
| Throughput | 9108.2 veh/h |
| Solver converged rate | 0.65 |
| Computation time | 139.94 s |

## VSL Activation

- Control intervals: `20`
- Any VSL active: `17 / 20`
- `FW_W seg0`: active `15 / 20`, min `50 km/h`
- `FW_E seg0`: active `17 / 20`, min `50 km/h`
- `FW_W/FW_E seg1`, `seg2`, `seg3`: always `100 km/h`

Interpretation: topology 재구성 후 Wu controller의 VSL은 실제로 activate된다. 활성화 위치는 의도한 상류 단순 segment `seg0`에만 집중되며, off-ramp가 붙은 병목 segment `seg1/seg2`는 후보 규칙대로 max VSL을 유지한다.

## Spillback / Storage Diagnosis

- `capacity_drop_active`: `1` for all intervals
- Max lane loss:
  - `FW_W seg1`: `0.000064 lanes`
  - `FW_W seg2`: `0.000245 lanes`
  - `FW_E seg1`: `0.000064 lanes`
  - `FW_E seg2`: `0.000247 lanes`
- `offramp_storage_binding`: `0`
- `offramp_blocked_flow_total`: `0`
- Max off-ramp occupancy ratio: about `0.0138`
- Mean ramp receiving factor: min `0.0336`, average `0.3613`

Interpretation: VSL activation 가능성은 복구되었지만, 이 3600초 `peak_demand` run에서는 off-ramp storage가 실제로 binding하지 않는다. 즉 현재 VSL은 “상류 VSL 후보가 작동 가능한지”는 보여주지만, 강한 off-ramp spillback 완화 효과까지 검증한 것은 아니다.

## Validation

```text
py_compile: PASS
31 related unit tests: PASS
WU-CD-F peak_demand 3600s run: PASS (run completed)
```

This is not a full acceptance run. Baseline/proposed same-scenario comparison and 8% improvement criterion were not evaluated in this pass.
