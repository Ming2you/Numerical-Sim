# Plotting Data Schema

This chapter defines the normalized data frames used by the figure scripts.
Scripts may read repository-native output files, but plots should be generated
from these normalized schemas when possible.

## Source Files

Typical closed-loop output directories contain:

```text
run_log.csv
progress_summary.csv
control_timeseries.csv
state_timeseries.csv
decision_diagnostics.csv
decision_progress.csv
metrics_raw.json
```

Comparison runners may additionally write:

```text
all_controller_summary.csv
all_no_control_summary.csv
analysis/summary_with_no_control.csv
analysis/controller_vs_no_control.csv
summary.json
```

## `df_summary`

Scenario-controller aggregate results.

```text
scenario
scenario_display_name
scenario_tags
controller_id
controller_label
seed
horizon_sec
total_ttt
urban_ttt
freeway_ttt
total_delay
average_travel_time
completed_vehicles
completed_vehicle_gain_vs_no_control
throughput_veh_h
terminal_total_vehicles
terminal_vehicles_vs_no_control
terminal_vehicle_reduction_vs_no_control
boundary_queue_mean
boundary_queue_max
onramp_queue_mean
onramp_queue_max
offramp_queue_mean
offramp_queue_max
spillback_duration_onramp_min
spillback_duration_offramp_min
spillback_duration_boundary_min
runtime_mean_sec
runtime_total_sec
controller_compute_total_sec
nash_iterations_mean
leader_candidate_count_mean
```

Use absolute completed vehicles and absolute terminal vehicles for the main
network-effect figure when no-control is included. Gain/reduction fields are
allowed as companion diagnostics, but do not plot a "gain" bar for no-control
unless it is explicitly zero and the axis label says so.

## `df_timeseries`

Control-step time-series.

```text
scenario
controller_id
seed
step
time_sec
interval_total_ttt
interval_urban_ttt
interval_freeway_ttt
cumulative_total_ttt
cumulative_urban_ttt
cumulative_freeway_ttt
boundary_queue
onramp_queue
offramp_queue
urban_accumulation
urban_storage_headroom
freeway_density_mean
freeway_density_max
freeway_speed_mean
terminal_total_vehicles
controller_compute_time_sec
control_interval_sec
```

## `df_controls`

Control actions and activation flags.

```text
scenario
controller_id
seed
step
time_sec
N_P_star
N_UF_star
ramp_id
metering_rate
metering_activation
segment_id
vsl_value
vsl_activation
intersection_id
movement_id
green_time
green_ratio
offset
offset_change
```

## `df_ramp`

Ramp-level mechanism data.

```text
scenario
controller_id
seed
step
time_sec
ramp_id
metering_rate
ramp_queue
ramp_discharge
ramp_storage_capacity
adjacent_urban_queue
freeway_density_near_ramp
freeway_speed_near_ramp
is_metering_active
is_spillback
```

Ramp-level figures should retain directional ramp IDs such as `R_D_E` and
`R_F_E` instead of averaging all ramps by default. For on-ramp mechanism figures,
keep upstream and downstream ramp metering rates and ramp queues in separate
panels or facets when the scenario is directional.

## `df_vsl`

Freeway segment and VSL data.

```text
scenario
controller_id
seed
step
time_sec
segment_id
direction
vsl_value
speed
density
flow
effective_lanes
is_incident_segment
is_vsl_active
```

## `df_signal`

Urban movement and signal data.

```text
scenario
controller_id
seed
step
time_sec
intersection_id
movement_id
movement_group
green_time
green_ratio
queue_length
queue_lag1
saturation_flow
actual_discharge
is_green_min_binding
is_green_max_binding
```

## `df_game`

Follower game and leader-response diagnostics.

```text
scenario
controller_id
seed
step
time_sec
nash_iteration
urban_objective
freeway_objective
total_objective
nash_gap
strategy_change_norm
urban_strategy_norm
freeway_strategy_norm
leader_selected_objective
leader_selected_N_P_star
leader_selected_N_UF_star
leader_selected_stage
leader_fallback_guard_selected
```

## `df_candidate_targets`

Leader candidate evaluation data.

```text
scenario
controller_id
seed
step
time_sec
stage
candidate_index
N_P_star
N_UF_star
objective
follower_ttt
mfd_storage_penalty
mfd_storage_excess_veh
is_feasible
is_selected
best_objective_so_far
```

## `df_topology_demand`

Scenario-level demand snapshot used for topology maps.

```text
scenario
scenario_display_name
time_sec
entity_type              # urban_boundary, freeway_entry, ramp_bound
entity_id
direction
node_id
x
y
demand_veh_h
scenario_tags
note
```

Topology maps should use this table instead of embedding demand numbers in the
plotting code whenever possible.
