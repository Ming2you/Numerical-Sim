# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 5. Simulation and Experiment Pipeline

### 5.1 Baseline cases

Implement at least the following baseline modes:

```yaml
baseline_modes:
  - no_control
  - fixed_signal_fixed_speed
  - local_control_only
```

Definitions:

- `no_control`: no active ramp metering, no VSL, fixed green time and offset
- `fixed_signal_fixed_speed`: fixed signal plans and fixed speed limit; ramp flow follows demand/capacity only
- `local_control_only`: freeway and urban controls operate independently without leader coordination

The primary improvement rate should compare the proposed controller to `fixed_signal_fixed_speed` unless configured otherwise.

### 5.2 Proposed-controller case

Run the closed-loop Stackelberg MPC controller over the same demand, initial state, and simulation horizon as the baseline.

Use fixed random seeds for reproducibility.

### 5.3 Ablation cases

Implement ablation runs to diagnose which control component contributes to performance:

```yaml
ablation_modes:
  - proposed_without_ramp_metering
  - proposed_without_vsl
  - proposed_without_offset_control
  - proposed_without_green_time_allocation
  - proposed_without_inflow_outflow_allocation
```

These are required for diagnosis when the proposed controller fails the 8% improvement criterion.

### 5.4 Scenario set

Support multiple demand scenarios:

```yaml
scenarios:
  - name: low_demand
  - name: medium_demand
  - name: peak_demand
  - name: oversaturated_demand
  - name: incident_or_capacity_drop
```

The controller passes only if it satisfies the acceptance criteria on the primary evaluation scenario. If multiple scenarios are configured as required, use the mean improvement and also report scenario-specific pass/fail results.

---
