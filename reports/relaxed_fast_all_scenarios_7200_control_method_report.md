# Relaxed-Fast 7200s Four-Controller Scenario Report

Date: 2026-06-18

Status: historical/superseded. This report is preserved as provenance for the
last relaxed-fast all-scenario run. The active code path no longer supports
`relaxed_fast_mode`; subsequent experiments should use
`relaxed_quantized_controls=true` with the full allocation module unless a new
validated shortcut is introduced.

Output root:

```text
outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1
```

Mode:

- `relaxed_fast_mode = true`
- `relaxed_quantized_controls = true`
- `leader_candidate_count = 5`
- `max_nash_iter = 3`
- `optimizer_maxiter = 16`
- `optimizer_n_starts = 1`
- `freeway_prediction_horizon_steps = 3`
- Horizon: `7200 s`

Important interpretation: `relaxed_fast_mode` is not a MILP solve. It uses
continuous or heuristic targets, then quantizes/repairs to feasible controls
before applying them to the plant. It also uses the smaller screening budgets
above, so this should be treated as the likely fast/default screening mode, not
as exact full optimization.

## Output Files

Primary tables:

- `outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/all_controller_summary.csv`
- `outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/all_no_control_summary.csv`
- `outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/summary_with_no_control.csv`
- `outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/activation_summary.csv`
- `outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/representative_timeseries.csv`

Visual evidence:

- `outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/charts/ttt_improvement_vs_no_control_heatmap.svg`
- `outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/charts/peak_freeway_vehicles_trajectory.svg`
- `outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/charts/peak_control_activation_rates.svg`
- `outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/charts/peak_metering_flow_mediator.svg`
- `outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/charts/capacity_drop_ttt_overcontrol.svg`

## Main Performance Table

Total TTT, veh-h:

| scenario | no-control | WU | P-FO | P-Stack | P-Cent | best incl. no-control | best 4-controller |
|---|---:|---:|---:|---:|---:|---|---|
| low_demand | 695.7 | 709.1 | 1139.9 | 1285.8 | 871.5 | No control | WU |
| medium_demand | 1944.0 | 1991.2 | 4042.8 | 3444.8 | 3633.2 | No control | WU |
| peak_demand | 11659.6 | 11645.9 | 7411.6 | 8608.1 | 6369.1 | P-Cent | P-Cent |
| oversaturated_demand | 19734.2 | 19739.1 | 13365.8 | 17978.8 | 15863.5 | P-FO | P-FO |
| incident_or_capacity_drop | 10473.2 | 10447.0 | 7159.4 | 8412.6 | 5826.2 | P-Cent | P-Cent |
| capacity_drop | 31794.5 | 33593.1 | 34867.8 | 40022.5 | 35096.9 | No control | WU |

Improvement versus same-scenario no-control:

| scenario | WU | P-FO | P-Stack | P-Cent |
|---|---:|---:|---:|---:|
| low_demand | -1.92% | -63.85% | -84.81% | -25.27% |
| medium_demand | -2.43% | -107.97% | -77.20% | -86.90% |
| peak_demand | 0.12% | 36.43% | 26.17% | 45.37% |
| oversaturated_demand | -0.03% | 32.27% | 8.89% | 19.61% |
| incident_or_capacity_drop | 0.25% | 31.64% | 19.68% | 44.37% |
| capacity_drop | -5.66% | -9.67% | -25.88% | -10.39% |

## Controller Characteristics

### WU-CD-F

In relaxed-fast mode, `WU-CD-F` behaves almost like a green-only controller in
these runs:

- Green active rate: `100%` in all scenarios.
- Ramp metering active rate: `0%`.
- Offset active rate: `0%`.
- Allocation active rate: `0%`.
- VSL active rate: `0%` in these relaxed-fast runs.

This is authority-consistent: Wu has green/VSL authority only, and the relaxed
VSL shortcut selected neutral max VSL in all scenarios. Because no ramp
metering or offset/allocation is available, Wu cannot meaningfully suppress
freeway accumulation in peak or incident regimes. In low/medium/capacity-drop,
Wu is the best among the four active controllers, but no-control is still
better; this means Wu is "least harmful", not actually beneficial, in those
regimes.

### PROPOSED-FOLLOWERS-ONLY

`PROPOSED-FOLLOWERS-ONLY` is the strongest distributed fast controller in heavy
but controllable demand. It uses ramp metering, green adjustment, and offsets
without the allocation/leader layer.

Best evidence: `oversaturated_demand`

- Total TTT improves by `32.27%` versus no-control.
- Ramp metering active rate: `100%`.
- Ramp restriction ratio: `0.5988`.
- Mean applied metering flow: `2404 veh/h` versus potential no-meter flow
  `4829 veh/h`.
- Mean freeway vehicles fall from Wu-like/no-control deep accumulation to
  `1341 veh`.
- Throughput rises from `7431 veh/h` no-control to `10503 veh/h`.

This is consistent with ramp metering literature: when freeway demand is
recoverably oversaturated, restricting ramp inflow protects mainline operation
and reduces downstream accumulation. The cost is ramp/urban queueing, but in
this scenario the throughput and total TTT benefit dominate.

Failure evidence: `low_demand` and `medium_demand`

- Ramp metering is active `100%` even when no-control is better.
- In `medium_demand`, P-FO cuts potential no-meter flow by about half
  (`5948 -> 2969 veh/h`) and removes density exceedance, but total TTT worsens
  from `1944` to `4043 veh-h`.
- This is an over-control signature: freeway state improves, but urban/ramp
  holding cost is larger than the freeway benefit.

### PROPOSED-STACKELBERG

`PROPOSED-STACKELBERG` activates the full proposed package:

- Ramp metering active rate: usually `100%`.
- Offset active rate: usually `100%`.
- Allocation active rate: `100%`.
- Leader targets active in all intervals.

However, under current relaxed-fast settings it is not consistently better than
P-FO. In peak/oversaturated/incident, it lowers freeway accumulation but often
adds too much urban cost or loses throughput.

Representative evidence:

- `peak_demand`: freeway TTT is lower than P-FO (`984` vs `1564 veh-h`), but
  urban TTT is higher (`7624` vs `5848 veh-h`), so total TTT is worse than P-FO.
- `capacity_drop`: ramp restriction ratio is `0.8441`, VSL active rate is
  `97.5%`, and allocation is active `100%`; throughput collapses to
  `7063 veh/h`, making it the worst controller.

Interpretation: the Stackelberg layer currently has a credible mechanism, but
the relaxed-fast leader/allocation response is too aggressive in several
regimes. It can protect freeway accumulation, but it has not yet learned when
the urban/ramp queue cost dominates.

### PROPOSED-CENTRALIZED

`PROPOSED-CENTRALIZED` is best in `peak_demand` and
`incident_or_capacity_drop`.

Best evidence: `peak_demand`

- Total TTT improves by `45.37%`.
- Throughput rises from `7936` to `11304 veh/h`.
- Terminal vehicles drop from `13488` to `6754`.
- Freeway TTT drops from `4900` to `338 veh-h`.
- Activation pattern: allocation `100%`, offset `100%`, green `95%`, VSL `0%`,
  explicit ramp metering `0%`.

This is not a ramp-metering story in the explicit actuator trace. It is a
network-coordination story: allocation/green/offset decisions keep freeway
vehicles very low while maintaining high throughput. This is consistent with
integrated control literature where coordinated arterial-freeway control can
outperform isolated local control under peak and incident stress.

Failure evidence: `capacity_drop`

- Freeway TTT improves versus no-control (`5734 -> 4143 veh-h`), but urban TTT
  worsens (`26060 -> 30954 veh-h`).
- Total TTT worsens by `10.39%`.

Interpretation: centralized control is strong when the capacity/receiving
constraints are still manageable, but it can still transfer cost to the urban
side in a pure capacity-drop or high-transfer regime.

## Control-Method Evidence

### Ramp Metering

Representative good case: `oversaturated_demand`, P-FO.

The controller activates ramp metering on every interval and reduces mean
applied freeway-entry flow from a potential `4829 veh/h` to `2404 veh/h`.
Freeway accumulation and density exceedance fall enough that total TTT improves
by `32.27%` and throughput improves by about `3072 veh/h` versus no-control.

This matches the standard ramp-metering mechanism: protect the mainline by
holding ramp demand when receiving capacity is stressed.

Representative bad case: `medium_demand`, P-FO.

Metering is also active `100%`, but no-control is best. The freeway side is
protected, yet the total system pays too much in urban/ramp storage. This is a
reasonable warning that the relaxed-fast follower should include a stronger
"do not meter unless needed" gate in lower demand.

### VSL

In these relaxed-fast runs, VSL is not the main source of improvement:

- `WU-CD-F`: VSL active `0%` in every scenario.
- `P-FO`: VSL active only in `capacity_drop` (`95%`), where total TTT worsens.
- `P-Stack`: VSL active in `capacity_drop` (`97.5%`), where total TTT worsens.
- `P-Cent`: VSL active in `oversaturated_demand` (`77.5%`), but P-FO is still
  better.

This is consistent with the earlier VSL investigation: VSL helps only when it
can meter an upstream free-flow segment before a bottleneck. In deep
oversaturation or pure capacity-drop cases, lowering VSL can become inert or
reduce throughput.

### Green Timing

Green timing is active in all non-no-control controllers. Wu uses this as its
main actuator, which explains why Wu can slightly change urban/freeway split
but cannot solve peak freeway accumulation. Proposed controllers combine green
changes with offset, allocation, and sometimes metering.

### Offset

Offset is active in all proposed runs and inactive in Wu. In `peak_demand` and
`incident_or_capacity_drop`, centralized offset/allocation/green coordination
correlates with large throughput gains and low terminal vehicles. However,
arrival-on-green or stop-rate metrics are not directly logged, so offset should
be presented as part of the coordinated package rather than as an isolated
causal effect.

### Allocation / Leader

Allocation is active in Stackelberg and centralized runs, not in Wu or P-FO.
The evidence is mixed:

- Centralized allocation is strongly beneficial in peak and incident scenarios.
- Stackelberg allocation/leader is currently too aggressive in relaxed-fast
  mode and often underperforms P-FO.

This supports the research framing that coordination is valuable, but the
current relaxed-fast Stackelberg implementation still needs better regime
gating or objective scaling to avoid urban cost transfer.

## Subagent Interpretation Review

Two subagent-style checks were used:

1. An evidence-framework pass identified the expected activation logic:
   ramp metering should respond to receiving/density stress, VSL should meter
   upstream of bottlenecks, green/allocation should respond to queue and
   storage imbalance, and offset evidence needs corridor progression metrics.
2. A result-interpretation pass summarized the all-scenario output.

Codex review correction:

- The interpretation pass labeled Wu as "best" in low/medium/capacity-drop.
  That is true only among the four active controllers. When no-control is
  included, no-control is best in those scenarios.
- Therefore the correct statement is:
  - Low/medium/capacity-drop: active control is not beneficial in the current
    relaxed-fast configuration; Wu is merely least harmful among active
    controllers.
  - Peak/oversaturated/incident: proposed control authority is beneficial, with
    P-Cent best in peak/incident and P-FO best in oversaturated.

## Current Verdict

Relaxed-fast mode gives usable computation cost and clear regime separation,
but it is not a final controller-quality proof:

- Strong positive cases:
  - `peak_demand`: P-Cent, P-FO.
  - `oversaturated_demand`: P-FO.
  - `incident_or_capacity_drop`: P-Cent, P-FO.
- Over-control cases:
  - `low_demand`, `medium_demand`, `capacity_drop`.
- Stackelberg concern:
  - The full Stackelberg package is active, but under relaxed-fast it often
    protects freeway states by transferring too much cost to urban/ramp queues.

Next technical target:

- Add or tune regime-aware activation gates for relaxed-fast metering and
  allocation/leader response, especially for low/medium and pure capacity-drop
  scenarios.
