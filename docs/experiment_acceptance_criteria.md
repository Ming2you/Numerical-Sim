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

- Boundary CV is reduced or not worsened relative to baseline.
- Boundary overflow ratio is reduced or not worsened.
- Net inflow tracking error is within `eps_U`, or infeasibility is explicitly logged.

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

