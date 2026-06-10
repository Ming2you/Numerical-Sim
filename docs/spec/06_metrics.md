# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 6. Metrics and Acceptance Criteria

### 6.1 Main performance metric

Default main metric:

```text
Total TTT = TTT_freeway + TTT_urban
```

The improvement rate is:

```text
ImprovementRate(%) = 100 * (Metric_baseline - Metric_proposed) / max(Metric_baseline, eps)
```

The proposed controller passes the main criterion if:

```text
ImprovementRate >= 8.0
```

For cost metrics such as TTT/TTS, lower is better. If the configured metric is a benefit metric where higher is better, use:

```text
ImprovementRate(%) = 100 * (Metric_proposed - Metric_baseline) / max(abs(Metric_baseline), eps)
```

The code must explicitly store whether the metric is `lower_is_better` or `higher_is_better`.

### 6.2 Control-specific validation metrics

The simulation must verify each proposed control.

#### Ramp metering validation

Report:

```text
total_metering_error = abs(sum_r r_ramp[r] - N_UF_star)
max_metering_violation
ramp_queue_overflow_count
ramp_queue_overflow_duration
```

Pass if:

```text
mean(total_metering_error) <= eps_F
ramp_queue_overflow_duration <= configured_tolerance
```

#### VSL validation

Report:

```text
vsl_feasible_rate
vsl_change_violation_count
density_exceedance_duration
speed_drop_reduction
```

Pass if:

```text
all VSL values are in {50, 60, 70, 80, 90, 100}
VSL smoothness violations == 0 unless explicitly relaxed
controlled density exceedance <= baseline density exceedance
```

#### Green time allocation validation

Report:

```text
cycle_sum_error
green_min_violation_count
green_max_violation_count
movement_capacity_violation_count
queue_overflow_count
```

Pass if:

```text
cycle_sum_error <= tolerance
green_min_violation_count == 0
green_max_violation_count == 0
queue_overflow_count does not increase relative to baseline
```

#### Offset validation

Report:

```text
offset_range_violation_count
offset_smoothness_violation_count
corridor_delay_change
number_of_stops_proxy_change
```

Pass if:

```text
0 <= offset < cycle_length for all intersections and times
offset_smoothness_violation_count == 0 unless explicitly relaxed
corridor delay does not increase materially relative to baseline
```

#### Inflow-outflow allocation and boundary queue balancing validation

Report:

```text
B_in
B_out
eps_balance
CV_boundary
MaxMin_boundary
OverflowRatio_boundary
boundary_queue_balance_improvement
boundary_balance_degenerate
boundary_empty_ratio
boundary_saturation_ratio
net_inflow_tracking_error
```

Default descriptive balance improvement:

```text
BalanceImprovement(%) = 100 * (CV_boundary_baseline - CV_boundary_proposed) / max(CV_boundary_baseline, eps)
```

`CV_boundary` and `MaxMin_boundary` are descriptive diagnostics. The acceptance gate must use the same movement-level density vectors as the §4.4 inflow-outflow allocation objective:

```text
k_inflow  = density vector of boundary_in + off_ramp movements
k_outflow = density vector of boundary_out + on_ramp movements
B_in/B_out = inverse-participation balance terms computed from those vectors
```

Pass if:

```text
B_in <= eps_balance
B_out <= eps_balance
boundary_balance_degenerate == false
OverflowRatio_boundary_proposed <= OverflowRatio_boundary_baseline
net_inflow_tracking_error <= eps_U or is explicitly logged as infeasible
```

The 8% improvement criterion applies to the main system-level metric by default. Boundary queue balancing should be separately reported and must not be hidden by total TTT improvement.

---
