# Agent Debate Protocol

This repository uses Markdown files as the shared workspace between Codex, Claude, and the human researcher.

## Agent Roles

| Agent | Role |
|---|---|
| Codex | Implementation, tests, simulation execution, reports |
| Claude | Critic, method reviewer, simulation validity reviewer |
| Shared Markdown | Evidence board and debate record |
| Human | Final approval and research judgment |

## Round Structure

Each round must follow this sequence:

1. Codex proposal or implementation
2. Codex simulation and validation run
3. Codex writes `reports/codex_run_report.md`
4. Claude reviews code, metrics, and report
5. Claude writes `reports/claude_review_report.md`
6. Codex reads Claude review and revises implementation
7. Repeat until the final acceptance criteria pass

## Debate Rules

- Do not rely on verbal claims only.
- Every claim must refer to code, simulation output, metric, or report evidence.
- Baseline and proposed simulations must use the same scenario, seed, horizon, and demand.
- Improvement below the configured threshold is a failure.
- Boundary queue balancing degradation is a failure unless explicitly justified.
- Infeasible controller constraints must be logged, not hidden.
- Failed attempts must be preserved under `outputs/{experiment_name}/attempt_{id}/`.

## Final Acceptance

The task is complete only when:

- Main metric improvement is at least the configured threshold, default 8%.
- Boundary queue imbalance is reduced or not worsened.
- Ramp metering, VSL, offset, green time allocation, and inflow-outflow allocation are all active or explicitly disabled by an ablation.
- Control validation checks pass.
- Unit tests and closed-loop smoke tests pass.
- Claude review verdict is PASS when Claude review is part of the loop.

