# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 10. Tests

Implement tests before relying on experiment results.

### 10.1 Constraint tests

Required tests:

```text
test_vsl_values_are_discrete
test_green_times_sum_to_cycle_length
test_green_time_bounds
test_offset_range
test_ramp_metering_bounds
test_total_metering_tracking_or_infeasibility_flag
test_boundary_queue_balance_safe_division
test_no_negative_density_speed_queue
```

### 10.2 Metric tests

Required tests:

```text
test_improvement_rate_lower_is_better
test_improvement_rate_higher_is_better
test_boundary_cv_zero_queue_case
test_balance_index_equal_queue_is_zero_or_near_zero
test_balance_index_unbalanced_queue_is_positive
```

### 10.3 Closed-loop smoke test

Create a small synthetic network and run:

```text
baseline simulation -> proposed simulation -> metrics -> report
```

The smoke test does not need to achieve 8% improvement, but it must complete without numerical errors and produce all required output files.

---
