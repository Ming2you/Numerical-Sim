# Clean Rebuild Notes

## Reason

The repository previously contained historical root-level simulation and controller files. Those files were removed from the active implementation path so the current controller can be reviewed as a spec-first implementation under `src/`.

## Sources Used

The rebuild is based on:

- `docs/codex_implementation_spec.md`
- `docs/experiment_acceptance_criteria.md`
- `docs/agent_debate_protocol.md`
- `src/config/default.yaml`
- `src/config/scenarios.yaml`

## Active Implementation Boundary

Only these paths are active for the new implementation:

- `src/models/`
- `src/controllers/`
- `src/simulation/`
- `src/evaluation/`
- `src/experiments/`
- `experiments/`
- `scripts/`

The repository root is now reserved for documentation and project entry points only.

## Structural Guard

`src/tests/test_clean_structure.py` checks that deleted historical controller names are not referenced by active Python, Markdown, or config files.

## Current Status

The clean rebuild provides:

- closed-loop baseline/proposed simulation
- Stackelberg leader candidate enumeration
- freeway follower projection for ramp metering and VSL
- urban two-stage follower for green time, offsets, and boundary allocation
- Nash-like iterative follower response with best-iterate fallback
- evaluation, diagnostics, reports, and auto-tuning attempt preservation

The smoke test verifies execution and required output files. It does not claim the 8% improvement criterion is achieved.

