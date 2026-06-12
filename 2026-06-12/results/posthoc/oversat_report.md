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
| Total TTT | 17136.132 | 13013.445 | 24.06% | Yes |
| Freeway TTT | 3632.178 | 340.855 |  |  |
| Urban TTT | 13503.955 | 12672.590 |  |  |
| Boundary B_in | 0.0274 | 0.0054 |  | No |
| Boundary B_out | 0.0017 | 0.0011 |  | No |
| Boundary CV (descriptive) | 1.202 | 1.023 |  |  |

## Control Validation
- ramp_metering: Yes. metering_active_steps=40, mean_total_metering_error=56.46, max_metering_violation=702.5, ramp_queue_overflow_duration=0
- vsl: Yes. vsl_active_steps=24, vsl_feasible_rate=1, vsl_change_violation_count=0, density_exceedance_duration=23
- green_time: Yes. cycle_sum_error=2.842e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0.5
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-831.4
- boundary_balance: No. B_in=0.005394, B_out=0.001127, eps_balance=0.03, CV_boundary=1.023, MaxMin_boundary=667.1, OverflowRatio_boundary=0.5, boundary_queue_balance_improvement=14.89, boundary_balance_degenerate=0, boundary_balance_controllable=1, boundary_empty_ratio=0, boundary_saturation_ratio=0.7438, boundary_in_empty_ratio=0, boundary_out_empty_ratio=0, boundary_in_saturation_ratio=0, boundary_out_saturation_ratio=0.7438, urban_net_inflow_tracking_error_veh_h=300.5, urban_accumulation_abs_error_veh=147.5

## Diagnostics
- Dominant failure mode: boundary_queue_balance_failed
- increase movement-level boundary balance weight or switch receiving-space rule

## Attempt History
- attempt_0: improvement=24.06%, passed=False, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
