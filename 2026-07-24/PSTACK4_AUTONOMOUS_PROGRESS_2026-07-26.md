# P-Stack4 autonomous redesign progress - 2026-07-26

## Goal

Find a robust, non-scenario-specific P-Stack controller that beats PFO on all five original scenarios at `T=14400`.

Hard constraints followed:

- Did not change controller depth/horizon for final search. `LEADER_V_DEPTH` was not used.
- Final validation target stayed at `T=14400`; shorter runs were only earlier diagnostics.
- P-Stack candidate runs used `PSTACK_STANDALONE=1`, so no PFO incumbent/fallback rescue.
- Added knobs are env-gated and disabled by default.

## Code added or changed

- Added `work/run_parallel_scenarios.py`.
  - Runs multiple scenarios concurrently.
  - Writes one output directory per scenario and keeps per-scenario stdout/stderr logs.

- Added `work/run_parallel_candidate_matrix.py`.
  - Runs candidate x scenario matrices concurrently.
  - Supports per-candidate env overrides such as `NAME:KEY=VALUE;KEY=VALUE`.
  - Writes `case_status.csv` and `score_summary.csv` while running.

- Extended P-Stack objective diagnostics in `src/controllers/stackelberg_mpc.py` and `src/models/state.py`.
  - Env-gated endpoint/trajectory terms:
    - `LEADER_URBAN_BARRIER`
    - `LEADER_RES_BALANCE`
    - `LEADER_GREEN_GUARD`
    - `LEADER_METER_CAP`
    - `LEADER_NP_AUTH_REG`
  - These were tested diagnostically, but are not the current best path.

- Added price-channel authority controls in `work/run_claude_style_five_controller.py`.
  - `METER_PRICE=0`
  - `VSL_PRICE=0`
  - `METER_PRICE_ADAPT=1`
  - `METER_ADAPT_*`
  - `METER_ADAPT_DEMAND=1`

- Added adaptive metering price authority in `src/controllers/stackelberg_wu_metered.py`.
  - State stress uses protected urban accumulation and freeway density.
  - Optional forecast demand gate uses forecast peak total demand.
  - If adaptive weight is zero, the metering price channel is fully inactive for that step, including trust/cert side effects.

- Added env-gated adaptive N_P dual authority in `src/controllers/stackelberg_wu_metered.py`.
  - `NP_DUAL_ADAPT_GATE=1` lets the N_P dual price act only when adaptive metering pressure is materially active.
  - `NP_DUAL_ADAPT_MIN_W` controls the activation threshold; final validation used `0.10`.
  - This is not scenario-specific; it keys off the same forecast-demand/state-stress metering authority signal.

- Added continuous adaptive N_P dual authority.
  - `NP_DUAL_ADAPT_MODE=scale` changes the gate from binary on/off to `lambda_eff = alpha * lambda_P`.
  - `NP_DUAL_ADAPT_LO_W` and `NP_DUAL_ADAPT_HI_W` define the smoothstep ramp for `alpha`.
  - `wu_faithful_np_price_scale` and `wu_faithful_np_effective_lambda` are exported for diagnostics.

## Important validation results

Baseline full-five candidates:

| Candidate | Low | Medium | Skew | Incident | High |
|---|---:|---:|---:|---:|---:|
| `BUDGET_OFF=1, GREEN_TRUST_SEC=1` | -7.345 | -93.572 | +66.449 | -195.525 | +253.490 |
| `BUDGET_OFF=1, GREEN_TRUST_SEC=2` | -5.026 | -71.042 | +72.053 | -193.525 | +77.259 |

Interpretation:

- `BUDGET_OFF=1` is a strong general change.
- Low, Medium, and Incident already beat PFO.
- Remaining blockers were Skew and High.

Skew/High search highlights:

- `VSL_PRICE=0` improved High from `+77.259` to `+61.575`, but did not solve Skew.
- `METER_PRICE=0` improved Skew from `+72.053` to `+47.465`, but hurt High.
- `VSL_PRICE=0, METER_PRICE_W=1.25` beat High by `-66.946`, but left Skew at `+71.565`.
- State-only adaptive metering failed because High needed the metering price channel earlier than current state stress activated it.
- Demand-gated adaptive metering was the best direction so far.

Current best Skew/High candidate:

```text
GREEN_TRUST_SEC=1.5
VSL_PRICE=0
METER_PRICE_ADAPT=1
METER_ADAPT_DEMAND=1
METER_ADAPT_LO=0.55
METER_ADAPT_HI=0.70
BUDGET_OFF=1
PSTACK_STANDALONE=1
```

Result on the two remaining blocker scenarios:

| Scenario | PFO | P-Stack | Gap |
|---|---:|---:|---:|
| `sweet_170_skew15_w` | 3944.430 | 3976.971 | +32.541 |
| `sweet_190_w` | 6079.287 | 5926.607 | -152.680 |

This is not solved yet. It beats High strongly but still loses Skew by about 32.5 TTT.

Rejected/latest failed branch:

- Green price subset tests (`PRICE_SIGNALS=A,B,C`, `A,B`, `C`, or `GREEN_PRICE=0`) were much worse:
  - Skew best in that screen was `+522.352`.
  - High best in that screen was `+1467.282`.
  - Do not continue that path unless a new reason appears.

## Current diagnosis

Skew remaining loss is mostly urban-side:

- PFO Skew uses strong D/F ramp-aware green movement:
  - Late `D_p1` around `41.15`, `F_p1` around `62.00`.
- Current best P-Stack keeps D/F close to neutral:
  - Late `D_p1` around `56.25`, `F_p1` around `56.00`.
- This reduces freeway pressure but leaves urban delay worse than PFO.

High needed demand-gated metering price authority:

- Fixed high metering price weight can beat High.
- Pure state gate activates too late.
- Forecast demand gate is the useful general signal so far.

## Previous full-five validation

The current best candidate was run on all five original scenarios at `T=14400` with five parallel workers.

Output root:

```text
outputs/_full14400_demand_gate_t15_candidate
```

Comparison baseline:

```text
outputs/_full14400_budgetoff_trust2_5scen
```

Result:

| Scenario | PFO TTT | P-Stack TTT | Gap | P-Stack freeway TTT | P-Stack urban TTT |
|---|---:|---:|---:|---:|---:|
| `sweet_155_w` | 3070.813 | 3064.265 | -6.548 | 1920.342 | 1143.923 |
| `sweet_170_w` | 3972.043 | 3870.918 | -101.125 | 2313.344 | 1557.575 |
| `sweet_170_skew15_w` | 3944.430 | 3976.971 | +32.541 | 2314.270 | 1662.701 |
| `sweet_170_incident_w` | 5606.992 | 5408.098 | -198.894 | 3783.608 | 1624.490 |
| `sweet_190_w` | 6079.287 | 5926.607 | -152.680 | 3478.431 | 2448.177 |

Status:

- Current best is `4/5` wins at `T=14400`.
- It is not solved yet because Skew still loses by `+32.541`.
- The full-five run confirms that Low, Medium, Incident, and High remain safe under the demand-gated adaptive metering candidate.

## First verified 5/5 candidate

The next diagnostic screen showed that fully removing the N_P dual path fixes Skew but breaks High:

| Candidate | Skew gap | High gap |
|---|---:|---:|
| `NP_PD_ITER=0` | -7.399 | +142.756 |
| `NP_OFF=1` | -7.399 | +143.238 |
| `NP_CAND_LAMBDA=0` | -7.399 | +142.756 |

The robust fix is to keep the N_P dual path only when adaptive metering authority is materially active:

```text
NP_DUAL_ADAPT_GATE=1
NP_DUAL_ADAPT_MIN_W=0.10
```

Final candidate env, relative to the common P-Stack settings:

```text
BUDGET_OFF=1
PSTACK_STANDALONE=1
GREEN_TRUST_SEC=1.5
VSL_PRICE=0
METER_PRICE_ADAPT=1
METER_ADAPT_DEMAND=1
METER_ADAPT_LO=0.55
METER_ADAPT_HI=0.70
NP_DUAL_ADAPT_GATE=1
NP_DUAL_ADAPT_MIN_W=0.10
```

Full-five validation output:

```text
outputs/_full14400_np_adapt_gate_candidate
```

Comparison baseline:

```text
outputs/_full14400_budgetoff_trust2_5scen
```

Final `T=14400` result:

| Scenario | PFO TTT | P-Stack TTT | Gap | P-Stack freeway TTT | P-Stack urban TTT |
|---|---:|---:|---:|---:|---:|
| `sweet_155_w` | 3070.813 | 3064.265 | -6.548 | 1920.342 | 1143.923 |
| `sweet_170_w` | 3972.043 | 3871.780 | -100.263 | 2311.578 | 1560.202 |
| `sweet_170_skew15_w` | 3944.430 | 3937.031 | -7.399 | 2295.678 | 1641.353 |
| `sweet_170_incident_w` | 5606.992 | 5408.535 | -198.457 | 3782.846 | 1625.688 |
| `sweet_190_w` | 6079.287 | 5926.607 | -152.680 | 3478.431 | 2448.177 |

Status:

- Final candidate is `5/5` wins at `T=14400`.
- No depth/horizon override was used.
- P-Stack remained standalone with `PSTACK_STANDALONE=1`.
- The gate was active only in materially high-pressure cases:
  - `sweet_155_w`: `0/80` active steps
  - `sweet_170_w`: `0/80` active steps
  - `sweet_170_skew15_w`: `0/80` active steps
  - `sweet_170_incident_w`: `21/80` active steps
  - `sweet_190_w`: `34/80` active steps

## Continuous dual authority validation

The binary gate was generalized to a continuous authority scale:

```text
lambda_eff = alpha * lambda_P
alpha = smoothstep(NP_DUAL_ADAPT_LO_W, NP_DUAL_ADAPT_HI_W, adaptive_metering_weight)
```

Representative continuous candidate:

```text
NP_DUAL_ADAPT_GATE=1
NP_DUAL_ADAPT_MODE=scale
NP_DUAL_ADAPT_LO_W=0.05
NP_DUAL_ADAPT_HI_W=0.20
```

Full-five validation output:

```text
outputs/_full14400_np_dual_scale005_020_candidate
```

Final `T=14400` result for the continuous candidate:

| Scenario | PFO TTT | P-Stack TTT | Gap | P-Stack freeway TTT | P-Stack urban TTT |
|---|---:|---:|---:|---:|---:|
| `sweet_155_w` | 3070.813 | 3064.265 | -6.548 | 1920.342 | 1143.923 |
| `sweet_170_w` | 3972.043 | 3871.780 | -100.263 | 2311.578 | 1560.202 |
| `sweet_170_skew15_w` | 3944.430 | 3937.031 | -7.399 | 2295.678 | 1641.353 |
| `sweet_170_incident_w` | 5606.992 | 5408.535 | -198.457 | 3782.846 | 1625.688 |
| `sweet_190_w` | 6079.287 | 5926.607 | -152.680 | 3478.431 | 2448.177 |

Scale diagnostics:

- `sweet_155_w`: active `0/80`, partial `0`, mean scale `0.000`
- `sweet_170_w`: active `0/80`, partial `0`, mean scale `0.000`
- `sweet_170_skew15_w`: active `1/80`, partial `1`, max scale `0.003`
- `sweet_170_incident_w`: active `21/80`, partial `1`, mean scale `0.257`
- `sweet_190_w`: active `34/80`, partial `0`, mean scale `0.425`

Additional Skew/High screens with wider continuous ramps also preserved the same two-scenario result:

| Candidate | Skew gap | High gap |
|---|---:|---:|
| `scale000_050` | -7.399 | -152.680 |
| `scale000_080` | -7.399 | -152.680 |
| `scale000_125` | -7.399 | -152.680 |

Interpretation:

- The controller no longer requires a binary implementation; the N_P dual price can be represented as a smooth authority scale.
- In the original five scenarios, the control choice lies on a plateau: continuous scale and switch gate produce the same TTT.
- The D/F over-binding failure is still avoided because Skew's adaptive metering pressure is near zero, so `lambda_eff` remains near zero there.
- High and Incident still receive strong N_P dual authority in high-pressure intervals.

## Current pushed work summary

Pushed implementation and tooling:

- Parallel scenario runner: `work/run_parallel_scenarios.py`.
- Parallel candidate matrix runner: `work/run_parallel_candidate_matrix.py`.
- Env-gated diagnostic objective terms in `src/controllers/stackelberg_mpc.py` and `src/models/state.py`.
- Price authority controls in `work/run_claude_style_five_controller.py`.
- Adaptive metering price authority in `src/controllers/stackelberg_wu_metered.py`.
- Adaptive N_P dual gate and continuous scale mode in `src/controllers/stackelberg_wu_metered.py`, `src/controllers/wu_faithful_follower.py`, and `work/run_claude_style_five_controller.py`.
- This progress document with the search path, rejected branches, final candidate, and validation evidence.

Validation completed:

- Syntax compile passed for the changed Python files.
- Skew/High N_P dual screen completed.
- Adaptive N_P dual gate threshold screen completed.
- Full-five `T=14400` validation completed for the final candidate.
- Continuous adaptive dual scale screen completed.
- Full-five `T=14400` validation completed for `scale005_020`.
- Final candidate beats PFO on all five original scenarios.
