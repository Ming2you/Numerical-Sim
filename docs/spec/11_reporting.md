# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 11. Reporting Requirements

Generate a final Markdown report at the end of every experiment.

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
| Boundary CV | 0.42 | 0.31 | 26.19% | Yes |
```

---
