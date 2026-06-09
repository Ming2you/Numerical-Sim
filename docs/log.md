# Update Log

This file records human-readable update notes for each direct push.

## 2026-06-09 15:33:40 +09:00

### Scope

- Split the implementation specification into focused files under `docs/spec/`.
- Converted `docs/codex_implementation_spec.md` into a master index that points to the relevant detailed spec files.
- Added activation-aware controller diagnostics for ramp metering, VSL, and `N_UF_star`.
- Added a congestion-aware leader heuristic so `N_UF_star` can move below full ramp capacity under congestion.
- Updated the run report for the 2x-demand diagnostic run.
- Added config-loading compatibility for the YAML-style `src/config/default.yaml`.

### Notes

- The new spec structure makes `docs/spec/*.md` the source of truth.
- The current controller changes are diagnostic and heuristic improvements only. The next implementation phase should start with a spec audit before rewriting the METANET and ramp interaction model.

### Validation

- `python -B -m py_compile src/models/state.py src/controllers/leader.py src/controllers/freeway_follower.py src/evaluation/metrics.py`
- `python -B -m unittest discover -s src/tests -v`
- Result: 15 tests passed. The smoke experiment still reports `FAIL improvement=0.00%`, which is expected for the smoke test and does not fail the unit suite.

## 2026-06-09 16:47:09 +09:00

### Scope

- Replaced the simplified freeway plant behavior with METANET-style density, speed, flow, VSL, and ramp receiving logic.
- Added first-class freeway flow state `q = rho * v * lanes`.
- Reworked the freeway follower to evaluate time-varying ramp/VSL sequences over the MPC forecast with bounded beam search.
- Added movement-level urban queues, directed urban storage, arrival buffers, and storage release buffers.
- Added physical on-ramp queue synchronization and off-ramp storage blocking in the coupling module.
- Reworked the urban follower to emit movement-level allocation decisions while keeping legacy boundary-link outputs for compatibility.
- Added implementation audit notes and tests for METANET equations, ramp receiving, follower horizon behavior, coupling diagnostics, on-ramp sync, and off-ramp storage binding.

### Notes

- Freeway follower sequence search is a bounded heuristic, not an exact global optimizer.
- Off-ramp coupling is implemented at the control-interval aggregate boundary; the fully nested per-`T_f`/`T_u` order remains a future refinement.
- The urban topology is explicit and configurable, but still a compact default topology rather than a calibrated full network.

### Validation

- `python -B -m py_compile src/models/state.py src/models/urban_queue_model.py src/models/metanet.py src/simulation/coupling.py src/controllers/urban_follower.py src/controllers/stackelberg_mpc.py src/tests/test_constraints.py`
- `python -B -m unittest discover -s src/tests -v`
- Result: 33 tests passed. The smoke experiment printed `FAIL improvement=20.79%`, but the unittest suite passed with `OK`.

## 2026-06-09 17:35:29 +09:00

### Scope

- Added a repository language policy: reports, review notes, agent-facing documents, code comments, and docstrings should be written in Korean by default.
- Clarified that code identifiers, public APIs, config keys, metric names, commands, units, and quoted output should preserve their existing English or symbolic spelling.
- Updated `CLAUDE.md` so Claude writes Korean review reports by default.
- Rewrote `README.md` to include the language policy and fixed the broken repository tree rendering.
- Expanded `docs/spec/12_coding_style.md` with required Korean comment coverage for equations, unit conversions, coupling boundaries, optimization logic, heuristics, diagnostics, and intentional approximations.

### Notes

- Korean reports and comments are acceptable for future Codex/Claude review and should not be treated as a blocker.
- The comment policy requires meaningful comments for non-trivial model/controller logic, not noisy comments on self-evident assignments.

### Validation

- Documentation-only change.
- `git diff --check`
