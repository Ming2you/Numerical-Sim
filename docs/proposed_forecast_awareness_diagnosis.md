# Proposed Controller Forecast-Awareness Diagnosis

Date: 2026-06-17

## Purpose

This note records a design/code diagnosis only. It intentionally does not
re-apply the previous five-item off-ramp/feed-forward patch, and it does not
push or modify controller code.

Question being checked:

Can `PROPOSED-STACKELBERG` choose poor `N_P_star` / `N_UF_star` values because
its follower response does not sufficiently account for forecasted arrivals?

Short answer:

Yes. The current Stackelberg outer loop evaluates candidate controls over the
forecast horizon, but the distributed follower response used by
`PROPOSED-STACKELBERG` is largely built from the first forecast demand step and
current queues. This can make the leader evaluate a myopic follower response as
if it were a forecast-aware response.

## Current Code Path

The six-controller runner maps `PROPOSED-STACKELBERG` to
`StackelbergMPCController` with distributed follower mode.

Relevant files:

- `src/experiments/six_controller_comparison.py`
- `src/controllers/stackelberg_mpc.py`
- `src/controllers/distributed_coordinator.py`
- `src/controllers/inflow_outflow_allocation.py`
- `src/controllers/urban_follower.py`
- `src/models/urban_queue_model.py`
- `src/controllers/freeway_follower.py`

## What Is Forecast-Aware

`StackelbergMPCController.decide_with_info` converts `demand_forecast` to
`forecast`, enumerates leader candidates, and then evaluates the selected
follower control over the MPC horizon:

```text
candidates = self.leader.candidates(state, previous, forecast[0])
nash = self.nash_solver.solve(state.copy(), action, forecast, previous)
predicted_states, follower_ttt = self._predict(state, nash.control, forecast)
```

`StackelbergMPCController._predict` then loops over:

```text
forecast[: self.cfg.mpc.horizon_steps]
```

So the outer candidate evaluation is forecast-aware.

## What Is Not Forecast-Aware Enough

### 1. Leader candidate generation uses only the first demand step

In `src/controllers/stackelberg_mpc.py`, leader candidates are generated with:

```text
self.leader.candidates(state, previous, forecast[0])
```

This means feasible/heuristic `N_UF_star` candidate placement uses only the
first interval demand. If later intervals have larger ramp arrivals, boundary
arrivals, off-ramp pressure, or incident recovery, the candidate set may not
cover the right region.

### 2. Distributed follower collapses the forecast to `first_demand`

In `src/controllers/distributed_coordinator.py`, `solve` accepts an iterable
forecast but immediately sets:

```text
first_demand = forecast[0]
```

Then the agent solves use that first demand:

```text
_solve_freeway_agent(..., first_demand, ...)
_solve_urban_agent(..., first_demand, ...)
_extract_coupling(..., first_demand)
```

Therefore the distributed follower response is not a horizon follower response.
It is a first-interval response that the leader later evaluates over multiple
future intervals.

This mismatch can select misleading `N_P_star` / `N_UF_star` values.

### 3. Urban allocation target is current-state feedback only

In `src/controllers/inflow_outflow_allocation.py`, the allocation module sets:

```text
target = urban_accumulation_feedback_flow(state, self.cfg, leader.N_P_star)
```

In `src/models/urban_queue_model.py`, this feedback is:

```text
error_veh = target_accumulation_veh - state.protected_accumulation_veh(cfg.network)
raw_flow = error_veh / N_P_feedback_horizon_h
```

This target does not include forecasted boundary arrivals, ramp arrivals,
off-ramp arrivals, or predicted uncontrolled internal transfer. As a result,
the controller can compute a net-flow target that is correct for current
accumulation error but wrong for the upcoming demand wave.

### 4. Proposed urban green uses current queues and allocation setpoints

`UrbanFollower._green_times` computes phase pressure from current
`urban_movement_queue` and optional allocation phase setpoints. It does not use
a phase-level arrival forecast in the same way as Wu's urban agent does.

The leaderless proposed green search has the same issue: `_search_green_times`
uses current phase queues and freeway pressure, while Wu's green logic uses a
pressure closer to:

```text
q0 + arrival * horizon
```

This means proposed urban control is more reactive: it tends to open green after
queues have accumulated, not before forecasted arrivals hit the intersection.

### 5. Two-block freeway follower is more forecast-aware than distributed follower

`src/controllers/freeway_follower.py` contains a horizon sequence search that
does use `forecast[:horizon_steps]` and includes future ramp arrivals in ramp
candidate weights.

However, in the current four/six-controller comparison, `PROPOSED-STACKELBERG`
uses distributed follower mode. The distributed freeway agents in
`DistributedCoordinator` are still first-demand/local-response based.

## Why This Matters For `N_P_star` And `N_UF_star`

The Stackelberg leader evaluates:

1. a candidate `N_P_star`, `N_UF_star`;
2. a follower response to that candidate;
3. predicted closed-loop states under that follower response.

If the follower response is myopic, the leader is not evaluating the response
that would actually be optimal under forecasted arrivals. It is evaluating a
first-interval follower decision rolled forward over the horizon.

That can cause:

- `N_P_star` to look too low or too high relative to the upcoming protected-area
  inflow;
- `N_UF_star` to over-meter ramps because later ramp/on-ramp demand is not
  priced correctly in the follower response;
- boundary queues and on-ramp queues to grow even when the leader objective
  appears to reduce predicted protected accumulation;
- Stackelberg to look worse than follower-only or Wu even when the high-level
  theory is not necessarily wrong.

## Relation To The Wu Comparison

The earlier Wu/proposed follower-only comparison showed a large performance gap.
The strongest immediate cause was proposed leaderless ramp metering:

- Wu-CD-F keeps ramp metering effectively at capacity.
- Proposed follower-only reduces metering strongly under local density pressure.
- A no-metering ablation reduced proposed follower-only TTT dramatically.

That ramp-metering issue is separate from, but compatible with, the forecast
issue here. Both point in the same direction: proposed followers are not yet
solving a faithful forecast-aware response problem.

## Recommended Fix Direction

Do not tune `N_P_crit`, off-ramp feed-forward, or leader penalties first. The
follower response should be made forecast-aware before interpreting
Stackelberg leader performance.

Recommended implementation order:

1. Make `DistributedCoordinator.solve` pass the full forecast into freeway and
   urban agent solves instead of collapsing to `first_demand`.
2. Add horizon-aware phase pressure to proposed urban green:

   ```text
   phase_pressure = current_phase_queue + predicted_phase_arrivals_over_horizon
   ```

   This should include boundary arrivals, upstream internal arrivals,
   on-ramp approach arrivals, and off-ramp arrivals where applicable.
3. Replace `urban_accumulation_feedback_flow` with a forecast-compatible target
   that accounts for predicted uncontrollable/disturbance inflow and required
   transfer demand, not only current `N_P_star - N_P`.
4. Generate leader candidates using forecast summaries, not only `forecast[0]`.
   Examples:
   - total predicted ramp/on-ramp demand over horizon;
   - predicted boundary inflow over horizon;
   - predicted off-ramp inflow/pressure over horizon;
   - current plus predicted queue pressure.
5. Fix proposed leaderless ramp metering so no-metering is a protected baseline
   candidate and ramp/on-ramp queue costs are fully priced.
6. After the follower response is forecast-aware, rerun:
   - `WU-CD-F`
   - `PROPOSED-FOLLOWERS-ONLY`
   - `PROPOSED-STACKELBERG`
   on the same peak and heavy-transfer scenarios.

## Minimal Validation Plan

Before long 7200 s runs:

1. Unit tests:
   - verify distributed follower receives and uses more than `forecast[0]`;
   - verify proposed green pressure changes when future arrivals change while
     current queues remain fixed;
   - verify allocation target changes when future off-ramp/boundary/ramp demand
     changes while current `N_P` is fixed.
2. 3600 s smoke:
   - peak demand;
   - heavy-transfer split scenario;
   - compare proposed follower-only with and without forecast-aware metering.
3. 7200 s validation:
   - only after 3600 s shows that proposed follower-only is no longer obviously
     worse than Wu due to ramp metering/green myopia.

## Current Conclusion

The proposed Stackelberg result should not be interpreted as a clean failure of
the Stackelberg game concept yet.

The current implementation likely evaluates leader candidates against a
partially myopic distributed follower response. Until that follower response is
forecast-aware, poor `N_P_star` / `N_UF_star` selection may be an implementation
artifact rather than a theoretical result.
