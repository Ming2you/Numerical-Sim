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
| Total TTT | 6523.314 | 5426.219 | 16.82% | Yes |
| Freeway TTT | 281.775 | 304.022 |  |  |
| Urban TTT | 6241.539 | 5122.197 |  |  |
| Boundary B_in | 0.0331 | 0.0184 |  | Yes |
| Boundary B_out | 0.0028 | 0.0067 |  | Yes |
| Boundary CV (descriptive) | 1.183 | 1.074 |  |  |

## Control Validation
- ramp_metering: Yes. metering_active_steps=37, mean_total_metering_error=49.68, max_metering_violation=1491, ramp_queue_overflow_duration=0
- vsl: No. vsl_active_steps=14, vsl_feasible_rate=1, vsl_change_violation_count=0, density_exceedance_duration=15
- green_time: Yes. cycle_sum_error=1.421e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-1119
- boundary_balance: Yes. B_in=0.0184, B_out=0.00669, eps_balance=0.03, CV_boundary=1.074, MaxMin_boundary=109.9, OverflowRatio_boundary=0, boundary_queue_balance_improvement=9.224, boundary_balance_degenerate=0, boundary_balance_controllable=1, boundary_empty_ratio=0.07143, boundary_saturation_ratio=0.4938, boundary_in_empty_ratio=0.07143, boundary_out_empty_ratio=0, boundary_in_saturation_ratio=0, boundary_out_saturation_ratio=0.4938, urban_net_inflow_tracking_error_veh_h=54.06, urban_accumulation_abs_error_veh=30.05

## Diagnostics
- Dominant failure mode: freeway_density_or_vsl_validation_failed
- increase density penalty or lower N_UF_star upper range

## Attempt History
- attempt_0: improvement=16.82%, passed=False, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
