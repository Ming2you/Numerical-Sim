# Computation Cost Figures

## Purpose

Show whether each controller can run within a rolling-horizon control budget, and
explain where computation time is spent.

## Required Metrics

| Metric | Source |
|---|---|
| wall time per control step | `progress_summary.csv` |
| controller compute time per step | `progress_summary.csv` |
| total wall time | summary or summed progress |
| Nash iteration count | `decision_diagnostics.csv` when available |
| leader candidate count | `decision_progress.csv` or diagnostics |
| fallback selection rate | `progress_summary.csv` |
| process/thread backend | command/config metadata |
| leader search mode and evaluation budget | command/config metadata |

## Fig. 6A. Runtime Per Control Step

Bar, boxplot, or violin plot:

- x-axis: active scenario;
- hue: controller;
- y-axis: mean runtime or compute time per control step (s);
- horizontal line: control interval, currently 180 s when the experiment uses
  180 s rolling-horizon updates.

For the current 3600 s focus figures, compute step cost as
`computation_time_sec / number_of_control_steps` where
`number_of_control_steps = horizon_sec / control_interval_sec`. The reference
line is not a target to optimize against; it is the real-time feasibility budget.

## Fig. 6B. Candidate Evaluation Budget

Bar or line plot:

- leader candidate evaluations per step;
- follower grid evaluations per step;
- Nash iterations per step.

Use separate panels if scales differ.

## Fig. 6C. Performance Vs Computation Trade-Off

Scatter plot:

- x-axis: mean compute time per step;
- y-axis: total TTT improvement or average travel time improvement;
- marker: controller;
- color: scenario tag.

This is the key figure for comparing PFO/P-Stack against WU and centralized
reference.

## Current Presentation Interpretation

Use this wording for the current 2026-06-23 effect-oriented figures:

- WU-CD-F and PFO are comfortably below the 180 s control interval.
- P-Stack is much more expensive because it evaluates leader targets and follower
  responses, but it remains below the 180 s online decision budget in these
  runs.
- P-Stack's computation cost is therefore feasible for this simplified numerical
  simulator, but scalability remains a practical trade-off before microscopic or
  larger-network deployment.

## Fig. 6D. Budget Sensitivity

For Stackelberg leader and centralized search, plot:

- evaluation budget or top-k setting on x-axis;
- TTT improvement, fallback rate, and compute time on y-panels.

Do not compare budget settings across different scenarios unless the caption
explicitly says it is a robustness sweep.
