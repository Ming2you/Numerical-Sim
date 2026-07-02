# Legacy P-Stack Reproduction Handoff

Date: 2026-07-02

## Goal

The next primary task is to reproduce the strong `legacy pre-WuFaithful
P-Stack` results with the current faster `WuFaithful P-Stack` architecture.

In other words, do not treat the legacy controller as the final controller. Use
it as the performance target and diagnostic reference. The research goal is:

```text
current WuFaithful P-Stack speed/structure
+ legacy pre-WuFaithful P-Stack performance behavior
```

## Why This Became the Next Target

The same-condition 7200 s comparison shows that the older pre-WuFaithful
Stackelberg path still finds substantially better solutions in both sweet
scenarios, but at much higher computation cost.

This means the leader concept is not the main problem. The likely issue is that
the current WuFaithful simplification/search path no longer sees, generates, or
scores part of the useful action-response space that the legacy P-Stack used.

## Evidence

Comparison CSV:

- `outputs/legacy_pstack_sweet155_sweet190_7200_20260702/comparison_summary.csv`

Detailed run note:

- `reports/codex_run_report.md`

| scenario | controller | total TTT | urban TTT | freeway TTT | completed veh | terminal veh | compute sec |
|---|---:|---:|---:|---:|---:|---:|---:|
| sweet_155 | current PFO | `4490.018` | `3676.465` | `813.553` | `32519.3` | `4244.7` | `161.61` |
| sweet_155 | current WuFaithful P-Stack | `4568.062` | `3772.098` | `795.964` | `32238.1` | `4527.8` | `841.34` |
| sweet_155 | legacy pre-WuFaithful P-Stack | `4051.641` | `3318.737` | `732.904` | `33243.2` | `3551.2` | `3219.54` |
| sweet_190 | current PFO | `13590.622` | `12365.455` | `1225.166` | `29731.7` | `15300.0` | `164.62` |
| sweet_190 | current WuFaithful P-Stack | `12984.869` | `11581.681` | `1403.187` | `30808.5` | `14194.3` | `827.07` |
| sweet_190 | legacy pre-WuFaithful P-Stack | `10728.763` | `9201.420` | `1527.343` | `33260.2` | `11685.0` | `3661.68` |

Legacy pre-WuFaithful P-Stack improvement over current WuFaithful P-Stack:

- `sweet_155`: `-516.421 veh-h` total TTT, `+1005.1` completed vehicles,
  `-976.6` terminal vehicles.
- `sweet_190`: `-2256.106 veh-h` total TTT, `+2451.7` completed vehicles,
  `-2509.3` terminal vehicles.

## Important Interpretation

Do not conclude:

```text
P-Stack leader is useless.
```

The evidence suggests the opposite:

```text
P-Stack can work, but the current WuFaithful follower/search approximation is
not yet reproducing the useful legacy action-response behavior.
```

The current problem is therefore a reproduction/diagnosis problem, not a reason
to abandon the Stackelberg structure.

## Immediate Diagnostic Questions

The next implementation round should compare legacy P-Stack and current
WuFaithful P-Stack step by step on `sweet_155` and `sweet_190`.

Focus on:

1. Leader targets
   - `N_P_star`
   - `N_UF_star`
   - selected objective
   - fallback/PFO incumbent selection

2. Follower response
   - total ramp metering release
   - per-ramp metering release
   - VSL activation and direction
   - green allocation by intersection/phase
   - offset changes
   - realized `sum_nin` / protected net inflow response

3. State response
   - urban departures
   - boundary queue and movement queue
   - on-ramp queue
   - freeway density and speed
   - completed vehicles
   - terminal vehicles

4. Objective fidelity
   - predicted leader objective
   - follower response objective
   - realized plant step TTT
   - cumulative realized TTT

## Candidate Causes to Test

The most likely causes are:

1. WuFaithful follower candidate set is too narrow.
   - Current local candidate generation may not include the legacy green/RM/VSL
     combinations that produced the better global response.

2. Current leader search is too anchored to PFO.
   - PFO-anchor stabilization is useful, but it may prevent the leader from
     moving toward the legacy solution family.

3. Current follower response scoring differs from legacy scoring.
   - The current WuFaithful local objective may be more conservative, more local,
     or less sensitive to downstream/global state than the legacy distributed
     coordinator.

4. Some coupling response is approximated away.
   - Especially check on-ramp release, green allocation, offset response, and
     urban departure effects.

5. High-accuracy search helps but is not enough.
   - High-accuracy current P-Stack improved sweet scenarios, but still did not
     reach legacy P-Stack performance.

## Recommended Next Procedure

1. Build a step-aligned comparison table for:
   - `sweet_155`
   - `sweet_190`
   - legacy pre-WuFaithful P-Stack
   - current WuFaithful P-Stack

2. Identify the first step where the control trajectory diverges materially.

3. At that step, compare:
   - legacy selected control
   - current selected control
   - whether current WuFaithful can evaluate the legacy-like candidate
   - whether current leader would choose that candidate if it were present

4. Classify the failure:
   - candidate generation failure
   - feasible-set/projection failure
   - objective scoring failure
   - rollout/plant fidelity failure
   - search-budget failure

5. Only then modify code.

## Guardrails

- Do not delete historical outputs or reports.
- Do not treat the legacy controller as production-ready, because its compute
  cost is too high.
- Do not optimize only `sweet_155`; reproduction must hold at least on both
  `sweet_155` and `sweet_190`.
- Keep the current WuFaithful speed advantage as an explicit constraint.
- Update `reports/codex_run_report.md` after each substantial diagnostic or
  implementation attempt.

## Desired End State

A successful next step should produce:

```text
current WuFaithful P-Stack TTT close to legacy pre-WuFaithful P-Stack
with computation cost closer to current WuFaithful P-Stack than to legacy.
```

At minimum, the next round should explain quantitatively why the current
WuFaithful path cannot yet reproduce the legacy solution.
