# Game Coupling Figures

## Purpose

Explain the interaction among distributed followers and the leader-follower
hierarchy. This chapter should be used carefully: only plot game diagnostics that
are actually logged or reproducible from candidate probes.

## Fig. 4A. Nash Iteration Convergence

Aligned panels for representative scenarios:

1. urban follower objective;
2. freeway follower objective;
3. total follower objective;
4. strategy change norm or Nash gap.

Add convergence tolerance lines if configured.

## Fig. 4B. Follower Coupling Matrix

Construct a sensitivity or response matrix:

| Perturbed control | Observed response |
|---|---|
| RM | ramp queue, freeway density, adjacent urban queue |
| VSL | upstream density, speed, bottleneck discharge |
| green time | movement queue, boundary inflow/outflow |
| offset | corridor throughput, stops, urban queues |

Plot as a heatmap after normalizing columns. The caption must state the
normalization.

## Fig. 4C. Best-Response Curves

Use only for low-dimensional probes, such as:

- ramp metering vs ramp-feeding green;
- VSL vs ramp metering;
- inflow green vs outflow green;
- offset vs corridor throughput.

Mark:

- PFO response;
- P-Stack selected response;
- no-control guard candidate if present.

## Fig. 4D. Predicted Objective Vs Realized Plant TTT

Scatter plot:

- x-axis: predicted follower or leader objective;
- y-axis: realized next-step or horizon plant TTT;
- color: scenario or controller;
- marker: selected vs rejected candidate when available.

This figure diagnoses objective fidelity. A weak or inverted relationship means
candidate selection is optimizing a proxy that does not match plant performance.

## Fig. 4E. Local Objective Coverage Audit

Use a table or stacked bars showing which vehicle/queue groups are counted by:

- freeway follower objective;
- urban follower objective;
- leader objective;
- final plant TTT metric.

This is useful when diagnosing hidden sinks, double counting, or uncounted
boundary queues.
