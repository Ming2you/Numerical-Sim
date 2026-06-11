# Experiment Report: peak_demand

## Metadata
- Scenario: peak_demand
- Baseline mode: fixed_signal_fixed_speed
- Controller mode: stackelberg_mpc
- Seed: 42
- Simulation horizon: 7200 s

## Final Result
**FAIL**

| Metric | Baseline | Proposed | Improvement | Pass |
|---|---:|---:|---:|---:|
| Total TTT | 7751.424 | 6546.003 | 15.55% | Yes |
| Freeway TTT | 985.454 | 296.819 |  |  |
| Urban TTT | 6765.969 | 6249.184 |  |  |
| Boundary B_in | 0.1268 | 0.1243 |  | No |
| Boundary B_out | 0.0874 | 0.0898 |  | No |
| Boundary CV (descriptive) | 1.199 | 1.097 |  |  |

## Control Validation
- ramp_metering: No. metering_active_steps=39, mean_total_metering_error=1678, max_metering_violation=4711, ramp_queue_overflow_duration=0
- vsl: No. vsl_active_steps=7, vsl_feasible_rate=1, vsl_change_violation_count=2, density_exceedance_duration=8
- green_time: Yes. cycle_sum_error=2.842e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0.1429
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-516.8
- boundary_balance: No. B_in=0.1243, B_out=0.08979, eps_balance=0.03, CV_boundary=1.097, MaxMin_boundary=249, OverflowRatio_boundary=0.1429, boundary_queue_balance_improvement=8.547, boundary_balance_degenerate=1, boundary_balance_controllable=0, boundary_empty_ratio=0.6522, boundary_saturation_ratio=0.3478, boundary_in_empty_ratio=0.6286, boundary_out_empty_ratio=0.6522, boundary_in_saturation_ratio=0.08571, boundary_out_saturation_ratio=0.3478, urban_net_inflow_tracking_error_veh_h=674.4, urban_accumulation_abs_error_veh=48.2

## Diagnostics
- Dominant failure mode: freeway_density_or_vsl_validation_failed
- increase density penalty or lower N_UF_star upper range
- increase ramp queue penalty or relax infeasible N_UF tracking
- boundary balance is degenerate; inspect saturation/empty ratios before tuning

## Attempt History
- attempt_0: improvement=15.55%, passed=False, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
