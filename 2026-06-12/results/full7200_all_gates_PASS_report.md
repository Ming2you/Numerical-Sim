# Experiment Report: peak_demand

## Metadata
- Scenario: peak_demand
- Baseline mode: fixed_signal_fixed_speed
- Controller mode: stackelberg_mpc
- Seed: 42
- Simulation horizon: 7200 s

## Final Result
**PASS**

| Metric | Baseline | Proposed | Improvement | Pass |
|---|---:|---:|---:|---:|
| Total TTT | 7751.424 | 6030.089 | 22.21% | Yes |
| Freeway TTT | 985.454 | 307.296 |  |  |
| Urban TTT | 6765.969 | 5722.793 |  |  |
| Boundary B_in | 0.0280 | 0.0120 |  | Yes |
| Boundary B_out | 0.0058 | 0.0038 |  | Yes |
| Boundary CV (descriptive) | 1.199 | 1.060 |  |  |

## Control Validation
- ramp_metering: Yes. metering_active_steps=38, mean_total_metering_error=75.48, max_metering_violation=1491, ramp_queue_overflow_duration=0
- vsl: Yes. vsl_active_steps=14, vsl_feasible_rate=1, vsl_change_violation_count=0, density_exceedance_duration=16
- green_time: Yes. cycle_sum_error=2.842e-14, green_min_violation_count=0, green_max_violation_count=0, queue_overflow_count=0
- offset: Yes. offset_range_violation_count=0, offset_smoothness_violation_count=0, corridor_delay_change=-1043
- boundary_balance: Yes. B_in=0.01201, B_out=0.003793, eps_balance=0.03, CV_boundary=1.06, MaxMin_boundary=180.2, OverflowRatio_boundary=0, boundary_queue_balance_improvement=11.57, boundary_balance_degenerate=0, boundary_balance_controllable=1, boundary_empty_ratio=0.05714, boundary_saturation_ratio=0.525, boundary_in_empty_ratio=0.05714, boundary_out_empty_ratio=0, boundary_in_saturation_ratio=0, boundary_out_saturation_ratio=0.525, urban_net_inflow_tracking_error_veh_h=71.91, urban_accumulation_abs_error_veh=41.59

## Diagnostics
- Dominant failure mode: none
- all configured acceptance criteria passed

## Attempt History
- attempt_0: improvement=22.21%, passed=True, changes=default config

## Ablation Results
- Not run for this attempt.

## Caveats
- This implementation uses deterministic grid/heuristic follower solvers when nonlinear optimization dependencies are unavailable.
- `N_P_star` is an urban accumulation target in vehicles; `N_UF_star` is a freeway on-ramp flow target in vehicles per hour.
- Boundary queue balancing is evaluated separately from Total TTT.
