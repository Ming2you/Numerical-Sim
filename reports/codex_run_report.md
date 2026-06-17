# Codex 실행 리포트

## 2026-06-10 17:54:15 +09:00

### 이번 작업

distributed player 1차 구현을 추가했습니다. 기존 `FreewayFollower + UrbanFollower` 2-block Nash 경로는 그대로 유지하고, 새 경로는 `mpc.follower_solver_mode: distributed`로 선택할 수 있게 했습니다.

### 구현 내용

- `src/controllers/distributed_coordinator.py` 추가
  - urban agent 4개: `U_A`, `U_C`, `U_D`, `U_F`
  - freeway agent 2개: `F_W`, `F_E`
  - topology에서 agent partition과 neighbor 후보를 자동 유도
  - coupling variables: `u_on_*`, `q_off_*`, ramp queue, freeway boundary density/speed, urban agent accumulation
  - iteration 종료 기준: control vector가 아니라 normalized coupling residual
- `mpc.follower_solver_mode` 추가
  - `two_block`: 기존 `NashSolver`
  - `distributed`: 새 `DistributedCoordinator`
- `mpc.distributed_coupling_tol` 추가
- `experiments.run_experiment`에 `--follower-solver-mode` CLI override 추가
- distributed 내부 iteration에서 offset이 실제 control interval의 `max_offset_step`을 누적 위반하지 않도록 최종 offset clamp 추가
- distributed diagnostics 추가
  - `distributed_player_active`
  - `nash_per_agent_active`
  - `distributed_urban_agent_count`
  - `distributed_freeway_agent_count`
  - `distributed_coupling_residual`
  - `agent_U_A_objective`, `agent_F_W_objective` 등 agent별 objective

### 한계

- 이번 구현은 Wu §IV-D 구조를 코드 경로로 넣은 1차 distributed player입니다.
- 각 agent가 완전한 MILP/SQP local optimization을 푸는 단계는 아닙니다.
- Urban agent는 기존 `UrbanFollower` 휴리스틱을 호출한 뒤 자기 signal/movement 변수만 추출합니다.
- Freeway agent는 링크별 local heuristic으로 ramp metering/VSL을 계산합니다.
- 즉, “공간 분산 agent + coupling exchange + per-agent diagnostics”는 구현됐지만, 논문 수준의 exact local optimizer는 다음 단계입니다.

### Distributed Smoke 결과

실행 명령:

```powershell
python -B -m experiments.run_experiment `
  --config src/config/default.yaml `
  --scenario peak_demand `
  --baseline fixed_signal_fixed_speed `
  --controller stackelberg_mpc `
  --T-total 360 `
  --follower-solver-mode distributed `
  --leader-candidate-count 5 `
  --max-nash-iter 3 `
  --output outputs\codex_distributed_player_peak_360_v2
```

결과:

| 항목 | 값 |
|---|---:|
| Total TTT baseline | 30.974 |
| Total TTT distributed proposed | 28.410 |
| Improvement | 8.28% |
| Final acceptance | FAIL |
| distributed player active | 1.0 |
| urban agents | 4 |
| freeway agents | 2 |

Acceptance가 FAIL인 이유:

- Total TTT 기준은 통과했습니다.
- offset validation은 수정 후 PASS입니다.
- 남은 실패는 boundary balance입니다.
  - `urban_net_inflow_tracking_error_veh_h=257.6`
  - `urban_accumulation_abs_error_veh=84.05`

### 검증

- `python -B -m py_compile src\controllers\distributed_coordinator.py src\controllers\stackelberg_mpc.py src\experiments\run_experiment.py src\models\state.py src\tests\test_constraints.py src\tests\test_metanet_equations.py`
- `python -B -m unittest src.tests.test_constraints.ConstraintTests.test_distributed_agent_partition_matches_topology src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics src.tests.test_metanet_equations.MetanetEquationTests.test_config_rejects_invalid_follower_solver_mode -v`
- `python -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_can_use_distributed_follower_solver -v`
- `python -B -m experiments.run_experiment --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --controller stackelberg_mpc --T-total 360 --follower-solver-mode distributed --leader-candidate-count 5 --max-nash-iter 3 --output outputs\codex_distributed_player_peak_360_v2`
- `python -B -m unittest discover -s src\tests -v`

결과:

- Distributed smoke: `FAIL improvement=8.28%`
- 전체 tests: `54 tests OK`

### 다음 작업 제안

1. Urban agent local solve를 기존 global `UrbanFollower` 추출 방식에서 signal별 직접 계산으로 더 분리합니다.
2. Freeway agent local solve를 현재 heuristic에서 링크별 horizon scoring으로 강화합니다.
3. Boundary balance 실패를 줄이기 위해 distributed urban agent가 `N_P_star` net inflow target을 agent별로 분담하도록 수정합니다.

## 2026-06-12: no-control TTT 악화 디버깅

### 구현 및 진단

- `ControlAction.fixed`는 equal green과 함께 movement capacity를 다시 `0.5`로 제한해 green fraction을 이중 적용하고 있었습니다.
- 이 action을 no-control baseline으로 사용하면 urban-to-freeway 유입이 숨은 gating을 받아, 특히 medium/peak/incident의 baseline freeway TTT가 비정상적으로 낮아졌습니다.
- 물리적 no-control을 나타내는 `ControlAction.uncontrolled`를 추가했습니다.
  - equal green, offset 0
  - ramp metering capacity, VSL 100 km/h
  - allocation 미사용: plant saturation flow에 green fraction을 한 번만 적용
- `no_control`, `fixed_signal_fixed_speed`, Wu neutral action이 같은 물리적 action을 사용하도록 수정했습니다.
- Wu coupling의 고정 mainline demand `1650 veh/h`를 시나리오별 forecast demand로 교체했습니다.
- Wu on-ramp coupling의 고정 `green_frac=0.5`를 실제 선택 green 기반 service capacity로 교체했습니다.

변경 파일:

- `src/models/state.py`
- `src/simulation/baseline.py`
- `src/controllers/wu_distributed.py`
- `src/tests/test_six_controller_comparison.py`

### 실행 조건

- config: `src/config/default.yaml`
- seed: `42`
- horizon: `7200 s`
- baseline: `run_closed_loop(..., mode="baseline", baseline_mode="no_control")`
- 비교 controller: `run_controller(..., controller_id="WU-CD-F")`
- 출력: `2026-06-12/results/ttt_debug_after_baseline_fix`

### 7200초 재실행 결과

| scenario | no-control TTT | WU-CD-F TTT | 개선율 | no-control freeway | WU freeway |
|---|---:|---:|---:|---:|---:|
| low | 878.834 | 878.834 | 0.000% | 191.776 | 191.776 |
| medium | 4992.468 | 4989.135 | +0.067% | 2184.953 | 2184.953 |
| peak | 11153.731 | 11254.966 | -0.908% | 3570.359 | 3570.359 |
| oversaturated | 15619.277 | 16060.854 | -2.827% | 4251.869 | 4251.869 |
| incident/capacity-drop | 10629.852 | 10701.738 | -0.676% | 3421.943 | 3421.943 |

Wu freeway TTT가 no-control과 전 시나리오에서 동일하므로, 기존 수천 veh·h 악화는 VSL 동작이 아니라 baseline action 불일치가 원인이었습니다. 남은 차이는 Wu green 조정에 의한 urban TTT입니다.

### 검증

- `python -B -m py_compile ...`: PASS
- `python -B -m unittest src.tests.test_six_controller_comparison -v`: `20 tests OK`
- `python -B -m unittest discover -s src/tests -v`: `101 tests OK`
- closed-loop smoke: 실행 완료, proposed improvement `-1.93%`

### Acceptance 및 남은 실패

- 이번 디버깅의 baseline 물리 일치성: PASS
- boundary queue balancing: 이번 Wu/no-control 원인 분해에서는 별도 acceptance 평가하지 않음
- Wu control validation: authority 테스트 PASS, VSL은 전 구간 100 km/h
- 전체 controller acceptance: **FAIL**
  - WU-CD-F는 요구 개선율 8%를 달성하지 못함
  - corrected baseline 기준 peak/oversaturated/incident에서 소폭 악화
  - closed-loop proposed smoke도 `-1.93%`로 실패

### 다음 수정

Wu urban local objective가 downstream storage와 freeway congestion cost를 충분히 반영하지 못해 혼잡 시 green 변경이 urban TTT를 늘립니다. 다음 단계에서는 이 objective와 green 후보 평가를 coupled horizon 기준으로 보강한 뒤, corrected no-control을 포함한 primary 4-controller 전체 표를 재생성해야 합니다.

## 2026-06-12: 수정 후 original Stackelberg quick validation

### 검증 목적

Baseline allocation 중복 제거와 Leader/follower 구현 오류 수정 후
`PROPOSED-STACKELBERG`의 실제 closed-loop 경로가 정상 작동하는지 짧게 확인했습니다.

적용한 구현 수정:

- Leader `(N_P_star, N_UF_star)` 후보 budget이 낮은 `N_P_star` 쪽으로 편향되지 않도록 전체 후보 공간을 균형 있게 포함
- segment agent의 VSL 제안을 link-level actuator consensus로 병합
- leaderless metering density prediction에 본선 상류 유입 포함

### 실행 조건

- scenario: `peak_demand`
- seed: `42`
- horizon: `720 s`
- control interval: `180 s` (`4 intervals`)
- baseline: corrected `no_control` (`allocation={}`)
- proposed: `PROPOSED-STACKELBERG`, 기본 MPC/Leader 설정
- 출력: `2026-06-12/results/stackelberg_quick_validation`

Baseline 실행:

```text
run_closed_loop(cfg, peak_demand, mode="baseline", baseline_mode="no_control")
```

Proposed 실행:

```text
run_controller(cfg, peak_demand, "PROPOSED-STACKELBERG", output_dir)
```

### 결과

| metric | no-control | Stackelberg | 변화 |
|---|---:|---:|---:|
| Total TTT | 154.516 | 158.370 | -2.49% |
| Urban TTT | 96.323 | 126.288 | +29.965 veh·h |
| Freeway TTT | 58.193 | 32.082 | -26.111 veh·h |
| completed vehicles | 1841.403 | 1965.001 | +123.598 |
| throughput | 9207.014 veh/h | 9825.003 veh/h | +617.989 veh/h |
| terminal total vehicles | 864.282 | 785.930 | -78.352 |

Leader/follower 동작:

- 각 interval Leader 후보 `16개` 평가
- Nash 수렴 `4/4 intervals`
- 평균 Nash iteration `5.75`
- 선택 `N_P_star`: `521.281, 495.217, 521.281, 547.345`
- 선택 `N_UF_star`: `4000, 6000, 4000, 6000`
- metering, VSL, green, offset, allocation 모두 실제 활성

Control validation:

- ramp metering bounds: PASS
- VSL discrete set/change limit: PASS
- green bounds/cycle sum: PASS
- offset range/change limit: PASS
- ramp queue overflow: `0`
- authority validation: PASS
- 평균 `B_in+B_out`: no-control `0.1472` → Stackelberg `0.0783`

### 판정

- controller 실행 경로와 Leader/follower 상호작용: **PASS**
- 제어 feasibility와 boundary balance: **PASS**
- Total TTT 8% 개선 기준: **FAIL** (`-2.49%`)

Freeway TTT 감소와 throughput/terminal state 개선은 확인됐지만, 720초 단기 구간에서 urban TTT 증가가 더 컸습니다. 따라서 original Stackelberg game은 기술적으로 정상 실행되지만, 현재 objective/urban follower가 total TTT를 일관되게 최소화한다고 아직 볼 수 없습니다.

## 2026-06-12: peak 3600초 Stackelberg validation

### 실행 조건

- scenario: `peak_demand`
- seed: `42`
- horizon: `3600 s`
- control interval: `180 s` (`20 intervals`)
- baseline: corrected `no_control` (`allocation={}`)
- controller: 수정된 `PROPOSED-STACKELBERG`
- 출력: `2026-06-12/results/stackelberg_peak_3600_validation`

### 성능 결과

| metric | no-control | Stackelberg | 변화 |
|---|---:|---:|---:|
| Total TTT | 2948.686 | 1958.904 | **+33.57% 개선** |
| Urban TTT | 1461.700 | 1806.921 | 23.62% 증가 |
| Freeway TTT | 1486.986 | 151.983 | **89.78% 감소** |
| completed vehicles | 9093.46 | 11519.00 | +2425.54 |
| throughput | 9093.46 veh/h | 11519.00 veh/h | +26.67% |
| terminal total vehicles | 5307.76 | 2887.43 | -45.60% |
| terminal urban vehicles | 3239.69 | 2729.67 | -510.02 |
| terminal freeway vehicles | 2068.06 | 157.77 | -1910.29 |

### 시간대별 원인

- `0~1080 s`: Stackelberg가 freeway 유입을 조절하면서 urban accumulation이 먼저 증가해 누적 Total TTT가 no-control보다 높음
- `1260 s`: 누적 Total TTT crossover, Stackelberg가 `18.35 veh·h` 우세
- `3600 s`: freeway 이득 `1335.00 veh·h`, urban 손실 `345.22 veh·h`, 순이득 `989.78 veh·h`

대표 상태:

| time | no-control freeway veh | Stackelberg freeway veh | no-control mean density W/E | Stackelberg W/E |
|---|---:|---:|---:|---:|
| 720 s | 406.1 | 142.1 | 48.7 / 84.7 | 20.6 / 22.6 |
| 1260 s | 1419.5 | 162.0 | 173.0 / 185.5 | 25.9 / 25.2 |
| 3600 s | 2068.1 | 157.8 | 219.1 / 230.2 | 27.6 / 21.8 |

No-control은 약 `900~1260 s`부터 freeway breakdown에 진입해 밀도와 TTT가 누적됩니다.
Stackelberg는 단기적으로 도시부 대기를 늘리는 대신 freeway density를 critical density
아래 부근으로 유지하고, 장기적으로 throughput과 terminal state까지 개선했습니다.

### Controller validation

- Leader candidate: interval당 `16개`
- Nash convergence: `20/20 intervals`
- mean Nash iteration: `5.7`
- authority validation: PASS
- ramp queue overflow: `0`
- density exceedance interval: no-control `19`, Stackelberg `8`
- mean boundary balance:
  - no-control `B_in=0.1680`, `B_out=0.0138`
  - Stackelberg `B_in=0.0286`, `B_out=0.0082`

### 판정

- 3600초 Total TTT 8% 기준: **PASS**
- 단기 720초 악화는 초기 urban holding cost가 freeway breakdown 예방 이득보다 먼저 나타나는 transient
- 3600초에서는 예방 이득이 `1260 s`부터 우세해지고 최종 개선율은 `33.57%`

## 2026-06-12: WU-CD-F / WU-CC-F 구현 검토 및 peak 3600초 재실행

### 확인 및 수정 사항

- `WU-CD-F`의 `u_on` coupling이 movement queue와 phase capacity를 각각 합산한 뒤
  `min`을 취해, feasible green split `56/56 -> 92/20`에도 ramp discharge가 변하지
  않던 오류를 수정했다.
- `WU-CD-F` freeway local model의 단일 평균-density 식은 낮은 VSL이 outflow만 줄여
  항상 최고 VSL을 선택하는 구조였다. 동일 multi-segment METANET substep과 ramp
  reservoir/receiving constraint를 사용하는 local rollout으로 교체했다.
- `WU-CC-F`가 Wu global TTS 대신 control-interval 말단 차량 수와 proposed leader
  penalty를 사용하던 목적함수를 수정했다. 이제 coupled plant의 실제 horizon
  `urban_ttt + freeway_ttt`와 green/VSL variation만 사용한다.
- 중앙집중형 smoothness가 green seconds와 VSL km/h를 그대로 더해 같은 계수를
  적용하던 mixed-unit 오류를 수정하고, 각 action range로 정규화했다.
- random search 전에 coordinate bound probe를 추가해 sparse green/VSL 개선을
  탐색할 수 있게 했다.

변경 파일:

- `src/controllers/wu_distributed.py`
- `src/controllers/centralized_mpc.py`
- `src/tests/test_six_controller_comparison.py`

### 실행 명령

Baseline:

```text
run_closed_loop(cfg, peak_demand, mode="baseline", baseline_mode="no_control")
```

WU controllers:

```text
python -B -m src.experiments.six_controller_comparison \
  --scenario peak_demand --T-total 3600 \
  --controllers WU-CD-F,WU-CC-F \
  --output 2026-06-12/results/wu_cd_cc_peak_3600_after_search_fix
```

실패 시도는 `2026-06-12/results/wu_cd_cc_peak_3600_after_fix`에 보존했다.

### 결과

| metric | no-control | WU-CD-F | WU-CC-F |
|---|---:|---:|---:|
| Total TTT [veh-h] | 2948.686 | 2946.105 | 2386.753 |
| Total TTT 개선율 | - | +0.088% | **+19.057%** |
| Urban TTT [veh-h] | 1461.700 | 1459.119 | 1339.491 |
| Freeway TTT [veh-h] | 1486.986 | 1486.986 | 1047.262 |
| Total delay [veh-h] | 2410.820 | 2408.239 | 1848.887 |
| Throughput [veh/h] | 9093.5 | 9111.3 | 9766.8 |
| Terminal total vehicles | 5694.0 | 5676.1 | 5020.6 |
| Terminal on-ramp vehicles | 3547.6 | 3549.3 | 3095.0 |

Boundary 및 control validation:

- mean `B_in`: no-control `0.1680`, WU-CD-F `0.1666`, WU-CC-F `0.1629`
- mean `B_out`: no-control `0.0138`, WU-CD-F `0.0138`, WU-CC-F `0.0080`
- boundary overflow 최대값: 모두 `0`
- ramp queue overflow: 모두 `0`
- authority validation: 두 controller 모두 PASS
- WU-CD-F: D/F green만 `56 -> 44`, VSL은 두 링크 모두 `100`
- WU-CC-F: 5개 signal green 활성, VSL은 두 링크 모두 `100`

Solver 진단:

- WU-CD-F: `820` evaluations, convergence `20/20`, 평균 iteration `1.0`,
  coupling residual 최대 `0`
- WU-CC-F: `1600` evaluations, reported convergence rate `0.9`,
  computation time `265.71 s`

### 판정 및 남은 문제

- `WU-CC-F`: Total TTT 8% 기준과 boundary non-degradation을 모두 만족해 이번
  peak 3600초 실행은 PASS.
- `WU-CD-F`: authority/feasibility는 PASS지만 Total TTT 개선 `0.088%`로 성능
  기준 FAIL.
- `WU-CD-F`의 모든 interval이 iteration 1, residual 0으로 끝났다. 현재
  urban-to-urban arrival와 freeway boundary coupling이 candidate control의 outgoing
  prediction이 아니라 현재 state를 다시 읽는 값이므로, Wu distributed exchange가
  실질적으로 갱신되지 않는 구조가 다음 수정 대상이다.
## 2026-06-16: off-ramp segment topology and storage coupling fix

### Implemented

- Corrected the default freeway off-ramp topology so each three-segment freeway link has one off-ramp on segment 0 and one off-ramp on segment 1:
  - `OR_D_W`, `OR_D_E` -> segment 0
  - `OR_F_W`, `OR_F_E` -> segment 1
- Updated METANET capacity-drop logic to apply `lambda_eff` on each off-ramp's configured segment instead of always the last segment.
- Updated freeway off-ramp outflow to compute per-off-ramp branch flows and per-off-ramp storage caps before vehicles leave the freeway.
- Preserved link-level `offramp_flow_FW_*` diagnostics as aggregates, but changed coupled plant, freeway follower prediction, and Wu distributed prediction to prefer direct `offramp_flow_OR_*` diagnostics.
- Updated the traffic-model spec so off-ramp interaction is segment-aware.
- Added/updated tests for configured off-ramp segment capacity drop and per-off-ramp storage-capacity coupling.

### Files changed

- `docs/spec/03_traffic_models.md`
- `src/config/default.yaml`
- `src/controllers/freeway_follower.py`
- `src/controllers/wu_distributed.py`
- `src/models/metanet.py`
- `src/models/state.py`
- `src/models/urban_queue_model.py`
- `src/simulation/coupling.py`
- `src/tests/test_metanet_equations.py`
- `src/tests/test_six_controller_comparison.py`
- `src/tests/test_constraints.py`

### Run commands

Baseline run command: not run in this topology-fix pass.

Proposed-controller run command: not run in this topology-fix pass.

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\models\metanet.py src\models\urban_queue_model.py src\simulation\coupling.py src\controllers\freeway_follower.py src\controllers\wu_distributed.py src\models\state.py src\tests\test_metanet_equations.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_metanet_equations -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_six_controller_comparison.WuDistributedFixesTests -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_metanet_equations src.tests.test_six_controller_comparison.WuDistributedFixesTests src.tests.test_constraints.ConstraintTests.test_freeway_follower_handles_capacity_drop_with_valid_vsl -v
```

### Metrics

- Baseline Total TTT/TTS: N/A, no closed-loop baseline run in this pass.
- Proposed Total TTT/TTS: N/A, no closed-loop proposed run in this pass.
- Improvement rate: N/A.
- Boundary queue balancing result: N/A for closed-loop metrics; targeted off-ramp storage test passes.
- Control validation summary: compile passed; 21 METANET tests, 5 Wu distributed regression tests, and 1 capacity-drop constraint test passed together (27 tests total).

### Targeted storage-coupling reproduction

With `OR_D_W_storage` full and `OR_F_W_storage` available on the same `FW_W` freeway link:

```text
offramp_flow_OR_D_W = 0.0
offramp_blocked_flow_OR_D_W = 192.0
offramp_flow_OR_F_W = 192.0
offramp_flow_FW_W = 192.0
offramp_flow_total = 192.0
accepted OR_D_W = 0.0, rejected OR_D_W = 0.0
accepted OR_F_W = 0.5333333333333333, rejected OR_F_W = 0.0
```

This verifies that a full first-segment off-ramp no longer causes vehicles from the second-segment off-ramp to be rejected through link-level redistribution.

### Failed criteria and next modification

- Full closed-loop performance criteria were not evaluated in this pass.
- Next modification: rerun the primary 4-controller comparison after this topology fix, because TTT/delay/throughput comparisons before this change used an incorrect off-ramp geometry.

## 2026-06-16: proposed FreewayFollower segment-level VSL correction

### Implemented

- Confirmed a controller-asymmetry bug: Wu distributed controller used segment-level VSL candidates, but the proposed default two-block `FreewayFollower` only explored link-level VSL candidates.
- Updated the proposed `FreewayFollower` to generate segment-vector VSL candidates with keys such as `FW_W__seg0`, `FW_W__seg1`, and `FW_W__seg2`.
- Kept the link-level key as a fallback/summary value so existing diagnostics and compatibility paths still work, while the plant reads segment keys through `segment_vsl`.
- Updated VSL smoothness scoring to compare segment-level VSL values against the previous segment-level action.
- Updated distributed topology test expectations after the off-ramp segment correction.
- Added a regression test that fails if the proposed `FreewayFollower` falls back to link-only VSL candidate generation.

### Files changed

- `src/controllers/freeway_follower.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Run commands

Baseline run command: not run in this controller-granularity pass.

Proposed-controller run command: not run in this controller-granularity pass.

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\freeway_follower.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_freeway_follower_vsl_candidates_are_segment_level src.tests.test_constraints.ConstraintTests.test_vsl_values_are_discrete src.tests.test_constraints.ConstraintTests.test_distributed_agent_partition_matches_topology -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_metanet_equations src.tests.test_six_controller_comparison.WuDistributedFixesTests src.tests.test_constraints.ConstraintTests.test_freeway_follower_handles_capacity_drop_with_valid_vsl src.tests.test_constraints.ConstraintTests.test_freeway_follower_vsl_candidates_are_segment_level src.tests.test_constraints.ConstraintTests.test_vsl_values_are_discrete src.tests.test_constraints.ConstraintTests.test_distributed_agent_partition_matches_topology -v
```

### Metrics

- Baseline Total TTT/TTS: N/A, no closed-loop baseline run in this pass.
- Proposed Total TTT/TTS: N/A, no closed-loop proposed run in this pass.
- Improvement rate: N/A.
- Boundary queue balancing result: N/A for closed-loop metrics.
- Control validation summary: compile passed; 30 related tests passed.

### Failed criteria and next modification

- Full closed-loop performance criteria were not evaluated in this pass.
- Next modification: rerun the primary 4-controller comparison because proposed VSL authority was previously link-level while Wu VSL authority was segment-level.
## 2026-06-16: WU-CD-F peak 3600s VSL activation diagnosis

### Implemented / Run

- Ran `WU-CD-F` for `peak_demand`, `T_total=3600 s`.
- Checked link-level and segment-level VSL time series, capacity-drop diagnostics, off-ramp storage binding, density exceedance, and WU VSL candidate vectors.
- Wrote detailed report: `outputs/wu_cd_f_peak_3600_vsl_diagnosis/vsl_activation_report.md`.

### Commands

Baseline run command: not run in this VSL diagnosis pass.

Proposed-controller run command: not run in this VSL diagnosis pass.

WU run command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --scenario peak_demand --T-total 3600 --controllers WU-CD-F --output outputs\wu_cd_f_peak_3600_vsl_diagnosis
```

### Metrics

- Baseline Total TTT/TTS: N/A.
- WU-CD-F Total TTT/TTS: `2474.438 veh-h`.
- WU-CD-F freeway TTT: `1428.690 veh-h`.
- WU-CD-F urban TTT: `1045.748 veh-h`.
- WU-CD-F total delay: `1936.572 veh-h`.
- WU-CD-F throughput: `9024.1 veh/h`.
- Improvement rate: N/A, no baseline run in this pass.
- Boundary queue balancing result: not evaluated as acceptance criterion in this pass.
- Control validation summary: WU authority ok; VSL remained at `100 km/h` on every link/segment.

### VSL Diagnosis

- VSL active intervals: `0 / 20`.
- Minimum link and segment VSL: `100 km/h`.
- `capacity_drop_active_steps`: `20 / 20`, but max lane loss was only `0.000261 lanes`.
- Max off-ramp occupancy ratio was `0.014189`; off-ramp storage binding and blocked flow were both `0`.
- Current WU candidate vectors after the corrected topology are:
  - `FW_W`: `[100,100,80]`, `[100,100,90]`, `[100,100,100]`
  - `FW_E`: `[100,100,80]`, `[100,100,90]`, `[100,100,100]`
- Because off-ramps are now on segments 0 and 1, the WU candidate rule freezes both off-ramp segments at max/previous VSL and only allows segment 2 to change. Segment 2 is downstream of both off-ramps, so lowering it does not recover off-ramp storage and only adds freeway TTS cost.

### Failed criteria and next modification

- This was not a full acceptance run.
- VSL non-activation is explained by weak physical spillback plus a candidate-set/topology mismatch.
- Next modification: decide whether VSL may be applied on the off-ramp segment itself or add/identify an upstream controllable VSL segment before the first off-ramp.

## 2026-06-16: Upstream simple segment topology and WU-CD-F 3600s VSL rerun

### Implemented / reviewed

- Added one upstream simple freeway segment to each of `FW_W` and `FW_E`.
- `freeway_segments_per_link` changed from `3` to `4`; `freeway_segment_length_km` remains `0.5 km`.
- The new `seg0` has no on-ramp or off-ramp.
- Existing ramp/off-ramp meanings were shifted downstream:
  - D off-ramps: `seg1`
  - F off-ramps: `seg2`
  - D/F on-ramp merge: `seg2`
- Updated topology tests and the Wu distributed regression test so Wu VSL can be checked on the new upstream segment.
- Adjusted `DistributedCoordinator` lane-loss lookup to read the agent's own segment lane profile instead of the last segment.
- Wrote detailed diagnosis: `reports/wu_cd_f_peak_3600_vsl_upstream_segment_report.md`.

### Files changed

- `src/models/state.py`
- `src/config/default.yaml`
- `src/controllers/distributed_coordinator.py`
- `src/tests/test_metanet_equations.py`
- `src/tests/test_constraints.py`
- `src/tests/test_six_controller_comparison.py`
- `reports/wu_cd_f_peak_3600_vsl_upstream_segment_report.md`
- `reports/codex_run_report.md`

### Commands

Baseline run command: not run in this pass.

Proposed-controller run command: not run in this pass.

WU run command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --scenario peak_demand --T-total 3600 --controllers WU-CD-F --output outputs\wu_cd_f_peak_3600_vsl_upstream_segment
```

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\models\state.py src\models\metanet.py src\controllers\distributed_coordinator.py src\controllers\wu_distributed.py src\tests\test_metanet_equations.py src\tests\test_constraints.py src\tests\test_six_controller_comparison.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_metanet_equations src.tests.test_constraints.ConstraintTests.test_distributed_agent_partition_matches_topology src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics src.tests.test_constraints.ConstraintTests.test_leaderless_metering_prediction_includes_upstream_mainline_flow src.tests.test_constraints.ConstraintTests.test_freeway_follower_handles_capacity_drop_with_valid_vsl src.tests.test_constraints.ConstraintTests.test_freeway_follower_vsl_candidates_are_segment_level src.tests.test_six_controller_comparison.WuDistributedFixesTests -v
```

### Metrics

- Baseline Total TTT/TTS: N/A.
- Proposed Total TTT/TTS: N/A.
- WU-CD-F Total TTT/TTS: `2474.384 veh-h`.
- WU-CD-F freeway TTT: `1525.292 veh-h`.
- WU-CD-F urban TTT: `949.092 veh-h`.
- WU-CD-F total delay: `1905.065 veh-h`.
- WU-CD-F throughput: `9108.2 veh/h`.
- Improvement rate: N/A, no baseline comparison in this pass.
- Boundary queue balancing result: not evaluated as acceptance criterion in this pass.

### Control validation summary

- `py_compile`: PASS.
- Related unit tests: `31` tests PASS.
- WU-CD-F 3600s run completed and `authority_ok=True`.
- VSL activation:
  - Any VSL active interval: `17 / 20`.
  - `FW_W seg0`: active `15 / 20`, min `50 km/h`.
  - `FW_E seg0`: active `17 / 20`, min `50 km/h`.
  - `seg1`, `seg2`, and `seg3` remained `100 km/h` on both links.
- Spillback/storage:
  - `capacity_drop_active=1`, but max lane loss is still tiny (`~0.000247 lanes`).
  - `offramp_storage_binding=0`.
  - `offramp_blocked_flow_total=0`.

### Failed criteria and next modification

- This is not a full acceptance run.
- The topology issue is resolved: Wu VSL can now activate on an upstream plain segment.
- Remaining issue: the `peak_demand` 3600s scenario still does not create binding off-ramp storage, so VSL activation is not yet evidence of strong spillback mitigation.
- Next modification: run the full 4-controller comparison on the new topology, and separately design a stronger spillback scenario if the research question is specifically VSL response to off-ramp storage saturation.

## 2026-06-16: Full primary 4-controller scenario comparison, 3600s

### Implemented / run

- Ran all configured scenarios with the primary 4-controller set:
  - `WU-CD-F`
  - `PROPOSED-FOLLOWERS-ONLY`
  - `PROPOSED-STACKELBERG`
  - `PROPOSED-CENTRALIZED`
- Horizon: `3600 s`.
- Topology: 4-segment freeway links with upstream simple `seg0`.
- Output root: `outputs/four_controller_all_scenarios_3600_upstream_segment`.
- Detailed report: `reports/four_controller_all_scenarios_3600_upstream_segment_report.md`.

### Commands

Baseline run command: not applicable as a no-control baseline; this pass uses spec 16 pairwise baselines between controllers.

Proposed-controller run command pattern:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --scenario <scenario> --T-total 3600 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --output outputs\four_controller_all_scenarios_3600_upstream_segment\<scenario>
```

### Scenario metrics

| Scenario | Best TTT controller | WU-CD-F TTT | P-FO TTT | P-Stack TTT | P-Cent TTT |
|---|---|---:|---:|---:|---:|
| low_demand | WU-CD-F | 347.823 | 405.402 | 450.171 | 377.590 |
| medium_demand | WU-CD-F | 529.830 | 1047.055 | 912.089 | 932.878 |
| peak_demand | PROPOSED-CENTRALIZED | 2474.384 | 1712.395 | 1831.105 | 1626.092 |
| oversaturated_demand | PROPOSED-CENTRALIZED | 4482.918 | 2915.558 | 3248.717 | 2810.376 |
| incident_or_capacity_drop | PROPOSED-CENTRALIZED | 2218.689 | 1646.729 | 1679.822 | 1554.556 |
| capacity_drop | WU-CD-F | 8012.501 | 8411.293 | 10269.381 | 9326.771 |

### Main findings

- `peak_demand`: `PROPOSED-STACKELBERG` improves TTT by `26.00%` vs `WU-CD-F`; `PROPOSED-CENTRALIZED` improves by `34.28%`.
- `oversaturated_demand`: `PROPOSED-STACKELBERG` improves TTT by `27.53%`; `PROPOSED-CENTRALIZED` improves by `37.31%`.
- `incident_or_capacity_drop`: `PROPOSED-STACKELBERG` improves TTT by `24.29%`; `PROPOSED-CENTRALIZED` improves by `29.93%`.
- `low_demand` and `medium_demand`: proposed controllers are worse than `WU-CD-F`.
- `capacity_drop`: proposed controllers are worse than `WU-CD-F`; `PROPOSED-STACKELBERG` is the worst case with `10269.381 veh-h` TTT and `7775.1 veh/h` throughput.

### Failed criteria and next modification

- Full acceptance is not claimed.
- Proposed Stackelberg does not dominate across scenarios and fails the `capacity_drop` stress case.
- Low/medium demand also show unnecessary control restriction relative to Wu.
- Next modification: diagnose why the Leader/allocation layer worsens throughput and terminal vehicles in `capacity_drop`, then rerun at least `capacity_drop`, `medium_demand`, and `peak_demand` before any full 7200s run.

## 2026-06-16: freeway upstream plain segment topology update

### 구현 내용

- `FW_W`, `FW_E` 각각의 기존 segment 0 앞에 동일 길이 `0.5 km` upstream plain segment를 추가하는 형태로 기본 topology를 재구성했습니다.
- `freeway_segments_per_link`를 `3 -> 4`로 늘렸고, 기존 segment length는 유지했습니다. 따라서 link당 총 freeway 길이는 `1.5 km -> 2.0 km`가 됩니다.
- 새 segment 0에는 on-ramp/off-ramp가 붙지 않도록 기존 segment-level 연결을 한 칸 downstream으로 이동했습니다.
  - on-ramp merge: `R_D_W`, `R_F_W`, `R_D_E`, `R_F_E` = segment 2
  - off-ramp: `OR_D_W`, `OR_D_E` = segment 1
  - off-ramp: `OR_F_W`, `OR_F_E` = segment 2
- topology/diagnostics 테스트를 4-segment agent partition과 새 off-ramp index에 맞춰 갱신했습니다.
- Wu regression fixture를 새 topology에 맞춰 갱신했고, Wu가 off-ramp 병목 segment는 max VSL로 유지하면서 upstream plain segment `seg0`에서 VSL 후보를 낮출 수 있음을 검증하도록 수정했습니다.

### 변경 파일

- `src/models/state.py`
- `src/config/default.yaml`
- `src/tests/test_constraints.py`
- `src/tests/test_metanet_equations.py`
- `src/tests/test_six_controller_comparison.py`
- `reports/codex_run_report.md`

### 실행 명령

Baseline run command: not run in this topology-only pass.

Proposed-controller run command: not run in this topology-only pass.

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\models\state.py src\models\metanet.py src\tests\test_constraints.py src\tests\test_metanet_equations.py src\tests\test_six_controller_comparison.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_metanet_equations src.tests.test_constraints src.tests.test_six_controller_comparison.WuDistributedFixesTests -v
```

### 지표

- Baseline Total TTT/TTS: N/A, closed-loop baseline not run.
- Proposed Total TTT/TTS: N/A, closed-loop proposed controller not run.
- Improvement rate: N/A.
- Boundary queue balancing result: N/A, no closed-loop acceptance run in this pass.
- Control validation summary: compile passed; related unit/regression tests `59 tests OK`.

### 실패 기준 및 다음 수정

- Full acceptance criteria are not evaluated in this pass because no closed-loop baseline/proposed simulation was run.
- Remaining risk: total freeway length changed from `1.5 km` to `2.0 km`; future closed-loop comparisons should be regenerated under the new topology before interpreting TTT improvements.

## 2026-06-17: relaxed-quantized fast controller mode implementation

### 구현 내용

- `docs/spec/17_relaxed_quantized_fast_mode.md` 기준으로 relaxed-quantized controller mode를 추가했습니다.
- `mpc.relaxed_quantized_controls=false` 기본값에서는 기존 full/grid/enumeration 경로가 유지되도록 분기했습니다.
- 명시 config/dataclass 필드 추가: `relaxed_quantized_controls`, `relaxed_fast_mode`, `relaxed_green_quantum_sec`, `relaxed_vsl_quantum_km_h`, `relaxed_rounding_mode`, `relaxed_wu_vsl_include_neutral`.
- 공통 green/VSL quantization/repair helper를 추가했습니다.
- WU-CD-F relaxed mode에서 urban green 7-point grid를 pressure split + repair로 대체하고, freeway segment-level VSL full Cartesian enumeration을 relaxed target vector 및 optional neutral max-VSL vector 평가로 축소했습니다.
- proposed followers / Stackelberg distributed follower는 relaxed mode에서 green split과 heuristic VSL output을 공통 repair로 통과합니다.
- centralized MPC는 relaxed mode에서 vector decode 후 green/VSL 공통 repair를 적용합니다.
- `--relaxed-fast-mode` CLI는 relaxed mode를 켜고 screening budget(`leader_candidate_count=5`, `max_nash_iter=3`, `optimizer_maxiter=16`, `optimizer_n_starts=1`, `freeway_prediction_horizon_steps=3`)을 명시적으로 적용합니다.
- six-controller decision diagnostics에 relaxed mode flag와 quantization/repair diagnostic columns를 추가했습니다.

### 변경 파일

- `src/config/default.yaml`
- `src/controllers/centralized_mpc.py`
- `src/controllers/distributed_coordinator.py`
- `src/controllers/freeway_follower.py`
- `src/controllers/relaxed_quantization.py`
- `src/controllers/urban_follower.py`
- `src/controllers/wu_distributed.py`
- `src/experiments/six_controller_comparison.py`
- `src/models/state.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### 실행 명령

Baseline run command: not run in this implementation-only pass.

Proposed-controller run command: not run in this implementation-only pass.

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\models\state.py src\controllers\relaxed_quantization.py src\controllers\wu_distributed.py src\controllers\urban_follower.py src\controllers\freeway_follower.py src\controllers\distributed_coordinator.py src\controllers\centralized_mpc.py src\experiments\six_controller_comparison.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_six_controller_comparison -v
```

### 지표

- Baseline Total TTT/TTS: N/A, full 3600s baseline simulation was not run by this subagent.
- Proposed Total TTT/TTS: N/A, full 3600s proposed simulation was not run by this subagent.
- Improvement rate: N/A.
- Boundary queue balancing result: N/A, no closed-loop acceptance comparison was run.
- Control validation summary:
  - `py_compile`: PASS.
  - `src.tests.test_constraints`: `38 tests OK`.
  - `src.tests.test_six_controller_comparison`: `29 tests OK`.

### 실패 기준 및 다음 수정

- Full acceptance is not claimed.
- Full 3600s simulations were not run in this pass.
- Remaining risk: relaxed-mode performance is only unit/smoke-wiring validated here; a 3600s primary four-controller run with explicit relaxed config is still needed before interpreting computation-time and TTT trade-offs.

## 2026-06-17: relaxed-fast 4-controller 6-scenario 3600s screening

### 구현 내용

- Review subagent 지적사항을 반영했습니다.
- `--relaxed-quantized-controls`, `--relaxed-fast-mode`, quantization 관련 CLI flag를 추가했습니다.
- `--relaxed-fast-mode`가 screening budget을 실제 override하도록 수정했습니다.
- green/VSL quantization residual과 repair count가 `ControlAction.diagnostics` 및 decision diagnostics에 기록되도록 연결했습니다.
- `validate_controls`가 link aggregate VSL뿐 아니라 segment VSL step 변화도 검사하도록 확장했습니다.
- 상세 결과 report를 `reports/relaxed_fast_4controllers_3600_report.md`에 작성했습니다.

### 변경 파일

- `src/config/default.yaml`
- `src/models/state.py`
- `src/controllers/relaxed_quantization.py`
- `src/controllers/wu_distributed.py`
- `src/controllers/urban_follower.py`
- `src/controllers/freeway_follower.py`
- `src/controllers/distributed_coordinator.py`
- `src/controllers/centralized_mpc.py`
- `src/controllers/nash_solver.py`
- `src/experiments/six_controller_comparison.py`
- `src/evaluation/metrics.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`
- `reports/relaxed_fast_4controllers_3600_report.md`

### 실행 명령

Baseline run command: pairwise Stage 1 comparison uses `WU-CD-F` / `PROPOSED-FOLLOWERS-ONLY` / `PROPOSED-STACKELBERG` / `PROPOSED-CENTRALIZED`; no separate no-control baseline was run in this screening.

Proposed-controller run command pattern:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --scenario <scenario> --T-total 3600 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --relaxed-quantized-controls --relaxed-fast-mode --output outputs\relaxed_fast_4controllers_3600\<scenario>
```

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\models\state.py src\controllers\relaxed_quantization.py src\controllers\wu_distributed.py src\controllers\urban_follower.py src\controllers\freeway_follower.py src\controllers\distributed_coordinator.py src\controllers\centralized_mpc.py src\controllers\nash_solver.py src\experiments\six_controller_comparison.py src\evaluation\metrics.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints src.tests.test_six_controller_comparison -v
```

### 지표

- Output root: `outputs/relaxed_fast_4controllers_3600`
- Combined summary: `outputs/relaxed_fast_4controllers_3600/combined_summary.csv`
- Combined paired comparisons: `outputs/relaxed_fast_4controllers_3600/combined_paired_comparisons.csv`
- Detailed report: `reports/relaxed_fast_4controllers_3600_report.md`
- Wall-clock runtime for all 24 runs: `910.4 s`.
- Sum of controller-reported computation time: `880.74 s`.
- Baseline Total TTT/TTS: pairwise baseline depends on comparison; see detailed report.
- Proposed Total TTT/TTS: see detailed report.
- Improvement rate:
  - Proposed followers-only improves over WU in `peak_demand` (`38.07%` delay), `oversaturated_demand` (`39.20%`), and `incident_or_capacity_drop` (`32.09%`).
  - Proposed followers-only worsens against WU in `low_demand`, `medium_demand`, and `capacity_drop`.
  - Proposed Stackelberg is worse than proposed followers-only in all six scenarios in this relaxed-fast run.
- Boundary queue balancing result: not separately accepted in this Stage 1 screening; terminal state and throughput are reported in the detailed report.
- Control validation summary:
  - `py_compile`: PASS.
  - `src.tests.test_constraints + src.tests.test_six_controller_comparison`: `67 tests OK`.
  - Review subagent final verdict: PASS for relaxed 3600s four-controller/six-scenario screening, one scenario per invocation.
  - `authority_ok=True` for all 24 controller/scenario runs.
  - relaxed/fast flags recorded as active for all decision rows.

### 실패 기준 및 다음 수정

- Computation-cost screening: PASS.
- Full controller acceptance: FAIL / not claimed.
- Failure reasons:
  - `PROPOSED-STACKELBERG` does not consistently improve over `WU-CD-F`.
  - `PROPOSED-STACKELBERG` is worse than `PROPOSED-FOLLOWERS-ONLY` in all six scenarios under the relaxed-fast budget.
  - Solver convergence rates remain low for `PROPOSED-STACKELBERG` and `PROPOSED-CENTRALIZED`.
- Proposed next modification:
  - Diagnose why the leader/allocation layer degrades the follower-only solution under relaxed-fast screening.
  - Revisit leader candidate objective/selection and allocation coupling before treating Stackelberg performance as valid.

## 2026-06-17: Leader Objective Term Logging and Residual Penalty Patch

### 구현 내용

- `Leader.objective_terms()`를 추가하여 leader objective를 다음 term으로 분해해 로그에 남기도록 했다.
  - `leader_base_accumulation`
  - `leader_state_accumulation_base`
  - `leader_follower_ttt_base`
  - `leader_boundary_leg_excluded_veh`
  - `leader_target_penalty`
  - `leader_density_excess`
  - `leader_density_penalty`
  - `leader_density_effective_lane_weight_count`
  - `leader_smoothness_penalty`
  - `leader_nonconvergence_penalty`
  - `leader_total_objective`
- `state_accumulation` base에서 외부 `boundary_in`/`boundary_out` leg queue와 boundary-out sink storage를 제외하는 config를 추가했다.
  - 기본값: `leader.state_accumulation_exclude_boundary_legs: true`
  - 내부 grid, on-ramp, off-ramp 관련 queue/storage는 계속 objective base에 포함한다.
- Nash non-convergence penalty를 고정 binary penalty에서 residual 기반 penalty로 바꿨다.
  - `non_convergence_penalty * (objective_residual / objective_scale + control_residual / control_scale)`
  - 기본 scale: 둘 다 `1.0`
- freeway density penalty는 lane drop/effective lane이 실제 nominal lane과 달라진 segment에서만 `lambda_eff`를 weight로 사용한다.
  - 기본값: `leader.use_effective_lanes_for_density_penalty: true`
- throughput/terminal backlog penalty는 이번 요청대로 보류했다.

### 변경 파일

- `src/config/default.yaml`
- `src/controllers/leader.py`
- `src/controllers/stackelberg_mpc.py`
- `src/experiments/six_controller_comparison.py`
- `src/models/state.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### 실행 명령

Baseline smoke command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --scenario low_demand --T-total 360 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --relaxed-quantized-controls --relaxed-fast-mode --output outputs\leader_objective_term_smoke_pair
```

Proposed-controller smoke command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --scenario low_demand --T-total 360 --controllers PROPOSED-STACKELBERG --relaxed-quantized-controls --relaxed-fast-mode --output outputs\leader_objective_term_smoke
```

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\leader.py src\controllers\stackelberg_mpc.py src\models\state.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\experiments\six_controller_comparison.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints src.tests.test_six_controller_comparison -v
```

### Smoke 결과

Output root: `outputs/leader_objective_term_smoke_pair`

| Controller | Total TTT/TTS | Total Delay | Freeway TTT | Urban TTT | Throughput | Terminal Total | Solver Converged |
|---|---:|---:|---:|---:|---:|---:|---:|
| `PROPOSED-FOLLOWERS-ONLY` | 33.729 | 3.562 | 11.355 | 22.374 | 7252.1 | 406.3 | 0.5 |
| `PROPOSED-STACKELBERG` | 36.293 | 6.126 | 9.754 | 26.540 | 6504.6 | 481.0 | 0.0 |

Improvement rate against the follower-only smoke baseline:

```text
100 * (33.729 - 36.293) / 33.729 = -7.60%
```

Boundary queue balancing result: full acceptance evaluation was not run in this short smoke; authority check was `True` for both controllers.

Control validation summary:

- `py_compile`: PASS.
- `src.tests.test_constraints + src.tests.test_six_controller_comparison`: PASS, `69 tests OK`.
- Closed-loop smoke: PASS for execution/logging, but not a performance acceptance run.
- New leader objective term columns were observed in both `decision_diagnostics.csv` and `control_timeseries.csv`.

### 실패 기준 및 다음 수정

- Full controller acceptance: FAIL / not claimed.
- The short smoke still shows `PROPOSED-STACKELBERG` worse than `PROPOSED-FOLLOWERS-ONLY`; this patch is diagnostic/objective-alignment work, not a performance fix claim.
- Next modification:
  - Re-run a longer targeted scenario after inspecting the new term breakdown.
  - Focus on why Stackelberg still shifts delay from freeway to urban when Nash convergence is poor.

## 2026-06-17: Peak 7200s leader diagnosis, current code before demand-compatible ceiling implementation

### What was implemented

- No controller fix was applied in this attempt.
- Ran a targeted 7200s `peak_demand` comparison to diagnose why the Stackelberg leader does not keep the protected-network accumulation near the critical target under peak demand.
- Inspected leader targets, actual accumulation, freeway/urban TTT split, throughput, terminal vehicles, convergence, and allocation logs.

### Files changed

- `reports/codex_run_report.md`

Generated output directory:

```text
outputs\peak_7200_leader_diagnosis_current
```

### Run commands

Baseline follower-only command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --scenario peak_demand --T-total 7200 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --relaxed-quantized-controls --relaxed-fast-mode --output outputs\peak_7200_leader_diagnosis_current
```

Proposed Stackelberg command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --scenario peak_demand --T-total 7200 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --relaxed-quantized-controls --relaxed-fast-mode --output outputs\peak_7200_leader_diagnosis_current
```

### Metric comparison

| Controller | Total TTT/TTS | Total Delay | Freeway TTT | Urban TTT | Throughput | Terminal Total | Solver Converged |
|---|---:|---:|---:|---:|---:|---:|---:|
| `PROPOSED-FOLLOWERS-ONLY` | 7172.074 | 6028.054 | 1579.712 | 5592.361 | 10839.8 | 7688.8 | 0.975 |
| `PROPOSED-STACKELBERG` | 8638.964 | 7494.944 | 336.029 | 8302.935 | 10321.1 | 8726.2 | 0.0 |

Improvement rate against follower-only:

```text
100 * (7172.074 - 8638.964) / 7172.074 = -20.45%
```

Delay improvement:

```text
100 * (6028.054 - 7494.944) / 6028.054 = -24.33%
```

Boundary queue / accumulation result:

- `N_P_crit = 556.081`.
- Follower-only `N_P` mean/final: `854.24 / 1593.33`.
- Stackelberg `N_P` mean/final: `958.42 / 1633.88`.
- Follower-only `N_P` excess area over critical: `770.24 veh*h`.
- Stackelberg `N_P` excess area over critical: `948.67 veh*h`.
- Result: FAIL. The leader path does not hold `N_P` at or near the critical value; it worsens protected-network over-critical exposure.

Control validation summary:

- Both controllers pass authority validation.
- Stackelberg dramatically lowers freeway TTT (`1579.712 -> 336.029`) and ramp/on-ramp queues, but this is not a network benefit because urban TTT rises much more (`5592.361 -> 8302.935`), throughput falls, and terminal vehicles increase.
- The Stackelberg run is also Nash-nonconverged over this run (`solver_converged_rate = 0.0`).

### Main diagnostic finding

The dominant current-code issue appears to be a hidden control-path asymmetry rather than only a leader objective-weight issue.

- `ControlAction.uncontrolled()` leaves `inflow_outflow_allocation` empty, so follower-only plant simulation falls back to the physical movement saturation capacity.
- `ControlAction.fixed()` initializes every urban movement allocation to `0.5 * movement_capacity_veh_h`.
- The Stackelberg coordinator starts from `ControlAction.fixed()` when a leader is present.
- The merge step starts from `current.inflow_outflow_allocation`, so movements not explicitly overwritten by the allocation module keep the fixed half-capacity values.
- The allocation module controls boundary/ramp-related movements, but internal urban movements are not explicitly replanned; therefore internal urban movements stay capped at `700 veh/h` in the Stackelberg path while follower-only effectively uses `1400 veh/h` fallback capacity.

Observed from `control_timeseries.csv`:

- Follower-only internal movement allocation values are absent/zero in the log, matching empty allocation fallback behavior.
- Stackelberg internal movement allocation values are exactly `700.0 veh/h` throughout.

This explains the peak failure pattern: the leader protects freeway/ramp states and lowers freeway TTT, but the urban network is silently capacity-throttled internally, so protected-network accumulation cannot be regulated near critical and urban TTT/terminal backlog grow.

### Failed criteria and next modification

- Full acceptance: FAIL.
- Total TTT/TTS improvement is negative.
- Delay improvement is negative.
- Throughput is lower.
- Terminal total vehicles are higher.
- `N_P` critical regulation is worse.
- Nash convergence is poor.

Proposed next modification:

- Remove the hidden internal-movement half-capacity cap from the leader-enabled path before changing leader theory.
- Use an uncontrolled/empty allocation fallback for non-controlled movements, or explicitly clear non-allocation-module/internal movement keys before plant simulation.
- Re-run the same `peak_demand` 7200s follower-only vs Stackelberg comparison after that fix.

## 2026-06-17 Step D — Leader Objective Formula Alignment

### What was implemented

- Aligned the default proposed Stackelberg leader objective with the user's formula.
- Changed the default leader base from `state_accumulation` to follower-response TTT/TTS (`follower_ttt`).
- Removed `boundary_in_queue_penalty` from `leader_total_objective`; it remains diagnostic-only.
- Removed `non_convergence_penalty` from `leader_total_objective`; it remains diagnostic-only.
- Updated controller spec, configuration requirements, default config, and Step D unit tests.

### Files changed

- `src/controllers/leader.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `docs/spec/04_controller.md`
- `docs/spec/07_auto_diagnosis.md`
- `docs/spec/09_configuration_requirements.md`
- `src/tests/test_constraints.py`
- `src/tests/test_metanet_equations.py`
- `src/tests/test_offramp_reattribution.py`
- `2026-06-17/proposed_controller_refactor_execution.md`

### Commands

Baseline run command:

```text
Not run for Step D. This was a formula-alignment/unit-test step.
```

Proposed-controller run command:

```text
Not run for Step D. This was a formula-alignment/unit-test step.
```

Unit test command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints src.tests.test_metanet_equations src.tests.test_offramp_reattribution -v
```

Result:

```text
70 tests, OK
```

### Metrics

Baseline Total TTT/TTS: not run.

Proposed Total TTT/TTS: not run.

Improvement rate: not computed for Step D.

Boundary queue balancing result: not run.

Control validation summary: Step D unit tests confirm that `leader_total_objective` now uses the follower TTT/TTS base by default, while boundary-in queue and non-convergence penalties remain logged diagnostics only.

### Review

- Coding subagent: `Ptolemy`.
- Review subagent: `Hypatia`, verdict `PASS_WITH_NOTES`.
- Codex final review: PASS after updating the stale `boundary_in_queue_vehicles()` comment and this report.

### Failed criteria and next modification

- Full acceptance remains unevaluated because no closed-loop simulation was run for this step.
- Next modification: Step C, port Wu-style neighbor coupling into the proposed distributed follower.

## 2026-06-17 Step C — Wu-Style Neighbor Coupling For Proposed Distributed Follower

### What was implemented

- Ported Wu-style neighbor coupling into the proposed `DistributedCoordinator`.
- `urban -> freeway`: `u_on_*` now uses ramp-space-cap-free on-ramp reservoir inflow from current green decisions.
- `freeway(off-ramp) -> urban`: selected off-ramp predicted arrival and storage pressure are passed into urban phase pressure.
- `urban -> urban`: upstream green release rate is converted into downstream phase arrival pressure using same-origin/same-phase beta sums.
- `freeway -> freeway`: adjacent segment density, speed, flow, and lane-loss pressure are exposed through coupling and used in freeway agent VSL/metering decisions.
- Added direction-aware coupling diagnostics for ablation interpretation.

### Files changed

- `src/controllers/distributed_coordinator.py`
- `src/controllers/urban_follower.py`
- `src/tests/test_forecast_awareness.py`
- `src/tests/test_constraints.py`
- `2026-06-17/proposed_controller_refactor_execution.md`

### Commands

Baseline run command:

```text
Not run for Step C. This was a controller-coupling/unit-test step.
```

Proposed-controller run command:

```text
Not run for Step C. This was a controller-coupling/unit-test step.
```

Syntax check:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\distributed_coordinator.py src\controllers\urban_follower.py src\tests\test_forecast_awareness.py src\tests\test_constraints.py
```

Result: OK.

Focused Step C test command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_forecast_awareness.ForecastAwarenessTests.test_onramp_coupling_preserves_green_difference_when_ramp_full src.tests.test_forecast_awareness.ForecastAwarenessTests.test_upstream_green_release_enters_downstream_phase_coupling src.tests.test_forecast_awareness.ForecastAwarenessTests.test_urban_follower_uses_selected_offramp_arrival_response src.tests.test_constraints.ConstraintTests.test_distributed_freeway_agent_reports_neighbor_pressure src.tests.test_constraints.ConstraintTests.test_distributed_ablation_diagnostics_report_blocked_coupling -v
```

Result:

```text
5 tests, OK
```

Broader Step C test command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_forecast_awareness src.tests.test_constraints -v
```

Result:

```text
52 tests, 50 OK, 2 failures
```

The two remaining failures are the already scheduled later steps:

- `test_leader_candidates_reflect_forecast_summary`: Step B will replace candidate-set comparison with candidate evaluation/ranking/selection sensitivity.
- `test_freeway_vsl_uses_future_offramp_inflow`: Step A will adjust the saturated VSL fixture/objective check.

### Metrics

Baseline Total TTT/TTS: not run.

Proposed Total TTT/TTS: not run.

Improvement rate: not computed for Step C.

Boundary queue balancing result: not run.

Control validation summary: focused Step C tests confirm urban->freeway, freeway->urban, urban->urban, freeway->freeway coupling paths and ablation diagnostics.

### Review

- Coding subagent: `Anscombe`.
- Review subagent: `Meitner`, initial verdict `PASS_WITH_NOTES`.
- Codex final review: PASS after addressing review notes.
- Re-review verdict: `PASS_WITH_NOTES`; previous findings were substantially resolved. Remaining note is only that `LOCAL_ONLY_COUPLING_PLAYERS` is summarized globally rather than per-agent.

### Failed criteria and next modification

- Full acceptance remains unevaluated because no closed-loop simulation was run for this step.
- Next modification: Step B, replace the leader forecast test with evaluation/ranking/selection sensitivity.

## 2026-06-17 Step B — Leader Forecast Evaluation Test

### What was implemented

- Replaced the leader forecast test assumption that forecast must change the candidate set.
- Added compact candidate evaluation metadata to `StackelbergMPCController.decide_with_info()`.
- The test now checks whether future forecast changes candidate evaluation, ranking, objective spread, or selected leader action even when candidate set summaries are identical.

### Files changed

- `src/controllers/stackelberg_mpc.py`
- `src/tests/test_forecast_awareness.py`
- `2026-06-17/proposed_controller_refactor_execution.md`

### Commands

Baseline run command:

```text
Not run for Step B. This was a diagnostic/test-design step.
```

Proposed-controller run command:

```text
Not run for Step B. This was a diagnostic/test-design step.
```

Syntax check:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\stackelberg_mpc.py src\tests\test_forecast_awareness.py
```

Result: OK.

Focused Step B test command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_forecast_awareness.ForecastAwarenessTests.test_leader_candidates_reflect_forecast_summary -v
```

Result:

```text
1 test, OK
```

Forecast-awareness suite:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_forecast_awareness -v
```

Result:

```text
8 tests, 7 OK, 1 failure
```

The remaining failure is the scheduled Step A VSL saturation test:

- `test_freeway_vsl_uses_future_offramp_inflow`

### Metrics

Baseline Total TTT/TTS: not run.

Proposed Total TTT/TTS: not run.

Improvement rate: not computed for Step B.

Boundary queue balancing result: not run.

Control validation summary: Step B confirms leader forecast sensitivity through candidate evaluation/ranking/selection metadata rather than requiring candidate-set changes.

### Review

- Coding subagent: `Erdos`.
- Review subagent: `Harvey`, verdict `PASS_WITH_NOTES`.
- Codex final review: PASS after adding the reviewer's recommended identical-candidate-set guard and separate previous-control objects for low/high forecast runs.

### Failed criteria and next modification

- Full acceptance remains unevaluated because no closed-loop simulation was run for this step.
- Next modification: Step E, recalibrate `N_P_crit_veh` after D/C/B controller semantics changed.
