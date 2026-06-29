# Congestion Transfer Figures

## Purpose

Show whether control reduces or merely relocates congestion across the
urban-freeway interface.

## Interface Metrics

| Metric | Interpretation |
|---|---|
| On-ramp queue exposure | Cost imposed by ramp metering |
| Off-ramp queue exposure | Urban blockage spilling back to freeway |
| Boundary queue exposure | Demand waiting at the urban perimeter |
| Accepted off-ramp flow ratio | Whether the urban network can receive freeway exits |
| Ramp discharge | Whether metering suppresses or restores freeway inflow |
| Spillback duration | Duration of physically problematic queue states |

## Fig. 2A. Spillback Summary

Create a grouped or stacked grouped bar chart:

- x-axis: active scenarios;
- group: controller;
- stack or panel: on-ramp, off-ramp, boundary spillback duration.

Use zero labels only when they improve readability.

## Fig. 2B. Queue Exposure Summary

Plot queue exposure:

\[
QE = \sum_t Q(t)\Delta t
\]

Use separate panels for:

- on-ramp queue exposure;
- off-ramp queue exposure;
- boundary queue exposure.

## Fig. 2C. Off-Ramp Acceptance Ratio

Definition:

\[
AR_{off} =
\frac{\text{actual accepted off-ramp flow}}
{\text{desired off-ramp outflow}}
\]

Low accepted ratio should be discussed together with urban storage and boundary
queue state.

## Fig. 2D. On-Ramp Mechanism Panel

For representative `peak`, `medium`, or `onramp-risk` scenarios, use aligned
time-series panels:

1. freeway density near ramp;
2. metering rate or actual ramp release;
3. ramp queue;
4. adjacent urban or ramp-feeding movement queue;
5. actual ramp discharge;
6. cumulative total or freeway TTT saved when the panel is used for slides.

Add threshold lines for critical density and ramp storage when configured.

For directional ramp systems, split upstream and downstream ramps instead of
plotting only one network average. The incident presentation figure should show
`D -> FW_E` and `F -> FW_E` metering commands and ramp queues separately.

## Fig. 2E. Off-Ramp Mechanism Panel

For representative `incident`, `peak`, or `offramp-risk` scenarios, use aligned
time-series panels:

1. urban storage headroom;
2. desired off-ramp outflow;
3. accepted off-ramp flow;
4. off-ramp queue;
5. boundary green or outflow-supporting green time;
6. freeway speed or density upstream of the off-ramp.

## Congestion Transfer Index

Optional diagnostic:

\[
CTI_{F \rightarrow U} =
\sum_t I(\rho_F(t) > \rho_F^{crit}) Q_{onramp}(t)\Delta t
\]

\[
CTI_{U \rightarrow F} =
\sum_t I(N_U(t) > N_U^{crit}) Q_{offramp}(t)\Delta t
\]

Use this only if the underlying queue and threshold definitions are documented in
the caption.

## Interpretation Guardrails

Do not conclude that a controller is "hiding vehicles" from ramp queue alone.
Check completed vehicles and terminal vehicles in the same scenario. A controller
can deliberately hold ramp traffic while still improving network performance if
it increases completed vehicles, reduces terminal burden, and reduces both urban
and freeway TTT.

Boundary-balance indices and boundary-queue magnitudes answer different
questions. A balance index can worsen when the remaining queue is unevenly
distributed even though the total queue amount is much lower. Report both when
the fairness claim matters.
