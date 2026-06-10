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

## 2026-06-10 11:19:23 +09:00

### Scope

- Claude full diagnostic run 결과를 기준으로 `reports/codex_run_report.md`를 갱신했습니다.
- `N_P_star`의 의미를 urban accumulation target, 단위 `veh`로 명시했습니다.
- urban follower가 `N_P_star`를 직접 veh/h 순유입으로 쓰지 않고, 현재 urban accumulation과 목표 accumulation의 차이에서 `net_inflow_target`을 유도하도록 수정했습니다.
- `urban_queue_model` diagnostics에 `net_inflow_target`, `urban_accumulation_veh`, `urban_accumulation_target_veh`, `urban_accumulation_error_veh`를 추가했습니다.
- leader의 `N_UF_star` 후보를 total ramp capacity가 아니라 현재 ramp queue, 예상 on-ramp green release, downstream receiving, mainline density headroom 기반 feasible capacity 안에서 생성하도록 수정했습니다.
- no-control/fixed baseline MFD sweep용 `experiments.calibrate_setpoints` CLI scaffold를 추가했습니다.
- 자동 생성 experiment report의 `N_P_star`/`N_UF_star` 단위 설명을 현재 코드 의미에 맞게 수정했습니다.

### Notes

- 짧은 `peak_demand`, `T_total=360` smoke에서는 Total TTT improvement가 `6.85%`로 나왔습니다.
- 아직 acceptance 기준 `8%`와 boundary balance validation은 통과하지 못했습니다.
- 다음 단계는 full `peak_demand 7200s` 재실행 전, boundary balance와 metering residual을 줄이는 안정화입니다.

### Validation

- `python -B -m py_compile src\\models\\state.py src\\models\\urban_queue_model.py src\\controllers\\leader.py src\\controllers\\urban_follower.py src\\controllers\\stackelberg_mpc.py src\\experiments\\calibrate_setpoints.py experiments\\calibrate_setpoints.py src\\tests\\test_closed_loop_smoke.py src\\tests\\test_metanet_equations.py`
- `python -B -m unittest src.tests.test_metanet_equations -v`
- `python -B -m unittest src.tests.test_closed_loop_smoke -v`
- `python -B -m unittest src.tests.test_constraints -v`
- `python -B -m unittest src.tests.test_metrics -v`
- `python -B -m unittest discover -s src\\tests -v`
- `python -B -m experiments.calibrate_setpoints --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --urban-scales 0.75,1.0,1.25 --T-total 360 --output outputs/codex_setpoint_calibration_smoke`
- `python -B -m experiments.run_experiment --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --T-total 360 --output outputs/codex_setpoint_peak_smoke`
- Result: 40 tests passed. Calibration smoke estimated `n_crit=172.225 veh`, `max_production=1306.667 veh/h`. Short peak smoke printed `FAIL improvement=6.85%`.

## 2026-06-10 13:06:17 +09:00

### Scope

- `docs/spec/04_controller.md`의 수정된 leader objective를 기준으로 `leader.py` objective를 `n_P + n_F + N_P_crit 초과 penalty + freeway density 초과 penalty + leader action L1 smoothness` 형태로 정리했습니다.
- 기본 `leader.objective_mode`를 `state_accumulation`으로 바꾸고, `follower_ttt`는 선택 모드로 남겼습니다.
- `N_P_star` 후보를 기존 임의 `[0, 500]` 균등 grid 대신 `N_P_crit_veh` 주변 band에서 생성하도록 수정했습니다.
- urban follower가 on-ramp movement allocation도 직접 결정하도록 연결했습니다.
- p2 green fraction이 짧을 때도 `N_UF_star`를 받칠 수 있도록 on-ramp saturation flow를 green fraction 기준으로 역산했습니다.
- off-ramp discharge phase가 최소 green에 묶여 urban outflow가 부족해지는 문제를 막기 위해 p1 green floor를 추가했습니다.
- urban net inflow tracking 진단은 follower가 allocation을 만들 때 사용한 control-interval target과 비교하도록 정리했습니다.
- `reports/codex_run_report.md`를 이번 검증 결과 기준으로 갱신했습니다.

### Validation

- `python -B -m py_compile src\\models\\state.py src\\controllers\\leader.py src\\controllers\\stackelberg_mpc.py src\\controllers\\urban_follower.py src\\models\\urban_queue_model.py src\\evaluation\\metrics.py src\\tests\\test_constraints.py src\\tests\\test_metanet_equations.py`
- `python -B -m unittest src.tests.test_metanet_equations -v`
- `python -B -m unittest src.tests.test_constraints -v`
- `python -B -m unittest src.tests.test_metrics -v`
- `python -B -m unittest discover -s src\\tests -v`
- `python -B -m experiments.run_experiment --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --T-total 360 --output outputs/codex_leader_objective_peak_360_v5`
- `python -B -m experiments.run_experiment --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --T-total 1800 --output outputs/codex_leader_objective_peak_1800_v2`
- Result: 44 tests passed. `peak_demand 360 s`는 PASS, Total TTT improvement `13.60%`. `peak_demand 1800 s`는 Total TTT improvement `32.38%`였지만 density/VSL validation과 장기 urban net inflow tracking validation이 남아 FAIL입니다.

## 2026-06-10 15:45:11 +09:00

### Scope

- Wu et al. Eq.(22) 계열 off-ramp spill-back capacity drop을 `lambda_eff`로 구현했습니다.
- `lane_reduction`은 2차로 네트워크에서 과격한 1차로 감소 대신 기본 `0.35` 분수 감소로 설정했습니다.
- `TrafficState.freeway_effective_lanes`를 추가하고, freeway flow/TTT/state logging이 유효 차로 수를 사용하도록 수정했습니다.
- λ 변화 시 차량이 사라지지 않도록 `rho`가 아니라 `N = rho * L * lambda`를 보존량으로 다루도록 `freeway_substep`을 수정했습니다.
- speed/desired-speed/VSL-effective-speed/anticipation 계산이 `rho_for_flow = N / (L * lambda_eff)`를 쓰도록 정리했습니다.
- `rho_max * L * lambda_eff` 상한 projection은 차량 삭제를 만들 수 있어 제거하고, 음수 차량 수만 projection하도록 바꿨습니다.
- simulator plant, freeway follower prediction, coupling aggregate diagnostics가 `capacity_drop_active`, `lambda_eff_*`, `capacity_drop_lane_loss_*`를 일관되게 전달하도록 맞췄습니다.
- `docs/capacity_drop_proposal.md`와 canonical spec을 현재 구현 원칙에 맞게 갱신했습니다.

### Notes

- 10번 튜닝은 제외했습니다. horizon, penalty, `N_UF_star` 후보 범위는 이번 변경에서 조정하지 않았습니다.
- 강제 spill-back unit test에서는 `lambda_eff` 경계값, 차량 보존, `rho_for_flow` 기반 속도 저하, VSL 속도 반응을 확인했습니다.
- 기본 `peak_demand` 360초/1800초 run에서는 `capacity_drop_active=0`, `lambda_eff_FW_W_last=2.0`, `lambda_eff_FW_E_last=2.0`으로 실제 차로 감소가 발화하지 않았습니다.
- 따라서 현재 VSL 미활성은 capacity-drop 수식 미구현 문제가 아니라, 기본 시나리오에서 off-ramp storage가 spill-back 임계까지 차지 않는 문제로 보는 것이 맞습니다.

### Validation

- `python -B -m py_compile src\\models\\state.py src\\models\\metanet.py src\\controllers\\freeway_follower.py src\\simulation\\coupling.py src\\simulation\\simulator.py src\\tests\\test_metanet_equations.py`
- `python -B -m unittest src.tests.test_metanet_equations -v`
- `python -B -m unittest discover -s src\\tests -v`
- `python -B -m experiments.run_experiment --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --T-total 360 --output outputs/codex_capacity_drop_peak_360_v2`
- `python -B -m experiments.run_experiment --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --T-total 1800 --output outputs/codex_capacity_drop_peak_1800_v2`
- Result: 49 tests passed. `peak_demand 360 s`는 PASS, Total TTT improvement `13.60%`. `peak_demand 1800 s`는 Total TTT improvement `33.66%`였지만 VSL/density validation과 boundary balance validation이 남아 FAIL입니다.

## 2026-06-10 17:36:31 +09:00

### Scope

- Capacity drop이 실제로 발생하는 stress tuning에서 VSL이 activate되는지 확인했습니다.
- 빠른 regression test `test_freeway_follower_activates_vsl_under_capacity_drop`를 추가했습니다.
- 재현 가능한 probe CLI `experiments.capacity_drop_vsl_probe`를 추가했습니다.
- `reports/codex_run_report.md`를 capacity-drop/VSL 튜닝 결과 기준으로 갱신했습니다.

### Tuning

- `off_ramp_split_ratio`: `0.90`
- `OR_W_D`, `OR_E_F` storage: `20 veh`
- `urban_avg_speed_km_h`: `3.0`
- `urban_avg_vehicle_length_m`: `15.0`
- `lane_reduction`: `0.75`
- `gamma`: `0.2`
- `vsl_smoothness_weight`: `0.0`
- `horizon_steps`: `3`

### Result

- `capacity_drop_active_steps=4`
- `vsl_active_steps=4`
- `overlap_steps=4`
- `lambda_min=1.250007`
- baseline total TTT `249.168`, proposed total TTT `250.111`, proposed_without_vsl total TTT `249.763`

### Notes

- 결론: capacity drop이 실제로 발화하면 현재 controller도 VSL을 activate할 수 있습니다.
- 단, 이 stress tuning에서 VSL이 TTT를 개선하지는 않았습니다. 다음 튜닝은 VSL activation 자체가 아니라 VSL 강도/penalty, ramp metering과의 분담, leader objective의 freeway spill-back penalty를 조정하는 방향이 맞습니다.

### Validation

- `python -B -m py_compile src\\experiments\\capacity_drop_vsl_probe.py experiments\\capacity_drop_vsl_probe.py src\\tests\\test_constraints.py`
- `python -B -m unittest src.tests.test_constraints.ConstraintTests.test_freeway_follower_activates_vsl_under_capacity_drop -v`
- `python -B -m experiments.capacity_drop_vsl_probe --output outputs\\codex_capacity_drop_vsl_probe_cli --T-total 720`
- `python -B -m unittest discover -s src\\tests -v`
- Result: probe reproduced `capacity_drop_active_steps=4`, `vsl_active_steps=4`, `overlap_steps=4`; 50 tests passed.

## 2026-06-10 17:54:15 +09:00

### Scope

- distributed player 1차 구현을 추가했습니다.
- 기존 2-block `NashSolver`는 유지하고, `mpc.follower_solver_mode: distributed`일 때 `DistributedCoordinator`를 사용하도록 연결했습니다.
- topology 기반 agent partition을 추가했습니다.
  - urban: `U_A`, `U_C`, `U_D`, `U_F`
  - freeway: `F_W`, `F_E`
- coupling variable exchange와 normalized coupling residual 기반 반복 종료를 추가했습니다.
- `run_experiment` CLI에 `--follower-solver-mode two_block|distributed` 옵션을 추가했습니다.
- distributed 내부 iteration에서 offset smoothness 제약이 누적 위반되지 않도록 최종 offset clamp를 추가했습니다.
- distributed player regression tests를 추가했습니다.

### Notes

- 이번 구현은 Wu §IV-D 구조를 코드 경로로 넣은 1차 버전입니다.
- agent별 exact MILP/SQP local optimizer는 아직 아닙니다.
- Urban agent는 기존 `UrbanFollower` 결과에서 자기 signal/movement 변수만 추출합니다.
- Freeway agent는 링크별 local heuristic으로 ramp metering/VSL을 계산합니다.
- 따라서 “agent partition + coupling exchange + diagnostics”는 구현됐고, local optimizer 정밀화는 다음 단계입니다.

### Validation

- `python -B -m py_compile src\\controllers\\distributed_coordinator.py src\\controllers\\stackelberg_mpc.py src\\experiments\\run_experiment.py src\\models\\state.py src\\tests\\test_constraints.py src\\tests\\test_metanet_equations.py`
- `python -B -m unittest src.tests.test_constraints.ConstraintTests.test_distributed_agent_partition_matches_topology src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics src.tests.test_metanet_equations.MetanetEquationTests.test_config_rejects_invalid_follower_solver_mode -v`
- `python -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_can_use_distributed_follower_solver -v`
- `python -B -m experiments.run_experiment --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --T-total 360 --follower-solver-mode distributed --leader-candidate-count 5 --max-nash-iter 3 --output outputs\\codex_distributed_player_peak_360_v2`
- `python -B -m unittest discover -s src\\tests -v`
- Result: 54 tests passed. Distributed smoke는 Total TTT improvement `8.28%`로 main metric은 통과했지만, boundary balance validation이 남아 최종 acceptance는 FAIL입니다.

## 2026-06-11 00:38:59 +09:00

### Scope

- canonical extended 6-intersection grid 구조를 기본 config/state에 반영했습니다.
- on-ramp/off-ramp를 D/F 교차로와 FW_W/FW_E 양방향 interface로 확장했습니다.
- 독립 `InflowOutflowAllocationModule`을 추가해 leader의 `N_P_star`를 movement별 inflow/outflow service와 green setpoint로 변환하도록 했습니다.
- `UrbanFollower`는 allocation module 결과를 기준으로 green을 band 안에서 fine-tune하고 offset을 계산하도록 정리했습니다.
- freeway response pressure가 들어오면 off-ramp storage를 비우는 도시 유입 phase를 우선하도록 수정했습니다.
- `DistributedCoordinator`를 교차로 agent 5개(`U_A`, `U_B`, `U_C`, `U_D`, `U_F`)와 freeway segment agent 6개(`F_W0..F_W2`, `F_E0..F_E2`) 구조로 확장했습니다.
- `w_r` ramp queue delay는 freeway TTT에 귀속하고, urban TTT에서는 on-ramp 접근부 `x_on`과 off-ramp storage만 계상되도록 정리했습니다.
- `docs/wu2022_distributed_reference.md`의 repo mapping도 새 topology와 agent partition 기준으로 갱신했습니다.

### Validation

- `python -B -m py_compile src\\controllers\\inflow_outflow_allocation.py src\\controllers\\urban_follower.py src\\controllers\\distributed_coordinator.py src\\models\\state.py src\\models\\urban_queue_model.py src\\simulation\\coupling.py src\\experiments\\capacity_drop_vsl_probe.py src\\tests\\test_constraints.py src\\tests\\test_metanet_equations.py`
- `python -B -m unittest discover -s src\\tests`
- Result: 54 tests passed.

## 2026-06-11 01:34:18 +09:00

### Scope

- GitHub `origin/main`을 pull하여 `ce9d3ed`의 boundary-balance proposal/Claude review를 반영했습니다.
- `leader.N_P_crit_veh`를 확장망 calibration 결과 `354.809 veh`로 갱신했습니다.
- distributed urban agent neighbor map이 존재하지 않는 `F_W`/`F_E`가 아니라 segment agent(`F_W1`, `F_W2`, `F_E1`, `F_E2`)를 가리키도록 수정했습니다.
- boundary-balance acceptance를 `CV_boundary` 기준에서 §3.2와 동일한 movement-level `B_in/B_out` 기준으로 정합했습니다.
- empty/saturated regime에서 작은 B가 trivial pass가 되지 않도록 `boundary_balance_degenerate`, empty/saturation ratio diagnostics를 추가했습니다.
- report/spec 문서에서 `CV_boundary`는 descriptive metric으로 낮추고, B 기준 acceptance를 명시했습니다.

### Run

- `python -B -m src.experiments.run_experiment --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --T-total 360 --follower-solver-mode distributed --leader-candidate-count 5 --max-nash-iter 3 --output outputs\\codex_boundary_acceptance_peak_360`
- Result: execution OK, Total TTT improvement `21.07%`, final evaluation `FAIL`.
- Failure reason: ramp metering error and movement-level boundary balance. Boundary diagnostics now expose `B_in=0.0843`, `B_out=0.1602`, `boundary_balance_degenerate=1`, `boundary_empty_ratio=0.6364`, `urban_net_inflow_tracking_error_veh_h=2988`.

### Validation

- `python -B -m py_compile src\\models\\urban_queue_model.py src\\controllers\\inflow_outflow_allocation.py src\\controllers\\urban_follower.py src\\controllers\\distributed_coordinator.py src\\evaluation\\metrics.py src\\evaluation\\report.py src\\evaluation\\diagnostics.py src\\models\\state.py src\\tests\\test_constraints.py src\\tests\\test_metanet_equations.py`
- `python -B -m unittest discover -s src\\tests`
- Result: 56 tests passed.

## 2026-06-11 00:48:56 +09:00

### Scope

- extended distributed smoke run 중 발견된 boundary-out legacy aggregate 덮어쓰기 버그를 수정했습니다.
- `DistributedCoordinator._legacy_boundary_allocations`가 `boundary_out` movement 합을 사용하도록 고치고 regression assertion을 추가했습니다.

### Run

- `python -B -m src.experiments.run_experiment --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --T-total 360 --follower-solver-mode distributed --leader-candidate-count 5 --max-nash-iter 3 --output outputs\\codex_extended_distributed_peak_360_v2`
- Result: execution OK, Total TTT improvement `19.54%`, final evaluation `FAIL`.
- Failure reason: `boundary_queue_balance_failed`; proposed Boundary CV `1.151` vs baseline `1.032`, urban net inflow tracking error `2352.50 veh/h`.
- Activation: distributed player active with 5 urban agents and 6 freeway agents; ramp metering active; green/offset active; VSL inactive under this non-spillback smoke scenario.

### Validation

- `python -B -m unittest discover -s src\\tests`
- Result: 54 tests passed.
