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

## Latest full-five validation

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

## Current pushed work summary

Pushed implementation and tooling:

- Parallel scenario runner: `work/run_parallel_scenarios.py`.
- Parallel candidate matrix runner: `work/run_parallel_candidate_matrix.py`.
- Env-gated diagnostic objective terms in `src/controllers/stackelberg_mpc.py` and `src/models/state.py`.
- Price authority controls in `work/run_claude_style_five_controller.py`.
- Adaptive metering price authority in `src/controllers/stackelberg_wu_metered.py`.
- This progress document with the search path, rejected branches, current best, and next search direction.

Validation completed:

- Syntax compile passed for the changed Python files.
- Full-five `T=14400` validation completed for the current best candidate.
- Current best is robust on four scenarios but still misses the all-scenario goal.

## Next task

The next search should focus on Skew while protecting the four existing wins.

Most promising next controller direction:

- Keep `BUDGET_OFF=1`.
- Keep `PSTACK_STANDALONE=1`.
- Keep `VSL_PRICE=0`.
- Keep forecast-demand-gated adaptive metering.
- Do not change depth/horizon.
- Investigate whether the N_P dual/price path is constraining D/F ramp-aware green movement on Skew:
  - `NP_OFF=1`
  - `NP_CAND_LAMBDA=0`
  - `NP_PD_ITER=0/1/2`
  - `NP_BIAS=0`
- If that is not enough, add only general pressure-based logic/objective terms, not scenario-specific or signal-name-specific hacks.

Suggested next screen:

```powershell
python work/run_parallel_candidate_matrix.py `
  --scenarios sweet_170_skew15_w,sweet_190_w `
  --T-total 14400 `
  --workers 10 `
  --controllers P-STACK-WU-FAITHFUL-ALLPRICE-JOINT `
  --output outputs\_skew_high14400_np_dual_screen `
  --pfo-root outputs/_full14400_budgetoff_trust2_5scen `
  --candidate 'base:' `
  --candidate 'np_off:NP_OFF=1' `
  --candidate 'np_candlambda0:NP_CAND_LAMBDA=0' `
  --candidate 'np_pd0:NP_PD_ITER=0' `
  --candidate 'np_pd1:NP_PD_ITER=1' `
  --candidate 'np_pd2:NP_PD_ITER=2' `
  --candidate 'np_bias0:NP_BIAS=0'
```
