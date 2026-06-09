# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 8. CLI Requirements

Implement command-line entry points.

### 8.1 Run one experiment

```bash
python -m experiments.run_experiment \
  --config src/config/default.yaml \
  --scenario peak_demand \
  --baseline fixed_signal_fixed_speed \
  --controller stackelberg_mpc \
  --output outputs/peak_demand_stackelberg
```

### 8.2 Run with auto-tuning

```bash
python -m experiments.run_experiment \
  --config src/config/default.yaml \
  --scenario peak_demand \
  --baseline fixed_signal_fixed_speed \
  --controller stackelberg_mpc \
  --auto-tune \
  --min-improvement-pct 8.0 \
  --output outputs/peak_demand_stackelberg_autotune
```

### 8.3 Run ablation

```bash
python -m experiments.run_ablation \
  --config src/config/default.yaml \
  --scenario peak_demand \
  --output outputs/ablation_peak_demand
```

---
