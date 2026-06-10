# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 9. Configuration Requirements

Create a YAML config with at least the following fields.

```yaml
simulation:
  T_total: 7200
  T_f: 10
  T_u: 5
  control_interval: 180
  random_seed: 42

mpc:
  horizon_steps: 5
  leader_candidate_count: 15
  max_nash_iter: 10
  nash_obj_tol: 1.0e-3
  nash_control_tol: 1.0e-3
  nash_relaxation_alpha: 0.8

leader:
  objective_mode: state_accumulation
  w_P: 1.0
  w_F: 1.0
  w_L: 0.05
  N_P_star_range: [0, 500]
  N_UF_star_range: [0, 6000]

freeway_follower:
  eps_F: 100
  vsl_set: [50, 60, 70, 80, 90, 100]
  max_vsl_step: 20
  ramp_queue_penalty: 10.0
  density_penalty: 10.0
  metering_smoothness_weight: 0.1
  vsl_smoothness_weight: 0.1

urban_follower:
  eps_U: 100
  eps_g: 5
  max_offset_step: 15
  boundary_balance_weight: 10.0
  offset_smoothness_weight: 0.1
  green_smoothness_weight: 0.1
  receiving_space_rule: proportional

evaluation:
  main_metric: total_ttt
  main_metric_direction: lower_is_better
  min_improvement_pct: 8.0
  eps: 1.0e-9

auto_tuning:
  enabled: true
  max_iterations: 5
  preserve_all_runs: true
```

Adjust units consistently. If `N_UF_star` and `N_P_star` are in vehicles per control interval rather than veh/h, make that explicit in the config and convert internally.

---
