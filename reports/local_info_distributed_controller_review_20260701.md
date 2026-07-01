# Local-Info Distributed Controller Fidelity Review

Date: 2026-07-01

## Scope

This note summarizes the code review and read-only probes performed after the
local-info distributed controller began performing worse than no-control in
`urban_med` and `sweet_155`.

The main question was not whether a no-control fallback should hide the
degradation. The question was whether `PROPOSED-FOLLOWERS-ONLY` and the
Wu-faithful P-Stack follower are actually minimizing a TTT-compatible objective.

## Leader Controller Changes Already Added

The current P-Stack leader path contains the PFO-anchor search changes:

- `StackelbergWuMeteredController` evaluates the PFO-equivalent point and uses
  it as the leader search center.
- Global search is now hybrid:
  - local refinement around the PFO-equivalent `(N_P_star, N_UF_star)`;
  - a limited full-range scout so the leader is not locked to the PFO region.
- A strict PFO-incumbent tie-break keeps the actual PFO `ControlAction` when a
  leader-conditioned replay only matches the same objective.
- The 180 s `urban_med` smoke reduced full leader evaluations from `10` to `4`
  and wall time from about `54.24 s` to `21.38 s`.

This is not a no-control guard. The current diagnosis intentionally excludes
adding no-control/PFO no-control guards as the main fix. If PFO truly minimizes
TTT-compatible cost, it should not need a no-control guard to avoid choosing a
worse-than-no-control action.

## Review Findings

### 1. Urban local objective drops vehicles after service

`src/controllers/local_signal_plant.py` scores ordinary and phased urban
rollouts with `sum(q.values()) * dt_h`.

After a vehicle is served, the local rollout removes it from the movement queue
and mostly stops charging it, while the plant still counts downstream storage
and terminal vehicles in TTT.

Plant accounting in `src/models/urban_queue_model.py` charges:

- urban movement queues;
- urban storage occupancy;
- off-ramp storage reattributed to freeway TTT.

This can make a green plan look good locally because it moves vehicles out of
the current movement queue, even if the plant still holds them downstream.

### 2. Ramp-aware local off-ramp drain likely has a sign error

In `rollout_local_tts_ramp_aware`, draining off-ramp storage updates downstream
available space with:

```python
s_eff[recv] += actual
```

The plant consumes downstream receiving space when those vehicles enter the
receiving link:

```python
state.urban_link_storage[receiving_link] -= actual
```

So the local model can treat off-ramp drainage as creating downstream space,
while the plant treats it as occupying downstream space. This is a strong
candidate for local ranking inversion.

### 3. Freeway/ramp release is wired to density, but timing differs

The earlier suspicion that ramp release never enters freeway density is not
supported. The plant passes actual metered release into `freeway_substep`, and
METANET injects it at the merge segment.

The mismatch is timing:

- local freeway scoring adds `u_on_{ramp}` into ramp reservoir before local
  metering release;
- the plant computes metering release from the current ramp reservoir first,
  then urban green release enters the ramp reservoir afterward.

Therefore the local scorer can rank a metering candidate using same-step
urban-to-ramp arrivals that the plant cannot meter until later.

### 4. PFO chooses a control that is worse under full plant rollout

A read-only one-step probe used the same initial state and same forecast, then
re-evaluated no-control, fixed, and PFO-selected actions with the full coupled
plant rollout.

For `sweet_155`, first decision step:

| action | horizon total TTT | freeway TTT | urban TTT |
|---|---:|---:|---:|
| no-control | 104.097684 | 31.449689 | 72.647995 |
| PFO-selected | 104.652236 | 31.530155 | 73.122080 |

The PFO-selected action was already worse than no-control under the same full
plant rollout that `WuFaithfulFollower.solve()` later reports as
`objective_value`.

Additional green sweep on the same state showed that better candidates existed:

| F p1 green | full rollout total TTT |
|---:|---:|
| 50 s | 104.652236 |
| 56 s | 104.097684 |
| 62 s | 103.672590 |

This points to local scoring/ranking error, not absence of feasible candidates.

### 5. Wu-metered P-Stack prefilter is action-blind

For the Wu-faithful follower path, the leader prefilter currently uses a cheap
current-state proxy rather than a candidate-dependent follower response. This
means different `(N_P_star, N_UF_star)` candidates can receive nearly identical
prefilter scores before full follower evaluation.

The risk is that top-K filtering may prune useful leader candidates for reasons
unrelated to predicted TTT. This is secondary to the PFO local objective issue,
but it matters once the follower fidelity is fixed.

### 6. P-Stack fallback rows can be post-hoc PFO labels

The Wu-metered P-Stack wrapper evaluates a leaderless PFO response and then
derives a PFO-equivalent `(N_P_star, N_UF_star)` label afterward. Those labels
are useful as anchors, but they were not actually applied as leader targets
during that leaderless PFO solve.

This explains why recent `urban_med` P-Stack runs matched PFO exactly while
still showing nonzero reported leader targets.

## Interpretation

The performance drop after switching to local-info distributed control is most
consistent with objective fidelity loss:

1. PFO local candidates are scored with a local movement-queue proxy.
2. The plant scores movement queue plus storage and freeway/ramp coupling.
3. Candidate rankings can invert.
4. P-Stack anchored on PFO inherits the follower's local ranking errors.

Thus the priority is not adding guards. The priority is making the local
candidate scorer TTT-compatible with the plant.

## Recommended Fix Order

1. Correct the off-ramp downstream storage sign in
   `rollout_local_tts_ramp_aware`.
2. Extend ordinary/phased urban local rollout cost so served vehicles remain
   counted when they occupy local receiving storage or downstream proxy storage.
3. Align local freeway ramp-release timing with the coupled plant ordering.
4. Add a rank-inversion test:
   - local cost ranking for a small green/RM/VSL candidate set;
   - full `run_coupled_interval` rollout ranking on the same copied state.
5. After follower fidelity is fixed, revisit the Wu-metered P-Stack prefilter
   so candidate ranking is action-dependent before top-K pruning.

## Validation Status

This report is based on static review and read-only one-step probes. No source
code was changed in this review step.

The previous PFO-anchor leader-search implementation was already compiled and
smoke-tested in `reports/codex_run_report.md`.
