# Codex Run Report

## Status

The controller objective and activation diagnostics were updated, then baseline and proposed simulations were rerun with `peak_demand` demand doubled.

Final verdict: **FAIL**.

The proposed controller now activates VSL and ramp metering, but Total TTT is still worse than baseline by **0.33%**, which is below the required **8.00%** improvement threshold.

## What Changed Before This Run

- Added activation-based review requirements to `CLAUDE.md`.
- Added `metering_active_steps` and `vsl_active_steps` to control validation metrics.
- Added congestion-aware `N_UF_star` heuristic candidates for the leader.
- Added leader objective penalties for:
  - excessive `N_UF_star` when freeway density is high
  - overly restrictive `N_UF_star` when ramp queues are high
- Relaxed VSL activation to use `90 km/h` rather than aggressive `80 km/h` in ordinary congestion.

## Why `N_UF_star` Previously Stayed at 6000

`N_UF_star` is selected by the leader from candidate values. Before the objective change, the leader objective mainly saw:

- lower ramp metering target -> larger ramp queues -> higher TTT
- full ramp metering target -> no ramp queue penalty

The simplified freeway model did not give enough objective credit for reducing freeway inflow under congestion. Therefore, `N_UF_star = 6000`, equal to total ramp capacity, was repeatedly selected. In that state, ramp metering had no practical meaning because all ramps were effectively fully open.

The revised leader objective now includes congestion-aware penalties and heuristic candidates around a density/queue-based `N_UF_star`, so `N_UF_star` can move below capacity when congestion is high.

## Run Configuration

- Scenario: `peak_demand_2x`
- Demand scaling relative to original `peak_demand`:
  - `urban_scale`: `1.25 -> 2.50`
  - `freeway_scale`: `1.20 -> 2.40`
  - `ramp_scale`: `1.25 -> 2.50`
- Baseline mode: `fixed_signal_fixed_speed`
- Controller mode: `stackelberg_mpc`
- Config: `src/config/default.yaml`
- Scenario config: `outputs/demand_2x_scenarios.yaml`
- Simulation horizon: `7200 s`
- Control interval: `180 s`
- Random seed: `42`
- Output directory: `outputs/codex_run_peak_demand_2x_objective_v6`

## Command Run

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m experiments.run_experiment --config src/config/default.yaml --scenarios-config outputs/demand_2x_scenarios.yaml --scenario peak_demand_2x --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --output outputs/codex_run_peak_demand_2x_objective_v6
```

## Main Metric Result

| Metric | Baseline | Proposed | Improvement | Pass |
|---|---:|---:|---:|---:|
| Total TTT | 17203.570 | 17261.157 | -0.33% | No |
| Freeway TTT | 2730.566 | 2788.152 | -2.11% | No |
| Urban TTT | 14473.005 | 14473.005 | 0.00% | No |

The required improvement is `>= 8.00%`; the observed result is `-0.3347%`.

## Control Activation

| Control | Active Steps | Evidence |
|---|---:|---|
| Ramp metering | 2 / 40 | `N_UF_star` selected values: `5325.738`, `5935.655`, `6000.000` |
| VSL | 39 / 40 | minimum VSL was `90 km/h` on both freeway directions |

Ramp metering did activate materially in the early part of the run:

- min R1 metering: `1189.536 veh/h`
- min R2 metering: `1257.796 veh/h`
- min R3 metering: `1378.407 veh/h`
- min R4 metering: `1500.000 veh/h`

So the latest failure is **not** because controls never activate. It is because the activated controls do not yet produce a positive Total TTT response in the simplified model.

## Boundary Queue Balancing

| Boundary Metric | Baseline | Proposed | Change | Pass |
|---|---:|---:|---:|---:|
| CV_boundary | 0.1124 | 0.1106 | 1.56% improvement | Partial |
| MaxMin_boundary | 797.989 | 787.624 | Reduced | Partial |
| OverflowRatio_boundary | 1.000 | 1.000 | No improvement | No |
| Net inflow tracking error | 0.000 | 264.595 | Worse | No |

Boundary queue dispersion improved slightly by CV, but boundary validation does **not** pass because overflow ratio remained at `1.0` and net inflow tracking error exceeded `eps_U = 100`.

## Control Validation Summary

| Control | Pass | Key Result |
|---|---:|---|
| Ramp metering | No | active steps = 2, mean total metering error = 4.114, max violation = 130.000, ramp queue overflow duration = 27 |
| VSL | Yes | active steps = 39, feasible rate = 1.000, smoothness violations = 0 |
| Green time allocation | Yes | cycle sum error = 0, min/max violations = 0 |
| Offset control | Yes | range violations = 0, smoothness violations = 0 |
| Boundary allocation | No | net inflow tracking error = 264.595 |

## Interpretation

The objective update fixed the earlier non-activation problem:

- `N_UF_star` is no longer always equal to total ramp capacity.
- Ramp metering activates in early congested steps.
- VSL activates for most congested steps.

However, Total TTT still does not improve. The proposed controller increases freeway TTT by about `57.587 veh*h`, while urban TTT is unchanged. This suggests the simplified model still does not reward freeway inflow control enough to offset ramp queue and speed-control effects.

The next issue is therefore not "controls are off"; it is "controls are on, but the plant/objective coupling is not yet producing useful system-level benefit."

## Diagnostics

Detected failure modes:

- `main_improvement_below_target`
- `ramp_metering_or_queue_validation_failed`
- `boundary_queue_balance_failed`

Dominant failure mode:

- `main_improvement_below_target`

Recommended next modifications:

- Strengthen the coupling between ramp metering and downstream freeway density/speed recovery.
- Add explicit ramp queue overflow penalty to the leader objective, not only follower objective.
- Revisit the simplified VSL model so VSL can reduce density exceedance or speed-drop cost instead of only capping desired speed.
- Strengthen the coupling between green allocation, boundary discharge, and urban TTT.
- Recheck whether the baseline is too permissive under oversaturated demand.

## Comparison Across Runs

| Run | Baseline Total TTT | Proposed Total TTT | Improvement | Activation Summary |
|---|---:|---:|---:|---|
| Original `peak_demand` before objective update | 5888.578 | 5886.190 | 0.04% | weak/no practical activation |
| `peak_demand_2x` before objective update | 17203.570 | 17203.570 | 0.00% | VSL inactive, ramp metering effectively full open |
| `peak_demand_2x` after objective update | 17203.570 | 17261.157 | -0.33% | VSL active 39/40, ramp metering active 2/40 |

## Output Artifacts

- `outputs/codex_run_peak_demand_2x_objective_v6/report.md`
- `outputs/codex_run_peak_demand_2x_objective_v6/attempt_0/metrics_summary.json`
- `outputs/codex_run_peak_demand_2x_objective_v6/attempt_0/diagnostics.json`
- `outputs/codex_run_peak_demand_2x_objective_v6/attempt_0/baseline/run_log.csv`
- `outputs/codex_run_peak_demand_2x_objective_v6/attempt_0/proposed/run_log.csv`
- `outputs/codex_run_peak_demand_2x_objective_v6/attempt_0/proposed/control_timeseries.csv`
- `outputs/codex_run_peak_demand_2x_objective_v6/attempt_0/proposed/state_timeseries.csv`

## Conclusion

The latest controller version makes `N_UF_star` meaningful enough to activate ramp metering and VSL, but it still fails the 8% Total TTT criterion. The next development step should improve the plant/objective coupling so activated controls can actually reduce freeway density exceedance, ramp overflow, or urban accumulation rather than merely changing feasible control values.

