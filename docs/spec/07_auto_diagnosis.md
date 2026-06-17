# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 7. Auto-Diagnosis and Self-Improvement Loop

### 7.1 Required behavior

After each full experiment run, evaluate acceptance criteria.

If all criteria pass:

1. Save final controls, states, metrics, plots, and report.
2. Mark experiment as `PASS`.

If the main improvement is below 8% or control-specific validation fails:

1. Diagnose likely causes.
2. Modify controller/configuration parameters.
3. Rerun the full simulation.
4. Repeat until:
   - criteria pass, or
   - maximum auto-tuning iterations are reached.

### 7.2 Maximum iterations

Default:

```yaml
auto_tuning:
  enabled: true
  max_iterations: 5
  min_required_improvement_pct: 8.0
  preserve_all_runs: true
```

Do not overwrite failed runs. Save each run under:

```text
outputs/{experiment_name}/attempt_{attempt_id}/
```

### 7.3 Diagnosis rules

Implement rule-based diagnosis first. More advanced search can be added later.

#### Case A: Main improvement < 8%, but all constraints feasible

Possible causes:

- leader candidate grid is too narrow or too coarse
- prediction horizon is too short
- follower Nash solver stops too early
- smoothness penalty is too strong, suppressing control action
- system-level objective weight is inconsistent with TTT/TTS

Actions:

```text
- expand leader candidate range for N_P_star and N_UF_star
- refine leader grid around best candidate from previous run
- increase prediction horizon by one control interval if computationally feasible
- reduce smoothness weights w_L, R_p, R_i by 10-30%
- increase max_nash_iter
```

#### Case B: Freeway density exceedance remains high

Possible causes:

- metering too permissive
- VSL not restrictive enough upstream of bottleneck
- N_UF_star too high
- density penalty w_F too low

Actions:

```text
- reduce upper range of N_UF_star
- increase density exceedance penalty w_F
- allow lower VSL candidate values if already configured; otherwise keep default set
- increase ramp metering penalty for downstream density exceedance
```

#### Case C: Ramp queues overflow

Possible causes:

- metering too restrictive
- N_UF_star too low
- ramp queue penalty too weak
- freeway receiving capacity is too low due to VSL or congestion

Actions:

```text
- increase lower range of N_UF_star
- increase ramp queue overflow penalty
- relax eps_F if strict tracking is infeasible
- reduce VSL aggressiveness if it causes unnecessary throughput loss
```

#### Case D: Boundary queues are not balanced

Possible causes:

- inflow-outflow balance weight too weak
- green time min/max bounds too restrictive
- N_P_star infeasible under current demand
- storage constraints dominate the allocation problem

Actions:

```text
- increase J_balance weight
- refine green time allocation step size
- relax eps_U if the leader target is infeasible, while logging infeasibility
- adjust N_P_star candidate range toward observed feasible net inflow
- switch boundary storage allocation rule among proportional, equal_split, and main_priority for diagnostic ablation
```

#### Case E: Offset control worsens corridor delay

Possible causes:

- offset estimation uses wrong travel time
- offset smoothness penalty is too weak or too strong
- green time fine-tuning conflicts with progression

Actions:

```text
- recompute corridor travel time using current queue and speed estimates
- reduce maximum offset step if oscillatory
- increase offset smoothness weight if offsets fluctuate
- reduce green fine-tuning eps_g if offset stage is distorting stage-1 allocation
```

#### Case F: Nash solver does not converge

Possible causes:

- follower responses are too strongly coupled
- best-response updates oscillate
- action step sizes are too large

Actions:

```text
- add relaxation: response_new = alpha * response_new + (1-alpha) * response_old
- decrease alpha from 1.0 to 0.7, then 0.5 if needed
- increase max_nash_iter
- report non-convergence penalty as a diagnostic without adding it to leader objective
```

### 7.4 Auto-tuning search strategy

Implement deterministic auto-tuning so results are reproducible.

Recommended default:

```text
Attempt 0: default config
Attempt 1: expand leader grid and reduce smoothness penalties
Attempt 2: increase density/queue penalties based on dominant failure mode
Attempt 3: refine best leader region and increase Nash iterations
Attempt 4: adjust boundary balancing and offset parameters
Attempt 5: final best-known configuration
```

Each attempt must save:

```text
config_used.yaml
metrics_summary.json
diagnostics.json
run_log.csv
control_timeseries.csv
state_timeseries.csv
plots/
report.md
```

The final report must state clearly whether the 8% criterion was achieved.

Do not hard-code results. Do not silently discard failed attempts. Do not tune on a single seed only when multiple seeds are configured.

---
