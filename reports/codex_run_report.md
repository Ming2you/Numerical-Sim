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

## 2026-06-17 Step E - N_P_crit_veh Recalibration

### What was implemented

- Reused the existing `src.experiments.calibrate_setpoints` CLI for a baseline MFD sweep under the current protected-accumulation semantics.
- Added the exact accumulation source to the calibration report: `state_timeseries.csv` field `urban_protected_accumulation_veh`, produced by `TrafficState.protected_accumulation_veh(net)`.
- Made calibration fail fast if `urban_protected_accumulation_veh` is absent, so stale `urban_vehicles` rows cannot silently recalibrate `N_P_crit_veh`.
- Updated `leader.N_P_crit_veh` from stale `556.081` to `509.448830418254` based on the new off-ramp-storage-excluding protected accumulation.
- Updated the matching dataclass default and config unit-test expectation.

### Files changed

- `src/experiments/calibrate_setpoints.py`
- `src/config/default.yaml`
- `src/models/state.py`
- `src/tests/test_metanet_equations.py`
- `2026-06-17/proposed_controller_refactor_execution.md`
- `reports/codex_run_report.md`

### Commands

Baseline/calibration run command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.calibrate_setpoints --config src/config/default.yaml --scenario peak_demand --baseline fixed_signal_fixed_speed --urban-scales 0.5,0.75,1.0,1.25,1.5,2.0,2.5,3.0 --T-total 7200 --output outputs/step_e_n_p_crit_recalibration_2026_06_17
```

Result:

```text
CALIBRATION n_crit=509.449 max_production=33868.583 output=outputs\step_e_n_p_crit_recalibration_2026_06_17
```

Proposed-controller run command:

```text
Not run for Step E. The user explicitly requested no long full simulation; this step is calibration/config/test only.
```

Syntax check:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\experiments\calibrate_setpoints.py src\models\state.py src\tests\test_metanet_equations.py src\tests\test_closed_loop_smoke.py src\tests\test_offramp_reattribution.py
```

Result: OK.

Focused tests:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_metanet_equations.MetanetEquationTests.test_config_exposes_time_ratios_and_units src.tests.test_closed_loop_smoke.ClosedLoopSmokeTest.test_setpoint_calibration_smoke_outputs_required_files src.tests.test_offramp_reattribution.OffRampReattributionTests.test_np_and_urban_total_exclude_offramp_storage_keep_leg -v
```

Result:

```text
3 tests, OK
```

Related model/config test module:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_metanet_equations -v
```

Result:

```text
21 tests, OK
```

### Calibration Output

- Output directory: `outputs/step_e_n_p_crit_recalibration_2026_06_17`
- Summary JSON: `outputs/step_e_n_p_crit_recalibration_2026_06_17/setpoint_calibration_summary.json`
- MFD points CSV: `outputs/step_e_n_p_crit_recalibration_2026_06_17/mfd_points.csv`
- Report: `outputs/step_e_n_p_crit_recalibration_2026_06_17/setpoint_calibration_report.md`
- New `N_P_crit_veh`: `509.448830418254 veh`
- Maximum observed production: `33868.58320594422 veh/h`
- Source point: `urban_scale=3.0`, `time_sec=720.0`

Baseline Total TTT/TTS for calibration sweep:

```text
urban_scale=0.5  total_ttt=5344.72517791123
urban_scale=0.75 total_ttt=7477.80195272855
urban_scale=1.0  total_ttt=9593.220960234255
urban_scale=1.25 total_ttt=11659.562092097874
urban_scale=1.5  total_ttt=13655.896245198968
urban_scale=2.0  total_ttt=17753.101395286547
urban_scale=2.5  total_ttt=21964.173641566962
urban_scale=3.0  total_ttt=26304.975617444008
```

Proposed Total TTT/TTS: not run for Step E.

Improvement rate: not computed for Step E.

Boundary queue balancing result: not evaluated as acceptance; the source MFD point has `CV_boundary=0.8943827648597883` and `MaxMin_boundary=120.49345496605291`.

Control validation summary: no full controller validation was run. Calibration CLI smoke, protected-accumulation semantics, config exposure, and METANET/unit checks passed.

### Review

- Coding subagent: `Kierkegaard`.
- Review subagent: `Cicero`, verdict `PASS_WITH_NOTES`.
- Blocking findings: none.
- Codex final review: PASS after removing the reviewer's noted `urban_vehicles` fallback from the calibration extractor.

### Failed Criteria And Next Modification

- Full acceptance remains unevaluated because no proposed-controller closed-loop run was requested or executed.
- `reports/claude_review_report.md` exists but is not a PASS verdict for the current Step E changes; the internal Step E review passed with notes.
- Proposed next modification: Step A, adjust the VSL forecast-aware test/objective saturation behavior.

## 2026-06-17 Step A - VSL Forecast-Aware Fixture Saturation Fix

### What was implemented

- `test_freeway_vsl_uses_future_offramp_inflow`의 off-ramp storage fixture를 98% 점유에서 30% 점유로 낮췄다.
- 기존 fixture는 low/high future forecast가 모두 최저 허용 VSL 후보로 포화되어 forecast 사용 여부를 구분하지 못했다.
- 컨트롤러 objective 수식은 변경하지 않았다. 이번 변경은 테스트 fixture saturation 해소에 한정했다.
- 실패 메시지에 agent별 `offramp_forecast_veh`와 `vsl_selected` diagnostics를 포함했다.
- high forecast가 더 큰 `offramp_forecast_veh`를 만들고, agent 내부 `vsl_selected`가 더 낮아지는지 직접 assertion으로 확인한다.

### Files changed

- `src/tests/test_forecast_awareness.py`
- `2026-06-17/proposed_controller_refactor_execution.md`
- `reports/codex_run_report.md`

### Commands

Baseline run command:

```text
Not run for Step A. This was a targeted unit-test fixture/saturation pass.
```

Proposed-controller run command:

```text
Not run for Step A. No closed-loop proposed simulation was requested.
```

Syntax check:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\distributed_coordinator.py src\tests\test_forecast_awareness.py
```

Result: OK.

Focused failing test:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_forecast_awareness.ForecastAwarenessTests.test_freeway_vsl_uses_future_offramp_inflow -v
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
8 tests, OK
```

Related constraints:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints -v
```

Result:

```text
44 tests, OK
```

### Metrics

Baseline Total TTT/TTS: not run.

Proposed Total TTT/TTS: not run.

Improvement rate: not computed for Step A.

Boundary queue balancing result: not run.

Control validation summary: compile passed; the targeted Step A test, full `src.tests.test_forecast_awareness`, and `src.tests.test_constraints` passed.

### Review

- Coding subagent: `Galileo`.
- Review subagent: `Godel`, verdict `PASS_WITH_NOTES`.
- Blocking findings: none.
- Codex final review: PASS after adding the reviewer's suggested forecast/VSL-direction assertions.

### Failed Criteria And Next Modification

- Full acceptance remains unevaluated because no closed-loop baseline/proposed simulation was run.
- `reports/claude_review_report.md` exists but is not a PASS verdict for the current Step A changes.
- Proposed next modification: run a full same-scenario baseline/proposed comparison when ready; Step A itself only resolves the VSL forecast-awareness unit-test saturation issue.

## 2026-06-18 Peak 7200s Four-Controller Relaxed-Fast Run

### What was run

- Ran the primary four-controller Stage 1 comparison for `peak_demand`, `T_total=7200`.
- Used explicit relaxed-fast mode, so this is a computational screening result, not a full-budget controller acceptance run.
- Controllers:
  - `WU-CD-F`
  - `PROPOSED-FOLLOWERS-ONLY`
  - `PROPOSED-STACKELBERG`
  - `PROPOSED-CENTRALIZED`

### Command

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --config src/config/default.yaml --scenario peak_demand --T-total 7200 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --relaxed-fast-mode --output outputs/peak_7200_four_controller_relaxed_fast_2026_06_18_v1
```

Result:

```text
WU-CD-F: ttt=11645.9 delay=10501.9 authority_ok=True
PROPOSED-FOLLOWERS-ONLY: ttt=7484.8 delay=6340.8 authority_ok=True
PROPOSED-STACKELBERG: ttt=7607.5 delay=6463.5 authority_ok=True
PROPOSED-CENTRALIZED: ttt=6369.1 delay=5225.1 authority_ok=True
```

### Output Files

- `outputs/peak_7200_four_controller_relaxed_fast_2026_06_18_v1/six_controller_summary.csv`
- `outputs/peak_7200_four_controller_relaxed_fast_2026_06_18_v1/paired_comparisons.csv`
- `outputs/peak_7200_four_controller_relaxed_fast_2026_06_18_v1/summary.json`
- Per-controller run logs under `outputs/peak_7200_four_controller_relaxed_fast_2026_06_18_v1/runs/peak_demand/`

### Summary

| controller | total TTT | total delay | throughput veh/h | terminal veh | comp sec | converge rate | TTT improvement vs WU-CD-F | delay improvement vs WU-CD-F |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `PROPOSED-CENTRALIZED` | 6369.101 | 5225.081 | 11304.3 | 6754.2 | 105.53 | 0.000 | 45.31% | 50.25% |
| `PROPOSED-FOLLOWERS-ONLY` | 7484.779 | 6340.759 | 10762.6 | 7837.6 | 0.73 | 0.725 | 35.73% | 39.62% |
| `PROPOSED-STACKELBERG` | 7607.514 | 6463.495 | 10263.7 | 8837.5 | 174.71 | 0.000 | 34.68% | 38.45% |
| `WU-CD-F` | 11645.893 | 10501.874 | 7945.7 | 13467.4 | 12.94 | 0.075 | 0.00% | 0.00% |

### Pairwise Interpretation

- `PROPOSED-FOLLOWERS-ONLY` improves total delay vs `WU-CD-F` by `4161.115 veh*h` (`39.62%`).
- `PROPOSED-STACKELBERG` improves total delay vs `WU-CD-F` by `4038.379 veh*h` (`38.45%`).
- `PROPOSED-STACKELBERG` is worse than `PROPOSED-FOLLOWERS-ONLY` in this relaxed-fast run:
  - total TTT increases by `122.735 veh*h`
  - total delay increases by `122.736 veh*h`
  - delay change = `-1.94%` relative to `PROPOSED-FOLLOWERS-ONLY`
  - throughput decreases by `498.9 veh/h`
  - terminal vehicles increase by `999.9 veh`
- `PROPOSED-CENTRALIZED` is best by TTT and delay, but it is a budgeted centralized numerical reference, not a guaranteed global optimum.

### Failed Criteria And Next Modification

- This run does not establish final controller acceptance because it used `--relaxed-fast-mode`.
- `PROPOSED-STACKELBERG` still does not outperform `PROPOSED-FOLLOWERS-ONLY` under peak 7200s relaxed-fast conditions.
- The next diagnosis should focus on why the leader/allocation layer raises urban delay and terminal vehicles relative to follower-only despite reducing freeway delay.

### Stackelberg vs Follower-Only Diagnosis

The current code does include the follower-response TTT/TTS base in the leader objective:

```text
leader_total_objective = leader_follower_ttt_base + leader_target_penalty + leader_density_penalty + leader_smoothness_penalty
```

The poor peak result is therefore not because the follower TTT term is absent. The observed issue is that the target term and the follower response induced by the leader move delay from the freeway into urban/on-ramp storage.

| diagnostic | `PROPOSED-FOLLOWERS-ONLY` | `PROPOSED-STACKELBERG` | interpretation |
|---|---:|---:|---|
| total TTT | 7484.779 | 7607.514 | Stackelberg is worse by 122.735 veh*h. |
| urban TTT | 5911.423 | 7281.841 | Urban cost increases by 1370.418 veh*h. |
| freeway TTT | 1573.356 | 325.674 | Freeway cost decreases by 1247.682 veh*h. |
| throughput | 10762.6 veh/h | 10263.7 veh/h | Stackelberg serves 498.9 veh/h fewer vehicles. |
| terminal total vehicles | 7837.6 | 8837.5 | Stackelberg leaves 999.9 more vehicles in the system. |
| terminal urban vehicles | 6988.9 | 8725.1 | The extra residual queue is mostly urban. |
| terminal freeway vehicles | 128.6 | 82.7 | Freeway residual improves slightly. |
| mean protected accumulation `N_P` | 852.716 veh | 700.539 veh | Leader lowers protected accumulation. |
| `N_P > N_P_crit` share | 62.5% | 55.0% | Leader reduces critical-point violations. |
| `N_P` excess area | 820.104 veh*h | 576.905 veh*h | Critical excess falls by about 29.7%. |
| mean total urban vehicles | 2862.739 veh | 3586.835 veh | Total urban storage grows despite lower protected `N_P`. |
| urban departures over 7200s | 27916.813 veh | 25077.134 veh | Stackelberg discharges 2839.679 fewer urban vehicles. |
| urban gate inflow over 7200s | 8798.022 veh | 8019.448 veh | Boundary/gate service is lower. |
| on-ramp green releases over 7200s | 6646.932 veh | 5360.205 veh | On-ramp service is lower. |
| mean leader follower-TTT base | n/a | 604.231 | Base term is active. |
| mean leader target penalty | n/a | 934.083 | Target penalty is larger than the follower-TTT base. |

Conclusion: the leader is doing the intended critical-point behavior in a narrow sense: it lowers `N_P` and freeway TTT. It fails at the network level because that improvement is smaller than the added urban TTT and throughput loss. In this run, the leader protects the freeway/protected core by pushing vehicles into urban/on-ramp storage instead of increasing completed throughput.

This also shows Stackelberg is not worse in every dimension. It improves freeway TTT, freeway delay, terminal freeway vehicles, mean `N_P`, and `N_P` critical excess. It is worse in the network objective dimensions that dominate the comparison: total TTT, total delay, urban TTT, throughput, and terminal residual vehicles.

Likely next modification: rebalance the leader objective so that the target term cannot dominate the follower-TTT base without also accounting for lost throughput/residual urban storage. A concrete scale issue is visible in the code: `_predict()` returns follower TTT as `freeway_ttt + urban_ttt`, where both plant terms already include `T_c_h`, but `leader_target_penalty` currently sums `max(N_P - N_P_crit, 0)` over predicted states without multiplying by `T_c_h`. If the intended mathematical term is TTT-style accumulation excess, this makes the target term about `1 / T_c_h = 20` times too large under the current 180 s control interval. Candidate fixes are (1) multiply target/density accumulation penalties by `T_c_h` or retune their weights into consistent units, (2) add a terminal residual/throughput loss term to the leader objective, or (3) require the leader candidate to beat or tie the follower-only predicted response before accepting a restrictive `N_P_star`/`N_UF_star` action.

## 2026-06-18 Leader Objective Time-Scale Fix And Peak 7200s Rerun

### What Was Implemented

- `leader.objective_mode: follower_ttt`에서 `leader_target_penalty`와 `leader_density_penalty`에 `T_c_h`를 곱하도록 수정했다.
- 이유: follower-response base는 plant TTT/TTS라 이미 veh*h인데, 기존 target/density accumulation penalty는 차량수 단위로 horizon 합만 더해져 target 항이 과대평가됐다.
- Legacy `state_accumulation` 모드는 기존 vehicle-sum 스케일을 유지했다. 이 모드는 명시적으로 켤 때만 쓰는 진단/legacy 경로다.
- `docs/spec/04_controller.md`에 `follower_ttt` 모드 target exceedance penalty는 `T_c_h`로 veh*h 스케일에 맞춘다고 명시했다.
- `src/tests/test_constraints.py`에 기본 leader objective의 `T_c_h` scaling 단위 테스트를 추가했다.

### Files Changed

- `src/controllers/leader.py`
- `src/tests/test_constraints.py`
- `docs/spec/04_controller.md`
- `reports/codex_run_report.md`

### Tests

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\leader.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_forecast_awareness
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_offramp_reattribution
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest discover -s src/tests
```

Result:

```text
src.tests.test_constraints: 45 tests, OK
src.tests.test_forecast_awareness: 8 tests, OK
src.tests.test_offramp_reattribution: 7 tests, OK
unittest discover: 143 tests, OK
```

The full discover run prints an expected smoke-report line (`FAIL improvement=-1.99% ...`) while still ending with `OK`; that smoke path preserves a failed improvement report and is not a failing unittest assertion.

### Baseline And Proposed Run Command

The four-controller comparison uses the same `peak_demand` scenario, demand, horizon, config, and relaxed-fast screening mode for all controllers.

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --config src/config/default.yaml --scenario peak_demand --T-total 7200 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --relaxed-fast-mode --output outputs/peak_7200_four_controller_relaxed_fast_time_scaled_objective_2026_06_18_v1
```

Output:

```text
WU-CD-F: ttt=11645.9 delay=10501.9 authority_ok=True
PROPOSED-FOLLOWERS-ONLY: ttt=7484.8 delay=6340.8 authority_ok=True
PROPOSED-STACKELBERG: ttt=6853.5 delay=5709.4 authority_ok=True
PROPOSED-CENTRALIZED: ttt=6369.1 delay=5225.1 authority_ok=True
```

### Metrics

| controller | total TTT | total delay | throughput veh/h | terminal veh | avg delay/completed h | comp sec | converge rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| `WU-CD-F` | 11645.893 | 10501.874 | 7945.7 | 13467.4 | 0.660855 | 12.82 | 0.075 |
| `PROPOSED-FOLLOWERS-ONLY` | 7484.779 | 6340.759 | 10762.6 | 7837.6 | 0.294574 | 0.73 | 0.725 |
| `PROPOSED-STACKELBERG` | 6853.454 | 5709.434 | 11064.9 | 7233.9 | 0.257998 | 177.03 | 0.000 |
| `PROPOSED-CENTRALIZED` | 6369.101 | 5225.081 | 11304.3 | 6754.2 | 0.231110 | 106.05 | 0.000 |

Pairwise:

- `PROPOSED-STACKELBERG` vs `PROPOSED-FOLLOWERS-ONLY`: total delay improves by `631.325 veh*h` (`9.96%`), throughput increases by `302.3 veh/h`, terminal vehicles decrease by `603.7 veh`.
- `PROPOSED-STACKELBERG` vs `WU-CD-F`: total delay improves by `4792.440 veh*h` (`45.63%`), throughput increases by `3119.2 veh/h`, terminal vehicles decrease by `6233.5 veh`.
- `PROPOSED-CENTRALIZED` remains best: it improves delay by another `484.353 veh*h` (`8.48%`) relative to `PROPOSED-STACKELBERG`.

### Before/After Diagnosis

| diagnostic | old unscaled Stackelberg | time-scaled Stackelberg | interpretation |
|---|---:|---:|---|
| total TTT | 7607.514 | 6853.454 | objective scale fix reduces TTT by 754.060 veh*h. |
| total delay | 6463.495 | 5709.434 | delay improves by 754.061 veh*h. |
| throughput | 10263.7 veh/h | 11064.9 veh/h | throughput recovers by 801.2 veh/h. |
| terminal total vehicles | 8837.5 | 7233.9 | residual vehicles fall by 1603.6 veh. |
| mean `leader_target_penalty` | 934.083 | 50.107 | target term no longer dominates the follower TTT base. |
| mean `leader_follower_ttt_base` | 604.231 | 541.239 | candidate evaluation now prefers lower predicted follower TTT. |
| mean `N_UF_star` | 4006.024 | 5505.570 | freeway inflow target becomes less restrictive. |
| on-ramp green releases | 5360.205 veh | 6922.715 veh | on-ramp service recovers. |
| ramp metering releases | 5330.466 veh | 6910.979 veh | actual freeway entry service recovers. |
| mean `N_P` | 700.539 | 723.170 | protected accumulation is allowed slightly higher. |
| `N_P > N_P_crit` share | 55.0% | 52.5% | critical exceedance frequency still improves vs follower-only. |

The previous failure mode is therefore confirmed as an objective scaling bug: the leader was over-penalizing `N_P` exceedance relative to follower TTT and was too restrictive. After the fix, Stackelberg still protects the freeway/core relative to follower-only, but it no longer sacrifices as much throughput and urban discharge.

### Boundary Queue Balancing And Control Validation

| controller | mean `B_in` | mean `B_out` | mean abs net inflow tracking error | ramp metering shortfall | VSL repair count | green repair count | density exceedance count |
|---|---:|---:|---:|---:|---:|---:|---:|
| `WU-CD-F` | 0.064794 | 0.018733 | 2004.853 | 0.0 | 411.0 | 600.0 | 5000.0 |
| `PROPOSED-FOLLOWERS-ONLY` | 0.069990 | 0.009558 | 729.866 | 0.0 | 0.0 | 1000.0 | 0.0 |
| `PROPOSED-STACKELBERG` | 0.013992 | 0.003919 | 815.701 | 0.0 | 0.0 | 900.0 | 116.0 |
| `PROPOSED-CENTRALIZED` | 0.125210 | 0.002036 | 622.763 | 0.0 | 0.0 | 0.0 | 0.0 |

Boundary balancing is not degraded relative to follower-only: both `B_in` and `B_out` improve under the time-scaled Stackelberg run. Net inflow tracking is worse than follower-only but much better than `WU-CD-F`. Ramp metering shortfall is zero. The Stackelberg run still has nonzero density exceedance count and zero Nash convergence rate under relaxed-fast screening, so this is a strong improvement result but not final acceptance.

### Failed Criteria And Next Modification

- This remains a relaxed-fast screening run, not a full-budget final acceptance run.
- `PROPOSED-STACKELBERG` now beats `PROPOSED-FOLLOWERS-ONLY` on total TTT, total delay, throughput, terminal total vehicles, average delay per completed vehicle, `B_in`, and `B_out`.
- Remaining gap: `PROPOSED-CENTRALIZED` is still better, and Stackelberg convergence rate remains `0.000`.
- Proposed next modification: diagnose the remaining centralized gap and non-convergence residuals now that the objective scale bug is removed.

### Three-Axis Controller-Value Check

This follow-up checks whether the time-scaled Stackelberg controller supports three research claims:

1. computation-cost positioning vs centralized and follower-only,
2. myopic follower-only problem mitigation, and
3. boundary queue balance improvement.

#### 1. Computation Cost

| controller | computation time sec | solver evaluations | convergence rate |
|---|---:|---:|---:|
| `PROPOSED-FOLLOWERS-ONLY` | 0.73 | 1495 | 0.725 |
| `PROPOSED-STACKELBERG` | 177.03 | 10080 | 0.000 |
| `PROPOSED-CENTRALIZED` | 106.05 | 640 | 0.000 |

Current verdict: FAIL for the "Stackelberg keeps computation cost moderate" claim in this relaxed-fast implementation. Stackelberg is `242.5x` slower than follower-only and `1.67x` slower than the current centralized reference. It also uses `15.75x` more solver evaluations than centralized. This does not prove Stackelberg is inherently more expensive than a full centralized MPC; this centralized controller is a budgeted relaxed-fast reference, not a full global optimizer. But with the current code and settings, the computation-cost advantage is not demonstrated.

Likely cause: Stackelberg evaluates many leader candidates and runs a follower-response iteration/prediction for each candidate. The current centralized reference uses a smaller budgeted candidate/evaluation path.

#### 2. Myopic Problem / Leader Necessity

| diagnostic | `PROPOSED-FOLLOWERS-ONLY` | `PROPOSED-STACKELBERG` | relative change |
|---|---:|---:|---:|
| total TTT | 7484.779 | 6853.454 | 8.43% lower |
| total delay | 6340.759 | 5709.434 | 9.96% lower |
| throughput | 10762.6 veh/h | 11064.9 veh/h | 2.81% higher |
| terminal total vehicles | 7837.6 | 7233.9 | 7.70% lower |
| freeway TTT | 1573.356 | 355.334 | 77.42% lower |
| urban TTT | 5911.423 | 6498.119 | 9.92% higher |
| mean `N_P` | 852.716 | 723.170 | lower |
| `N_P > N_P_crit` share | 62.5% | 52.5% | 10.0 percentage points lower |
| `N_P` excess area | 820.104 veh*h | 621.127 veh*h | 24.26% lower |

Current verdict: PASS as evidence that the leader mitigates a myopic follower-only failure. Follower-only has lower urban TTT, but it does so while allowing much larger freeway TTT and larger protected-accumulation excess. The Stackelberg leader lowers the network objective, raises throughput, and reduces terminal residual vehicles while reducing time-averaged `N_P` critical excess. This supports the claim that the leader adds value beyond local follower responses.

Caveat: Stackelberg does not improve every subsystem. Urban TTT increases by `586.696 veh*h`, and terminal urban vehicles are slightly higher (`7069.9` vs `6988.9`). The net gain comes from reducing freeway/on-ramp congestion and residual vehicles more than the added urban cost.

#### 3. Boundary Queue Balance / Leader Necessity

| controller | mean `B_in` | mean `B_out` | load-weighted `B_in` | load-weighted `B_out` |
|---|---:|---:|---:|---:|
| `WU-CD-F` | 0.064794 | 0.018733 | 0.015587 | 0.009126 |
| `PROPOSED-FOLLOWERS-ONLY` | 0.069990 | 0.009558 | 0.028254 | 0.005373 |
| `PROPOSED-STACKELBERG` | 0.013992 | 0.003919 | 0.007034 | 0.002627 |
| `PROPOSED-CENTRALIZED` | 0.125210 | 0.002036 | 0.100189 | 0.001670 |

Current verdict: PASS for the boundary-balance leader-value claim. Relative to follower-only, time-scaled Stackelberg reduces load-weighted `B_in` by `75.11%` and load-weighted `B_out` by `51.12%`. It is also the best of the four controllers for `B_in`, while centralized is best for `B_out` but much worse for `B_in`.

Important caveat: net inflow tracking error is worse than follower-only (`815.701` vs `729.866`) even though balance indices improve. Therefore the leader currently improves fairness/balance across boundary queues, but not the raw net-inflow tracking error. This distinction should be kept explicit in the paper/report.

#### Overall Three-Axis Conclusion

- Computation-cost claim: not supported by the current implementation. This needs further optimization or a fairer full-centralized benchmark before it can be claimed.
- Myopic-problem claim: supported. Stackelberg beats follower-only on TTT, delay, throughput, terminal vehicles, freeway TTT, and `N_P` critical excess.
- Boundary-balance claim: supported. Stackelberg materially improves both `B_in` and `B_out` relative to follower-only, especially under load-weighted evaluation.

Next recommended modification: optimize Stackelberg candidate evaluation or cache/reuse follower responses so the controller is not slower than the current centralized relaxed-fast reference.

## 2026-06-18 Stackelberg Follower-Response Objective Rerun

### What Was Implemented

- Changed the default `PROPOSED-STACKELBERG` leader evaluation path so `objective_mode: follower_ttt` uses `NashResult.objective_value` directly as the follower-response base.
- Removed the extra full-system coupled plant rollout from the default Stackelberg candidate evaluation.
- Kept the legacy rollout path only for `leader.objective_mode: state_accumulation`, where the state trajectory itself is the base objective.
- Updated the Stage 1 solver-evaluation accounting: when the default follower-response path is used, Stackelberg no longer adds `horizon_steps` rollout evaluations to each leader candidate.
- Added a unit test confirming that default Stackelberg candidate evaluation does not call `run_coupled_interval`.
- Updated `docs/spec/04_controller.md` to state that the default Stackelberg objective uses the follower-response objective, not a second full-system rollout TTT.

### Files Changed

- `src/controllers/stackelberg_mpc.py`
- `src/experiments/six_controller_comparison.py`
- `src/tests/test_constraints.py`
- `docs/spec/04_controller.md`
- `reports/codex_run_report.md`

### Tests

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\stackelberg_mpc.py src\experiments\six_controller_comparison.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_forecast_awareness
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_six_controller_comparison
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest discover -s src/tests
```

Result:

```text
src.tests.test_constraints: 46 tests, OK
src.tests.test_forecast_awareness: 8 tests, OK
src.tests.test_six_controller_comparison: 29 tests, OK
unittest discover: 144 tests, OK
```

The full discover run prints an expected smoke-report line (`FAIL improvement=-1.99% ...`) while still ending with `OK`; that line is produced by a smoke report path and is not a failing unittest assertion.

### Four-Controller Run Command

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --config src/config/default.yaml --scenario peak_demand --T-total 7200 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --relaxed-fast-mode --output outputs/peak_7200_four_controller_follower_response_objective_2026_06_18_v1
```

Output:

```text
WU-CD-F: ttt=11645.9 delay=10501.9 authority_ok=True
PROPOSED-FOLLOWERS-ONLY: ttt=7484.8 delay=6340.8 authority_ok=True
PROPOSED-STACKELBERG: ttt=10281.1 delay=9137.1 authority_ok=True
PROPOSED-CENTRALIZED: ttt=6369.1 delay=5225.1 authority_ok=True
```

### Metrics

| controller | total TTT | total delay | throughput veh/h | terminal veh | comp sec | solver eval |
|---|---:|---:|---:|---:|---:|---:|
| `WU-CD-F` | 11645.893 | 10501.874 | 7945.7 | 13467.4 | 12.79 | 1059 |
| `PROPOSED-FOLLOWERS-ONLY` | 7484.779 | 6340.759 | 10762.6 | 7837.6 | 0.70 | 1495 |
| `PROPOSED-STACKELBERG` | 10281.141 | 9137.122 | 9432.4 | 10499.0 | 136.09 | 9360 |
| `PROPOSED-CENTRALIZED` | 6369.101 | 5225.081 | 11304.3 | 6754.2 | 106.91 | 640 |

Pairwise:

- `PROPOSED-STACKELBERG` is worse than `PROPOSED-FOLLOWERS-ONLY`: total delay increases by `2796.363 veh*h` (`-44.10%` leader value).
- `PROPOSED-STACKELBERG` is still better than `WU-CD-F`: total delay improves by `1364.752 veh*h` (`13.00%`).
- `PROPOSED-CENTRALIZED` is much better than `PROPOSED-STACKELBERG`: delay improves by `3912.041 veh*h` (`42.81%`).

### Rollout Removal Diagnostics

| diagnostic | previous time-scaled rollout Stackelberg | follower-response Stackelberg | interpretation |
|---|---:|---:|---|
| computation time | 177.03 s | 136.09 s | Removing rollout reduces cost by about 23.1%. |
| solver evaluations | 10080 | 9360 | The `+ horizon_steps` rollout count was removed. |
| `leader_rollout_prediction_used` | n/a | 0.0 | New path is active. |
| `leader_follower_response_objective_used` | n/a | 1.0 | Leader uses `NashResult.objective_value`. |
| mean follower-response base | 541.239 | 4959.008 | New base is follower objective, not plant rollout TTT. |
| mean `N_UF_star` | 5505.570 | 3426.741 | Follower-response objective selects much more restrictive freeway inflow. |
| urban departures | 27221.165 veh | 20371.157 veh | Urban discharge collapses. |
| on-ramp green releases | 6922.715 veh | 4623.023 veh | On-ramp service collapses. |
| ramp metering releases | 6910.979 veh | 4593.071 veh | Freeway entry service is strongly restricted. |
| final urban vehicles | 7002.237 veh | 10373.625 veh | Residual urban storage rises sharply. |
| final freeway vehicles | 164.024 veh | 112.629 veh | Freeway remains protected. |

### Diagnosis

The code now matches the requested Stackelberg structure more closely: the leader no longer adds a second full-system rollout TTT after receiving the follower response. However, performance degrades because the current distributed `NashResult.objective_value` is not yet a faithful network TTT/TTS objective. It is a sum of local/proxy follower objectives:

- freeway agent terms include density, metering, VSL, and storage-aware proxy costs;
- urban agent terms include local queue, balance, allocation residual, and smoothness terms;
- the sum does not currently represent completed-throughput loss or terminal urban residual strongly enough.

Therefore, when full rollout is removed, the leader optimizes the follower proxy objective and chooses restrictive `N_UF_star` values that protect freeway states but suppress urban/on-ramp service. This confirms the next required fix: align the follower-response objective itself with the intended follower TTT/TTS before relying on it as the leader base.

### Failed Criteria And Next Modification

- This run FAILS the proposed leader-value criterion relative to follower-only.
- Computation cost improves but remains worse than the current centralized relaxed-fast reference (`136.09 s` vs `106.91 s`).
- Next modification: redefine or augment `NashResult.objective_value` so the follower response objective is TTT/TTS-compatible. The correct target is not to reintroduce full Stackelberg rollout, but to make follower agents report a response objective that includes the same TTT/delay/throughput-relevant terms the leader is supposed to receive.

## 2026-06-18 Previous-Control Mutation Bug And Follower Objective Diagnosis

### What Was Found

Two code-level issues explain why the follower-response Stackelberg run became worse than follower-only.

1. `previous_control` mutation bug:
   - `DistributedCoordinator.solve()` and the legacy `NashSolver.solve()` assigned `current = previous_control` and then overwrote `current.N_P_star` / `current.N_UF_star`.
   - During Stackelberg candidate evaluation, this mutated the shared previous-control object across leader candidates.
   - Consequences:
     - candidate evaluations were not independent;
     - the leader smoothness penalty was often accidentally zero;
     - later candidates could start from a previous candidate's action rather than the true previous control.

2. `NashResult.objective_value` is not yet follower TTT/TTS:
   - In distributed mode, `NashResult.objective_value` is the sum of local/proxy agent objectives.
   - Urban agent objective is mainly boundary balance, allocation residual, smoothness, and local queue proxy.
   - Freeway agent objective is density/metering/VSL/off-ramp-storage proxy.
   - This objective does not directly penalize lost throughput, terminal urban residual, or withholding ramp/on-ramp service strongly enough.

Therefore, "best follower response" in the current code means "best under the distributed proxy objective," not "minimum follower TTT/TTS."

### What Was Implemented

- Added `ControlAction.copy()` to copy all dict fields.
- Updated `DistributedCoordinator.solve()` to copy `previous_control` before mutating `N_P_star` / `N_UF_star`.
- Updated the legacy `NashSolver.solve()` similarly.
- Updated `StackelbergMPCController` to copy previous controls before candidate evaluation and before storing `self.previous_control`.
- Updated the Stage 1 controller adapter to store a copy of returned controls.
- Added regression tests:
  - distributed follower does not mutate `previous_control`;
  - two-block Nash solver does not mutate `previous_control`.

### Tests

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\models\state.py src\controllers\distributed_coordinator.py src\controllers\nash_solver.py src\controllers\stackelberg_mpc.py src\experiments\six_controller_comparison.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_forecast_awareness
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_six_controller_comparison
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest discover -s src/tests
```

Result:

```text
src.tests.test_constraints: 48 tests, OK
src.tests.test_forecast_awareness: 8 tests, OK
src.tests.test_six_controller_comparison: 29 tests, OK
unittest discover: 146 tests, OK
```

The full discover run prints an expected smoke-report line (`FAIL improvement=-8.87% ...`) while still ending with `OK`; that line is generated by a smoke report path and is not a failing unittest assertion.

### Four-Controller Run After Mutation Fix

Command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --config src/config/default.yaml --scenario peak_demand --T-total 7200 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --relaxed-fast-mode --output outputs/peak_7200_four_controller_follower_response_prevcopy_2026_06_18_v1
```

Output:

```text
WU-CD-F: ttt=11645.9 delay=10501.9 authority_ok=True
PROPOSED-FOLLOWERS-ONLY: ttt=7484.8 delay=6340.8 authority_ok=True
PROPOSED-STACKELBERG: ttt=15115.3 delay=13971.3 authority_ok=True
PROPOSED-CENTRALIZED: ttt=6369.1 delay=5225.1 authority_ok=True
```

### Diagnostic Metrics

| controller/run | total TTT | delay | throughput veh/h | terminal veh | mean `N_UF_star` | ramp releases | on-ramp green releases |
|---|---:|---:|---:|---:|---:|---:|---:|
| follower-only | 7484.779 | 6340.759 | 10762.6 | 7837.6 | 0.0 | 5926.932 | 6646.932 |
| follower-response Stackelberg before copy fix | 10281.141 | 9137.122 | 9432.4 | 10499.0 | 3426.741 | 4593.071 | 4623.023 |
| follower-response Stackelberg after copy fix | 15115.284 | 13971.264 | 6984.2 | 15396.9 | 0.0 | 8.102 | 728.102 |

After the copy fix, the hidden smoothness/objective behavior becomes explicit: `PROPOSED-STACKELBERG` selects `N_UF_star = 0` for the whole run. This nearly shuts off ramp metering releases and on-ramp service, causing a large urban/on-ramp backlog.

### Candidate Ranking Evidence

At an intermediate state around step 10, the follower-response objective ranks a no-freeway-inflow candidate first, even though a high-inflow candidate has lower actual rollout TTT:

| candidate | `N_UF_star` | follower-response objective | diagnostic rollout TTT |
|---|---:|---:|---:|
| selected by current follower objective | 0.0 | 2684.006 | 443.475 |
| best by diagnostic rollout TTT | 6000.0 | 2686.764 | 421.933 |

This confirms the core issue: candidate selection is not using a follower TTT objective. It is using a proxy objective whose ranking can prefer withholding freeway/on-ramp inflow even when that worsens network TTT.

### Conclusion

The poor follower-response Stackelberg result is caused by code/objective mismatch, not by the Stackelberg idea itself. The previous-control mutation was a real coding bug and has been fixed. The remaining failure is that the follower objective returned to the leader is not yet the intended follower TTT/TTS. The next code change should redefine distributed follower `objective_value` so it reports a TTT/TTS-compatible response value, including served-flow/throughput and terminal residual costs, before the leader uses it as `leader_follower_ttt_base`.

## 2026-06-18 Distributed Follower TTS-Compatible Response Objective

### What Was Implemented

The core failure diagnosed above was addressed without restoring the old full-system Stackelberg rollout path.

- `DistributedCoordinator.solve()` now separates:
  - local distributed agent proxy objective, retained as `distributed_response_proxy_objective`;
  - returned `NashResult.objective_value`, now `distributed_response_objective_tts`.
- The new response objective is a lightweight vehicle-hour conservation proxy:
  - current urban/freeway/ramp/off-ramp/origin vehicles;
  - horizon forecast arrivals;
  - estimated green service and boundary-out sinks;
  - estimated on-ramp green release and ramp metering release;
  - estimated mainline exits;
  - estimated off-ramp inflow/storage departure;
  - freeway density-excess exposure;
  - terminal residual vehicles and Nash residual penalty.
- `Leader.objective_terms()` now converts `Delta N_UF_star` from veh/h to vehicles over one control interval before applying `w_L` smoothness.
- `docs/spec/04_controller.md` now states that the distributed follower must return a TTT/TTS-compatible response objective and that local proxy costs are diagnostics only.
- Added regression coverage:
  - distributed `objective_value` equals logged `distributed_response_objective_tts`;
  - high ramp service is preferred over zero metering when the freeway has receiving room;
  - leader smoothness uses `T_c_h * Delta N_UF_star` when `N_UF_star_unit = veh_per_hour`.

### Changed Files

- `src/controllers/distributed_coordinator.py`
- `src/controllers/leader.py`
- `docs/spec/04_controller.md`
- `src/tests/test_constraints.py`
- Existing in-progress files from the previous step remain modified: `src/models/state.py`, `src/controllers/nash_solver.py`, `src/controllers/stackelberg_mpc.py`, `src/experiments/six_controller_comparison.py`.

### Validation Commands

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src/controllers/distributed_coordinator.py src/controllers/leader.py src/controllers/stackelberg_mpc.py src/models/state.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics src.tests.test_constraints.ConstraintTests.test_distributed_response_objective_rewards_ramp_service src.tests.test_constraints.ConstraintTests.test_leader_objective_matches_spec_accumulation_form src.tests.test_constraints.ConstraintTests.test_default_leader_accumulation_penalties_use_control_interval_hours src.tests.test_constraints.ConstraintTests.test_stackelberg_default_objective_uses_follower_response_without_rollout -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints src.tests.test_forecast_awareness src.tests.test_six_controller_comparison -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest discover -s src/tests -v
```

Result:

```text
targeted tests: 5 tests, OK
constraints + forecast + six-controller comparison: 86 tests, OK
unittest discover: 147 tests, OK
```

The full discover command still prints a smoke-report line (`FAIL improvement=-1.99% ...`) before the unittest listing, but the unittest run itself ends with `OK`.

### Peak 7200 s Four-Controller Run

Command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --config src/config/default.yaml --scenario peak_demand --T-total 7200 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --relaxed-fast-mode --output outputs/peak_7200_four_controller_response_tts_objective_2026_06_18_v1
```

Output:

```text
WU-CD-F: ttt=11645.9 delay=10501.9 authority_ok=True
PROPOSED-FOLLOWERS-ONLY: ttt=7411.6 delay=6267.5 authority_ok=True
PROPOSED-STACKELBERG: ttt=7208.0 delay=6063.9 authority_ok=True
PROPOSED-CENTRALIZED: ttt=6369.1 delay=5225.1 authority_ok=True
```

### Metric Summary

| controller | total TTT | total delay | throughput veh/h | terminal veh | computation s | solver evals |
|---|---:|---:|---:|---:|---:|---:|
| WU-CD-F | 11645.893 | 10501.874 | 7945.7 | 13467.4 | 12.85 | 1059 |
| PROPOSED-FOLLOWERS-ONLY | 7411.565 | 6267.545 | 10790.0 | 7782.8 | 0.81 | 1495 |
| PROPOSED-STACKELBERG | 7207.966 | 6063.946 | 10913.7 | 7537.2 | 137.42 | 9360 |
| PROPOSED-CENTRALIZED | 6369.101 | 5225.081 | 11304.3 | 6754.2 | 107.60 | 640 |

Relative to `PROPOSED-FOLLOWERS-ONLY`, the corrected Stackelberg run improves:

- total TTT / delay by `203.599 veh*h` (`3.25%`);
- throughput by `123.7 veh/h`;
- terminal total vehicles by `245.6 veh`.

Relative to `WU-CD-F`, the corrected Stackelberg run improves:

- total TTT / delay by `4437.927 veh*h` (`42.26%`);
- throughput by `2968.0 veh/h`;
- terminal total vehicles by `5930.2 veh`.

### Leader / Response Diagnostics

For `PROPOSED-STACKELBERG`:

| diagnostic | mean | min | max |
|---|---:|---:|---:|
| selected `N_UF_star` | 5612.322 | 3000.000 | 6000.000 |
| selected `N_P_star` | 489.708 | 458.504 | 534.921 |
| `leader_follower_ttt_base` | 622.733 | 117.926 | 1207.627 |
| `leader_target_penalty` | 48.130 | 0.000 | 169.202 |
| `leader_smoothness_penalty` | 2.264 | 0.000 | 30.425 |
| `leader_total_objective` | 673.502 | 148.351 | 1376.829 |
| `distributed_response_proxy_objective` | 3672.779 | 810.919 | 7217.758 |
| `distributed_response_ramp_release_veh` | 440.039 | 287.419 | 597.974 |
| `distributed_response_mainline_exit_veh` | 1186.857 | 1088.056 | 1200.000 |
| `leader_rollout_prediction_used` | 0.000 | 0.000 | 0.000 |
| `leader_follower_response_objective_used` | 1.000 | 1.000 | 1.000 |

This confirms that the run did not restore the second full-system rollout. The leader is using `NashResult.objective_value`, and that value is now the TTS-compatible distributed response objective.

### Boundary Queue Balancing Result

The current output files do not expose the old boundary-balance scalar columns for this run. Relevant replacement diagnostics are present for leader boundary terms and distributed response terminal vehicles, but a direct `boundary_balance_index` comparison was not produced by the Stage 1 output schema. This remains a reporting gap rather than a controller infeasibility in this run.

### Failed Criteria And Next Modification

This patch fixes the specific objective mismatch: Stackelberg no longer collapses to `N_UF_star = 0`, and it now beats follower-only on TTT, delay, throughput, and terminal vehicles in the peak 7200 s relaxed-fast run.

However, it still does not satisfy all completion criteria:

- Stackelberg improvement over follower-only is `3.25%`, below the default `8%` threshold.
- Stackelberg computation time is still worse than centralized relaxed-fast (`137.42 s` vs `107.60 s`), even though the conceptual goal is for Stackelberg to be cheaper than centralized.
- Solver convergence rate for Stackelberg remains `0.0`, so the distributed response iteration is still relying on best-seen response selection rather than convergence.
- Boundary balance needs an explicit output column restored or reintroduced for direct acceptance reporting.

Proposed next modification:

- Reduce Stackelberg leader evaluation cost by pruning dominated leader candidates or using a warm-start/local candidate set after the first few intervals.
- Add a direct boundary balance metric to Stage 1 outputs.
- Investigate distributed residual convergence under the new response objective, especially whether relaxation/termination criteria are too strict for the current coupling scale.

## 2026-06-18 Relaxed-Fast Allocation Module Attempt

### What Was Implemented

- Added a separate `RelaxedFastAllocationModule` for `mpc.relaxed_fast_mode`.
- The original `InflowOutflowAllocationModule` remains the default when fast mode is off.
- The fast module keeps the same `AllocationResult` interface, but uses:
  - warm-start particles keyed by `(N_P_star, N_UF_star, movement set)`;
  - midpoint, previous response, perturbation, greedy-upper, and random particles;
  - early stopping after a minimum PSO iteration count when objective improvement stalls.
- Exposed allocation solver diagnostics into distributed controller and Stage 1 control logs.
- Set the quality-preserving fast budget to:
  - particles `36`;
  - max iterations `32`;
  - min iterations `16`;
  - patience `8`;
  - tolerance `1.0e-5`.

### Changed Files

- `src/controllers/relaxed_fast_allocation.py`
- `src/controllers/urban_follower.py`
- `src/controllers/distributed_coordinator.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/tests/test_constraints.py`
- `docs/spec/17_relaxed_quantized_fast_mode.md`

### Validation Commands

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\relaxed_fast_allocation.py src\controllers\urban_follower.py src\controllers\distributed_coordinator.py src\models\state.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_relaxed_fast_uses_warm_started_allocation_module src.tests.test_constraints.ConstraintTests.test_relaxed_quantized_controls_are_off_by_default src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics src.tests.test_constraints.ConstraintTests.test_stackelberg_default_objective_uses_follower_response_without_rollout -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints src.tests.test_forecast_awareness src.tests.test_six_controller_comparison -v
```

Result:

```text
targeted tests: 4 tests, OK
constraints + forecast + six-controller comparison: 87 tests, OK
```

### Baseline And Proposed Run Commands

The Stage 1 command runs the baseline/reference controller (`WU-CD-F`) and the proposed controllers under the same `peak_demand`, seed/config, plant, demand, horizon, and free-flow delay reference:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --config src/config/default.yaml --scenario peak_demand --T-total 7200 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --relaxed-fast-mode --output outputs/peak_7200_four_controller_relaxed_fast_warmstart_allocation_2026_06_18_v3
```

### 7200 s Peak Result

Output:

```text
WU-CD-F: ttt=11645.9 delay=10501.9 authority_ok=True
PROPOSED-FOLLOWERS-ONLY: ttt=7411.6 delay=6267.5 authority_ok=True
PROPOSED-STACKELBERG: ttt=11131.5 delay=9987.5 authority_ok=True
PROPOSED-CENTRALIZED: ttt=6369.1 delay=5225.1 authority_ok=True
```

| controller | total TTT | total delay | throughput veh/h | terminal veh | computation s | solver evals |
|---|---:|---:|---:|---:|---:|---:|
| WU-CD-F | 11645.893 | 10501.874 | 7945.7 | 13467.4 | 16.39 | 1059 |
| PROPOSED-FOLLOWERS-ONLY | 7411.565 | 6267.545 | 10790.0 | 7782.8 | 1.23 | 1495 |
| PROPOSED-STACKELBERG | 11131.502 | 9987.482 | 8539.9 | 12283.9 | 77.91 | 9243 |
| PROPOSED-CENTRALIZED | 6369.101 | 5225.081 | 11304.3 | 6754.2 | 139.87 | 640 |

### Computation-Cost Comparison

- `PROPOSED-STACKELBERG` improved computation time versus the previous full-allocation response-objective run: `137.42 s -> 77.91 s`.
- In this fast-mode run, Stackelberg is cheaper than centralized: `77.91 s` vs `139.87 s`.
- The cost reduction is not a success by itself because the TTT objective degraded severely.

### TTT-Minimization Comparison

- Relative to `WU-CD-F`, `PROPOSED-STACKELBERG` improves TTT by only `514.391 veh*h` (`4.90%`), below the default `8%` criterion.
- Relative to `PROPOSED-FOLLOWERS-ONLY`, `PROPOSED-STACKELBERG` is worse by `3719.937 veh*h` (`-59.35%` delay improvement).
- Relative to `PROPOSED-CENTRALIZED`, `PROPOSED-STACKELBERG` is worse by `4762.401 veh*h`.

### Boundary Queue Balancing Result

Mean values over the 7200 s run:

| controller | B_in | B_out | overflow ratio | boundary-in load veh |
|---|---:|---:|---:|---:|
| WU-CD-F | 0.0648 | 0.0187 | 0.1232 | 987.6 |
| PROPOSED-FOLLOWERS-ONLY | 0.0695 | 0.0103 | 0.1214 | 1012.8 |
| PROPOSED-STACKELBERG | 0.0279 | 0.0073 | 0.2161 | 1697.7 |
| PROPOSED-CENTRALIZED | 0.1252 | 0.0020 | 0.1429 | 1163.7 |

The Stackelberg fast run improves the balance-index means, but it does so while increasing boundary load, overflow ratio, terminal vehicles, and total TTT. This is not an acceptable control result; it indicates that the allocation/balance proxy is being satisfied in a way that is misaligned with closed-loop throughput.

### Failure Diagnosis

Compared with the previous full allocation Stackelberg run:

| diagnostic | full allocation mean | relaxed-fast v3 mean |
|---|---:|---:|
| selected `N_UF_star` | 5612.322 | 2795.454 |
| `distributed_response_ramp_release_veh` | 440.039 | 235.628 |
| `distributed_response_onramp_green_veh` | 427.220 | 218.989 |
| `leader_follower_ttt_base` | 622.733 | 1590.420 |
| `leader_density_penalty` | 0.375 | 61.214 |
| `leader_total_objective` | 673.502 | 1714.152 |

Closed-loop traces show that relaxed-fast starts by opening high ramp targets, then density penalty rises and the leader begins choosing much lower `N_UF_star` values, including one `0` target. The final effect is under-release to the freeway, reduced throughput, larger urban/on-ramp storage, and worse TTT.

A first-step comparison also showed that disabling early stop while keeping the fast warm-start module (`36` particles, `48` iterations, no early stop) still selected the same first-step fast response. Therefore the failure is not only early stopping. The more likely issue is that the warm-started allocation response and current follower proxy can rank leader candidates differently from the old full allocation path, and the resulting closed-loop trajectory falls into a low-metering/high-urban-storage regime.

### Failed Criteria And Next Modification

Verdict: **FAIL for performance**, **PASS for unit/runtime correctness**.

Failed criteria:

- `PROPOSED-STACKELBERG` does not beat `PROPOSED-FOLLOWERS-ONLY`.
- `PROPOSED-STACKELBERG` does not reach the default `8%` improvement threshold over `WU-CD-F`.
- Boundary balance index improves, but boundary load/overflow and TTT degrade.

Recommended next modification:

- Do not use the current relaxed-fast allocation path as the final comparison controller.
- Add a closed-loop aligned term to the allocation/follower response objective for on-ramp service and terminal residual queues, rather than relying mostly on balance plus net-flow residual.
- Alternatively, keep fast mode only for screening and use the full allocation module for final Stackelberg comparison until the fast proxy is calibrated against full closed-loop behavior.

## 2026-06-18 Relaxed-Fast Allocation Without Warm Start

### What Was Implemented

- Removed all previous-response warm-start behavior from `RelaxedFastAllocationModule`.
- Removed the warm-start cache keyed by leader action and movement set.
- Removed `relaxed_fast_allocation_warm_start_noise` from config/schema.
- Kept only deterministic midpoint/greedy seeds plus random particles.
- Kept early stopping with the same budget:
  - particles `36`;
  - max iterations `32`;
  - min iterations `16`;
  - patience `8`;
  - tolerance `1.0e-5`.
- Kept compatibility diagnostics, but `allocation_pso_previous_warm_start_used` and `allocation_pso_warm_start_seed_count` are now always `0.0`.

### Changed Files

- `src/controllers/relaxed_fast_allocation.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/tests/test_constraints.py`
- `docs/spec/17_relaxed_quantized_fast_mode.md`
- `reports/codex_run_report.md`

### Validation Commands

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\relaxed_fast_allocation.py src\controllers\urban_follower.py src\models\state.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_relaxed_fast_uses_early_stop_allocation_module_without_warm_start src.tests.test_constraints.ConstraintTests.test_relaxed_quantized_controls_are_off_by_default src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints src.tests.test_forecast_awareness src.tests.test_six_controller_comparison -v
```

Result:

```text
targeted tests: 3 tests, OK
constraints + forecast + six-controller comparison: 87 tests, OK
```

### 7200 s Peak Run Command

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --config src/config/default.yaml --scenario peak_demand --T-total 7200 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --relaxed-fast-mode --output outputs/peak_7200_four_controller_relaxed_fast_earlystop_only_2026_06_18_v1
```

Output:

```text
WU-CD-F: ttt=11645.9 delay=10501.9 authority_ok=True
PROPOSED-FOLLOWERS-ONLY: ttt=7411.6 delay=6267.5 authority_ok=True
PROPOSED-STACKELBERG: ttt=8146.8 delay=7002.8 authority_ok=True
PROPOSED-CENTRALIZED: ttt=6369.1 delay=5225.1 authority_ok=True
```

| controller | total TTT | total delay | throughput veh/h | terminal veh | computation s | solver evals |
|---|---:|---:|---:|---:|---:|---:|
| WU-CD-F | 11645.893 | 10501.874 | 7945.7 | 13467.4 | 13.04 | 1059 |
| PROPOSED-FOLLOWERS-ONLY | 7411.565 | 6267.545 | 10790.0 | 7782.8 | 0.84 | 1495 |
| PROPOSED-STACKELBERG | 8146.788 | 7002.768 | 9600.4 | 10164.6 | 65.73 | 9360 |
| PROPOSED-CENTRALIZED | 6369.101 | 5225.081 | 11304.3 | 6754.2 | 110.35 | 640 |

### Warm-Start Removal Effect

| Stackelberg variant | total TTT | throughput veh/h | terminal veh | computation s | mean `N_UF_star` | mean ramp release veh | warm-start used |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full allocation reference | 7207.966 | 10913.7 | 7537.2 | 137.42 | 5612.322 | 440.039 | NA |
| Warm-start fast v3 | 11131.502 | 8539.9 | 12283.9 | 77.91 | 2795.454 | 235.628 | 0.700 |
| Early-stop only | 8146.788 | 9600.4 | 10164.6 | 65.73 | 4118.968 | 320.858 | 0.000 |

Removing warm-start clearly improves the fast Stackelberg result:

- TTT improves by `2984.714 veh*h` versus warm-start fast.
- Computation time improves from `77.91 s` to `65.73 s`.
- Mean `N_UF_star` and ramp release recover substantially.
- Diagnostics confirm `allocation_pso_previous_warm_start_used = 0.0` for all decisions.

### Boundary Queue Balancing Result

Mean values over the early-stop-only 7200 s run:

| controller | B_in | B_out | overflow ratio | boundary-in load veh |
|---|---:|---:|---:|---:|
| WU-CD-F | 0.0648 | 0.0187 | 0.1232 | 987.6 |
| PROPOSED-FOLLOWERS-ONLY | 0.0695 | 0.0103 | 0.1214 | 1012.8 |
| PROPOSED-STACKELBERG | 0.0308 | 0.0049 | 0.1536 | 1342.6 |
| PROPOSED-CENTRALIZED | 0.1252 | 0.0020 | 0.1429 | 1163.7 |

Early-stop-only Stackelberg still improves `B_in/B_out` versus follower-only, but it worsens overflow ratio and boundary-in load. The balance proxy remains partially misaligned with closed-loop TTT.

### Failed Criteria And Next Modification

Verdict: **FAIL for final performance**, **PASS for runtime/test correctness**.

Compared with warm-start fast, the early-stop-only modification is clearly better and suggests the warm-start cache was a real source of bad closed-loop behavior. However:

- `PROPOSED-STACKELBERG` is still worse than `PROPOSED-FOLLOWERS-ONLY` by `735.223 veh*h`.
- It remains worse than the full allocation Stackelberg reference by `938.822 veh*h`.
- It improves over `WU-CD-F` by `3499.105 veh*h` (`33.32% delay improvement`) and is cheaper than centralized, but it does not satisfy the proposed-controller leader-value criterion.

Recommended next modification:

- Keep warm-start disabled.
- Test whether early stopping alone should use a higher minimum iteration count or full `48` iterations with no warm-start.
- More importantly, revise the allocation/follower response proxy so lower `B_in/B_out` cannot be achieved by creating larger terminal boundary load and lower freeway release.

## 2026-06-18 Pure Early-Stop PSO Audit

### Why Performance Changed

The previous "early-stop only" implementation was not actually identical to the
full allocation PSO before the stopping rule. It changed several PSO details:

- max iterations changed from full `48` to fast `32`;
- random seed changed from `seed` to `seed + 7919 * solve_count`;
- deterministic midpoint/greedy particles were injected into the initial swarm;
- initial velocity noise changed from `0.10 * span` to `0.08 * span`.

Therefore its performance could change even without warm-start. This was a code
issue in the experimental fast module, not evidence that early stopping itself
is harmless.

### Correction

`RelaxedFastAllocationModule` was revised so that it now matches the full
allocation PSO before the stop rule:

- same `allocation_pso_particles`;
- same `allocation_pso_iterations`;
- same `np.random.default_rng(seed)`;
- same random initial particle matrix;
- same `0.10 * span` initial velocity scale;
- no warm-start cache or previous-response seed.

Only the stop rule remains different. The default stop guard was made more
conservative:

```text
relaxed_fast_allocation_pso_min_iterations = 36
relaxed_fast_allocation_pso_patience = 8
relaxed_fast_allocation_pso_tol = 1.0e-6
```

### Evidence

First-decision diagnostic:

| variant | objective | selected `N_UF_star` | allocation iterations | ramp release veh |
|---|---:|---:|---:|---:|
| full module | 131.227 | 3000.0 | full module | 289.653 |
| pure early-stop, old loose guard | 133.733 | 3000.0 | 18 | 269.611 |
| pure early-stop, conservative guard | 131.205 | 3000.0 | 42 | 289.949 |
| same module, stop disabled | 131.227 | 3000.0 | 48 | 289.653 |

The stop-disabled relaxed module exactly reproduces the full module on the
first decision. A 7200 s Stackelberg-only run with the relaxed module and stop
disabled also exactly reproduced the full-allocation reference:

```text
PROPOSED-STACKELBERG no-stop same PSO:
total_ttt = 7207.966
total_delay = 6063.946
throughput = 10913.7 veh/h
terminal_total_vehicles = 7537.2
computation_time_sec = 143.51
```

This confirms that the remaining performance change comes from the early-stop
criterion itself, not from hidden plant/controller changes.

### Conservative Pure Early-Stop 7200 s Run

Command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --config src/config/default.yaml --scenario peak_demand --T-total 7200 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --relaxed-fast-mode --output outputs/peak_7200_four_controller_relaxed_fast_earlystop_pure_conservative_2026_06_18_v1
```

Output:

```text
WU-CD-F: ttt=11645.9 delay=10501.9 authority_ok=True
PROPOSED-FOLLOWERS-ONLY: ttt=7411.6 delay=6267.5 authority_ok=True
PROPOSED-STACKELBERG: ttt=8608.1 delay=7464.0 authority_ok=True
PROPOSED-CENTRALIZED: ttt=6369.1 delay=5225.1 authority_ok=True
```

| Stackelberg variant | total TTT | throughput veh/h | terminal veh | computation s | mean allocation iter |
|---|---:|---:|---:|---:|---:|
| full allocation reference | 7207.966 | 10913.7 | 7537.2 | 137.42 | 48 |
| pure early-stop conservative | 8608.054 | 9422.5 | 10520.4 | 119.50 | 39.075 |
| same relaxed module, stop disabled | 7207.966 | 10913.7 | 7537.2 | 143.51 | 48 |

### Interpretation

Even with identical PSO initialization and a conservative guard, the current
early-stop rule still changes closed-loop performance because PSO often has
late improvements after a temporary objective plateau. In the 7200 s run,
`allocation_pso_early_stopped` was active in `92.5%` of Stackelberg decisions
with a mean of `39.075 / 48` iterations. Those small follower-response
differences changed leader candidate rankings, lowered mean selected
`N_UF_star` (`5612.322 -> 3846.046`), and reduced mean ramp release
(`440.039 -> 292.967`).

Verdict: **Do not use early-stop allocation PSO as a performance-equivalent
replacement yet.** It is computationally faster, but the stop criterion is not a
safe convergence certificate for this PSO/follower response problem.

Recommended next modification:

- Treat allocation early-stop as an optional screening diagnostic only.
- For final four-controller comparison, use the full allocation PSO or disable
  early stop with `min_iterations = allocation_pso_iterations`.
- If early-stop is still desired, require a stronger certificate, such as
  checking objective stability plus particle-spread/control-vector stability
  over multiple iterations, not objective stagnation alone.

## 2026-06-18 Allocation Objective Vectorization

### What Was Implemented

The safe computation-cost reduction path was implemented first: keep the full
allocation PSO search unchanged, but vectorize the objective evaluation over
particles.

Changes:

- Added `_ObjectiveContext` in `src/controllers/inflow_outflow_allocation.py`.
- Added `_objective_context()`, `_objective_many()`, and `_balance_index_many()`.
- Updated `InflowOutflowAllocationModule._run_pso()` so that:
  - particle count is unchanged;
  - max iterations are unchanged;
  - random seed is unchanged;
  - particle initialization is unchanged;
  - velocity initialization is unchanged;
  - PSO update order is unchanged;
  - only particle objective evaluation is batched.
- Added a regression test comparing scalar `_objective()` and batch
  `_objective_many()` to `1e-12` precision.

This is not a solver approximation. It should return the same PSO trajectory
and same selected allocation up to floating-point roundoff.

### Changed Files

- `src/controllers/inflow_outflow_allocation.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

Existing uncommitted files from the previous early-stop experiment remain in the
working tree, but the vectorized full-allocation result below uses
`relaxed_fast_mode = false`.

### Validation Commands

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\inflow_outflow_allocation.py src\controllers\relaxed_fast_allocation.py src\controllers\urban_follower.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_allocation_batch_objective_matches_scalar_objective src.tests.test_constraints.ConstraintTests.test_relaxed_fast_uses_early_stop_allocation_module_without_warm_start -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints src.tests.test_forecast_awareness src.tests.test_six_controller_comparison -v
```

Result:

```text
targeted tests: 2 tests, OK
constraints + forecast + six-controller comparison: 88 tests, OK
```

### Objective Micro-Benchmark

Same state, same particle matrix, `36` particles, `1000` repeated evaluations:

```text
scalar objective loop: 11.0999 s
batched objective:      0.0726 s
speedup:              152.79x
max_abs_diff:           1.28e-13
```

### Peak 7200 s Stackelberg-Only Check

Run condition:

- scenario: `peak_demand`
- horizon: `7200 s`
- controller: `PROPOSED-STACKELBERG`
- `relaxed_fast_mode = false`
- same reduced Stage 1 screening budget as the previous full-allocation
  reference: `leader_candidate_count = 5`, `max_nash_iter = 3`,
  `freeway_prediction_horizon_steps = 3`

Result:

| Stackelberg run | total TTT | delay | throughput veh/h | terminal veh | computation s |
|---|---:|---:|---:|---:|---:|
| pre-vectorization full allocation reference | 7207.966 | 6063.946 | 10913.7 | 7537.2 | 137.42 |
| vectorized full allocation | 7207.966 | 6063.946 | 10913.7 | 7537.2 | 8.56 |

The closed-loop metrics are identical to the reference, while Stackelberg
controller computation dropped by about `93.8%`.

### Peak 7200 s Four-Controller Run

Output root:

```text
outputs/peak_7200_four_controller_vectorized_full_allocation_2026_06_18_v1
```

Run condition:

- scenario: `peak_demand`
- horizon: `7200 s`
- controllers: `WU-CD-F`, `PROPOSED-FOLLOWERS-ONLY`,
  `PROPOSED-STACKELBERG`, `PROPOSED-CENTRALIZED`
- `relaxed_fast_mode = false`
- same Stage 1 screening budget overrides as above.

Output:

```text
WU-CD-F: ttt=11645.9 delay=10501.9 authority_ok=True comp=12.86
PROPOSED-FOLLOWERS-ONLY: ttt=7411.6 delay=6267.5 authority_ok=True comp=0.82
PROPOSED-STACKELBERG: ttt=7208.0 delay=6063.9 authority_ok=True comp=8.6
PROPOSED-CENTRALIZED: ttt=6369.1 delay=5225.1 authority_ok=True comp=107.95
```

| controller | total TTT | total delay | throughput veh/h | terminal veh | computation s |
|---|---:|---:|---:|---:|---:|
| WU-CD-F | 11645.893 | 10501.874 | 7945.7 | 13467.4 | 12.86 |
| PROPOSED-FOLLOWERS-ONLY | 7411.565 | 6267.545 | 10790.0 | 7782.8 | 0.82 |
| PROPOSED-STACKELBERG | 7207.966 | 6063.946 | 10913.7 | 7537.2 | 8.60 |
| PROPOSED-CENTRALIZED | 6369.101 | 5225.081 | 11304.3 | 6754.2 | 107.95 |

### Interpretation

This vectorization resolves the immediate computation-cost concern without
damaging closed-loop performance:

- Stackelberg is now far cheaper than centralized in wall-clock controller time:
  `8.60 s` vs `107.95 s`.
- Stackelberg remains slightly better than follower-only on TTT:
  `7207.966` vs `7411.565`.
- Stackelberg remains far better than `WU-CD-F` on TTT:
  `7207.966` vs `11645.893`.

Verdict: **PASS for the computation-cost reduction attempt**, while the broader
research performance criterion remains as before: Stackelberg's leader value
over follower-only is positive but still below the default `8%` improvement
threshold.

Next step:

- Do not implement leader candidate screening yet. The vectorization speedup is
  large enough that screening is not currently necessary, and screening would
  introduce a new approximation that could affect leader candidate ranking.

## 2026-06-18: Wu-CD-F Peak 7200 s No-Control Baseline and Implementation Diagnosis

### Purpose

The user suspected that `WU-CD-F` was performing too poorly because something
was missing or incorrectly implemented. I checked the declared Wu authority,
control traces, no-control baseline, and two higher-fidelity Wu sensitivity
runs.

### Files Changed

- No controller code changed in this diagnostic pass.
- New simulation outputs were written under:
  - `outputs/peak_7200_no_control_vectorized_context_2026_06_18_v1`
  - `outputs/wu_peak_7200_relaxed_default_2026_06_18_v1`
  - `outputs/wu_peak_7200_full_enum_default_2026_06_18_v1`
- This report was updated.

### Commands / Conditions

No-control baseline:

```text
custom baseline loop using baseline_control("no_control"),
scenario=peak_demand, T_total=7200 s, same plant/demand/free-flow reference
as outputs/peak_7200_four_controller_vectorized_full_allocation_2026_06_18_v1
```

Wu sensitivity runs:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --config src/config/default.yaml --scenario peak_demand --T-total 7200 --controllers WU-CD-F --relaxed-quantized-controls --output outputs/wu_peak_7200_relaxed_default_2026_06_18_v1

C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.six_controller_comparison --config src/config/default.yaml --scenario peak_demand --T-total 7200 --controllers WU-CD-F --output outputs/wu_peak_7200_full_enum_default_2026_06_18_v1
```

The current four-controller comparison remains:

```text
outputs/peak_7200_four_controller_vectorized_full_allocation_2026_06_18_v1
```

### Main Results Versus No-Control

| controller | TTT | TTT improvement vs no-control | delay | delay improvement vs no-control | throughput veh/h | terminal veh | comp s |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 11659.562 | 0.00% | 10515.542 | 0.00% | 7936.1 | 13488.0 | 0.00 |
| WU-CD-F, current comparison budget | 11645.893 | 0.12% | 10501.874 | 0.13% | 7945.7 | 13467.4 | 12.86 |
| WU-CD-F, relaxed default Smax/Np | 11633.970 | 0.22% | 10489.950 | 0.24% | 7949.1 | 13460.5 | 61.38 |
| WU-CD-F, full enumeration default Smax/Np | 11513.726 | 1.25% | 10369.706 | 1.39% | 7986.6 | 13388.1 | 200.51 |
| PROPOSED-FOLLOWERS-ONLY | 7411.565 | 36.43% | 6267.545 | 40.40% | 10790.0 | 7782.8 | 0.82 |
| PROPOSED-STACKELBERG | 7207.966 | 38.18% | 6063.946 | 42.33% | 10913.7 | 7537.2 | 8.60 |
| PROPOSED-CENTRALIZED | 6369.101 | 45.37% | 5225.081 | 50.31% | 11304.3 | 6754.2 | 107.95 |

### Control Trace Diagnosis

| controller | VSL active steps | min VSL | green changed steps | ramp metering changed | offset changed | allocation used |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 0/40 | 100 | 0/40 | 0/40 | 0/40 | 0/40 |
| WU-CD-F, current comparison budget | 0/40 | 100 | 40/40 | 0/40 | 0/40 | 0/40 |
| WU-CD-F, relaxed default Smax/Np | 0/40 | 100 | 40/40 | 0/40 | 0/40 | 0/40 |
| WU-CD-F, full enumeration default Smax/Np | 36/40 | 50 | 23/40 | 0/40 | 0/40 | 0/40 |

Authority check:

- This is consistent with `docs/spec/16_six_controller_comparison.md` and
  `src/analysis/authority.py`: Wu group is allowed to change only green and
  VSL. Ramp metering is fixed at capacity, offset is fixed at zero, and
  inflow/outflow allocation is unused.
- The current comparison-budget `WU-CD-F` was not doing ramp metering or offset
  control because those controls are intentionally outside Wu authority, not
  because they were silently broken.
- The full-enumeration Wu run does activate segment-level VSL in 36 of 40
  intervals, so VSL is not fundamentally unimplemented. However, even with VSL
  active, the improvement over no-control is only `1.25%` TTT.

### Boundary Queue Balancing

| controller | mean boundary-in q | final boundary-in q | max boundary-in q | mean boundary-out q | final boundary-out q | max boundary-out q |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 978.1 | 3231.7 | 3231.7 | 30.1 | 14.9 | 56.6 |
| WU-CD-F, current comparison budget | 987.6 | 3212.1 | 3212.1 | 32.4 | 16.0 | 57.0 |
| WU-CD-F, full enumeration default Smax/Np | 942.8 | 3160.3 | 3160.3 | 28.5 | 16.9 | 55.2 |
| PROPOSED-FOLLOWERS-ONLY | 1012.8 | 3157.9 | 3157.9 | 42.0 | 9.2 | 83.6 |
| PROPOSED-STACKELBERG | 1613.5 | 4001.7 | 4001.7 | 26.3 | 15.4 | 51.8 |
| PROPOSED-CENTRALIZED | 1163.7 | 3045.8 | 3045.8 | 33.4 | 72.4 | 72.4 |

### Interpretation

The large gap is not primarily a missing implementation in `WU-CD-F`. The
dominant reason is authority/package difference:

- Wu has no ramp metering. In this peak case, the proposed controllers gain most
  of their system benefit by regulating freeway entry and preventing freeway
  accumulation/terminal vehicles from exploding.
- Wu has no offset control and no inflow/outflow allocation, so urban signal
  coordination is limited to phase green split.
- Current comparison-budget Wu uses a relaxed VSL shortcut and a reduced
  Smax/Np, which weakens it slightly. Restoring default Smax/Np and full
  enumeration improves TTT from `11645.893` to `11513.726`, but that is still
  only `1.25%` better than no-control.
- Full-enumeration Wu activates VSL, but VSL alone is too weak in this scenario:
  it can slightly reduce terminal accumulation, yet without ramp metering it
  cannot sufficiently control on-ramp/freeway inflow.

### Failed Criteria / Next Modification

- `WU-CD-F` does not meet the default `8%` improvement threshold versus
  no-control in peak 7200 s, even under full enumeration.
- No code correction is recommended solely from this diagnostic result.
- If a stronger Wu reference is desired, the fair next experiment is to run
  `WU-CC-F` or a separate "Wu + ramp metering" ablation, but that would no
  longer be the declared Wu authority in spec 16.

## 2026-06-18: All-Scenario 7200 s Four-Controller Relaxed-Fast Run

### Purpose

The user asked to rerun all six scenarios for the four primary controllers
using `relaxed_fast_mode=true`, then interpret controller behavior with
quantitative and visual activation evidence.

Clarification:

- `relaxed_fast_mode` is not a MILP solve.
- It enables `relaxed_quantized_controls`, uses continuous/heuristic targets,
  repairs them to feasible quantized controls, and applies smaller screening
  budgets.
- In this run: `leader_candidate_count=5`, `max_nash_iter=3`,
  `optimizer_maxiter=16`, `optimizer_n_starts=1`,
  `freeway_prediction_horizon_steps=3`.

Detailed report:

```text
reports/relaxed_fast_all_scenarios_7200_control_method_report.md
```

Output root:

```text
outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1
```

Generated evidence:

```text
outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/summary_with_no_control.csv
outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/activation_summary.csv
outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/representative_timeseries.csv
outputs/all_scenarios_7200_four_controller_relaxed_fast_2026_06_18_v1/analysis/charts/*.svg
```

### Commands / Conditions

The run used a custom Python loop calling `run_controller(...)` for each
controller and `baseline_control("no_control")` for the no-control comparison,
with the same scenario plant, demand, horizon, and free-flow reference per
scenario.

Controllers:

- `WU-CD-F`
- `PROPOSED-FOLLOWERS-ONLY`
- `PROPOSED-STACKELBERG`
- `PROPOSED-CENTRALIZED`

Scenarios:

- `low_demand`
- `medium_demand`
- `peak_demand`
- `oversaturated_demand`
- `incident_or_capacity_drop`
- `capacity_drop`

### Main Results

Total TTT, veh-h:

| scenario | no-control | WU | P-FO | P-Stack | P-Cent | best incl. no-control | best 4-controller |
|---|---:|---:|---:|---:|---:|---|---|
| low_demand | 695.7 | 709.1 | 1139.9 | 1285.8 | 871.5 | No control | WU |
| medium_demand | 1944.0 | 1991.2 | 4042.8 | 3444.8 | 3633.2 | No control | WU |
| peak_demand | 11659.6 | 11645.9 | 7411.6 | 8608.1 | 6369.1 | P-Cent | P-Cent |
| oversaturated_demand | 19734.2 | 19739.1 | 13365.8 | 17978.8 | 15863.5 | P-FO | P-FO |
| incident_or_capacity_drop | 10473.2 | 10447.0 | 7159.4 | 8412.6 | 5826.2 | P-Cent | P-Cent |
| capacity_drop | 31794.5 | 33593.1 | 34867.8 | 40022.5 | 35096.9 | No control | WU |

Improvement versus no-control:

| scenario | WU | P-FO | P-Stack | P-Cent |
|---|---:|---:|---:|---:|
| low_demand | -1.92% | -63.85% | -84.81% | -25.27% |
| medium_demand | -2.43% | -107.97% | -77.20% | -86.90% |
| peak_demand | 0.12% | 36.43% | 26.17% | 45.37% |
| oversaturated_demand | -0.03% | 32.27% | 8.89% | 19.61% |
| incident_or_capacity_drop | 0.25% | 31.64% | 19.68% | 44.37% |
| capacity_drop | -5.66% | -9.67% | -25.88% | -10.39% |

### Activation Evidence

Peak demand:

- `WU-CD-F`: green active `100%`, ramp/VSL/offset/allocation `0%`;
  TTT improvement only `0.12%`.
- `PROPOSED-FOLLOWERS-ONLY`: ramp metering active `100%`, offset active `100%`,
  VSL `0%`; mean applied metering flow `2976 veh/h` versus potential no-meter
  flow `5956 veh/h`; density exceedance drops to `0`; TTT improvement `36.43%`.
- `PROPOSED-CENTRALIZED`: allocation active `100%`, offset active `100%`,
  green active `95%`, explicit ramp metering `0%`, VSL `0%`; freeway TTT drops
  from `4900` to `338 veh-h`; total TTT improvement `45.37%`.

Oversaturated demand:

- `PROPOSED-FOLLOWERS-ONLY` is best: ramp active `100%`, restriction ratio
  `0.5988`, throughput rises from `7431` to `10503 veh/h`, total TTT improves
  `32.27%`.

Capacity-drop:

- All four active controllers are worse than no-control.
- `PROPOSED-STACKELBERG` is the clearest over-control case: ramp active `100%`,
  restriction ratio `0.8441`, VSL active `97.5%`, allocation active `100%`;
  throughput falls to `7063 veh/h`, and total TTT worsens `25.88%`.

### Interpretation

- Low/medium/capacity-drop: active control is currently unnecessary or
  over-aggressive in relaxed-fast mode. Wu is the best of the four active
  controllers only because it is least invasive; no-control is still better.
- Peak/incident/oversaturated: proposed authority matters. The gains come
  mostly from ramp metering and coordinated allocation/offset/green behavior,
  not from VSL in this relaxed-fast run.
- VSL is not a dominant positive mechanism here. It remains neutral in peak and
  becomes active mainly in capacity-drop or centralized oversaturated cases,
  where it does not by itself guarantee total TTT improvement.
- Stackelberg remains the concern: it activates the full proposed package but
  often protects freeway states by transferring too much cost to the urban/ramp
  side under the current relaxed-fast approximation.

### Control Validation Summary

- Authority checks in `all_controller_summary.csv` are `True` for all four
  controllers and all scenarios.
- No code changes were made for this run.
- Unit tests were not rerun because this was a simulation/reporting pass only.

### Proposed Next Modification

Add or tune regime-aware activation gates for relaxed-fast mode:

- avoid ramp metering when low/medium demand has no freeway receiving stress;
- avoid leader/allocation over-restriction when urban/ramp queue cost dominates;
- treat VSL as bottleneck-specific evidence, not a default remedy in deep
  oversaturation or pure capacity-drop regimes.

## 2026-06-18: removed relaxed-fast code path and kept relaxed-quantized mode

### What Was Implemented

- Removed the separate `relaxed_fast_mode` control path from active code.
- Kept `relaxed_quantized_controls` as the supported computationally practical
  mode.
- Removed the dedicated relaxed-fast allocation module from the active
  controller path.
- Updated active specs so heuristic rules are treated as proposal generators and
  final follower actions are expected to be selected by TTT/TTS-compatible
  argmin.

### Files Changed

- `src/controllers/urban_follower.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/experiments/six_controller_comparison.py`
- `src/tests/test_constraints.py`
- `docs/spec/17_relaxed_quantized_fast_mode.md`
- `docs/spec/18_follower_tts_objective_alignment.md`
- `docs/perimeter_control_boundary_design_note.md`
- `reports/codex_run_report.md`

### Baseline Run Command

Not run. This was a code cleanup/spec-alignment step only.

### Proposed-Controller Run Command

Not run. The next simulation should use `relaxed_quantized_controls=true`
without a separate fast-mode shortcut.

### Baseline Total TTT/TTS

Not measured in this cleanup step.

### Proposed Total TTT/TTS

Not measured in this cleanup step.

### Improvement Rate

Not measured in this cleanup step.

### Boundary Queue Balancing Result

Not measured in this cleanup step.

### Control Validation Summary

Static compile and cleanup-focused tests passed.

Commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src/controllers/urban_follower.py src/models/state.py src/experiments/six_controller_comparison.py src/tests/test_constraints.py src/controllers/inflow_outflow_allocation.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_relaxed_quantized_controls_are_off_by_default src.tests.test_constraints.ConstraintTests.test_allocation_batch_objective_matches_scalar_objective
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints
```

Results:

```text
py_compile: OK
targeted cleanup tests: 2 tests, OK
constraints suite: 50 tests, OK
```

Active code/spec references to `relaxed_fast_mode`,
`RelaxedFastAllocationModule`, `relaxed_fast_allocation`, and
`--relaxed-fast-mode` were removed. Historical run-report entries were kept as
provenance for previous failed fast-mode experiments.

### Failed Criteria

Full acceptance is not claimed. No closed-loop smoke test or full scenario run
was executed for this cleanup step.

### Proposed Next Modification

Implement the follower objective alignment from
`docs/spec/18_follower_tts_objective_alignment.md`:

- joint ramp-metering/VSL local TTS candidate evaluation;
- urban stage-2 green/offset TTS candidate evaluation;
- default/no-control guard candidates in WU-CD-F and PROPOSED-FOLLOWERS-ONLY;
- relaxed-quantized proposal-centered search instead of direct pressure-rule
  selection.

## 2026-06-18: follower TTS objective alignment and 7200 s all-scenario run

### What Was Implemented

- Freeway follower ramp metering now includes no-metering/default and
  previous-control guard candidates before heuristic candidates.
- Freeway follower VSL in relaxed-quantized mode now uses a pressure proposal
  center plus feasible neighboring VSL candidates; the final action is chosen by
  horizon local TTS-compatible objective evaluation.
- Freeway objective now includes freeway vehicle TTS, ramp queue TTS, and
  predicted upstream/on-ramp urban queue TTS, plus existing density,
  overflow/receiving, and smoothness terms.
- Distributed freeway agents now jointly evaluate ramp metering and VSL
  candidate pairs rather than choosing ramp metering first and VSL second.
  Diagnostics include candidate counts, joint evaluations, ramp queue TTS, and
  on-ramp urban queue TTS.
- Urban follower stage-2 green time and offset control now builds candidate
  neighborhoods from default, previous, heuristic, pressure, and allocation
  setpoint centers; final green/offset selection uses a local urban
  TTS-compatible argmin.
- WU-CD-F relaxed green and VSL paths now treat pressure rules as proposal
  centers and evaluate feasible neighborhoods, including default/previous
  guards.
- Added a reusable all-scenario 4-controller driver that runs the no-control
  baseline in the same scenario/demand/horizon loop and writes no-control
  comparisons.

### Files Changed

- `src/controllers/freeway_follower.py`
- `src/controllers/distributed_coordinator.py`
- `src/controllers/urban_follower.py`
- `src/controllers/wu_distributed.py`
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Baseline Run Command

The no-control baseline was run inside the paired all-scenario driver for each
scenario using the same config, seed, demand, and 7200 s horizon as the
controller runs:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario all --T-total 7200 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --output outputs\all_scenarios_7200_four_controller_tts_aligned_relaxed_quantized_2026_06_18_v1 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

Important run settings:

- `relaxed_quantized_controls=true`
- full allocation module path, no `relaxed_fast_mode`
- screening MPC budgets: `leader_candidate_count=5`, `max_nash_iter=3`,
  `optimizer_maxiter=16`, `optimizer_n_starts=1`,
  `freeway_prediction_horizon_steps=3`

### Proposed-Controller Run Command

Same command as above. The driver runs `NO-CONTROL`, `WU-CD-F`,
`PROPOSED-FOLLOWERS-ONLY`, `PROPOSED-STACKELBERG`, and
`PROPOSED-CENTRALIZED` for each scenario and writes paired comparison CSVs.

Output:

```text
outputs\all_scenarios_7200_four_controller_tts_aligned_relaxed_quantized_2026_06_18_v1
```

Key files:

- `all_no_control_summary.csv`
- `all_controller_summary.csv`
- `analysis\summary_with_no_control.csv`
- `analysis\controller_vs_no_control.csv`
- per-controller `run_log.csv`, `control_timeseries.csv`,
  `decision_diagnostics.csv`

### Baseline Total TTT/TTS

| scenario | no-control total TTT |
|---|---:|
| low_demand | 695.716 |
| medium_demand | 1943.962 |
| peak_demand | 11659.562 |
| oversaturated_demand | 19734.156 |
| incident_or_capacity_drop | 10473.200 |
| capacity_drop | 31794.474 |

### Proposed Total TTT/TTS and Improvement

| scenario | WU-CD-F | P-FO | P-Stack | P-Cent |
|---|---:|---:|---:|---:|
| low_demand | 695.716 / 0.000% | 3654.782 / -425.327% | 4239.403 / -509.358% | 871.492 / -25.265% |
| medium_demand | 1943.916 / 0.002% | 5482.993 / -182.052% | 6628.035 / -240.955% | 3633.187 / -86.896% |
| peak_demand | 11655.629 / 0.034% | 7266.195 / 37.680% | 10203.140 / 12.491% | 6369.101 / 45.374% |
| oversaturated_demand | 19719.156 / 0.076% | 17306.003 / 12.304% | 14290.845 / 27.583% | 15863.496 / 19.614% |
| incident_or_capacity_drop | 10470.933 / 0.022% | 6949.487 / 33.645% | 9439.356 / 9.871% | 5826.187 / 44.371% |
| capacity_drop | 33082.793 / -4.052% | 34339.448 / -8.004% | 38689.695 / -21.687% | 35096.930 / -10.387% |

### Boundary Queue Balancing Result

`mean_B_sum = mean_B_in + mean_B_out`, compared against no-control in the same
scenario.

| scenario | no-control B_sum | WU-CD-F | P-FO | P-Stack | P-Cent |
|---|---:|---:|---:|---:|---:|
| low_demand | 0.150430 | 0.150430 | 0.110993 | 0.069637 | 0.336063 |
| medium_demand | 0.189289 | 0.189235 | 0.109151 | 0.063039 | 0.144306 |
| peak_demand | 0.082207 | 0.082404 | 0.074613 | 0.025493 | 0.127246 |
| oversaturated_demand | 0.041634 | 0.041993 | 0.055408 | 0.016039 | 0.069875 |
| incident_or_capacity_drop | 0.091609 | 0.091718 | 0.077386 | 0.030947 | 0.138681 |
| capacity_drop | 0.044671 | 0.012552 | 0.014527 | 0.006360 | 0.014206 |

Boundary balance is mixed:

- P-FO improves mean B_sum in low, medium, peak, incident, and capacity-drop,
  but worsens it in oversaturated demand.
- P-Stack improves mean B_sum in all scenarios, but its max boundary overflow
  ratio is worse than no-control in low, medium, incident, and capacity-drop.
- P-Cent often improves TTT in congested scenarios, but worsens mean B_sum in
  low, peak, oversaturated, and incident scenarios.
- Therefore boundary non-degradation is not globally satisfied.

### Control Validation Summary

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\freeway_follower.py src\controllers\distributed_coordinator.py src\controllers\urban_follower.py src\controllers\wu_distributed.py src\experiments\all_scenarios_four_controller_comparison.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_freeway_ramp_candidates_include_default_and_previous_guard src.tests.test_constraints.ConstraintTests.test_relaxed_urban_stage2_evaluates_default_guard_and_neighborhood src.tests.test_constraints.ConstraintTests.test_distributed_freeway_agent_jointly_evaluates_metering_and_vsl_guards src.tests.test_constraints.ConstraintTests.test_relaxed_wu_urban_green_evaluates_neighborhood_candidates -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest discover -s src\tests -v
```

Results:

```text
py_compile: OK
targeted follower-alignment tests: 4 tests, OK
constraints suite: 54 tests, OK
full unittest discovery: 152 tests, OK
closed-loop smoke test: completed inside unittest discovery
7200 s all-scenario 4-controller run: completed
```

Control logging:

- `control_timeseries.csv` includes ramp metering, VSL, offset, green time, and
  allocation fields for all controller runs.
- Proposed distributed/freeway logs include `joint_candidate_evaluations`,
  `ramp_queue_tts`, and `onramp_urban_queue_tts`.
- New run outputs contain no active `relaxed_fast_mode` field.
- Authority checks are `True` for all four active controllers in all scenarios.

Activation diagnostics:

| scenario/controller | ramp active | VSL active | offset active | green active | allocation active | mean metering ratio |
|---|---:|---:|---:|---:|---:|---:|
| low / P-FO | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.289 |
| low / P-Stack | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 0.258 |
| medium / P-FO | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.409 |
| medium / P-Stack | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 0.337 |
| peak / P-FO | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.508 |
| peak / P-Stack | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 0.334 |
| oversaturated / P-FO | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.832 |
| oversaturated / P-Stack | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 0.379 |
| capacity_drop / P-FO | 1.00 | 0.78 | 1.00 | 1.00 | 0.00 | 0.449 |
| capacity_drop / P-Stack | 1.00 | 0.95 | 1.00 | 1.00 | 1.00 | 0.306 |

### Failed Criteria

Full completion is not claimed.

- The 8% improvement threshold is not satisfied across all scenarios.
  Low/medium demand and capacity_drop remain failures for the proposed
  controllers.
- Boundary non-degradation is not globally satisfied.
- P-FO, P-Stack, and P-Cent all still produce large low/medium demand
  regressions relative to no-control.
- Capacity_drop is still a severe over-control case: all active controllers are
  worse than no-control by total TTT.

### Diagnosis

- The default/no-control guard works for WU-CD-F in low/medium demand: WU-CD-F
  is effectively identical to no-control there. However, WU capacity_drop still
  worsens TTT by `4.052%` with green active `97%`, meaning the Wu urban green
  local objective can improve boundary/urban queues while worsening freeway
  coupling and total system TTT.
- P-FO and P-Stack still over-meter in low/medium demand despite guard
  candidates. In low demand, P-FO applies a mean metering ratio of `0.289` and
  P-Stack `0.258`; no-control total TTT is already near free-flow (`695.716`
  versus free-flow reference `690.720`). The local freeway objective is still
  undervaluing ramp/upstream urban queue and terminal throughput effects when
  there is no real freeway stress.
- In peak, oversaturated, and incident scenarios, metering is useful enough to
  clear the 8% threshold for P-FO, P-Stack, and P-Cent. This suggests the new
  candidate argmin structure is directionally useful under real congestion.
- Capacity_drop remains misaligned. P-FO improves freeway TTT slightly
  (`5734.487 -> 5499.762`) but worsens urban TTT (`26059.987 -> 28839.686`) and
  total TTT by `8.004%`. P-Stack is worse: mean metering ratio `0.306`, VSL
  active `95%`, throughput drops by `3655.9 veh/h`, and terminal vehicles rise
  by `7316.5`. The controller is transferring delay into urban/ramp/terminal
  queues instead of reducing total TTS.
- P-Cent has strong peak/incident TTT gains but still lacks a whole-action
  no-control/default guard; low/medium/capacity regressions show that the
  centralized search objective still needs stronger terminal queue and
  throughput protection.

### Proposed Next Modification

1. Add a controller-level no-control/default action guard for P-FO,
   P-Stack follower responses, and P-Cent, not only per-agent guard candidates.
   If the complete action worsens a one-step or short-horizon TTS-compatible
   system proxy versus no-control, choose the default action.
2. Strengthen freeway follower queue accounting in low-stress regimes:
   increase the terminal ramp/upstream urban queue horizon term or add a
   throughput-loss term so metering cannot dominate when density/off-ramp
   storage pressure is low.
3. Add activation gates for metering and VSL based on density ratio, off-ramp
   storage occupancy, and receiving-capacity stress. The current low/medium
   regressions show that local TTS argmin alone still activates metering too
   early.
4. For capacity_drop, revise VSL and metering coupling so freeway protection is
   accepted only when urban/ramp terminal queue growth is bounded. The current
   Stackelberg run protects parts of the freeway at the cost of much larger
   urban and terminal accumulation.
5. Extend WU urban green objective with freeway-coupling cost or a whole-action
   default guard, because capacity_drop WU worsens total TTT with green changes
   even though ramp/VSL/offset/allocation remain inactive.

## 2026-06-18: corrected metering no-control guard and upstream queue accounting

### What Was Implemented

- Removed `metering_error` from freeway final objective scoring. It remains only
  as diagnostic/infeasibility information.
- Changed distributed freeway upstream urban queue cost so it counts only
  candidate-created spillback beyond ramp reservoir capacity. Existing
  `urban_movement_queue` is no longer charged again by the freeway agent.
- Changed freeway follower lightweight prediction so on-ramp urban cost comes
  from ramp-space blocking (`onramp_urban_spillback_tts`) rather than the whole
  current on-ramp urban movement queue.
- Fixed no-metering guard candidates: metering ratio `1.0` now means physical
  ramp capacity, not `min(capacity, available, receiving)` upper.
- Added a receiving-overrequest penalty so physical no-metering candidates are
  evaluated but not selected when downstream receiving capacity is closed.
- Added tests for spillback-only upstream urban queue accounting and physical
  ratio-1 metering/VSL guard candidates.

### Files Changed

- `src/controllers/freeway_follower.py`
- `src/controllers/distributed_coordinator.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Baseline Run Command

The targeted low-demand run used the same paired driver; no-control was run
inside the same scenario/demand/horizon loop.

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario low_demand --T-total 7200 --controllers PROPOSED-FOLLOWERS-ONLY --output outputs\low_7200_pfo_physical_no_meter_guard_2026_06_18_v1 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

### Proposed-Controller Run Command

Same command as above, with `PROPOSED-FOLLOWERS-ONLY` as the controller under
test.

### Baseline Total TTT/TTS

| scenario | controller | total TTT | total delay |
|---|---|---:|---:|
| low_demand | NO-CONTROL | 695.716 | 4.995 |

### Proposed Total TTT/TTS

| scenario | controller | total TTT | total delay | improvement |
|---|---|---:|---:|---:|
| low_demand | PROPOSED-FOLLOWERS-ONLY | 998.817 | 308.096 | -43.567% |

This is still worse than no-control, but it is a large improvement over the
previous low-demand P-FO result from this branch (`3654.782`, `-425.327%`).

### Boundary Queue Balancing Result

| scenario | no-control B_sum | P-FO B_sum |
|---|---:|---:|
| low_demand | 0.150430 | 0.213254 |

Boundary balance is still degraded in this targeted low-demand P-FO run.

### Control Validation Summary

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\freeway_follower.py src\controllers\distributed_coordinator.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_freeway_ramp_candidates_include_default_and_previous_guard src.tests.test_constraints.ConstraintTests.test_distributed_freeway_agent_jointly_evaluates_metering_and_vsl_guards src.tests.test_constraints.ConstraintTests.test_distributed_freeway_urban_queue_term_counts_only_spillback src.tests.test_constraints.ConstraintTests.test_distributed_freeway_candidates_include_ratio_one_guards -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints -v
```

Results:

```text
py_compile: OK
targeted tests: 4 tests, OK
constraints suite: 56 tests, OK
targeted low-demand P-FO 7200 s run: completed
```

Ramp metering diagnostics for low-demand P-FO:

| run | mean metering ratio | mean metering flow | max ramp queue | final ramp queue | mean green shortfall |
|---|---:|---:|---:|---:|---:|
| before physical guard | 0.289 | 1707.8 | 720.0 | 720.0 | 186.1 |
| after physical guard | 1.000 | 2962.5 | 20.7 | 14.8 | 0.0 |

### Failed Criteria

Full completion is not claimed.

- Low-demand P-FO still fails the 8% improvement criterion.
- Boundary balance is still worse than no-control in this targeted run.
- Full all-scenario 4-controller validation has not been rerun after this
  correction.

### Diagnosis

- The earlier low-demand P-FO regression was substantially caused by the
  metering candidate set: the "no-control" guard had been clipped to
  availability/receiving upper bounds, so the physical metering ratio-1 action
  was missing. Restoring physical ramp-capacity candidates removed the ramp
  queue blow-up.
- Existing urban on-ramp movement queues were also being added to freeway local
  objective diagnostics. That was a system-level double count; the freeway
  agent now prices only additional upstream spillback caused by ramp reservoir
  overflow.
- Remaining low-demand P-FO loss is not from ramp metering: metering ratio is
  now `1.0`, ramp queues remain small, and green shortfall is zero. The residual
  TTT loss is urban-side (`urban_ttt 480.439 -> 788.623`) and points to
  green/offset stage-2 objective or boundary-balance pressure still changing
  signals when no-control is already near free-flow.

### Proposed Next Modification

Add the same whole-action/default guard concept to urban stage-2 green/offset:
fixed green and zero offset must remain in the candidate set and must be chosen
when the local urban TTS-compatible objective does not beat the neutral action.
Then rerun low/medium demand before repeating the full all-scenario comparison.

## 2026-06-18: diagnosed and corrected urban follower low-demand TTT misalignment

### What Was Implemented

- Diagnosed the remaining low-demand P-FO regression after ramp metering was
  fixed. The loss was urban-side, primarily green allocation.
- Removed metering tracking residual from urban freeway-pressure `total_pressure`.
  It remains reported as `metering_pressure`, but it no longer pushes urban
  off-ramp phases.
- Changed distributed freeway response aggregation for off-ramp predicted
  arrivals/flows from sum to max. The same link-level off-ramp forecast was
  being emitted by each segment agent and then counted multiple times.
- Changed urban-to-urban distributed coupling arrival forecasts to cap upstream
  release by currently available movement demand instead of treating green
  capacity as actual arrival.
- Added regression tests for all three failure modes.

### Files Changed

- `src/controllers/urban_follower.py`
- `src/controllers/distributed_coordinator.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Diagnostic Evidence

Before this correction, low-demand P-FO with physical no-metering guard still
had:

| metric | no-control | P-FO before urban fix |
|---|---:|---:|
| total TTT | 695.716 | 998.817 |
| urban TTT | 480.439 | 788.623 |
| freeway TTT | 215.277 | 210.193 |
| terminal urban vehicles | 222.3 | 442.6 |

Stage ablations showed the loss was mostly green allocation:

| variant | total TTT | urban TTT | freeway TTT |
|---|---:|---:|---:|
| P-FO all controls | 998.817 | 788.623 | 210.193 |
| fixed green only | 693.685 | 479.534 | 214.152 |
| fixed offset only | 957.246 | 745.312 | 211.935 |
| fixed green and offset | 695.716 | 480.439 | 215.277 |

Movement-level queue decomposition found the dominant losses in starved phases:

| phase | queue delta vs no-control |
|---|---:|
| F_p2 | +135.170 veh-h |
| D_p2 | +111.317 veh-h |
| B_p1 | +57.048 veh-h |

Root causes:

- `metering_tracking_residual` still entered urban pressure. With no-metering
  selected, this residual averaged `2346 veh/h` and created artificial off-ramp
  phase pressure.
- `offramp_predicted_arrival_*` was summed across 4 same-link segment agents.
  Example: `OR_D_E` first-step forecast was `32.958 veh` per segment agent and
  was passed to urban as `131.832 veh`.
- urban-to-urban coupling used upstream green capacity as arrival flow even
  when the upstream movement had no available queued vehicles.

### Baseline Run Command

The paired no-control baseline was run by the same comparison driver:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario low_demand --controllers PROPOSED-FOLLOWERS-ONLY --T-total 7200 --output outputs\low_7200_pfo_urban_coupling_objective_fix_2026_06_18_v1 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

### Proposed-Controller Run Command

Same command as above, with `PROPOSED-FOLLOWERS-ONLY` as the requested
controller.

### Baseline Total TTT/TTS

| scenario | controller | total TTT | total delay |
|---|---|---:|---:|
| low_demand | NO-CONTROL | 695.716 | 4.995 |

### Proposed Total TTT/TTS

| scenario | controller | total TTT | total delay | improvement |
|---|---|---:|---:|---:|
| low_demand | PROPOSED-FOLLOWERS-ONLY | 695.162 | 4.442 | +0.080% |

Subcomponent TTT:

| scenario | controller | urban TTT | freeway TTT |
|---|---|---:|---:|
| low_demand | NO-CONTROL | 480.439 | 215.277 |
| low_demand | PROPOSED-FOLLOWERS-ONLY | 481.448 | 213.715 |

### Boundary Queue Balancing Result

| scenario | no-control B_sum | P-FO B_sum | delta |
|---|---:|---:|---:|
| low_demand | 0.150430 | 0.151706 | +0.001276 |

Boundary balance is still very slightly degraded in this low-demand targeted
run. The run also has many degenerate boundary intervals, so this remains a
guardrail item rather than a completion pass.

### Control Validation Summary

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_urban_freeway_pressure_ignores_metering_tracking_residual src.tests.test_constraints.ConstraintTests.test_distributed_freeway_response_deduplicates_offramp_forecasts src.tests.test_constraints.ConstraintTests.test_distributed_urban_arrival_coupling_is_queue_limited -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\distributed_coordinator.py src\controllers\urban_follower.py src\controllers\freeway_follower.py src\tests\test_constraints.py
```

Results:

```text
targeted regression tests: 3 tests, OK
constraints suite: 59 tests, OK
py_compile: OK
targeted low-demand P-FO 7200 s paired run: completed
```

### Failed Criteria

Full completion is not claimed.

- Low-demand P-FO now beats no-control by only `0.080%`, below the default 8%
  improvement criterion.
- Boundary balance is still slightly degraded versus no-control.
- Full 7200 s all-scenario 4-controller validation has not been rerun after
  this correction.

### Proposed Next Modification

The major green misalignment is fixed for low demand: P-FO green stays at the
neutral 56/56 split and no longer over-protects D/F off-ramp phases or B_p2.
The remaining urban delta is small and appears offset-related (`offsets` still
move 6-12 sec under low free-flow). Next, make offset candidate evaluation use
the same local plant-compatible TTS proxy, or require a positive local TTS
margin before leaving the zero-offset guard in low-stress states. Then rerun
low/medium P-FO and the full all-scenario 4-controller comparison.

### Offset Ablation Follow-Up

Command:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B - <inline zero-offset ablation using outputs\low_7200_pfo_zero_offset_ablation_after_urban_fix_2026_06_18_v1>
```

Result:

| scenario | controller variant | total TTT | urban TTT | freeway TTT |
|---|---|---:|---:|---:|
| low_demand | NO-CONTROL | 695.716 | 480.439 | 215.277 |
| low_demand | P-FO after urban fix | 695.162 | 481.448 | 213.715 |
| low_demand | P-FO with offsets forced to 0 | 695.716 | 480.439 | 215.277 |

Interpretation:

- The small `+0.080%` total-TTT improvement in the latest low-demand P-FO run
  comes from nonzero offset timing interaction, not from green split changes.
- That offset timing worsens urban TTT by about `+1.009 veh*h` but improves
  freeway TTT by about `-1.562 veh*h`, producing a tiny net total improvement.
- With zero offsets, all green splits remain 56/56 and the run collapses back
  to the no-control trajectory. This confirms offset control is not yet a
  robust urban-TTT minimizer in low free-flow; it is a small cross-network timing
  perturbation.

## 2026-06-18: aligned WU-CD-F coupling forecast with proposed follower forecast

### What Was Implemented

- Kept WU-CD-F authority and iteration structure unchanged:
  green time + VSL only, no ramp metering, no offset, no allocation.
- Updated WU urban-to-urban coupling map so downstream phase arrivals are built
  from all movement origins in the phase, not only internal movements.
- Updated WU upstream leaving-rate coupling so green capacity is capped by
  currently available movement demand. Queue-free movements no longer create
  artificial downstream arrival pressure.
- Added on-ramp external demand to WU phase-arrival coupling so on-ramp approach
  arrivals are treated consistently with the proposed follower forecast.
- Added WU-specific regression tests for queue-limited arrival coupling and
  all-movement downstream phase mapping.

### Files Changed

- `src/controllers/wu_distributed.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Baseline Run Command

The no-control baseline was run inside the paired all-scenario driver.

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario all --controllers WU-CD-F --T-total 7200 --output outputs\all_scenarios_7200_wu_coupling_aligned_2026_06_18_v1 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

### Proposed-Controller Run Command

Same command as above, with `WU-CD-F` as the requested controller.

### Baseline and WU Total TTT/TTS

| scenario | no-control TTT | WU-CD-F TTT | improvement |
|---|---:|---:|---:|
| low_demand | 695.716 | 695.716 | 0.000% |
| medium_demand | 1943.962 | 1943.945 | +0.001% |
| peak_demand | 11659.562 | 11658.272 | +0.011% |
| oversaturated_demand | 19734.156 | 19738.250 | -0.021% |
| incident_or_capacity_drop | 10473.200 | 10473.318 | -0.001% |
| capacity_drop | 31794.474 | 32637.555 | -2.652% |

Compared with the earlier WU run before this correction, capacity_drop improved
from `-4.052%` to `-2.652%`, but WU-CD-F still does not meet the acceptance
threshold or produce meaningful scenario-wide gains.

### Boundary Queue Balancing Result

| scenario | no-control B_sum | WU-CD-F B_sum | delta |
|---|---:|---:|---:|
| low_demand | 0.150430 | 0.150430 | 0.000000 |
| medium_demand | 0.189289 | 0.189114 | -0.000175 |
| peak_demand | 0.082207 | 0.082231 | +0.000024 |
| oversaturated_demand | 0.041634 | 0.041575 | -0.000059 |
| incident_or_capacity_drop | 0.091609 | 0.091627 | +0.000018 |
| capacity_drop | 0.044671 | 0.019587 | -0.025084 |

Boundary balance is mostly neutral or better, but TTT performance remains weak.

### Control Validation Summary

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\wu_distributed.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_wu_urban_arrival_coupling_is_queue_limited src.tests.test_constraints.ConstraintTests.test_wu_upstream_map_uses_all_downstream_phase_movements -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints -v
```

Results:

```text
py_compile: OK
targeted WU coupling tests: 2 tests, OK
constraints suite: 61 tests, OK
7200 s all-scenario WU-CD-F run: completed
```

Activation diagnostics:

| scenario | green active | VSL active | ramp metering ratio | mean iterations |
|---|---:|---:|---:|---:|
| low_demand | 0.000 | 0.000 | 1.000 | 3.000 |
| medium_demand | 0.075 | 0.000 | 1.000 | 2.700 |
| peak_demand | 0.625 | 0.000 | 1.000 | 2.125 |
| oversaturated_demand | 0.775 | 0.000 | 1.000 | 1.600 |
| incident_or_capacity_drop | 0.550 | 0.000 | 1.000 | 2.000 |
| capacity_drop | 0.975 | 0.000 | 1.000 | 2.550 |

### Failed Criteria

Full completion is not claimed.

- WU-CD-F still does not reach the 8% improvement threshold in any scenario.
- VSL remains inactive in all scenarios, so WU-CD-F is effectively a green-only
  controller in these runs.
- In capacity_drop, WU-CD-F improves freeway TTT versus no-control
  (`6250.641` vs `6766.795` implied by delta), but worsens urban TTT enough
  that total TTT remains worse by `843.081 veh*h`.

### Diagnosis

- The user's hypothesis was directionally right for controller authority:
  P-FO without ramp metering and offset has the same high-level control knobs as
  WU-CD-F. However, simply aligning WU coupling forecast is not enough because
  WU's local VSL objective still selects no VSL change in every scenario.
- The corrected WU coupling removes artificial arrival pressure, so low-demand
  behavior safely collapses to no-control. That is good for guard behavior but
  also shows WU has little useful actuation under low/medium demand.
- In congested/capacity-drop regimes, WU can move green timings, but without
  ramp metering or a system-level default guard its green changes mostly
  redistribute queues. Capacity-drop boundary balance improves, but total TTT
  worsens because urban TTT grows more than freeway TTT falls.
- The next WU-specific issue is not the coupling forecast anymore; it is VSL
  activation/objective alignment. WU's VSL local objective is too conservative
  under these scenarios or does not price downstream/capacity-drop benefits
  strongly enough to choose a non-default VSL.

### Proposed Next Modification

Keep WU authority fixed, but revise the WU VSL local objective/candidates so
VSL can activate only when a plant-compatible short-horizon TTS proxy beats the
default VSL guard. Then rerun WU-CD-F against the same all-scenario comparison.
If VSL still remains inactive, WU-CD-F's limited authority means it should be
reported as a weak baseline rather than expected to approach PFO/Stackelberg
performance.

## 2026-06-18 - WU-CD-F routed to PFO-style TTT argmin with green/VSL-only authority

### What Was Implemented

- Added `WU_GREEN_VSL_ONLY_TTT` mode to `DistributedCoordinator`.
- Routed `WU-CD-F` through `DistributedCoordinator(..., ablation="WU_GREEN_VSL_ONLY_TTT")`
  instead of the old WU surrogate/Jacobi controller.
- In that mode, the follower uses the same TTT-compatible distributed response
  objective machinery as PFO, but clamps authority to WU variables only:
  `green_times` and `vsl` may vary, while ramp metering is fixed at physical
  capacity, offsets are fixed at 0, allocation is empty, and leader targets are 0.
- Freeway agents in this mode evaluate VSL candidates against a no-metering
  ramp candidate only.
- Urban agents in this mode keep green-time candidate search but return zero
  offsets and no allocation.
- Added a coordinator-level previous/no-control guard for this WU-only mode so
  WU-CD-F cannot accept a green/VSL candidate unless the local
  TTT-compatible response objective beats the guard.
- Added diagnostics copied into decision rows:
  `wu_green_vsl_only_ttt_authority`, guard evaluated/selected flags.

### Files Changed

- `src/controllers/distributed_coordinator.py`
- `src/experiments/six_controller_comparison.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Baseline Run Command

No-control baselines were run inside the scenario drivers below. The final WU
baseline/comparison run was:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario all --controllers WU-CD-F --T-total 7200 --output outputs\all_scenarios_7200_wu_green_vsl_ttt_2026_06_18_v2 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

### Proposed-Controller Run Commands

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario all --controllers WU-CD-F --T-total 7200 --output outputs\all_scenarios_7200_wu_green_vsl_ttt_2026_06_18_v2 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario all --controllers PROPOSED-FOLLOWERS-ONLY --T-total 7200 --output outputs\all_scenarios_7200_pfo_ttt_guard_scoped_2026_06_18_v1 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario all --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --T-total 7200 --output outputs\all_scenarios_7200_four_controllers_ttt_guard_2026_06_18_v1 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

The full four-controller command timed out at 600 s after completing low,
medium, peak, oversaturated, and incident WU/PFO/Stackelberg runs. Missing
pieces were completed with:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario incident_or_capacity_drop --controllers PROPOSED-CENTRALIZED --T-total 7200 --output outputs\incident_7200_proposed_centralized_ttt_guard_2026_06_18_v1 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario capacity_drop --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --T-total 7200 --output outputs\capacity_drop_7200_four_controllers_ttt_guard_2026_06_18_v1 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

### Final 7200 s TTT, Delay, And Computation Cost

This table combines valid current-code outputs: WU from
`all_scenarios_7200_wu_green_vsl_ttt_2026_06_18_v2`, PFO from
`all_scenarios_7200_pfo_ttt_guard_scoped_2026_06_18_v1`, Stackelberg from the
partial four-controller run plus capacity-drop fragment, and centralized from
the partial run plus incident/capacity fragments.

| scenario | controller | total TTT | delay | computation sec | improvement vs no-control |
|---|---|---:|---:|---:|---:|
| low_demand | WU-CD-F | 695.716 | 4.995 | 0.85 | 0.000% |
| low_demand | PROPOSED-FOLLOWERS-ONLY | 695.162 | 4.441 | 0.98 | +0.080% |
| low_demand | PROPOSED-STACKELBERG | 1170.255 | 479.534 | 20.50 | -68.209% |
| low_demand | PROPOSED-CENTRALIZED | 871.492 | 180.771 | 104.54 | -25.266% |
| medium_demand | WU-CD-F | 1943.962 | 1019.342 | 0.96 | 0.000% |
| medium_demand | PROPOSED-FOLLOWERS-ONLY | 1940.978 | 1016.358 | 1.09 | +0.153% |
| medium_demand | PROPOSED-STACKELBERG | 3523.838 | 2599.218 | 19.82 | -81.271% |
| medium_demand | PROPOSED-CENTRALIZED | 3633.187 | 2708.567 | 102.72 | -86.896% |
| peak_demand | WU-CD-F | 11659.562 | 10515.542 | 1.26 | 0.000% |
| peak_demand | PROPOSED-FOLLOWERS-ONLY | 11737.078 | 10593.058 | 1.27 | -0.665% |
| peak_demand | PROPOSED-STACKELBERG | 7299.135 | 6155.115 | 19.75 | +37.398% |
| peak_demand | PROPOSED-CENTRALIZED | 6369.101 | 5225.081 | 102.85 | +45.374% |
| oversaturated_demand | WU-CD-F | 19734.156 | 18321.761 | 1.19 | 0.000% |
| oversaturated_demand | PROPOSED-FOLLOWERS-ONLY | 19835.189 | 18422.794 | 1.26 | -0.512% |
| oversaturated_demand | PROPOSED-STACKELBERG | 16743.906 | 15331.511 | 20.79 | +15.153% |
| oversaturated_demand | PROPOSED-CENTRALIZED | 15863.496 | 14451.101 | 110.38 | +19.614% |
| incident_or_capacity_drop | WU-CD-F | 10473.200 | 9372.666 | 1.12 | 0.000% |
| incident_or_capacity_drop | PROPOSED-FOLLOWERS-ONLY | 10488.095 | 9387.561 | 1.22 | -0.142% |
| incident_or_capacity_drop | PROPOSED-STACKELBERG | 7331.833 | 6231.299 | 22.11 | +29.994% |
| incident_or_capacity_drop | PROPOSED-CENTRALIZED | 5826.187 | 4725.653 | 107.62 | +44.371% |
| capacity_drop | WU-CD-F | 31794.474 | 28171.317 | 1.30 | 0.000% |
| capacity_drop | PROPOSED-FOLLOWERS-ONLY | 32996.036 | 29372.879 | 1.69 | -3.779% |
| capacity_drop | PROPOSED-STACKELBERG | 39877.916 | 36254.759 | 14.47 | -25.424% |
| capacity_drop | PROPOSED-CENTRALIZED | 35096.930 | 31473.773 | 105.87 | -10.387% |

### Boundary Queue Balancing Result

WU-CD-F exactly matches no-control after the WU-only objective guard:

| scenario | no-control B_sum | WU-CD-F B_sum | delta |
|---|---:|---:|---:|
| low_demand | 0.150430 | 0.150430 | 0.000000 |
| medium_demand | 0.189289 | 0.189289 | 0.000000 |
| peak_demand | 0.082207 | 0.082207 | 0.000000 |
| oversaturated_demand | 0.041634 | 0.041634 | 0.000000 |
| incident_or_capacity_drop | 0.091609 | 0.091609 | 0.000000 |
| capacity_drop | 0.044671 | 0.044671 | 0.000000 |

### Control Validation Summary

Validation commands:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\distributed_coordinator.py src\experiments\six_controller_comparison.py src\tests\test_constraints.py
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_green_vsl_only_ttt_mode_preserves_wu_authority src.tests.test_constraints.ConstraintTests.test_wu_cd_f_adapter_uses_green_vsl_only_ttt_coordinator src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics src.tests.test_constraints.ConstraintTests.test_distributed_freeway_agent_jointly_evaluates_metering_and_vsl_guards -v
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints -v
```

Results:

```text
py_compile: OK
targeted tests: 4 tests, OK
constraints suite: 63 tests, OK
WU-CD-F 7200 s all-scenario run: completed
PFO 7200 s all-scenario run: completed
four-controller run: partial due 600 s timeout, completed by scenario fragments
```

WU-CD-F authority/activation diagnostics after the guard:

| scenario | guard selected avg | authority avg | green active steps | VSL active steps | ramp active steps | offset active steps |
|---|---:|---:|---:|---:|---:|---:|
| low_demand | 1.000 | 1.000 | 0/40 | 0/40 | 0/40 | 0/40 |
| medium_demand | 1.000 | 1.000 | 0/40 | 0/40 | 0/40 | 0/40 |
| peak_demand | 1.000 | 1.000 | 0/40 | 0/40 | 0/40 | 0/40 |
| oversaturated_demand | 1.000 | 1.000 | 0/40 | 0/40 | 0/40 | 0/40 |
| incident_or_capacity_drop | 1.000 | 1.000 | 0/40 | 0/40 | 0/40 | 0/40 |
| capacity_drop | 1.000 | 1.000 | 0/40 | 0/40 | 0/40 | 0/40 |

### Failed Criteria

Full completion is not claimed.

- The 8% improvement threshold is not met by WU-CD-F or PFO.
- WU-CD-F now obeys WU authority exactly, but all candidate green/VSL actions
  lose against the previous/no-control guard under the TTT-compatible response
  objective, so WU-CD-F collapses to no-control in every scenario.
- PFO remains slightly helpful only in low and medium demand, then worsens in
  peak, oversaturated, incident, and capacity-drop cases.
- Proposed Stackelberg and centralized improve peak/oversaturated/incident but
  fail badly in capacity_drop. Low/medium Stackelberg and centralized are also
  worse than no-control, indicating leader/global-objective activation still
  needs demand-regime guards.

### Diagnosis

- The user's proposed equivalence is now implemented literally: WU-CD-F uses
  the PFO-style distributed TTT-compatible argmin, but with only WU control
  variables (`green`, `VSL`) left enabled.
- Before the coordinator guard, the same green/VSL-only candidates worsened
  peak/oversat/incident/capacity-drop because local green/VSL changes were
  accepted even when the merged response objective had no proven advantage over
  the previous/default control. With the guard, those actions are rejected.
- This means the remaining WU limitation is not just a coding/Jacobian issue:
  under the current plant-compatible response proxy, green/VSL-only authority
  does not find a positive-TTT action. WU cannot reproduce PFO's low/medium
  tiny gains because PFO's gains come from the broader follower package,
  especially ramp/offset interactions, not from green/VSL alone.
- Capacity-drop remains the clearest objective-alignment failure for proposed
  leader/centralized modes. The high-authority controllers activate controls,
  but the current prediction/objective still overvalues actions that later
  increase total TTT.

### Proposed Next Modification

Keep the WU-CD-F constrained PFO-style implementation as the fair WU baseline:
it is now safe and authority-correct. Next work should focus on the proposed
leader/centralized objective and capacity-drop guard, plus a PFO guard/diagnostic
that can reject green/offset/metering combinations when the actual plant rollout
would worsen TTT despite a favorable local proxy.

## 2026-06-18 - Current 4-controller rerun on 5 non-low scenarios

### What Was Run

Per user request, reran the four primary controllers on all scenarios except
`low_demand` using the current code:

- `WU-CD-F`
- `PROPOSED-FOLLOWERS-ONLY`
- `PROPOSED-STACKELBERG`
- `PROPOSED-CENTRALIZED`

Each scenario run includes its own no-control baseline using the same demand,
seed, and 7200 s horizon.

### Files Changed

- `reports/codex_run_report.md`

### Baseline And Controller Run Commands

The same command template was used for each of:
`medium_demand`, `peak_demand`, `oversaturated_demand`,
`incident_or_capacity_drop`, and `capacity_drop`.

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario <scenario> --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --T-total 7200 --output outputs\five_scenarios_7200_four_controllers_current_2026_06_18\<scenario> --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

### Total TTT, Delay, And Computation Cost

| scenario | controller | total TTT | delay | computation sec | improvement vs no-control |
|---|---|---:|---:|---:|---:|
| medium_demand | WU-CD-F | 1943.962 | 1019.342 | 1.14 | 0.000% |
| medium_demand | PROPOSED-FOLLOWERS-ONLY | 1940.978 | 1016.357 | 1.44 | +0.154% |
| medium_demand | PROPOSED-STACKELBERG | 3523.838 | 2599.218 | 25.62 | -81.271% |
| medium_demand | PROPOSED-CENTRALIZED | 3633.187 | 2708.566 | 144.18 | -86.896% |
| peak_demand | WU-CD-F | 11659.562 | 10515.542 | 1.57 | 0.000% |
| peak_demand | PROPOSED-FOLLOWERS-ONLY | 11737.078 | 10593.059 | 1.45 | -0.665% |
| peak_demand | PROPOSED-STACKELBERG | 7299.135 | 6155.116 | 28.23 | +37.398% |
| peak_demand | PROPOSED-CENTRALIZED | 6369.101 | 5225.081 | 149.51 | +45.374% |
| oversaturated_demand | WU-CD-F | 19734.156 | 18321.761 | 1.44 | 0.000% |
| oversaturated_demand | PROPOSED-FOLLOWERS-ONLY | 19835.189 | 18422.794 | 1.52 | -0.512% |
| oversaturated_demand | PROPOSED-STACKELBERG | 16743.906 | 15331.511 | 24.62 | +15.153% |
| oversaturated_demand | PROPOSED-CENTRALIZED | 15863.496 | 14451.101 | 115.96 | +19.614% |
| incident_or_capacity_drop | WU-CD-F | 10473.200 | 9372.666 | 1.16 | 0.000% |
| incident_or_capacity_drop | PROPOSED-FOLLOWERS-ONLY | 10488.095 | 9387.561 | 1.05 | -0.142% |
| incident_or_capacity_drop | PROPOSED-STACKELBERG | 7331.833 | 6231.299 | 19.84 | +29.994% |
| incident_or_capacity_drop | PROPOSED-CENTRALIZED | 5826.187 | 4725.653 | 105.57 | +44.371% |
| capacity_drop | WU-CD-F | 31794.474 | 28171.317 | 1.40 | 0.000% |
| capacity_drop | PROPOSED-FOLLOWERS-ONLY | 32996.036 | 29372.879 | 1.53 | -3.779% |
| capacity_drop | PROPOSED-STACKELBERG | 39877.916 | 36254.759 | 14.82 | -25.424% |
| capacity_drop | PROPOSED-CENTRALIZED | 35096.930 | 31473.773 | 108.61 | -10.387% |

### Boundary Queue Balancing Result

| scenario | no-control B_sum | WU-CD-F | PFO | Stackelberg | Centralized |
|---|---:|---:|---:|---:|---:|
| medium_demand | 0.189289 | 0.189289 | 0.200358 | 0.046515 | 0.144306 |
| peak_demand | 0.082207 | 0.082207 | 0.086660 | 0.022185 | 0.127246 |
| oversaturated_demand | 0.041634 | 0.041634 | 0.043370 | 0.013207 | 0.069875 |
| incident_or_capacity_drop | 0.091609 | 0.091609 | 0.099825 | 0.027256 | 0.138681 |
| capacity_drop | 0.044671 | 0.044671 | 0.017925 | 0.007496 | 0.014206 |

### Control Validation Summary

- All five scenario runs completed successfully.
- `authority_ok=True` for all controller/scenario rows.
- No compile/tests were rerun for this simulation-only request; the immediately
  preceding validation on this code state was:
  `py_compile: OK`, targeted tests `4 OK`, full constraints suite `63 OK`.

### Failed Criteria

Full completion is not claimed.

- WU-CD-F remains exactly no-control in all five scenarios because its
  green/VSL-only TTT guard rejects all active candidates.
- PFO only improves `medium_demand` by `+0.154%` and worsens the other four
  non-low scenarios.
- Stackelberg and centralized are strong in `peak`, `oversaturated`, and
  `incident_or_capacity_drop`, but both fail `capacity_drop`; they also fail
  `medium_demand`.
- The 8% improvement acceptance threshold is not consistently satisfied across
  scenarios/controllers.

### Proposed Next Modification

Capacity-drop and medium-demand guards should be added to the high-authority
controllers. The next useful diagnostic is to compare the accepted
leader/centralized candidate response objective against a one-step plant rollout
proxy, because the current optimizer is still accepting controls that look good
locally but increase realized total TTT in `medium_demand` and `capacity_drop`.

## 2026-06-18 - Distributed Response Horizon Rollout TTT Objective

### What Was Implemented

Per user request, replaced the PFO/WU distributed final response selector's
lightweight conservation/terminal objective with a coupled MPC horizon rollout
TTT objective.

- `DistributedCoordinator._response_tts_objective(...)` now copies the current
  traffic state, applies the candidate `ControlAction` over each forecast step,
  calls `run_coupled_interval(...)`, advances rollout time, and minimizes the
  accumulated `freeway_ttt + urban_ttt`.
- The objective no longer adds the old terminal trapezoid approximation,
  density penalty, or residual penalty. Density/residual values remain
  diagnostics only.
- Added rollout diagnostics:
  `distributed_response_rollout_active`,
  `distributed_response_rollout_ttt`,
  `distributed_response_rollout_freeway_ttt`,
  `distributed_response_rollout_urban_ttt`, and terminal rollout vehicle
  diagnostics.
- Preserved existing response diagnostics keys where possible so downstream
  summaries keep working.
- Added a unit test that patches `src.simulation.coupling.run_coupled_interval`
  and verifies the distributed response objective calls the coupled plant once
  per horizon step and returns the accumulated rollout TTT.

### Files Changed

- `src/controllers/distributed_coordinator.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Baseline And Proposed Run Commands

Compile:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python.exe -B -m py_compile src\controllers\distributed_coordinator.py src\tests\test_constraints.py src\experiments\six_controller_comparison.py
```

Targeted tests:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_distributed_response_objective_uses_coupled_horizon_rollout src.tests.test_constraints.ConstraintTests.test_distributed_response_objective_rewards_ramp_service src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics -v
```

Full constraints:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python.exe -B -m unittest src.tests.test_constraints -v
```

Closed-loop smoke:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY --T-total 360 --output outputs\smoke_distributed_rollout_ttt_with_baseline_2026_06_18
```

Additional non-baseline runner smoke:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python.exe -B -m src.experiments.six_controller_comparison --config src\config\default.yaml --scenario medium_demand --T-total 360 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY --output outputs\smoke_distributed_rollout_ttt_2026_06_18
```

### Baseline And Proposed TTT/TTS

360 s `medium_demand` smoke with the same demand/seed:

| controller | total TTT | delay | computation sec | improvement vs no-control |
|---|---:|---:|---:|---:|
| NO-CONTROL | 41.011 | 0.610 | 0.00 | baseline |
| WU-CD-F | 41.036 | 0.635 | 1.06 | -0.061% |
| PROPOSED-FOLLOWERS-ONLY | 40.834 | 0.434 | 0.37 | +0.432% |

### Boundary Queue Balancing Result

| controller | mean B_sum | delta vs no-control | non-degraded |
|---|---:|---:|---:|
| NO-CONTROL | 0.146213 | 0.000000 | baseline |
| WU-CD-F | 0.138999 | -0.007214 | true |
| PROPOSED-FOLLOWERS-ONLY | 0.153990 | +0.007777 | false |

### Control Validation Summary

- `py_compile`: passed.
- Targeted rollout/objective tests: 3 passed.
- Full `src.tests.test_constraints`: 64 passed.
- Closed-loop smoke completed.
- `authority_ok=True` for WU-CD-F and PFO in the smoke.

### Failed Criteria

Full completion is not claimed.

- This was a 360 s implementation smoke, not the required 7200 s all-scenario
  acceptance run.
- PFO improvement in the smoke is only `+0.432%`, below the 8% threshold.
- PFO boundary balance degraded in this short smoke
  (`mean_B_sum +0.007777` vs no-control).

### Proposed Next Modification

Run the 7200 s scenario set again with the rollout objective. If PFO still
stores vehicles upstream while improving the short-horizon rollout score, add a
throughput-shortfall guard against the default/no-control candidate rather than
introducing another arbitrary queue-weight term.

## 2026-06-18 - 7200 s All-Scenario Rollout-TTT Rerun

### What Was Implemented

No additional implementation change in this section. This was the requested
7200 s rerun after changing the distributed final response objective to coupled
horizon rollout TTT.

### Files Changed

- `reports/codex_run_report.md`

### Baseline And Controller Run Command

The run includes the no-control baseline and all six configured scenarios:
`low_demand`, `medium_demand`, `peak_demand`, `oversaturated_demand`,
`incident_or_capacity_drop`, and `capacity_drop`.

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario all --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --T-total 7200 --output outputs\all_scenarios_7200_four_controllers_rollout_ttt_2026_06_18 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

### Total TTT, Delay, And Computation Cost

Output root:
`outputs\all_scenarios_7200_four_controllers_rollout_ttt_2026_06_18`

Positive improvement means lower TTT than no-control.

| scenario | controller | total TTT | delay | comp sec | improvement | throughput delta veh/h | terminal delta veh |
|---|---|---:|---:|---:|---:|---:|---:|
| low_demand | WU-CD-F | 695.716 | 4.995 | 21.97 | +0.000% | +0.0 | +0.0 |
| low_demand | PROPOSED-FOLLOWERS-ONLY | 695.162 | 4.442 | 7.74 | +0.080% | +2.4 | -3.8 |
| low_demand | PROPOSED-STACKELBERG | 858.833 | 168.113 | 155.25 | -23.446% | -93.3 | +187.3 |
| low_demand | PROPOSED-CENTRALIZED | 871.492 | 180.772 | 123.97 | -25.265% | -84.0 | +167.6 |
| medium_demand | WU-CD-F | 1937.743 | 1013.122 | 23.22 | +0.320% | +1.3 | -2.4 |
| medium_demand | PROPOSED-FOLLOWERS-ONLY | 1940.978 | 1016.357 | 9.34 | +0.154% | -0.6 | +4.2 |
| medium_demand | PROPOSED-STACKELBERG | 3292.374 | 2367.753 | 142.81 | -69.364% | -143.5 | +286.3 |
| medium_demand | PROPOSED-CENTRALIZED | 3633.187 | 2708.566 | 110.53 | -86.896% | -621.1 | +1247.4 |
| peak_demand | WU-CD-F | 11664.060 | 10520.041 | 25.21 | -0.039% | -2.6 | +6.0 |
| peak_demand | PROPOSED-FOLLOWERS-ONLY | 11738.835 | 10594.815 | 11.45 | -0.680% | -30.9 | +63.3 |
| peak_demand | PROPOSED-STACKELBERG | 6618.652 | 5474.632 | 140.66 | +43.234% | +3249.4 | -6506.6 |
| peak_demand | PROPOSED-CENTRALIZED | 6369.101 | 5225.081 | 112.70 | +45.374% | +3368.2 | -6733.8 |
| oversaturated_demand | WU-CD-F | 19736.236 | 18323.841 | 25.35 | -0.011% | -1.0 | +2.2 |
| oversaturated_demand | PROPOSED-FOLLOWERS-ONLY | 19791.395 | 18379.000 | 9.07 | -0.290% | -5.1 | +11.4 |
| oversaturated_demand | PROPOSED-STACKELBERG | 17211.397 | 15799.002 | 139.72 | +12.784% | +1164.3 | -2328.8 |
| oversaturated_demand | PROPOSED-CENTRALIZED | 15863.496 | 14451.101 | 108.26 | +19.614% | +1122.1 | -2238.0 |
| incident_or_capacity_drop | WU-CD-F | 10475.976 | 9375.442 | 24.14 | -0.027% | -1.5 | +3.9 |
| incident_or_capacity_drop | PROPOSED-FOLLOWERS-ONLY | 10488.088 | 9387.554 | 10.22 | -0.142% | -8.7 | +18.9 |
| incident_or_capacity_drop | PROPOSED-STACKELBERG | 6185.536 | 5085.003 | 142.77 | +40.939% | +2956.9 | -5918.7 |
| incident_or_capacity_drop | PROPOSED-CENTRALIZED | 5826.187 | 4725.653 | 109.01 | +44.371% | +3139.2 | -6280.7 |
| capacity_drop | WU-CD-F | 31949.707 | 28326.550 | 27.47 | -0.488% | +30.5 | -60.9 |
| capacity_drop | PROPOSED-FOLLOWERS-ONLY | 33008.400 | 29385.243 | 14.99 | -3.818% | -840.1 | +1680.4 |
| capacity_drop | PROPOSED-STACKELBERG | 39086.833 | 35463.676 | 108.56 | -22.936% | -3668.3 | +7336.7 |
| capacity_drop | PROPOSED-CENTRALIZED | 35096.930 | 31473.773 | 109.43 | -10.387% | -851.9 | +1703.9 |

### Boundary Queue Balancing Result

| scenario | WU-CD-F B delta | PFO B delta | Stackelberg B delta | Centralized B delta |
|---|---:|---:|---:|---:|
| low_demand | +0.000000 | +0.001276 | +0.006124 | +0.185633 |
| medium_demand | -0.008812 | +0.011069 | -0.150433 | -0.044983 |
| peak_demand | -0.002454 | +0.003843 | -0.047948 | +0.045039 |
| oversaturated_demand | -0.000515 | +0.000752 | -0.028006 | +0.028241 |
| incident_or_capacity_drop | -0.003414 | +0.008304 | -0.049092 | +0.047072 |
| capacity_drop | +0.012320 | -0.024316 | -0.040189 | -0.030465 |

### Control Validation Summary

- All six 7200 s scenario runs completed.
- `authority_ok=True` for all reported controller rows.
- Previous validation on the same implementation state:
  `py_compile` passed, targeted rollout/objective tests passed, and full
  `src.tests.test_constraints` passed with 64 tests.
- WU-CD-F now has nonzero green/VSL action in some scenarios because the
  rollout objective can accept green/VSL-only candidates, but ramp metering and
  offsets remain disabled by WU authority.

### PFO Ramp/Throughput Diagnostic

Signs: positive urban/freeway delta means TTT reduction vs no-control; negative
means that component got worse.

| scenario | TTT improvement | urban TTT delta | freeway TTT delta | throughput delta veh/h | terminal on-ramp delta | terminal total delta | ramp active | avg ramp ratio | VSL active |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| low_demand | +0.080% | -1.0 | +1.6 | +2.4 | -2.4 | -3.8 | 0/40 | 1.000 | 0/40 |
| medium_demand | +0.154% | -8.7 | +11.7 | -0.6 | +10.6 | +4.2 | 15/40 | 0.838 | 0/40 |
| peak_demand | -0.680% | -295.3 | +216.1 | -30.9 | +200.7 | +63.3 | 32/40 | 0.285 | 0/40 |
| oversaturated_demand | -0.290% | -268.2 | +211.0 | -5.1 | +162.8 | +11.4 | 36/40 | 0.180 | 0/40 |
| incident_or_capacity_drop | -0.142% | -40.5 | +25.6 | -8.7 | -16.7 | +18.9 | 31/40 | 0.333 | 0/40 |
| capacity_drop | -3.818% | -1775.1 | +561.2 | -840.1 | +1626.4 | +1680.4 | 34/40 | 0.444 | 38/40 |

### Comparison To Previous PFO Run

| scenario | previous PFO improvement | rollout PFO improvement | previous TTT | rollout TTT | previous throughput delta | rollout throughput delta |
|---|---:|---:|---:|---:|---:|---:|
| medium_demand | +0.154% | +0.154% | 1940.978 | 1940.978 | -0.6 | -0.6 |
| peak_demand | -0.665% | -0.680% | 11737.078 | 11738.835 | -30.7 | -30.9 |
| oversaturated_demand | -0.512% | -0.290% | 19835.189 | 19791.395 | -11.5 | -5.1 |
| incident_or_capacity_drop | -0.142% | -0.142% | 10488.095 | 10488.088 | -8.7 | -8.7 |
| capacity_drop | -3.779% | -3.818% | 32996.036 | 33008.400 | -816.1 | -840.1 |

### Failed Criteria

Full completion is not claimed.

- PFO does not meet the 8% improvement threshold in any scenario.
- PFO still worsens peak, oversaturated, incident, and capacity-drop scenarios.
- PFO still trades freeway TTT reduction for larger urban/on-ramp accumulation,
  especially in peak/oversaturated/capacity-drop.
- Stackelberg/centralized remain strong in peak and incident, but still fail
  low/medium/capacity-drop.
- Boundary queue balancing is not consistently non-degraded.

### Diagnosis And Proposed Next Modification

The rollout objective is active, but it only ranks the distributed response
candidates produced by the follower iteration. PFO can still fail when the
candidate set arriving at the final selector is already biased toward active
green/offset and restrictive ramp metering. In particular:

- PFO still meters ramps in 32/40 peak steps and 36/40 oversaturated steps.
- Average PFO ramp ratio remains very low in congested scenarios:
  `0.285` peak and `0.180` oversaturated.
- The no-metering ratio-1 candidate exists at the freeway-agent level, but PFO
  lacks a full-controller default/no-control guard evaluated by the new coupled
  rollout objective.

Next implementation should add a PFO-level default/previous/no-control guard
candidate to the final distributed selector, evaluated by the same coupled
horizon rollout TTT objective, and then add a throughput-shortfall guard if the
full default guard is still insufficient.

## 2026-06-18 - PFO/WU Full-Controller Guard Candidates

### What Was Implemented

Added leaderless distributed full-controller guard candidates to the final
rollout-TTT selector.

- PFO and WU-CD-F now evaluate `previous`, `no_control`, and `default`
  full-controller guard candidates before follower-iteration candidates.
- Each guard is evaluated by the same coupled horizon rollout TTT objective used
  by normal distributed response candidates.
- The PFO `default` guard uses equal green, no metering, no VSL, zero offset,
  and empty allocation, so it does not smuggle allocation authority into
  followers-only mode.
- WU guards are passed through the WU green/VSL-only authority clamp, preserving
  no ramp metering, zero offset, and empty allocation.
- Added diagnostics:
  `distributed_full_controller_guard_active`,
  `distributed_guard_candidate_count`,
  `distributed_previous_guard_objective_tts`,
  `distributed_no_control_guard_objective_tts`,
  `distributed_default_guard_objective_tts`, and per-guard selected flags.
- Added a unit test that verifies all three guard candidates are evaluated and
  that the default guard has empty allocation.

### Files Changed

- `src/controllers/distributed_coordinator.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Validation Commands

Compile:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\distributed_coordinator.py src\tests\test_constraints.py
```

Targeted tests:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_leaderless_distributed_evaluates_full_controller_guards src.tests.test_constraints.ConstraintTests.test_distributed_response_objective_uses_coupled_horizon_rollout src.tests.test_constraints.ConstraintTests.test_green_vsl_only_ttt_mode_preserves_wu_authority src.tests.test_constraints.ConstraintTests.test_wu_cd_f_adapter_uses_green_vsl_only_ttt_coordinator -v
```

Full constraints:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints -v
```

### 7200 s WU/PFO Rerun Command

Only WU-CD-F and PFO were rerun because this patch affects the leaderless
distributed selector. No-control baselines were regenerated for each scenario
using the same demand/seed/horizon.

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario all --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY --T-total 7200 --output outputs\all_scenarios_7200_wu_pfo_full_guard_2026_06_18 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

### Baseline And Proposed TTT/TTS

Output root:
`outputs\all_scenarios_7200_wu_pfo_full_guard_2026_06_18`

Positive improvement means lower TTT than no-control.

| scenario | controller | total TTT | delay | comp sec | improvement | throughput delta veh/h | terminal delta veh |
|---|---|---:|---:|---:|---:|---:|---:|
| low_demand | WU-CD-F | 695.716 | 4.995 | 28.55 | +0.000% | +0.0 | +0.0 |
| low_demand | PROPOSED-FOLLOWERS-ONLY | 691.383 | 0.663 | 28.44 | +0.623% | +3.3 | -6.0 |
| medium_demand | WU-CD-F | 1937.743 | 1013.122 | 29.85 | +0.320% | +1.3 | -2.4 |
| medium_demand | PROPOSED-FOLLOWERS-ONLY | 1916.244 | 991.624 | 28.84 | +1.426% | +14.2 | -28.2 |
| peak_demand | WU-CD-F | 11664.060 | 10520.041 | 31.61 | -0.039% | -2.6 | +6.0 |
| peak_demand | PROPOSED-FOLLOWERS-ONLY | 11637.655 | 10493.635 | 31.26 | +0.188% | +6.6 | -13.2 |
| oversaturated_demand | WU-CD-F | 19736.236 | 18323.841 | 30.30 | -0.011% | -1.0 | +2.2 |
| oversaturated_demand | PROPOSED-FOLLOWERS-ONLY | 19678.640 | 18266.245 | 30.09 | +0.281% | +15.9 | -31.6 |
| incident_or_capacity_drop | WU-CD-F | 10475.976 | 9375.442 | 29.87 | -0.027% | -1.5 | +3.9 |
| incident_or_capacity_drop | PROPOSED-FOLLOWERS-ONLY | 10452.109 | 9351.575 | 29.05 | +0.201% | +6.3 | -12.7 |
| capacity_drop | WU-CD-F | 31949.707 | 28326.550 | 33.14 | -0.488% | +30.5 | -60.9 |
| capacity_drop | PROPOSED-FOLLOWERS-ONLY | 31732.015 | 28108.858 | 31.86 | +0.196% | +44.7 | -89.2 |

### Boundary Queue Balancing Result

| scenario | WU-CD-F B delta | PFO B delta |
|---|---:|---:|
| low_demand | +0.000000 | -0.000395 |
| medium_demand | -0.008812 | +0.001948 |
| peak_demand | -0.002454 | +0.000411 |
| oversaturated_demand | -0.000515 | +0.000737 |
| incident_or_capacity_drop | -0.003414 | +0.001156 |
| capacity_drop | +0.012320 | +0.003150 |

### Control Validation Summary

- `py_compile`: passed.
- Targeted guard/rollout/WU tests: 4 passed.
- Full `src.tests.test_constraints`: 65 passed.
- 7200 s WU/PFO all-scenario rerun completed.
- `authority_ok=True` for all WU/PFO rows.

### PFO Ramp/Throughput Diagnostic

The full-controller guard substantially reduced PFO's restrictive metering and
fixed the earlier throughput-shortfall pattern.

| scenario | improvement | urban TTT delta | freeway TTT delta | throughput delta veh/h | terminal on-ramp delta | terminal total delta | ramp active | avg ramp ratio | guard selected previous/no/default |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| low_demand | +0.623% | +3.2 | +1.1 | +3.3 | -1.0 | -6.0 | 0/40 | 1.000 | 39/0/0 |
| medium_demand | +1.426% | +14.5 | +13.2 | +14.2 | -18.1 | -28.2 | 2/40 | 0.981 | 29/5/0 |
| peak_demand | +0.188% | +16.0 | +5.9 | +6.6 | -4.1 | -13.2 | 1/40 | 0.981 | 32/3/0 |
| oversaturated_demand | +0.281% | +40.4 | +15.1 | +15.9 | -10.9 | -31.6 | 1/40 | 0.981 | 36/2/0 |
| incident_or_capacity_drop | +0.201% | +15.8 | +5.3 | +6.3 | -4.7 | -12.7 | 2/40 | 0.963 | 29/4/0 |
| capacity_drop | +0.196% | +2.9 | +59.5 | +44.7 | -8.1 | -89.2 | 2/40 | 0.989 | 34/3/0 |

### Comparison To Pre-Guard PFO

| scenario | pre-guard improvement | full-guard improvement | pre-guard TTT | full-guard TTT | pre-guard throughput delta | full-guard throughput delta | pre-guard terminal delta | full-guard terminal delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| low_demand | +0.080% | +0.623% | 695.162 | 691.383 | +2.4 | +3.3 | -3.8 | -6.0 |
| medium_demand | +0.154% | +1.426% | 1940.978 | 1916.244 | -0.6 | +14.2 | +4.2 | -28.2 |
| peak_demand | -0.680% | +0.188% | 11738.835 | 11637.655 | -30.9 | +6.6 | +63.3 | -13.2 |
| oversaturated_demand | -0.290% | +0.281% | 19791.395 | 19678.640 | -5.1 | +15.9 | +11.4 | -31.6 |
| incident_or_capacity_drop | -0.142% | +0.201% | 10488.088 | 10452.109 | -8.7 | +6.3 | +18.9 | -12.7 |
| capacity_drop | -3.818% | +0.196% | 33008.400 | 31732.015 | -840.1 | +44.7 | +1680.4 | -89.2 |

### Failed Criteria

Full completion is still not claimed.

- PFO now improves all six scenarios, but remains below the 8% acceptance
  threshold.
- Boundary B-sum is slightly degraded for PFO in all non-low scenarios, though
  the deltas are much smaller than before.
- WU-CD-F still has near-zero effect and worsens peak/oversaturated/incident/
  capacity-drop slightly.
- The full four-controller 7200 s suite was not rerun after this guard patch;
  only the affected WU/PFO controllers were rerun.

### Proposed Next Modification

The full-controller guard fixed the major throughput/on-ramp accumulation
failure mode without adding a new queue penalty. The next likely improvement is
to keep this guard and then tune/expand green/offset candidate generation,
because PFO now mostly selects previous/no-control guards and rarely accepts
active metering. A throughput-shortfall guard is less urgent after this result,
but remains useful if future candidate expansion reintroduces upstream storage.

## 2026-06-18 - Combined Ramp/Intersection Spillback Capacity Constraints

### Literature/Spec Check

The proposed direction is reasonable and consistent with ramp-metering MPC
practice:

- Airaldi, De Schutter, and Dabiri formulate ramp metering with a stage-cost
  term for violations of the maximum queue constraint:
  https://arxiv.org/abs/2311.08820
- Li and Savla's adaptive MPC ramp-metering paper gives conditions under which
  closed-loop ramp queue lengths remain bounded:
  https://arxiv.org/abs/2308.05265
- The local spec already requires `0 <= ramp_queue <= ramp_queue_max` and queue
  overflow penalties in `docs/spec/04_controller.md`, while spec 18 requires
  ramp queue TTS and queue overflow terms in the TTS-compatible follower
  objective.

### Implementation

Implemented a combined spillback feasibility layer for the distributed freeway
agent candidate search:

- On-ramp combined capacity = upstream intersection on-ramp movement storage
  plus the ramp reservoir capacity.
- On-ramp terminal occupancy = current upstream movement queue + current ramp
  queue + forecast ramp arrivals - candidate metering release.
- Off-ramp combined capacity = off-ramp storage link capacity plus downstream
  intersection movement-leg storage.
- Off-ramp terminal occupancy = current off-ramp storage occupancy + downstream
  movement queue + VSL-scaled predicted off-ramp inflow.
- Candidate selection now prefers spillback-feasible RM/VSL candidates. If all
  candidates are infeasible, the existing ramp queue penalty weights the
  violation so the least-violating candidate can still be selected.

### Files Changed

- `src/controllers/spillback_constraints.py` (new helper module)
- `src/controllers/distributed_coordinator.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Validation Commands

Compile:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\spillback_constraints.py src\controllers\distributed_coordinator.py src\tests\test_constraints.py
```

Targeted tests:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_spillback_assessment_uses_combined_ramp_and_intersection_capacity src.tests.test_constraints.ConstraintTests.test_distributed_freeway_agent_reports_spillback_constraint_diagnostics src.tests.test_constraints.ConstraintTests.test_distributed_freeway_agent_jointly_evaluates_metering_and_vsl_guards
```

Full constraints:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints
```

360 s all-scenario four-controller smoke, including regenerated no-control
baselines with the same scenario demand/horizon:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --T-total 360 --output outputs\spillback_capacity_constraint_smoke_360_2026_06_18 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED
```

### Validation Results

- `py_compile`: passed.
- Targeted tests: 3 passed.
- Full `src.tests.test_constraints`: 67 passed.
- 360 s closed-loop smoke completed for six scenarios, four controllers, plus
  no-control baseline.
- Selected-candidate spillback diagnostics were written to `control_timeseries`
  columns such as `diag_agent_*_spillback_constraint_feasible`.

### 360 s Smoke TTT/TTS Summary

Output root:
`outputs\spillback_capacity_constraint_smoke_360_2026_06_18`

Positive improvement means lower TTT than no-control. Computation time is
controller-reported decision time over the smoke run.

| scenario | no-control TTT | controller | TTT | delay | comp sec | TTT improvement |
|---|---:|---|---:|---:|---:|---:|
| low_demand | 32.386 | WU-CD-F | 32.386 | 2.219 | 1.32 | +0.000% |
| low_demand | 32.386 | PROPOSED-FOLLOWERS-ONLY | 32.323 | 2.156 | 1.33 | +0.195% |
| low_demand | 32.386 | PROPOSED-STACKELBERG | 35.822 | 5.655 | 45.81 | -10.610% |
| low_demand | 32.386 | PROPOSED-CENTRALIZED | 32.796 | 2.629 | 25.82 | -1.266% |
| medium_demand | 41.011 | WU-CD-F | 41.036 | 0.635 | 1.32 | -0.061% |
| medium_demand | 41.011 | PROPOSED-FOLLOWERS-ONLY | 40.834 | 0.434 | 1.30 | +0.432% |
| medium_demand | 41.011 | PROPOSED-STACKELBERG | 44.178 | 3.777 | 47.37 | -7.722% |
| medium_demand | 41.011 | PROPOSED-CENTRALIZED | 42.294 | 1.894 | 35.54 | -3.128% |
| peak_demand | 49.745 | WU-CD-F | 49.745 | -0.262 | 2.46 | +0.000% |
| peak_demand | 49.745 | PROPOSED-FOLLOWERS-ONLY | 49.372 | -0.635 | 1.98 | +0.750% |
| peak_demand | 49.745 | PROPOSED-STACKELBERG | 53.842 | 3.835 | 48.84 | -8.236% |
| peak_demand | 49.745 | PROPOSED-CENTRALIZED | 51.482 | 1.475 | 27.45 | -3.492% |
| oversaturated_demand | 62.540 | WU-CD-F | 62.546 | 0.778 | 1.76 | -0.010% |
| oversaturated_demand | 62.540 | PROPOSED-FOLLOWERS-ONLY | 62.012 | 0.245 | 1.73 | +0.844% |
| oversaturated_demand | 62.540 | PROPOSED-STACKELBERG | 67.407 | 5.640 | 49.37 | -7.782% |
| oversaturated_demand | 62.540 | PROPOSED-CENTRALIZED | 64.048 | 2.281 | 27.37 | -2.411% |
| incident_or_capacity_drop | 48.235 | WU-CD-F | 48.235 | 0.114 | 1.69 | +0.000% |
| incident_or_capacity_drop | 48.235 | PROPOSED-FOLLOWERS-ONLY | 47.864 | -0.257 | 1.36 | +0.769% |
| incident_or_capacity_drop | 48.235 | PROPOSED-STACKELBERG | 52.393 | 4.273 | 49.52 | -8.620% |
| incident_or_capacity_drop | 48.235 | PROPOSED-CENTRALIZED | 50.031 | 1.910 | 27.56 | -3.723% |
| capacity_drop | 117.497 | WU-CD-F | 117.142 | -27.650 | 3.00 | +0.302% |
| capacity_drop | 117.497 | PROPOSED-FOLLOWERS-ONLY | 116.736 | -28.055 | 3.31 | +0.648% |
| capacity_drop | 117.497 | PROPOSED-STACKELBERG | 126.916 | -17.876 | 52.79 | -8.016% |
| capacity_drop | 117.497 | PROPOSED-CENTRALIZED | 125.793 | -18.999 | 27.25 | -7.061% |

### Boundary Queue Balancing Result

- PFO improved TTT in all six 360 s smoke scenarios, but boundary balance still
  degraded in `medium_demand`, `capacity_drop`, and possibly other short-run
  cases depending on controllability/degeneracy flags.
- Stackelberg and centralized still show strong throughput shortfall in this
  short run, so full completion is not claimed.

### Spillback Constraint Diagnostic

In the 360 s smoke, selected candidates had:

- max selected on/off-ramp combined spillback violation: `0.000 veh`
- infeasible selected agent-steps: `0`

This means the new constraint layer is active and logged, but it was not binding
in the 360 s smoke. It should matter most when candidate generation proposes
metering/VSL actions that would fill the combined on-ramp or off-ramp storage
over the prediction horizon.

### Failed Criteria / Next Modification

Full completion is still not claimed.

- The 360 s smoke is not an acceptance run.
- PFO remains below the 8% acceptance threshold in both the previous 7200 s run
  and this smoke.
- WU-CD-F remains close to no-control, indicating its signal/VSL-only authority
  still has limited leverage.
- Stackelberg/centralized still worsen total TTT in the 360 s smoke, mainly via
  throughput/terminal accumulation rather than direct selected-candidate
  spillback violation.

Next likely modification: add the same combined spillback feasibility diagnostic
to the leader/centralized candidate evaluation path, or add a horizon throughput
shortfall guard there, because the distributed freeway candidate layer alone
does not explain the leader/centralized short-run degradation.

## 2026-06-19 - Revert Distributed Response Rollout To Proxy And Harden Spillback Guards

### What Was Implemented

Per user diagnosis, reverted the expensive PFO/WU distributed final-response
selector from coupled horizon rollout TTT back to the lightweight
TTS-compatible conservation proxy.

Also strengthened the queue constraint path so it is not only a post-hoc
filter:

- Freeway metering candidate generation now adds an on-ramp
  spillback-min-release boundary candidate.
- On-ramp feasibility is evaluated using expected physically releasable flow
  `min(candidate_metering, upper)` rather than requested metering alone.
- Candidate selection is lexicographic: feasible first; if all infeasible, lower
  spillback violation first; objective breaks ties.
- Full-controller guard candidates (`previous`, `no_control`, `default`) now
  carry the same response-level combined spillback diagnostics. They can no
  longer beat an active response solely by proxy objective if they have larger
  spillback violation.
- Response objective diagnostics now explicitly log
  `distributed_response_rollout_active=0.0`.

### Files Changed

- `src/controllers/distributed_coordinator.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Validation Commands

Compile:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\distributed_coordinator.py src\tests\test_constraints.py
```

Targeted tests:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_distributed_response_objective_uses_lightweight_proxy_without_rollout src.tests.test_constraints.ConstraintTests.test_distributed_freeway_candidates_include_spillback_min_release_boundary src.tests.test_constraints.ConstraintTests.test_leaderless_guard_selection_respects_spillback_constraint src.tests.test_constraints.ConstraintTests.test_leaderless_distributed_evaluates_full_controller_guards
```

Full constraints:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints
```

360 s four-controller smoke:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --T-total 360 --output outputs\proxy_hard_spillback_guard_smoke_360_2026_06_19 --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED
```

7200 s WU/PFO check:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario all --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY --T-total 7200 --output outputs\proxy_hard_spillback_guard_wu_pfo_7200_2026_06_19 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

### Validation Results

- `py_compile`: passed.
- Targeted tests: 4 passed.
- Full `src.tests.test_constraints`: 69 passed.
- 360 s four-controller smoke completed.
- 7200 s WU/PFO all-scenario check completed.

### 360 s Computation Cost Impact

Compared with the prior rollout-TTT smoke, the proxy path reduced computation
substantially for WU/PFO and Stackelberg.

| scenario | controller | rollout comp sec | proxy comp sec | rollout improvement | proxy improvement |
|---|---|---:|---:|---:|---:|
| low_demand | WU-CD-F | 1.32 | 0.04 | +0.000% | +0.000% |
| low_demand | PROPOSED-FOLLOWERS-ONLY | 1.33 | 0.04 | +0.195% | +0.000% |
| low_demand | PROPOSED-STACKELBERG | 45.81 | 6.79 | -10.610% | -16.553% |
| medium_demand | WU-CD-F | 1.32 | 0.04 | -0.061% | +0.000% |
| medium_demand | PROPOSED-FOLLOWERS-ONLY | 1.30 | 0.04 | +0.432% | +0.000% |
| medium_demand | PROPOSED-STACKELBERG | 47.37 | 7.32 | -7.722% | -14.079% |
| peak_demand | WU-CD-F | 2.46 | 0.08 | +0.000% | +0.000% |
| peak_demand | PROPOSED-FOLLOWERS-ONLY | 1.98 | 0.08 | +0.750% | +0.000% |
| peak_demand | PROPOSED-STACKELBERG | 48.84 | 7.33 | -8.236% | -6.475% |
| oversaturated_demand | WU-CD-F | 1.76 | 0.08 | -0.010% | +0.000% |
| oversaturated_demand | PROPOSED-FOLLOWERS-ONLY | 1.73 | 0.08 | +0.844% | +0.000% |
| oversaturated_demand | PROPOSED-STACKELBERG | 49.37 | 6.99 | -7.782% | -13.236% |
| incident_or_capacity_drop | WU-CD-F | 1.69 | 0.08 | +0.000% | +0.000% |
| incident_or_capacity_drop | PROPOSED-FOLLOWERS-ONLY | 1.36 | 0.09 | +0.769% | +0.000% |
| incident_or_capacity_drop | PROPOSED-STACKELBERG | 49.52 | 7.48 | -8.620% | -16.876% |
| capacity_drop | WU-CD-F | 3.00 | 0.16 | +0.302% | +0.000% |
| capacity_drop | PROPOSED-FOLLOWERS-ONLY | 3.31 | 0.18 | +0.648% | +0.000% |
| capacity_drop | PROPOSED-STACKELBERG | 52.79 | 7.44 | -8.016% | -7.487% |

### 7200 s WU/PFO Result

Output root:
`outputs\proxy_hard_spillback_guard_wu_pfo_7200_2026_06_19`

| scenario | controller | total TTT | delay | comp sec | improvement |
|---|---|---:|---:|---:|---:|
| low_demand | WU-CD-F | 695.716 | 4.995 | 1.00 | +0.000% |
| low_demand | PROPOSED-FOLLOWERS-ONLY | 695.716 | 4.995 | 1.03 | +0.000% |
| medium_demand | WU-CD-F | 1943.962 | 1019.342 | 1.14 | +0.000% |
| medium_demand | PROPOSED-FOLLOWERS-ONLY | 1943.962 | 1019.342 | 1.07 | +0.000% |
| peak_demand | WU-CD-F | 11659.562 | 10515.542 | 1.41 | +0.000% |
| peak_demand | PROPOSED-FOLLOWERS-ONLY | 11659.562 | 10515.542 | 1.44 | +0.000% |
| oversaturated_demand | WU-CD-F | 19734.156 | 18321.761 | 1.26 | +0.000% |
| oversaturated_demand | PROPOSED-FOLLOWERS-ONLY | 19734.156 | 18321.761 | 1.28 | +0.000% |
| incident_or_capacity_drop | WU-CD-F | 10473.200 | 9372.666 | 1.18 | +0.000% |
| incident_or_capacity_drop | PROPOSED-FOLLOWERS-ONLY | 10473.200 | 9372.666 | 1.21 | +0.000% |
| capacity_drop | WU-CD-F | 31794.474 | 28171.317 | 1.41 | +0.000% |
| capacity_drop | PROPOSED-FOLLOWERS-ONLY | 31794.474 | 28171.317 | 1.41 | +0.000% |

### Constraint/Guard Diagnostic

- Agent-level spillback-min-release candidates are generated and become active
  in non-low scenarios:
  - medium: max `176.442 veh/h`
  - peak/oversaturated/incident/capacity-drop: max `3000 veh/h`
- Final guard selection still chooses `previous` in all 40 steps for every
  WU/PFO scenario.
- In these runs, `previous` is effectively no-control/max-metering from the
  prior step. Therefore the combined on-ramp constraint cannot demand a higher
  metering rate: the previous guard is already at max metering.
- Remaining response-level spillback violation in high-demand cases is not
  caused by under-metering relative to no-control; it is caused by demand and
  receiving/storage limits that cannot be cleared within the response horizon.

### Interpretation

The user's concern was correct in structure:

- A hard queue constraint must affect candidate generation and final guard
  selection; otherwise it is mostly diagnostic.
- The implementation now does both.

However, the result did not improve WU/PFO performance because the relevant
fallback (`previous`) is already no-control/max-metering in normal closed-loop
operation. The spillback constraint has no additional RM lever beyond max
metering. Reverting to the proxy fixes computation cost but removes the small
active-control gains that the rollout objective had accepted.

### Failed Criteria / Next Modification

Full completion is not claimed.

- WU/PFO are now computationally cheap but exactly match no-control in the 7200 s
  check.
- Stackelberg remains worse than no-control in the 360 s smoke.
- The queue constraint alone cannot create improvement when no-control already
  satisfies the metering-side safety action.

Next modification should target the proxy's ranking of non-metering controls:
green/offset/VSL candidates need a local objective term or guard condition that
can accept throughput-improving active controls without reintroducing expensive
full coupled rollout for every candidate.

## Medium Control Interval Sensitivity: 120 s / 5-Step Proxy Guard

### What Was Tested

The medium-demand scenario was rerun with a shorter controller update interval
to check whether the inactive WU/PFO behavior was caused by the default
`control_interval=180 s` being out of phase with the `cycle_length=120 s`.

Overrides:

- `simulation.T_total = 7200.0`
- `simulation.control_interval = 120.0`
- `mpc.horizon_steps = 5`
- `mpc.max_nash_iter = 3`
- `mpc.relaxed_quantized_controls = true`

This keeps the prediction span close to the prior 3 x 180 s setting
(new horizon = 5 x 120 s = 600 s, prior horizon = 540 s).

### Run Command

Inline Python used the existing comparison helpers from
`src.experiments.all_scenarios_four_controller_comparison` and
`src.experiments.six_controller_comparison`, writing to:

```text
outputs\medium_control_interval_120_horizon5_wu_pfo_7200_2026_06_19
```

Controllers:

- `WU-CD-F`
- `PROPOSED-FOLLOWERS-ONLY`
- plus `NO-CONTROL` baseline

### Result

| controller | total TTT | total delay | comp sec | wall sec | improvement vs no-control |
|---|---:|---:|---:|---:|---:|
| NO-CONTROL | 1962.233 | 1039.683 | 0.00 | 2.378 | 0.000% |
| WU-CD-F | 1962.233 | 1039.683 | 1.74 | 4.183 | 0.000% |
| PROPOSED-FOLLOWERS-ONLY | 1962.233 | 1039.683 | 1.89 | 4.400 | 0.000% |

Other matched metrics:

- completed vehicles: `21361.4`
- network throughput: `10680.7 veh/h`
- terminal total vehicles: `2489.6`
- mean boundary balance sum: `0.208425`

### Guard/Control Diagnostic

Control values exactly matched no-control:

- ramp metering: constant `1500 veh/h`
- VSL: constant `100 km/h`
- green times: constant `56 s`
- offsets: constant `0 s`
- max absolute control delta vs no-control: `0.0`

Full-controller guard selection:

- `diag_distributed_guard_selected_previous`: `60/60`
- `diag_distributed_guard_selected_no_control`: `0/60`
- `diag_distributed_guard_selected_default`: `0/60`

Spillback diagnostics:

- response spillback feasible fraction: `58/60 = 0.9667`
- total response spillback violation sum: `40.135 veh`
- max response spillback violation: `30.925 veh`
- agent spillback-min-release max: `414.902 veh/h`
- agent spillback-min-release positive count: `3`
- agent spillback feasibility fraction: `478/480 = 0.9958`
- `diag_distributed_response_rollout_active`: `0`

### Interpretation

Changing the controller interval from 180 s to 120 s did not activate WU/PFO.
The result stayed exactly no-control because the final full-controller guard
selected `previous` at every decision step. This means the current proxy guard
is too conservative for non-metering controls: feasible green/offset/VSL
candidates are generated, but none pass the final response-level ranking.

The 120 s no-control baseline also differs from the 180 s baseline
(`1962.233` vs `1943.962` total TTT in the prior 7200 s medium run), so
control-interval sensitivity should be interpreted within the same interval
setting rather than across intervals.

### Failed Criteria / Next Modification

Full completion is not claimed.

This experiment rules out `180 s` update phasing as the sole cause of inactive
WU/PFO behavior. The next modification should inspect the response guard
objective/candidate comparison directly: the guard is selecting `previous`
even when agent-level feasibility is almost always satisfied, so the proxy
ranking likely needs a better local benefit signal for green/offset/VSL changes
without returning to expensive full rollout evaluation.

## E 비통제 노드 TTT/TTS Coverage 보강

### 구현 내용

사용자 지적에 따라 intersection `E`는 계속 비통제 노드로 유지하되, `E`에 접한
urban link/storage와 `E` intersection movement queue가 objective 밖의 hidden sink로
해석되지 않도록 coverage를 명시화했다.

변경 파일:

- `src/models/state.py`
  - `uncontrolled_node_movement_queue_veh`
  - `uncontrolled_node_storage_occupancy_veh`
  - `uncontrolled_node_vehicles`
- `src/models/urban_queue_model.py`
  - plant urban substep diagnostics에 `urban_uncontrolled_node_*` 추가
  - `urban_uncontrolled_node_ttt`를 interval aggregation 합산 대상으로 추가
- `src/controllers/urban_follower.py`
  - UrbanFollower objective에 비통제 내부 노드 TTS 항 추가
  - `urban_uncontrolled_node_objective_tts`,
    `urban_uncontrolled_node_objective_covered` metrics 추가
- `src/controllers/distributed_coordinator.py`
  - distributed response diagnostics에
    `distributed_response_uncontrolled_node_urban_vehicles` 추가
  - urban agent diagnostics에 `urban_uncontrolled_node_*` 전달
- `src/controllers/wu_distributed.py`
  - WU 계열 control diagnostics에도 동일한 `urban_uncontrolled_node_*` coverage
    키 추가
- `src/tests/test_constraints.py`
  - E storage/queue가 total urban vehicles, plant TTT diagnostics, UrbanFollower
    objective에 포함되는 targeted tests 추가

### 설계 판단

`E`를 `network.signals`에 넣어 urban player로 만들지는 않았다. `E`는 topology상
비통제 통과 노드이며 green/offset actuator가 없으므로, player set 확장보다
TTT/TTS coverage 보강이 더 좁고 안전하다. 기존 `total_urban_vehicles(net)`와
plant urban TTT는 이미 전체 urban storage를 포함했지만, 이번 변경으로 `E` 주변
차량 수와 follower objective 반영 여부를 별도 key로 검증 가능하게 만들었다.

### Validation Commands

Compile:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\models\state.py src\models\urban_queue_model.py src\controllers\urban_follower.py src\controllers\distributed_coordinator.py src\controllers\wu_distributed.py src\tests\test_constraints.py
```

Targeted tests:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_uncontrolled_E_vehicles_are_counted_in_ttt_coverage src.tests.test_constraints.ConstraintTests.test_urban_follower_objective_covers_uncontrolled_E_vehicles src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics
```

Full constraints:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints
```

360 s medium smoke:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --T-total 360 --output outputs\e_uncontrolled_node_ttt_coverage_smoke_360_2026_06_19 --leader-candidate-count 3 --max-nash-iter 2 --optimizer-maxiter 8 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

### Validation Results

- `py_compile`: passed.
- Targeted E coverage tests: 3 passed.
- Full `src.tests.test_constraints`: 71 passed.
- 360 s medium 4-controller smoke completed.

Smoke output root:

```text
outputs\e_uncontrolled_node_ttt_coverage_smoke_360_2026_06_19
```

| controller | total TTT | total delay | comp sec | improvement vs no-control |
|---|---:|---:|---:|---:|
| NO-CONTROL | 41.011 | 0.610 | 0.00 | 0.000% |
| WU-CD-F | 41.011 | 0.610 | 0.04 | 0.000% |
| PROPOSED-FOLLOWERS-ONLY | 41.011 | 0.610 | 0.04 | 0.000% |
| PROPOSED-STACKELBERG | 45.655 | 5.254 | 0.51 | -11.324% |
| PROPOSED-CENTRALIZED | 42.506 | 2.106 | 3.70 | -3.645% |

Coverage diagnostics observed in smoke outputs:

- `run_log.csv` includes:
  - `urban_uncontrolled_node_movement_queue_veh`
  - `urban_uncontrolled_node_storage_occupancy_veh`
  - `urban_uncontrolled_node_vehicles_veh`
  - `urban_uncontrolled_node_ttt`
- distributed controller `control_timeseries.csv` includes:
  - `diag_urban_uncontrolled_node_objective_tts`
  - `diag_urban_uncontrolled_node_objective_covered`
  - `diag_distributed_response_uncontrolled_node_urban_vehicles`

Example from NO-CONTROL first row:

```text
urban_uncontrolled_node_vehicles_veh = 90.9824289271819
urban_uncontrolled_node_ttt = 2.315101272860697
```

### Failed Criteria / Next Modification

Full controller acceptance is not claimed. This change fixes accounting and
objective coverage observability for `E`, but it does not by itself make WU/PFO
active or improve the 360 s smoke performance. The next controller-side issue
remains the conservative final guard/proxy ranking that keeps selecting
`previous` for WU/PFO.

## Distributed Follower Response Freeway Queue Double-Count Fix

### Diagnosis

The user asked whether the Stackelberg leader is receiving a correct
global-TTT-compatible follower response. Code inspection confirmed a real
accounting bug in the distributed follower response proxy.

`TrafficState.total_freeway_vehicles(net)` already includes:

- freeway segment vehicles
- ramp queues
- mainline origin queues

Before this fix, `DistributedCoordinator._response_tts_objective` did:

```text
freeway_start = state.total_freeway_vehicles(net)
ramp_start = sum(state.ramp_queue.values())
origin_start = sum(state.mainline_origin_queue.values())
current_total = urban_start + ramp_start + freeway_start + off_storage_start + origin_start
```

Therefore ramp queues and mainline origin queues were counted twice in the
leader's distributed follower-TTT base. The terminal proxy had the same issue
because `freeway_terminal` started from `freeway_start` and then separate
`ramp_terminal`/`origin_terminal` were also added.

This issue affects the distributed follower path used by:

- `PROPOSED-FOLLOWERS-ONLY`
- `PROPOSED-STACKELBERG`
- WU-style distributed guard comparisons when using the shared distributed
  response objective

`WU-CD-F` and centralized system objectives were not double-counting in the
same way because their system objective uses
`total_urban_vehicles + total_freeway_vehicles + off_ramp_storage` without
adding ramp/origin queues again.

### Implementation

Changed files:

- `src/models/state.py`
  - Added `freeway_segment_vehicles(net)` for mainline segment vehicles only.
  - Kept `total_freeway_vehicles(net)` semantics unchanged: segment vehicles +
    ramp queues + origin queues.
- `src/controllers/distributed_coordinator.py`
  - Replaced distributed response `freeway_start` with
    `state.freeway_segment_vehicles(net)`.
  - Kept `ramp_start` and `origin_start` as separate non-overlapping queue
    components.
  - Added diagnostics:
    - `distributed_response_freeway_segment_vehicles`
    - `distributed_response_freeway_total_vehicles_including_queues`
    - `distributed_response_ramp_queue_start_veh`
    - `distributed_response_origin_queue_start_veh`
- `src/tests/test_constraints.py`
  - Added `test_distributed_response_objective_does_not_double_count_freeway_queues`.

Corrected response accounting:

```text
current_total =
    urban_start
  + freeway_segment_start
  + ramp_start
  + off_storage_start
  + origin_start
```

and:

```text
freeway_terminal =
    freeway_segment_start
  + freeway_mainline_arrivals
  + ramp_release
  - mainline_exit
  - offramp_inflow
```

### Validation Commands

Compile:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\models\state.py src\controllers\distributed_coordinator.py src\tests\test_constraints.py
```

Targeted response tests:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints.ConstraintTests.test_distributed_response_objective_does_not_double_count_freeway_queues src.tests.test_constraints.ConstraintTests.test_distributed_response_objective_uses_lightweight_proxy_without_rollout src.tests.test_constraints.ConstraintTests.test_distributed_response_objective_rewards_ramp_service src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics
```

Full constraints:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints
```

360 s medium smoke:

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --T-total 360 --output outputs\distributed_response_no_double_count_smoke_360_2026_06_19 --leader-candidate-count 3 --max-nash-iter 2 --optimizer-maxiter 8 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

### Validation Results

- `py_compile`: passed.
- Targeted response tests: 4 passed.
- Full `src.tests.test_constraints`: 72 passed.
- 360 s medium 4-controller smoke completed.

Smoke output root:

```text
outputs\distributed_response_no_double_count_smoke_360_2026_06_19
```

| controller | total TTT | total delay | comp sec | improvement vs no-control |
|---|---:|---:|---:|---:|
| NO-CONTROL | 41.011 | 0.610 | 0.00 | 0.000% |
| WU-CD-F | 41.011 | 0.610 | 0.04 | 0.000% |
| PROPOSED-FOLLOWERS-ONLY | 41.011 | 0.610 | 0.04 | 0.000% |
| PROPOSED-STACKELBERG | 45.655 | 5.254 | 0.50 | -11.324% |
| PROPOSED-CENTRALIZED | 42.506 | 2.106 | 2.88 | -3.645% |

Example first-row PFO diagnostics:

```text
distributed_response_current_vehicles = 284.0
distributed_response_freeway_segment_vehicles = 144.0
distributed_response_freeway_total_vehicles_including_queues = 144.0
distributed_response_ramp_queue_start_veh = 0.0
distributed_response_origin_queue_start_veh = 0.0
```

The smoke first row has no ramp/origin queue, so the numerical difference is
not visible there. The regression test explicitly sets positive ramp and
origin queues and verifies that the distributed response current-vehicle count
matches the non-overlapping sum rather than the previous double-counted sum.

### Failed Criteria / Next Modification

Full controller acceptance is not claimed. This fixes a real leader/follower
response accounting bug. Next, rerun the requested 7200 s medium 4-controller
diagnosis with the corrected response proxy and inspect whether P-Stack/PFO
selection changes, especially guard selection and terminal queue accounting.

## Medium 7200 s Four-Controller Diagnosis After Response Double-Count Fix

### Run Command

```text
C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --T-total 7200 --output outputs\medium_4controller_no_double_count_7200_2026_06_19 --leader-candidate-count 5 --max-nash-iter 3 --optimizer-maxiter 16 --optimizer-n-starts 1 --freeway-prediction-horizon-steps 3
```

Output root:

```text
outputs\medium_4controller_no_double_count_7200_2026_06_19
```

### Result Summary

| controller | total TTT | urban TTT | freeway TTT | total delay | comp sec | improvement vs no-control |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 1943.962 | 887.149 | 1056.814 | 1019.342 | 0.00 | 0.000% |
| WU-CD-F | 1943.962 | 887.149 | 1056.814 | 1019.342 | 1.34 | 0.000% |
| PROPOSED-FOLLOWERS-ONLY | 1943.962 | 887.149 | 1056.814 | 1019.342 | 1.22 | 0.000% |
| PROPOSED-STACKELBERG | 3523.838 | 3236.844 | 286.994 | 2599.218 | 23.98 | -81.271% |
| PROPOSED-CENTRALIZED | 3633.187 | 3363.420 | 269.767 | 2708.566 | 130.02 | -86.896% |

Throughput / terminal:

| controller | throughput delta vs no-control | terminal vehicles delta |
|---|---:|---:|
| WU-CD-F | 0.0 veh/h | 0.0 veh |
| PROPOSED-FOLLOWERS-ONLY | 0.0 veh/h | 0.0 veh |
| PROPOSED-STACKELBERG | -422.5 veh/h | +844.0 veh |
| PROPOSED-CENTRALIZED | -621.1 veh/h | +1247.4 veh |

Boundary:

| controller | mean B sum | delta vs no-control |
|---|---:|---:|
| NO-CONTROL | 0.189289 | 0.000000 |
| WU-CD-F | 0.189289 | 0.000000 |
| PROPOSED-FOLLOWERS-ONLY | 0.189289 | 0.000000 |
| PROPOSED-STACKELBERG | 0.046515 | -0.142774 |
| PROPOSED-CENTRALIZED | 0.144306 | -0.044983 |

### WU/PFO Diagnosis

WU-CD-F and PROPOSED-FOLLOWERS-ONLY still exactly match no-control:

- changed control columns vs no-control: `0`
- ramp metering: constant `1500 veh/h`
- VSL: constant `100 km/h`
- green: constant `56 s`
- offset: constant `0 s`
- full-controller guard selected `previous` in all `40/40` decisions

The response double-count fix did not make WU/PFO active. Their remaining issue
is still the conservative guard/proxy ranking.

### P-Stack Diagnosis

P-Stack changed only green/offset in this run:

- ramp metering: constant `1500 veh/h`
- VSL: constant `100 km/h`
- changed control columns: `15`
- green range: `35.0` to `77.0 s`
- offsets: `6.0` to `12.0 s`

The active control pattern reduced freeway TTT but moved the cost into urban
queues:

| metric | no-control avg | P-Stack avg | delta |
|---|---:|---:|---:|
| urban TTT per interval | 22.179 | 80.921 | +58.742 |
| freeway TTT per interval | 26.420 | 7.175 | -19.245 |
| urban total vehicles | 469.449 | 1655.912 | +1186.462 |
| on-ramp approach queue | 153.554 | 650.039 | +496.484 |
| ramp queue | 117.020 | 9.279 | -107.741 |
| boundary-out sink vehicles | 215.089 | 186.357 | -28.733 |
| urban total departures | 858.171 | 722.141 | -136.030 |
| E uncontrolled-node vehicles | 102.832 | 144.299 | +41.466 |

Leader/follower response diagnostics:

- mean selected `N_P_star`: `490.981 veh`
- mean selected `N_UF_star`: `5512.727 veh/h`
- mean `leader_follower_ttt_base`: `328.841 veh-h`
- mean `leader_state_accumulation_base`: `3372.126` vehicle-sum diagnostic
- mean `distributed_response_current_vehicles`: `1726.679`
- mean `distributed_response_terminal_proxy_vehicles`: `2452.330`
- mean `distributed_response_uncontrolled_node_urban_vehicles`: `144.299`

Interpretation:

P-Stack is not worsening because of direct metering restriction. It keeps
metering at max. The bad behavior comes from the urban side: the leader chooses
`N_P_star` near the calibrated critical accumulation, and the urban follower's
net-inflow/allocation response appears to treat that as a target to approach
from below. In medium demand this encourages retaining vehicles inside the
protected urban network instead of freely discharging them:

- inbound service decreases from `290.666` to `258.715 veh/interval`
- outbound service decreases from `358.299` to `310.429 veh/interval`
- on-ramp green release decreases from `185.801` to `167.043 veh/interval`
- boundary-out sink decreases from `215.089` to `186.357 veh/interval`

The controller improves freeway TTT by starving/retaining urban discharge, but
Total TTT worsens sharply because urban queues accumulate and throughput falls.

### Centralized Diagnosis

Centralized shows the same high-level failure mode:

- freeway TTT avg per interval falls by `19.676`
- urban TTT avg per interval rises by `61.907`
- on-ramp approach queue rises by `644.259`
- network throughput falls by `621.1 veh/h`
- terminal vehicles increase by `1247.4`

It is more aggressive than P-Stack:

- green range: `20.0` to `92.0 s`
- offsets: `0.0` to `105.0 s`
- D/F p1 averages drop to `36.2` and `44.3 s`, shifting service away from
  some approaches and increasing urban retention.

### Accounting Check

The corrected response diagnostic is present in the 7200 s output. For WU/PFO:

- mean `distributed_response_freeway_segment_vehicles`: `376.889`
- mean `distributed_response_freeway_total_vehicles_including_queues`: `502.037`
- mean `distributed_response_ramp_queue_start_veh`: `107.966`
- mean `distributed_response_origin_queue_start_veh`: `17.182`

This confirms the response now separates freeway segment vehicles from ramp and
origin queues rather than double-counting them.

### Failed Criteria / Next Modification

Full acceptance is not claimed.

The next correction should address `N_P_star` semantics in the urban follower
and/or leader response:

- In medium demand, `N_P_star` near `N_P_crit` is functioning like a lower target
  that can justify retaining vehicles in the protected urban network.
- For TTT minimization, `N_P_star` should likely behave as a ceiling/upper
  pressure guard, not a command to increase accumulation when current
  protected accumulation is below target.
- A targeted fix should prevent urban allocation/green decisions from reducing
  throughput or on-ramp/boundary-out discharge solely to raise `N_P` toward
  `N_P_star`.

## 2026-06-19: PFO No-Guard Diagnostic Probe

### Purpose

The medium 7200 s four-controller run showed `PROPOSED-FOLLOWERS-ONLY` equal to
no-control because the full-controller guard selected the previous/default
control at every interval. To separate "guard too conservative" from "follower
candidate package has little value", I ran an ad-hoc diagnostic probe that
monkey-patched `DistributedCoordinator._full_controller_guard_candidates` to an
empty list for `PROPOSED-FOLLOWERS-ONLY` only.

No source files were changed for this probe.

### Command

Ad-hoc Python probe using the same medium demand scenario and 7200 s horizon:

```powershell
@'
from pathlib import Path
from src.controllers.distributed_coordinator import DistributedCoordinator
from src.experiments.six_controller_comparison import run_controller
...
DistributedCoordinator._full_controller_guard_candidates = lambda self, current: []
result = run_controller(cfg, scenario, "PROPOSED-FOLLOWERS-ONLY", output_dir)
'@ | python -B -
```

Output directory:

`outputs/pfo_no_guard_probe_medium_7200_2026_06_19`

### Results

| Controller | Total TTT | Urban TTT | Freeway TTT | Delay | Completed | Throughput | Terminal vehicles | Improvement |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 1943.962 | 887.149 | 1056.814 | 1019.342 | 21380.3 | 10690.1 | 2469.8 | baseline |
| PFO no-guard probe | 1940.978 | 895.890 | 1045.088 | 1016.357 | 21379.0 | 10689.5 | 2474.0 | +0.154% |

Mean per-interval changes vs no-control:

| Metric | NO-CONTROL | PFO no-guard | Delta |
|---|---:|---:|---:|
| urban TTT | 22.179 | 22.397 | +0.219 |
| freeway TTT | 26.420 | 26.127 | -0.293 |
| urban total vehicles | 469.449 | 463.772 | -5.678 |
| ramp queue | 117.020 | 119.461 | +2.442 |
| on-ramp approach queue | 153.554 | 150.583 | -2.971 |
| boundary-out sink | 215.089 | 215.126 | +0.036 |
| urban total departures | 858.171 | 857.900 | -0.271 |
| mainline exit flow | 6388.351 | 6387.004 | -1.347 |

### Control Diagnostics

The no-guard probe changed only a narrow part of the follower package:

- `green_D_p1`: `56.0` to `72.56 s`, mean `61.433 s`
- `green_F_p1`: `56.0` to `72.602 s`, mean `62.072 s`
- `offset_D`: `6.0` to `12.0 s`, mean `9.45 s`
- VSL stayed at max for all links.
- Final control logs did not show meaningful ramp-metering variation.

### Interpretation

Removing the full-controller guard yields only a tiny `+0.154%` Total TTT
improvement, while boundary balance degrades slightly (`mean_B_sum` `0.189289`
to `0.200358`) and terminal vehicles increase by `4.2`.

Therefore the zero-improvement PFO result is not only a guard issue. The current
leaderless follower candidate package can find a very small freeway-side gain,
but it does not produce a meaningful network-level TTT reduction in the medium
scenario. This suggests the next debugging target should be the PFO candidate
generation/objective itself before further leader tuning.

### Failed Criteria / Next Modification

Full acceptance is not claimed.

Recommended next step:

- Add explicit diagnostics for the candidate selected by each urban follower
  (`p1`, `p2`, offset, local TTS cost, default/previous/proposal candidate
  comparison) before the distributed full-controller guard overwrites the final
  action.
- Then test whether broader stage-2 green/offset neighborhoods or a
  throughput-aware local TTS objective can create a real PFO improvement without
  relying on leader `N_P_star`.

## 2026-06-19: Forced Ramp-Metering Sensitivity Check

### Purpose

The PFO no-guard probe showed almost no ramp-metering activation. I checked
whether this was a plant/METANET limitation by forcing fixed ramp-metering rates
under otherwise uncontrolled fixed-signal/fixed-VSL control in the medium
7200 s scenario.

No source files were changed for this probe.

### Command

Ad-hoc Python probe:

```powershell
@'
from src.models.state import ExperimentConfig, ControlAction
from src.models.demand import load_scenarios, apply_scenario_network_overrides, DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
...
control = ControlAction.uncontrolled(cfg)
control.ramp_metering = {r: rate for r in cfg.network.ramps}
log = sim.step(control, demand, step)
'@ | python -B -
```

### Results

| Forced ramp rate | Total TTT | Urban TTT | Freeway TTT | Mean metering flow | Mean no-meter flow | Mean ramp queue | Mean receiving factor |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1500 | 1943.962 | 887.149 | 1056.814 | 3534.9 | 3534.9 | 117.0 | 0.809 |
| 1200 | 1928.134 | 876.906 | 1051.229 | 3545.2 | 4191.2 | 116.5 | 0.811 |
| 1000 | 1465.544 | 670.144 | 795.400 | 3939.1 | 5841.2 | 246.6 | 1.000 |
| 750 | 3620.337 | 2214.469 | 1405.869 | 2980.8 | 5951.6 | 583.5 | 1.000 |
| 300 | 8216.021 | 6695.742 | 1520.279 | 1198.1 | 5952.3 | 672.6 | 1.000 |
| 0 | 10886.642 | 9363.658 | 1522.984 | 0.0 | 5974.9 | 690.2 | 1.000 |

### Interpretation

The plant/METANET path can respond strongly to ramp metering. A fixed
`1000 veh/h/ramp` metering policy improves medium Total TTT by about `24.6%`
relative to no-control (`1943.962 -> 1465.544`). Therefore the current PFO/WU
failure is not because the simulation environment cannot activate ramp
metering.

The controller-side failure is more likely in candidate generation/objective
selection:

- The useful rate is an intermediate policy near `1000 veh/h/ramp`.
- Too-low metering (`750` or below) creates large ramp/on-ramp queues and
  worsens TTT.
- PFO no-guard did not discover/apply this intermediate metering regime; it
  mostly changed D/F green and offset only.

### Failed Criteria / Next Modification

Full acceptance is not claimed.

Recommended next step:

- Add freeway-follower candidate diagnostics that log each evaluated ramp-rate
  vector, its local objective terms, spillback feasibility, and selected reason.
- Check whether the current leaderless/distributed freeway objective incorrectly
  rejects the intermediate `~1000 veh/h/ramp` region due to local queue pricing,
  target construction, guard comparison, or candidate projection.

## 2026-06-19: Why PFO Does Not Search the Useful Metering Region

### Purpose

After the forced metering sensitivity check found a strong medium-scenario
improvement near `1000 veh/h/ramp`, I inspected the leaderless
`DistributedCoordinator` freeway follower candidate set on the no-control
medium trajectory.

No source files were changed for this probe.

### Method

Ad-hoc instrumentation monkey-patched
`DistributedCoordinator._metering_candidates` to print the generated candidates
for the ramp-owning freeway agents (`F_W2`, `F_E2`) at selected control steps.
The actual MPC forecast length was used.

### Findings

At step 20 (`t = 3600 s`), the ramp-owning agents generated:

```text
F_W2:
  upper = {R_D_W: 1306.7, R_F_W: 1372.5}
  target = 1339.6 total veh/h
  candidates:
    {1500.0, 1500.0}      # no-metering guard
    {649.9, 689.7}        # projected target
    {0.0, 0.0}            # spillback-min guard degenerates to zero here
    {552.4, 586.3}        # target * 0.85
    {747.3, 793.2}        # target * 1.15
  selected = {1500.0, 1500.0}

F_E2:
  upper = {R_D_E: 1405.3, R_F_E: 1471.2}
  target = 1438.2 total veh/h
  candidates:
    {1500.0, 1500.0}
    {699.5, 738.8}
    {0.0, 0.0}
    {594.5, 628.0}
    {804.4, 849.6}
  selected = {1500.0, 1500.0}
```

Similar behavior appeared at steps 5 and 10. The useful intermediate region
seen in the forced-metering probe (`~1000 veh/h/ramp`) is usually not in the
candidate set. The candidate generator first computes one target, often near
`0.5 * upper`, and then only evaluates that target plus `±15%`. It does not keep
the broader fractional set (`0.7`, `0.75`, `0.8`, `0.85`, etc.) as final
argmin candidates.

There is a second, more important issue: the local final freeway objective does
not make freeway density/vehicle TTS depend on the metering candidate. In
`_freeway_agent_objective`, the freeway vehicle term is based on current
`rhos`, and `density_excess` is also current-state based. Lower metering mostly
adds ramp queue TTS, while the future mainline relief that made the forced
`1000 veh/h/ramp` policy successful is not credited in the local argmin.

Therefore the selected no-metering guard is expected under the current cost:

- no-metering has the smallest immediate ramp queue TTS;
- lower metering candidates do not receive enough local freeway TTS benefit;
- the `~1000 veh/h/ramp` region is generally not searched anyway.

### Failed Criteria / Next Modification

Full acceptance is not claimed.

Recommended correction:

1. Expand PFO/freeway metering candidates to retain explicit feasible fractions
   of the no-metering/upper flow, including the intermediate region around
   `0.65` to `0.9` of upper capacity.
2. Replace the current metering-insensitive freeway term with a lightweight
   candidate-dependent horizon proxy: at minimum, predict merge-segment density
   under each ramp-rate candidate and include predicted freeway vehicle TTS /
   density excess in the local objective.
3. Keep the no-metering/previous guard candidates, but allow the intermediate
   metering candidate to win when it lowers predicted local TTS without causing
   spillback.

## 2026-06-19: Candidate-Dependent Freeway Rho Projection

### What Was Implemented

Implemented the proposed local rho-based TTS correction in
`DistributedCoordinator` freeway agents:

- `_metering_candidates` now retains explicit intermediate metering fractions
  of `upper`: `0.65`, `0.70`, `0.75`, `0.80`, `0.85`, and `0.90`.
- Ramp metering candidates are bounded by configured
  `freeway_follower.ramp_metering_rate_min` when a positive release is
  feasible.
- All-zero spillback-min candidates are skipped so a zero release is not added
  merely because no spillback is predicted.
- Added `_candidate_freeway_tts_terms`, which predicts candidate-dependent
  merge-segment `rho_next` over the local horizon and converts it to:
  - freeway vehicle TTS,
  - density-excess TTS,
  - terminal/peak projected density diagnostics,
  - projected release diagnostics.
- `_freeway_agent_objective` now accepts optional projected freeway vehicle TTS
  and density-excess TTS. When provided, the freeway term is candidate-dependent
  instead of using only current `rhos`.
- Added tests for intermediate metering candidates and candidate-dependent
  density/TTS pricing.

### Files Changed

- `src/controllers/distributed_coordinator.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\distributed_coordinator.py src\tests\test_constraints.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_distributed_freeway_candidates_include_intermediate_upper_fractions src.tests.test_constraints.ConstraintTests.test_distributed_freeway_projection_prices_metering_density_relief src.tests.test_constraints.ConstraintTests.test_distributed_freeway_agent_jointly_evaluates_metering_and_vsl_guards src.tests.test_constraints.ConstraintTests.test_distributed_freeway_candidates_include_ratio_one_guards src.tests.test_constraints.ConstraintTests.test_distributed_freeway_candidates_include_spillback_min_release_boundary
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints
```

Results:

```text
py_compile: OK
targeted tests: 5 tests, OK
constraints suite: 74 tests, OK
```

### Medium 7200 s Guarded PFO Run

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-FOLLOWERS-ONLY --T-total 7200 --output outputs\pfo_density_projection_minrate_guard_medium_7200_2026_06_19 --max-nash-iter 3 --freeway-prediction-horizon-steps 3
```

Results:

| Controller | Total TTT | Urban TTT | Freeway TTT | Improvement | B_sum |
|---|---:|---:|---:|---:|---:|
| NO-CONTROL | 1943.962 | 887.149 | 1056.814 | baseline | 0.189289 |
| PROPOSED-FOLLOWERS-ONLY | 1943.962 | 887.149 | 1056.814 | 0.000% | 0.189289 |

The full-controller guard still selects the previous/default action for all
40 intervals, so the newly generated metering candidates are not applied in the
guarded controller.

### Medium 7200 s No-Guard Diagnostic Probe

To inspect the raw follower package, I reran PFO with
`_full_controller_guard_candidates` monkey-patched to return an empty list.

Output:

`outputs/pfo_density_projection_minrate_no_guard_medium_7200_2026_06_19`

| Controller | Total TTT | Urban TTT | Freeway TTT | Improvement | Throughput delta | Terminal delta | B_sum |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 1943.962 | 887.149 | 1056.814 | baseline | baseline | baseline | 0.189289 |
| PFO no-guard density projection | 1970.872 | 890.712 | 1080.160 | -1.384% | -51.2 veh/h | +105.4 veh | 0.200016 |

Selected metering diagnostics in the no-guard probe:

- `ramp_metering_R_D_E`: min `67.8` before min-rate correction; after min-rate
  correction the controller still over-meters enough to worsen throughput.
- mean plant `total_metering_flow`: about `3470 veh/h`
- mean plant `total_no_meter_flow`: about `3879 veh/h`
- mean ramp queue: about `139 veh`
- mean on-ramp approach queue: about `149 veh`

### Diagnosis

The rho projection change successfully makes metering affect the local freeway
objective and causes the no-guard follower to activate metering. However, the
current lightweight projection is still not sufficient to recover the beneficial
fixed `1000 veh/h/ramp` behavior:

- The guarded controller correctly blocks the new follower action because the
  response objective does not beat previous/default.
- Without that guard, the dynamic follower action worsens Total TTT by `1.384%`.
- The local rho projection prices immediate merge-density relief, but it still
  does not capture the downstream/network-wide throughput benefit/loss with
  enough fidelity.
- The forced fixed-rate probe showed that a stable uniform `1000 veh/h/ramp`
  policy can strongly improve medium demand, but the distributed local response
  is asymmetric and time-varying, so it can reduce throughput and increase
  terminal vehicles.

### Failed Criteria / Next Modification

Full acceptance is not claimed.

Next correction should not be another local static rho proxy alone. The follower
needs a candidate evaluation that can distinguish the good stable intermediate
metering regime from harmful dynamic over-metering. Candidate options:

1. Evaluate ramp-rate candidates with a lightweight multi-step freeway rollout
   using the same `compute_ramp_release_flows`/`freeway_substep` accounting, but
   keep the horizon short and cache by agent to control computation cost.
2. Add a throughput/terminal-vehicle term to the leaderless full-response guard
   so a candidate cannot reduce completions relative to default.
3. Add a stable metering band or smoothing rule around the useful intermediate
   regime so local agents do not swing between very low and max release.

---

## 2026-06-19: Medium Demand Recheck After Rho Projection

### Purpose

Rechecked the medium-demand scenario because the previous poor ramp-metering
behavior might have been caused by peak/oversaturated demand rather than an
objective/search problem.

No code was changed in this step.

### Files Changed

- `reports/codex_run_report.md`

### Medium Demand Definition

`medium_demand` is the scenario closest to a median/base case in the current
configuration:

- `urban_scale = 1.0`
- `freeway_scale = 1.0`
- `ramp_scale = 1.0`

`peak_demand` is higher:

- `urban_scale = 1.25`
- `freeway_scale = 1.20`
- `ramp_scale = 1.25`

The demand generator still applies an internal time profile
`1.0 + 0.22 * sin(pi * x)`, so medium has a mild within-run peak but does not
use the configured peak scenario scales.

### Fixed Ramp Metering Sweep

Command type:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B - <medium fixed-rate sweep script>
```

The sweep kept signals and VSL at no-control/default and applied one uniform
ramp metering rate to all ramps for `7200 s`.

| Rate (veh/h/ramp) | Total TTT | Urban TTT | Freeway TTT | Throughput (veh/h) | Terminal vehicles | Mean ramp queue |
|---:|---:|---:|---:|---:|---:|---:|
| 1500 | 1943.962 | 887.149 | 1056.814 | 10690.1 | 2469.8 | 117.0 |
| 1400 | 1939.506 | 884.594 | 1054.912 | 10693.1 | 2464.0 | 116.5 |
| 1300 | 1933.104 | 880.569 | 1052.534 | 10697.6 | 2454.9 | 116.0 |
| 1200 | 1928.134 | 876.906 | 1051.229 | 10701.7 | 2446.8 | 116.5 |
| 1150 | 1670.964 | 764.189 | 906.775 | 10868.4 | 2113.1 | 97.9 |
| 1100 | 1081.302 | 649.807 | 431.495 | 11679.8 | 488.1 | 49.1 |
| 1050 | 1230.652 | 649.424 | 581.228 | 11600.4 | 646.7 | 131.0 |
| 1000 | 1465.544 | 670.144 | 795.400 | 11467.4 | 912.7 | 246.6 |
| 950 | 1767.871 | 748.745 | 1019.125 | 11294.1 | 1259.5 | 367.4 |
| 900 | 2115.655 | 930.960 | 1184.695 | 11108.0 | 1632.0 | 457.3 |
| 850 | 2534.394 | 1245.104 | 1289.290 | 10798.7 | 2250.8 | 515.3 |
| 800 | 3047.239 | 1688.635 | 1358.604 | 10409.6 | 3029.4 | 555.1 |
| 750 | 3620.337 | 2214.469 | 1405.869 | 10031.8 | 3785.2 | 583.5 |

Key result: medium demand has a strong beneficial metering region near
`1100 veh/h/ramp`. The issue is not that only peak/oversaturated demand makes
ramp metering impossible.

### Medium 7200 s Four-Controller Recheck

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --T-total 7200 --output outputs\medium_4controllers_recheck_2026_06_19 --max-nash-iter 3 --freeway-prediction-horizon-steps 3
```

Output directory:

`outputs/medium_4controllers_recheck_2026_06_19`

| Controller | Total TTT | Urban TTT | Freeway TTT | Improvement | Throughput (veh/h) | Terminal vehicles | B_sum | Wall time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 1943.962 | 887.149 | 1056.814 | baseline | 10690.1 | 2469.8 | 0.189289 | 4.207 s |
| WU-CD-F | 1943.962 | 887.149 | 1056.814 | 0.000% | 10690.1 | 2469.8 | 0.189289 | 4.207 s |
| PROPOSED-FOLLOWERS-ONLY | 1943.962 | 887.149 | 1056.814 | 0.000% | 10690.1 | 2469.8 | 0.189289 | 3.903 s |
| PROPOSED-STACKELBERG | 3485.428 | 3198.435 | 286.994 | -79.295% | 10374.8 | 3099.4 | 0.047000 | 64.614 s |
| PROPOSED-CENTRALIZED | 3314.431 | 3038.216 | 276.215 | -70.499% | 10260.9 | 3336.6 | 0.119405 | 527.739 s |

### Action Diagnostics

| Controller | Mean ramp action | Ramp action below 1400 | Ramp action in 1050-1150 | Mean plant metering flow | Mean ramp queue | Mean VSL | Green range | Offset range |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 1500.0 | 0.000 | 0.000 | 3534.9 | 117.0 | 100.0 | 56.0-56.0 | 0.0-0.0 |
| WU-CD-F | 1500.0 | 0.000 | 0.000 | 3534.9 | 117.0 | 100.0 | 56.0-56.0 | 0.0-0.0 |
| PROPOSED-FOLLOWERS-ONLY | 1500.0 | 0.000 | 0.000 | 3534.9 | 117.0 | 100.0 | 56.0-56.0 | 0.0-0.0 |
| PROPOSED-STACKELBERG | 1500.0 | 0.000 | 0.000 | 3339.2 | 10.0 | 100.0 | 36.0-76.0 | 0.0-12.0 |
| PROPOSED-CENTRALIZED | 1498.7 | 0.000 | 0.000 | 3187.1 | 9.0 | 99.5 | 20.0-92.0 | 0.0-109.8 |

### Diagnosis

- The fixed-rate sweep proves a good medium-demand metering solution exists
  near `1100 veh/h/ramp`.
- WU-CD-F and guarded PFO do not apply that solution. Their full-controller
  guards selected the previous/default action in all `40` intervals.
- The no-guard PFO diagnostic from the previous step selected mean ramp action
  about `1160 veh/h/ramp`, but it was unstable: about `23.7%` of ramp actions
  were below `900 veh/h/ramp`, and the run worsened Total TTT to `1970.872`.
- Stackelberg and centralized did not find the good metering band either.
  Their mean ramp action stayed almost no-control, while green/offset changes
  starved on-ramp arrivals. This reduced freeway TTT but moved excessive TTT
  into the urban side.

### Failed Criteria / Next Modification

Full acceptance is not claimed.

The medium-demand case rules out "only peak demand is too high" as the primary
cause. The remaining issue is controller search/objective structure:

1. PFO/WU need a stable intermediate metering candidate family around the
   empirically useful `1050-1150 veh/h/ramp` region, not only local pressure
   swings and previous/no-control fallback.
2. The guard should compare candidate packages that include these stable
   intermediate metering choices, so it can choose a beneficial metering action
   rather than only blocking unstable no-guard actions.
3. Stackelberg/centralized need a constraint or objective coverage fix so they
   cannot improve freeway TTT by hiding vehicles in upstream urban queues via
   signal/offset starvation while ramp metering remains essentially inactive.

---

## 2026-06-19: Medium Green Time and Offset Open-Loop Check

### Purpose

Checked whether urban green time and offset controls fail because no useful
solution exists, or because current follower/leader search does not select a
good solution. Ramp metering was fixed at no-control (`1500 veh/h/ramp`) unless
noted otherwise.

No controller code was changed in this step.

### Files Changed

- `reports/codex_run_report.md`

### Validation / Diagnostic Commands

Command type:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B - <medium fixed-policy sweep scripts>
```

The scripts used `MixedTrafficSimulator`, `DemandProfile`, and fixed
`ControlAction` policies on `medium_demand`, `T_total=7200 s`.

### Baselines

| Policy | Total TTT | Urban TTT | Freeway TTT | Throughput (veh/h) | Terminal vehicles | Mean ramp queue | Mean on-ramp approach queue |
|---|---:|---:|---:|---:|---:|---:|---:|
| RM 1500, default green/offset | 1943.962 | 887.149 | 1056.814 | 10690.1 | 2469.8 | 117.0 | 153.6 |
| RM 1100, default green/offset | 1081.302 | 649.807 | 431.495 | 11679.8 | 488.1 | 49.1 | 33.1 |

### Green-Time Sweep

Uniform all-signal green split with RM fixed at `1500 veh/h/ramp`:

| Policy | Total TTT | Urban TTT | Freeway TTT | Improvement vs default |
|---|---:|---:|---:|---:|
| all p1 = 44 s | 1098.129 | 757.939 | 340.190 | 43.511% |
| all p1 = 80 s | 1741.539 | 1423.271 | 318.268 | 10.413% |
| all p1 = 56 s | 1943.962 | 887.149 | 1056.814 | 0.000% |
| all p1 = 32 s | 2389.527 | 2086.535 | 302.992 | -22.920% |
| all p1 = 20 s | 4289.435 | 4012.240 | 277.196 | -120.654% |
| all p1 = 92 s | 4538.672 | 4258.082 | 280.590 | -133.475% |

D/F-only green grid with RM fixed at `1500 veh/h/ramp`:

| Policy | Total TTT | Urban TTT | Freeway TTT | Improvement vs default |
|---|---:|---:|---:|---:|
| D p1 = 56 s, F p1 = 44 s | 1087.523 | 745.133 | 342.390 | 44.056% |
| D p1 = 68 s, F p1 = 44 s | 1092.694 | 752.005 | 340.689 | 43.790% |
| D p1 = 44 s, F p1 = 44 s | 1095.249 | 754.890 | 340.359 | 43.659% |
| D p1 = 80 s, F p1 = 56 s | 1316.967 | 985.154 | 331.813 | 32.253% |

D/F-only green grid with RM fixed at the good metering baseline
`1100 veh/h/ramp`:

| Policy | Total TTT | Urban TTT | Freeway TTT | Improvement vs RM1100 default |
|---|---:|---:|---:|---:|
| D p1 = 56 s, F p1 = 56 s | 1081.302 | 649.807 | 431.495 | 0.000% |
| D p1 = 44 s, F p1 = 56 s | 1084.005 | 657.962 | 426.044 | -0.250% |
| D p1 = 56 s, F p1 = 68 s | 1090.060 | 656.080 | 433.980 | -0.810% |
| D p1 = 68 s, F p1 = 56 s | 1091.311 | 657.492 | 433.818 | -0.926% |

Interpretation: green time has a strong beneficial fixed-policy solution when
RM remains no-control. The effect largely overlaps with the ramp-metering
benefit; once RM is already fixed at `1100`, D/F green changes do not improve
the default split.

### Offset Sweep

Offset-only structured/random sweep with default green and RM fixed at
`1500 veh/h/ramp`:

| Policy | Total TTT | Urban TTT | Freeway TTT | Improvement vs default |
|---|---:|---:|---:|---:|
| lower-east, delta 15 s | 1912.532 | 864.631 | 1047.901 | 1.617% |
| random07 | 1913.214 | 868.760 | 1044.454 | 1.582% |
| random11 | 1915.419 | 865.856 | 1049.563 | 1.468% |
| lower-west, delta 15 s | 1916.126 | 867.429 | 1048.696 | 1.432% |

Offset on top of the good green policy (`D p1=56`, `F p1=44`):

| Policy | Total TTT | Urban TTT | Freeway TTT | Improvement vs D56/F44 no-offset |
|---|---:|---:|---:|---:|
| lower-west, delta 5 s | 1082.913 | 740.887 | 342.026 | 0.424% |
| lower-east, delta 5 s | 1083.155 | 740.775 | 342.380 | 0.402% |
| random04 | 1083.506 | 743.073 | 340.433 | 0.369% |

Worst tested offsets on top of `D56/F44` degraded TTT by about `3.1%`.

### Current Controller Action Check

The medium four-controller run at
`outputs/medium_4controllers_recheck_2026_06_19` showed:

- Guarded PFO: every signal stayed at `p1=56`, offset `0`.
- WU-CD-F: same as no-control because green/VSL-only authority plus guard
  selected previous/default.
- Stackelberg: green moved moderately, but not toward the stable D/F open-loop
  solution; final TTT degraded because urban was starved.
- Centralized: green and offsets moved aggressively, but ramp metering stayed
  almost no-control and urban TTT exploded.

The no-guard PFO diagnostic selected:

- `A p1=56`, `B p1=44`, `C p1=56`
- `D p1` mean about `61.5`
- `F p1` mean about `61.4`

This is not the good open-loop green policy. In particular, the good policy
uses `F p1=44`, while no-guard PFO tends to increase F p1.

### Local Stage-2 Objective Check

Directly calling the leaderless urban follower along the medium no-control
trajectory selected default `56/56` at almost every inspected state:

| State step | Selected D p1 | Selected F p1 | Default selected signals |
|---:|---:|---:|---:|
| 0 | 56 | 56 | 5 |
| 5 | 56 | 56 | 5 |
| 10 | 56 | 56 | 5 |
| 15 | 56 | 56 | 5 |
| 20 | 56 | 56 | 5 |
| 30 | 56 | 56 | 5 |

At state step `20`, local stage-2 costs for D/F were:

| Signal | p1 | Cost | Cost without green smoothness |
|---|---:|---:|---:|
| D | 44 | 1.2070 | 0.0070 |
| D | 56 | 0.0087 | 0.0087 |
| D | 68 | 1.2105 | 0.0105 |
| F | 44 | 1.2080 | 0.0080 |
| F | 56 | 0.0100 | 0.0100 |
| F | 68 | 1.2121 | 0.0121 |

The current local stage-2 objective is therefore strongly biased toward the
previous/default green split:

- `green_smoothness_weight * abs(p1 - previous_p1)` dominates the local TTS
  terms for moderate `12 s` green changes.
- Even without the smoothness term, the local one-signal queue proxy sees
  immediate queues, not the multi-step upstream arrival/storage/freeway
  interaction that makes `F p1=44` beneficial in the plant.
- Offset objective has the same issue: useful offset patterns are corridor
  progression effects, but the current cost mostly prices immediate phase wait
  and smoothness.

### Diagnosis

Green time definitely has useful medium-demand solutions; the current
controller does not select them. This is an objective/search issue, not a lack
of feasible good green policies.

Offset also has useful solutions, but the effect size is much smaller:
approximately `1.6%` by itself and `0.4%` on top of a good green policy in the
tested medium sweeps. Offset selection still appears to be a search/objective
coverage problem because the local cost lacks a corridor rollout, but it is a
secondary lever compared with ramp metering and D/F green split.

### Failed Criteria / Next Modification

Full acceptance is not claimed.

Recommended next implementation direction:

1. Add structured green candidate packages to the same final guard/evaluation
   path as ramp metering, especially D/F stable splits such as `F p1=44`,
   `D p1 in {44,56,68}`, and no-control/default.
2. Evaluate green packages with a short urban/freeway-compatible rollout or a
   full-response guard, not only the current per-signal stage-2 proxy.
3. Re-scale or temporarily disable green/offset smoothness inside the selection
   objective during diagnostics; keep physical max-step constraints as the
   true feasibility limit.
4. Treat offset as a smaller structured-grid refinement around good green/RM
   packages rather than the first-order control lever.

---

## 2026-06-19: A/C/D Structured Grid Search Revision

### Purpose

Implemented the requested search-control changes:

- A. hard feasibility pre-check before expensive rollout evaluation.
- C. incumbent-based rollout early termination.
- D'. finite-difference sensitivity/Jacobian direction candidate generation.

The revision keeps the broad periodic grid idea: global grid at start and every
`1800 s`, local trust-region grid between refreshes.

### Files Changed

- `src/controllers/structured_grid.py`
- `src/controllers/distributed_coordinator.py`
- `src/controllers/centralized_mpc.py`
- `src/experiments/six_controller_comparison.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Implementation Summary

- Added `sensitivity_probe_candidates` and `sensitivity_direction_candidates`.
  The probe stage evaluates +/- finite differences around the incumbent grid
  solution. The direction stage estimates local axis slopes and builds one-step,
  two-step, and small multi-axis descent candidates.
- Added candidate `axis` and `delta` metadata so sensitivity probes can be
  grouped by true control direction.
- Added hard pre-check in distributed grid evaluation using the existing
  TTS-compatible spillback diagnostics. If any feasible candidates exist in a
  stage, infeasible candidates are filtered before rollout; if no candidate is
  feasible, all candidates are retained as an explicit fallback.
- Added hard pre-check in centralized proposed mode using on-ramp arrival,
  release, and combined storage violation estimates.
- Added rollout early termination: after guard/incumbent evaluation, candidate
  rollouts stop once partial TTT exceeds the current incumbent objective.
- Exposed decision diagnostics for total candidates, sensitivity probe/direction
  counts, pre-check filtered/evaluated counts, early-terminated candidates, and
  global-refresh flags.

### Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m py_compile src\controllers\structured_grid.py src\controllers\distributed_coordinator.py src\controllers\centralized_mpc.py src\tests\test_constraints.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest src.tests.test_constraints
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 360 --controllers PROPOSED-FOLLOWERS-ONLY --output outputs\pfo_acd_sensitivity_medium_360_v3_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 7200 --controllers PROPOSED-FOLLOWERS-ONLY --output outputs\pfo_acd_sensitivity_medium_7200_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 7200 --controllers PROPOSED-FOLLOWERS-ONLY --output outputs\pfo_acd_sensitivity_peak_7200_2026_06_19
```

### Test Result

- `py_compile`: PASS
- Targeted distributed/Stackelberg tests: PASS, 5 tests in `151.327 s`
- Full constraint tests: PASS, 74 tests in `272.708 s`

### Medium 360 s Smoke

| Controller | Total TTT | Improvement vs no-control | Total delay | Throughput (veh/h) | Computation time |
|---|---:|---:|---:|---:|---:|
| NO-CONTROL | 41.011 | 0.000% | 0.610 | 9185.7 | 0.0 |
| PROPOSED-FOLLOWERS-ONLY | 40.452 | 1.363% | 0.052 | 9330.2 | 83.32 s |

Diagnostics:

- Step 0: `327` candidates, `31` sensitivity probes, `249`
  early-terminated candidates, global refresh active.
- Step 1: `164` candidates, `30` sensitivity probes, `122`
  early-terminated candidates, local scope.
- Sensitivity direction candidates were `0` in this smoke because the probe
  stage found no improving descent axis after the coarse incumbent.
- Pre-check filtered candidates were `0`; the current feasibility estimator
  considered all tested candidates feasible.

### Medium 7200 s PFO Result

| Controller | Total TTT | Delay | Throughput (veh/h) | Terminal vehicles | Boundary non-degraded | Computation time |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 1943.962 | 1019.342 | 10690.1 | 2469.8 | baseline | 0.0 |
| PROPOSED-FOLLOWERS-ONLY | 1000.610 | 75.990 | 11720.0 | 418.3 | True | 1595.23 s |

Improvement:

- Total TTT improvement: `48.527%`
- Total delay improvement: `92.545%`
- Throughput delta: `+1029.9 veh/h`
- Terminal vehicle delta: `-2051.5`
- Mean boundary sum delta: `-0.033438`

Search diagnostics:

- Steps: `40`
- Candidate sum: `8417`
- Early-terminated candidate sum: `6752`
- Global refresh steps: `4`
- Mean computation per control step: `39.881 s`

Control summary:

| Control | Min | Mean | Max |
|---|---:|---:|---:|
| `R_D_W` metering | 1500.0 | 1500.0 | 1500.0 |
| `R_D_E` metering | 1100.0 | 1401.4 | 1500.0 |
| `R_F_W` metering | 1500.0 | 1500.0 | 1500.0 |
| `R_F_E` metering | 1000.5 | 1374.6 | 1500.0 |
| `D_p1` | 56.0 | 56.0 | 56.0 |
| `F_p1` | 50.0 | 55.9 | 56.0 |
| `FW_W` VSL | 100.0 | 100.0 | 100.0 |
| `FW_E` VSL | 100.0 | 100.0 | 100.0 |

### Peak 7200 s PFO Result

| Controller | Total TTT | Delay | Throughput (veh/h) | Terminal vehicles | Boundary non-degraded | Computation time |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 11659.562 | 10515.542 | 7936.1 | 13488.0 | baseline | 0.0 |
| PROPOSED-FOLLOWERS-ONLY | 3773.909 | 2629.889 | 12894.7 | 3565.7 | False | 1697.49 s |

Improvement:

- Total TTT improvement: `67.632%`
- Total delay improvement: `74.990%`
- Throughput delta: `+4958.6 veh/h`
- Terminal vehicle delta: `-9922.3`
- Mean boundary sum delta: `+0.076874`
- Max boundary overflow ratio: `0.214286`

Search diagnostics:

- Steps: `40`
- Candidate sum: `10050`
- Early-terminated candidate sum: `7760`
- Global refresh steps: `4`
- Mean computation per control step: `42.437 s`

Control summary:

| Control | Min | Mean | Max |
|---|---:|---:|---:|
| `R_D_W` metering | 923.8 | 1078.6 | 1500.0 |
| `R_D_E` metering | 817.2 | 1038.4 | 1500.0 |
| `R_F_W` metering | 919.3 | 1132.7 | 1500.0 |
| `R_F_E` metering | 850.0 | 1040.8 | 1500.0 |
| `D_p1` | 20.0 | 40.0 | 68.0 |
| `F_p1` | 22.6 | 44.3 | 58.6 |
| `FW_W` VSL | 100.0 | 100.0 | 100.0 |
| `FW_E` VSL | 100.0 | 100.0 | 100.0 |

### Diagnosis

- The A/C/D search revision fixes the medium PFO failure: the controller now
  finds a strong 7200 s solution, improves throughput, and reduces terminal
  vehicles rather than hiding vehicles upstream.
- The computation cost is high: about `40-42 s` per 180 s control interval for
  PFO on the tested machine. Early termination is active and large
  (`6752/8417` medium, `7760/10050` peak), but the broad grid plus full
  sensitivity probes is still expensive.
- The hard pre-check did not bind in these runs (`0` filtered candidates in the
  inspected diagnostics). This means the current spillback feasibility estimate
  is not the limiting factor for the chosen medium/peak candidate sets.
- Peak demand passes TTT/delay/throughput checks but fails boundary balance.
  The peak controller uses aggressive metering and green changes; it reduces
  network accumulation strongly, but shifts boundary balance upward.
- Sensitivity direction candidates can be zero when the probe stage finds no
  improving local descent axis after the coarse incumbent. The probe stage is
  still active; a future version may allow non-improving but high-gradient
  directions if extrapolation is desired.

### Failed Criteria / Next Modification

Full acceptance is not claimed.

- Only PFO was run for the new A/C/D implementation at 7200 s. The four
  controller comparison still needs rerun after this search revision.
- Peak PFO fails boundary balance despite large TTT improvement.
- Computation cost remains too high for online use without further pruning or a
  compiled/batched rollout path.

Proposed next modification:

1. Run the same medium/peak 7200 s comparison for `WU-CD-F`,
   `PROPOSED-STACKELBERG`, and `PROPOSED-CENTRALIZED`.
2. Add a boundary-balance term or hard boundary-balance guard to the grid
   objective for peak demand, separate from the spillback feasibility check.
3. Keep the current broad global grid, but consider compiled batch rollout or
   process-level parallelism before expanding the grid further.

---

## 2026-06-19: Switchable Grid Parallel Backend

### Purpose

Added a small reusable grid-parallel module so candidate rollout evaluation can
be switched at runtime without rewriting controller logic.

Supported backends:

- `serial`: no parallelism/off switch.
- `thread`: previous behavior, `ThreadPoolExecutor`-style candidate evaluation.
- `process`: chunked `ProcessPoolExecutor` candidate rollout evaluation.

### Files Changed

- `src/controllers/grid_parallel.py`
- `src/controllers/distributed_coordinator.py`
- `src/controllers/centralized_mpc.py`
- `src/experiments/six_controller_comparison.py`
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `reports/codex_run_report.md`

### Implementation Summary

- Added `MPCConfig` fields:
  - `grid_parallel_backend: serial|thread|process`
  - `grid_parallel_max_workers`
  - `grid_parallel_min_items`
  - `grid_parallel_chunk_size`
- Added CLI options to experiment runners:
  - `--grid-parallel-backend`
  - `--grid-parallel-max-workers`
  - `--grid-parallel-chunk-size`
- Added `src/controllers/grid_parallel.py` with a single `evaluate_grid_items`
  entry point.
- Kept guard/incumbent evaluation serial, then evaluated non-guard candidate
  batches with the configured backend.
- Process backend uses chunk payloads so Windows spawn does not send one
  process task per candidate.
- Logged backend diagnostics into decision CSV:
  - backend used
  - fallback flag
  - worker count
  - chunk count

### Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m py_compile src\controllers\grid_parallel.py src\controllers\distributed_coordinator.py src\controllers\centralized_mpc.py src\models\state.py src\experiments\six_controller_comparison.py src\experiments\all_scenarios_four_controller_comparison.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics src.tests.test_constraints.ConstraintTests.test_wu_cd_f_adapter_uses_green_vsl_only_ttt_coordinator
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 360 --controllers PROPOSED-FOLLOWERS-ONLY --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --output outputs\pfo_grid_process_medium_360_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 360 --controllers PROPOSED-FOLLOWERS-ONLY --grid-parallel-backend serial --output outputs\pfo_grid_serial_medium_360_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 7200 --controllers PROPOSED-FOLLOWERS-ONLY --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --output outputs\pfo_grid_process_medium_7200_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 7200 --controllers PROPOSED-FOLLOWERS-ONLY --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --output outputs\pfo_grid_process_peak_7200_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest src.tests.test_constraints
```

### Test Result

- `py_compile`: PASS
- Targeted tests: PASS, 2 tests in `38.816 s`
- Full constraint tests: PASS, 74 tests in `284.502 s`

### 360 s Backend Smoke

| Backend | Scenario | Total TTT | Improvement | Compute time | Backend fallback |
|---|---|---:|---:|---:|---:|
| `thread` previous smoke | medium | 40.452 | 1.363% | 83.32 s | 0 |
| `process` | medium | 40.452 | 1.363% | 18.33 s | 0 |
| `serial` | medium | 40.452 | 1.363% | 80.7 s wall | 0 |

Process diagnostics showed `distributed_grid_parallel_backend_process=1.0`,
`distributed_grid_parallel_backend_fallback=0.0`, and up to `8` workers.

### 7200 s PFO Backend Comparison

| Scenario | Backend | Total TTT | Improvement | Delay | Throughput | Terminal vehicles | Boundary OK | Compute time | Avg decision |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| medium | thread | 1000.610 | 48.527% | 75.990 | 11720.0 | 418.3 | True | 1595.23 s | 39.881 s |
| medium | process | 1000.610 | 48.527% | 75.990 | 11720.0 | 418.3 | True | 341.98 s | 8.549 s |
| peak | thread | 3773.909 | 67.632% | 2629.889 | 12894.7 | 3565.7 | False | 1697.49 s | 42.437 s |
| peak | process | 3773.909 | 67.632% | 2629.889 | 12894.7 | 3565.7 | False | 402.69 s | 10.067 s |

Speedup:

- Medium process vs thread: `1595.23 / 341.98 = 4.66x`
- Peak process vs thread: `1697.49 / 402.69 = 4.22x`

Controller-performance check:

- Medium process backend exactly matched thread backend on Total TTT, delay,
  throughput, terminal vehicles, candidate count, and early-termination count.
- Peak process backend exactly matched thread backend on the same metrics.
- Therefore process parallelization did not change the selected controller
  trajectory for the tested PFO medium/peak 7200 s runs.

### Diagnosis

- Process-level candidate rollout evaluation is clearly better than thread
  evaluation for this Python-object-heavy simulator.
- The online decision cost for PFO falls from roughly `40-42 s` per decision to
  roughly `8.5-10.1 s` per decision.
- Because the control interval is `180 s`, the process backend uses about
  `4.7-5.6%` of the available interval for PFO decisions in these two runs.
- The process backend did not solve the peak boundary-balance issue; it only
  preserves controller behavior while reducing compute time.

### Failed Criteria / Next Modification

Full acceptance is still not claimed.

- The process backend has been validated on PFO medium/peak 7200 s. The four
  controller comparison still needs rerun with `--grid-parallel-backend process`.
- Peak PFO still fails boundary balance.
- Stackelberg may benefit more from the backend, but its leader-candidate loop
  still needs a dedicated timing check.

---

## 2026-06-19: Medium Stackelberg Process-Backend Timing Check

### Purpose

Attempted the requested median/medium `PROPOSED-STACKELBERG` run after enabling
the process backend. The goal was to verify whether the new grid parallelism is
enough for Stackelberg and whether controller performance changes.

### Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 7200 --controllers PROPOSED-STACKELBERG --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --output outputs\stackelberg_grid_process_medium_7200_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 180 --controllers PROPOSED-STACKELBERG --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --output outputs\stackelberg_grid_process_medium_180_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 180 --controllers PROPOSED-STACKELBERG --leader-candidate-count 4 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --output outputs\stackelberg_grid_process_medium_180_lc4_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 180 --controllers PROPOSED-STACKELBERG --leader-candidate-count 8 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --output outputs\stackelberg_grid_process_medium_180_lc8_2026_06_19
```

### Result

- The full `7200 s` medium Stackelberg run was stopped by the `20 min` command
  limit. No completed Stackelberg summary CSV was produced because the runner
  writes controller CSVs only after the controller run completes.
- The no-control baseline for the same attempted run completed all `40` steps
  and matches the medium baseline scale.
- A one-decision `180 s` Stackelberg smoke completed and showed the bottleneck.

### 180 s Stackelberg Timing

| Requested leader candidates | Actual candidates | Total TTT | Improvement vs no-control | Compute time | Solver evals | Grid candidates | Nash iterations |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 5 | 17.803 | -1.062% | 65.27 s | 2305 | 331 | 10 |
| 8 | 9 | 17.803 | -1.062% | 116.09 s | 4149 | 331 | 10 |
| 15/default | 16 | 17.803 | -1.062% | 207.89 s | 7376 | 331 | 10 |

The process backend was active in the selected follower response:
`distributed_grid_parallel_backend_process=1.0`,
`distributed_grid_parallel_backend_fallback=0.0`, `workers=8`.

### Diagnosis

- Stackelberg is still too expensive for a full medium `7200 s` run in the
  current structure.
- Runtime scales almost linearly with the number of leader candidates. The
  default one-decision run took `207.89 s`; a 40-step closed-loop run would be
  roughly `2.3 h` if the same cost persists.
- The follower/grid process backend works, but it sits inside a mostly serial
  leader-candidate loop. The current bottleneck is therefore not candidate
  rollout inside one follower response; it is repeated follower solves across
  leader candidates.
- For the first decision, reducing leader candidates from default `16` to `5`
  preserved the same selected closed-loop action/TTT in the `180 s` smoke, but
  this is not enough evidence for a 7200 s acceptance run.

### Proposed Next Modification

Do not run full default Stackelberg again until the leader loop is changed.

Recommended options:

1. Add a cheap leader prefilter: evaluate all leader candidates with the
   lightweight follower proxy, then run full distributed follower/grid only for
   top `K` candidates plus previous/default guards.
2. Add outer leader-candidate parallelism, but avoid nested process pools by
   using either outer-process + inner-serial/thread or a shared process-pool
   scheduler.
3. Add leader candidate caching/warm start: if adjacent candidates pick the
   same follower control or have near-identical proxy response, skip duplicate
   full follower rollout.
4. For diagnostic runs, use `--leader-candidate-count 4` or `8`; the first
   `180 s` smoke suggests major speed gains with no first-step TTT change, but
   this must be validated over longer horizons.

---

## 2026-06-19: Stackelberg Leader Prefilter and Outer Parallelism

### Purpose

Confirmed and extended Stackelberg acceleration:

- The Stackelberg follower response already uses `DistributedCoordinator` when
  `mpc.follower_solver_mode=distributed`, so the follower-side A/C/D grid
  changes are active:
  - A. hard feasibility pre-check
  - C. incumbent-based rollout early termination
  - D'. finite-difference sensitivity direction generation
- Added the three leader-side improvements requested after the first medium
  Stackelberg timeout:
  - cheap leader proxy prefilter
  - leader-candidate outer parallelism
  - nested process-pool avoidance when outer process mode is used

### Files Changed

- `src/controllers/stackelberg_mpc.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/experiments/six_controller_comparison.py`
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `reports/codex_run_report.md`

### Implementation Summary

- Added `MPCConfig` fields:
  - `stackelberg_prefilter_top_k`
  - `stackelberg_leader_parallel_backend: serial|thread|process`
  - `stackelberg_leader_parallel_max_workers`
  - `stackelberg_inner_backend_when_outer_process: serial|thread`
- Added CLI options with the same names in kebab case.
- Cheap proxy prefilter evaluates all leader candidates using the
  TTS-compatible distributed response proxy without running full Nash/grid for
  each candidate.
- Full follower/grid evaluation is then run only for selected candidates.
- Leader-candidate outer parallelism supports `serial`, `thread`, and
  `process`.
- If outer leader parallelism uses `process` and the inner grid backend is also
  configured as `process`, the inner grid backend is downgraded to configured
  `stackelberg_inner_backend_when_outer_process` (`thread` by default), so
  nested process pools are not created.
- Solver-evaluation accounting now uses
  `leader_candidate_full_evaluated_count` instead of raw candidate count when
  prefiltering is active.

### Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m py_compile src\controllers\stackelberg_mpc.py src\models\state.py src\experiments\six_controller_comparison.py src\experiments\all_scenarios_four_controller_comparison.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_default_objective_uses_follower_response_without_rollout src.tests.test_constraints.ConstraintTests.test_stackelberg_can_use_distributed_follower_solver src.tests.test_constraints.ConstraintTests.test_leader_candidate_budget_covers_extremes_and_previous_action
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 180 --controllers PROPOSED-STACKELBERG --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-prefilter-top-k 4 --stackelberg-leader-parallel-backend process --stackelberg-leader-parallel-max-workers 4 --stackelberg-inner-backend-when-outer-process thread --output outputs\stackelberg_outer_process_medium_180_top4_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 180 --controllers PROPOSED-STACKELBERG --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-prefilter-top-k 4 --stackelberg-leader-parallel-backend process --stackelberg-leader-parallel-max-workers 4 --stackelberg-inner-backend-when-outer-process serial --output outputs\stackelberg_outer_process_medium_180_top4_inner_serial_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 180 --controllers PROPOSED-STACKELBERG --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-prefilter-top-k 4 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 4 --output outputs\stackelberg_outer_thread_medium_180_top4_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 7200 --controllers PROPOSED-STACKELBERG --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-prefilter-top-k 4 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 4 --output outputs\stackelberg_outer_thread_medium_7200_top4_2026_06_19
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest src.tests.test_constraints
```

### Test Result

- `py_compile`: PASS
- Targeted Stackelberg tests: PASS, 3 tests in `74.912 s`
- Full constraint tests: PASS, 74 tests in `267.245 s`
- No leftover Python workers after runs.

### 180 s Timing Comparison

All 180 s cases selected the same first-step closed-loop TTT:
`17.803` vs no-control `17.616` (`-1.062%`).

| Mode | Full leader candidates | Inner grid backend | Compute time | Notes |
|---|---:|---|---:|---|
| previous default, serial leader | 16 | process | 207.89 s | full candidate loop |
| prefilter top4, serial leader | 5 | process | 65.27 s | earlier diagnostic |
| prefilter top4, outer process | 4 | thread | 68.67 s | nested process avoided |
| prefilter top4, outer process | 4 | serial | ~71 s wall | nested process avoided |
| prefilter top4, outer thread | 4 | process | 30.82 s | fastest smoke |

Interpretation:

- Outer `process` correctly avoids nested process pools, but downgrading the
  inner grid backend to thread/serial loses much of the follower-grid speedup.
- Outer `thread` plus inner `process` is fastest in this codebase because it
  parallelizes leader candidates while preserving the faster process backend
  inside each follower/grid solve. This is not nested process pooling because
  the outer layer is threads, not processes.

### Medium 7200 s Stackelberg Result

Command used the fastest safe smoke setting:

```powershell
--stackelberg-prefilter-top-k 4
--stackelberg-leader-parallel-backend thread
--stackelberg-leader-parallel-max-workers 4
--grid-parallel-backend process
```

| Controller | Total TTT | Delay | Throughput (veh/h) | Terminal vehicles | Boundary OK | Compute time |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 1943.962 | 1019.342 | 10690.1 | 2469.8 | baseline | 0.0 |
| PROPOSED-STACKELBERG | 1006.538 | 81.917 | 11720.6 | 411.0 | True | 890.82 s |

Improvement:

- Total TTT improvement: `48.222%`
- Total delay improvement: `91.964%`
- Throughput delta: `+1030.5 veh/h`
- Terminal vehicle delta: `-2058.8`
- Mean boundary sum delta: `-0.004195`

Timing diagnostics:

- Steps: `40`
- Total compute: `890.817 s`
- Average decision time: `22.270 s`
- Max decision time: `43.123 s`
- Raw leader candidates: `640` total (`16` per step)
- Full evaluated leader candidates after prefilter: `160` total (`4` per step)
- Prefilter active on all `40` steps
- Outer leader thread backend active on all `40` steps
- Inner distributed grid process backend active on all `40` steps

Control summary:

| Control | Min | Mean | Max |
|---|---:|---:|---:|
| `R_D_W` metering | 1440.6 | 1497.0 | 1500.0 |
| `R_D_E` metering | 1000.5 | 1356.8 | 1500.0 |
| `R_F_W` metering | 1440.6 | 1497.0 | 1500.0 |
| `R_F_E` metering | 1161.7 | 1402.4 | 1500.0 |
| `D_p1` | 44.0 | 48.2 | 56.0 |
| `F_p1` | 50.0 | 54.2 | 56.0 |
| `FW_W` VSL | 100.0 | 100.0 | 100.0 |
| `FW_E` VSL | 100.0 | 100.0 | 100.0 |

### Diagnosis

- The requested leader-side acceleration makes medium Stackelberg practical
  under the 20-minute target on this machine.
- Medium Stackelberg now performs similarly to PFO:
  - PFO process medium: `1000.610`, compute `341.98 s`
  - Stackelberg top4/thread+process medium: `1006.538`, compute `890.82 s`
- Stackelberg is still slower than PFO because every step evaluates four full
  leader-conditioned follower responses.
- The cheap proxy consistently selected a useful top-K on medium; first five
  steps had proxy best index equal to final best index (`0`).
- The prefilter changes controller semantics because only top-K candidates are
  fully evaluated. This is a deliberate speed/coverage trade-off and should be
  reported separately from full default Stackelberg.

### Failed Criteria / Next Modification

Full acceptance is not yet claimed.

- The medium Stackelberg run passes TTT/delay/throughput/boundary checks, but
  peak Stackelberg has not been rerun with this leader prefilter/parallel setup.
- Full default Stackelberg without prefilter remains too expensive.
- Need compare `top_k=4` vs `top_k=8` over 7200 s to quantify whether the
  proxy prefilter ever drops a better full-evaluation candidate.

## 2026-06-19 - Leader Coarse/Refined Grid And Movement-Bound Diagnostics

### Implementation

- Added a two-stage leader search to `StackelbergMPCController`:
  - global/coarse leader candidate stage at `t=0` and every
    `mpc.leader_global_refresh_sec`;
  - local refined leader candidate stage around the best coarse action;
  - non-refresh steps use a local coarse stage around the previous leader
    reference, then the same refined stage.
- Increased the default leader coarse search budget from `15` to `49` and added
  `mpc.leader_refinement_candidate_count=25`.
- Added leader diagnostics for coarse/refined candidate counts, evaluated
  counts, best-stage flags, global-refresh flags, and N_P/N_UF feasible bounds.
- Added N_UF physical lower binding from the configured ramp metering minimum.
  A leader target below the ramp lower bound is projected to the minimum
  aggregate release instead of permitting a zero-metering action.
- Added N_P movement-bound diagnostics. The urban allocation target is checked
  against:
  - `min_net = sum(inflow lower) - sum(outflow upper)`
  - `max_net = sum(inflow upper) - sum(outflow lower)`
  which corresponds to the requested
  `[(inflow min, outflow max), (inflow max, outflow min)]` binding.

### Files Changed

- `src/controllers/leader.py`
- `src/controllers/stackelberg_mpc.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/tests/test_constraints.py`

### Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\leader.py src\controllers\stackelberg_mpc.py src\models\state.py src\tests\test_constraints.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_leader_evaluates_coarse_and_refined_grid src.tests.test_constraints.ConstraintTests.test_allocation_net_inflow_binding_uses_inflow_outflow_extremes src.tests.test_constraints.ConstraintTests.test_leader_nuf_candidates_and_projection_respect_ramp_bounds src.tests.test_constraints.ConstraintTests.test_stackelberg_normalizes_no_control_previous_nuf_reference src.tests.test_constraints.ConstraintTests.test_leader_candidate_budget_covers_extremes_and_previous_action src.tests.test_constraints.ConstraintTests.test_stackelberg_can_use_distributed_follower_solver
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 180 --controllers PROPOSED-STACKELBERG --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-prefilter-top-k 0 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 4 --output outputs\stackelberg_leader_refined_medium_180_2026_06_19
```

### Test Result

- `py_compile`: PASS
- Targeted constraints/Stackelberg tests: PASS, 6 tests in `91.978 s`
- Medium 180 s smoke: completed.
- Full constraints suite was not rerun after this change because the new
  full-evaluation leader refinement substantially increases Stackelberg test
  runtime.

### Medium 180 s Smoke Result

| Controller | Total TTT | Delay | Throughput (veh/h) | Terminal vehicles | Boundary OK | Compute time |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 17.616 | 4.394 | 8000.6 | 399.4 | baseline | 0.0 |
| PROPOSED-STACKELBERG | 18.301 | 1.730 | 7180.3 | 439.4 | False | 55.45 s |

Improvement:

- Total TTT improvement: `-3.889%`
- Total delay improvement: positive relative to prior Stackelberg smoke, but
  total TTT still worse than no-control on this 180 s smoke.
- Boundary balance degraded slightly on this short smoke:
  `mean_B_sum=0.119673` vs no-control `0.109886`.

Leader diagnostics:

- Coarse candidates: `50`
- Refined candidates: `25`
- Full evaluated leader candidates: `75`
- Best stage: refined
- Selected `N_P_star`: `458.504`
- Selected `N_UF_star`: `5446.488 veh/h`
- Selected ramp metering: `1361.622 veh/h` on each of the four ramps
- `N_P` calibrated bound: `[458.504, 534.921]`
- `N_UF` bound: `[1715.700, 6000.000]`
- Movement-derived N_P net-flow interval:
  `[-22100.000, 21466.667] veh/h`
- Movement-derived N_P bound active: no, because the movement feasible interval
  is much wider than the calibrated N_P band in the medium initial state.

### Diagnosis / Next Modification

- The leader is no longer limited to 16 coarse candidates. It now evaluates a
  broad stage plus a refined local stage, and the refined stage actually changed
  the selected leader action in the smoke run.
- The earlier `N_UF_star=0` pathology is fixed by ramp minimum binding and
  no-control previous-reference normalization.
- `N_P_star` movement binding is present in the allocation target clipping and
  now logged in leader diagnostics. In the medium initial state it is not active
  because movement capacity is not the binding constraint.
- The remaining short-smoke TTT loss is now more likely from the
  leader-conditioned urban green/allocation choice than from ramp closure.
- Next check should compare 7200 s medium with the refined leader before drawing
  acceptance conclusions; 180 s is only a smoke and currently costs `55.45 s`.

## 2026-06-19 - Leader Top-K Prefilter And Incumbent Early-Termination Hook

### Implementation

- Enabled leader top-K prefilter by default with
  `mpc.stackelberg_prefilter_top_k=8`.
- Applied the same top-K prefilter to both leader stages:
  - coarse/global or coarse/local stage;
  - refined local stage around the coarse best.
- Preserved proxy ranking order in the selected top-K set so the first full
  candidate can seed the incumbent.
- Added leader incumbent propagation:
  - `_evaluate_candidate_set` evaluates the first selected candidate as an
    incumbent seed;
  - subsequent leader candidates receive the current best leader objective as
    `incumbent_obj`;
  - `DistributedCoordinator.solve(..., leader_incumbent_obj=...)` passes that
    threshold into leader-conditioned follower grid rollout evaluation;
  - follower rollout candidates can terminate early when partial rollout TTT
    exceeds the incumbent threshold.
- Added diagnostics:
  - coarse/refined prefilter active and selected counts;
  - incumbent seed/active/final objective flags;
  - total follower grid early-terminated candidate count across evaluated
    leader candidates.

### Files Changed

- `src/controllers/stackelberg_mpc.py`
- `src/controllers/distributed_coordinator.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/tests/test_constraints.py`

### Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\stackelberg_mpc.py src\controllers\distributed_coordinator.py src\models\state.py src\tests\test_constraints.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_leader_evaluates_coarse_and_refined_grid src.tests.test_constraints.ConstraintTests.test_allocation_net_inflow_binding_uses_inflow_outflow_extremes src.tests.test_constraints.ConstraintTests.test_stackelberg_can_use_distributed_follower_solver
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --T-total 180 --controllers PROPOSED-STACKELBERG --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 4 --output outputs\stackelberg_leader_topk_incumbent_medium_180_2026_06_19
```

### Test Result

- `py_compile`: PASS
- Targeted unittest: PASS, 3 tests in `40.433 s`
- Medium 180 s smoke: completed.

### Medium 180 s Smoke Result

| Controller | Total TTT | Delay | Throughput (veh/h) | Terminal vehicles | Boundary OK | Compute time |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 17.616 | 4.394 | 8000.6 | 399.4 | baseline | 0.0 |
| PROPOSED-STACKELBERG | 18.301 | 1.730 | 7180.3 | 439.4 | False | 15.99 s |

Comparison to full refined leader smoke:

- Same selected refined leader action:
  `N_P_star=458.504`, `N_UF_star=5446.488 veh/h`.
- Same 180 s total TTT: `18.301`.
- Compute time dropped from `55.45 s` to `15.99 s`.

Leader diagnostics:

- Total generated leader candidates: `75`
- Coarse candidates: `50`
- Refined candidates: `25`
- Full evaluated leader candidates after top-K: `17`
- Coarse evaluated: `9`
- Refined evaluated: `8`
- Coarse prefilter active: `1`
- Refined prefilter active: `1`
- Top-K: `8`
- Best stage: refined
- Incumbent passed to follower evaluations: active
- Follower rollout early-terminated candidates in this smoke: `0`

### Diagnosis / Next Modification

- Top-K prefilter is now active and preserved the same refined best action on
  the medium 180 s smoke while cutting compute time by about `71%`.
- Incumbent early-termination plumbing is implemented, but the medium 180 s
  smoke did not trigger actual early exits because none of the evaluated
  follower rollouts exceeded the incumbent threshold early enough.
- Need run at least medium 7200 s to measure whether early termination triggers
  in later congested steps and whether the top-K refined leader preserves the
  previous full-refined performance.

## 2026-06-19: WU-CD-F PFO-Based Green/VSL-Only Authority Check

### What Changed

- Confirmed `WU-CD-F` is routed through the PFO `DistributedCoordinator` with
  ablation mode `WU_GREEN_VSL_ONLY_TTT`.
- Added a regression test proving the shared structured-grid and sensitivity
  candidate generation exposes only green-time and VSL axes under `authority="wu"`.
- The test also verifies that any malicious previous/center control with
  non-neutral ramp metering, offsets, or allocation is reset to Wu authority:
  ramp metering at no-metering capacity, zero offsets, and no inflow-outflow
  allocation.

### Files Changed

- `src/tests/test_constraints.py`

### Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "src\controllers\distributed_coordinator.py" "src\controllers\structured_grid.py" "src\experiments\six_controller_comparison.py" "src\tests\test_constraints.py"
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_green_vsl_only_ttt_mode_preserves_wu_authority src.tests.test_constraints.ConstraintTests.test_wu_cd_f_adapter_uses_green_vsl_only_ttt_coordinator src.tests.test_constraints.ConstraintTests.test_wu_structured_grid_exposes_only_green_and_vsl_authority -v
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers WU-CD-F --T-total 180 --output outputs\wu_cd_f_green_vsl_only_medium_180_2026_06_19 --max-nash-iter 1 --freeway-prediction-horizon-steps 3
```

### Test Result

- `py_compile`: PASS
- Targeted unittest: PASS, 3 tests in `43.457 s`
- Medium 180 s WU-CD-F smoke: completed.

### Medium 180 s Smoke Result

| Controller | Total TTT | Delay | Throughput (veh/h) | Terminal vehicles | Mean B sum | Compute time |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 17.616 | 1.046 | 8000.6 | 399.4 | 0.109886 | 0.00 s |
| WU-CD-F | 17.525 | 0.955 | 7917.2 | 401.1 | 0.233959 | 21.23 s |

### Authority Verification

- `wu_green_vsl_only_ttt_authority`: min `1`, max `1`
- Ramp metering request ranges:
  - `R_D_E`: `1500..1500 veh/h`
  - `R_D_W`: `1500..1500 veh/h`
  - `R_F_E`: `1500..1500 veh/h`
  - `R_F_W`: `1500..1500 veh/h`
- Max absolute offset: `0 s`
- Max absolute allocation value: `0 veh/h`
- VSL selected in this short medium smoke: all freeway links/segments stayed at
  `100 km/h`
- Green times changed, e.g. `D_p1=38`, `F_p1=44`, confirming the Wu path can
  still use signal authority while RM/offset/allocation stay disabled.

### Diagnosis / Next Modification

- The requested modification is effectively already implemented for `WU-CD-F`:
  it is PFO's TTS-compatible distributed/grid solver with Wu authority limited
  to green time and VSL.
- The old `WuDistributedController` remains available for matched-Wu legacy
  comparisons such as `WU-MATCHED-STACKELBERG`; `WU-CD-F` in the four-controller
  comparison does not use that legacy path.
- This smoke is not an acceptance run. Boundary balance worsened over 180 s, so
  later performance diagnosis should still use medium/peak 7200 s comparisons.

## 2026-06-19: No-Control + WU/PFO/Stackelberg 7200 s Six-Scenario Screening

### What Was Run

- Ran the requested controller set:
  - `NO-CONTROL` baseline
  - `WU-CD-F`
  - `PROPOSED-FOLLOWERS-ONLY`
  - `PROPOSED-STACKELBERG`
- Scenario set: all six configured scenarios.
- Horizon: `7200 s`.
- The first attempt used `max_nash_iter=3` and thread grid parallelism, but
  `low_demand` timed out after `1800 s` before Stackelberg completed. Partial
  output was preserved at:
  `outputs\no_wu_pfo_stack_7200_2026_06_19_v1\low_demand`.
- Completed screening therefore used `max_nash_iter=1`, process-based grid
  evaluation, and process-based Stackelberg leader outer-loop evaluation.

### Files / Outputs Changed

- `outputs\no_wu_pfo_stack_7200_2026_06_19_v2\<scenario>\...`
- Combined CSVs:
  - `outputs\no_wu_pfo_stack_7200_2026_06_19_v2\combined_no_control_summary.csv`
  - `outputs\no_wu_pfo_stack_7200_2026_06_19_v2\combined_controller_summary.csv`
  - `outputs\no_wu_pfo_stack_7200_2026_06_19_v2\combined_controller_vs_no_control.csv`
- `reports/codex_run_report.md`

### Baseline / Proposed Run Command

The no-control baseline is run inside the same paired driver and therefore uses
the same scenario, demand, seed, horizon, and plant as each controller:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario <scenario> --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --T-total 7200 --output outputs\no_wu_pfo_stack_7200_2026_06_19_v2\<scenario> --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-leader-parallel-backend process --stackelberg-leader-parallel-max-workers 8 --stackelberg-inner-backend-when-outer-process serial
```

### Result Summary

| Scenario | Controller | Total TTT | Delay | TTT improvement vs no-control | Computation sec | Throughput veh/h | Terminal veh | Mean B sum |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| low_demand | NO-CONTROL | 695.716 | 4.995 | 0.000% | 0.00 | 8,689.7 | 303.2 | 0.150430 |
| low_demand | WU-CD-F | 682.782 | -7.938 | 1.859% | 243.98 | 8,690.7 | 299.6 | 0.332087 |
| low_demand | PROPOSED-FOLLOWERS-ONLY | 680.545 | -10.176 | 2.181% | 301.18 | 8,694.0 | 298.8 | 0.147724 |
| low_demand | PROPOSED-STACKELBERG | 4,089.887 | 3,399.166 | -487.867% | 680.63 | 6,746.5 | 4,196.9 | 0.026209 |
| medium_demand | NO-CONTROL | 1,943.962 | 1,019.342 | 0.000% | 0.00 | 10,690.1 | 2,469.8 | 0.189289 |
| medium_demand | WU-CD-F | 1,027.697 | 103.076 | 47.134% | 244.02 | 11,712.4 | 421.0 | 0.227123 |
| medium_demand | PROPOSED-FOLLOWERS-ONLY | 1,000.610 | 75.990 | 48.527% | 349.54 | 11,720.0 | 418.3 | 0.155851 |
| medium_demand | PROPOSED-STACKELBERG | 7,691.122 | 6,766.502 | -295.642% | 673.60 | 8,197.6 | 7,454.4 | 0.014013 |
| peak_demand | NO-CONTROL | 11,659.562 | 10,515.542 | 0.000% | 0.00 | 7,936.1 | 13,488.0 | 0.082207 |
| peak_demand | WU-CD-F | 7,370.486 | 6,226.466 | 36.786% | 251.46 | 10,262.4 | 8,832.8 | 0.165210 |
| peak_demand | PROPOSED-FOLLOWERS-ONLY | 3,773.909 | 2,629.889 | 67.632% | 413.57 | 12,894.7 | 3,565.7 | 0.159081 |
| peak_demand | PROPOSED-STACKELBERG | 10,399.443 | 9,255.424 | 10.808% | 684.18 | 9,756.8 | 9,842.0 | 0.009136 |
| oversaturated_demand | NO-CONTROL | 19,734.156 | 18,321.761 | 0.000% | 0.00 | 7,431.0 | 21,459.7 | 0.041634 |
| oversaturated_demand | WU-CD-F | 18,615.646 | 17,203.251 | 5.668% | 242.84 | 7,674.2 | 20,973.3 | 0.069393 |
| oversaturated_demand | PROPOSED-FOLLOWERS-ONLY | 15,793.348 | 14,380.953 | 19.969% | 370.33 | 8,839.9 | 18,649.1 | 0.098495 |
| oversaturated_demand | PROPOSED-STACKELBERG | 16,380.151 | 14,967.756 | 16.996% | 561.63 | 9,205.1 | 17,906.5 | 0.010211 |
| incident_or_capacity_drop | NO-CONTROL | 10,473.200 | 9,372.666 | 0.000% | 0.00 | 8,027.7 | 12,400.5 | 0.091609 |
| incident_or_capacity_drop | WU-CD-F | 6,293.528 | 5,192.994 | 39.908% | 250.00 | 10,382.3 | 7,688.8 | 0.175629 |
| incident_or_capacity_drop | PROPOSED-FOLLOWERS-ONLY | 3,234.854 | 2,134.320 | 69.113% | 416.85 | 12,816.2 | 2,818.6 | 0.266097 |
| incident_or_capacity_drop | PROPOSED-STACKELBERG | 10,041.496 | 8,940.962 | 4.122% | 680.86 | 9,517.5 | 9,415.7 | 0.009146 |
| capacity_drop | NO-CONTROL | 31,794.474 | 28,171.317 | 0.000% | 0.00 | 11,531.7 | 33,074.4 | 0.044671 |
| capacity_drop | WU-CD-F | 31,254.907 | 27,631.750 | 1.697% | 242.59 | 12,201.1 | 31,735.8 | 0.056720 |
| capacity_drop | PROPOSED-FOLLOWERS-ONLY | 30,807.868 | 27,184.711 | 3.103% | 346.61 | 12,819.1 | 30,499.7 | 0.083774 |
| capacity_drop | PROPOSED-STACKELBERG | 42,840.461 | 39,217.304 | -34.742% | 386.27 | 6,920.2 | 42,297.4 | 0.003880 |

### Control Validation Summary

- All completed controller runs reported `authority_ok=True`.
- `WU-CD-F` remained in the green/VSL-only authority group while using the PFO
  distributed TTS-compatible solver path.
- Solver convergence rates were mixed:
  - WU-CD-F: `1.0`, `0.35`, `0.025`, `0.075`, `0.075`, `0.0`
  - PFO: `1.0`, `1.0`, `0.05`, `0.175`, `0.1`, `0.0`
  - Stackelberg: `0.0` in all six scenarios
- This is a completed 7200 s screening run, but not a final acceptance run
  because it used `max_nash_iter=1` after the stricter `max_nash_iter=3`
  attempt timed out.

### Boundary Queue Balancing Result

- PFO only improved mean B sum in `low_demand` and `medium_demand`.
- WU-CD-F worsened mean B sum in all six scenarios.
- Stackelberg has very low mean B sum in all scenarios, but this is misleading
  in the failed cases because it also creates much larger terminal vehicle
  accumulation and lower throughput.
- Therefore boundary non-degradation is not globally satisfied.

### Failed Criteria

Full completion is not claimed.

- The initial stricter `max_nash_iter=3` run did not complete within 30 minutes
  even for `low_demand`.
- The completed screening used `max_nash_iter=1`, so Nash/follower convergence
  is weaker than the intended controller setting.
- PFO clears the 8% TTT improvement threshold in medium, peak, oversaturated,
  and incident scenarios, but not in low or capacity_drop.
- WU-CD-F clears 8% only in medium, peak, and incident scenarios.
- Stackelberg is severely worse than no-control in low, medium, and
  capacity_drop, despite improving peak and oversaturated.
- Boundary non-degradation fails for most WU/PFO scenarios.

### Diagnosis / Next Modification

- The WU-CD-F rewrite is now behaviorally meaningful: unlike the prior nearly
  inactive WU path, the PFO-based green/VSL-only controller improves TTT in all
  six scenarios. It still fails the 8% target in low, oversaturated, and
  capacity_drop and generally worsens boundary balance.
- PFO is now the strongest active controller in this screening. It delivers
  large TTT/throughput/terminal-vehicle gains in medium, peak, oversaturated,
  and incident scenarios, but capacity_drop remains below threshold and boundary
  balance often worsens.
- Stackelberg remains the main broken path. The leader-conditioned follower
  projection/top-K search is selecting actions that hide or strand vehicles in
  low/medium/capacity_drop: throughput collapses and terminal vehicles explode
  in those failed cases. The low/medium failures are too large to be explained
  by follower noise alone; the leader objective/guard needs a whole-action
  throughput/terminal-vehicle protection against no-control/PFO incumbent.
- Next suggested modification: add a Stackelberg leader-level incumbent guard
  that evaluates no-control and PFO follower-only response as admissible
  fallback actions, then rejects leader candidates whose full closed-loop
  short-horizon objective has lower predicted throughput or higher terminal
  vehicle accumulation without sufficient TTT gain.

## 2026-06-19: Why Stackelberg Can Be Worse Than Follower-Only

### Diagnostic Question

The surprising result was that `PROPOSED-STACKELBERG` can be much worse than
`PROPOSED-FOLLOWERS-ONLY` even though Stackelberg evaluates a follower response.

### Code-Level Findings

- `PROPOSED-FOLLOWERS-ONLY` calls `DistributedCoordinator.solve(..., leader=None)`.
  That path runs the broad follower structured grid:
  `distributed_grid_full_search_active=1`.
- `PROPOSED-STACKELBERG` calls `DistributedCoordinator.solve(..., leader=action)`.
  That path runs `_leader_conditioned_grid_refinement`, not the same follower
  search as PFO:
  `distributed_grid_leader_conditioned=1`,
  `distributed_grid_full_search_active=0`.
- In the completed 7200 s screening:
  - PFO evaluated about `160-330` follower grid candidates per interval.
  - Stackelberg's leader-conditioned follower evaluated only `21` candidates
    per leader candidate.
- Therefore the Stackelberg follower response is a constrained/local response
  to the leader target, not the unconstrained PFO best response. PFO is not in
  the Stackelberg candidate set as a fallback.

### Quantitative Evidence

Low, medium, and capacity-drop failed because Stackelberg's leader-conditioned
response introduces nonzero allocation and binds the follower around leader
`N_P_star/N_UF_star` targets. PFO has no allocation authority in this comparison.

| Scenario | Controller | mean metering ratio | mean abs offset | mean abs allocation | mean terminal proxy veh |
|---|---|---:|---:|---:|---:|
| low_demand | PFO | 1.000 | 34.90 | 0.0 | 890.9 |
| low_demand | Stackelberg | 0.900 | 45.10 | 723.9 | 2631.1 |
| medium_demand | PFO | 0.963 | 55.02 | 0.0 | 1190.2 |
| medium_demand | Stackelberg | 0.895 | 13.24 | 772.5 | 4665.8 |
| capacity_drop | PFO | 0.995 | 42.98 | 0.0 | 17616.7 |
| capacity_drop | Stackelberg | 0.500 | 4.21 | 845.4 | 24318.3 |

Concrete examples:

- `low_demand` final Stackelberg intervals still targeted
  `N_UF_star≈4537-5259 veh/h` and selected metering sums exactly matching those
  targets, while the terminal proxy had grown to about `4480-4657 veh`.
- `medium_demand` final Stackelberg intervals had terminal proxy vehicles around
  `7839-7987`, compared with PFO's roughly `1068-1102` at the end.
- `capacity_drop` Stackelberg eventually selected `N_UF_star=1200 veh/h` and
  strong VSL/lower metering, with terminal proxy vehicles above `43k-45k`.

### Interpretation

- The presence of a follower response does not guarantee dominance over PFO
  because the follower is solving a different, leader-constrained problem.
- The current leader objective uses the follower-response objective as its base
  and adds target/density/smoothness terms. It does not include a hard
  comparison against PFO/no-control throughput or terminal accumulation.
- The allocation module becomes active only in the Stackelberg path. In the
  failed scenarios, leader-conditioned allocation and metering targets can
  reduce short-horizon objective locally while increasing actual terminal
  accumulation over the 7200 s closed-loop run.
- This is a Stackelberg guard/candidate-set problem, not evidence that PFO's
  follower logic itself is worse.

### Proposed Fix Direction

1. Add PFO/no-control as admissible Stackelberg fallback candidates at the
   whole-action level, not only as per-agent follower guards.
2. During leader evaluation, reject candidates whose response has lower
   predicted throughput or higher terminal vehicles than the PFO/no-control
   incumbent unless the TTT gain clears a threshold.
3. Expand leader-conditioned follower candidates to include the PFO neutral
   control neighborhood: empty allocation, no leader RM projection, and previous
   follower action.
4. Add diagnostics comparing each selected Stackelberg action against a PFO
   incumbent objective at the same state/forecast.

## 2026-06-19: Stackelberg PFO/No-Control Fallback Guard Implementation

### What Was Implemented

- Added whole-action fallback candidates to `StackelbergMPCController`:
  - physical `no-control`;
  - `PFO follower-only` response from `DistributedCoordinator.solve(..., leader=None)`.
- Added a leader-level guard after coarse/refined leader evaluation:
  - compare the best leader-conditioned response against the best fallback;
  - reject the leader candidate if it is objective-worse, terminal-proxy severe,
    completed-vehicle severe, or terminal/completion-worse without enough
    objective gain;
  - select the PFO/no-control fallback when the guard rejects the leader.
- Added diagnostics:
  - `leader_fallback_guard_active`
  - `leader_fallback_guard_selected`
  - `leader_fallback_guard_selected_pfo`
  - `leader_fallback_guard_selected_no_control`
  - leader/fallback objective, terminal proxy, and completed proxy comparisons
  - selected stage flags separate from raw objective-best candidate flags.
- Added regression coverage for the guard rejecting a terminal-worse leader
  candidate.

### Files Changed

- `src/controllers/stackelberg_mpc.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "src\controllers\stackelberg_mpc.py" "src\tests\test_constraints.py"
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_fallback_guard_rejects_terminal_worse_leader src.tests.test_constraints.ConstraintTests.test_stackelberg_leader_evaluates_coarse_and_refined_grid -v
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario low_demand --controllers PROPOSED-STACKELBERG --T-total 360 --output outputs\stackelberg_fallback_guard_low_360_2026_06_19 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-leader-parallel-backend process --stackelberg-leader-parallel-max-workers 8 --stackelberg-inner-backend-when-outer-process serial
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 360 --output outputs\stackelberg_fallback_guard_medium_360_2026_06_19 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-leader-parallel-backend process --stackelberg-leader-parallel-max-workers 8 --stackelberg-inner-backend-when-outer-process serial
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario capacity_drop --controllers PROPOSED-STACKELBERG --T-total 360 --output outputs\stackelberg_fallback_guard_capacity_360_2026_06_19 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-leader-parallel-backend process --stackelberg-leader-parallel-max-workers 8 --stackelberg-inner-backend-when-outer-process serial
```

### Test Result

- `py_compile`: PASS
- Targeted unittest: PASS, 2 tests in `76.264 s`
- 360 s Stackelberg smoke runs: completed for low, medium, and capacity_drop.

### 360 s Smoke Result

| Scenario | No-control TTT | Stackelberg TTT | Improvement | Stack delay | Stack throughput | Stack terminal veh | Mean B sum | Compute sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| low_demand | 32.386 | 31.895 | 1.516% | 1.728 | 7691.9 | 357.7 | 0.150069 | 54.78 |
| medium_demand | 41.011 | 40.452 | 1.363% | 0.052 | 9330.2 | 492.7 | 0.147235 | 64.71 |
| capacity_drop | 117.497 | 116.378 | 0.952% | -28.414 | 9964.1 | 1837.1 | 0.037944 | 65.14 |

Fallback guard diagnostics in these smokes:

| Scenario | intervals | fallback selected rate | PFO selected rate | no-control selected rate | leader rejected rate |
|---|---:|---:|---:|---:|---:|
| low_demand | 2 | 1.000 | 1.000 | 0.000 | 1.000 |
| medium_demand | 2 | 1.000 | 1.000 | 0.000 | 1.000 |
| capacity_drop | 2 | 1.000 | 1.000 | 0.000 | 1.000 |

### Diagnosis / Next Modification

- The guard prevents the short-horizon Stackelberg collapse mode in 360 s low,
  medium, and capacity-drop smokes: Stackelberg now falls back to the PFO
  response instead of selecting the terminal-worse leader-conditioned response.
- This is not final acceptance. The guard increases Stackelberg online cost
  because each Stack decision now also evaluates a PFO follower-only response.
- Next run should repeat the 7200 s six-scenario comparison for
  `NO-CONTROL`, `WU-CD-F`, `PROPOSED-FOLLOWERS-ONLY`, and
  `PROPOSED-STACKELBERG` to verify that the low/medium/capacity failures are
  removed over the full horizon.

## 2026-06-20: Boundary-In Queue TTS Coverage In Leader Objective

### What Was Implemented

- 진단 결과, 최종 Total TTT에는 `boundary_in` queue가 포함되지만 leader
  objective에서는 `leader_boundary_in_queue_penalty`가 진단 전용으로만 남아
  있었습니다.
- `Leader.objective_terms()`에서 boundary-in queue를 TTS-compatible 비용으로
  `leader_total_objective`에 포함하도록 변경했습니다.
  - `follower_ttt` mode: `w_boundary_in * boundary_in_queue_veh * T_c_h`
  - `state_accumulation` mode: 기존 accumulation scale과 동일하게 vehicle-sum
    scale 사용
- `non_convergence_penalty`는 기존 정책대로 진단 전용으로 유지했습니다.
- `04_controller.md`와 `18_follower_tts_objective_alignment.md`의 objective
  coverage 설명을 새 정책에 맞게 갱신했습니다.

### Files Changed

- `src/controllers/leader.py`
- `src/tests/test_constraints.py`
- `src/tests/test_offramp_reattribution.py`
- `src/config/default.yaml`
- `docs/spec/04_controller.md`
- `docs/spec/18_follower_tts_objective_alignment.md`
- `reports/codex_run_report.md`

### Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\leader.py src\tests\test_constraints.py src\tests\test_offramp_reattribution.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_leader_objective_matches_spec_accumulation_form src.tests.test_constraints.ConstraintTests.test_default_leader_objective_uses_follower_ttt_base src.tests.test_constraints.ConstraintTests.test_default_leader_accumulation_penalties_use_control_interval_hours src.tests.test_offramp_reattribution.OffRampReattributionTests.test_leader_boundary_in_cost_enters_total_objective -v
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints -v
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 360 --output outputs\stackelberg_boundary_in_tts_medium_360_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-leader-parallel-backend process --stackelberg-leader-parallel-max-workers 8 --stackelberg-inner-backend-when-outer-process serial
```

### Test Result

- `py_compile`: PASS
- targeted leader/boundary-in objective tests: PASS, 4 tests
- full `src.tests.test_constraints`: PASS, 81 tests in `350.320 s`
- medium 360 s Stackelberg smoke: completed

### Medium 360 s Smoke Result

| Controller | Total TTT | Urban TTT | Freeway TTT | Delay | Throughput veh/h | Terminal veh | Mean B sum | Compute sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 41.011 | 26.842 | 14.169 | 0.610 | 9185.7 | 499.3 | 0.146213 | 0.00 |
| PROPOSED-STACKELBERG | 40.452 | 26.441 | 14.011 | 0.052 | 9330.2 | 492.7 | 0.147235 | 56.63 |

- Total TTT improvement vs no-control: `1.363%`
- Boundary balance non-degradation: FAIL for this 360 s smoke
  (`mean_B_sum` increased by `0.001022`)
- `leader_boundary_in_queue_penalty` was logged and included in selected leader
  objective:
  - step 0: `21.0 veh*h`
  - step 1: `4.8536458333 veh*h`
- In this short smoke, fallback guard selected PFO fallback in both intervals.

### Diagnosis / Next Modification

- The user's diagnosis was correct in the controller-objective sense: some
  boundary-in vehicles were visible as diagnostics but not priced in the leader
  objective, even though final closed-loop Total TTT counts them.
- This change fixes the leader objective coverage mismatch for boundary-in
  queues. It does not by itself prove 7200 s acceptance.
- Next run should repeat the 7200 s comparison after the boundary-in TTS change
  and fallback guard to check whether low/medium/capacity Stackelberg terminal
  accumulation is reduced over the full horizon.

## 2026-06-20: Stackelberg Runtime Guard Scheduling

### What Was Implemented

- Stackelberg fallback candidates are now evaluated before leader candidates.
  The best fallback objective seeds `leader_incumbent_obj`, so leader/follower
  rollouts can terminate early when they are already worse than the PFO/no-control
  incumbent.
- PFO fallback now keeps its own cached previous PFO action. The first interval
  and every configured refresh interval run broad/global search; between refresh
  points the fallback response uses cached-PFO local search.
- Added explicit runtime controls:
  - `mpc.grid_global_refresh_sec`
  - `mpc.grid_reuse_process_pool`
  - `mpc.stackelberg_prefilter_local_top_k`
  - `mpc.stackelberg_fallback_full_refresh_sec`
  - `mpc.stackelberg_fallback_use_cached_pfo`
  - `mpc.stackelberg_reuse_process_pool`
- Added reusable process-pool support to both the shared grid evaluator and the
  Stackelberg leader-candidate outer loop. Diagnostics now report whether reuse
  was enabled and whether an existing pool was reused.
- CLI overrides were added for the new runtime knobs in the four-controller and
  six-controller experiment entrypoints.

### Files Changed

- `src/controllers/stackelberg_mpc.py`
- `src/controllers/grid_parallel.py`
- `src/controllers/distributed_coordinator.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `src/experiments/six_controller_comparison.py`
- `src/tests/test_constraints.py`
- `docs/spec/17_relaxed_quantized_fast_mode.md`
- `reports/codex_run_report.md`

### Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\models\state.py src\controllers\grid_parallel.py src\controllers\distributed_coordinator.py src\controllers\stackelberg_mpc.py src\experiments\all_scenarios_four_controller_comparison.py src\experiments\six_controller_comparison.py src\tests\test_constraints.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_fallback_guard_rejects_terminal_worse_leader src.tests.test_constraints.ConstraintTests.test_stackelberg_leader_evaluates_coarse_and_refined_grid -v
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 360 --output outputs\stackelberg_runtime_guard_medium_360_2026_06_20_v2 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-leader-parallel-backend process --stackelberg-leader-parallel-max-workers 8 --stackelberg-inner-backend-when-outer-process serial
```

### Test Result

- `py_compile`: PASS
- Targeted Stackelberg tests: PASS, 2 tests in `90.403 s`; after adding metadata
  assertions, the coarse/refined grid test also passed in `93.919 s`.
- Medium 360 s Stackelberg smoke: completed.

### Medium 360 s Smoke Result

| Controller | Total TTT | Urban TTT | Freeway TTT | Delay | Throughput veh/h | Terminal veh | Mean B sum | Compute sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 41.011 | 26.842 | 14.169 | 0.610 | 9185.7 | 499.3 | 0.146213 | 0.00 |
| PROPOSED-STACKELBERG | 40.452 | 26.441 | 14.011 | 0.052 | 9330.2 | 492.7 | 0.147235 | 52.87 |

- Total TTT improvement vs no-control: `1.363%`
- Boundary balance non-degradation: FAIL (`mean_B_sum` worsened by `0.001022`)
- Authority validation: PASS (`authority_ok=True`)
- Fallback guard selected PFO fallback in both intervals.

### Runtime Diagnostics

| Diagnostic | Previous medium 360 | New medium 360 |
|---|---:|---:|
| total computation time | 56.63 s | 52.87 s |
| mean computation time / decision | 28.32 s | 26.44 s |
| solver evaluations | 8966 | 7578 |
| leader full evaluations | 17, 18 | 15, 14 |
| PFO fallback grid candidates | 327, 164 | 327, 164 |

- `leader_fallback_incumbent_seed_active=1` in both intervals.
- Interval 1: PFO fallback used global search.
- Interval 2: PFO fallback used cached previous PFO local search
  (`leader_fallback_pfo_cached_previous_used=1`).
- Grid process-pool reuse was enabled and reused an existing pool in both
  intervals.
- Stackelberg leader outer process-pool reuse was enabled; the second interval
  reused the existing leader pool.

### Failed Criteria / Next Modification

- This is not an acceptance pass: the 8% Total TTT improvement criterion is not
  met in this 360 s smoke, and boundary balance is slightly degraded.
- Runtime improved, but the cost is still high because PFO fallback itself still
  evaluates 327 global / 164 local grid candidates. If 7200 s runtime remains too
  high, the next targeted runtime change should keep the 1800 s broad refresh but
  reduce between-refresh PFO local candidates or add a proxy prefilter before
  full local rollout.

## 2026-06-20: Stackelberg Runtime Toggle Diagnosis

### Diagnostic Question

The previous day's medium Stackelberg run was remembered as roughly `20 s` per
decision. The latest smoke was closer to `26 s` per decision, so I checked which
runtime toggles differed.

### Finding

The faster 2026-06-19 run used:

```text
--stackelberg-prefilter-top-k 4
--stackelberg-leader-parallel-backend thread
--stackelberg-leader-parallel-max-workers 4
--grid-parallel-backend process
```

The newer v2 smoke used:

```text
--stackelberg-leader-parallel-backend process
--stackelberg-leader-parallel-max-workers 8
--stackelberg-inner-backend-when-outer-process serial
```

and did not override top-K to 4, so it used the current defaults:

```text
stackelberg_prefilter_top_k = 8
stackelberg_prefilter_local_top_k = 6
```

On this Windows run, `outer thread + inner grid process` was faster than
`outer process + inner serial`, because the latter avoids nested process pools
but pays more serialization/process overhead and forces each follower grid to be
serial inside the outer worker.

### Comparison

| Run | Leader backend | top-K | Compute sec | Per decision | Solver evals | Leader full evals |
|---|---|---:|---:|---:|---:|---:|
| 2026-06-19 medium 7200 | thread | 4 | 890.82 | 22.27 | 40160 | 4 per interval |
| 2026-06-20 v2 medium 360 | process | 8/6 | 52.87 | 26.44 | 7578 | 15, 14 |
| 2026-06-20 thread/top4 medium 360 | thread | 4/4 | 45.42 | 22.71 | 4830 | 9, 10 |

The latest thread/top4 diagnostic command was:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 360 --output outputs\stackelberg_runtime_guard_medium_360_thread_top4_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --stackelberg-prefilter-top-k 4 --stackelberg-prefilter-local-top-k 4 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 4
```

### Diagnostic Result

- Medium 360 s TTT stayed unchanged at `40.452`.
- Computation dropped from `52.87 s` to `45.42 s`.
- Per-decision computation was `24.69 s`, then `20.72 s`.
- Fallback guard still selected PFO fallback in both intervals.
- The first interval remains slower because the fallback PFO path performs global
  search (`327` grid candidates); the second interval uses cached-PFO local
  search (`164` candidates).

### Next Modification

Use `outer thread + top-K 4/4` as the runtime profile for medium/peak screening
when comparing against the 2026-06-19 timing. Keep the broader `8/6` profile
available for sensitivity checks because smaller top-K can change leader search
coverage.

## 2026-06-20: Stackelberg Runtime Profile Default Update

### What Was Implemented

- Changed the default Stackelberg leader outer-loop backend to `thread`.
- Changed the default leader candidate prefilter budget to `4`.
- Changed the local/refined leader prefilter budget to `4` as well, so the
  default runtime profile matches the measured `thread + top-K 4/4` screening
  setup rather than mixing global top-K 4 with local top-K 6.
- Updated the relaxed-quantized runtime spec example to show the same defaults.

### Files Changed

- `src/models/state.py`
- `src/config/default.yaml`
- `docs/spec/17_relaxed_quantized_fast_mode.md`
- `reports/codex_run_report.md`

### Validation Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\models\state.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -c "from src.models.state import ExperimentConfig; cfg=ExperimentConfig.from_file('src/config/default.yaml'); print(cfg.mpc.stackelberg_leader_parallel_backend, cfg.mpc.stackelberg_prefilter_top_k, cfg.mpc.stackelberg_prefilter_local_top_k, cfg.mpc.stackelberg_leader_parallel_max_workers)"
```

### Validation Result

- `py_compile`: PASS
- Default config load printed:

```text
thread 4 4 4
```

### Next Modification

- Future medium/peak Stackelberg screening can omit explicit
  `--stackelberg-prefilter-top-k 4`,
  `--stackelberg-prefilter-local-top-k 4`, and
  `--stackelberg-leader-parallel-backend thread` overrides because these are now
  defaults.

## 2026-06-20: Medium/Peak 7200 s Screening Without Centralized Controller

### What Was Run

- Ran `medium_demand` and `peak_demand` for 7200 s.
- Controllers:
  - `WU-CD-F`
  - `PROPOSED-FOLLOWERS-ONLY`
  - `PROPOSED-STACKELBERG`
- `PROPOSED-CENTRALIZED` was intentionally excluded.
- The driver also ran the no-control baseline for each scenario with the same
  demand, seed, and horizon.
- Stackelberg used the new default runtime profile:
  - `stackelberg_leader_parallel_backend=thread`
  - `stackelberg_prefilter_top_k=4`
  - `stackelberg_prefilter_local_top_k=4`

### Run Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand,peak_demand --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --T-total 7200 --output outputs\no_wu_pfo_stack_medium_peak_7200_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8
```

Output:

```text
outputs\no_wu_pfo_stack_medium_peak_7200_2026_06_20
```

### Summary

| Scenario | Controller | Total TTT | Improvement | Total delay | Compute sec | Throughput veh/h | Terminal veh | Mean B sum | Boundary OK |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| medium_demand | NO-CONTROL | 1943.962 | 0.000% | 1019.342 | 0.00 | 10690.1 | 2469.8 | 0.189289 | baseline |
| medium_demand | WU-CD-F | 1027.697 | 47.134% | 103.076 | 222.57 | 11712.4 | 421.0 | 0.227123 | FAIL |
| medium_demand | PROPOSED-FOLLOWERS-ONLY | 1000.610 | 48.527% | 75.990 | 317.44 | 11720.0 | 418.3 | 0.155851 | PASS |
| medium_demand | PROPOSED-STACKELBERG | 1000.610 | 48.527% | 75.990 | 925.63 | 11720.0 | 418.3 | 0.155851 | PASS |
| peak_demand | NO-CONTROL | 11659.562 | 0.000% | 10515.542 | 0.00 | 7936.1 | 13488.0 | 0.082207 | baseline |
| peak_demand | WU-CD-F | 7370.486 | 36.786% | 6226.466 | 219.56 | 10262.4 | 8832.8 | 0.165210 | FAIL |
| peak_demand | PROPOSED-FOLLOWERS-ONLY | 3773.909 | 67.632% | 2629.889 | 380.20 | 12894.7 | 3565.7 | 0.159081 | FAIL |
| peak_demand | PROPOSED-STACKELBERG | 3773.909 | 67.632% | 2629.889 | 1049.92 | 12894.7 | 3565.7 | 0.159081 | FAIL |

### Stackelberg Diagnostics

| Scenario | intervals | fallback selected | PFO fallback selected | leader selected | avg leader full eval | full eval min/max | early term sum | top-K | leader backend |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| medium_demand | 40 | 40 | 40 | 0 | 10.62 | 9 / 12 | 44080 | 4/4 | thread |
| peak_demand | 40 | 40 | 40 | 0 | 11.62 | 9 / 12 | 32552 | 4/4 | thread |

PFO fallback/grid refresh diagnostics:

| Scenario | leader global refresh intervals | PFO global refresh intervals | cached PFO intervals | avg selected grid candidates | grid min/max |
|---|---:|---:|---:|---:|---:|
| medium_demand | 4 | 4 | 36 | 210.42 | 156 / 442 |
| peak_demand | 4 | 4 | 36 | 251.25 | 168 / 459 |

### Interpretation

- The Stackelberg collapse mode is prevented: both medium and peak select the PFO
  fallback in every control interval, so `PROPOSED-STACKELBERG` exactly matches
  `PROPOSED-FOLLOWERS-ONLY` on TTT, delay, throughput, terminal vehicles, and
  boundary metrics.
- The leader-conditioned Stackelberg candidates still do not beat the PFO
  fallback under the guard. This is safer than the previous failed Stackelberg
  results, but it means the leader layer is not yet adding performance over PFO.
- Computation remains the main cost issue. P-Stack took `925.63 s` for medium
  and `1049.92 s` for peak, roughly `23.14 s` and `26.25 s` per decision.
- Boundary acceptance is mixed:
  - medium PFO/P-Stack pass boundary non-degradation;
  - peak PFO/P-Stack improve TTT strongly but worsen mean boundary balance
    relative to no-control.

### Failed Criteria / Next Modification

- `WU-CD-F` fails boundary non-degradation in both medium and peak.
- `PROPOSED-FOLLOWERS-ONLY` and guarded `PROPOSED-STACKELBERG` pass the main TTT
  criterion in both scenarios, but fail boundary non-degradation in peak.
- Since P-Stack always falls back to PFO, the next performance question is not
  whether Stackelberg is unsafe; it is why the leader-conditioned candidate set
  cannot beat the PFO incumbent. The next targeted diagnosis should compare
  rejected leader candidates against the PFO fallback objective, terminal proxy,
  and boundary balance in the peak intervals where the leader has the strongest
  possible advantage.

## 2026-06-20: Peak 7200 s Stackelberg Run With Fallback Disabled

### Implementation

- Added diagnostic-only runtime switch `mpc.stackelberg_enable_fallback`.
- Added CLI flag `--disable-stackelberg-fallback` to both experiment drivers.
- Default behavior remains unchanged: fallback is enabled unless the flag is
  explicitly passed.

Changed files:

- `src/models/state.py`
- `src/config/default.yaml`
- `src/controllers/stackelberg_mpc.py`
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `src/experiments/six_controller_comparison.py`

Validation:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\stackelberg_mpc.py src\models\state.py src\experiments\all_scenarios_four_controller_comparison.py src\experiments\six_controller_comparison.py
```

Result: PASS.

### Run Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\pstack_no_fallback_peak_7200_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback
```

Output:

```text
outputs\pstack_no_fallback_peak_7200_2026_06_20
```

### Summary

| Controller / Mode | Total TTT | Improvement vs no-control | Total delay | Urban TTT | Freeway TTT | Throughput veh/h | Terminal veh | Compute sec | Solver evals | Mean B sum |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 11659.562 | baseline | 10515.542 | 6759.336 | 4900.226 | 7936.1 | 13488.0 | 0.00 | 0 | 0.082207 |
| Previous PFO | 3773.909 | 67.632% | 2629.889 | 2463.602 | 1310.307 | 12894.7 | 3565.7 | 380.20 | 10570 | 0.159081 |
| Previous guarded P-Stack | 3773.909 | 67.632% | 2629.889 | 2463.602 | 1310.307 | 12894.7 | 3565.7 | 1049.92 | 121904 | 0.159081 |
| P-Stack fallback disabled | 10552.197 | 9.497% | 9408.178 | 10253.681 | 298.516 | 9583.2 | 10189.4 | 474.32 | 7661 | 0.009483 |

### Stackelberg Diagnostics

| Mode | intervals | fallback evals | fallback selected | PFO fallback selected | coarse selected | refined selected | avg full leader eval | early term sum | avg N_P_star | avg N_UF_star |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Previous guarded P-Stack | 40 | 80 | 40 | 40 | 0 | 0 | 11.625 | 32552 | n/a | n/a |
| P-Stack fallback disabled | 40 | 0 | 0 | 0 | 29 | 11 | 8.150 | 0 | 490.052 | 5137.026 |

### Interpretation

- The exact equality between previous P-Stack and PFO was caused by the fallback
  guard: the previous peak run selected PFO fallback in all 40 control intervals.
- With fallback disabled, P-Stack no longer matches PFO. It selects leader
  candidates in every interval, with `N_UF_star` averaging `5137.026 veh/h`.
- The leader-only solution strongly protects the freeway (`freeway_ttt=298.516`)
  but pushes cost into the urban side (`urban_ttt=10253.681`), so total TTT is
  much worse than PFO despite still beating no-control by `9.497%`.
- Computation drops from `1049.92 s` to `474.32 s` because the expensive PFO
  fallback response is not evaluated; however, this is not a viable controller
  performance profile.

### Failed Criteria / Next Modification

- Fallback-disabled P-Stack fails the practical performance comparison against
  PFO and guarded P-Stack.
- The next diagnosis should focus on the leader objective/allocation coupling:
  leader-conditioned actions appear biased toward freeway clearance and are not
  internalizing the urban TTT increase enough. Candidate generation is active;
  the issue is more likely objective weighting/coverage, target binding, or the
  allocation module's response to high `N_UF_star` than fallback mechanics alone.

## 2026-06-20: Leader MPC Future-State Penalty Evaluation

### Implementation

- Changed Stackelberg leader `follower_ttt` evaluation so the base objective
  remains the follower/Nash response objective, but leader target, boundary-in,
  and density penalties are evaluated on future MPC rollout states instead of
  repeated copies of the current state.
- Added diagnostics that distinguish:
  - `leader_rollout_prediction_used`
  - `leader_follower_response_objective_used`
  - `leader_rollout_objective_base_used`
- Updated the Stackelberg unit test to verify that default `follower_ttt` mode
  uses future penalty states while keeping the follower response objective as
  the base.

Changed files:

- `src/controllers/stackelberg_mpc.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Validation

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\stackelberg_mpc.py src\models\state.py src\experiments\all_scenarios_four_controller_comparison.py src\experiments\six_controller_comparison.py src\tests\test_constraints.py
```

Result: PASS.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_prediction_uses_coupling_module src.tests.test_constraints.ConstraintTests.test_stackelberg_default_objective_uses_follower_response_with_future_penalty_states src.tests.test_constraints.ConstraintTests.test_default_leader_objective_uses_follower_ttt_base src.tests.test_offramp_reattribution.OffRampReattributionTests.test_leader_boundary_in_cost_enters_total_objective -v
```

Result: PASS (`4` tests).

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_fallback_guard_rejects_terminal_worse_leader src.tests.test_constraints.ConstraintTests.test_stackelberg_leader_evaluates_coarse_and_refined_grid src.tests.test_constraints.ConstraintTests.test_stackelberg_prediction_uses_coupling_module src.tests.test_constraints.ConstraintTests.test_stackelberg_default_objective_uses_follower_response_with_future_penalty_states src.tests.test_offramp_reattribution.OffRampReattributionTests.test_leader_boundary_in_cost_enters_total_objective -v
```

Result: PASS (`5` tests, `83.905 s`).

### Smoke Run

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --controllers PROPOSED-STACKELBERG --T-total 360 --output outputs\pstack_future_rollout_penalty_peak_360_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback
```

Result:

| Scenario | Controller | Total TTT | Improvement | Urban TTT | Freeway TTT | Compute sec | Mean B sum |
|---|---|---:|---:|---:|---:|---:|---:|
| peak_demand | NO-CONTROL | 49.745 | baseline | n/a | n/a | 0.00 | 0.144364 |
| peak_demand | PROPOSED-STACKELBERG | 57.989 | -16.573% | 44.576 | 13.414 | 26.96 | 0.044296 |

Diagnostics confirmed the intended objective structure:

| Diagnostic | Mean |
|---|---:|
| `leader_rollout_prediction_used` | 1.000 |
| `leader_follower_response_objective_used` | 1.000 |
| `leader_rollout_objective_base_used` | 0.000 |
| `leader_boundary_in_queue_penalty` | 44.410 |
| `leader_selected_N_UF_star` | 5812.500 |

### 7200 s Peak Run

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\pstack_future_rollout_penalty_peak_7200_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback
```

Output:

```text
outputs\pstack_future_rollout_penalty_peak_7200_2026_06_20
```

Summary:

| Mode | Total TTT | Improvement vs no-control | Total delay | Urban TTT | Freeway TTT | Throughput veh/h | Terminal veh | Compute sec | Solver evals | Mean B sum |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 11659.562 | baseline | 10515.542 | 6759.336 | 4900.226 | 7936.1 | 13488.0 | 0.00 | 0 | 0.082207 |
| Previous PFO | 3773.909 | 67.632% | 2629.889 | 2463.602 | 1310.307 | 12894.7 | 3565.7 | 380.20 | 10570 | 0.159081 |
| Old P-Stack fallback disabled | 10552.197 | 9.497% | 9408.178 | 10253.681 | 298.516 | 9583.2 | 10189.4 | 474.32 | 7661 | 0.009483 |
| Future-penalty P-Stack fallback disabled | 10581.044 | 9.250% | 9437.024 | 10275.913 | 305.131 | 9671.6 | 10013.2 | 491.13 | 8923 | 0.008058 |

Selected-objective diagnostics:

| Mode | rollout used | follower base used | rollout base used | avg objective base | avg boundary penalty | avg target penalty | avg N_UF_star | avg terminal urban proxy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Old P-Stack fallback disabled | 0.000 | 1.000 | 0.000 | 1345.632 | 349.998 | 60.225 | 5137.026 | 6182.575 |
| Future-penalty P-Stack fallback disabled | 1.000 | 1.000 | 0.000 | 1241.874 | 396.828 | 66.916 | 5426.789 | 6182.728 |

### Interpretation

- The implementation now makes leader penalties MPC-style: they are evaluated
  on future rollout states rather than current-state copies.
- This did increase the boundary-in penalty (`349.998 -> 396.828`) and correctly
  marks rollout state usage in diagnostics.
- It did not fix the leader-only performance problem. Peak Total TTT changed
  from `10552.197` to `10581.044`, still far worse than PFO (`3773.909`).
- The selected leader `N_UF_star` increased (`5137.026 -> 5426.789`), which
  means the remaining issue is not simply missing future penalty states. The
  leader/allocation objective still prefers high ramp discharge / freeway
  clearance under fallback-disabled selection.

### Failed Criteria / Next Modification

- Future-state penalties are structurally correct but not sufficient.
- The next diagnosis should compare candidate-level `N_UF_star` vs predicted
  urban terminal accumulation and realized urban TTT. If higher `N_UF_star`
  keeps looking cheaper, the likely fix is a leader feasibility/constraint or
  allocation target reformulation, not more boundary queue accounting.

## 2026-06-20: Stackelberg Leader N_P Grid Expansion

### Implementation

- Broadened the Stackelberg leader `N_P_star` grid from the tight calibrated
  band `0.90~1.05 * N_P_crit` to `0.40~1.35 * N_P_crit`.
  - With the current `N_P_crit=509.449 veh`, the default grid range is now
    `203.780~687.756 veh`.
  - This covers the previously observed peak PFO protected-accumulation band
    of roughly `244~592 veh`.
- Aligned the dataclass default `leader.N_P_star_range` with
  `src/config/default.yaml` (`[0.0, 850.0]`) so direct `ExperimentConfig()`
  use does not silently cap the leader grid at `500 veh`.
- Kept movement-reachability bounds as diagnostics and candidate anchors rather
  than hard clipping the leader `N_P_star` setpoint range.
- Added current `protected_accumulation`, movement lower/upper anchors, and
  `N_P_crit` anchors to both coarse and refined leader candidate generation.
- Added a regression test that the default leader `N_P` candidate bounds cover
  the observed PFO band.

Changed files:

- `src/config/default.yaml`
- `src/controllers/leader.py`
- `src/models/state.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Validation

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\leader.py src\controllers\stackelberg_mpc.py src\models\state.py src\tests\test_constraints.py
```

Result: PASS.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_leader_candidate_budget_covers_extremes_and_previous_action src.tests.test_constraints.ConstraintTests.test_leader_np_candidates_use_calibrated_crit_band src.tests.test_constraints.ConstraintTests.test_default_leader_np_grid_covers_observed_pfo_band src.tests.test_constraints.ConstraintTests.test_stackelberg_fallback_guard_rejects_terminal_worse_leader src.tests.test_constraints.ConstraintTests.test_stackelberg_default_objective_uses_follower_response_with_future_penalty_states -v
```

Result: PASS (`5` tests).

Default-grid diagnostic:

```text
N_P_bounds 203.780 687.756
movement_bounds 96.000 2496.000
candidate_count 50
N_P_candidates [203.780, 284.442, 365.105, 445.768, 509.449, 526.430, 607.093, 687.756]
```

### Smoke Run

180 s baseline and proposed-controller command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --controllers PROPOSED-STACKELBERG --T-total 360 --output outputs\pstack_expanded_np_grid_peak_360_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback
```

| Scenario | Controller | Total TTT | Improvement | Urban TTT | Freeway TTT | Compute sec | Mean B sum |
|---|---|---:|---:|---:|---:|---:|---:|
| peak_demand | NO-CONTROL | 49.745 | baseline | 31.886 | 17.859 | 0.00 | 0.144364 |
| peak_demand | PROPOSED-STACKELBERG | 58.356 | -17.310% | 45.106 | 13.250 | 36.22 | 0.044643 |

Smoke leader diagnostics:

| Diagnostic | Mean | Min | Max |
|---|---:|---:|---:|
| `diag_leader_np_bound_lower` | 203.780 | 203.780 | 203.780 |
| `diag_leader_np_bound_upper` | 687.756 | 687.756 | 687.756 |
| `N_P_star` | 211.342 | 203.780 | 218.904 |
| `N_UF_star` | 6000.000 | 6000.000 | 6000.000 |
| `diag_leader_candidate_prefilter_top_k` | 4.000 | 4.000 | 4.000 |
| `diag_leader_candidate_full_evaluated_count` | 8.500 | 8.000 | 9.000 |

### 7200 s Peak Run

Baseline and proposed-controller command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\pstack_expanded_np_grid_peak_7200_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback
```

| Scenario | Controller | Total TTT | Improvement | Total delay | Urban TTT | Freeway TTT | Throughput veh/h | Terminal veh | Compute sec | Solver evals | Mean B sum |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| peak_demand | NO-CONTROL | 11659.562 | baseline | 10515.542 | 6759.336 | 4900.226 | 7936.1 | 13488.0 | 0.00 | 0 | 0.082207 |
| peak_demand | PROPOSED-STACKELBERG | 10554.805 | 9.475% | 9410.786 | 10245.342 | 309.464 | 9704.5 | 9946.9 | 694.52 | 8450 | 0.011982 |

Leader diagnostics:

| Diagnostic | Mean | Min | Max |
|---|---:|---:|---:|
| `N_P_star` | 204.741 | 203.780 | 211.808 |
| `N_UF_star` | 5659.936 | 5283.953 | 6000.000 |
| `diag_leader_np_bound_lower` | 203.780 | 203.780 | 203.780 |
| `diag_leader_np_bound_upper` | 687.756 | 687.756 | 687.756 |
| `diag_leader_nuf_bound_lower` | 2735.532 | 1523.888 | 4102.101 |
| `diag_leader_nuf_bound_upper` | 6000.000 | 6000.000 | 6000.000 |
| `diag_leader_candidate_prefilter_top_k` | 4.000 | 4.000 | 4.000 |
| `diag_leader_candidate_full_evaluated_count` | 8.150 | 8.000 | 10.000 |
| `diag_leader_boundary_in_queue_penalty` | 390.077 | 36.546 | 822.522 |
| `diag_leader_target_penalty` | 70.143 | 0.000 | 172.008 |
| `diag_leader_follower_ttt_base` | 1233.342 | 94.047 | 2625.081 |

### Interpretation

- The leader now definitely searches the PFO-like low protected-accumulation
  region. In both smoke and 7200 s peak runs, it selected the new lower band
  rather than being trapped near `N_P_crit`.
- This rules out a narrow `N_P` grid as the primary remaining cause of the
  P-Stack vs PFO gap.
- The remaining failure mode is sharper: even with low `N_P_star`, the leader
  still selects very high `N_UF_star` (`mean 5659.936 veh/h`), producing low
  freeway TTT but very high urban TTT.
- Boundary balance improved relative to no-control (`B_sum 0.082207 ->
  0.011982`), but Total TTT is still far worse than the previous PFO peak
  result (`3773.909`). This is not an acceptance pass for the proposed
  Stackelberg controller.

### Failed Criteria / Next Modification

- Main Total TTT improvement over no-control is positive but still fails the
  research goal because P-Stack remains much worse than PFO under the same
  scenario class.
- The next diagnosis should move from `N_P` feasibility to `N_UF` candidate
  and objective coverage:
  - compare candidate-level `N_UF_star` vs predicted urban queue/terminal
    accumulation,
  - check whether low/mid `N_UF_star` candidates are filtered out by cheap
    proxy top-K before full follower evaluation,
  - inspect whether follower response under low `N_UF_star` is over-penalized
    by ramp/on-ramp queue terms or under-credited for urban throughput.

## 2026-06-20: Stackelberg N_UF / Global TTT Mismatch Diagnosis

### Diagnostic Context

The user questioned whether selecting high `N_UF_star` while closed-loop global
Total TTT degrades is itself evidence of a coding/objective problem.

I inspected the Stackelberg evaluation path:

- `PROPOSED-STACKELBERG` mutates `mpc.follower_solver_mode` to `distributed`.
- Leader coarse/refined candidates are first cheap-prefiltered.
- Full candidate evaluation calls the distributed follower.
- The leader base objective then uses the follower response objective
  (`nash.objective_value`) and adds leader penalties on predicted states.
- In the distributed Stackelberg follower path, the leader-conditioned follower
  did not reuse the shared structured-grid search primitives used by the
  follower-only path. It used a reduced leader-conditioned candidate set:
  - ramp metering projected to `leader.N_UF_star`,
  - green around allocation-derived setpoints (`±6 s`),
  - offset around the local center (`±5 s`),
  - no full shared RM/green/offset/VSL grid under the leader constraints.

### Candidate Sweep Evidence

I ran an in-memory diagnostic on the initial `peak_demand` state using the same
important experiment settings:

```text
follower_solver_mode = distributed
relaxed_quantized_controls = true
max_nash_iter = 1
horizon_steps = 3
freeway_prediction_horizon_steps = 3
grid_parallel_backend = serial for diagnostic stability
```

The diagnostic evaluated every coarse leader candidate with full distributed
follower evaluation, not only the top-K prefilter candidates.

Top result by full leader objective:

| idx | N_P_star | N_UF_star | prefilter | full objective | follower rollout TTT | rollout urban | rollout freeway | terminal rollout veh |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 203.780 | 6000.000 | true | 127.647 | 83.680 | 66.447 | 17.233 | 777.914 |

Best full-evaluated objective by `N_UF_star` group:

| N_UF_star | best N_P_star | full objective | rollout TTT | rollout urban | rollout freeway | prefilter selected |
|---:|---:|---:|---:|---:|---:|---:|
| 1862.000 | 284.442 | 169.604 | 100.078 | 86.213 | 13.864 | false |
| 2482.667 | 203.780 | 172.520 | 101.087 | 86.977 | 14.110 | false |
| 2551.667 | 284.442 | 164.703 | 96.843 | 83.052 | 13.792 | false |
| 3103.333 | 203.780 | 144.911 | 91.083 | 76.058 | 15.025 | false |
| 3241.333 | 284.442 | 165.927 | 94.592 | 79.706 | 14.886 | false |
| 3931.000 | 284.442 | 151.245 | 91.699 | 75.737 | 15.962 | false |
| 4620.667 | 203.780 | 155.301 | 96.157 | 81.629 | 14.527 | true |
| 5310.333 | 203.780 | 136.961 | 87.120 | 70.824 | 16.296 | true |
| 6000.000 | 203.780 | 127.647 | 83.680 | 66.447 | 17.233 | true |

### Interpretation

- This is not merely a top-K prefilter bug. At the initial peak state, the full
  distributed follower horizon objective itself prefers `N_UF_star=6000`.
- The controller is therefore not minimizing the eventual 7200 s global Total
  TTT. It is minimizing a short MPC-horizon response objective that currently
  views high ramp discharge as beneficial.
- The remaining code-level mismatch is likely the Stackelberg follower response
  set, not only the scalar leader objective:
  - The follower-only path uses the broader shared structured grid and can find
    a much better closed-loop policy.
  - P-Stack's leader-conditioned follower uses a much narrower local candidate
    set around allocation/projection centers.
  - Therefore the leader may never evaluate a comparable control combination
    even if the abstract leader variables could represent it.

### Next Modification

The next fix should make the Stackelberg follower response comparable to the
follower-only search space without using the follower-only selected solution as
truth:

1. For each leader candidate, build follower candidates from the same
   shared structured-grid primitives.
2. Project only the parts that must obey leader constraints:
   - RM sum to `N_UF_star`,
   - green/allocation around the leader `N_P_star` allocation plan.
3. Keep the full green/offset/VSL neighborhood and sensitivity candidates
   available under those projections.
4. Then evaluate projected candidates with the same rollout TTT objective.

This tests the critical question directly:

```text
Can the leader choose a variable pair whose induced follower feasible set
contains a PFO-like good solution?
```

If yes, P-Stack should stop being worse than PFO for coding reasons. If no, the
Stackelberg formulation/leader variables are over-constraining the problem and
need reformulation rather than another penalty tweak.

## 2026-06-20: Leader-Conditioned Shared Structured Follower Search

### Implementation

- Changed the Stackelberg distributed follower response so leader-conditioned
  follower candidates are generated from the shared structured-grid primitives
  rather than the former narrow hand-written leader-local candidate set.
- This does not run `PROPOSED-FOLLOWERS-ONLY` first and does not inject a PFO
  selected control as a truth solution.
- Each shared candidate is projected into the Stackelberg leader feasible set:
  - `N_P_star` and `N_UF_star` are copied from the leader action,
  - ramp-metering rates are projected so their sum tracks `leader.N_UF_star`,
    preserving the candidate's ramp ratio as much as possible,
  - inflow/outflow allocation is replaced by the allocation-module result for
    the leader `N_P_star`,
  - green times are clipped only to the allocation phase band so the shared
    grid/sensitivity direction remains visible under the allocation constraint,
  - offset and VSL candidates remain available subject to the existing actuator
    repair and rollout feasibility checks.
- Replaced the former one-stage Stackelberg follower refinement with the same
  four-stage structure used by the follower-only grid search:
  - coarse shared grid,
  - finite-difference sensitivity probes,
  - sensitivity-direction candidates,
  - fine local shared grid.

Changed files:

- `src/controllers/distributed_coordinator.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Validation

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\distributed_coordinator.py src\controllers\stackelberg_mpc.py src\controllers\leader.py src\models\state.py src\tests\test_constraints.py
```

Result: PASS.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_distributed_coordinator_returns_per_agent_diagnostics src.tests.test_constraints.ConstraintTests.test_leader_conditioned_grid_projects_metering_target src.tests.test_constraints.ConstraintTests.test_default_leader_np_grid_covers_observed_pfo_band src.tests.test_constraints.ConstraintTests.test_stackelberg_fallback_guard_rejects_terminal_worse_leader src.tests.test_constraints.ConstraintTests.test_stackelberg_default_objective_uses_follower_response_with_future_penalty_states -v
```

Result: PASS (`5` tests, `11.621 s`).

### Smoke Run

Baseline and proposed-controller command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --controllers PROPOSED-STACKELBERG --T-total 180 --output outputs\pstack_shared_structured_leader_followers_peak_180_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback
```

| Scenario | Controller | Total TTT | Improvement | Urban TTT | Freeway TTT | Compute sec | Mean B sum |
|---|---|---:|---:|---:|---:|---:|---:|
| peak_demand | NO-CONTROL | 20.181 | baseline | 12.730 | 7.451 | 0.00 | 0.111382 |
| peak_demand | PROPOSED-STACKELBERG | 21.165 | -4.876% | 14.546 | 6.619 | 56.29 | 0.097095 |

Follower-search diagnostics from the smoke run:

| Diagnostic | Mean | Min | Max |
|---|---:|---:|---:|
| `distributed_grid_parallel_stages` | 4.000 | 4.000 | 4.000 |
| `distributed_grid_full_search_active` | 1.000 | 1.000 | 1.000 |
| `distributed_grid_leader_conditioned` | 1.000 | 1.000 | 1.000 |
| `distributed_grid_stage1_candidates` | 92.000 | 92.000 | 92.000 |
| `distributed_grid_stage2_candidates` | 47.000 | 47.000 | 47.000 |
| `distributed_grid_sensitivity_probe_candidates` | 25.000 | 25.000 | 25.000 |
| `distributed_grid_sensitivity_direction_candidates` | 0.000 | 0.000 | 0.000 |
| `distributed_grid_total_candidates` | 164.000 | 164.000 | 164.000 |
| `leader_candidate_full_evaluated_count` | 10.000 | 10.000 | 10.000 |
| `leader_selected_N_UF_star` | 6000.000 | 6000.000 | 6000.000 |
| `leader_selected_N_P_star` | 284.442 | 284.442 | 284.442 |

360 s follow-up smoke command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --controllers PROPOSED-STACKELBERG --T-total 360 --output outputs\pstack_shared_structured_leader_followers_peak_360_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback
```

| Scenario | Controller | Total TTT | Improvement | Urban TTT | Freeway TTT | Compute sec | Mean B sum |
|---|---|---:|---:|---:|---:|---:|---:|
| peak_demand | NO-CONTROL | 49.745 | baseline | 31.886 | 17.859 | 0.00 | 0.144364 |
| peak_demand | PROPOSED-STACKELBERG | 56.811 | -14.204% | 43.051 | 13.759 | 87.20 | 0.043516 |

360 s follower-search diagnostics:

| Diagnostic | Mean | Min | Max |
|---|---:|---:|---:|
| `distributed_grid_parallel_stages` | 4.000 | 4.000 | 4.000 |
| `distributed_grid_full_search_active` | 1.000 | 1.000 | 1.000 |
| `distributed_grid_stage1_candidates` | 73.000 | 47.000 | 99.000 |
| `distributed_grid_stage2_candidates` | 47.000 | 46.000 | 48.000 |
| `distributed_grid_sensitivity_probe_candidates` | 25.000 | 25.000 | 25.000 |
| `distributed_grid_sensitivity_direction_candidates` | 0.000 | 0.000 | 0.000 |
| `distributed_grid_total_candidates` | 145.000 | 120.000 | 170.000 |
| `leader_candidate_full_evaluated_count` | 9.000 | 8.000 | 10.000 |
| `leader_selected_N_UF_star` | 6000.000 | 6000.000 | 6000.000 |
| `leader_selected_N_P_star` | 213.862 | 203.780 | 223.945 |

### Interpretation

- The implementation now answers the user's concern: Stackelberg does not reuse
  a PFO-selected solution as truth; it reuses only the shared search basis, then
  applies leader allocation/RM constraints to every candidate.
- The allocation module still has authority because every projected candidate
  receives the allocation-module flow map for the tested leader action.
- The former follower candidate-space mismatch is reduced: Stackelberg follower
  search now evaluates coarse, probe, direction, and fine stages under leader
  constraints.
- The 180 s and 360 s smoke runs still selected `N_UF_star=6000` and did not
  improve Total TTT. These short runs are not acceptance runs, but they show the
  high-`N_UF` bias is not fixed solely by broadening the follower candidate
  generator.
- Sensitivity-direction candidates were `0` in the smoke because the probe
  stage did not find a finite-difference descent direction after projection.
  This is diagnostically useful: the probe stage is active, but the projected
  local direction set may still be too constrained or too myopic.

### Failed Criteria / Next Modification

- Acceptance is still FAIL. Only 180 s and 360 s smokes were run after this
  structural change, and both were worse than no-control.
- Next diagnostic should compare leader-conditioned projected candidates against
  follower-only candidates at the same state to see which dimensions collapse
  under allocation projection, especially green phase bands and RM projection.

## 2026-06-20: Stackelberg Top-K Prefilter vs Search-Space Diagnosis

The user asked whether the remaining PFO-vs-Stackelberg gap is caused by the
runtime-lightweight `top-K` leader prefilter or by the underlying Stackelberg
leader/follower search itself.

### Simulation / Diagnostic Commands

Full-evaluation 180 s smoke with Stackelberg fallback disabled and leader
prefilter disabled:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --controllers PROPOSED-STACKELBERG --T-total 180 --output outputs\pstack_no_prefilter_peak_180_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend process --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback --stackelberg-prefilter-top-k 0 --stackelberg-prefilter-local-top-k 0
```

Targeted one-decision replay diagnostic:

- Replayed the saved fallback-disabled peak Stackelberg control sequence from
  `outputs/pstack_expanded_np_grid_peak_7200_2026_06_20` up to control step 9.
- Re-evaluated the same reproduced state with current code under:
  - default lightweight `top-K=4`
  - no prefilter, `top-K=0`
- Fallback remained disabled in both cases.

### Results

180 s full-evaluation smoke:

| Scenario | Controller | Total TTT | Improvement | Mean B sum | Interpretation |
|---|---|---:|---:|---:|---|
| peak_demand | NO-CONTROL | 20.181 | baseline | 0.111382 | baseline |
| peak_demand | P-Stack no-prefilter | 21.165 | -4.876% | 0.097095 | same TTT as top-K smoke |

Targeted step-9 replay:

| Mode | Full leader evals | Selected `N_UF_star` | Leader objective | Runtime |
|---|---:|---:|---:|---:|
| `top-K=4` | 8 | 5550.058 | 190.907390 | 10.902 s |
| `top-K=0` | 74 | 5400.077 | 186.090962 | 101.682 s |

Reference from the previous PFO peak 7200 s control log at the same step:

| Quantity | Value |
|---|---:|
| PFO actual RM sum | 4418.750 veh/h |
| Stack top-K selected `N_UF_star` | 5550.058 veh/h |
| Stack no-prefilter selected `N_UF_star` | 5400.077 veh/h |

### Interpretation

- The runtime-lightweight prefilter is part of the problem: disabling it at the
  reproduced step improves the selected leader objective and moves `N_UF_star`
  downward by about `150 veh/h`.
- But prefiltering is not the whole problem. Even with all 74 leader candidates
  fully evaluated, Stackelberg still selects a high-`N_UF` target around
  `5400 veh/h`, far above the PFO actual RM sum around `4419 veh/h`.
- Therefore the current evidence points to both:
  1. `top-K` can worsen the leader choice.
  2. The full Stackelberg leader/follower objective/search still prefers too much
     freeway release relative to the PFO direct-control solution.
- A separate implementation issue is visible: the returned control's actual RM
  sum can remain above the selected `N_UF_star` after Nash relaxation/merge. The
  step-9 replay returned actual RM sum `5700.231 veh/h` while the selected
  leader target was `5400.077 veh/h`. This means leader target selection and
  plant-applied RM are not perfectly aligned under the current relaxed
  follower merge path.

### Next Modification

- First, make the leader-conditioned follower output enforce the selected
  `N_UF_star` after Nash relaxation/merge, or explicitly diagnose the intended
  relaxation semantics.
- Then rerun the targeted step-9 comparison to determine whether low/mid
  `N_UF` candidates remain unattractive when the plant-applied RM actually
  matches the evaluated leader target.

## 2026-06-20: PFO vs Stackelberg Player Region / Objective Coverage Check

The user asked whether the Stackelberg failure could be caused by PFO players
and Stackelberg follower players looking at different TTT regions.

### Code Inspection

- `DistributedCoordinator.__init__()` calls the same `build_agent_specs(cfg)`
  for both leaderless PFO and Stackelberg.
- The resulting player set is independent of `leader`:
  - urban agents: signals `A, B, C, D, F`
  - freeway agents: every segment of `FW_E` and `FW_W`
- Node `E` remains uncontrolled, but its queues/storage are included in
  follower TTS diagnostics through `uncontrolled_node_*` terms.
- The final distributed response objective is computed by the same
  `_response_tts_objective()` function for both PFO and Stackelberg. This
  objective includes:
  - urban vehicles from movement queues and in-transit storage,
  - uncontrolled-node vehicles,
  - ramp queues,
  - freeway segment vehicles,
  - off-ramp storage,
  - mainline origin queue,
  - terminal proxy vehicles and spillback penalties.

### Log Coverage Check

Selected rows from the previous peak 7200 s logs:

| Step | Controller | Urban agents | Freeway agents | E covered | Allocation used | RM sum | Response objective | Current vehicles | Terminal proxy | Movement queue projection |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | PFO | 5 | 8 | 1 | 0 | 6000.000 | 106.774 | 284.000 | 1139.653 | 140.000 |
| 0 | Stack | 5 | 8 | 1 | 1 | 6000.000 | 117.756 | 284.000 | 1286.083 | 140.000 |
| 9 | PFO | 5 | 8 | 1 | 0 | 4418.750 | 220.625 | 857.983 | 1841.576 | 309.097 |
| 9 | Stack | 5 | 8 | 1 | 1 | 5700.231 | 440.541 | 2319.252 | 3554.622 | 2051.485 |
| 20 | PFO | 5 | 8 | 1 | 0 | 3806.641 | 363.454 | 1773.957 | 2885.844 | 615.250 |
| 20 | Stack | 5 | 8 | 1 | 1 | 5283.953 | 1330.419 | 5621.813 | 6744.919 | 5341.201 |
| 39 | PFO | 5 | 8 | 1 | 0 | 4500.042 | 598.454 | 3541.478 | 4248.482 | 2491.059 |
| 39 | Stack | 5 | 8 | 1 | 1 | 5675.347 | 2625.081 | 9745.649 | 10605.867 | 9553.394 |

### Interpretation

- The available evidence does not support a missing-player-region explanation:
  PFO and Stackelberg both report the same player counts, and uncontrolled node
  `E` coverage is active in both.
- Stackelberg is not blind to the urban queue buildup. Its own response
  objective becomes much worse as urban movement queues grow.
- However, the optimization problems are still not equivalent:
  - PFO has no allocation module and searches direct control variables.
  - Stackelberg conditions follower candidates on `N_P_star`, `N_UF_star`, and
    the allocation module, so green/allocation/RM feasible actions are projected
    differently.
  - The leader's default `follower_ttt` mode uses the follower response
    objective as the base, while future rollout states are used for penalties.
    It is therefore not pure full-rollout global TTT minimization at the leader
    outer loop.
  - The previous step-9 diagnostic showed the selected `N_UF_star` can differ
    from the final plant-applied RM sum after Nash relaxation/merge.

### Next Modification

- First fix or explicitly account for the selected-`N_UF_star` vs final-RM-sum
  mismatch in the leader-conditioned follower path.
- Then run a same-state candidate-level table with columns:
  `N_UF_star`, plant-applied RM sum, rollout TTT, response objective,
  terminal urban vehicles, movement queue projection, and allocation residual.
  This will separate objective-proxy error from feasible-set/projection error.

## 2026-06-20: Stackelberg Step-9 Same-State Candidate / Allocation Diagnosis

The user asked to analyze three suspected causes of the Stackelberg-vs-PFO
gap:

1. selected `N_UF_star` vs final applied ramp-metering sum mismatch,
2. same-state candidate-level `N_UF` objective table,
3. allocation on/off style diagnostic.

### Files / Artifacts

- Added diagnostic-only script:
  `outputs/diagnostics/stack_step9_leader_follower_analysis_2026_06_20/diagnose_stack_step9.py`
- Generated diagnostic artifacts:
  - `summary.json`
  - `candidate_table_all.csv`
  - `candidate_table_top15.csv`
  - `candidate_bins.csv`
  - `allocation_ablation_fixed_actions.csv`
  - `progress.log`

No production controller code was changed in this diagnostic pass.

### Commands

Targeted same-state replay/candidate diagnostic:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B outputs\diagnostics\stack_step9_leader_follower_analysis_2026_06_20\diagnose_stack_step9.py
```

Diagnostic script compile check:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile outputs\diagnostics\stack_step9_leader_follower_analysis_2026_06_20\diagnose_stack_step9.py
```

### Results

The script replayed the saved fallback-disabled peak Stackelberg sequence from
`outputs/pstack_expanded_np_grid_peak_7200_2026_06_20` to the state before
control decision step 9 (`time_sec=1620.0`). It then evaluated the same state
with PFO and with Stackelberg full no-prefilter leader candidate capture.

Same-state PFO reference:

| Metric | Value |
|---|---:|
| PFO response objective | 422.686 |
| PFO applied RM sum | 5100.231 veh/h |
| PFO terminal urban vehicles | 2977.422 |
| PFO movement queue projection | 2051.485 |
| PFO solve time | 9.919 s |

Stackelberg full no-prefilter capture:

| Metric | Value |
|---|---:|
| Candidate count | 74 |
| Full capture time | 241.824 s |
| Selected `N_P_star` | 203.780 veh |
| Selected `N_UF_star` | 5700.231 veh/h |
| Applied RM sum | 5700.231 veh/h |
| Applied RM minus target | 0.000 veh/h |
| Leader objective | 571.972 |
| Follower/rollout base | 405.043 |
| Boundary-in penalty | 166.527 |
| Response objective | 439.764 |
| Terminal urban vehicles | 3441.088 |

Best Stackelberg candidate by `N_UF` bin:

| `N_UF` bin | Count | Best `N_UF_star` | Applied RM | Leader objective | Response objective | Terminal urban |
|---|---:|---:|---:|---:|---:|---:|
| 0-4500 | 20 | 4200.231 | 4200.231 | 590.937 | 444.623 | 3507.452 |
| 4500-5000 | 16 | 4650.174 | 4650.174 | 590.572 | 444.705 | 3507.523 |
| 5000-5500 | 14 | 5100.116 | 5100.116 | 584.545 | 440.113 | 3447.316 |
| 5500-6000 | 16 | 5700.231 | 5700.231 | 571.972 | 439.764 | 3441.088 |
| 6000-7000 | 8 | 6000.000 | 6000.000 | 597.034 | 446.038 | 3526.076 |

Allocation/green-band diagnostic on two fixed leader actions:

| Case | `N_UF_star` | Leader objective | Follower base | Boundary-in penalty | Response objective | Terminal urban |
|---|---:|---:|---:|---:|---:|---:|
| selected high `N_UF`, normal | 5700.231 | 571.972 | 405.043 | 166.527 | 439.764 | 3441.088 |
| selected high `N_UF`, green band 999 | 5700.231 | 568.029 | 404.654 | 162.974 | 440.221 | 3447.187 |
| selected high `N_UF`, neutral allocation diagnostic | 5700.231 | 670.076 | 423.678 | 236.615 | 423.678 | 2989.145 |
| PFO-like low `N_UF`, normal | 5100.116 | 584.545 | 408.926 | 173.717 | 440.113 | 3447.316 |
| PFO-like low `N_UF`, green band 999 | 5100.116 | 582.130 | 409.125 | 171.103 | 440.488 | 3452.323 |
| PFO-like low `N_UF`, neutral allocation diagnostic | 5100.116 | 668.774 | 423.678 | 236.615 | 423.678 | 2989.145 |

### Interpretation

- At this reproduced pre-step-9 state, the selected `N_UF_star` is preserved:
  applied RM sum exactly matches the selected leader target for the selected
  candidate and for the best candidate in every `N_UF` bin. Therefore the
  selected-target vs applied-RM mismatch is not the dominant explanation for
  this specific logged step.
- Full no-prefilter search does see lower `N_UF` regions. It evaluates 20
  candidates below `4500 veh/h`, 16 in `4500-5000`, and 14 in `5000-5500`.
  However, within the current Stackelberg follower response model, the
  `5500-6000 veh/h` bin has the lowest leader objective.
- The important gap is between Stackelberg's leader-conditioned follower
  response and PFO's direct follower response. On the same reproduced Stack
  state, PFO chooses an applied RM sum near `5100 veh/h` and reaches terminal
  urban vehicles `2977.422`, while the Stackelberg `N_UF≈5100` candidate still
  has terminal urban vehicles `3447.316`.
- Relaxing the allocation green band improves the leader objective slightly,
  but does not flip the ranking: high `N_UF` remains preferred over the
  PFO-like lower `N_UF`.
- The neutral-allocation diagnostic is not a valid controller candidate because
  it bypasses allocation constraints and loses the leader-conditioned grid
  diagnostics, but it is informative: terminal urban vehicles fall near the PFO
  range (`~2989`). This points to the allocation-conditioned follower feasible
  response as a stronger suspect than the leader `N_UF` grid itself.

### Next Modification

Investigate and revise the leader-conditioned follower construction so that,
when the leader sets `N_P_star` and `N_UF_star`, the follower's green/offset/RM
response can still reproduce the direct-control PFO feasible response when that
response is TTT-better. Specifically inspect:

- allocation module movement-flow constraints and their interaction with
  `_select_stage2_controls()`,
- whether allocation-derived green setpoints over-constrain stage-2 service
  even when the green band is widened,
- whether Stackelberg should evaluate a direct-control follower guard candidate
  with the same `N_UF` projection but without forcing allocation setpoints.
## 2026-06-20: Stackelberg Direct Leader-Feasible Follower Search

### Implementation

- Revised the distributed Stackelberg follower path so the inflow-outflow
  allocation module is no longer used as the follower candidate generator.
- Stack follower controls are now projected directly into the leader-constrained
  set:
  - ramp metering is projected so `sum(ramp_metering) ~= leader.N_UF_star`,
  - green/offset/VSL remain direct structured-grid candidates,
  - `inflow_outflow_allocation` is cleared for the Stack follower path.
- Added leader `N_P_star` net-inflow feasibility diagnostics and pre-checks:
  - projected candidate net inflow,
  - target net inflow from `urban_accumulation_feedback_flow`,
  - net-inflow residual beyond `eps_U`,
  - projected movement storage violation.
- Added balance tie-break diagnostics. Balance is used only as a near-equal-TTT
  tie-break among leader-direct grid candidates, not as an additive TTT cost.
- Updated the Nash-iteration candidate under a leader so it is also evaluated
  by the same rollout TTT path; the selected Stack follower response no longer
  falls back to proxy-only `distributed_response_objective_tts`.

Changed files:

- `src/controllers/distributed_coordinator.py`
- `src/controllers/urban_follower.py`
- `reports/codex_run_report.md`

### Validation

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\distributed_coordinator.py src\controllers\urban_follower.py
```

Result: PASS.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_urban_follower_objective_covers_uncontrolled_E_vehicles src.tests.test_constraints.ConstraintTests.test_allocation_net_inflow_binding_uses_inflow_outflow_extremes -v
```

Result: PASS (`2` tests).

### Smoke Runs

180 s command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 180 --output outputs\pstack_direct_feasible_medium_180_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback
```

360 s command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 360 --output outputs\pstack_direct_feasible_medium_360_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback
```

| Horizon | Controller | Total TTT | Improvement vs no-control | Total delay | Throughput veh/h | Mean B sum | Compute sec |
|---:|---|---:|---:|---:|---:|---:|---:|
| 180 s | NO-CONTROL | 17.616 | baseline | 1.046 | 8000.6 | 0.109886 | 0.00 |
| 180 s | PROPOSED-STACKELBERG | 17.625 | -0.051% | 1.055 | 7770.2 | 0.122422 | 334.07 |
| 360 s | NO-CONTROL | 41.011 | baseline | 0.610 | 9185.7 | 0.146213 | 0.00 |
| 360 s | PROPOSED-STACKELBERG | 41.301 | -0.707% | 0.901 | 9114.5 | 0.109114 | 558.32 |

### Control Validation Summary

- Direct Stack path diagnostics are active in the selected response:
  - `distributed_grid_leader_allocation_module_disabled = 1.0`,
  - `distributed_stackelberg_direct_feasible_set_active = 1.0`,
  - `distributed_grid_leader_direct_feasible_set_active = 1.0`,
  - `allocation_module_active = 0.0`,
  - `agent_U_A_allocation_module_used = 0.0`.
- The selected 180 s Stack response was evaluated by rollout:
  - `distributed_response_rollout_active = 1.0`,
  - `distributed_nash_candidate_rollout_evaluated = 1.0`.
- Remaining issue: the current leader-selected `N_P_star/N_UF_star` combination
  still creates an empty or nearly empty feasible set under the direct
  net-inflow pre-check. In the 180 s medium smoke, selected diagnostics were:
  - target net inflow `-728.147 veh/h`,
  - projected net inflow `-2403.333 veh/h`,
  - absolute residual `1675.186 veh/h`,
  - constraint violation after `eps_U=100` of `1575.186`.

### Failed Criteria / Next Modification

- This is not an acceptance pass. Short smoke Total TTT is slightly worse than
  no-control, and computation cost is high.
- The implementation now matches the intended structural direction better:
  allocation no longer decides the follower action, and final selected Stack
  follower candidates use rollout TTT.
- The next issue is feasibility coverage, not allocation leakage: the leader is
  still selecting high `N_UF_star` values whose direct follower candidate set
  cannot satisfy the `N_P_star` net-inflow target. The next modification should
  diagnose leader candidate filtering/ranking with the new
  `distributed_grid_leader_net_inflow_*` diagnostics and either reject such
  leader candidates earlier or widen direct green/on-ramp candidates enough to
  make the leader feasible set non-empty before comparing TTT.
## 2026-06-20: Target-Aware Green Projection for Stackelberg Followers

### Implementation

- Added target-aware green projection to the Stackelberg distributed follower
  candidate path.
- Each leader-conditioned structured-grid seed is now augmented with an
  additional `target_net_inflow` candidate when green adjustment reduces the
  residual between:
  - `urban_accumulation_feedback_flow(state, cfg, leader.N_P_star, forecast)`,
  - the candidate's projected net inflow from boundary/off-ramp inflow and
    boundary/on-ramp outflow service.
- The projection keeps the leader constraints:
  - ramp metering remains projected to `N_UF_star`,
  - allocation module remains disabled,
  - only direct green splits are adjusted.
- Added a coarse all-signal min/max green pass before coordinate search so the
  projection is less likely to get stuck in one-signal local minima.
- Added a hard feasibility penalty to rollout objective when a candidate still
  violates the leader direct net-inflow/storage constraints. This is a
  constraint violation penalty, not a balance cost term.
- Applied the same target-aware green projection to leader-present Nash
  iteration candidates before rollout evaluation so the final response cannot
  bypass the target-aware candidate logic.

Changed files:

- `src/controllers/distributed_coordinator.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Validation

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\distributed_coordinator.py src\controllers\urban_follower.py src\tests\test_constraints.py
```

Result: PASS.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_leader_conditioned_grid_projects_metering_target src.tests.test_constraints.ConstraintTests.test_urban_follower_objective_covers_uncontrolled_E_vehicles src.tests.test_constraints.ConstraintTests.test_allocation_net_inflow_binding_uses_inflow_outflow_extremes -v
```

Result: PASS (`3` tests).

Candidate-level diagnostic on the initial `medium_demand` state:

| Candidate set | Count | target-net candidates | Best abs net-inflow residual | Best projected net inflow | Target net inflow |
|---|---:|---:|---:|---:|---:|
| Base leader-conditioned grid | 127 | 0 | 3530.964 | 2739.457 | -791.507 |
| Target-aware augmented grid | 182 | 55 | 3254.347 | 2462.840 | -791.507 |

### Smoke Run

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 180 --output outputs\pstack_target_green_nash_medium_180_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback
```

| Controller | Total TTT | Improvement vs no-control | Total delay | Throughput veh/h | Mean B sum | Compute sec |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 17.616 | baseline | 1.046 | 8000.6 | 0.109886 | 0.00 |
| PROPOSED-STACKELBERG | 17.439 | 1.005% | 0.869 | 7881.3 | 0.064870 | 593.16 |

Selected response diagnostics:

| Diagnostic | Value |
|---|---:|
| `distributed_response_rollout_active` | 1.0 |
| `distributed_nash_candidate_target_green_projection_active` | 1.0 |
| `allocation_module_active` | 0.0 |
| `distributed_grid_leader_net_inflow_target_veh_h` | -674.372 |
| `distributed_grid_leader_projected_net_inflow_veh_h` | 2372.000 |
| `distributed_grid_leader_net_inflow_abs_residual_veh_h` | 3046.372 |
| `distributed_grid_leader_constraint_penalty` | 13258.673 |

### Interpretation

- The structural correction is active: Stack follower responses are direct
  control candidates, allocation is disabled, and selected Nash candidates are
  forced through target-aware green projection before rollout evaluation.
- The 180 s medium smoke improves Total TTT and boundary balance compared with
  no-control, but the controller is not acceptance-ready.
- The remaining problem is now clearer: the selected leader target can still be
  outside what the direct green/RM feasible set can realize over the current
  horizon. In this smoke, the target asks for negative net inflow, while the
  best selected projected net inflow is still strongly positive.

### Failed Criteria / Next Modification

- This is not a final performance pass: horizon is only 180 s and computation
  cost is high.
- Next modification should move the feasibility logic one level up:
  leader candidates whose follower feasible set cannot get near the `N_P_star`
  net-inflow target should be rejected or heavily down-ranked before expensive
  full follower evaluation, and the leader `N_P_star` grid should prefer targets
  whose requested net inflow is reachable by direct green/RM controls in the
  current state.
## 2026-06-20: Net-Inflow Feasibility Unit Normalization

### Implementation

- Removed the Stack follower leader-constraint penalty from rollout objective.
  The selected grid objective is again:
  - rollout Total TTT,
  - plus existing spillback penalty only.
- Converted direct leader net-inflow feasibility diagnostics to vehicle units:
  - `distributed_grid_leader_net_inflow_target_veh`,
  - `distributed_grid_leader_projected_net_inflow_veh`,
  - `distributed_grid_leader_net_inflow_residual_veh`,
  - `distributed_grid_leader_net_inflow_abs_residual_veh`,
  - `distributed_grid_leader_net_inflow_eps_veh`,
  - `distributed_grid_leader_net_inflow_violation_veh`.
- Kept rate diagnostics only as explicitly named rates:
  - `distributed_grid_leader_net_inflow_target_rate_veh_h`,
  - `distributed_grid_leader_projected_net_inflow_rate_veh_h`.
- `distributed_grid_leader_total_constraint_violation` is now in vehicles, so
  it is unit-compatible with spillback/storage violation checks.

Changed files:

- `src/controllers/distributed_coordinator.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Validation

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\distributed_coordinator.py src\controllers\urban_follower.py src\tests\test_constraints.py
```

Result: PASS.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_leader_conditioned_grid_projects_metering_target src.tests.test_constraints.ConstraintTests.test_urban_follower_objective_covers_uncontrolled_E_vehicles src.tests.test_constraints.ConstraintTests.test_allocation_net_inflow_binding_uses_inflow_outflow_extremes -v
```

Result: PASS (`3` tests).

Candidate-level unit diagnostic on the initial `medium_demand` state:

| Metric | Value |
|---|---:|
| Augmented candidate count | 182 |
| Target-net-inflow candidates | 55 |
| Best abs residual | 488.152 veh |
| Target net inflow | -118.726 veh |
| Projected net inflow | 369.426 veh |
| Net-inflow eps | 15.000 veh |
| Total constraint violation | 473.152 veh |

No closed-loop smoke was rerun after this unit-only correction because the
latest 180 s Stack smoke took roughly ten minutes and included the now-removed
leader-constraint penalty. That previous smoke should not be interpreted as the
current implementation's performance result.

### Interpretation

- The previous `veh/h + veh` constraint aggregation was unit-inconsistent. This
  is fixed: net-inflow residuals are converted to vehicle counts over the
  follower horizon before feasibility comparison.
- The remaining gap is not just a unit issue. The target can still be physically
  hard to realize with the current direct green/RM candidate set.
- The MFD-style feedback target can also conflict with TTT minimization in
  under-critical scenarios. If the leader objective penalizes only
  `N_P > N_P_crit`, then all under-critical protected accumulations are nearly
  equivalent from the critical-penalty perspective. In median/slack states, a
  high or permissive `N_P_star` can allow more vehicles into the protected
  network even when doing so is not Total TTT-optimal.

### Failed Criteria / Next Modification

- This is not an acceptance pass; no post-fix 7200 s or smoke performance run
  has been completed.
- Next modification should separate the two concepts:
  - keep MFD critical-overflow protection as a gridlock prevention term,
  - avoid using the feedback target as a hard constraint when the network is
    below critical or when the target is unreachable over the MPC horizon.
  A reasonable next test is to gate `N_P` target tracking so it activates only
  when protected accumulation is near/above critical, while still letting
  rollout TTT decide below-critical median states.

## 2026-06-20: Spec 16 N_P_star Semantics Correction

### Implementation

- Corrected `docs/spec/16_six_controller_comparison.md` so it no longer defines
  proposed-controller `N_P_star` as a protected-network accumulation target.
- The proposed Stackelberg section now matches the base controller specs:
  `N_P_star` is the target net inflow to the protected urban network, while
  `N_P_crit` is a separate critical-accumulation guard used by the
  objective/constraints.
- Renamed the Wu-authority-matched Stackelberg variant's accumulation references
  from `N_P_star/N_F_star` to `N_P_ref/N_F_ref` inside the spec to avoid
  overloading `N_P_star` with two meanings.

Changed file:

- `docs/spec/16_six_controller_comparison.md`

### Validation

- No code tests or closed-loop simulations were run for this documentation-only
  correction.

### Interpretation

- The primary specs already stated the intended semantics:
  - `docs/spec/01_control_concept.md`: `N_P_star` is target net inflow.
  - `docs/spec/04_controller.md`: urban follower constraints compare projected
    inflow-minus-outflow service against `N_P_star`.
- `docs/spec/16_six_controller_comparison.md` had drifted and was describing
  `N_P_star` as accumulation/coordination target, which is inconsistent with
  the proposed controller formulation and contributed to the current code path
  that computes
  `(target_accumulation - current_accumulation) / feedback_h`.

### Failed Criteria / Next Modification

- This does not fix the implementation yet. Current code still contains
  accumulation-target semantics in `urban_accumulation_feedback_flow()` and in
  leader candidate bounds tied to `N_P_crit`.
- Next implementation step should restore proposed-controller `N_P_star` as a
  direct net-inflow target and broaden leader search over feasible net-inflow
  values, while keeping `N_P_crit` only as a critical-overflow guard.

## 2026-06-20: P-Stack N_P_star Direct Net-Inflow Semantics

### Implementation

- Restored Proposed Stackelberg `N_P_star` to the original spec meaning:
  protected-urban net-inflow target, expressed as vehicles over the follower
  evaluation horizon.
- Changed leader candidate generation so `N_P_star` is no longer generated from
  an `N_P_crit` accumulation band. The default search is now clipped by:
  - configured direct target range `leader.N_P_star_range`,
  - movement-level feasible inflow-minus-outflow bounds over the follower
    horizon.
- Updated default `leader.N_P_star_range` from `[0, 850]` to
  `[-3500, 3500]`, matching the current topology's approximate feasible
  medium initial-state horizon range (`-3315` to `3220 veh`).
- Removed accumulation-feedback conversion from P-Stack direct follower
  diagnostics:
  - old: `(target_accumulation - current_accumulation) / feedback_h`,
  - new: `target_net_inflow_veh = leader.N_P_star` and
    `target_rate = target_net_inflow_veh / horizon_h`.
- Treated `urban_follower.eps_U` as a vehicle-count tolerance in the direct
  follower precheck, not a rate multiplied by horizon.
- Updated the allocation module so if it is used with a leader, it converts
  direct `N_P_star` vehicles to a veh/h service target by dividing by the
  follower horizon.
- Updated urban follower and urban model diagnostics so P-Stack no longer logs
  `N_P_star` as an accumulation target. Accumulation target diagnostics are
  disabled and net-inflow target diagnostics are logged explicitly.
- Updated `docs/spec/09_configuration_requirements.md` to match the corrected
  direct net-inflow semantics.

Changed files:

- `src/controllers/leader.py`
- `src/controllers/distributed_coordinator.py`
- `src/controllers/urban_follower.py`
- `src/controllers/inflow_outflow_allocation.py`
- `src/models/urban_queue_model.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/tests/test_constraints.py`
- `docs/spec/09_configuration_requirements.md`
- `reports/codex_run_report.md`

### Validation

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\leader.py src\controllers\distributed_coordinator.py src\controllers\urban_follower.py src\controllers\inflow_outflow_allocation.py src\models\urban_queue_model.py src\models\state.py src\tests\test_constraints.py
```

Result: PASS.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_leader_candidate_budget_covers_extremes_and_previous_action src.tests.test_constraints.ConstraintTests.test_leader_np_candidates_use_feasible_net_inflow_range src.tests.test_constraints.ConstraintTests.test_default_leader_np_grid_covers_feasible_net_inflow_range src.tests.test_constraints.ConstraintTests.test_leader_conditioned_grid_projects_metering_target src.tests.test_constraints.ConstraintTests.test_allocation_net_inflow_binding_uses_inflow_outflow_extremes -v
```

Result: PASS (`5` tests).

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_metanet_equations.MetanetEquationTests.test_config_exposes_time_ratios_and_units src.tests.test_metanet_equations.MetanetEquationTests.test_config_rejects_invalid_np_candidate_band -v
```

Result: PASS (`2` tests).

Candidate-bound diagnostic on initial `medium_demand`:

| Metric | Value |
|---|---:|
| leader `N_P_star` lower | -3315.000 veh |
| leader `N_P_star` upper | 3220.000 veh |
| candidate count | 50 |
| zero target included | yes |

### Smoke Run

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 180 --output outputs\pstack_np_direct_net_inflow_medium_180_2026_06_20 --max-nash-iter 1 --freeway-prediction-horizon-steps 3 --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 8 --disable-stackelberg-fallback
```

| Controller | Total TTT | Improvement vs no-control | Total delay | Throughput veh/h | Mean B sum | Compute sec |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 17.616 | baseline | 1.046 | 8000.6 | 0.109886 | 0.0 |
| PROPOSED-STACKELBERG | 17.439 | 1.005% | 0.869 | 7881.3 | 0.064870 | 564.2 |

Selected diagnostic row:

| Diagnostic | Value |
|---|---:|
| selected `N_P_star` | 0.000 veh |
| selected `N_UF_star` | 6000.000 veh/h |
| leader `N_P_star` bound lower | -3315.000 veh |
| leader `N_P_star` bound upper | 3220.000 veh |
| target net inflow | 0.000 veh |
| projected net inflow | 355.800 veh |
| net-inflow residual | 355.800 veh |
| net-inflow eps | 100.000 veh |

### Interpretation

- The semantic correction is active: the leader searched negative, zero, and
  positive direct net-inflow targets, and the selected 180 s smoke target was
  `N_P_star = 0 veh` rather than an accumulation target near `N_P_crit`.
- The direct follower diagnostics now compare projected
  `inflow_veh - outflow_veh` against `leader.N_P_star` in vehicle units.
- The smoke result is not an acceptance result. It is only a semantic
  closed-loop check over 180 s. Improvement remains small and throughput is
  lower than no-control.
- Computation cost remains high (`564.2 s` for one 180 s Stack smoke), so future
  7200 s runs still need a candidate-evaluation cost reduction or smaller
  semantic smoke harness.

### Failed Criteria / Next Modification

- Full 7200 s acceptance was not run.
- The selected `N_UF_star` is still at the high bound in this short medium
  smoke, so the remaining P-Stack/PFO gap may now be more about `N_UF_star`
  leader search/prefilter and the follower feasible response than about
  `N_P_star` semantics.
- Next recommended diagnostic: compare full-evaluated leader candidates grouped
  by `N_UF_star` under the corrected `N_P_star` semantics and verify whether the
  proxy prefilter is still dropping lower-freeway-release candidates that have
  better rollout Total TTT.

## 2026-06-20: Simplified Allocation-Backed P-Stack Ablation

### Purpose

`N_P_star` 의미 오류 때문에 기존 allocation module이 잘못 작동했는지 분리해서
확인했다. 기존 direct feasible Stackelberg path는 삭제하지 않고, 새 deterministic
allocation module을 별도 파일로 추가한 뒤 `mpc.stackelberg_allocation_mode=simplified`
일 때만 사용했다.

### Implementation

Changed files:

- `src/controllers/simplified_inflow_outflow_allocation.py`
- `src/controllers/distributed_coordinator.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

Implementation notes:

- Added `SimplifiedInflowOutflowAllocationModule`.
- It interprets `leader.N_P_star` as protected-urban net inflow target in
  vehicles over the follower horizon, then converts to veh/h only inside the
  allocation module.
- It uses deterministic queue/balance seed plus net-inflow projection. It does
  not use PSO, so this ablation does not mix allocation semantics with
  stochastic solver noise.
- Default `mpc.stackelberg_allocation_mode` remains `direct`; current direct
  feasible Stackelberg behavior is preserved.
- In simplified mode, the distributed Stackelberg follower skips the broad
  direct grid and evaluates the allocation seed plus Nash response only. This is
  an ablation path, not the primary controller definition.

### Validation

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\simplified_inflow_outflow_allocation.py src\controllers\distributed_coordinator.py src\models\state.py src\experiments\all_scenarios_four_controller_comparison.py src\tests\test_constraints.py
```

Result: PASS.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_simplified_allocation_uses_np_star_as_net_inflow_vehicles src.tests.test_constraints.ConstraintTests.test_stackelberg_simplified_allocation_projection_keeps_allocation_map src.tests.test_constraints.ConstraintTests.test_leader_np_candidates_use_feasible_net_inflow_range src.tests.test_constraints.ConstraintTests.test_default_leader_np_grid_covers_feasible_net_inflow_range -v
```

Result: PASS (`4` tests).

### 180 s Smoke

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 180 --output outputs\pstack_simplified_allocation_seed_medium_180_2026_06_20 --max-nash-iter 1 --stackelberg-allocation-mode simplified --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 4 --stackelberg-prefilter-top-k 4 --stackelberg-prefilter-local-top-k 4 --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 8 --freeway-prediction-horizon-steps 3 --disable-stackelberg-fallback
```

| Controller | Total TTT | Improvement vs no-control | Urban TTT | Freeway TTT | Throughput veh/h | Terminal vehicles | Mean B sum | Compute sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 17.616 | baseline | 11.253 | 6.363 | 8000.6 | 399.4 | 0.109886 | 0.0 |
| PROPOSED-STACKELBERG simplified allocation | 19.445 | -10.383% | 15.035 | 4.410 | 5739.8 | 512.9 | 0.050733 | 4.98 |

Key diagnostics:

| Diagnostic | Value |
|---|---:|
| selected `N_P_star` | 0.000 veh |
| selected `N_UF_star` | 6000.000 veh/h |
| allocation target net inflow | 0.000 veh |
| allocation projected net inflow | approximately 0.000 veh |
| allocation residual | approximately 0.000 veh |

### 7200 s Medium Scenario Run

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\pstack_simplified_allocation_seed_medium_7200_2026_06_20 --max-nash-iter 1 --stackelberg-allocation-mode simplified --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 4 --stackelberg-prefilter-top-k 4 --stackelberg-prefilter-local-top-k 4 --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 8 --freeway-prediction-horizon-steps 3 --disable-stackelberg-fallback
```

| Controller | Total TTT | Improvement vs no-control | Urban TTT | Freeway TTT | Total delay | Completed vehicles | Throughput veh/h | Terminal vehicles | Mean B sum | Compute sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 1943.962 | baseline | 887.149 | 1056.814 | 1019.342 | 21380.3 | 10690.1 | 2469.8 | 0.189289 | 0.0 |
| PROPOSED-STACKELBERG simplified allocation | 10728.267 | -451.876% | 10518.924 | 209.344 | 9803.647 | 14013.1 | 7006.6 | 9842.6 | 0.016441 | 186.21 |

Boundary balance is numerically lower in `B_sum`, but this is not a valid
success because boundary overflow worsened (`max_OverflowRatio_boundary=0.5`)
and terminal vehicles increased by `7372.8` vehicles.

### Diagnosis

- The new allocation module itself is not failing the `N_P_star` target
  constraint. Across 40 control intervals, `N_P_star=0` and `N_UF_star=6000`
  were selected every time. Allocation net-inflow residual averaged only
  `1.98 veh` and maxed at `14.61 veh`.
- The failure is throughput/terminal-state collapse: completed vehicles fell
  from `21380.3` to `14013.1`, throughput fell by `3683.5 veh/h`, and terminal
  urban vehicles rose from `1224.9` to `9736.5`.
- Freeway TTT dropped sharply (`1056.814 -> 209.344`), but the controller
  achieved this by shifting cost into the urban network. This is exactly the
  subnetwork-scale/leader-objective imbalance suspected in the discussion.
- Therefore the old allocation module may indeed have been confused by the old
  `N_P_star` feedback interpretation, but after fixing the semantics the pure
  allocation-backed ablation still fails. The remaining root cause is not the
  allocation target residual; it is that the Leader keeps choosing
  `N_P_star=0, N_UF_star=6000` because its evaluated objective/prefilter does
  not sufficiently price future urban terminal queues and lost throughput.

### Failed Criteria / Next Modification

- FAIL: Total TTT is far worse than no-control.
- FAIL: Total delay and average delay per completed vehicle are far worse than
  no-control.
- FAIL: Throughput is materially lower and terminal vehicles are materially
  higher.
- FAIL: Boundary overflow worsened despite lower mean `B_sum`.
- Next modification should target the Leader evaluation, not the allocation
  residual: add a hard/large throughput-shortfall and terminal-urban-vehicle
  guard to leader candidate evaluation, then verify whether candidates with
  nonzero/positive `N_P_star` beat the current `N_P_star=0` solution under the
  corrected allocation semantics.

## 2026-06-20: Direct P-Stack Leader Candidate Table Diagnostic

### Purpose

Direct/no-allocation Stackelberg에서도 `N_P_star=0, N_UF_star=6000`이 왜
선택되는지 첫 medium-demand MPC decision의 후보별 objective table을 직접
재현했다.

### Diagnostic Setup

- Scenario: `medium_demand`
- State: initial state
- Horizon: `mpc.horizon_steps=3`
- Mode: direct Stackelberg (`mpc.stackelberg_allocation_mode=direct`)
- Fallback disabled for leader-candidate diagnosis
- `max_nash_iter=1`
- The table was generated by reproducing `StackelbergMPCController` internal
  candidate generation, prefiltering, and `_evaluate_full_candidate()` calls.

### Prefilter Table

Top coarse candidates before full evaluation:

| Rank | Index | `N_P_star` | `N_UF_star` | Proxy obj | Follower TTT proxy | Selected for full eval |
|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 5 | 0.0 | 6000.0 | 114.776 | 93.776 | yes |
| 2 | 20 | -47.5 | 5294.3 | 118.916 | 93.776 | yes |
| 3 | 39 | -47.5 | 4588.5 | 120.680 | 93.776 | yes |
| 4 | 49 | 0.0 | 2942.7 | 122.420 | 93.776 | yes |
| 5 | 12 | -47.5 | 3882.8 | 122.444 | 93.776 | no |
| 6 | 29 | -47.5 | 3177.1 | 124.209 | 93.776 | no |
| 7 | 4 | 0.0 | 2354.1 | 125.156 | 95.042 | no |
| 8 | 45 | -47.5 | 1765.6 | 135.411 | 101.450 | yes |

### Full-Evaluated Candidate Table

The full-evaluated leader candidates are not ignoring the rollout TTT among the
candidate set: the leader-objective ranking and the rollout-TTT ranking both
put `N_P_star=0, N_UF_star=6000` first.

| Rank | Stage | Index | `N_P_star` | `N_UF_star` | Leader obj | Rollout TTT | Urban | Freeway | Terminal urban proxy | Completed proxy |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | coarse | 5 | 0.0 | 6000.0 | 81.624 | 65.158 | 46.029 | 19.129 | 839.4 | 1022.4 |
| 2 | refined | 50 | 0.0 | 6000.0 | 81.624 | 65.158 | 46.029 | 19.129 | 839.4 | 1022.4 |
| 3 | refined | 73 | 0.0 | 5625.0 | 82.622 | 65.218 | 46.027 | 19.191 | 839.4 | 1022.4 |
| 4 | refined | 72 | 0.0 | 5250.0 | 83.678 | 65.336 | 46.023 | 19.314 | 839.4 | 1022.4 |
| 5 | refined | 71 | 0.0 | 4875.0 | 84.763 | 65.484 | 46.016 | 19.468 | 839.4 | 1022.4 |
| 6 | coarse | 20 | -47.5 | 5294.3 | 85.926 | 65.320 | 46.023 | 19.297 | 839.4 | 1022.4 |
| 7 | coarse | 39 | -47.5 | 4588.5 | 87.995 | 65.625 | 46.012 | 19.613 | 839.4 | 1022.4 |
| 8 | coarse | 49 | 0.0 | 2942.7 | 93.691 | 69.581 | 45.885 | 23.695 | 839.4 | 1022.4 |
| 9 | refined | 69 | 0.0 | 2354.1 | 98.364 | 72.783 | 45.779 | 27.004 | 839.4 | 1010.4 |
| 10 | coarse | 45 | -47.5 | 1765.6 | 105.872 | 76.445 | 45.671 | 30.774 | 839.4 | 925.0 |
| 11 | coarse | 0 | -3315.0 | 1765.6 | 269.247 | 76.445 | 45.671 | 30.774 | 839.4 | 925.0 |

### Guard/Fallback Comparison

When the physical no-control action is rolled out over the same three-step
MPC horizon, it has lower rollout TTT than the selected leader candidate.

| Candidate | Leader/follower obj | Rollout TTT | Urban | Freeway | Completed proxy | Terminal urban | Terminal freeway |
|---|---:|---:|---:|---:|---:|---:|---:|
| selected `N_P=0,N_UF=6000` | 81.624 | 65.158 | 46.029 | 19.129 | 1330.9 | 404.6 | 124.6 |
| physical no-control | proxy 129.757 | 60.478 | 40.407 | 20.071 | 1418.6 | 314.2 | 127.3 |
| PFO fallback | 67.531 | 67.531 | 49.493 | 18.038 | 1302.4 | 437.5 | 119.1 |

### Diagnosis

- Among the evaluated leader candidates, `N_P=0,N_UF=6000` is not ignoring TTT;
  it is the lowest rollout-TTT candidate in that restricted candidate set.
- The physical no-control action is not part of the leader candidate set.
- The fallback no-control path uses a response proxy for its leader objective,
  not the same full rollout TTT used in the diagnostic comparison above.
  Therefore no-control can have better rollout TTT (`60.478`) but still look
  worse to the fallback/leader objective (`129.757 > 81.624`).
- Root cause: objective/candidate-set mismatch, not allocation residual.

### Next Modification

- Add physical no-control/previous-control guard candidates directly into leader
  candidate evaluation, not only in fallback.
- Evaluate guard candidates with the same rollout-TTT-compatible metric used for
  full leader candidates.
- Add terminal-urban and throughput-shortfall guard terms so a candidate cannot
  win by reducing freeway TTT while accumulating hidden urban queues or reducing
  completed vehicles.

## 2026-06-20: Medium 1800 s PFO Horizon Check

### Purpose

Checked whether the short 180 s finding that the follower-only/PFO-style guard
can reduce TTT persists over a longer 1800 s medium-demand run.

### Run Command

Baseline and proposed controller were run in the same command with identical
scenario, demand, and horizon:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-FOLLOWERS-ONLY --T-total 1800 --output outputs\pfo_medium_1800_2026_06_20 --max-nash-iter 1 --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 8 --freeway-prediction-horizon-steps 3
```

### Results

| Controller | Total TTT | Total delay | Urban TTT | Freeway TTT | Throughput | Terminal vehicles | Mean B_sum | Wall time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 244.284 | 16.595 | 159.181 | 85.103 | 11390.3 | 464.1 | 0.145984 | 0.557 s |
| PROPOSED-FOLLOWERS-ONLY | 239.241 | 11.552 | 155.151 | 84.090 | 11417.0 | 456.9 | 0.143317 | 288.258 s |

Improvement rate: `2.064%` Total TTT reduction vs no-control.

Boundary queue balancing result: non-degraded (`mean_B_sum` improves by
`0.002667`, max boundary overflow remains `0.0`).

Control validation summary: authority checks passed for
`PROPOSED-FOLLOWERS-ONLY`; solver convergence rate was `1.0`.

### Diagnosis

- The 180 s PFO/fallback benefit is not only a one-interval artifact: over
  1800 s, PFO still improves Total TTT, urban TTT, freeway TTT, throughput, and
  terminal vehicles relative to no-control.
- The improvement remains below the 8% acceptance threshold, so this is a
  diagnostic pass rather than controller acceptance.
- Running direct Stackelberg for 1800 s with the current full candidate
  evaluation would likely be much more expensive than this PFO check; the prior
  first-decision diagnostic already took roughly minutes per MPC decision.

### Next Modification

Before a full 1800 s direct Stackelberg run, align the fallback/guard candidates
with the same rollout-TTT-compatible evaluation used for full leader candidates,
and add physical no-control/previous-control guard actions directly to the
leader candidate set. This should separate a true leader-grid spacing issue
from the current objective/candidate-set mismatch.

## 2026-06-20: Medium 180 s Tight Leader Grid Injection Diagnostic

### Purpose

Tested whether the Stackelberg leader fails because the leader grid does not
contain the no-control/PFO-equivalent `N_P_star` and `N_UF_star` choices. The
diagnostic reverse-engineered leader targets from the physical no-control
action and the PFO action, injected those exact targets into a tight leader
candidate grid, and evaluated the candidates with the production distributed
follower path.

An initial diagnostic attempt accidentally used the default legacy
`follower_solver_mode=two_block`; that result is superseded. The valid run
below explicitly sets `follower_solver_mode=distributed`, matching the
`PROPOSED-STACKELBERG` adapter.

### Run Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.leader_grid_injection_diagnostic --scenario medium_demand --T-total 180 --output outputs\leader_grid_injection_medium_180_distributed_fg_2026_06_20 --max-nash-iter 1 --np-step 40 --nuf-step 500
```

### Reverse-Engineered Anchors

Both physical no-control and PFO produced the same leader target pair under
the current reverse mapping:

| Source action | Reverse `N_P_star` | Reverse `N_UF_star` | One-step plant TTT | Urban TTT | Freeway TTT | Terminal vehicles |
|---|---:|---:|---:|---:|---:|---:|
| no-control | 461.300 | 6000.000 | 17.616 | 11.253 | 6.363 | 399.382 |
| PFO | 461.300 | 6000.000 | 17.320 | 10.986 | 6.334 | 394.131 |

### Tight Candidate Ranking

| Rank | Label | `N_P_star` | `N_UF_star` | Leader obj | Rollout TTT | Urban rollout | Freeway rollout | Boundary penalty | Smoothness penalty |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | previous_default_exact | 0.000 | 6000.000 | 80.481 | 64.367 | 45.506 | 18.861 | 16.114 | 0.000 |
| 2 | no_control_np_-80 | 381.300 | 6000.000 | 82.333 | 58.796 | 39.221 | 19.575 | 4.473 | 19.065 |
| 3 | no_control_np_-40 | 421.300 | 6000.000 | 84.333 | 58.796 | 39.221 | 19.575 | 4.473 | 21.065 |
| 4 | reverse_no_control_exact | 461.300 | 6000.000 | 86.333 | 58.796 | 39.221 | 19.575 | 4.473 | 23.065 |
| 5 | no_control_nuf_-500 | 461.300 | 5500.000 | 87.636 | 58.849 | 39.220 | 19.629 | 4.473 | 24.315 |
| 6 | no_control_np_+40 | 501.300 | 6000.000 | 88.333 | 58.796 | 39.221 | 19.575 | 4.473 | 25.065 |
| 7 | no_control_nuf_-1000 | 461.300 | 5000.000 | 88.998 | 58.960 | 39.218 | 19.742 | 4.473 | 25.565 |
| 8 | no_control_np_+80 | 541.300 | 6000.000 | 90.333 | 58.796 | 39.221 | 19.575 | 4.473 | 27.065 |

Selected leader candidate: `previous_default_exact`
(`N_P_star=0`, `N_UF_star=6000`).

### Diagnosis

- The reverse-engineered no-control/PFO target was present in the leader
  candidate set, but it was not selected.
- The injected reverse target has much lower distributed rollout TTT
  (`58.796`) than the selected previous/default target (`64.367`).
- The exact reverse target loses because `leader_smoothness_penalty=23.065`
  dominates the rollout-TTT and boundary-penalty improvement. Without the
  smoothness term, the exact reverse target would have objective
  `58.796 + 4.473 = 63.269`, which beats the selected candidate's
  `64.367 + 16.114 = 80.481`.

### Failed Criteria / Next Modification

- FAIL: The leader does not choose the injected lower-rollout-TTT PFO/no-control
  target.
- Likely cause is not coarse leader grid spacing in this first medium decision;
  it is the `N_P_star` smoothness penalty scale/definition.
- Next modification should either remove `N_P_star` from the leader smoothness
  penalty, dramatically rescale it, or apply smoothness only as a tie-break
  after rollout-TTT-compatible objective comparison. Then rerun this same tight
  injection diagnostic.

## 2026-06-20: No-Smooth Leader and PSO Allocation Recheck

### Implementation

- Removed leader action smoothness from `leader_total_objective`.
  `leader_smoothness_penalty` remains logged as `0.0` for provenance.
- Set default `leader.w_L` to `0.0`.
- Added Stackelberg allocation mode `pso`, which uses the original
  `InflowOutflowAllocationModule` instead of the simplified ablation module.
- Added CLI support for `--stackelberg-allocation-mode pso` and for
  `--leader-refinement-candidate-count`.
- Added a diagnostic experiment
  `src/experiments/leader_grid_injection_diagnostic.py`.

### Changed Files

- `src/controllers/leader.py`
- `src/controllers/distributed_coordinator.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `src/experiments/leader_grid_injection_diagnostic.py`
- `src/tests/test_constraints.py`
- `docs/spec/04_controller.md`
- `docs/spec/09_configuration_requirements.md`
- `docs/spec/16_six_controller_comparison.md`

### Validation

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\distributed_coordinator.py src\controllers\inflow_outflow_allocation.py src\controllers\leader.py src\models\state.py src\experiments\all_scenarios_four_controller_comparison.py src\experiments\leader_grid_injection_diagnostic.py
```

PASS.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_pso_allocation_uses_original_module src.tests.test_constraints.ConstraintTests.test_stackelberg_simplified_allocation_projection_keeps_allocation_map src.tests.test_constraints.ConstraintTests.test_simplified_allocation_uses_np_star_as_net_inflow_vehicles src.tests.test_constraints.ConstraintTests.test_leader_objective_matches_spec_accumulation_form src.tests.test_constraints.ConstraintTests.test_default_leader_objective_uses_follower_ttt_base -v
```

PASS, 5 tests.

### No-Smooth Injection Sanity Check

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.leader_grid_injection_diagnostic --scenario medium_demand --T-total 180 --output outputs\leader_grid_injection_medium_180_no_smooth_2026_06_20 --max-nash-iter 1 --np-step 40 --nuf-step 500
```

Result: after removing smoothness, the leader selected the injected
`reverse_no_control_exact` / PFO-equivalent target
(`N_P_star=461.3`, `N_UF_star=6000`) with `leader_obj=63.268` and one-step
plant TTT `17.320`. This confirms the previous failure was caused by leader
smoothness, not by the injected target being absent.

### 7200 s Run Commands

PFO reference:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand,peak_demand --controllers PROPOSED-FOLLOWERS-ONLY --T-total 7200 --output outputs\pfo_no_smooth_finegrid_medium_peak_7200_2026_06_20_fg --max-nash-iter 1 --leader-candidate-count 81 --leader-refinement-candidate-count 49 --stackelberg-prefilter-top-k 8 --stackelberg-prefilter-local-top-k 8 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 8 --grid-parallel-backend thread --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --freeway-prediction-horizon-steps 3
```

P-Stack PSO allocation with default fallback enabled:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand,peak_demand --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\pstack_pso_allocation_no_smooth_finegrid_medium_peak_7200_2026_06_20_fg --max-nash-iter 1 --stackelberg-allocation-mode pso --leader-candidate-count 81 --leader-refinement-candidate-count 49 --stackelberg-prefilter-top-k 8 --stackelberg-prefilter-local-top-k 8 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 8 --grid-parallel-backend thread --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --freeway-prediction-horizon-steps 3
```

P-Stack PSO allocation with fallback disabled, to prevent PFO from being
selected:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand,peak_demand --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\pstack_pso_allocation_no_smooth_no_pfo_fallback_finegrid_medium_peak_7200_2026_06_20_fg --max-nash-iter 1 --stackelberg-allocation-mode pso --leader-candidate-count 81 --leader-refinement-candidate-count 49 --stackelberg-prefilter-top-k 8 --stackelberg-prefilter-local-top-k 8 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 8 --grid-parallel-backend thread --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --freeway-prediction-horizon-steps 3 --disable-stackelberg-fallback
```

P-Stack direct/allocation-off fine-grid attempt:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand,peak_demand --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\pstack_direct_no_smooth_finegrid_medium_peak_7200_2026_06_20_fg --max-nash-iter 1 --stackelberg-allocation-mode direct --leader-candidate-count 81 --leader-refinement-candidate-count 49 --stackelberg-prefilter-top-k 8 --stackelberg-prefilter-local-top-k 8 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 8 --grid-parallel-backend thread --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --freeway-prediction-horizon-steps 3
```

This direct/allocation-off run timed out after 7200 s before completing the
medium-demand Stackelberg run. Only the medium no-control baseline files were
written, so no valid direct P-Stack 7200 s result is available for this
fine-grid setting.

### Results

| Scenario | Controller / mode | Fallback | Total TTT | Improvement vs no-control | Total delay | Throughput veh/h | Terminal vehicles | Mean B_sum | Boundary non-degraded |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| medium | NO-CONTROL | n/a | 1943.962 | 0.000% | 1019.342 | 10690.1 | 2469.8 | 0.189289 | n/a |
| medium | PFO | n/a | 1000.610 | 48.527% | 75.990 | 11720.0 | 418.3 | 0.155851 | yes |
| medium | P-Stack PSO allocation | enabled | 1000.610 | 48.527% | 75.990 | 11720.0 | 418.3 | 0.155851 | yes |
| medium | P-Stack PSO allocation | disabled | 10819.104 | -456.549% | 9894.484 | 6281.0 | 10937.6 | 0.046258 | no |
| peak | NO-CONTROL | n/a | 11659.562 | 0.000% | 10515.542 | 7936.1 | 13488.0 | 0.082207 | n/a |
| peak | PFO | n/a | 3773.909 | 67.632% | 2629.889 | 12894.7 | 3565.7 | 0.159081 | no |
| peak | P-Stack PSO allocation | enabled | 3773.909 | 67.632% | 2629.889 | 12894.7 | 3565.7 | 0.159081 | no |
| peak | P-Stack PSO allocation | disabled | 14732.361 | -26.354% | 13588.341 | 7236.3 | 14889.5 | 0.044965 | yes |

### Diagnosis

- Production 7200 s runs did not inject reverse-engineered PFO targets into the
  leader grid. That injection is confined to the diagnostic script.
- With default fallback enabled, P-Stack PSO allocation exactly matches PFO
  because `leader_fallback_guard_selected_pfo=1.0`; the leader candidate itself
  is rejected by the fallback guard.
- With fallback disabled, PSO allocation does not match PFO, but performance is
  much worse. Early diagnostics show the leader repeatedly selects
  `N_P_star=3219.999...` and `N_UF_star=6000`, i.e. the upper feasible
  protected net-inflow target, causing large terminal urban/on-ramp queues and
  throughput loss.
- The original PSO allocation module is therefore not merely hidden by the
  simplified module. Its leader-candidate objective/search still prefers an
  over-inflow/high-release target when PFO fallback is removed.
- The direct/allocation-off fine-grid path is currently computationally
  infeasible at 7200 s under `leader_candidate_count=81`,
  `leader_refinement_candidate_count=49`, and top-K `8/8`; it did not finish
  one Stackelberg medium scenario within 7200 s wall time.

### Failed Criteria / Next Modification

- FAIL: P-Stack PSO allocation without fallback is worse than no-control in
  both medium and peak.
- FAIL: P-Stack with fallback enabled is not evidence of leader value because
  fallback selects PFO.
- FAIL: Peak PFO/P-Stack fallback result improves TTT but degrades boundary
  balancing.
- Next modification should inspect why the no-fallback leader objective ranks
  the upper `N_P_star` bound so strongly. Candidate fixes:
  1. Add a throughput-shortfall / terminal-urban guard directly to full leader
     candidate evaluation, not only fallback.
  2. Re-rank leader candidates by rollout terminal vehicles and completed
     proxy before accepting high `N_P_star`.
  3. Make allocation-on follower evaluation use a broader green/offset/RM
     neighborhood around the PSO plan, instead of a single allocation seed.
  4. For direct/allocation-off 7200 s, reduce the full rollout burden with a
     cached no-fallback candidate table or a scenario-level checkpoint runner
     before repeating fine-grid runs.

## 2026-06-21 - Leader All-Urban Half-Cap MFD Penalty and Checkpoint Logging

### Implementation

- Added `leader.mfd_penalty_mode` with modes `disabled`, `protected_exceed`,
  `all_urban_halfcap`, and `combined`.
- Set the default mode to `all_urban_halfcap`.
- In `all_urban_halfcap`, the leader adds
  `mfd_storage_weight * sum(max(0, q_i - threshold_ratio * cap_i))` over all
  urban movement queues, including boundary movements, and non-off-ramp urban
  link occupancies. In `follower_ttt` mode this is scaled by `T_c_h`.
- Added `leader.mfd_boundary_queue_capacity_veh=220.0` as a penalty reference
  for boundary movement queues only. The plant queue is not clipped by this
  value.
- Kept the legacy protected-network exceedance term as the
  `protected_exceed` mode instead of deleting it.
- Added step checkpoint files:
  `run_log.csv`, `control_timeseries.csv`, `state_timeseries.csv`,
  `decision_diagnostics.csv`, and `progress_summary.csv` are refreshed after
  each control step.
- Added Stackelberg candidate-progress files:
  `decision_progress.jsonl` and `decision_progress.csv` record fallback,
  coarse, and refined candidate evaluation progress within each long step.

Changed files:

- `src/config/default.yaml`
- `src/models/state.py`
- `src/controllers/leader.py`
- `src/controllers/stackelberg_mpc.py`
- `src/experiments/six_controller_comparison.py`
- `src/simulation/closed_loop_runner.py`
- `src/tests/test_constraints.py`
- `docs/spec/04_controller.md`
- `docs/spec/09_configuration_requirements.md`

### Validation

Syntax compile:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -c "from pathlib import Path; files=['src/controllers/stackelberg_mpc.py','src/experiments/six_controller_comparison.py']; [compile(Path(f).read_text(encoding='utf-8'), f, 'exec') for f in files]; print('syntax compile ok')"
```

Targeted tests:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_leader_all_urban_halfcap_penalty_counts_boundary_and_storage -v
```

Result: PASS.

Checkpoint smoke:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 360 --controllers PROPOSED-FOLLOWERS-ONLY --output outputs/checkpoint_smoke_peak_360_20260621 --leader-candidate-count 9 --leader-refinement-candidate-count 9 --max-nash-iter 1 --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 4 --freeway-prediction-horizon-steps 2
```

Result: PASS. `progress_summary.csv` was written during the run.

Candidate-progress smoke:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 180 --controllers PROPOSED-STACKELBERG --output outputs/candidate_progress_smoke_peak_180_20260621 --leader-candidate-count 5 --leader-refinement-candidate-count 5 --max-nash-iter 1 --stackelberg-prefilter-top-k 2 --stackelberg-prefilter-local-top-k 2 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 2 --stackelberg-allocation-mode direct --grid-parallel-backend thread --grid-parallel-max-workers 2 --grid-parallel-chunk-size 2 --freeway-prediction-horizon-steps 2
```

Result: PASS. `decision_progress.jsonl` and `decision_progress.csv` show
fallback and candidate-stage events within the long first step.

### Peak 1800 s Runs

PFO full run:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 1800 --controllers PROPOSED-FOLLOWERS-ONLY --output outputs/mfd_halfcap_peak_1800_pfo_20260621 --leader-candidate-count 81 --leader-refinement-candidate-count 49 --max-nash-iter 1 --stackelberg-prefilter-top-k 8 --stackelberg-prefilter-local-top-k 8 --stackelberg-fallback-full-refresh-sec 1800 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 8 --stackelberg-inner-backend-when-outer-process thread --grid-parallel-backend thread --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --freeway-prediction-horizon-steps 3
```

P-Stack allocation-on PSO full run:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 1800 --controllers PROPOSED-STACKELBERG --output outputs/mfd_halfcap_peak_1800_pstack_pso_20260621 --leader-candidate-count 81 --leader-refinement-candidate-count 49 --max-nash-iter 1 --stackelberg-prefilter-top-k 8 --stackelberg-prefilter-local-top-k 8 --stackelberg-fallback-full-refresh-sec 1800 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 8 --stackelberg-inner-backend-when-outer-process thread --stackelberg-allocation-mode pso --grid-parallel-backend thread --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --freeway-prediction-horizon-steps 3
```

P-Stack allocation-off direct checkpoint attempt:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 1800 --controllers PROPOSED-STACKELBERG --output outputs/mfd_halfcap_peak_1800_pstack_direct_topk4_20260621 --leader-candidate-count 81 --leader-refinement-candidate-count 49 --max-nash-iter 1 --stackelberg-prefilter-top-k 4 --stackelberg-prefilter-local-top-k 4 --stackelberg-fallback-full-refresh-sec 1800 --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 8 --stackelberg-inner-backend-when-outer-process thread --stackelberg-allocation-mode direct --grid-parallel-backend thread --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --freeway-prediction-horizon-steps 3
```

The direct allocation-off attempt was stopped after 2/10 control steps because
the first two steps already required a long wall-clock time. Partial outputs
are preserved.

| Run | Horizon completed | Total TTT | Total delay | Improvement vs no-control | Throughput veh/h | Terminal vehicles | Computation / wall time |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 1800 s | 605.825 | 324.093 | 0.000% | 10002.1 | 2539.0 | n/a |
| PFO | 1800 s | 451.476 | 169.745 | 25.477% | 11849.9 | 1616.6 | 372.52 / 373.09 s |
| P-Stack allocation on, PSO | 1800 s | 451.476 | 169.745 | 25.477% | 11849.9 | 1616.6 | 457.82 / 458.37 s |
| P-Stack allocation off, direct | 360 s partial | 46.839 cumulative | n/a | same as PFO at 360 s | n/a | n/a | partial only |

### Direct Allocation-Off Candidate Diagnosis

For `outputs/mfd_halfcap_peak_1800_pstack_direct_topk4_20260621`, the first
two completed steps both selected `fallback_pfo`:

| Step | P-Stack cumulative TTT | PFO cumulative TTT | Delta vs PFO | Selected stage | N_P_star | N_UF_star |
|---:|---:|---:|---:|---|---:|---:|
| 0 | 19.856931 | 19.856931 | ~0 | fallback_pfo | 0.0 | 0.0 |
| 1 | 46.839085 | 46.839085 | ~0 | fallback_pfo | 0.0 | 0.0 |

Candidate-progress evidence:

- Step 0 fallback PFO objective: `77.1965`.
- Step 0 coarse/refined direct leader candidates were all worse than fallback
  PFO; the best observed direct candidate objective was `82.7214`.
- Step 1 fallback PFO objective: `91.4487`.
- Step 1 coarse/refined direct leader candidates were all worse than fallback
  PFO; the best observed direct candidate objective was `100.8989`.
- Step 2 began before the run was stopped; fallback PFO objective was
  `103.5099`, while the first coarse direct candidate was `121.8787`.

### Failed Criteria / Next Modification

- PASS: all-urban half-cap MFD penalty mode is implemented without clipping
  plant queues.
- PASS: step-level and candidate-level checkpoint logging works.
- PARTIAL: peak 1800 s PFO and P-Stack PSO allocation-on runs completed.
- PARTIAL: direct allocation-off run did not complete 1800 s due computation
  cost; the partial result indicates fallback PFO dominates the evaluated
  direct candidates.
- NOT RUN: allocation-off fallback-disabled 1800 s was not started after the
  direct fallback-on run showed prohibitive per-step cost.
- Next modification should reduce direct Stackelberg full-evaluation cost before
  repeating fallback-off 1800 s. Candidate options:
  1. Add a safe stage-level cutoff when fallback incumbent is far better and
     evaluated direct candidates plus proxy ranking are consistently worse.
  2. Add scenario-level resume/checkpoint so an interrupted 1800 s run can
     continue from the last completed control step.
  3. Run fallback-off first at 360/900 s with candidate progress to identify
     whether direct leader choices are qualitatively different before spending
     a full 1800 s run.

## 2026-06-21 - Peak 1800 s Direct P-Stack Without Fallback

### Run

User requested the same peak 1800 s direct/allocation-off Stackelberg run with
fallback removed to measure how far it diverges from PFO.

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 1800 --controllers PROPOSED-STACKELBERG --output outputs/mfd_halfcap_peak_1800_pstack_direct_no_fallback_topk4_20260621 --leader-candidate-count 81 --leader-refinement-candidate-count 49 --max-nash-iter 1 --stackelberg-prefilter-top-k 4 --stackelberg-prefilter-local-top-k 4 --stackelberg-fallback-full-refresh-sec 1800 --disable-stackelberg-fallback --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 8 --stackelberg-inner-backend-when-outer-process thread --stackelberg-allocation-mode direct --grid-parallel-backend thread --grid-parallel-max-workers 8 --grid-parallel-chunk-size 8 --freeway-prediction-horizon-steps 3
```

Output:

- `outputs/mfd_halfcap_peak_1800_pstack_direct_no_fallback_topk4_20260621`

### Results

| Run | Total TTT | Total delay | Improvement vs no-control | Throughput veh/h | Terminal vehicles | Computation sec | Wall sec | Delta vs PFO TTT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 605.825 | 324.093 | 0.000% | 10002.1 | 2539.0 | 0.00 | 0.56 | n/a |
| PFO | 451.476 | 169.745 | 25.477% | 11849.9 | 1616.6 | 372.52 | 373.09 | 0.000 |
| P-Stack PSO fallback on | 451.476 | 169.745 | 25.477% | 11849.9 | 1616.6 | 457.82 | 458.37 | 0.000 |
| P-Stack direct fallback off | 471.030 | 189.298 | 22.250% | 12183.9 | 1452.0 | 3374.79 | 3375.57 | +19.554 |

### Step Trace

| Step | Time sec | P-Stack cumulative TTT | PFO cumulative TTT | Delta vs PFO | N_P_star | N_UF_star |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 180 | 19.897 | 19.857 | +0.040 | 3220.0 | 6000.0 |
| 1 | 360 | 48.432 | 46.839 | +1.593 | 3220.0 | 6000.0 |
| 2 | 540 | 82.388 | 77.124 | +5.264 | 3220.0 | 6000.0 |
| 3 | 720 | 121.879 | 111.283 | +10.596 | 3220.0 | 6000.0 |
| 4 | 900 | 166.870 | 150.204 | +16.666 | 3220.0 | 6000.0 |
| 5 | 1080 | 217.044 | 195.270 | +21.774 | 3220.0 | 6000.0 |
| 6 | 1260 | 272.423 | 245.794 | +26.629 | 3220.0 | 6000.0 |
| 7 | 1440 | 332.968 | 304.995 | +27.973 | 3220.0 | 6000.0 |
| 8 | 1620 | 399.435 | 373.938 | +25.498 | -3315.0 | 4500.0 |
| 9 | 1800 | 471.030 | 451.476 | +19.554 | -3315.0 | 4125.0 |

### Diagnosis

- Removing fallback exposes the direct Stackelberg leader/follower choice. It
  does not match PFO.
- For steps 0-7, the direct no-fallback Stackelberg consistently selected the
  upper leader targets `N_P_star ~= 3220` and `N_UF_star = 6000`.
- The cumulative TTT gap against PFO grew from `+0.040` veh*h at 180 s to
  `+27.973` veh*h at 1440 s.
- At steps 8-9, the selected `N_P_star` switched to the lower bound and the gap
  narrowed, but the final 1800 s TTT remained `+19.554` veh*h worse than PFO.
- The no-fallback run still improves over no-control, but less than PFO:
  `22.250%` vs `25.477%` improvement.
- Computation cost is high: `3374.79 s` controller computation for a 1800 s
  peak run.

### Failed Criteria / Next Modification

- FAIL: direct no-fallback P-Stack is worse than PFO on peak 1800 s.
- FAIL: computation cost is too high for iterative diagnostics.
- The next diagnostic should inspect why the direct leader objective ranks the
  high `N_P_star`, high `N_UF_star` candidates best for steps 0-7 despite worse
  closed-loop TTT. Candidate-level logs are available in
  `decision_progress.csv`; the next useful table is per-step selected
  candidate objective decomposition: follower TTT base, MFD storage penalty,
  density penalty, terminal/throughput proxies, and realized next-step TTT.

## 2026-06-21 - Continuous Leader Optimizer Implementation

### Discussion Summary

Added a written discussion record:

- `reports/leader_continuous_optimizer_discussion.md`

The summary records the current diagnosis:

- `N_P_star` and `N_UF_star` are continuous leader targets; grid search was a
  numerical approximation, not a mathematical requirement.
- Dense/fine grid diagnostics showed an intermediate `N_P_star ~= 1819.6`
  candidate nearly tied with the upper-bound `N_P_star ~= 3220` candidate at
  step 0, indicating that coarse grid/top-K filtering can hide useful interior
  regions.
- `leader_candidate_proxy_objective_spread = 0.0` in earlier diagnostics means
  the cheap proxy prefilter may not rank candidates meaningfully; top-K
  candidate ordering can therefore influence which candidates receive full
  follower evaluation.
- Follower actuators remain discrete/quantized where required, so leader search
  should use derivative-free continuous optimization rather than gradient
  descent.

### Implementation

Implemented configurable Stackelberg leader search mode:

```yaml
mpc:
  leader_search_mode: continuous  # continuous | grid
  leader_continuous_max_evals: 25
  leader_continuous_seed_count: 7
  leader_continuous_local_iterations: 4
  leader_continuous_initial_step_fraction: 0.35
  leader_continuous_shrink_factor: 0.5
  leader_continuous_min_np_step_veh: 40.0
  leader_continuous_min_nuf_step_veh_h: 125.0
```

`leader_search_mode=continuous` now evaluates continuous `(N_P_star, N_UF_star)`
targets using deterministic derivative-free pattern search:

1. Build continuous feasible bounds from movement/net-inflow and ramp-release
   constraints.
2. Evaluate seed targets: previous/default, midpoint, heuristic, and bounds.
3. Evaluate coordinate/diagonal local perturbations around the incumbent best.
4. Shrink step size when no improvement is found.
5. Preserve existing follower response, fallback guard, candidate diagnostics,
   and progress logging.

`leader_search_mode=grid` preserves the previous coarse/refined grid path.

Changed files:

- `src/models/state.py`
- `src/config/default.yaml`
- `src/controllers/stackelberg_mpc.py`
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `src/experiments/six_controller_comparison.py`
- `src/experiments/leader_grid_injection_diagnostic.py`
- `src/tests/test_constraints.py`
- `docs/spec/04_controller.md`
- `docs/spec/09_configuration_requirements.md`
- `reports/leader_continuous_optimizer_discussion.md`
- `reports/codex_run_report.md`

### Validation

Syntax compile:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\models\state.py src\controllers\stackelberg_mpc.py src\experiments\all_scenarios_four_controller_comparison.py src\experiments\six_controller_comparison.py src\experiments\leader_grid_injection_diagnostic.py src\tests\test_constraints.py
```

Result: PASS.

Targeted unit tests:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_leader_continuous_search_evaluates_targets src.tests.test_constraints.ConstraintTests.test_stackelberg_leader_evaluates_coarse_and_refined_grid src.tests.test_constraints.ConstraintTests.test_leader_all_urban_halfcap_penalty_counts_boundary_and_storage -v
```

Result: PASS, 3 tests in 3.518 s.

Full `src.tests.test_constraints` was not completed in this turn because the
large test suite exceeded the tool timeout during Stackelberg/distributed
controller tests. The targeted tests above cover the new continuous mode,
legacy grid mode compatibility, and the recent MFD half-cap penalty.

### Distributed Smoke

First distributed smoke with 5 continuous leader evaluations produced output
but exceeded the tool timeout:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 180 --controllers PROPOSED-STACKELBERG --output outputs\continuous_leader_smoke_peak_180_20260621 --leader-search-mode continuous --leader-continuous-max-evals 5 --leader-continuous-seed-count 3 --leader-continuous-local-iterations 1 --max-nash-iter 1 --disable-stackelberg-fallback --stackelberg-allocation-mode direct --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 4 --freeway-prediction-horizon-steps 2
```

Output showed `leader_search_mode_continuous=1`, 5 evaluated leader targets,
and selected `N_P_star=2287.25`, `N_UF_star=6000.0`, but controller compute
time was about 312.6 s for one 180 s step. This confirms the continuous leader
outer loop works, while distributed follower evaluation remains expensive.

Shorter smoke completed successfully:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 180 --controllers PROPOSED-STACKELBERG --output outputs\continuous_leader_smoke_peak_180_evals2_20260621 --leader-search-mode continuous --leader-continuous-max-evals 2 --leader-continuous-seed-count 2 --leader-continuous-local-iterations 0 --max-nash-iter 1 --disable-stackelberg-fallback --stackelberg-allocation-mode direct --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 4 --freeway-prediction-horizon-steps 2
```

Result:

| Run | Horizon | Total TTT | Total delay | Improvement vs no-control | Throughput veh/h | Terminal vehicles | Computation sec |
|---|---:|---:|---:|---:|---:|---:|---:|
| PROPOSED-STACKELBERG continuous | 180 s | 19.991 | -0.522 | 0.941% | 8521.9 | 493.6 | 118.69 |

Diagnostics:

- `leader_search_mode_continuous = 1.0`
- `leader_candidate_full_evaluated_count = 2.0`
- `leader_candidate_coarse_evaluated_count = 2.0`
- `leader_candidate_refined_evaluated_count = 0.0`
- selected `N_P_star = 0.0`
- selected `N_UF_star = 6000.0`
- boundary balance was not degraded vs no-control in this one-step smoke:
  `mean_B_sum = 0.068619` vs no-control `0.111382`

### Failed Criteria / Next Modification

- PASS: continuous leader target search is implemented and configurable.
- PASS: legacy grid leader search remains available via `leader_search_mode=grid`.
- PASS: syntax compile and targeted tests passed.
- PASS: short distributed closed-loop smoke completed.
- PARTIAL: 5-evaluation continuous smoke shows the expected intermediate target
  behavior but is still too expensive for routine closed-loop diagnosis.
- FAIL for final acceptance: no 7200 s scenario comparison was run after this
  implementation.
- Next modification should reduce per-leader-evaluation distributed follower
  cost or add a reliable resume/checkpoint runner before running medium/peak
  1800 s and then 7200 s comparisons with continuous mode.

## 2026-06-21 - Peak 1800 s PFO vs Continuous P-Stack Comparison

### Run

User requested a 1800 s comparison between PFO and the new continuous leader
Stackelberg path. This run uses peak demand, `leader_search_mode=continuous`,
five leader target evaluations per control step, direct allocation mode, and
fallback disabled so the P-Stack result is not masked by PFO fallback.

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 1800 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output outputs\continuous_leader_peak_1800_pfo_pstack_evals5_20260621 --leader-search-mode continuous --leader-continuous-max-evals 5 --leader-continuous-seed-count 3 --leader-continuous-local-iterations 1 --max-nash-iter 1 --disable-stackelberg-fallback --stackelberg-allocation-mode direct --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 4 --freeway-prediction-horizon-steps 2
```

Output:

- `outputs/continuous_leader_peak_1800_pfo_pstack_evals5_20260621`

### Results

| Controller | Total TTT | Total delay | Improvement vs no-control | Throughput veh/h | Completed vehicles | Terminal vehicles | Mean B_sum | Computation sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PROPOSED-FOLLOWERS-ONLY | 451.476 | 169.745 | 25.477% | 11849.9 | 5925.0 | 1616.6 | 0.158910 | 363.76 |
| PROPOSED-STACKELBERG continuous | 468.482 | 186.750 | 22.670% | 12233.7 | 6116.9 | 1411.0 | 0.194264 | 1703.12 |

Delta P-Stack minus PFO:

| Metric | Delta |
|---|---:|
| Total TTT | +17.006 veh*h |
| Total delay | +17.005 veh*h |
| Throughput | +383.8 veh/h |
| Completed vehicles | +191.9 |
| Terminal vehicles | -205.6 |
| Average TTT / completed vehicle | +1.40 s |

Step trace:

| Step | Time sec | PFO cumulative TTT | P-Stack cumulative TTT | Delta | P-Stack N_P_star | P-Stack N_UF_star |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 180 | 19.857 | 19.897 | +0.040 | 2287.25 | 6000.0 |
| 1 | 360 | 46.839 | 48.432 | +1.593 | 2287.25 | 6000.0 |
| 2 | 540 | 77.124 | 82.388 | +5.264 | 2287.25 | 6000.0 |
| 3 | 720 | 111.283 | 121.879 | +10.596 | 2287.25 | 6000.0 |
| 4 | 900 | 150.204 | 166.870 | +16.666 | 2287.25 | 6000.0 |
| 5 | 1080 | 194.731 | 217.044 | +22.313 | 2287.25 | 6000.0 |
| 6 | 1260 | 245.794 | 272.450 | +26.657 | 2247.25 | 4500.0 |
| 7 | 1440 | 304.995 | 333.077 | +28.082 | 2247.25 | 4500.0 |
| 8 | 1620 | 373.938 | 398.789 | +24.852 | 2247.25 | 4500.0 |
| 9 | 1800 | 451.476 | 468.482 | +17.006 | 2207.25 | 6000.0 |

### Diagnosis

- Continuous leader search changed the selected target from the old grid upper
  bound (`N_P_star ~= 3220`) to an interior positive target around
  `N_P_star ~= 2207-2287`.
- However, the selected targets still push strongly toward high protected
  network inflow and high ramp release. P-Stack therefore processes more
  vehicles than PFO (`+191.9` completed vehicles), but Total TTT remains higher.
- Average TTT per completed vehicle is only about `+1.40 s` worse than PFO, so
  part of the TTT increase is explained by higher throughput/vehicle processing.
  Still, under the configured Total TTT criterion, P-Stack continuous fails to
  beat PFO.
- Boundary balance is worse than PFO in this run (`mean_B_sum 0.194264` vs
  `0.158910`), and `boundary_balance_non_degraded_vs_no_control` is false for
  P-Stack.
- Computation cost remains high: `1703.12 s` controller computation for a
  1800 s peak run with only five leader evaluations per step.

### Failed Criteria / Next Modification

- FAIL: P-Stack continuous is worse than PFO on peak 1800 s by `+17.006` veh*h
  Total TTT.
- FAIL: boundary balance degrades relative to no-control/PFO.
- PARTIAL: throughput and completed vehicles improve substantially, so the
  leader may be favoring completion/terminal reduction in a way not captured by
  the final Total TTT target.
- Next diagnostic should inspect per-candidate leader objective decomposition
  for steps 0-5, especially why `N_P_star ~= 2287`, `N_UF_star=6000` beats lower
  `N_P` alternatives under the leader objective even though realized closed-loop
  TTT is worse than PFO.

## 2026-06-21 - Continuous Leader Search Lightweight Guards

### Implementation

User selected the following continuous-search acceleration/diagnosis features:

1. hard feasibility pre-check
2. incumbent-based early termination
3. adaptive top-K equivalent with cheap proxy sampling
4. parallel multi-start full evaluation
5. sensitivity/finite-difference direction generation

Implemented them in the `leader_search_mode=continuous` path only. The legacy
grid path is unchanged.

New configuration keys:

```yaml
mpc:
  leader_continuous_prefilter_samples: 31
  leader_continuous_prefilter_top_k: 7
  leader_continuous_hard_precheck: true
  leader_continuous_precheck_spillback_tolerance_veh: 0.0
  leader_continuous_parallel_multistart: true
  leader_continuous_use_sensitivity_directions: true
```

Continuous leader search now works as:

1. Build deterministic low-discrepancy samples in the continuous
   `(N_P_star, N_UF_star)` feasible box.
2. Score samples with the existing cheap leader proxy.
3. Apply hard spillback pre-check when enabled.
4. Select top-K proxy-ranked targets for full follower evaluation.
5. Reuse the grid path's `_evaluate_candidate_set`, so the first target seeds
   the incumbent and remaining multi-start targets can be evaluated through the
   configured leader backend (`serial`, `thread`, or `process`).
6. Rank local pattern-search directions with cheap proxy scores and insert a
   sensitivity-like direction before evaluating local refinements.

Changed files:

- `src/models/state.py`
- `src/config/default.yaml`
- `src/controllers/stackelberg_mpc.py`
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `src/experiments/six_controller_comparison.py`
- `src/tests/test_constraints.py`
- `docs/spec/04_controller.md`
- `docs/spec/09_configuration_requirements.md`
- `reports/codex_run_report.md`

### Validation

Syntax compile:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\models\state.py src\controllers\stackelberg_mpc.py src\experiments\all_scenarios_four_controller_comparison.py src\experiments\six_controller_comparison.py src\tests\test_constraints.py
```

Result: PASS.

Targeted tests:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_leader_continuous_search_evaluates_targets -v
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_leader_evaluates_coarse_and_refined_grid -v
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_leader_all_urban_halfcap_penalty_counts_boundary_and_storage -v
```

Result: PASS.

Short distributed smoke:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario peak_demand --T-total 180 --controllers PROPOSED-STACKELBERG --output outputs\continuous_leader_prefilter_smoke_peak_180_20260621 --leader-search-mode continuous --leader-continuous-max-evals 2 --leader-continuous-seed-count 2 --leader-continuous-prefilter-samples 5 --leader-continuous-prefilter-top-k 2 --leader-continuous-local-iterations 0 --max-nash-iter 1 --disable-stackelberg-fallback --stackelberg-allocation-mode direct --stackelberg-leader-parallel-backend thread --stackelberg-leader-parallel-max-workers 2 --grid-parallel-backend thread --grid-parallel-max-workers 4 --grid-parallel-chunk-size 4 --freeway-prediction-horizon-steps 2
```

Result:

| Run | Horizon | Total TTT | Improvement vs no-control | Throughput veh/h | Terminal vehicles | Computation sec |
|---|---:|---:|---:|---:|---:|---:|
| P-Stack continuous prefilter smoke | 180 s | 19.991 | 0.941% | 8521.9 | 493.6 | 122.10 |

Continuous diagnostics:

- `leader_continuous_prefilter_active = 1.0`
- `leader_continuous_prefilter_samples = 16.0`
- `leader_continuous_prefilter_proxy_evaluated_count = 16.0`
- `leader_continuous_prefilter_selected_count = 2.0`
- `leader_candidate_full_evaluated_count = 2.0`
- `leader_candidate_parallel_backend_thread = 1.0`
- `leader_candidate_incumbent_any_active = 1.0`
- `leader_candidate_follower_early_terminated_candidates_total = 406.0`
- selected `N_P_star = 0.0`, `N_UF_star = 6000.0`

### Failed Criteria / Next Modification

- PASS: selected continuous-search safeguards are implemented and logged.
- PASS: legacy grid path still passes the targeted compatibility test.
- PASS: short distributed smoke completed.
- NOT RUN: 1800 s PFO/P-Stack comparison after these new safeguards.
- Next run should repeat the peak 1800 s PFO vs P-Stack continuous comparison
  with `leader_continuous_prefilter_samples` and `leader_continuous_prefilter_top_k`
  enabled, then inspect whether the selected targets move away from the previous
  high-release pattern.
