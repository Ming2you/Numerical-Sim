# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 11. Reporting Requirements

Generate a final Markdown report at the end of every experiment.

### 11.1 Single-run report

The report must include:

1. Experiment metadata
   - scenario name
   - baseline mode
   - controller mode
   - seed
   - simulation horizon
2. Final pass/fail result
3. Main metric comparison
   - baseline total TTT
   - proposed total TTT
   - improvement rate
   - whether improvement >= 8%
4. Control validation summary
   - ramp metering
   - VSL
   - green time allocation
   - offset
   - inflow-outflow allocation and boundary queue balancing
5. Diagnostics
   - failure mode if any
   - parameter changes made by auto-tuner
   - rerun attempt history
6. Ablation results
7. Plots and exported CSV file paths
8. Explicit caveats
   - infeasible constraints
   - non-converged Nash iterations
   - scenario where controller failed

Example final result table:

```markdown
| Metric | Baseline | Proposed | Improvement | Pass |
|---|---:|---:|---:|---:|
| Total TTT | 123456 | 112000 | 9.28% | Yes |
| Freeway TTT | 60000 | 55200 | 8.00% | Yes |
| Urban TTT | 63456 | 56800 | 10.49% | Yes |
| Boundary B_in | 0.024 | 0.011 |  | Yes |
| Boundary B_out | 0.020 | 0.014 |  | Yes |
| Boundary CV (descriptive) | 0.42 | 0.31 |  |  |
```

### 11.2 Three-stage post-analysis report

The final post-analysis report must follow:

- `16_six_controller_comparison.md`
- `../literature_grounded_post_analysis_plan.md`

#### Stage 1: Six-controller comparison

The main table must include exactly:

```text
WU-CD-F
WU-MATCHED-STACKELBERG
WU-CC-F
PROPOSED-FOLLOWERS-ONLY
PROPOSED-STACKELBERG
PROPOSED-CENTRALIZED
```

For every controller report:

- total, urban and freeway TTT/TTS
- common free-flow reference TTT
- total, urban and freeway delay
- absolute and percentage delay improvement for paired comparisons
- completed vehicles, network throughput and average delay per completed vehicle
- terminal queues and total vehicles
- accepted/blocked off-ramp flow and on-ramp transfer
- capacity-drop and density-exceedance metrics
- computation time, solver evaluations and convergence
- authority group, Leader presence and centralized/distributed flag

The Stage 1 main result must treat the following as one outcome block:

```text
TTT/TTS
delay
throughput/completed vehicles
terminal state
```

Use one controller-independent free-flow reference for every controller in the same scenario/seed pair.
If baseline delay is at or below the configured epsilon, report percentage delay improvement as `NA` and
use the absolute `[veh*h]` difference. A negative calculated delay is an accounting/reference failure,
not a value to clamp to zero.

Report the predefined paired comparisons separately. Every paired comparison must include TTT difference,
delay difference, throughput difference and terminal-state difference. Do not label cross-authority
differences as the pure value of one control variable. Do not claim improvement when lower delay is
obtained by reducing throughput or increasing terminal queues beyond the configured tolerance.

#### Stage 2: Control mechanism validation

For allocation/green, offset, VSL and ramp metering report:

```text
challenged_event_count
correctly_inactive_event_count
directional_accuracy
response_delay
mechanism_success_rate
outcome_success_rate
unnecessary_activation_rate
congestion_shift_event_count
```

Each conclusion must identify:

```text
Trigger -> Action -> Physical mediator -> Outcome
```

Activation count alone is not evidence of a valid mechanism.

#### Stage 3: Player and information ablation

Report:

- active/removed strategic players
- allowed/blocked information directions
- confirmation that physical coupling remained active
- confirmation that remaining players and Leader were reoptimized
- total and subsystem cost change
- directional information value
- bidirectional synergy
- urban/freeway coupling-player marginal value
- communication and computation cost

Required cases:

```text
FULL_COUPLING
NO_U_TO_F_INFO
NO_F_TO_U_INFO
NO_CROSS_NETWORK_INFO
LOCAL_ONLY_COUPLING_PLAYERS
FIXED_URBAN_COUPLING_PLAYERS
FIXED_FREEWAY_COUPLING_PLAYERS
FIXED_ALL_COUPLING_PLAYERS
```

The report must distinguish strategic player removal from physical network removal.

### 11.3 Required post-analysis outputs

```text
post_analysis/
  stage1/
  stage2/
  stage3/
  plots/
  final_post_analysis_report.md
```

---
