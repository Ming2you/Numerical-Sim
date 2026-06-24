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
2. metering rate;
3. ramp queue;
4. adjacent urban queue;
5. actual ramp discharge.

Add threshold lines for critical density and ramp storage when configured.

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
