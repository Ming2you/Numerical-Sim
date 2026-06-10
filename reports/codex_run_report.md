# Codex 실행 리포트

## 2026-06-10 17:36:31 +09:00

### 질문

capacity drop이 실제로 발생하는 조건까지 튜닝했을 때, VSL이 activate되는지 확인했습니다.

### 결론

- 예. stress tuning에서 capacity drop이 실제로 발화하면 VSL도 activate됩니다.
- `outputs/codex_capacity_drop_vsl_probe_cli` run에서 `capacity_drop_active_steps=4`, `vsl_active_steps=4`, `overlap_steps=4`였습니다.
- 최소 effective lane은 `lambda_min=1.250007`로, 2차로에서 약 `0.75`차로 감소가 실제 run log에 기록됐습니다.
- 단, 이 결과는 “VSL이 켜지는가”에 대한 positive check입니다. “VSL이 항상 TTT를 개선하는가”는 아직 positive proof가 아닙니다.

### Stress Tuning

기본 `peak_demand`에서는 off-ramp storage가 충분히 차지 않아 `capacity_drop_active=0`이었습니다. 그래서 capacity drop 발화를 확인하기 위해 아래 stress 조건을 사용했습니다.

- `off_ramp_split_ratio`: `0.90`
- `OR_W_D`, `OR_E_F` storage: `20 veh`
- `urban_avg_speed_km_h`: `3.0`
- `urban_avg_vehicle_length_m`: `15.0`
- `lane_reduction`: `0.75`
- `gamma`: `0.2`
- `vsl_smoothness_weight`: `0.0`
- `horizon_steps`: `3`
- `T_total`: `720 s`

### 실행 결과

| run | total TTT | freeway TTT | urban TTT | capacity drop active | lambda min | VSL active | overlap |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 249.168 | 136.497 | 112.671 | 4 | 1.250009 | 0 | 0 |
| proposed | 250.111 | 123.387 | 126.723 | 4 | 1.250007 | 4 | 4 |
| proposed_without_vsl | 249.763 | 123.071 | 126.692 | 4 | 1.250009 | 0 | 0 |

### 해석

- Capacity drop과 VSL activation은 같은 control step에서 함께 관측됐습니다.
- Proposed controller는 capacity drop 상황에서 VSL `50 km/h`를 선택했습니다.
- Proposed는 baseline 대비 freeway TTT는 낮췄지만 urban TTT가 올라 전체 TTT는 약간 나빠졌습니다.
- `proposed_without_vsl`과 비교하면 VSL이 이 stress setting에서 TTT를 개선하지는 않았습니다.
- 따라서 다음 튜닝 목표는 “VSL activation”이 아니라, VSL이 너무 강하게 `50 km/h`까지 떨어지지 않도록 VSL cost/benefit을 재조정하거나, capacity drop 대응을 ramp metering과 분담하게 만드는 것입니다.

### 추가된 재현 도구

- `src/experiments/capacity_drop_vsl_probe.py`
- `experiments/capacity_drop_vsl_probe.py`

재실행 명령:

```powershell
python -B -m experiments.capacity_drop_vsl_probe `
  --output outputs\codex_capacity_drop_vsl_probe_cli `
  --T-total 720
```

### 검증

- `python -B -m py_compile src\experiments\capacity_drop_vsl_probe.py experiments\capacity_drop_vsl_probe.py src\tests\test_constraints.py`
- `python -B -m unittest src.tests.test_constraints.ConstraintTests.test_freeway_follower_activates_vsl_under_capacity_drop -v`
- `python -B -m experiments.capacity_drop_vsl_probe --output outputs\codex_capacity_drop_vsl_probe_cli --T-total 720`
- `python -B -m unittest discover -s src\tests -v`

결과:

- Capacity drop/VSL probe: `capacity_drop_active_steps=4`, `vsl_active_steps=4`, `overlap_steps=4`, `lambda_min=1.250007`
- 전체 tests: `50 tests OK`
