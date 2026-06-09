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
