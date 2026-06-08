# Numerical-Sim

MPC-based Stackelberg game simulation framework for integrated urban-freeway traffic control.

## Repository Structure

```text
.
├── AGENTS.md
├── CLAUDE.md
├── docs/
│   ├── codex_implementation_spec.md
│   ├── agent_debate_protocol.md
│   ├── experiment_acceptance_criteria.md
│   └── clean_room_rebuild_notes.md
├── reports/
│   ├── codex_run_report.md
│   ├── claude_review_report.md
│   └── final_validation_report.md
├── scripts/
│   ├── run_baseline.py
│   ├── run_proposed.py
│   ├── evaluate_improvement.py
│   └── diagnose_and_retry.py
├── src/
│   ├── config/
│   ├── controllers/
│   ├── evaluation/
│   ├── experiments/
│   ├── models/
│   ├── simulation/
│   └── tests/
└── experiments/
```

## Run

```powershell
python -m experiments.run_experiment `
  --config src/config/default.yaml `
  --scenario peak_demand `
  --baseline fixed_signal_fixed_speed `
  --controller stackelberg_mpc `
  --output outputs/peak_demand_stackelberg
```

With auto-tuning:

```powershell
python -m experiments.run_experiment `
  --config src/config/default.yaml `
  --scenario peak_demand `
  --baseline fixed_signal_fixed_speed `
  --controller stackelberg_mpc `
  --auto-tune `
  --output outputs/peak_demand_stackelberg_autotune
```

## Agent Workflow

- Codex implements and runs simulations.
- Claude reviews methodology, code, and simulation validity.
- Shared Markdown files under `reports/` preserve the debate and validation record.

## Clean Implementation Boundary

The active implementation lives under `src/`. Historical root-level model/controller files were removed so the current code path is driven by the spec and the structured package only.
