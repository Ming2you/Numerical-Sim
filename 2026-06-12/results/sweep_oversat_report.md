# Experiment Report: oversaturated_demand

## Metadata
- Scenario: oversaturated_demand
- Baseline mode: fixed_signal_fixed_speed
- Controller mode: stackelberg_mpc
- Seed: 42
- Simulation horizon: 7200 s

## Final Result
**FAIL**

| Metric | Baseline | Proposed | Improvement | Pass |
|---|---:|---:|---:|---:|
| Total TTT | 16983.662 | 12327.506 | 27.42% | Yes |
| Freeway TTT | 3631.612 | 335.067 |  |  |
| Urban TTT | 13352.050 | 11992.439 |  |  |
| Boundary B_in | 0.0276 | 0.0145 |  | No |
| Boundary B_out | 0.0017 | 0.0011 |  | No |
| Boundary CV (descriptive) | 1.221 | 1.135 |  |  |

## Control Validation
- ramp_metering: No. metering_active_steps=40, mean_total_metering_error=245.9, max_metering_violation=1295, ramp_queue_overflow_duration=0
- vsl: Yes. vsl_active_steps=28, vsl_feasible_rate=1, vsl_change_violation_count=0, density_exceedance_duration=26
- green_time: Yes. cycle_sum_error=1.421e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0.4286
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-1360
- boundary_balance: No. B_in=0.01454, B_out=0.001068, eps_balance=0.03, CV_boundary=1.135, MaxMin_boundary=758.5, OverflowRatio_boundary=0.4286, boundary_queue_balance_improvement=7.052, boundary_balance_degenerate=0, boundary_balance_controllable=1, boundary_empty_ratio=0.01786, boundary_saturation_ratio=0.7438, boundary_in_empty_ratio=0.01786, boundary_out_empty_ratio=0, boundary_in_saturation_ratio=0, boundary_out_saturation_ratio=0.7438, urban_net_inflow_tracking_error_veh_h=287.3, urban_accumulation_abs_error_veh=119.7

## Diagnostics
- Dominant failure mode: ramp_metering_or_queue_validation_failed
- increase ramp queue penalty or relax infeasible N_UF tracking
- increase movement-level boundary balance weight or switch receiving-space rule

## Attempt History
- attempt_0: improvement=27.42%, passed=False, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
