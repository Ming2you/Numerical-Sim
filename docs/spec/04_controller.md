# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

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
        + w_P * positive_part(n_P(t) - n_P_crit)
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

The follower layer can be selected by configuration:

```yaml
mpc:
  follower_solver_mode: two_block      # legacy FreewayFollower + UrbanFollower Nash loop
  # or
  follower_solver_mode: distributed    # urban/freeway agent coordinator
```

In `distributed` mode, partition the current topology into urban signal agents and freeway link agents, exchange coupling variables between neighboring agents, and terminate iterations by coupling residual rather than raw mixed-unit control-vector difference. The first implementation may reuse deterministic local follower heuristics, but it must expose per-agent diagnostics so later MILP/SQP local optimizers can replace the heuristic pieces without changing the outer Stackelberg interface.

---
