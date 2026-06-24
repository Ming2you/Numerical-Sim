# Macro Performance Figures

## Purpose

Show whether each controller improves whole-network performance under identical
plant, demand, horizon, seed, and metric accounting.

## Required Aggregate Metrics

| Metric | Why it is needed |
|---|---|
| Total TTT | Main network performance measure |
| Urban TTT | Detects freeway-to-urban burden shifting |
| Freeway TTT | Detects freeway protection and capacity-drop response |
| Total delay | Complements TTT with free-flow reference accounting |
| Average travel time | Interprets TTT when throughput differs |
| Completed vehicles or throughput | Detects whether control improves service or hides demand |
| Terminal vehicles | Detects residual storage at the end of simulation |
| Boundary, ramp, and off-ramp queues | Detects congestion transfer |

## Fig. 1A. Total TTT Cross-Scenario Bar Chart

Grouped bar chart:

- x-axis: active scenarios from `02_scenario_catalog.md`;
- y-axis: total TTT (veh-h);
- hue: controller label from `01_controller_catalog.md`;
- annotation: percent change relative to no-control and relative to WU where
  useful.

Do not assume a fixed number of scenarios.

## Fig. 1B. Urban And Freeway TTT Decomposition

Use either:

- two aligned grouped bar panels: urban TTT and freeway TTT; or
- stacked bars only if the visual question is total composition.

Prefer aligned panels because urban and freeway burden shifts are easier to see.

## Fig. 1C. Delay, Average Travel Time, And Throughput

Use three aligned panels:

1. total delay;
2. average travel time;
3. completed vehicles or throughput.

This figure is important when a controller increases throughput while also
increasing raw TTT.

## Fig. 1D. Terminal-State Burden

Grouped bars or dot plots:

- terminal total vehicles;
- terminal urban vehicles;
- terminal freeway vehicles;
- terminal ramp vehicles if available.

Interpret this as residual burden, not as a standalone performance objective.

## Fig. 2. Scenario Time-Series Package

For each active scenario, create aligned time-series panels:

1. interval total TTT;
2. cumulative total TTT;
3. urban TTT;
4. freeway TTT;
5. throughput or departures;
6. terminal or accumulated vehicles.

Use event windows from `02_scenario_catalog.md` for shading. Skip unavailable
event types.
