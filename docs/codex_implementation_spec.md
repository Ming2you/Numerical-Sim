# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 0. Purpose

Implement an end-to-end simulation and control framework for the proposed MPC-based Stackelberg game controller.

The implementation must include not only the controller logic, but also a closed-loop simulation validation pipeline that checks whether the proposed controls work as intended:

- ramp metering
- variable speed limit (VSL)
- signal offset control
- movement-level green time allocation
- inflow-outflow allocation for boundary queue balancing

The system must compare the proposed controller against a baseline simulation. The proposed controller passes only when the target performance improvement is at least **8%** on the main system-level metric, unless a different metric is explicitly configured.

If the controller does not pass, the code must diagnose likely causes, adjust controller/configuration parameters, rerun the simulation, and produce a final report showing all attempts.

---

## 1. Background and Control Concept

The target method is an MPC-based Stackelberg game controller for a mixed urban-freeway network.

The upper-level **leader** decides coordination variables:

- `N_P_star`: target net inflow to the protected urban network
- `N_UF_star`: target total metering rate from urban roads to the freeway

Given the leader decision, the lower-level **followers** solve decentralized control problems:

- Freeway follower:
  - ramp metering rate for each ramp
  - VSL for each freeway link or segment
- Urban follower:
  - inflow-outflow allocation
  - movement-level green time allocation
  - signal offset adjustment

The follower layer should approximate a Nash-equilibrium-like response under the selected leader decision. The leader evaluates the follower response using system-level performance, including TTT/TTS and target-exceedance penalties, then selects the best leader decision.

The implementation should treat the controller as a closed-loop MPC controller. At each control interval:

1. Read current traffic state.
2. Predict traffic evolution over the prediction horizon.
3. Enumerate or optimize leader candidates.
4. For each leader candidate, solve follower responses.
5. Choose the leader candidate that minimizes the leader objective.
6. Apply only the first-step control actions to the simulator.
7. Advance the simulation.
8. Log state, control, objective, and diagnostic metrics.

---

## 2. Implementation Scope

### 2.1 Mandatory modules

Implement the following modules.

```text
src/
  config/
    default.yaml
    scenarios.yaml
  models/
    metanet.py
    urban_queue_model.py
    demand.py
    state.py
  controllers/
    leader.py
    freeway_follower.py
    urban_follower.py
    nash_solver.py
    stackelberg_mpc.py
    auto_tuner.py
  simulation/
    simulator.py
    baseline.py
    closed_loop_runner.py
  evaluation/
    metrics.py
    diagnostics.py
    report.py
    plots.py
  experiments/
    run_experiment.py
    run_ablation.py
  tests/
    test_constraints.py
    test_metrics.py
    test_closed_loop_smoke.py
```

If the current repository already has a different structure, adapt this structure without breaking existing code. Keep module boundaries equivalent.

---

## 3. Traffic Models

### 3.1 Freeway model: METANET-style dynamics

Implement a METANET-style freeway model with the following core state variables:

- `rho[m, i]`: density of segment `i` on link `m`
- `v[m, i]`: speed of segment `i` on link `m`
- `q[m, i]`: flow of segment `i` on link `m`
- `w[o]`: on-ramp/origin queue

Core equations to implement:

```text
q[m,i](k) = rho[m,i](k) * v[m,i](k) * lanes[m]

rho[m,i](k+1) = rho[m,i](k)
                + T_f / (L[m] * lanes[m]) * (q[m,i-1](k) - q[m,i](k))

V_desired[m,i](k) = v_free[m] * exp(-1/a[m] * (rho[m,i](k) / rho_crit[m]) ** a[m])
```

Implement speed update using the Payne/METANET form with optional terms for:

- relaxation to desired speed
- convection
- anticipation
- ramp merging speed drop
- lane-drop/weaving speed drop

The model must support VSL by modifying the effective desired speed or maximum allowed segment speed.

### 3.2 Ramp queue and ramp metering

For each on-ramp/origin `o`, implement:

```text
w[o](k+1) = w[o](k) + T_f * (d[o](k) - q_ramp[o](k))
```

The ramp outflow must satisfy:

```text
0 <= q_ramp[o](k) <= q_ramp_max[o]
q_ramp[o](k) <= demand[o](k) + w[o](k) / T_f
q_ramp[o](k) <= receiving_capacity_of_downstream_freeway_segment
```

Ramp metering control must also satisfy the total metering target from the leader:

```text
abs(sum_r q_ramp[r](k) - N_UF_star(k)) <= eps_F
```

If this constraint is infeasible, the controller must project to the nearest feasible solution and log the violation.

### 3.3 Urban model: horizontal queue and turning-direction-dependent queues

Implement an urban queue model that supports:

- horizontal queues
- turning-direction-dependent queues
- blocking due to limited receiving space
- signal phase-dependent departure
- short time steps for offset-sensitive simulation

Core state variables:

- `x[o, s, d]`: queue length of vehicles from origin `o` through intersection `s` toward destination `d`
- `m_arr[o, s, d]`: arriving vehicles
- `m_dep[o, s, d]`: departing vehicles
- `S[s, d]`: available downstream storage/free space
- `beta[o, s, d]`: turning ratio
- `g[o, s, d]`: binary or effective green indicator

For a movement, implement intended departure:

```text
if signal_is_red:
    m_dep_int[o,s,d](k) = 0
else:
    m_dep_int[o,s,d](k) = min(x[o,s,d](k) + m_arr[o,s,d](k), T_u * Q_cap[o,s,d])
```

Queue update:

```text
x[o,s,d](k+1) = x[o,s,d](k) + m_arr[o,s,d](k) - m_dep[o,s,d](k)
```

Receiving-space update:

```text
S[s,d](k+1) = S[s,d](k) - inbound_to_link[s,d](k) + outbound_from_link[s,d](k)
```

When total intended departures exceed available receiving space, implement a configurable allocation rule:

- `main_priority`: mainline movement receives priority, remaining space goes to others
- `equal_split`: available storage is split across competing movements
- `proportional`: available storage is distributed proportional to intended departures

The default should be `proportional`, but include the other two options for ablation and diagnosis.

---

## 4. Controller Implementation

### 4.1 Stackelberg MPC controller

Implement a controller class:

```python
class StackelbergMPCController:
    def decide(self, state, demand_forecast, previous_control, config) -> ControlAction:
        ...
```

At every control interval, it must:

1. Generate leader candidate pairs `(N_P_star, N_UF_star)`.
2. For each leader candidate:
   - solve freeway follower response
   - solve urban follower response
   - iterate follower responses until convergence or maximum Nash iterations
   - simulate/predict state trajectory over horizon
   - compute leader objective
3. Select the candidate with minimum objective.
4. Return first-step controls:
   - ramp metering rates
   - VSL values
   - green times
   - offsets
   - inflow-outflow allocation decisions

### 4.2 Leader objective

Implement the leader objective as configurable, with this default form:

```text
J_L = sum_over_horizon[
        n_P(t) + n_F(t)
        + w_P * positive_part(n_P(t) - n_P_star)
        + w_F * sum_m sum_i L[m] * lanes[m] * positive_part(rho[m,i](t) - rho_crit[m])
        + w_L * L1_norm(U_L(t) - U_L(t-1))
      ]
```

where:

```text
U_L(t) = [N_P_star(t), N_UF_star(t)]
positive_part(x) = max(x, 0)
```

The implementation must allow the leader to use follower-response TTT/TTS directly as the main term if configured:

```yaml
leader:
  objective_mode: "state_accumulation"  # or "follower_ttt"
```

If `objective_mode = follower_ttt`, then:

```text
J_L = TTT_freeway + TTT_urban + target_exceedance_penalties + smoothness_penalty
```

### 4.3 Freeway follower

Implement a freeway follower that chooses:

```text
R_F = [r_ramp_star, vsl_link_star]
```

with:

- ramp metering rate for each ramp
- VSL for each freeway link/segment

VSL feasible set:

```text
v_l_star in {50, 60, 70, 80, 90, 100}  # km/h
```

Default objective:

```text
J_F = sum_over_horizon[
        T_f * (sum_m sum_i rho[m,i](t) * L[m] * lanes[m] + sum_r ramp_queue[r](t))
        + vsl_smoothness_penalty
        + metering_smoothness_penalty
      ]
```

Mandatory constraints:

```text
abs(sum_r r_ramp[r](k) - N_UF_star) <= eps_F
0 <= r_ramp[r](k) <= r_ramp_max[r]
0 <= ramp_queue[r](k) <= ramp_queue_max[r]
vsl in {50, 60, 70, 80, 90, 100}
abs(vsl[l](k) - vsl[l](k-1)) <= max_vsl_step
```

If the ramp queue exceeds its maximum, add a large penalty and flag `ramp_queue_overflow = true`.

### 4.4 Urban follower, stage 1: inflow-outflow allocation and green time allocation

Implement the urban follower as a two-stage controller.

Stage 1 decides movement-level green times or equivalent movement capacities to balance boundary queues and satisfy leader net inflow.

Default decision:

```text
R_U = [g_i_m]
```

The objective must include inflow and outflow queue balancing terms:

```text
B_in  = (||k_inflow||_2^2 / ||k_inflow||_1^2) - 1 / dim(k_inflow)
B_out = (||k_outflow||_2^2 / ||k_outflow||_1^2) - 1 / dim(k_outflow)
J_balance = B_in^2 + B_out^2
```

Use safe division. If all queues are zero, set the corresponding balance term to zero.

The controller must also evaluate a more interpretable boundary queue balance index:

```text
CV_boundary = std(boundary_queue) / max(mean(boundary_queue), eps)
MaxMin_boundary = max(boundary_queue) - min(boundary_queue)
OverflowRatio_boundary = count(queue > queue_max) / number_of_boundary_links
```

Mandatory constraints:

```text
abs(sum_i H_L * (sum_m_in g[i,m] * s[i,m] - sum_m_out g[i,m] * s[i,m]) - N_P_star) <= eps_U
0 <= Q_m(k) <= Q_m_max
q_min[i,m] <= q[i,m] <= q_max[i,m]
g_min[i,m] <= g[i,m] <= g_max[i,m]
sum_m g[i,m] + lost_time[i] = cycle_length[i]
```

If exact equality is infeasible, project green times to the nearest feasible cycle split and log the residual.

### 4.5 Urban follower, stage 2: offset adjustment and green time fine-tuning

Stage 2 receives stage-1 green times and adjusts:

```text
R_S = [g_i_m_star, phi_i_star]
```

where:

- `g_i_m_star`: fine-tuned green times
- `phi_i_star`: signal offset for intersection `i`

Default objective:

```text
J_S = sum_over_horizon[
        T_u * sum_i sum_m queue_or_accumulation[i,m](t)
        + offset_smoothness_penalty
        + green_smoothness_penalty
      ]
```

Mandatory constraints:

```text
abs(g_i_m_star - g_i_m_stage1) <= eps_g
0 <= phi_i(k) < cycle_length[i]
0 <= Q_m(k) <= Q_m_max
sum_m g_i_m_star + lost_time[i] = cycle_length[i]
abs(phi_i(k) - phi_i(k-1)) <= max_offset_step
```

The offset controller must use corridor/mainstream travel time information when available. If travel time information is unavailable, use link travel time estimates from queue length and average speed.

### 4.6 Follower Nash response solver

Implement an iterative follower solver:

```python
for nash_iter in range(max_nash_iter):
    freeway_response = freeway_follower.solve(state, leader_action, urban_response_prev)
    urban_response = urban_follower.solve(state, leader_action, freeway_response)
    if converged(freeway_response, urban_response, previous_responses):
        break
```

Convergence criteria:

```text
delta_objective < nash_obj_tol
and delta_control_norm < nash_control_tol
```

If convergence is not achieved:

- return the best response found so far
- set `nash_converged = false`
- log the number of iterations and residual values
- apply a penalty to the leader objective

---

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
CV_boundary
MaxMin_boundary
OverflowRatio_boundary
boundary_queue_balance_improvement
net_inflow_tracking_error
```

Default balance improvement:

```text
BalanceImprovement(%) = 100 * (CV_boundary_baseline - CV_boundary_proposed) / max(CV_boundary_baseline, eps)
```

Pass if:

```text
CV_boundary_proposed <= CV_boundary_baseline
OverflowRatio_boundary_proposed <= OverflowRatio_boundary_baseline
net_inflow_tracking_error <= eps_U or is explicitly logged as infeasible
```

The 8% improvement criterion applies to the main system-level metric by default. Boundary queue balancing should be separately reported and must not be hidden by total TTT improvement.

---

## 7. Auto-Diagnosis and Self-Improvement Loop

### 7.1 Required behavior

After each full experiment run, evaluate acceptance criteria.

If all criteria pass:

1. Save final controls, states, metrics, plots, and report.
2. Mark experiment as `PASS`.

If the main improvement is below 8% or control-specific validation fails:

1. Diagnose likely causes.
2. Modify controller/configuration parameters.
3. Rerun the full simulation.
4. Repeat until:
   - criteria pass, or
   - maximum auto-tuning iterations are reached.

### 7.2 Maximum iterations

Default:

```yaml
auto_tuning:
  enabled: true
  max_iterations: 5
  min_required_improvement_pct: 8.0
  preserve_all_runs: true
```

Do not overwrite failed runs. Save each run under:

```text
outputs/{experiment_name}/attempt_{attempt_id}/
```

### 7.3 Diagnosis rules

Implement rule-based diagnosis first. More advanced search can be added later.

#### Case A: Main improvement < 8%, but all constraints feasible

Possible causes:

- leader candidate grid is too narrow or too coarse
- prediction horizon is too short
- follower Nash solver stops too early
- smoothness penalty is too strong, suppressing control action
- system-level objective weight is inconsistent with TTT/TTS

Actions:

```text
- expand leader candidate range for N_P_star and N_UF_star
- refine leader grid around best candidate from previous run
- increase prediction horizon by one control interval if computationally feasible
- reduce smoothness weights w_L, R_p, R_i by 10-30%
- increase max_nash_iter
```

#### Case B: Freeway density exceedance remains high

Possible causes:

- metering too permissive
- VSL not restrictive enough upstream of bottleneck
- N_UF_star too high
- density penalty w_F too low

Actions:

```text
- reduce upper range of N_UF_star
- increase density exceedance penalty w_F
- allow lower VSL candidate values if already configured; otherwise keep default set
- increase ramp metering penalty for downstream density exceedance
```

#### Case C: Ramp queues overflow

Possible causes:

- metering too restrictive
- N_UF_star too low
- ramp queue penalty too weak
- freeway receiving capacity is too low due to VSL or congestion

Actions:

```text
- increase lower range of N_UF_star
- increase ramp queue overflow penalty
- relax eps_F if strict tracking is infeasible
- reduce VSL aggressiveness if it causes unnecessary throughput loss
```

#### Case D: Boundary queues are not balanced

Possible causes:

- inflow-outflow balance weight too weak
- green time min/max bounds too restrictive
- N_P_star infeasible under current demand
- storage constraints dominate the allocation problem

Actions:

```text
- increase J_balance weight
- refine green time allocation step size
- relax eps_U if the leader target is infeasible, while logging infeasibility
- adjust N_P_star candidate range toward observed feasible net inflow
- switch boundary storage allocation rule among proportional, equal_split, and main_priority for diagnostic ablation
```

#### Case E: Offset control worsens corridor delay

Possible causes:

- offset estimation uses wrong travel time
- offset smoothness penalty is too weak or too strong
- green time fine-tuning conflicts with progression

Actions:

```text
- recompute corridor travel time using current queue and speed estimates
- reduce maximum offset step if oscillatory
- increase offset smoothness weight if offsets fluctuate
- reduce green fine-tuning eps_g if offset stage is distorting stage-1 allocation
```

#### Case F: Nash solver does not converge

Possible causes:

- follower responses are too strongly coupled
- best-response updates oscillate
- action step sizes are too large

Actions:

```text
- add relaxation: response_new = alpha * response_new + (1-alpha) * response_old
- decrease alpha from 1.0 to 0.7, then 0.5 if needed
- increase max_nash_iter
- add penalty for non-convergence in leader objective
```

### 7.4 Auto-tuning search strategy

Implement deterministic auto-tuning so results are reproducible.

Recommended default:

```text
Attempt 0: default config
Attempt 1: expand leader grid and reduce smoothness penalties
Attempt 2: increase density/queue penalties based on dominant failure mode
Attempt 3: refine best leader region and increase Nash iterations
Attempt 4: adjust boundary balancing and offset parameters
Attempt 5: final best-known configuration
```

Each attempt must save:

```text
config_used.yaml
metrics_summary.json
diagnostics.json
run_log.csv
control_timeseries.csv
state_timeseries.csv
plots/
report.md
```

The final report must state clearly whether the 8% criterion was achieved.

Do not hard-code results. Do not silently discard failed attempts. Do not tune on a single seed only when multiple seeds are configured.

---

## 8. CLI Requirements

Implement command-line entry points.

### 8.1 Run one experiment

```bash
python -m experiments.run_experiment \
  --config src/config/default.yaml \
  --scenario peak_demand \
  --baseline fixed_signal_fixed_speed \
  --controller stackelberg_mpc \
  --output outputs/peak_demand_stackelberg
```

### 8.2 Run with auto-tuning

```bash
python -m experiments.run_experiment \
  --config src/config/default.yaml \
  --scenario peak_demand \
  --baseline fixed_signal_fixed_speed \
  --controller stackelberg_mpc \
  --auto-tune \
  --min-improvement-pct 8.0 \
  --output outputs/peak_demand_stackelberg_autotune
```

### 8.3 Run ablation

```bash
python -m experiments.run_ablation \
  --config src/config/default.yaml \
  --scenario peak_demand \
  --output outputs/ablation_peak_demand
```

---

## 9. Configuration Requirements

Create a YAML config with at least the following fields.

```yaml
simulation:
  T_total: 7200
  T_f: 10
  T_u: 5
  control_interval: 180
  random_seed: 42

mpc:
  horizon_steps: 5
  leader_candidate_count: 15
  max_nash_iter: 10
  nash_obj_tol: 1.0e-3
  nash_control_tol: 1.0e-3
  nash_relaxation_alpha: 0.8

leader:
  objective_mode: follower_ttt
  w_P: 1.0
  w_F: 1.0
  w_L: 0.05
  N_P_star_range: [0, 500]
  N_UF_star_range: [0, 6000]

freeway_follower:
  eps_F: 100
  vsl_set: [50, 60, 70, 80, 90, 100]
  max_vsl_step: 20
  ramp_queue_penalty: 10.0
  density_penalty: 10.0
  metering_smoothness_weight: 0.1
  vsl_smoothness_weight: 0.1

urban_follower:
  eps_U: 100
  eps_g: 5
  max_offset_step: 15
  boundary_balance_weight: 10.0
  offset_smoothness_weight: 0.1
  green_smoothness_weight: 0.1
  receiving_space_rule: proportional

evaluation:
  main_metric: total_ttt
  main_metric_direction: lower_is_better
  min_improvement_pct: 8.0
  eps: 1.0e-9

auto_tuning:
  enabled: true
  max_iterations: 5
  preserve_all_runs: true
```

Adjust units consistently. If `N_UF_star` and `N_P_star` are in vehicles per control interval rather than veh/h, make that explicit in the config and convert internally.

---

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

## 11. Reporting Requirements

Generate a final Markdown report at the end of every experiment.

The report must include:

1. Experiment metadata
   - scenario name
   - baseline mode
   - controller mode
   - seed
   - simulation horizon
2. Final pass/fail result
3. Main metric comparison
   - baseline total TTT
   - proposed total TTT
   - improvement rate
   - whether improvement >= 8%
4. Control validation summary
   - ramp metering
   - VSL
   - green time allocation
   - offset
   - inflow-outflow allocation and boundary queue balancing
5. Diagnostics
   - failure mode if any
   - parameter changes made by auto-tuner
   - rerun attempt history
6. Ablation results
7. Plots and exported CSV file paths
8. Explicit caveats
   - infeasible constraints
   - non-converged Nash iterations
   - scenario where controller failed

Example final result table:

```markdown
| Metric | Baseline | Proposed | Improvement | Pass |
|---|---:|---:|---:|---:|
| Total TTT | 123456 | 112000 | 9.28% | Yes |
| Freeway TTT | 60000 | 55200 | 8.00% | Yes |
| Urban TTT | 63456 | 56800 | 10.49% | Yes |
| Boundary CV | 0.42 | 0.31 | 26.19% | Yes |
```

---

## 12. Coding Style and Robustness

Follow these implementation rules:

- Use typed dataclasses or Pydantic models for states, controls, and config objects.
- Keep units explicit in variable names or config comments.
- Prevent negative density, speed, flow, and queue values by projection and logging.
- Avoid hidden global variables.
- Use deterministic random seeds.
- Save all raw time series.
- Never claim that the controller passed unless the metric calculation says so.
- If optimization is infeasible, return the nearest feasible control and log the infeasibility.
- If a dependency such as CasADi, scipy, or cvxpy is unavailable, implement a fallback grid search or heuristic solver.

---

## 13. Minimal Implementation Order

Implement in this order.

### Step 1. Core data structures

Create:

```text
TrafficState
ControlAction
NetworkConfig
ControllerConfig
EvaluationResult
DiagnosticResult
```

### Step 2. Baseline simulator

Run the network without proposed control and save TTT/TTS, queues, densities, speeds, and signal states.

### Step 3. Freeway model and freeway follower

Implement METANET update, ramp queue update, ramp metering, and VSL.

### Step 4. Urban queue model and urban follower

Implement horizontal queue dynamics, green time allocation, offset adjustment, and boundary queue balance metrics.

### Step 5. Stackelberg MPC loop

Connect leader, follower Nash solver, prediction, and first-step control application.

### Step 6. Evaluation and report generation

Implement metrics, diagnostics, and report export.

### Step 7. Auto-tuning and rerun logic

Implement the self-improvement loop with saved attempt histories.

### Step 8. Ablation experiments

Run component removal cases for diagnosis.

---

## 14. Definition of Done

The implementation is complete only when all of the following are true:

- The proposed controller can run closed-loop simulation end to end.
- Baseline and proposed simulations use the same scenario, seed, horizon, and demand.
- Ramp metering, VSL, green time, offset, and inflow-outflow allocation are all logged as time series.
- The evaluation computes total TTT/TTS and improvement rate.
- The 8% improvement criterion is checked automatically.
- Boundary queue balancing is evaluated separately from total TTT/TTS.
- If the first run fails, the diagnosis and auto-tuning loop reruns the simulation.
- Every attempt is saved and visible in the final report.
- Unit tests and the closed-loop smoke test pass.
- The final report clearly states `PASS` or `FAIL`.

---

## 15. Important Caveats

The current mathematical specification contains some parts that may require implementation choices, especially:

- exact units of `N_P_star` and `N_UF_star`
- whether the leader objective should use accumulation terms or follower TTT directly
- the exact network topology and demand input format
- whether the urban queue model should operate at 1 s, 5 s, or another short interval
- how to map VSL to desired speed in the METANET model
- whether boundary queue balancing should use only perimeter movements or all inflow/outflow movements

Implement these as explicit config options. Do not silently assume them without documenting the assumption in `report.md`.

