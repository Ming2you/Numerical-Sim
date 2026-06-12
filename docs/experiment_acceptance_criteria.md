# Experiment Acceptance Criteria

## Main Metric

The default main metric is:

```text
Total TTT = Freeway TTT + Urban TTT
```

The proposed controller passes the main criterion only if:

```text
ImprovementRate >= min_improvement_pct
```

The default threshold is 8%.

For lower-is-better metrics:

```text
ImprovementRate(%) = 100 * (Metric_baseline - Metric_proposed) / max(Metric_baseline, eps)
```

For higher-is-better metrics:

```text
ImprovementRate(%) = 100 * (Metric_proposed - Metric_baseline) / max(abs(Metric_baseline), eps)
```

## Required Control Validations

### Ramp Metering

Pass conditions:

- Mean total metering error is within `eps_F`, or infeasibility is explicitly logged.
  - `N_UF_star` is a ceiling-type target scored asymmetrically at the control-interval
    level: (a) releasing more than the target is an over-release violation; (b) releasing
    less counts only to the extent that the ramp reservoir actually accumulated
    (cycle-aligned `w_r` growth, or the reservoir pegged at capacity). Releasing less
    than `N_UF_star` because demand is insufficient is correct behavior, not a tracking
    failure; the raw-target gap is reported separately via `metering_target_infeasible`.
    Queue growth is measured between cycle-aligned samples because the signal-phase
    plant makes `w_r` oscillate within each cycle (per-`T_f` rectified differences
    would misread pulse buffering as withheld vehicles).
- Ramp queue overflow duration is within tolerance.
- Metering rates are nonnegative and do not exceed ramp capacities.

### Variable Speed Limit

Pass conditions:

- Every VSL value belongs to the configured discrete VSL set.
- VSL changes do not exceed `max_vsl_step`.
- Controlled density exceedance does not exceed baseline density exceedance unless justified.

### Green Time Allocation

Pass conditions:

- Green time plus lost time equals cycle length.
- Green times respect min/max bounds.
- Queue overflow does not increase relative to baseline.

### Offset Control

Pass conditions:

- Offsets are in `[0, cycle_length)`.
- Offset changes respect `max_offset_step`, accounting for signal-cycle wraparound.
- Corridor delay does not materially increase relative to baseline.

### Inflow-Outflow Allocation

Pass conditions:

- Boundary-element balance indices satisfy `B_in <= eps_balance` and `B_out <= eps_balance`.
  - Densities are aggregated per physical boundary element (gate in-link, off-ramp,
    on-ramp), not per turning movement. With grid routing each gate splits into 3-4
    beta-share movements whose individually-empty queues dominate a movement-level
    index regardless of controller quality; element-level aggregation preserves the
    metric's original dimensionality and intent (fairness across entry/exit points).
  - `B_in` covers external entry gates (`boundary_in`) only. Off-ramp discharge queues
    are transfer queues that are intentionally priority-served to protect the freeway
    (their densities are structurally near zero), so mixing them with gates lets
    structural zeros dominate the index instead of measuring gate fairness.
  - `B_out` covers controllable outflow elements only (`on_ramp`). Free-discharge
    boundary-out movements are excluded: a free sink must always be served at maximum
    rate, so equalizing its densities is not a well-posed control objective.
  - `B_in`/`B_out` are time-aggregated over controllable (non-degenerate) intervals of
    the run, not over the final-state snapshot, and weighted by the queued load of the
    interval. The balance index is scale-invariant, so noise-level leftover queues in
    lightly loaded intervals would otherwise dominate the average; fairness matters in
    proportion to how many vehicles are actually waiting. The run is judged degenerate
    only if the controllable-interval fraction is below
    `boundary_controllable_min_fraction`.
- Boundary overflow ratio is reduced or not worsened. Boundary CV is descriptive only.
- Net inflow tracking error is within `eps_U`, or infeasibility is explicitly logged.
  - The realized net inflow is `d(N_P)/dt` measured over the `N_P_feedback_horizon_h`
    window (matching the feedback law's timescale), not the gross boundary service
    flow. The gross-flow figure remains available as a descriptive diagnostic.

## Required Output Files

Every full run should save:

- `config_used.yaml`
- `metrics_summary.json`
- `diagnostics.json`
- `run_log.csv`
- `control_timeseries.csv`
- `state_timeseries.csv`
- `plots/`
- `report.md`

## Failure Handling

If the controller fails:

1. Diagnose likely causes.
2. Modify controller or configuration parameters.
3. Rerun the full simulation.
4. Preserve every failed attempt.
5. State PASS or FAIL explicitly in the report.

