# Experiment Report: peak_demand

## Metadata
- Scenario: peak_demand
- Baseline mode: fixed_signal_fixed_speed
- Controller mode: stackelberg_mpc
- Seed: 42
- Simulation horizon: 900.0 s

## Final Result
**FAIL**

| Metric | Baseline | Proposed | Improvement | Pass |
|---|---:|---:|---:|---:|
| Total TTT | 210.617 | 226.745 | -7.66% | No |
| Freeway TTT | 36.224 | 71.839 |  |  |
| Urban TTT | 174.393 | 154.907 |  |  |
| Boundary B_in | 0.1379 | 0.1347 |  | No |
| Boundary B_out | 0.0817 | 0.1694 |  | No |
| Boundary CV (descriptive) | 1.071 | 1.141 |  |  |

## Control Validation
- ramp_metering: Yes. metering_active_steps=5, mean_total_metering_error=54.36, max_metering_violation=270.8, ramp_queue_overflow_duration=0
- vsl: No. vsl_active_steps=1, vsl_feasible_rate=1, vsl_change_violation_count=0, density_exceedance_duration=2
- green_time: Yes. cycle_sum_error=1.421e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-19.49
- boundary_balance: No. B_in=0.1347, B_out=0.1694, eps_balance=0.03, CV_boundary=1.141, MaxMin_boundary=27.39, OverflowRatio_boundary=0, boundary_queue_balance_improvement=-6.461, boundary_balance_degenerate=1, boundary_balance_controllable=0, boundary_empty_ratio=0.7143, boundary_saturation_ratio=0, boundary_in_empty_ratio=0.7143, boundary_out_empty_ratio=0.6957, boundary_in_saturation_ratio=0, boundary_out_saturation_ratio=0, urban_net_inflow_tracking_error_veh_h=1068, urban_accumulation_abs_error_veh=153.3

## Diagnostics
- Dominant failure mode: main_improvement_below_target
- expand leader candidate ranges
- reduce smoothness weights
- increase prediction horizon or Nash iterations
- increase density penalty or lower N_UF_star upper range
- boundary balance is degenerate; inspect saturation/empty ratios before tuning

## Attempt History
- attempt_0: improvement=-7.66%, passed=False, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
