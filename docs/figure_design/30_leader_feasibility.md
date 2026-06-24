# Leader Feasibility Figures

## Purpose

Show what the Stackelberg leader adds beyond PFO. This chapter applies mainly to
`PROPOSED-STACKELBERG`.

The important question is not merely whether P-Stack improves total TTT. The
important question is whether the leader selects feasible macroscopic targets
that produce better follower responses than PFO under the same plant and
constraints.

## Required Diagnostics

| Diagnostic | Source |
|---|---|
| `N_P_star` | `control_timeseries.csv` or `progress_summary.csv` |
| `N_UF_star` | `control_timeseries.csv` or `progress_summary.csv` |
| actual net inflow | `run_log.csv` |
| actual metering release or total ramp flow | `run_log.csv` |
| leader selected objective | `progress_summary.csv`, `decision_diagnostics.csv` |
| candidate objective values | `decision_progress.csv` |
| fallback selected flag | `progress_summary.csv`, `decision_diagnostics.csv` |
| allocation mode | command/config metadata |

## Fig. 3A. Target And Response Time-Series

Aligned panels:

1. `N_P_star` vs actual net inflow;
2. `N_UF_star` vs actual total metering/ramp release;
3. leader selected objective;
4. fallback guard selected flag.

If actual response cannot physically match the target, annotate the binding
constraint or report that the binding constraint is unknown.

## Fig. 3B. Candidate Objective Table Or Dot Plot

For selected control steps, plot leader candidates:

- x-axis: `N_P_star`;
- y-axis: `N_UF_star`;
- color: objective or follower TTT;
- marker: selected, fallback PFO, no-control guard, infeasible.

This is the primary figure for diagnosing why P-Stack selects or fails to select
a non-fallback target.

## Fig. 3C. PFO Fallback Selection Rate

Cross-scenario bar chart:

\[
\text{PFO fallback rate} =
\frac{\# \text{steps where fallback PFO selected}}{\# \text{control steps}}
\]

Interpretation:

- high fallback rate means P-Stack is mostly reproducing PFO;
- low fallback rate means the leader is actively shaping follower responses;
- worse performance with low fallback rate suggests leader objective or
  candidate fidelity issues.

## Fig. 3D. Feasibility And Tracking Error

Two-panel grouped bars:

1. mean absolute net inflow tracking error;
2. mean absolute total metering target tracking error.

Report units in veh or veh/h consistently with the logged variable.

## Fig. 3E. Allocation Mode Comparison

When comparing `direct`, `simplified`, and `pso` allocation modes, use the same
scenario, horizon, seed, fallback setting, and leader search budget.

Show:

- total TTT;
- tracking errors;
- fallback selection rate;
- compute time.
