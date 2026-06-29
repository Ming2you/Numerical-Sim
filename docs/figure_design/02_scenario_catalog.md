# Scenario Catalog

This file is the flexible scenario registry for plotting. Update this file when
`src/config/scenarios.yaml` changes. Other figure chapters should not hard-code
scenario names or assume a fixed number of scenarios.

## Registry Principle

Each active scenario should be described by:

```text
scenario_id
display_name
demand_level_tag
stress_tags
event_windows
main_question
caption_note
```

Suggested tags:

- `low`
- `medium`
- `peak`
- `incident`
- `surge`
- `spatial-skew`
- `urban-heavy`
- `freeway-heavy`
- `onramp-risk`
- `offramp-risk`
- `spillback-risk`
- `capacity-drop-risk`

Figures should select or annotate scenarios by tags. For example, incident
figures should find scenarios tagged `incident`, not a specific scenario name.

## Current Active Scenario Snapshot

This snapshot reflects the current canonical six-scenario direction. If the
scenario list changes, update only this table and the notes below.

| Scenario ID | Display name | Tags | Main question |
|---|---|---|---|
| `low_demand` | Low demand | `low`, `baseline` | Does the controller avoid unnecessary intervention under light demand? |
| `medium_demand` | Medium demand | `medium`, `baseline` | Does control improve a controllable but not fully saturated case? |
| `peak_demand` | Peak demand | `peak`, `spillback-risk`, `capacity-drop-risk` | Does control mitigate heavy congestion and storage pressure? |
| `medium_incident_east` | Medium demand with eastbound incident | `medium`, `incident`, `capacity-drop-risk` | Does VSL/RM/signal coordination respond to a directional bottleneck? |
| `medium_urban_west_skew` | Medium demand with west-heavy urban entries | `medium`, `spatial-skew`, `urban-heavy` | Does coordination handle asymmetric urban demand without hiding queues? |
| `medium_surge` | Medium demand with temporary surge | `medium`, `surge`, `spillback-risk` | Does the controller recover after a temporary demand shock? |

## Historical Or Focus Figure Sets

Some existing presentation figures were generated from a frozen 2026-06-23 focus
set rather than the current canonical six-scenario registry:

| Historical ID | Display name in figures | Suggested tags |
|---|---|---|
| `medium_demand` | Median | `medium`, `baseline` |
| `peak_demand` | Peak | `peak`, `spillback-risk`, `capacity-drop-risk` |
| `skew_peak` | Peak skew | `peak`, `spatial-skew`, `urban-heavy` |
| `incident_or_capacity_drop` | Incident | `incident`, `capacity-drop-risk`, `spillback-risk` |

For such figure sets, read the scenario list from the figure manifest or output
directory and map each scenario to tags. Do not rename historical figures unless
the source runs are regenerated.

## Demand Topology Figure Convention

Scenario-demand overview figures should place exogenous demand on the mixed
network topology:

- urban boundary entries near their boundary intersection;
- freeway upstream entries at the first freeway boundary segment;
- ramp-bound demand near the upstream urban intersection feeding the ramp, not
  directly on the physical ramp link.

Use this wording in captions: "values indicate exogenous inflow rates in veh/h
at the plotted demand snapshot." If ramp-bound demand is shown, make clear that
it is a demand stream approaching the ramp through the boundary/intersection
system, not vehicles magically generated on the ramp.

## Event Window Convention

Use event windows from scenario configuration or diagnostics:

```text
scenario_id,event_type,start_sec,end_sec,metadata
```

Examples:

- `incident`: shade the incident period in speed, density, VSL, and bottleneck
  discharge plots.
- `surge`: shade the surge ramp-up and ramp-down period in macro time-series.
- `spillback`: shade diagnosed spillback windows, not merely high queue windows.
- `capacity_binding`: shade intervals where storage, RM, VSL, or green bounds are
  binding.

## Flexible Plotting Rule

Cross-scenario figures should use all active scenarios by default:

```text
for scenario in active_scenarios:
    plot scenario-controller aggregate
```

Mechanism figures should use representative scenarios selected by tags:

```text
incident_figures: scenarios where "incident" in tags
surge_figures: scenarios where "surge" in tags
baseline_mechanism_figures: one medium or peak scenario
```

If a tag has no active scenario, skip that specialized figure and report the skip
in the figure-generation log.
