# Spec Implementation Audit

Created: 2026-06-09 15:39:39 +09:00

## Spec Files Used

- `docs/spec/03_traffic_models.md`
- `docs/spec/04_controller.md`
- `docs/spec/06_metrics.md`
- `docs/spec/12_coding_style.md`
- `docs/spec/15_caveats.md`

## Code Reviewed

- `src/models/state.py`
- `src/models/metanet.py`
- `src/models/urban_queue_model.py`
- `src/simulation/simulator.py`
- `src/simulation/closed_loop_runner.py`
- `src/simulation/baseline.py`
- `src/controllers/leader.py`
- `src/controllers/freeway_follower.py`
- `src/controllers/urban_follower.py`
- `src/controllers/stackelberg_mpc.py`
- `src/evaluation/metrics.py`

## Executive Summary

The current code can run an end-to-end closed-loop experiment, but it is not yet a faithful implementation of the split specification. The largest issue is not controller tuning. The largest issue is that the plant model used by the controller and simulator is still a simplified control-interval model, while the spec now requires explicit freeway, urban, and controller time scales, METANET speed dynamics, ramp receiving constraints, and urban-freeway coupling.

Until the P0 items below are fixed, Total TTT, VSL impact, and `N_UF_star` behavior should be treated as diagnostic only. They should not be used as evidence that the proposed controller works or fails under the intended mathematical model. The gap tables below record the initial audit; the progress updates record code changes made after that audit.

## Progress Updates

### 2026-06-09 16:41 +09:00

Completed in the movement-level urban/coupling pass:

- Added movement-level urban queues, directed urban link storage, movement arrival buffers, and storage release buffers to `TrafficState`.
- Added explicit default urban/freeway interface topology in config: on-ramp movement mappings, off-ramp storage links, off-ramp movement mappings, and off-ramp split ratios.
- Replaced the aggregate urban queue update with movement-level horizontal queue dynamics over `T_u` substeps.
- Urban movements now compute intended departures from movement queues, effective green fractions, movement capacities, and directed receiving storage.
- Directed link storage now blocks movement departures and uses delay/release buffers before vehicles leave a link or arrive at a downstream movement queue.
- Coupling now synchronizes one physical on-ramp queue between freeway `w[r]` and the urban on-ramp movement queue.
- Coupling now computes off-ramp receiving capacity from directed urban storage, applies it as a freeway downstream boundary cap, and schedules accepted freeway-to-off-ramp vehicles into the urban arrival buffer.
- Freeway last-segment outflow now supports off-ramp split ratios, storage binding diagnostics, and effective speed reduction when off-ramp storage binds.
- Urban follower allocation now includes movement-level allocation keys while retaining legacy boundary-link allocation outputs for compatibility.
- State/control timeseries now include movement queues, directed storage availability, and movement-level allocations.
- Added tests for on-ramp queue synchronization, off-ramp storage limiting freeway boundary flow, movement model diagnostics, and nonnegative movement/storage states.

Still remaining:

- Freeway node-to-node topology between freeway links is still simplified.
- The urban movement topology is explicit and configurable but still compact; it is not a calibrated full network geometry.
- Off-ramp coupling is implemented at the control-interval aggregate boundary, while the spec's most detailed order is written per `T_f` freeway step with nested `T_u` substeps.
- The urban follower is movement-level but still heuristic; it is not an exact optimization over all signal phases and offsets.

### 2026-06-09 16:26 +09:00

Completed after the held-control caveat review:

- Replaced held-control freeway follower scoring with a time-varying ramp/VSL sequence search.
- The follower now expands ramp-metering and VSL candidates at each forecast step from the predicted state at that step.
- The sequence search uses configurable beam search: `horizon_beam_width`, `horizon_ramp_candidate_limit`, and `horizon_vsl_candidate_limit_per_link`.
- The returned action is still the first control interval action of the best predicted sequence, as expected for receding-horizon MPC.
- Added diagnostics for sequence optimization, beam width, and expanded candidate nodes.
- Added tests that verify the follower evaluates later forecast steps and can expand a later-step VSL candidate that was infeasible in the first step.

Still remaining:

- This is a bounded beam-search heuristic, not an exact exhaustive mixed-integer/nonlinear optimizer over all ramp/VSL sequences.
- Superseded by the 16:41 update: the urban model now uses movement-level queues/storage and physical on-ramp/off-ramp coupling.
- The urban follower is movement-level but still heuristic and still uses the first demand step inside the Nash loop.

### 2026-06-09 16:16 +09:00

Completed in the freeway follower horizon pass:

- Added `TrafficState.freeway_flow` as a first-class freeway flow state.
- `TrafficState.initial()` and `freeway_step()` now maintain `q = rho * v * lanes` explicitly.
- Added state timeseries output for mean freeway flow by link.
- Changed Stackelberg/Nash wiring so the freeway follower receives the MPC demand forecast, not just the first demand step.
- Changed freeway follower scoring so ramp allocation candidates and VSL candidates are evaluated over `cfg.mpc.horizon_steps`.
- Ramp metering still returns a first-interval rate, but allocation candidates are generated from the feasible projected `N_UF_star` target and scored over the forecast.
- VSL still returns first-interval link-level VSL values, but those values are evaluated over the forecast instead of only one control interval.
- Added tests for first-class freeway flow and freeway follower forecast-horizon scoring.

Still remaining:

- Superseded by the 16:26 update: the freeway follower now performs bounded time-varying sequence search rather than held-control horizon scoring.
- Superseded by the 16:41 update: the urban model now uses movement-level queues/storage and physical on-ramp/off-ramp coupling.
- The urban follower is movement-level but still heuristic and still uses the first demand step inside the Nash loop.

### 2026-06-09 16:03 +09:00

Completed after the METANET rewrite:

- Reworked the freeway follower ramp-metering response around a feasible projection of `N_UF_star`.
- The projection now uses available ramp vehicles, ramp capacity, downstream freeway receiving factor, and the configured `N_UF_star_unit`.
- Added follower infeasibility diagnostics for target tracking residual, boolean target infeasibility, ramp queue overflow, and minimum receiving factor.
- Reworked VSL selection from a density-threshold heuristic into a discrete candidate evaluation using predicted `freeway_step` dynamics and smoothness cost.
- Added `src/simulation/coupling.py` as the single simulator entrypoint for a coupled control interval.
- Updated `MixedTrafficSimulator.step()` to call the coupling module rather than invoking freeway and urban steps directly.
- Updated Stackelberg horizon prediction to use the same coupling module as the simulator.
- Added tests for downstream receiving capacity in ramp metering, coupling-module diagnostics, and coupling-based Stackelberg prediction.

Still remaining:

- Superseded by the 16:41 update: coupling now synchronizes on-ramp queues, applies off-ramp storage blocking, and schedules freeway-to-urban off-ramp arrivals.
- Superseded by the 16:41 update: the urban model now uses movement queues, directed storage, and buffers.
- Freeway segment flow is still computed/logged by the plant but not stored as a first-class `TrafficState` field.
- Superseded by later updates: freeway flow is now first-class state and the freeway follower now uses bounded sequence search over the forecast.

### 2026-06-09 15:50 +09:00

Completed after the initial audit:

- Added explicit simulation time properties and validation for `T_f`, `T_u`, and `control_interval`.
- Added explicit `leader.N_UF_star_unit`, `network.v_min`, and `network.alpha_vsl` config fields.
- Added METANET helper functions for segment flow, desired speed with VSL, and speed update.
- Replaced the old control-interval freeway update with a `K_cf` substep METANET update inside `freeway_step`.
- Removed the hard-coded `0.65/0.35` speed relaxation from the applied freeway step.
- Replaced fractional ramp injection with full ramp inflow at the merge segment.
- Added downstream receiving-factor limits for ramp outflow.
- Added equation-level tests for METANET flow, density conservation, VSL desired speed, speed update, time ratios, and ramp merge injection.

Still remaining:

- Freeway segment flow is computed and logged as an average diagnostic, but it is not yet stored as a first-class `TrafficState` field.
- Ramp metering target projection still needs to move into the freeway follower using all constraints, including downstream receiving capacity.
- Superseded by later updates: the simulator now calls a coupling entrypoint with movement-level urban queues and physical on-ramp/off-ramp boundaries.
- The most detailed per-`T_f` nested coupling order is still approximated at the control-interval boundary.

Priority definitions:

- `P0`: Must fix before interpreting controller performance.
- `P1`: Required for spec completeness, but can follow after the model core is corrected.
- `P2`: Reporting, diagnostics, or design-choice cleanup after the main model is aligned.

## P0 Gaps

| Area | Spec Requirement | Current Implementation | Gap / Risk | Fix Target |
|---|---|---|---|---|
| Time scales | Use `T_f_sec`, `T_u_sec`, `T_c_sec`; validate divisibility; convert to `T_f_h`, `T_u_h`, `T_c_h`. | `freeway_step` and `urban_step` both use `cfg.simulation.control_interval_h`. `T_f` and `T_u` are configured but not used in the plant update. | The simulation skips the required freeway and urban substeps. Vehicle conservation and offset-sensitive behavior are distorted. | Add explicit properties for `T_f_h`, `T_u_h`, `T_c_h`; validate `T_c % T_f == 0` and `T_f % T_u == 0`; update simulator to step at the proper nested time scales. |
| Segment flow `q` | `q[m,i](k) = rho[m,i](k) * v[m,i](k) * lanes[m]`. | `flow` is computed locally with capacity and availability caps, and no `q` state or time series is stored. | The model does not expose the required flow state, making conservation and diagnostics hard to verify. | Add explicit per-segment flow computation and logging. If capacity clipping is retained, document it as a configured receiving/capacity constraint rather than silently replacing the core `q` equation. |
| Density update | `rho(k+1) = rho(k) + T_f_h/(L*lanes) * (q_in - q_out)`. | Density is updated over one control interval using a local `prev_out`, capacity caps, and a middle-segment ramp injection. | The update is not the required METANET conservation update over `T_f`. | Rebuild density update around explicit upstream boundary flow, segment outflow, ramp flow, and node/off-ramp boundary flow. |
| Ramp injection | Vehicles may only enter through explicit boundary, ramp, or node flows. | Ramp flow is added as `ramp_in / len(rhos)` only at the middle segment. | This injects only a fraction of the actual ramp flow when there are multiple segments, so ramp metering effects are understated and conservation is wrong. | Map each ramp to an explicit merge segment and add the full ramp flow to that segment's inflow term. |
| VSL effect | `V_eff = min(V_no_vsl, (1 + alpha_vsl) * vsl)` when VSL is active. | `v_des = min(desired_speed, vsl)` with no `alpha_vsl` and no active/inactive distinction beyond link-level VSL value. | VSL behavior is close to the strict-compliance special case, but the required parameter and reporting are missing. | Add `alpha_vsl` config and compute `V_no_vsl` and `V_eff` explicitly. Keep link-level VSL only as a documented simplification. |
| Speed update | METANET relaxation, convection, and anticipation terms. No unconfigured speed-drop terms. | `v_new = 0.65 * old_speed + 0.35 * desired_speed`, with a hard-coded floor. | This is an invented relaxation rule and not the specified METANET speed equation. It can make VSL look harmful or useful for the wrong reason. | Replace with the specified speed equation using configured `tau`, `nu`, `kappa`, `a`, and `v_min`. |
| Ramp receiving constraint | Ramp outflow must be limited by available vehicles, ramp capacity, and downstream receiving factor. | Plant ramp release checks available vehicles and ramp capacity, but not downstream freeway receiving capacity. | Ramp metering can release vehicles into a saturated freeway segment. | Compute `receiving_factor` from downstream density and apply it to no-metering ramp outflow. |
| `N_UF_star` units | Configure `N_UF_star_unit` as `veh_per_hour` or `veh_per_control_interval` and convert internally. | `N_UF_star` is treated implicitly as `veh/h`. No unit config exists. | Future changes can silently mix rates and counts. | Add `leader.N_UF_star_unit`, default to `veh_per_hour`, and centralize conversion. |
| `N_UF_star` projection | If target tracking is infeasible, project to nearest feasible ramp-flow vector and log `metering_target_infeasible` and residual. | Freeway follower projects by queue weights and capacity, but ignores downstream receiving capacity and does not log the required boolean flag. | Target tracking diagnostics are incomplete and can appear feasible under missing constraints. | Create a ramp projection helper using all ramp constraints and explicit residual/infeasibility logging. |
| Coupled simulation order | Required order synchronizes on-ramp queues, computes ramp outflows, runs urban substeps, computes off-ramp boundary, updates freeway, then distributes off-ramp flow. | `MixedTrafficSimulator.step()` calls `freeway_step()` once and then `urban_step()` once per control interval. | On-ramp queues, off-ramp blocking, and urban-freeway storage interaction are not represented. | Implement nested `T_c -> T_f -> T_u` stepping and the mandatory coupling order. |

## P1 Gaps

| Area | Spec Requirement | Current Implementation | Gap / Risk | Fix Target |
|---|---|---|---|---|
| Traffic state | State includes freeway density/speed/flow, ramp queue, movement queues, storage, and arrival buffers. | `TrafficState` has density, speed, ramp queue, aggregate urban queue, and boundary queue only. | Missing `q`, movement-level `x[o,s,d]`, storage `S[u,v]`, turning ratios, and arrival buffers. | Extend state in phases: first add freeway `q`; later add movement queues and storage. |
| Node coupling | Explicit upstream boundary, virtual downstream density, and virtual entering speed. | Links are independent except demand and ramps. | Cannot represent freeway link-to-link propagation or off-ramp boundary effects. | Add a minimal node topology or explicitly document the current two-link independent simplification until topology is available. |
| Urban queue model | Movement-level queues, intended departures, receiving-space allocation by directed receiving links, storage update, delay buffer. | Aggregate boundary and urban queues with hard-coded `0.35` arrival split and `0.65` departure split. | Urban TTT is weakly coupled to green/allocation decisions and can remain unchanged across controls. | Replace aggregate model with movement-level queues and storage; remove hard-coded split coefficients unless configured and documented. |
| On-ramp double-counting | If on-ramp exists in urban model, use one physical queue and synchronize with freeway queue. | Ramp queue and urban queues are independent. | On-ramp spillback into urban network is not captured. | Introduce explicit on-ramp movement queues or document that ramps are freeway-only until urban coupling is implemented. |
| Off-ramp interaction | Off-ramp storage limits freeway outflow and feeds urban arrival buffers. | No off-ramp storage or freeway-to-urban boundary condition exists. | Freeway congestion from urban spillback cannot be represented. | Add off-ramp topology and storage before claiming integrated urban-freeway coupling. |
| Freeway follower objective | Horizon TTT-like objective with ramp queues, VSL smoothness, and metering smoothness. | Single-step heuristic projection and density/queue penalties. | Follower response is feasible-looking but not the specified horizon optimization. | After plant correction, implement a grid/heuristic horizon evaluation over ramp metering and VSL candidates. |
| VSL decision | Follower chooses VSL from feasible set with smoothness constraints. | VSL is density-threshold heuristic, usually link-level. | It can activate, but it is not selected by objective minimization. | Evaluate VSL candidates using predicted METANET dynamics and smoothness penalty. |
| Urban follower stage 1 | Green/capacity allocation must satisfy net inflow target and queue balance constraints. | Allocation tracks `N_P_star` with a simple aggregate in/out split. | Does not use movement-level saturation and phase-specific constraints. | Rebuild stage 1 after movement-level urban model exists. |
| Urban follower stage 2 | Offset and green fine-tuning objective over `T_u` queue accumulation. | Offset uses freeway average speed proxy; green fine-tuning is not separate from stage 1. | Offset effect is weak and not tied to corridor travel delay. | Add actual link travel delay estimates from urban buffers/storage. |
| Nash solver | Iterative freeway/urban best responses until objective/control convergence. | Solver iterates deterministic responses on the same state and first demand step. | It has convergence logs, but the response coupling is shallow. | Revisit after follower objectives and coupled prediction are corrected. |

## P2 Gaps

| Area | Spec Requirement | Current Implementation | Gap / Risk | Fix Target |
|---|---|---|---|---|
| Leader objective | Default objective is accumulation plus target/density/smoothness penalties; `follower_ttt` mode is allowed. | `follower_ttt` mode includes extra congestion-aware `N_UF_star` heuristic penalties. | Useful diagnostic, but not part of the default mathematical form. | Keep behind explicit config or move to auto-diagnosis after the model is corrected. |
| Config caveats | Implementation choices must be explicit config options and documented in reports. | Some choices are configured, but `alpha_vsl`, `v_min`, `N_UF_star_unit`, link-level VSL simplification, and independent freeway links are not fully documented. | Future agents can repeat hidden assumptions. | Add config fields and report caveats once the model rewrite begins. |
| Metrics | Report `speed_drop_reduction`, movement capacity violations, number-of-stops proxy, and infeasible target logs. | Activation metrics were added, but several spec metrics are missing. | Control validation is useful but incomplete. | Add metrics after the plant exposes the needed flows, speeds, queues, and infeasibility flags. |
| Tests | Test equations and constraints before relying on experiments. | Existing tests cover smoke, bounds, and simple metrics. | They do not protect METANET equations, ramp receiving, VSL `V_eff`, or unit conversion. | Add equation-level tests before major model replacement. |
| Run reports | Reports must include caveats, infeasible constraints, non-converged Nash iterations, and failed scenarios. | Reports include pass/fail and diagnostics, but not all new spec caveats. | Users may over-trust early results. | Report explicitly when the current model is simplified or not spec-complete. |

## Recommended Repair Sequence

Do not tune the controller further before the P0 model gaps are addressed.

1. Config and state scaffold
   - Add explicit `T_f_h`, `T_u_h`, `T_c_h` properties and divisibility validation.
   - Add `leader.N_UF_star_unit`, `network.v_min`, `network.alpha_vsl`, and any missing METANET parameters.
   - Add freeway flow storage/logging support.

2. METANET helper functions
   - Implement `segment_flow(rho, v, lanes)`.
   - Implement `v_no_vsl`.
   - Implement `v_eff` with `alpha_vsl`.
   - Implement the METANET speed update exactly as specified.
   - Add unit tests for each helper.

3. Freeway density and ramp update
   - Rebuild density update around explicit `q_in`, `q_out`, and full ramp merge flow.
   - Add downstream receiving factor to ramp outflow.
   - Add `N_UF_star` unit conversion and target projection with infeasibility logs.

4. Simulator time stepping
   - Replace one control-interval plant step with nested control/freeway/urban stepping.
   - Preserve first-step MPC control over all substeps in that control interval.

5. Urban model expansion
   - Replace aggregate queues with movement-level queues and directed-link storage.
   - Add receiving-space allocation and delay buffers.
   - Then synchronize on-ramp queues with freeway queues.

6. Off-ramp and full urban-freeway coupling
   - Add off-ramp storage and freeway outflow boundary limitation.
   - Feed effective off-ramp flow into urban arrival buffers.

7. Controller alignment
   - Revisit freeway follower and VSL selection after the corrected plant exists.
   - Move heuristic `N_UF_star` penalties behind explicit config if still needed.
   - Re-evaluate leader objective only after plant tests pass.

8. Metrics, reports, and acceptance rerun
   - Add missing validation metrics.
   - Regenerate the 2x-demand report only after the model is spec-aligned.

## Immediate Next Commit Suggestion

The next code commit should be small and mechanical:

```text
Add explicit time/unit config validation and METANET helper tests
```

It should not yet change controller objective behavior. The purpose is to make the model rewrite testable before replacing `freeway_step`.
