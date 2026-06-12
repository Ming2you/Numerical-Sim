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
| Total TTT | 3971.809 | 3135.855 | 21.05% | Yes |
| Freeway TTT | 237.134 | 266.508 |  |  |
| Urban TTT | 3734.675 | 2869.347 |  |  |
| Boundary B_in | 0.0844 | 0.0239 |  | Yes |
| Boundary B_out | 0.0054 | 0.0085 |  | Yes |
| Boundary CV (descriptive) | 1.479 | 0.930 |  |  |

## Control Validation
- ramp_metering: Yes. metering_active_steps=37, mean_total_metering_error=25.37, max_metering_violation=525.1, ramp_queue_overflow_duration=0
- vsl: No. vsl_active_steps=3, vsl_feasible_rate=1, vsl_change_violation_count=0, density_exceedance_duration=6
- green_time: Yes. cycle_sum_error=2.842e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-865.3
- boundary_balance: Yes. B_in=0.02393, B_out=0.008488, eps_balance=0.03, CV_boundary=0.9303, MaxMin_boundary=53.47, OverflowRatio_boundary=0, boundary_queue_balance_improvement=37.1, boundary_balance_degenerate=0, boundary_balance_controllable=1, boundary_empty_ratio=0.06071, boundary_saturation_ratio=0, boundary_in_empty_ratio=0.06071, boundary_out_empty_ratio=0, boundary_in_saturation_ratio=0, boundary_out_saturation_ratio=0, urban_net_inflow_tracking_error_veh_h=48.26, urban_accumulation_abs_error_veh=63.13

## Diagnostics
- Dominant failure mode: freeway_density_or_vsl_validation_failed
- increase density penalty or lower N_UF_star upper range

## Attempt History
- attempt_0: improvement=21.05%, passed=False, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
