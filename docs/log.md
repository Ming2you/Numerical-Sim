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

## 2026-06-09 17:39:44 +09:00

### Scope

- Added a repository sync policy to `CLAUDE.md` and `README.md`.
- The policy requires agents to check `origin/main` before starting user-requested work.
- If the local working tree is clean and the remote is ahead, agents should automatically fast-forward with `git pull --ff-only origin main` before editing.
- If local uncommitted changes exist, agents must not overwrite them and should ask how to proceed.

### Notes

- This policy is intended to prevent Codex/Claude from working on stale local code after another agent pushes to GitHub.
- Direct `main` work should continue to avoid accidental merge commits by using fast-forward pulls.

### Validation

- Documentation-only change.
- `git diff --check`

## 2026-06-09 18:09:13 +09:00

### Scope

- `freeway_step`를 `freeway_substep` 기반 wrapper로 분해하고, `T_f` 단위 METANET 갱신을 독립 실행 가능하게 정리했습니다.
- `urban_step`를 `urban_substep` 기반 wrapper로 분해하고, on-ramp demand/release가 urban movement queue에 실제로 반영되도록 연결했습니다.
- `coupling.py`를 spec 3.4.3의 `T_c -> T_f -> T_u` nested order로 재작성했습니다.
- Freeway follower prediction을 standalone freeway plant가 아니라 coupled plant 기반으로 통일했습니다.
- Urban follower가 freeway follower response pressure를 green/allocation 결정에 반영하도록 수정했습니다.
- Nash solver diagnostics에 mutual response 및 coupled prediction 사용 여부를 기록하도록 추가했습니다.
- Smoke test용 MPC/search override CLI 옵션과 coupling/follower 관련 regression tests를 추가했습니다.

### Notes

- 기본 실험 설정은 유지하고, smoke test에서만 horizon/search 규모를 줄이도록 CLI override를 사용합니다.
- `coupling_nested_order_active`, `freeway_follower_coupled_prediction`, `nash_mutual_response_active` diagnostics로 새 coupling/prediction 경로를 확인할 수 있습니다.

### Validation

- `python -B -m py_compile src\\models\\metanet.py src\\models\\urban_queue_model.py src\\simulation\\coupling.py src\\controllers\\freeway_follower.py src\\controllers\\urban_follower.py src\\controllers\\nash_solver.py src\\tests\\test_constraints.py`
- `python -B -m unittest src.tests.test_constraints -v`
- `python -B -m unittest src.tests.test_metanet_equations -v`
- `python -B -m unittest discover -s src\\tests -v`
- Result: 36 tests passed. Smoke experiment printed `FAIL improvement=-5.67%`, but the unittest suite passed with `OK`.
