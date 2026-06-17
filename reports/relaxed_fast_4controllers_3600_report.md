# Relaxed-Fast 4-Controller 3600s Screening Report

## Scope

- Date: 2026-06-17
- Controller set: `WU-CD-F`, `PROPOSED-FOLLOWERS-ONLY`, `PROPOSED-STACKELBERG`, `PROPOSED-CENTRALIZED`
- Scenarios: `low_demand`, `medium_demand`, `peak_demand`, `oversaturated_demand`, `incident_or_capacity_drop`, `capacity_drop`
- Horizon: `3600 s`
- Mode: `--relaxed-quantized-controls --relaxed-fast-mode`
- Output root: `outputs/relaxed_fast_4controllers_3600`
- Combined CSVs:
  - `outputs/relaxed_fast_4controllers_3600/combined_summary.csv`
  - `outputs/relaxed_fast_4controllers_3600/combined_paired_comparisons.csv`
  - `outputs/relaxed_fast_4controllers_3600/combined_relaxed_diagnostics.csv`

The independent review subagent verdict was PASS for running this screening one
scenario per invocation.

## Commands

Validation:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\models\state.py src\controllers\relaxed_quantization.py src\controllers\wu_distributed.py src\controllers\urban_follower.py src\controllers\freeway_follower.py src\controllers\distributed_coordinator.py src\controllers\centralized_mpc.py src\controllers\nash_solver.py src\experiments\six_controller_comparison.py src\evaluation\metrics.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints src.tests.test_six_controller_comparison -v
```

Simulation command pattern:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --scenario <scenario> --T-total 3600 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --relaxed-quantized-controls --relaxed-fast-mode --output outputs\relaxed_fast_4controllers_3600\<scenario>
```

## Runtime

- Wall-clock runtime for all 24 runs: `910.4 s`.
- Sum of controller-reported computation time: `880.74 s`.
- This is a clear computation-cost improvement over the prior 9-hour run.

| Controller | Total computation time [s] | Average per scenario [s] |
|---|---:|---:|
| `WU-CD-F` | 32.76 | 5.46 |
| `PROPOSED-FOLLOWERS-ONLY` | 1.21 | 0.20 |
| `PROPOSED-STACKELBERG` | 527.46 | 87.91 |
| `PROPOSED-CENTRALIZED` | 319.31 | 53.22 |

## Scenario Summary

| Scenario | Best TTT controller | WU TTT | P-FO TTT | P-Stack TTT | P-Cent TTT |
|---|---|---:|---:|---:|---:|
| `low_demand` | `WU-CD-F` | 354.250 | 426.791 | 544.629 | 392.152 |
| `medium_demand` | `WU-CD-F` | 554.045 | 1098.285 | 1140.216 | 1002.357 |
| `peak_demand` | `PROPOSED-CENTRALIZED` | 2521.447 | 1778.235 | 1970.282 | 1652.604 |
| `oversaturated_demand` | `PROPOSED-FOLLOWERS-ONLY` | 4500.765 | 3012.109 | 3432.532 | 3437.740 |
| `incident_or_capacity_drop` | `PROPOSED-CENTRALIZED` | 2259.426 | 1710.096 | 1822.937 | 1592.862 |
| `capacity_drop` | `WU-CD-F` | 8002.199 | 8535.703 | 10206.175 | 8970.159 |

## Pairwise Interpretation

`FollowerPackageDifference = WU-CD-F - PROPOSED-FOLLOWERS-ONLY`.

| Scenario | TTT diff | Delay diff | Delay % | Throughput diff |
|---|---:|---:|---:|---:|
| `low_demand` | -72.541 | -72.541 | -689.09 | -110.6 |
| `medium_demand` | -544.240 | -544.240 | -579.48 | -819.7 |
| `peak_demand` | 743.212 | 743.211 | 38.07 | 2433.8 |
| `oversaturated_demand` | 1488.656 | 1488.655 | 39.20 | 3077.3 |
| `incident_or_capacity_drop` | 549.330 | 549.330 | 32.09 | 2073.5 |
| `capacity_drop` | -533.504 | -533.505 | -8.60 | -1184.4 |

`FullPackageValue = WU-CD-F - PROPOSED-STACKELBERG`.

| Scenario | TTT diff | Delay diff | Delay % | Throughput diff |
|---|---:|---:|---:|---:|
| `low_demand` | -190.379 | -190.379 | -1808.48 | -215.1 |
| `medium_demand` | -586.171 | -586.171 | -624.13 | -779.5 |
| `peak_demand` | 551.165 | 551.164 | 28.23 | 2193.1 |
| `oversaturated_demand` | 1068.233 | 1068.232 | 28.13 | 2856.7 |
| `incident_or_capacity_drop` | 436.489 | 436.489 | 25.50 | 1880.3 |
| `capacity_drop` | -2203.976 | -2203.977 | -35.52 | -4883.7 |

`ProposedLeaderValue = PROPOSED-FOLLOWERS-ONLY - PROPOSED-STACKELBERG`.

| Scenario | TTT diff | Delay diff | Delay % |
|---|---:|---:|---:|
| `low_demand` | -117.838 | -117.838 | -141.86 |
| `medium_demand` | -41.931 | -41.931 | -6.57 |
| `peak_demand` | -192.047 | -192.047 | -15.89 |
| `oversaturated_demand` | -420.423 | -420.423 | -18.21 |
| `incident_or_capacity_drop` | -112.841 | -112.841 | -9.71 |
| `capacity_drop` | -1670.472 | -1670.472 | -24.79 |

## Diagnostics

- `authority_ok=True` for all 24 controller/scenario runs.
- `relaxed_quantized_controls=1` and `relaxed_fast_mode=1` were recorded for all decision rows.
- Relaxed repair diagnostics are no longer silent-zero:
  - WU green repair counts are nonzero in all scenarios.
  - WU VSL repair counts are nonzero in medium/peak/oversaturated/incident/capacity-drop scenarios.
  - Proposed follower and Stackelberg green repair counts are nonzero.

## Interpretation

The relaxed-fast implementation fixes the computation-cost failure mode: the
full primary screening finished in about 15 minutes, not hours.

Performance is mixed:

- Proposed controllers improve strongly over WU in `peak_demand`,
  `oversaturated_demand`, and `incident_or_capacity_drop`.
- WU remains best in `low_demand`, `medium_demand`, and `capacity_drop`.
- `PROPOSED-STACKELBERG` is worse than `PROPOSED-FOLLOWERS-ONLY` in all six
  scenarios in this relaxed-fast run. This means the current leader/allocation
  layer is not yet adding value under the relaxed screening budget.
- `PROPOSED-CENTRALIZED` is best in `peak_demand` and
  `incident_or_capacity_drop`, but not in `oversaturated_demand` or
  `capacity_drop`.

## PASS/FAIL

Computation-cost screening: PASS.

Full controller acceptance: FAIL / not claimed.

Reasons:

- Proposed Stackelberg does not consistently improve over WU or over proposed
  followers-only.
- Several solver convergence rates remain low, especially centralized random
  search and proposed Stackelberg.
- The relaxed-fast mode is a computational screening variant, not a final
  full-budget optimality claim.
