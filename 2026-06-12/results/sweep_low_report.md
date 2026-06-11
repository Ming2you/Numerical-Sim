# Experiment Report: low_demand

## Metadata
- Scenario: low_demand
- Baseline mode: fixed_signal_fixed_speed
- Controller mode: stackelberg_mpc
- Seed: 42
- Simulation horizon: 7200 s

## Final Result
**FAIL**

| Metric | Baseline | Proposed | Improvement | Pass |
|---|---:|---:|---:|---:|
| Total TTT | 1147.226 | 864.562 | 24.64% | Yes |
| Freeway TTT | 183.142 | 191.775 |  |  |
| Urban TTT | 964.084 | 672.787 |  |  |
| Boundary B_in | 0.0515 | 0.1877 |  | No |
| Boundary B_out | 0.0351 | 0.1082 |  | No |
| Boundary CV (descriptive) | 3.579 | 2.397 |  |  |

## Control Validation
- ramp_metering: Yes. metering_active_steps=39, mean_total_metering_error=84.73, max_metering_violation=2345, ramp_queue_overflow_duration=0
- vsl: Yes. vsl_active_steps=0, vsl_feasible_rate=1, vsl_change_violation_count=0, density_exceedance_duration=0
- green_time: Yes. cycle_sum_error=1.421e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-291.3
- boundary_balance: No. B_in=0.1877, B_out=0.1082, eps_balance=0.03, CV_boundary=2.397, MaxMin_boundary=7.494, OverflowRatio_boundary=0, boundary_queue_balance_improvement=33.02, boundary_balance_degenerate=0, boundary_balance_controllable=1, boundary_empty_ratio=0.3643, boundary_saturation_ratio=0, boundary_in_empty_ratio=0.3643, boundary_out_empty_ratio=0.075, boundary_in_saturation_ratio=0, boundary_out_saturation_ratio=0, urban_net_inflow_tracking_error_veh_h=131.4, urban_accumulation_abs_error_veh=151.1

## Diagnostics
- Dominant failure mode: boundary_queue_balance_failed
- increase movement-level boundary balance weight or switch receiving-space rule

## Attempt History
- attempt_0: improvement=24.64%, passed=False, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
