# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 2. Implementation Scope

### 2.1 Mandatory modules

Implement the following modules.

```text
src/
  config/
    default.yaml
    scenarios.yaml
  models/
    metanet.py
    urban_queue_model.py
    demand.py
    state.py
  controllers/
    leader.py
    freeway_follower.py
    urban_follower.py
    nash_solver.py
    stackelberg_mpc.py
    auto_tuner.py
  simulation/
    simulator.py
    baseline.py
    closed_loop_runner.py
  evaluation/
    metrics.py
    diagnostics.py
    report.py
    plots.py
  experiments/
    run_experiment.py
    run_ablation.py
  tests/
    test_constraints.py
    test_metrics.py
    test_closed_loop_smoke.py
```

If the current repository already has a different structure, adapt this structure without breaking existing code. Keep module boundaries equivalent.

---
