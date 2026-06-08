# Codex Run Report

## Status

Clean structured implementation completed. The active code path is now limited to the `src/` package and documented wrappers. Historical root-level implementation files were removed from the repository root to avoid accidental reuse.

## Implemented

- Added `src/` package structure matching the implementation spec.
- Added config files under `src/config/`.
- Implemented traffic state/config dataclasses.
- Implemented simplified METANET-style freeway dynamics and urban queue dynamics.
- Implemented Stackelberg MPC controller with:
  - leader candidate generation
  - freeway follower
  - urban follower
  - Nash-like follower iteration
  - first-step control application
- Implemented baseline/proposed closed-loop runner.
- Implemented metrics, diagnostics, reporting, placeholder plots, and auto-tuning loop.
- Added CLI wrappers:
  - `python -m experiments.run_experiment`
  - `python -m experiments.run_ablation`
- Added unit and smoke tests under `src/tests/`.
- Added `src/tests/test_clean_structure.py` to guard against references to deleted historical controller names.
- Added `docs/clean_room_rebuild_notes.md`.

## Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest discover -s src\tests -v
```

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m experiments.run_experiment --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --T-total 1800 --output outputs/peak_demand_stackelberg_30min_smoke_v5
```

## Latest Observed Smoke Result

- Unit tests: PASS, 14 tests OK
- 30-minute smoke: completed
- Main metric: FAIL
- Improvement rate: 0.00%
- Boundary CV improved in the smoke run
- Ramp metering and net inflow tracking did not satisfy strict configured tolerances

## Known Issues

- The simplified controller/model currently validates execution and logging, but does not yet demonstrate the configured 8% Total TTT improvement.
- Ramp metering target tracking can be infeasible under current leader candidates and ramp demand.
- Net inflow tracking still exceeds the default urban tolerance in smoke runs.

## Proposed Next Modification

Calibrate the simplified traffic response and leader objective so that control actions affect Total TTT in a physically meaningful way. Then rerun full auto-tuning and ask Claude to review simulation validity.

