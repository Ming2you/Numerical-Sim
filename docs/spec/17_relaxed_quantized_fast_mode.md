# Relaxed-Quantized Controller Mode

## 17.1 Purpose

This document defines a computationally practical relaxed-quantized controller
variant for the primary four-controller comparison in
`16_six_controller_comparison.md`.

The current 4-controller, 6-scenario 3600 sec experiment can become a
computation-cost failure because several controllers repeatedly evaluate
candidate controls through coupled urban-freeway rollouts. The expensive part is
not a formal MILP/MINLP integer solver. It is mainly:

- segment-level VSL candidate combinations in `WU-CD-F`
- green-time grid search in distributed urban agents
- nested leader-candidate and follower-response loops in `PROPOSED-STACKELBERG`
- centralized random-search rollout budget in `PROPOSED-CENTRALIZED`

The relaxed-quantized mode may reduce candidate enumeration, but it must still
select final local actions by a TTT/TTS-compatible objective. Heuristic pressure
rules may generate proposal centers only; they must not replace objective-based
selection.

## 17.2 Non-Goals

Do not change the coupled plant equations.

Specifically, this mode must not modify:

- METANET density/speed conservation
- off-ramp storage blocking and capacity-drop coupling
- on-ramp queue synchronization
- urban receiving-space allocation
- free-flow delay reference and metric accounting
- four-controller authority definitions

This is a controller-side solver approximation, not a new traffic model.

## 17.3 Configuration

Add explicit configuration keys rather than silently replacing the existing
controller behavior.

Recommended keys:

```yaml
mpc:
  relaxed_quantized_controls: false
  relaxed_green_quantum_sec: 1.0
  relaxed_vsl_quantum_km_h: 10.0
  relaxed_rounding_mode: floor      # floor, nearest
  relaxed_wu_vsl_include_neutral: true
```

When `relaxed_quantized_controls = false`, existing behavior must be preserved.
Solver budgets such as `leader_candidate_count`, `max_nash_iter`,
`optimizer_maxiter`, and `freeway_prediction_horizon_steps` remain explicit
ordinary configuration values. They are not controlled by a separate fast-mode
flag.

## 17.4 Quantization and Feasibility Repair

The relaxed solver may compute continuous intermediate values, but every action
applied to the plant must be feasible under the existing control constraints.

### VSL

The continuous VSL target is projected in this order:

1. clip to `[min(vsl_set), max(vsl_set)]`
2. enforce `max_vsl_step` relative to previous segment VSL
3. quantize to `relaxed_vsl_quantum_km_h`
4. project to the configured discrete `vsl_set`
5. re-check `max_vsl_step`

`floor` is the default requested experiment mode. It is conservative and may
reduce throughput, so `nearest` should remain available for sensitivity checks.

### Green time

The continuous phase split is projected in this order:

1. compute continuous `p1` and `p2 = effective_green_total - p1`
2. clip both phases to `[green_min, green_max]`
3. quantize with `relaxed_green_quantum_sec`
4. repair the pair so that `p1 + p2 + lost_time = cycle_length`
5. re-check phase min/max constraints

If exact repair is impossible, return the nearest feasible cycle split and log
the residual. Do not silently violate the cycle constraint.

## 17.5 Controller-Specific Changes

### WU-CD-F

The WU controller remains a green/VSL-only distributed controller. The relaxed
mode changes only the local optimizer.

For urban agents:

- use queue/arrival-pressure rules as proposal centers
- include the default/previous green split as a candidate
- evaluate a small feasible neighborhood with the local TTS objective
- quantize and repair the selected result before returning the control

For freeway agents:

- avoid Cartesian enumeration of all segment-level VSL vectors
- compute one continuous target vector per freeway link from current density,
  downstream/off-ramp pressure, lane-loss pressure, and previous VSL
- keep bottleneck/off-ramp segments at or near free-flow VSL unless lowering
  them is explicitly beneficial in the local probe
- lower upstream plain segments first when downstream pressure is active
- if `relaxed_wu_vsl_include_neutral = true`, evaluate both the relaxed target
  vector and the neutral max-VSL vector, then choose the better local objective

This preserves the intended Wu mechanism: VSL should meter upstream approach
flow rather than artificially reducing bottleneck discharge.

### PROPOSED-FOLLOWERS-ONLY

The proposed follower-only controller keeps the same authority:

- green
- offset
- ramp metering
- VSL

Relaxed mode should:

- use continuous proposal centers plus local TTS candidate search
- keep offset and metering logic unchanged unless a feasibility bug is found
- quantize any continuous or heuristic VSL output through the common VSL repair

### PROPOSED-STACKELBERG

The Stackelberg structure remains unchanged:

- leader candidates are still evaluated
- followers still respond through the distributed/two-block loop
- only follower local solves become relaxed/quantized

Do not swap the allocation module based on relaxed quantization. The
Stackelberg path should continue to use `InflowOutflowAllocationModule` unless a
future spec introduces and validates a replacement against the full objective.

### PROPOSED-CENTRALIZED

The centralized controller already uses continuous decision vectors internally.
Relaxed mode should focus on:

- using the common green and VSL repair functions
- reporting `solver_evaluations`, convergence rate, and computation time

Do not describe the centralized result as a global optimum.

## 17.6 Required Diagnostics

Every relaxed run must log enough information to separate performance from
computational shortcut effects.

Required diagnostics:

```text
relaxed_quantized_controls
relaxed_rounding_mode
green_quantization_residual_sec
vsl_quantization_residual_km_h
green_repair_count
vsl_repair_count
solver_evaluations
computation_time_sec
solver_converged
allocation_pso_objective_evaluations
```

The 4-controller Stage 1 table must continue to include:

- TTT/TTS
- total, urban, and freeway delay
- throughput and completed vehicles
- terminal vehicles and subsystem queues
- computation time
- convergence rate

## 17.7 Tests

Add or update tests to verify:

- relaxed mode is off by default
- existing full mode still returns controls in the same feasible sets
- relaxed VSL values belong to `vsl_set`
- relaxed VSL changes respect `max_vsl_step`
- relaxed green times satisfy min/max and cycle-sum constraints
- WU relaxed freeway solve evaluates bounded VSL candidates
- primary four controllers can run a short smoke test with relaxed mode enabled

## 17.8 Experiment Procedure

Use a two-step validation.

Step 1: smoke and runtime check

```text
scenario = peak_demand
T_total = 3600 sec
controllers = WU-CD-F, PROPOSED-FOLLOWERS-ONLY,
              PROPOSED-STACKELBERG, PROPOSED-CENTRALIZED
```

Step 2: full Stage 1 screening run

```text
T_total = 3600 sec
controllers = primary four
scenarios = all configured six scenarios
```

The run is acceptable only if:

- unit tests pass
- smoke test completes
- all controls pass feasibility checks
- computation time is reported
- failed or non-converged cases are preserved under `outputs/`

Do not claim final controller acceptance solely from faster computation. The
performance criteria in `experiment_acceptance_criteria.md` still apply.
