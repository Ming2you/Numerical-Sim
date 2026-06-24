# Microscopic Control Behavior Figures

## Purpose

Show how each control actuator responds to traffic state. These figures explain
mechanism, not just aggregate performance.

## Ramp Metering

### RM Summary

Cross-scenario panels:

- average metering rate;
- metering activation duration;
- ramp queue exposure;
- ramp discharge.

### RM Mechanism

Representative time-series panels:

1. freeway density near ramp;
2. metering rate;
3. ramp queue;
4. adjacent urban movement queue;
5. actual ramp discharge.

Scatter diagnostics:

- metering rate vs freeway density;
- metering rate vs ramp queue;
- metering rate vs adjacent urban queue.

## VSL

### VSL Summary

Cross-scenario panels:

- VSL activation duration;
- mean VSL reduction;
- density exceedance duration;
- bottleneck discharge.

### VSL Mechanism

Recommended figures:

- VSL space-time heatmap;
- freeway speed space-time heatmap;
- freeway density space-time heatmap;
- fundamental diagram colored by VSL state.

For incident scenarios, shade the incident period and mark the incident segment.

## Green Time

### Green Summary

Cross-scenario panels:

- average green ratio by movement group;
- green adjustment magnitude;
- binding rate at green minimum and maximum;
- movement discharge or service.

### Green Mechanism

Representative figures:

- movement-level green allocation over time;
- lagged queue vs next-step green time scatter;
- inflow/outflow green ratio vs `N_P_star` or actual net inflow.

Use lagged queue \(Q(t-1)\) for queue-response scatter plots.

## Offset

### Offset Summary

Cross-scenario panels:

- mean absolute offset change;
- offset activation duration;
- corridor throughput;
- cumulative departures.

### Offset Mechanism

Representative figures:

- offset timeline;
- time-space progression diagram;
- cumulative departure curve.

If vehicle trajectories are unavailable, use movement discharge and signal bands
instead of inventing trajectories.

## Activation Interpretation

Activation should be defined consistently:

- RM active when metering rate is below no-metering capacity by a configured
  tolerance.
- VSL active when posted speed is below free-flow speed.
- Green active when split differs from fixed-time baseline beyond a tolerance.
- Offset active when offset differs from fixed-time baseline beyond a tolerance.
