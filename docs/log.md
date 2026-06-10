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

## 2026-06-09 20:10:49 +09:00

### Scope

- on-ramp 결합을 2저수지 구조로 수정했습니다.
- `urban_movement_queue[R*_onramp]`는 urban 접근부 queue `x_on`, `state.ramp_queue[R*]`는 freeway ramp queue `w_r`로 분리했습니다.
- `demand.ramp_arrival`은 먼저 `x_on`에 쌓이고, urban green/phase/capacity가 `x_on -> w_r` release를 제어하도록 연결했습니다.
- ramp metering은 `w_r -> freeway` release만 담당하도록 분리했습니다.
- 기존 on-ramp sync helper는 두 queue를 복사하지 않고 각 reservoir의 유효 범위만 정리하도록 재정의했습니다.
- `onramp_two_reservoir_active`, `coupling_onramp_two_reservoir_active`, `onramp_green_releases_veh`, `ramp_metering_releases_veh` diagnostics를 추가했습니다.
- on-ramp green 증가가 실제 ramp queue 유입을 증가시키는 regression test를 추가했습니다.

### Notes

- 짧은 reduced search feasibility probe는 0.318초에 완료되어 2저수지 구조 자체의 실행 문제는 확인되지 않았습니다.
- 기본 config 기준 한 MPC decision의 coupled interval 호출 상한은 약 60,750개로 계산되어, full 인증 run 전에 prediction 경량화 또는 단계적 run이 필요할 수 있습니다.

### Validation

- `python -B -m py_compile src\\models\\urban_queue_model.py src\\simulation\\coupling.py src\\tests\\test_constraints.py`
- `python -B -m unittest src.tests.test_constraints -v`
- `python -B -m unittest discover -s src\\tests -v`
- Reduced feasibility probe: `run_experiment --T-total 180 --mpc-horizon-steps 1 --leader-candidate-count 2 --max-nash-iter 2 --freeway-horizon-beam-width 1 --freeway-ramp-candidate-limit 1 --freeway-vsl-candidate-limit 1`
- Result: 37 tests passed. Reduced probe completed in 0.318 sec and printed `FAIL improvement=-2.98%`, which is diagnostic only.

## 2026-06-09 21:42:49 +09:00

### Scope

- 기본 MPC prediction horizon을 3으로 낮췄습니다.
- `src/config/default.yaml`의 `mpc.horizon_steps`를 `8 -> 3`으로 수정했습니다.
- 코드에서 직접 `ExperimentConfig()`를 생성하는 경우와의 혼선을 줄이기 위해 `MPCConfig.horizon_steps` 기본값도 `3`으로 맞췄습니다.

### Notes

- 기본 config의 freeway follower transition 상한은 약 405에서 135로 줄었습니다.
- leader 후보와 Nash 반복까지 포함한 한 MPC decision의 coupled interval 호출 상한은 약 60,750에서 20,250으로 줄었습니다.
- 기본 config 첫 control decision은 78.7초에 완료되었습니다.
- full default run은 시도했지만 사용자 중단 전까지 baseline 산출물만 생성되었습니다. Proposed/controller 단계는 여전히 무거워 추가 경량화가 필요할 수 있습니다.

### Validation

- `python -B -c "from src.models.state import ExperimentConfig; cfg=ExperimentConfig.from_file('src/config/default.yaml'); print(cfg.mpc.horizon_steps)"`
- `python -B -c "<first StackelbergMPCController.decide timing probe>"`
- `python -B -m unittest discover -s src\\tests -v`
- Result: 37 tests passed. First default-config control decision completed in 78.7 sec.

## 2026-06-10 10:19:06 +09:00

### Scope

- Wu et al.(2022) 문헌 PDF를 `docs/`에 추가해 integrated urban-freeway distributed control 구현 기준 문헌으로 보존했습니다.
- on-ramp metering release를 요청량이 아니라 `w_r`에서 실제로 빠진 차량 수 기준으로 freeway METANET에 주입하도록 수정했습니다.
- `urban_substep` diagnostics에 ramp별 metering request/actual/shortfall 차량 수를 추가했습니다.
- Freeway follower 후보 평가에서 full `run_coupled_interval` 호출을 제거하고, 고정된 urban control로부터 on-ramp green release와 off-ramp storage capacity를 예측하는 lightweight boundary forecast 경로를 추가했습니다.
- 2저수지 구조에 맞게 ramp metering 상한 계산에서 raw ramp demand를 바로 쓰지 않고, `x_on -> w_r` 예상 green release를 사용하도록 수정했습니다.
- follower prediction diagnostics에 `freeway_follower_lightweight_prediction`을 추가하고, 더 이상 coupled prediction을 사용하지 않음을 표시했습니다.
- actual ramp release만 freeway substep에 전달되는지 확인하는 regression test를 추가했습니다.

### Notes

- 이번 변경은 Wu et al. 방식의 “경계 상호작용 변수는 고정/예측하고 local problem은 가볍게 푸는” 방향으로 freeway follower의 계산 병목을 먼저 제거한 단계입니다.
- 짧은 `peak_demand` smoke에서는 실행 가능성은 확인됐지만, total TTT improvement는 아직 -2.56%로 목표 8%를 만족하지 못했습니다.
- 다음 단계에서는 objective/leader 후보와 boundary balance, metering infeasibility 처리 쪽을 조정해야 합니다.

### Validation

- `python -B -m py_compile src\\models\\urban_queue_model.py src\\simulation\\coupling.py src\\controllers\\freeway_follower.py`
- `python -B -m py_compile src\\tests\\test_constraints.py`
- `python -B -m unittest src.tests.test_constraints -v`
- `python -B -m unittest discover -s src\\tests -v`
- `python -B -m experiments.run_experiment --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --T-total 360 --output outputs/codex_lightweight_peak_smoke`
- Result: 38 tests passed. Short peak smoke completed in about 45 sec and printed `FAIL improvement=-2.56%`.
