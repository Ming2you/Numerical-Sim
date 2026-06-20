# Follower TTS Objective Alignment Plan

## 18.1 Purpose

This document records the diagnosis from the 2026-06-18 controller comparison
discussion and defines the next implementation direction.

The short conclusion is:

```text
Heuristics should be proposal generators only.
Final follower decisions must be selected by TTT/TTS-compatible argmin.
```

The current controller architecture is still useful, but several follower
decision paths mix TTT/TTS objectives with pressure rules, density penalties,
balance residuals, and hand-written offset rules. This can make WU-CD-F,
PROPOSED-FOLLOWERS-ONLY, and PROPOSED-STACKELBERG choose active controls even
when the default/no-control action would have lower closed-loop Total TTT.

## 18.2 Reference Documents

Use this document together with:

- `04_controller.md`
- `16_six_controller_comparison.md`
- `17_relaxed_quantized_fast_mode.md`
- `../experiment_acceptance_criteria.md`
- `../agent_debate_protocol.md`

This document is a repair plan for follower objective consistency. It does not
change the physical plant, topology, demand, metric accounting, or controller
authority definitions.

## 18.3 Current Findings

### Relaxed Quantized Is Not Fast Mode

`relaxed_quantized_controls = true` should mean:

```text
continuous or low-dimensional local proposal/search
then feasible green/VSL quantization and repair
```

Solver-budget changes should be explicit ordinary config overrides rather than
a separate fast-mode flag.

The observed performance issue is not simply caused by quantization. The larger
issue is that some relaxed-quantized paths replace local TTS minimization with a
single pressure-based control rule.

### P-Stack Difference Under Fast Allocation

For `peak_demand`, 7200 s:

| Run mode | P-FO Total TTT | P-Stack Total TTT | Interpretation |
|---|---:|---:|---|
| vectorized full allocation | 7411.565 | 7207.966 | P-Stack improves over P-FO |
| former fast-allocation shortcut | 7411.565 | 8608.054 | P-Stack worsens due to the allocation/follower-response approximation |

Therefore the statement "P-Stack has a problem" is mode-specific. The full or
vectorized allocation path can still make P-Stack better than P-FO, while a
shortcut allocation path can distort the follower response.

### No-Control Degradation Pattern

In the 7200 s all-scenario shortcut-allocation run, WU-CD-F and
PROPOSED-FOLLOWERS-ONLY are not uniformly better than no-control:

- WU-CD-F is close to no-control and can be slightly worse in light or capacity
  drop cases.
- PROPOSED-FOLLOWERS-ONLY improves in peak, incident, and oversaturated
  scenarios, but worsens in low and medium demand and in capacity drop.

The likely cause is not lack of forecast data. The likely cause is that the
forecast is evaluated through local proxy objectives that are not sufficiently
compatible with closed-loop Total TTT.

## 18.4 Freeway Follower Problems

### Ramp Metering Objective Mismatch

Spec `04_controller.md` defines the freeway follower objective as:

```text
J_F = sum_over_horizon[
        T_f * (sum_m sum_i rho[m,i](t) * L[m] * lanes[m]
               + sum_r ramp_queue[r](t))
        + vsl_smoothness_penalty
        + metering_smoothness_penalty
      ]
```

The intended local decision should price:

- freeway vehicle TTS
- ramp queue TTS
- predicted upstream/on-ramp urban queue TTS where the ramp queue is fed by
  urban green release
- VSL and metering smoothness
- queue overflow penalties

The current distributed leaderless ramp metering path instead uses a density
threshold proxy plus a short-term held-vehicle cost. This can make metering look
beneficial because it lowers local density even when it increases ramp and
urban waiting enough to worsen Total TTT.

### Ramp Metering And VSL Are Not Jointly Optimized

The current distributed freeway path effectively does:

```text
choose/project ramp metering first
then search VSL conditional on that metering vector
```

This is not a joint ramp-metering/VSL local TTS argmin. The standalone
`FreewayFollower` beam search is closer to the desired structure because it
evaluates ramp candidates crossed with VSL candidates, but the distributed
coordinator path does not consistently follow that pattern.

## 18.5 Urban Follower Problems

### Stage 1 Allocation Is Not The Main Problem

The Stackelberg urban allocation module is allowed to be a balance and
net-inflow target module. Its objective is not pure Total TTT:

```text
B_in^2 + B_out^2 + net_inflow_residual_penalty
```

That is consistent with the stage-1 allocation role.

### Stage 2 Green Fine-Tuning And Offset Are Not TTS Argmin

Spec `04_controller.md` defines urban stage 2 as:

```text
J_S = sum_over_horizon[
        T_u * sum_i sum_m queue_or_accumulation[i,m](t)
        + offset_smoothness_penalty
        + green_smoothness_penalty
      ]
```

Stage 2 should receive stage-1 green setpoints and then choose:

```text
R_S = [g_i_m_star, phi_i_star]
```

where `g_i_m_star` is a fine-tuned green plan near the stage-1 setpoint and
`phi_i_star` is the offset.

The current implementation is closer to:

```text
allocation setpoint
-> pressure/arrival/freeway-pressure green split
-> clamp to allocation band
-> corridor offset heuristic
```

The offset rule estimates a plausible green wave from queue/storage direction
and link travel time, but it does not evaluate offset candidates by the stage-2
TTS objective.

### Relaxed Quantized Urban Green Is Too Heuristic

With `relaxed_quantized_controls = true`, some green paths use one pressure
split and then quantize/repair it. The code may compute a cost after the split,
but that cost is not used to compare multiple candidates. This should be
changed so the pressure split becomes a candidate center, not the final
decision rule.

## 18.6 Required Repair Principle

For each local follower decision, use this pattern:

```text
1. Build heuristic proposals.
2. Build default/previous/no-control proposals.
3. Build a small feasible neighborhood around the heuristic proposals.
4. Quantize/repair candidates when required.
5. Evaluate candidates with a TTT/TTS-compatible objective.
6. Choose argmin.
```

The default/no-control candidate must be present. If active control does not
improve the local TTS objective beyond tolerance, the follower should preserve
the default or previous neutral action.

## 18.7 Freeway Repair Plan

### Candidate Generation

For each freeway agent, generate:

- no-metering/default ramp release
- previous ramp release
- leader or leaderless target projection
- small metering neighborhood around the projected target
- max/default VSL
- previous VSL
- pressure-based VSL proposal
- VSL neighborhood around the proposal, respecting `vsl_set` and
  `max_vsl_step`

### Joint Evaluation

Evaluate ramp-metering candidates crossed with VSL candidates:

```text
J_freeway_local =
    freeway_vehicle_TTS
  + ramp_queue_TTS
  + predicted_upstream_onramp_urban_queue_TTS
  + vsl_smoothness_penalty
  + metering_smoothness_penalty
  + queue_overflow_penalty
  + soft_density_excess_penalty
```

Density excess should be a soft penalty or diagnostic, not the dominant
substitute for TTS.

### Expected Result

In low or medium demand, if no-control already clears the ramp and freeway
without creating congestion, the no-metering/default candidate should win.

In peak, incident, or downstream spillback cases, metering and/or VSL should win
only when the TTS reduction exceeds the added holding cost.

## 18.8 Urban Repair Plan

### Stackelberg Urban Stage 2

After stage-1 allocation:

1. Convert movement allocation to phase green setpoints.
2. Generate green candidates within `eps_g` or the configured allocation band.
3. Generate offset candidates around:
   - previous offset
   - zero/default offset
   - current corridor heuristic offset
   - small step variations within `max_offset_step`
4. Evaluate green x offset candidates with a local urban TTS objective.

Suggested objective:

```text
J_urban_stage2 =
    urban_movement_queue_TTS
  + boundary_in_queue_TTS
  + x_on_or_onramp_approach_queue_TTS
  + off_ramp_storage_or_receiving_queue_TTS
  + green_smoothness_penalty
  + offset_smoothness_penalty
```

Boundary-in queues are part of closed-loop Total TTT accounting. They must not
be treated as hidden storage or diagnostic-only queues when a controller
candidate can increase them.

### Proposed Followers Only

Without allocation, use the same stage-2 search but build green anchors from:

- fixed 50:50/default green
- previous green
- pressure-based green proposal
- forecast-arrival pressure proposal

Again, the final selected green/offset must be the TTS argmin, not the pressure
rule itself.

## 18.9 Relaxed Quantized Repair Plan

`relaxed_quantized_controls = true` must not mean "use a heuristic instead of
optimization." It should mean:

```text
small proposal-centered candidate search
continuous center values allowed
final action quantized/repaired to feasible actuator values
```

For green:

- candidate centers: default, previous, allocation setpoint, pressure proposal
- neighborhood: +/- 1 s, +/- 2 s, +/- 5 s, clipped to bounds and repaired

For VSL:

- candidate centers: max/default, previous, pressure proposal
- neighborhood: +/- 10 km/h, respecting `vsl_set` and `max_vsl_step`

For ramp metering:

- candidate centers: no-metering, previous, target projection, pressure proposal
- neighborhood: small fractions around the target projection

## 18.10 Validation Plan

After implementation, run at least:

1. Unit tests for candidate feasibility:
   - green cycle equality and min/max bounds
   - offset range and max step
   - VSL set and max step
   - ramp metering capacity and nonnegativity
2. Local objective tests:
   - no-control/default candidate is included
   - if all active candidates have worse TTS, default is selected
   - relaxed-quantized mode still evaluates multiple candidates
3. Closed-loop smoke test for:
   - WU-CD-F
   - PROPOSED-FOLLOWERS-ONLY
   - PROPOSED-STACKELBERG
   - PROPOSED-CENTRALIZED
4. 7200 s scenario comparison with:
   - Total TTT
   - Total Delay
   - Throughput
   - terminal vehicles
   - computation time
   - control activation logs

The key diagnostic question is not whether every controller always beats
no-control. The key question is whether local followers avoid unnecessary active
control when the TTS objective says default is better, and whether active
control appears only when it has a measurable TTS benefit.

## 18.11 Implementation Order

Recommended order:

1. Add shared local TTS evaluation helpers for freeway and urban candidate
   screening.
2. Refactor distributed freeway follower to jointly evaluate ramp metering and
   VSL candidates.
3. Refactor urban stage-2 green and offset to use proposal-centered TTS search.
4. Change relaxed-quantized mode from pressure-rule selection to
   proposal-centered candidate search.
5. Add default/no-control guards for WU-CD-F and PROPOSED-FOLLOWERS-ONLY.
6. Re-run 7200 s all-scenario comparison with `relaxed_quantized_controls=true`
   and the full allocation module before testing any shortcut.

Do not introduce a new shortcut allocation path until the full relaxed-quantized
path passes the acceptance checks.
