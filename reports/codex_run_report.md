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
