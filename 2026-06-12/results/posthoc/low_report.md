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
| Total TTT | 1281.294 | 1206.790 | 5.81% | No |
| Freeway TTT | 182.881 | 189.755 |  |  |
| Urban TTT | 1098.413 | 1017.034 |  |  |
| Boundary B_in | 0.1688 | 0.1014 |  | No |
| Boundary B_out | 0.0433 | 0.0124 |  | No |
| Boundary CV (descriptive) | 1.603 | 0.751 |  |  |

## Control Validation
- ramp_metering: Yes. metering_active_steps=39, mean_total_metering_error=21.04, max_metering_violation=562.4, ramp_queue_overflow_duration=0
- vsl: Yes. vsl_active_steps=0, vsl_feasible_rate=1, vsl_change_violation_count=0, density_exceedance_duration=0
- green_time: Yes. cycle_sum_error=2.842e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-81.38
- boundary_balance: No. B_in=0.1014, B_out=0.01243, eps_balance=0.03, CV_boundary=0.7513, MaxMin_boundary=10.59, OverflowRatio_boundary=0, boundary_queue_balance_improvement=53.14, boundary_balance_degenerate=0, boundary_balance_controllable=1, boundary_empty_ratio=0.1786, boundary_saturation_ratio=0, boundary_in_empty_ratio=0.1786, boundary_out_empty_ratio=0, boundary_in_saturation_ratio=0, boundary_out_saturation_ratio=0, urban_net_inflow_tracking_error_veh_h=83.53, urban_accumulation_abs_error_veh=162.2

## Diagnostics
- Dominant failure mode: main_improvement_below_target
- expand leader candidate ranges
- reduce smoothness weights
- increase prediction horizon or Nash iterations
- increase movement-level boundary balance weight or switch receiving-space rule

## Attempt History
- attempt_0: improvement=5.81%, passed=False, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
