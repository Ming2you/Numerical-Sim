# Experiment Report: incident_or_capacity_drop

## Metadata
- Scenario: incident_or_capacity_drop
- Baseline mode: fixed_signal_fixed_speed
- Controller mode: stackelberg_mpc
- Seed: 42
- Simulation horizon: 7200 s

## Final Result
**FAIL**

| Metric | Baseline | Proposed | Improvement | Pass |
|---|---:|---:|---:|---:|
| Total TTT | 6670.921 | 6084.334 | 8.79% | Yes |
| Freeway TTT | 281.690 | 302.908 |  |  |
| Urban TTT | 6389.231 | 5781.426 |  |  |
| Boundary B_in | 0.0335 | 0.0102 |  | No |
| Boundary B_out | 0.0027 | 0.0076 |  | No |
| Boundary CV (descriptive) | 1.138 | 1.075 |  |  |

## Control Validation
- ramp_metering: Yes. metering_active_steps=38, mean_total_metering_error=29.32, max_metering_violation=454.9, ramp_queue_overflow_duration=0
- vsl: No. vsl_active_steps=13, vsl_feasible_rate=1, vsl_change_violation_count=0, density_exceedance_duration=13
- green_time: Yes. cycle_sum_error=1.421e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0.07143
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-607.8
- boundary_balance: No. B_in=0.01023, B_out=0.007609, eps_balance=0.03, CV_boundary=1.075, MaxMin_boundary=244.6, OverflowRatio_boundary=0.07143, boundary_queue_balance_improvement=5.58, boundary_balance_degenerate=0, boundary_balance_controllable=1, boundary_empty_ratio=0.01071, boundary_saturation_ratio=0.5, boundary_in_empty_ratio=0.01071, boundary_out_empty_ratio=0, boundary_in_saturation_ratio=0, boundary_out_saturation_ratio=0.5, urban_net_inflow_tracking_error_veh_h=123.7, urban_accumulation_abs_error_veh=60.07

## Diagnostics
- Dominant failure mode: freeway_density_or_vsl_validation_failed
- increase density penalty or lower N_UF_star upper range
- increase movement-level boundary balance weight or switch receiving-space rule

## Attempt History
- attempt_0: improvement=8.79%, passed=False, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
