# Experiment Report: peak_demand

## Metadata
- Scenario: peak_demand
- Baseline mode: fixed_signal_fixed_speed
- Controller mode: stackelberg_mpc
- Seed: 42
- Simulation horizon: 7200 s

## Final Result
**PASS**

| Metric | Baseline | Proposed | Improvement | Pass |
|---|---:|---:|---:|---:|
| Total TTT | 7911.843 | 6481.070 | 18.08% | Yes |
| Freeway TTT | 992.137 | 302.822 |  |  |
| Urban TTT | 6919.706 | 6178.248 |  |  |
| Boundary B_in | 0.0285 | 0.0140 |  | Yes |
| Boundary B_out | 0.0058 | 0.0028 |  | Yes |
| Boundary CV (descriptive) | 1.165 | 1.042 |  |  |

## Control Validation
- ramp_metering: Yes. metering_active_steps=37, mean_total_metering_error=28.29, max_metering_violation=461.3, ramp_queue_overflow_duration=0
- vsl: Yes. vsl_active_steps=13, vsl_feasible_rate=1, vsl_change_violation_count=0, density_exceedance_duration=13
- green_time: Yes. cycle_sum_error=1.421e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0.1429
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-741.5
- boundary_balance: Yes. B_in=0.01405, B_out=0.002771, eps_balance=0.03, CV_boundary=1.042, MaxMin_boundary=248.7, OverflowRatio_boundary=0.1429, boundary_queue_balance_improvement=10.56, boundary_balance_degenerate=0, boundary_balance_controllable=1, boundary_empty_ratio=0.03214, boundary_saturation_ratio=0.5188, boundary_in_empty_ratio=0.03214, boundary_out_empty_ratio=0, boundary_in_saturation_ratio=0, boundary_out_saturation_ratio=0.5188, urban_net_inflow_tracking_error_veh_h=88.11, urban_accumulation_abs_error_veh=50.99

## Diagnostics
- Dominant failure mode: none
- all configured acceptance criteria passed

## Attempt History
- attempt_0: improvement=18.08%, passed=True, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
