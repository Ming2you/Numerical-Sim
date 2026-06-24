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

Boxplot or violin plot:

- x-axis: controller;
- y-axis: runtime per control step (s);
- color: scenario or scenario tag;
- horizontal line: real-time threshold if defined.

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

## Fig. 6D. Budget Sensitivity

For Stackelberg leader and centralized search, plot:

- evaluation budget or top-k setting on x-axis;
- TTT improvement, fallback rate, and compute time on y-panels.

Do not compare budget settings across different scenarios unless the caption
explicitly says it is a robustness sweep.
