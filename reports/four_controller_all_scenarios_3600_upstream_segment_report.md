# Four-Controller Scenario Comparison, 3600s, Upstream-Segment Topology

## Run Scope

- Topology: 4 freeway segments per link, with a simple upstream `seg0`.
- Horizon: `3600 s`.
- Controllers:
  - `WU-CD-F`
  - `PROPOSED-FOLLOWERS-ONLY`
  - `PROPOSED-STACKELBERG`
  - `PROPOSED-CENTRALIZED`
- Output root: `outputs/four_controller_all_scenarios_3600_upstream_segment`

This run is a 4-controller pairwise comparison, not a no-control baseline comparison.

## Commands

Each scenario was run with:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --scenario <scenario> --T-total 3600 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --output outputs\four_controller_all_scenarios_3600_upstream_segment\<scenario>
```

## Controller Metrics

| Scenario | Controller | Total TTT | Total Delay | Throughput | Terminal Vehicles | Converged Rate |
|---|---|---:|---:|---:|---:|---:|
| low_demand | WU-CD-F | 347.823 | 4.100 | 8666.8 | 319.3 | 0.85 |
| low_demand | PROPOSED-FOLLOWERS-ONLY | 405.402 | 61.679 | 8569.7 | 416.4 | 1.00 |
| low_demand | PROPOSED-STACKELBERG | 450.171 | 106.448 | 8487.9 | 498.2 | 1.00 |
| low_demand | PROPOSED-CENTRALIZED | 377.590 | 33.867 | 8628.4 | 357.7 | 1.00 |
| medium_demand | WU-CD-F | 529.830 | 69.703 | 11297.8 | 771.9 | 0.85 |
| medium_demand | PROPOSED-FOLLOWERS-ONLY | 1047.055 | 586.928 | 10429.7 | 1640.0 | 1.00 |
| medium_demand | PROPOSED-STACKELBERG | 912.089 | 451.962 | 10699.3 | 1370.5 | 1.00 |
| medium_demand | PROPOSED-CENTRALIZED | 932.878 | 472.751 | 10547.4 | 1522.4 | 1.00 |
| peak_demand | WU-CD-F | 2474.384 | 1905.065 | 9108.2 | 5715.3 | 0.65 |
| peak_demand | PROPOSED-FOLLOWERS-ONLY | 1712.395 | 1143.077 | 11549.8 | 3273.7 | 1.00 |
| peak_demand | PROPOSED-STACKELBERG | 1831.105 | 1261.787 | 11426.9 | 3396.6 | 1.00 |
| peak_demand | PROPOSED-CENTRALIZED | 1626.092 | 1056.774 | 11936.7 | 2886.8 | 0.90 |
| oversaturated_demand | WU-CD-F | 4482.918 | 3780.030 | 8794.0 | 9509.6 | 0.70 |
| oversaturated_demand | PROPOSED-FOLLOWERS-ONLY | 2915.558 | 2212.669 | 11969.7 | 6333.9 | 1.00 |
| oversaturated_demand | PROPOSED-STACKELBERG | 3248.717 | 2545.829 | 11870.8 | 6432.8 | 1.00 |
| oversaturated_demand | PROPOSED-CENTRALIZED | 2810.376 | 2107.488 | 12505.4 | 5798.2 | 0.55 |
| incident_or_capacity_drop | WU-CD-F | 2218.689 | 1671.005 | 9150.3 | 5221.1 | 0.65 |
| incident_or_capacity_drop | PROPOSED-FOLLOWERS-ONLY | 1646.729 | 1099.045 | 11242.0 | 3129.4 | 1.00 |
| incident_or_capacity_drop | PROPOSED-STACKELBERG | 1679.822 | 1132.138 | 11234.9 | 3136.5 | 1.00 |
| incident_or_capacity_drop | PROPOSED-CENTRALIZED | 1554.556 | 1006.872 | 11581.9 | 2789.5 | 0.95 |
| capacity_drop | WU-CD-F | 8012.501 | 6215.763 | 12553.0 | 15892.6 | 0.45 |
| capacity_drop | PROPOSED-FOLLOWERS-ONLY | 8411.293 | 6614.555 | 11592.9 | 16852.7 | 1.00 |
| capacity_drop | PROPOSED-STACKELBERG | 10269.381 | 8472.643 | 7775.1 | 20670.6 | 1.00 |
| capacity_drop | PROPOSED-CENTRALIZED | 9326.771 | 7530.034 | 10081.3 | 18364.4 | 0.70 |

## WU-CD-F Relative Improvement

Positive means the controller is better than `WU-CD-F`.

| Scenario | Controller | TTT Improvement | Delay Improvement | Throughput Improvement |
|---|---|---:|---:|---:|
| low_demand | PROPOSED-FOLLOWERS-ONLY | -16.55% | -1404.37% | -1.12% |
| low_demand | PROPOSED-STACKELBERG | -29.43% | -2496.29% | -2.06% |
| low_demand | PROPOSED-CENTRALIZED | -8.56% | -726.02% | -0.44% |
| medium_demand | PROPOSED-FOLLOWERS-ONLY | -97.62% | -742.04% | -7.68% |
| medium_demand | PROPOSED-STACKELBERG | -72.15% | -548.41% | -5.30% |
| medium_demand | PROPOSED-CENTRALIZED | -76.07% | -578.24% | -6.64% |
| peak_demand | PROPOSED-FOLLOWERS-ONLY | 30.80% | 40.00% | 26.81% |
| peak_demand | PROPOSED-STACKELBERG | 26.00% | 33.77% | 25.46% |
| peak_demand | PROPOSED-CENTRALIZED | 34.28% | 44.53% | 31.05% |
| oversaturated_demand | PROPOSED-FOLLOWERS-ONLY | 34.96% | 41.46% | 36.11% |
| oversaturated_demand | PROPOSED-STACKELBERG | 27.53% | 32.65% | 34.99% |
| oversaturated_demand | PROPOSED-CENTRALIZED | 37.31% | 44.25% | 42.20% |
| incident_or_capacity_drop | PROPOSED-FOLLOWERS-ONLY | 25.78% | 34.23% | 22.86% |
| incident_or_capacity_drop | PROPOSED-STACKELBERG | 24.29% | 32.25% | 22.78% |
| incident_or_capacity_drop | PROPOSED-CENTRALIZED | 29.93% | 39.74% | 26.57% |
| capacity_drop | PROPOSED-FOLLOWERS-ONLY | -4.98% | -6.42% | -7.65% |
| capacity_drop | PROPOSED-STACKELBERG | -28.17% | -36.31% | -38.06% |
| capacity_drop | PROPOSED-CENTRALIZED | -16.40% | -21.14% | -19.69% |

Low-demand delay percentages are unstable because the `WU-CD-F` delay denominator is only `4.1 veh-h`; TTT and throughput are more interpretable there.

## Pairwise Spec Comparisons

| Scenario | Comparison | Baseline | Other | TTT Difference | Delay Improvement | Throughput Difference |
|---|---|---|---|---:|---:|---:|
| low_demand | ProposedLeaderValue | PROPOSED-FOLLOWERS-ONLY | PROPOSED-STACKELBERG | -44.769 | -72.58% | -81.8 |
| low_demand | ProposedCentralizationGap | PROPOSED-STACKELBERG | PROPOSED-CENTRALIZED | 72.581 | 68.18% | 140.5 |
| low_demand | FollowerPackageDifference | WU-CD-F | PROPOSED-FOLLOWERS-ONLY | -57.579 | -1404.37% | -97.1 |
| low_demand | FullPackageValue | WU-CD-F | PROPOSED-STACKELBERG | -102.348 | -2496.29% | -178.9 |
| medium_demand | ProposedLeaderValue | PROPOSED-FOLLOWERS-ONLY | PROPOSED-STACKELBERG | 134.966 | 23.00% | 269.6 |
| medium_demand | ProposedCentralizationGap | PROPOSED-STACKELBERG | PROPOSED-CENTRALIZED | -20.789 | -4.60% | -151.9 |
| medium_demand | FollowerPackageDifference | WU-CD-F | PROPOSED-FOLLOWERS-ONLY | -517.225 | -742.04% | -868.1 |
| medium_demand | FullPackageValue | WU-CD-F | PROPOSED-STACKELBERG | -382.259 | -548.41% | -598.5 |
| peak_demand | ProposedLeaderValue | PROPOSED-FOLLOWERS-ONLY | PROPOSED-STACKELBERG | -118.710 | -10.39% | -122.9 |
| peak_demand | ProposedCentralizationGap | PROPOSED-STACKELBERG | PROPOSED-CENTRALIZED | 205.013 | 16.25% | 509.8 |
| peak_demand | FollowerPackageDifference | WU-CD-F | PROPOSED-FOLLOWERS-ONLY | 761.989 | 40.00% | 2441.6 |
| peak_demand | FullPackageValue | WU-CD-F | PROPOSED-STACKELBERG | 643.279 | 33.77% | 2318.7 |
| oversaturated_demand | ProposedLeaderValue | PROPOSED-FOLLOWERS-ONLY | PROPOSED-STACKELBERG | -333.159 | -15.06% | -98.9 |
| oversaturated_demand | ProposedCentralizationGap | PROPOSED-STACKELBERG | PROPOSED-CENTRALIZED | 438.341 | 17.22% | 634.6 |
| oversaturated_demand | FollowerPackageDifference | WU-CD-F | PROPOSED-FOLLOWERS-ONLY | 1567.360 | 41.46% | 3175.7 |
| oversaturated_demand | FullPackageValue | WU-CD-F | PROPOSED-STACKELBERG | 1234.201 | 32.65% | 3076.8 |
| incident_or_capacity_drop | ProposedLeaderValue | PROPOSED-FOLLOWERS-ONLY | PROPOSED-STACKELBERG | -33.093 | -3.01% | -7.1 |
| incident_or_capacity_drop | ProposedCentralizationGap | PROPOSED-STACKELBERG | PROPOSED-CENTRALIZED | 125.266 | 11.06% | 347.0 |
| incident_or_capacity_drop | FollowerPackageDifference | WU-CD-F | PROPOSED-FOLLOWERS-ONLY | 571.960 | 34.23% | 2091.7 |
| incident_or_capacity_drop | FullPackageValue | WU-CD-F | PROPOSED-STACKELBERG | 538.867 | 32.25% | 2084.6 |
| capacity_drop | ProposedLeaderValue | PROPOSED-FOLLOWERS-ONLY | PROPOSED-STACKELBERG | -1858.088 | -28.09% | -3817.8 |
| capacity_drop | ProposedCentralizationGap | PROPOSED-STACKELBERG | PROPOSED-CENTRALIZED | 942.610 | 11.13% | 2306.2 |
| capacity_drop | FollowerPackageDifference | WU-CD-F | PROPOSED-FOLLOWERS-ONLY | -398.792 | -6.42% | -960.1 |
| capacity_drop | FullPackageValue | WU-CD-F | PROPOSED-STACKELBERG | -2256.880 | -36.31% | -4777.9 |

## Interpretation

- `peak_demand`, `oversaturated_demand`, and `incident_or_capacity_drop`: proposed controllers improve substantially over `WU-CD-F`; `PROPOSED-CENTRALIZED` is best by TTT.
- `low_demand` and `medium_demand`: `WU-CD-F` is best by TTT. Under light/moderate demand, the proposed control actions appear to add unnecessary restriction or queueing.
- `capacity_drop`: `WU-CD-F` is best. `PROPOSED-STACKELBERG` is worst, with lower throughput and higher terminal vehicles. This scenario should be treated as a failure case for the current proposed Stackelberg implementation.
- `PROPOSED-STACKELBERG` is not consistently better than `PROPOSED-FOLLOWERS-ONLY`; the Leader/allocation layer helps in `medium_demand` but hurts in `low`, `peak`, `oversaturated`, `incident`, and especially `capacity_drop`.

## Caveats

- The run uses 3600s horizon, not the default 7200s.
- This is not a no-control baseline table.
- Centralized results are numerical references under current random-search budget, not guaranteed global optima.
- Full acceptance is not claimed because the proposed controller does not dominate across scenarios and fails the capacity-drop stress case.
