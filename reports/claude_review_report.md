# Claude Review Report

_Reviewed commit: `c4e68b3` "Implement metanet coupling and movement urban model"._
_Scope: validate `docs/spec_implementation_audit.md` against the split spec and the
actual code. Three review axes requested: (1) was Codex's repair direction correct,
(2) were the claimed fixes actually implemented, (3) what is still missing._

## Verdict

**FAIL** — review stopped at the implementation-validation stage, as instructed by
`CLAUDE.md`.

This is *not* a judgment that the work is poor. The plant-model rewrite is real,
spec-directed progress and is backed by passing equation-level tests. The verdict is
FAIL because (a) blocking implementation gaps remain (the mandatory coupled
simulation order of spec 3.4.3, a genuine Nash response, functional on-ramp
coupling), and (b) there is **no simulation evidence corresponding to the current
code**: the only committed run report predates the rewrite, and `outputs/` is
git-ignored. Per `CLAUDE.md`, simulation improvements must not be interpreted until
implementation validity is established, so the integrated result cannot be certified
yet.

Test evidence: full suite runs green — **33/33 tests pass** with numpy 2.3.5 /
Python 3.12 (`python -m unittest discover -s src/tests`). The equation-level METANET
tests (`src/tests/test_metanet_equations.py`, 12 tests) pass even on the bare stdlib
interpreter; the 3 modules that failed on the system Python do so only because numpy
is not installed there (environment, not a code defect).

## Answers to the three review questions

1. **Was the repair direction correct? Yes.** The audit correctly diagnosed that the
   bottleneck was the *plant model*, not controller tuning, and prioritized the P0
   METANET/coupling rebuild before any further tuning. The staged repair sequence
   (config/state scaffold → METANET helpers → density/ramp → time stepping → urban
   expansion → coupling → controller alignment) is sound. I endorse it.
2. **Were the claimed fixes actually implemented?** Freeway/METANET P0: **Yes**,
   verified at code + test level. Coupling: **Partial** — the off-ramp direction is
   functional, but the nested time-step order and on-ramp coupling are approximated
   or effectively inert. Controller: the freeway follower was genuinely upgraded to a
   beam-search sequence optimizer, but the Nash loop and follower/plant model
   consistency remain weak. The audit's own "Still remaining" notes are honest about
   these.
3. **What is still missing?** See *Recommended Fixes* below.

## Critical Issues

1. **No current-model simulation evidence.**
   - `reports/codex_run_report.md` describes a run from *before* the METANET rewrite:
     it cites the old "VSL 90 km/h density heuristic", Urban TTT unchanged at
     `14473.005` (0.00%), and makes no mention of METANET equations, coupling, or the
     movement urban model. It does not reflect commit `c4e68b3`.
   - `.gitignore:8` excludes `outputs/`; the repository contains zero output
     artifacts. The `control_timeseries.csv` fields required by `CLAUDE.md` §5
     (`metering_active_steps`, `vsl_active_steps`, `N_UF_star` values) cannot be
     inspected. Simulation-result review is therefore not possible from evidence.
2. **Mandatory coupled simulation order (spec 3.4.3) is not implemented as specified.**
   - `src/simulation/coupling.py:32-43` runs one full `urban_step` (all `K_cu=36`
     urban substeps for the whole 180 s interval) and then one full `freeway_step`
     (all `K_cf=18` substeps), at the control-interval level. The spec requires the
     coupling to be executed *per freeway step* with nested `T_u` substeps. Within an
     interval, on-ramp/off-ramp interactions are decoupled. The audit acknowledges
     this ("control-interval aggregate boundary").
3. **On-ramp urban–freeway coupling is structurally present but functionally inert.**
   - Urban demand (`src/models/demand.py`) only feeds `in_A/in_C/out_D/out_F`; the
     `on_ramp` movements (origins A/C/D/F) receive no arrivals, and
     `src/models/urban_queue_model.py:263` skips `on_ramp` movements in the departure
     loop. `sync_onramp_queues_from/to_freeway` (`:56-69`) only mirror
     `ramp_queue ↔ movement_queue`.
   - Consequently the very motivation of spec 3.4.1 (one physical queue so urban
     spillback can reach the on-ramp) never takes effect. The claim of "physical
     on-ramp queue synchronization" is formally true but its physical effect is zero.

## Methodological Issues

1. **The Nash solver is not a true best-response equilibrium.**
   `src/controllers/nash_solver.py:62-97`: the freeway follower never sees the urban
   control, and `UrbanFollower.solve(...)` accepts `freeway_response` but does not use
   it (`src/controllers/urban_follower.py:126-158`). The iteration only
   relaxation-smooths toward state-derived targets, so "convergence" is trivial rather
   than strategic. This is the concrete location of the audit's "shallow coupling".
2. **The follower optimizes against a different plant than the simulator.**
   `src/controllers/freeway_follower.py:214` (`_transition_node`) calls
   `freeway_step(probe, control, demand, cfg)` **without** `offramp_capacity_veh_h`
   and **without** the coupling module, whereas the actual plant and the leader's
   horizon prediction use `run_coupled_interval`
   (`src/controllers/stackelberg_mpc.py:97-107`). The optimizer chooses VSL/metering
   while ignoring off-ramp blocking and urban interaction that the plant applies.
3. **Leader objective adds non-spec heuristic penalties.** In `follower_ttt` mode the
   leader adds congestion/queue-aware `N_UF_star` penalties not present in the spec's
   default form (`src/controllers/leader.py:96-101`). Acceptable only if kept behind
   explicit config and documented (audit P2 agrees).

## Code-Level Issues

Mostly positive — these confirm the audit's P0 claims against the actual code:

- Segment flow `q = rho * v * lanes` (`src/models/metanet.py:10`).
- `V_eff = min(V_no_vsl, (1+alpha_vsl)*vsl)` with `alpha_vsl` and an active/inactive
  flag (`src/models/metanet.py:20-33`).
- METANET speed update as relaxation + convection + anticipation, with the old
  hard-coded `0.65/0.35` relaxation removed (`src/models/metanet.py:36-59`).
- Conservation density update with the full ramp flow injected at the merge segment
  (`src/models/metanet.py:169-189`).
- Downstream receiving-factor limit on ramp outflow (`src/models/metanet.py:126-138`).
- First-class `freeway_flow` state; explicit `T_f_h/T_u_h/T_c_h` and `K_cf/K_cu/K_fu`
  with divisibility `validate()` actually invoked (`src/models/state.py:125-175`,
  `:398-402`); `N_UF_star_unit` conversion (`src/models/metanet.py:66-69`).
- Equation-level tests assert all of the above and pass
  (`src/tests/test_metanet_equations.py`).

Minor:
- Baselines `no_control` and `fixed_signal_fixed_speed` are identical (both return
  `ControlAction.fixed`, `src/simulation/baseline.py:18-21`). Acceptable in this
  simplified plant, but they are not distinct baselines; differentiate or document.

## Simulation Validity Issues

1. Baseline and proposed use identical, deterministic demand (`DemandProfile`,
   `src/simulation/closed_loop_runner.py:49,58`) — `CLAUDE.md` §4 "same demand" is
   structurally satisfied.
2. With no current-model results (see Critical 1), improvement rate, control
   activation, and boundary-queue balancing cannot be evaluated from evidence. The
   only committed result (old plant) was FAIL (-0.33% TTT, urban 0.00%) and is
   unrelated to the current code.
3. `improvement_rate` / boundary metrics in `src/evaluation/metrics.py` are exercised
   by passing tests (`test_metrics`), but a full result comparison still requires a
   fresh current-model run.

## Recommended Fixes for Codex

Priority order:

- **P0** — Implement the nested `T_c → T_f → T_u` coupled order of spec 3.4.3: perform
  on-ramp synchronization and off-ramp boundary computation *inside* the freeway
  substep loop, not once per control interval.
- **P0** — Either give on-ramp movements a real urban inflow path, or explicitly
  document that on-ramps are freeway-only for now. The current inert mirror cannot
  support an "integrated urban-freeway coupling" claim.
- **P1** — Unify the follower's internal prediction with the plant by calling
  `run_coupled_interval` (or `freeway_step` with `offramp_capacity_veh_h`) so the
  optimizer and the simulator share one model.
- **P1** — Make the Nash loop a genuine mutual best response (urban follower consumes
  `freeway_response`; freeway follower reflects urban control), or state explicitly
  that it is single-shot.
- **Ops** — Re-run baseline/proposed on the current model and preserve the key
  artifacts (`control_timeseries.csv`, etc.) in an inspectable form; the committed
  report is stale and `outputs/` is git-ignored.
- Differentiate/document the baseline modes; add the missing spec metrics
  (`speed_drop_reduction`, `number_of_stops_proxy`).

## Should Codex Rerun Simulation?

**No** for certification — a rerun aimed at the 8% verdict is premature.

However, a *diagnostic* rerun on the current model is required, because the committed
run report is stale and there are currently no results matching `c4e68b3`. Acceptance
interpretation should wait until the P0 blocking items (nested coupling, functional
on-ramp coupling, genuine Nash response) are resolved — which is consistent with the
audit's own "treat Total TTT as diagnostic only" position.
