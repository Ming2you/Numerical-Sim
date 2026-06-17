# Demand-Compatible Reference/Ceiling Design Note

## Purpose

This note summarizes the proposed next modification for the proposed
Stackelberg controller after the recent leader-objective diagnostics.

The key design change is to stop interpreting the protected-network
accumulation target and freeway accumulation reference as fixed targets that
should be reached in every demand regime. Instead, both urban and freeway
references should be demand-compatible: low demand should not be forced toward
critical accumulation, while peak demand may justify operation near the
critical accumulation.

This follows the interpretation in Chen et al. (2025): off-peak low demand may
need no control, peak demand can use a target close to the critical
accumulation, and medium/off-peak demand should not be forced to a critical
target that is above the steady state implied by the demand pattern.

Relevant references:

- Chen et al. (2025), "Learning-Based Tracking Perimeter Control for Two-region
  Macroscopic Traffic Dynamics", arXiv:2505.21818.
- Jusoh and Ampountolas (2024), "Multi-gated perimeter flow control for
  monocentric cities: Efficiency and equity", arXiv:2403.06312.
- Yang, Zheng, and Menendez (2016), "Multi-scale Perimeter Control Approach in
  a Connected-Vehicle Environment", arXiv:1612.05910.

## Current Issue

The current proposed Stackelberg controller can select leader targets such as:

```text
N_P_star ~= 0.9 * N_P_crit or higher
N_UF_star ~= upper range / max feasible release
```

This is reasonable in a congested regime, but it can be wrong in low or medium
demand. If the current protected accumulation is far below `N_P_crit`, a fixed
critical-band `N_P_star` can make the urban follower allocate positive net
inflow simply because the city is "below target". That creates urban TTT without
necessarily improving the closed-loop system.

The same interpretation problem can appear on the freeway side if a freeway
critical state is treated as something to reach, rather than a ceiling or
congestion threshold to avoid exceeding.

## Proposed Principle

For each subsystem `X in {P, F}`:

- `P`: protected urban network accumulation.
- `F`: freeway accumulation.

Use a demand-compatible reference:

```text
N_X_ref(k) = demand-regime-aware reference or ceiling
```

rather than a fixed target:

```text
N_X_star = N_X_crit
```

The controller should not create vehicles or force accumulation upward just to
reach a critical value. It should intervene mainly when the predicted or current
state exceeds the demand-compatible reference.

## Candidate Mathematical Form

Let `N_X^0(k+H)` be the predicted accumulation under neutral/no-control or
demand-serving operation over a short horizon. Then:

```text
if N_X^0 <= eta_low * N_X_crit:
    N_X_ref = N_X^0
elif N_X^0 < eta_peak * N_X_crit:
    N_X_ref = (1 - alpha) * N_X^0 + alpha * N_X_crit
else:
    N_X_ref = N_X_crit
```

where:

- `eta_low` defines the low-demand/no-control regime.
- `eta_peak` defines the peak/congested regime.
- `alpha` controls how aggressively the reference moves toward critical
  accumulation in the intermediate regime.

This makes `N_X_ref` high only when the demand regime can plausibly support it.

## Urban Side: `N_P`

### Current Symmetric Tracking Interpretation

The current allocation path can behave like:

```text
error = N_P_star - current_N_P
target_net_inflow = error / feedback_horizon
```

This is symmetric tracking. If `current_N_P < N_P_star`, it can produce a
positive net-inflow target. That is exactly the behavior we want to avoid in
low demand.

### Proposed Asymmetric Ceiling Interpretation

Use `N_P_ref` or `N_P_ceiling` as a ceiling:

```text
excess_P = max(0, current_N_P - N_P_ref)
target_net_inflow = -min(flow_limit, excess_P / feedback_horizon)
```

If:

```text
current_N_P <= N_P_ref
```

then:

```text
target_net_inflow = neutral_or_demand_serving_value
```

The important point is that the controller does not intentionally fill the
protected network toward `N_P_crit` when the demand pattern does not support
that state.

## Freeway Side: `N_F`

The proposed controller currently has `N_UF_star` as the explicit leader
freeway-side variable, while `N_F` is mainly represented through freeway density
and accumulation penalties.

The demand-compatible design should introduce an internal freeway reference:

```text
N_F_ref = demand-compatible freeway accumulation ceiling
```

A simple critical accumulation estimate is:

```text
N_F_crit = rho_crit * sum_lanes_and_lengths
```

More explicitly:

```text
N_F_crit =
    sum over freeway segments i:
        rho_crit * segment_length_km * effective_lanes_i
```

Then ramp metering and VSL should respond asymmetrically:

```text
excess_F = max(0, current_N_F - N_F_ref)
N_UF_star = feasible_release - K_F * excess_F / feedback_horizon
```

with clipping to physical bounds:

```text
0 <= N_UF_star <= feasible_release
```

Thus `N_UF_star` is not an equality target. It is a ramp-release ceiling used to
avoid adding vehicles to an already overloaded freeway.

## Input-Output Allocation Must Change Too

The leader-side reinterpretation is not sufficient by itself. The
input-output allocation module must be changed at the same time, otherwise the
allocation module may continue to treat `N_P_star` as a net-inflow tracking
target.

### Current Allocation Semantics

Current path:

```text
N_P_star
  -> urban_accumulation_feedback_flow()
  -> target_net_inflow
  -> allocation module projects movement flows to match target_net_inflow
```

This is still target tracking.

### Proposed Allocation Semantics

New path:

```text
N_P_ref / N_P_ceiling
  -> compute net-inflow ceiling or drain command
  -> allocate feasible movement service without exceeding the ceiling
```

The residual should be asymmetric:

```text
violation = max(0, projected_net_inflow - net_inflow_ceiling)
penalty = violation^2
```

If demand is insufficient and realized inflow is below the command, that should
not be considered a tracking failure. It is unused or infeasible capacity.

This is consistent with Jusoh and Ampountolas (2024), where actual gate flow is
bounded by demand, ordered flow, and maximum gate capacity:

```text
q_o(t) = min{d_o(t), q_o_ordered(t), q_o_max}
```

except in oversaturation, where a minimum gate release can be imposed to avoid
complete blockage.

It is also consistent with Yang, Zheng, and Menendez (2016), where movement
departure is bounded by both demand/queue and green-capacity:

```text
mu_m(k) = min{available_queue_plus_arrival, green_capacity}
```

## Required Code Changes

### 1. `src/controllers/leader.py`

Add helper methods:

```text
_demand_compatible_np_ref(state, demand, previous)
_demand_compatible_nf_ref(state, demand, previous)
_freeway_critical_accumulation(state)
```

Change `N_P_star` candidate generation:

```text
old:
    candidates around 0.9~1.05 * N_P_crit

new:
    include current_N_P
    include previous_N_P_star
    include N_P_ref
    include N_P_crit only as a peak/congestion candidate
```

Change leader objective:

```text
old:
    w_P * max(0, N_P - N_P_crit)
    w_F * density_excess

new:
    w_P * max(0, N_P - N_P_ref)
    w_F * max(0, N_F - N_F_ref)
    plus existing density_excess for segment-level spillback risk
```

Diagnostics to log:

```text
leader_N_P_ref
leader_N_P_ref_mode
leader_N_F_ref
leader_N_F_ref_mode
leader_N_F_crit
leader_N_P_excess_over_ref
leader_N_F_excess_over_ref
```

### 2. `src/models/urban_queue_model.py`

Change `urban_accumulation_feedback_flow()` from symmetric tracking to
asymmetric ceiling mode, guarded by config:

```text
leader.N_P_feedback_mode:
  - tracking_target
  - asymmetric_ceiling
```

For `asymmetric_ceiling`:

```text
excess = max(0, current_N_P - target_accumulation_veh)
raw_flow = -excess / feedback_horizon
```

When the city is below the reference, return neutral/demand-serving flow rather
than positive fill-up flow.

### 3. `src/controllers/inflow_outflow_allocation.py`

Change the allocation objective from equality tracking to ceiling violation
when `N_P_feedback_mode == asymmetric_ceiling`:

```text
old residual:
    residual = net_flow - target

new residual:
    residual = max(0, net_flow - net_flow_ceiling)
```

The projection step should also respect asymmetric feasibility:

- If the command is a ceiling, avoid forcing net flow up to the ceiling.
- If demand or queue is insufficient, log the infeasible/raw gap instead of
  treating it as a tracking failure.
- Preserve boundary balance among feasible movement services.

Diagnostics to log:

```text
allocation_net_inflow_ceiling_veh_h
allocation_net_inflow_ceiling_violation_veh_h
allocation_target_type
allocation_target_infeasible_veh_h
```

### 4. `src/controllers/freeway_follower.py`

Treat `N_UF_star` as a release ceiling, not equality target:

```text
effective_target = min(N_UF_star, feasible_release)
```

When `N_F <= N_F_ref`, use no-metering or demand-serving release unless local
receiving constraints bind.

When `N_F > N_F_ref`, reduce release according to the freeway excess:

```text
N_UF_star = feasible_release - K_F * max(0, N_F - N_F_ref) / H_F
```

The follower should continue to log:

```text
metering_target_infeasible
metering_tracking_residual
```

but under ceiling semantics, under-release due to insufficient demand should not
be scored as a failure.

### 5. `src/controllers/wu_distributed.py`

For `WU-MATCHED-STACKELBERG`, update leader candidates:

```text
old:
    p_values = [0.8 * current_N_P, current_N_P, N_P_crit]
    f_values = [0.8 * current_N_F, current_N_F, 1.2 * current_N_F]

new:
    p_values = [current_N_P, previous/reference N_P, N_P_ref, N_P_crit]
    f_values = [current_N_F, N_F_ref, N_F_crit]
```

Local conditioning terms should use reference/ceiling exceedance:

```text
max(0, n_pred - omega * N_ref)
```

not a symmetric target gap.

### 6. Config

Add conservative config entries:

```yaml
leader:
  demand_compatible_reference_enabled: true
  demand_reference_low_factor: 0.75
  demand_reference_peak_factor: 0.95
  demand_reference_blend_alpha: 0.50
  N_P_feedback_mode: asymmetric_ceiling
  N_P_neutral_net_inflow_veh_h: 0.0
  N_F_feedback_horizon_h: 0.25
  N_F_metering_gain: 1.0
```

Default should be documented carefully. If backward compatibility is needed,
the old behavior can remain available as:

```yaml
leader:
  demand_compatible_reference_enabled: false
  N_P_feedback_mode: tracking_target
```

## Validation Plan

Minimum smoke tests:

```text
controllers:
  - PROPOSED-FOLLOWERS-ONLY
  - PROPOSED-STACKELBERG

scenarios:
  - low_demand
  - medium_demand
  - peak_demand

horizons:
  - 360 s
  - 720 s
```

Metrics:

```text
Total TTT
Total Delay
Freeway TTT
Urban TTT
Throughput
Terminal vehicles
N_P_ref vs current N_P
N_F_ref vs current N_F
N_UF_star vs realized ramp release
allocation ceiling violation
leader objective term breakdown
Nash convergence/residual
```

Expected first-order effect:

- In low/medium demand, Stackelberg should stop selecting targets that
  intentionally fill the city toward `N_P_crit`.
- Urban TTT should not increase merely because `current_N_P < N_P_crit`.
- `N_UF_star` should behave as a feasible release ceiling.
- The allocation module should report unused/infeasible capacity separately
  from true ceiling violations.

## Non-Goals

This note does not claim the controller passes the final acceptance criteria.
It only defines the next implementation direction. After implementation, the
usual requirements still apply:

- unit tests pass;
- closed-loop smoke test completes;
- baseline/proposed use same scenario and demand;
- Total TTT improvement meets the configured threshold;
- boundary queue balance is not degraded;
- ramp metering, VSL, offset, green allocation, and inflow-outflow allocation
  are logged.
