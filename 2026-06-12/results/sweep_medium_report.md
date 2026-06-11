# Experiment Report: medium_demand

## Metadata
- Scenario: medium_demand
- Baseline mode: fixed_signal_fixed_speed
- Controller mode: stackelberg_mpc
- Seed: 42
- Simulation horizon: 7200 s

## Final Result
**FAIL**

| Metric | Baseline | Proposed | Improvement | Pass |
|---|---:|---:|---:|---:|
| Total TTT | 3825.830 | 2965.066 | 22.50% | Yes |
| Freeway TTT | 237.400 | 262.791 |  |  |
| Urban TTT | 3588.430 | 2702.274 |  |  |
| Boundary B_in | 0.0923 | 0.0305 |  | No |
| Boundary B_out | 0.0054 | 0.0045 |  | No |
| Boundary CV (descriptive) | 1.600 | 1.104 |  |  |

## Control Validation
- ramp_metering: Yes. metering_active_steps=37, mean_total_metering_error=51.04, max_metering_violation=1808, ramp_queue_overflow_duration=0
- vsl: No. vsl_active_steps=4, vsl_feasible_rate=1, vsl_change_violation_count=0, density_exceedance_duration=4
- green_time: Yes. cycle_sum_error=2.842e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-886.2
- boundary_balance: No. B_in=0.0305, B_out=0.004471, eps_balance=0.03, CV_boundary=1.104, MaxMin_boundary=38.13, OverflowRatio_boundary=0, boundary_queue_balance_improvement=31, boundary_balance_degenerate=0, boundary_balance_controllable=1, boundary_empty_ratio=0.1598, boundary_saturation_ratio=0.0375, boundary_in_empty_ratio=0.1571, boundary_out_empty_ratio=0.00625, boundary_in_saturation_ratio=0, boundary_out_saturation_ratio=0.0375, urban_net_inflow_tracking_error_veh_h=40.62, urban_accumulation_abs_error_veh=58.05

## Diagnostics
- Dominant failure mode: freeway_density_or_vsl_validation_failed
- increase density penalty or lower N_UF_star upper range
- increase movement-level boundary balance weight or switch receiving-space rule

## Attempt History
- attempt_0: improvement=22.50%, passed=False, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
