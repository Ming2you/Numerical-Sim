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

## 2026-06-21 - Leader follower-TTT fidelity probe

### Purpose

Claude's boundary-queue hypothesis was set aside. The diagnostic question was
whether the Stackelberg leader's `leader_follower_ttt_base` is faithful to the
actual plant TTT/TTS observed after applying the selected control.

### Commands

Existing 1800 s peak continuous P-Stack output was re-read:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -c "<csv correlation probe>" `
  # input: outputs\continuous_leader_peak_1800_pfo_pstack_evals5_20260621\runs\peak_demand\PROPOSED-STACKELBERG
```

A current-code smoke probe was also run with a small leader evaluation budget:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" C:\tmp\fidelity_probe_current.py `
  --scenario peak_demand `
  --seconds 900 `
  --max-evals 1 `
  --prefilter-samples 5 `
  --prefilter-top-k 1 `
  --output-dir outputs\fidelity_probe_current_peak_900_evals1_20260621
```

### Results

Existing 1800 s peak P-Stack continuous output:

| Comparison | Rows | Correlation | Mean ratio | Mean abs error |
|---|---:|---:|---:|---:|
| `leader_follower_ttt_base` vs same-step plant TTT | 10 | 0.9995 | 3.419 | n/a |
| `leader_follower_ttt_base` vs complete 3-step rolling plant TTT | 8 | 0.999999 | 1.002 | 0.272 veh*h |

Current-code 900 s peak smoke (`leader_continuous_max_evals=1`):

| Comparison | Rows | Correlation | Mean ratio | Mean abs error |
|---|---:|---:|---:|---:|
| `leader_follower_ttt_base` vs same-step plant TTT | 5 | 0.9906 | 3.503 | n/a |
| `leader_follower_ttt_base` vs complete 3-step rolling plant TTT | 3 | 0.999891 | 1.007 | 0.617 veh*h |

The same-step comparison is expected to be roughly 3x larger because
`leader_follower_ttt_base` is an MPC-horizon cost while `step_total_ttt` is a
single control interval. When compared against the complete 3-step rolling
plant TTT, the selected-control fidelity is very high.

### Diagnosis

- PASS: for selected controls, `leader_follower_ttt_base` is effectively a
  3-step plant TTT/TTS proxy under the current model and logging.
- This does not support the hypothesis that P-Stack is worse because
  `follower_ttt_base` omits a large part of realized plant TTT.
- Remaining likely causes are candidate/ranking effects rather than
  selected-action accounting: finite horizon, leader target feasible-set
  restrictions, release/throughput tradeoff, continuous-search budget, or
  penalties shaping the selected target.
- NOT VERIFIED by this probe: counterfactual candidate-level fidelity. A next
  diagnostic should compare candidate objective rankings against actual
  counterfactual rollouts from the same initial state.

## 2026-06-23 - Stackelberg-RL Rollout Export 보강

### 구현

Stackelberg-RL Milestone 1 환경 wrapper의 in-memory 기록을 파일로 보존하는
export 유틸을 추가했다. `export_rollout_records(records, output_dir)`는 다음
두 파일을 저장한다.

- `rl_rollout_steps.jsonl`: step별 leader target, follower local observations,
  follower action, physical `ControlAction`, leader/follower reward, simulator
  diagnostics를 중첩 JSON 구조로 저장한다.
- `rl_rollout_summary.csv`: step별 leader target, global step TTT, reward,
  follower count, control/simulator diagnostics를 빠르게 확인하는 요약 표로
  저장한다.

이 보강은 spec 19의 “leader target -> follower response -> plant outcome”
사후 재구성 요구사항을 파일 산출물 수준으로 맞추기 위한 것이다. neural
DDQN/torch/gymnasium training은 아직 추가하지 않았다.

### 변경 파일

- `src/rl/env.py`
- `src/rl/__init__.py`
- `src/tests/test_rl_environment.py`
- `reports/codex_run_report.md`

### 검증

이 세션에는 기존 기록에 있던 Codex Python 런타임
`C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
가 없어서, `winget`으로 Python 3.12.10을 사용자 범위에 설치하고 `numpy`
2.5.0을 추가 설치했다.

실행 명령:

```powershell
winget install --id Python.Python.3.12 --exact --scope user --accept-package-agreements --accept-source-agreements --silent
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pip install numpy
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -B -m py_compile src\rl\__init__.py src\rl\agents.py src\rl\action_space.py src\rl\observations.py src\rl\rewards.py src\rl\env.py src\tests\test_rl_environment.py
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -B -m unittest src.tests.test_rl_environment -v
```

결과:

- `py_compile`: PASS
- `src.tests.test_rl_environment`: PASS, 6 tests OK

추가한 테스트:

- `StackelbergRLEnvironmentTest.test_rollout_export_preserves_reconstruction_keys`

### Metrics / Acceptance

- Baseline run command: N/A, logging utility 보강.
- Proposed-controller run command: N/A, logging utility 보강.
- Baseline Total TTT/TTS: N/A.
- Proposed Total TTT/TTS: N/A.
- Improvement rate: N/A.
- Boundary queue balancing result: N/A.
- Control validation summary: RL environment compile과 targeted unit tests PASS.
- Failed criteria: final controller acceptance와 neural training은 범위 밖이며
  실행되지 않았다.
- Proposed next modification: follower pretraining용 replay/sample export 또는
  Phase 1 scaffold를 추가한다.

## 2026-06-23 - Stackelberg-RL Follow-up Foundation

### Milestone 1 Summary

The current Stackelberg-RL foundation preserves the required decision order: leader target -> follower local observation/action -> projected physical `ControlAction` -> plant outcome -> leader/follower rewards.

- `StackelbergRLEnvironment` wraps `MixedTrafficSimulator`.
- Leader action is a DDQN-ready discrete `(N_P_star, N_UF_star)` target index.
- Follower actions are DDQN-ready local discrete actions: freeway segment VSL/RM and urban intersection green/offset.
- Follower observations remain local to owned links, ramps, movements, signals, connected coupling summaries, previous local action, and leader target.
- Intersection `E` remains passive/no-control and is not emitted as an RL actor.
- Leader reward uses global step TTT plus freeway density excess and urban half-cap storage terms.
- Follower rewards use local TTS-compatible costs.
- VSL requests are projected through `max_vsl_step` and physical VSL bounds.
- No neural DDQN, torch, gymnasium, or training loop was added.

### This Follow-up Implementation

- Added `src/experiments/rl_stackelberg_smoke.py`.
  - Runs scripted or random safe Stackelberg-RL rollouts.
  - Loads real scenarios from `src/config/scenarios.yaml`.
  - Writes `rl_step_records.csv`, `rl_rewards.csv`, `rl_actions.csv`, `rl_observations_summary.csv`, and `metadata.json`.
  - Includes `epsilon_Nash_hat` and best-deviation fields in `rl_step_records.csv`.
- Added `src/rl/replay.py`.
  - Defines `RLTransition` with `episode`, `step`, `agent_id`, `agent_family`, `observation`, `action_index`, `reward`, `next_observation`, `done`, and `info`.
  - Schema accepts both leader and follower transitions.
- Added/kept `src/rl/nash_probe.py`.
  - Implements a one-step local follower Nash residual probe.
  - For fixed leader target and fixed other-follower actions, varies each follower's local discrete action through the normal projection/simulator path.
  - Returns/logs `epsilon_Nash_hat`, best deviating agent id, realized reward, best unilateral reward, best unilateral action index, realized action index, and candidate rewards.
- Updated `src/rl/__init__.py`.
  - Exposes `RLTransition`, `NashProbeResult`, and `probe_follower_nash_residual`.
- Updated `src/rl/action_space.py`.
  - Stores leader action-space bin metadata for probe/smoke reuse.
- Updated `src/tests/test_rl_environment.py`.
  - Covers requested smoke output files, replay leader/follower schema, nonnegative Nash residual, passive/no-control `E`, and existing VSL `max_vsl_step` projection.

### Smoke Output

Output root:

```text
outputs\rl_stackelberg_smoke_medium
```

Written files:

- `metadata.json`
- `rl_step_records.csv`
- `rl_rewards.csv`
- `rl_actions.csv`
- `rl_observations_summary.csv`

Sanity check:

- `metadata.json`: `scenario=medium_demand`, `policy=scripted`, `actual_steps=2`, `seed=42`.
- `rl_step_records.csv`: 2 rows, `follower_count=13`, `epsilon_Nash_hat=0.0` for the scripted neutral rollout rows.

### Verification

The literal requested wildcard compile command was attempted with the available local Python runtime path and failed because `py_compile` received `src\rl\*.py` as a literal path in this PowerShell/native-command environment:

```powershell
& 'C:\Users\alsrj\AppData\Local\Programs\Python\Python312\python.exe' -B -m py_compile src\rl\*.py src\experiments\rl_stackelberg_smoke.py src\tests\test_rl_environment.py
```

Result:

```text
[Errno 22] Invalid argument: 'src\\rl\\*.py'
```

Equivalent expanded compile command:

```powershell
& 'C:\Users\alsrj\AppData\Local\Programs\Python\Python312\python.exe' -B -m py_compile src\rl\__init__.py src\rl\agents.py src\rl\action_space.py src\rl\env.py src\rl\nash_probe.py src\rl\observations.py src\rl\replay.py src\rl\rewards.py src\experiments\rl_stackelberg_smoke.py src\tests\test_rl_environment.py
```

Result: PASS.

Unit tests:

```powershell
& 'C:\Users\alsrj\AppData\Local\Programs\Python\Python312\python.exe' -B -m unittest src.tests.test_rl_environment -v
```

Result: PASS, 10 tests OK.

Smoke run with a valid scenario:

```powershell
& 'C:\Users\alsrj\AppData\Local\Programs\Python\Python312\python.exe' -B -m src.experiments.rl_stackelberg_smoke --scenario medium_demand --steps 2 --policy scripted --output outputs\rl_stackelberg_smoke_medium
```

Result: PASS. The command printed paths for all requested output files.

### Reviewer Verdict And Next Work

- Coding subagent implemented the smoke/replay/probe foundation and reported PASS on local compile, unit tests, and smoke run.
- Reviewer subagent initially returned FAIL on two issues:
  - Nash residual selected highest absolute best reward instead of highest unilateral improvement.
  - Observation summary did not persist the actual feature vector.
- A second reviewer returned FAIL on one additional issue:
  - Nash probe restored only state and lost simulator accumulators/logs at step > 0.
- All three issues were fixed:
  - `src/rl/nash_probe.py` now selects `max_i(max(best_i - realized_i, 0))`.
  - `rl_observations_summary.csv` now includes `features` JSON.
  - `src/rl/nash_probe.py` snapshots/restores `env.sim.copy()` and tests preserve simulator accumulators/logs.
- Final reviewer verdict: PASS.
  - Reconstruction logging: PASS.
  - DDQN-ready `RLTransition`: PASS.
  - One-step unilateral Nash probe and state restoration: PASS.
  - Locality / E passive preservation: PASS.
  - Regression tests: PASS.
- Next foundation step remains follower pretraining/replay sample generation; neural DDQN training is still intentionally out of scope.

## 2026-06-23 - Stackelberg-RL Leader N_P Grid Follow-up

### Review Item Addressed

`reports/rl_code_review_2026-06-23.md` flagged the first DDQN-ready leader
`N_P_star` grid as too wide and too coarse because it inherited the full MPC
physical range `[-3500, 3500]`. With 5 bins this produced mostly unreachable
targets and left little resolution in the useful few-hundred-vehicle range.

### Implementation

- Updated `src/rl/action_space.py`.
  - `LeaderDiscreteActionSpace` now keeps the broad configured
    `leader.N_P_star_range` as a physical clipping bound.
  - The default DDQN pilot vocabulary for `N_P_star` is compacted to
    `[-100, 1000]`.
  - With the default 5 bins, leader `N_P_star` values are now
    `[-100, 175, 450, 725, 1000]`.
  - `N_UF_star` remains on the configured `[0, 6000]` grid because the review
    found that axis still has useful leverage.
- Updated `src/tests/test_rl_environment.py`.
  - Added `test_leader_np_grid_uses_compact_ddqn_vocabulary`.
  - The test verifies the compact DDQN `N_P_star` values remain inside the
    configured physical range while no longer using the extreme
    `[-3500, 3500]` endpoints.

### Verification

```powershell
& 'C:\Users\alsrj\AppData\Local\Programs\Python\Python312\python.exe' -B -m py_compile src\rl\__init__.py src\rl\agents.py src\rl\action_space.py src\rl\observations.py src\rl\rewards.py src\rl\env.py src\rl\replay.py src\rl\nash_probe.py src\experiments\rl_stackelberg_smoke.py src\tests\test_rl_environment.py
```

Result: PASS.

```powershell
& 'C:\Users\alsrj\AppData\Local\Programs\Python\Python312\python.exe' -B -m unittest src.tests.test_rl_environment -v
```

Result: PASS, 11 tests OK.

```powershell
& 'C:\Users\alsrj\AppData\Local\Programs\Python\Python312\python.exe' -B -m src.experiments.rl_stackelberg_smoke --scenario medium_demand --steps 2 --policy scripted --output outputs\rl_stackelberg_smoke_medium
```

Result: PASS. The smoke log now records the scripted neutral leader target as
`N_P_star=450`, `N_UF_star=3000`, which is the midpoint of the compact DDQN
pilot target vocabulary.

## 2026-06-23 - Cheap Replay Dataset Collection Scaffold

### Purpose

Instead of starting expensive neural DDQN training immediately, this update
adds a low-cost path for accumulating replay data while rollout/training code is
running. The intent is to let future follower/leader learners append
transitions step-by-step, then train offline or in small batches from saved
JSONL data.

### Implementation

- Updated `src/rl/replay.py`.
  - Added `ReplayDatasetWriter`, an append-only streaming writer.
  - Writes full transitions to `rl_transitions.jsonl`.
  - Writes a small scan-friendly `rl_transition_index.csv`.
  - Writes `metadata.json` with scenario/policy/run metadata and transition
    count.
  - Added `transitions_from_env_step(episode, step_result)` to convert one
    `StackelbergRLEnvironment.step(...)` result into one leader transition plus
    one transition per follower.
  - Each transition stores observation features, action index, reward,
    next-observation features, done flag, and compact info payload.
- Added `src/experiments/rl_collect_replay_dataset.py`.
  - Runs cheap scripted or random safe rollouts.
  - Streams replay transitions as the rollout proceeds.
  - This is deliberately a data collection entry point, not a neural training
    loop.
- Updated `src/experiments/rl_stackelberg_smoke.py`.
  - Added optional `--replay-output`.
  - Existing smoke runs can now write replay transitions while they run.
  - CLI output includes `replay_transitions`, `replay_index`, and
    `replay_metadata` paths when the option is used.
- Updated `src/rl/__init__.py`.
  - Exposes `ReplayDatasetWriter` and `transitions_from_env_step`.
- Updated `src/tests/test_rl_environment.py`.
  - Added tests for streaming replay transition files and replay dataset
    collector output.
  - Added a smoke-run test for the optional replay stream.

### Verification

```powershell
& 'C:\Users\alsrj\AppData\Local\Programs\Python\Python312\python.exe' -B -m py_compile src\rl\__init__.py src\rl\agents.py src\rl\action_space.py src\rl\observations.py src\rl\rewards.py src\rl\env.py src\rl\replay.py src\rl\nash_probe.py src\experiments\rl_stackelberg_smoke.py src\experiments\rl_collect_replay_dataset.py src\tests\test_rl_environment.py
```

Result: PASS.

```powershell
& 'C:\Users\alsrj\AppData\Local\Programs\Python\Python312\python.exe' -B -m unittest src.tests.test_rl_environment -v
```

Result: PASS, 14 tests OK after adding the smoke replay stream test.

```powershell
& 'C:\Users\alsrj\AppData\Local\Programs\Python\Python312\python.exe' -B -m src.experiments.rl_collect_replay_dataset --scenario medium_demand --episodes 1 --steps 2 --policy scripted --output outputs\rl_replay_dataset_medium
```

Result: PASS.

Generated files:

- `outputs\rl_replay_dataset_medium\rl_transitions.jsonl`
- `outputs\rl_replay_dataset_medium\rl_transition_index.csv`
- `outputs\rl_replay_dataset_medium\metadata.json`
- `outputs\rl_replay_dataset_medium\run_summary.json`

Sanity check: 1 episode x 2 environment steps x 14 agents
(leader + 13 followers) produced 28 replay transitions.

Smoke-run replay stream:

```powershell
& 'C:\Users\alsrj\AppData\Local\Programs\Python\Python312\python.exe' -B -m src.experiments.rl_stackelberg_smoke --scenario medium_demand --steps 1 --policy scripted --output outputs\rl_stackelberg_smoke_replay_check --replay-output outputs\rl_replay_from_smoke_check --T-total 360
```

Result: PASS. The smoke command produced the normal smoke CSV files and replay
dataset files in parallel.

Sanity check: 1 smoke step x 14 agents produced 14 replay transitions in
`outputs\rl_replay_from_smoke_check\metadata.json`.

## 2026-06-24 - Capacity Drop Step 2 Hysteresis Gate

### Purpose

`reports/capacity_drop_handoff_for_codex.md` requested Step 2 before any
scenario matrix rerun: turn on the Arora-Kattan anticipation-regime split,
tune `metanet_nu_cong_km2_h`, drive the plant with rise-fall demand, and verify
that a flow-density hysteresis loop is actually visible. If the loop is not
visible, Step 3 must stop.

### Implementation

- Added `2026-06-24/diag_scripts/capacity_drop_hysteresis_probe.py`.
- The diagnostic script leaves `src/config/default.yaml` unchanged.
- Runtime overrides only:
  - `capacity_drop_anticipation=true/false`.
  - `metanet_nu_cong_km2_h` sweep.
  - `freeway_offramp_capacity_drop.enabled=false`.
  - `off_ramp_split_ratio=0` to isolate anticipation capacity-drop from
    off-ramp lane-loss spillback.
- The script uses the existing `freeway_substep` plant and records
  `rho`, `speed`, and `flow=rho*speed*lanes` for a probe segment under
  rise-fall mainline/ramp demand.
- It writes:
  - `outputs/capacity_drop_hysteresis_step2_final/summary.csv`
  - `outputs/capacity_drop_hysteresis_step2_final/trajectory_*.csv`
  - `reports/figures/fig_capacity_drop_hysteresis_step2_final.png`

### Final Gate Run

Preliminary demand sweeps showed two unhelpful regimes:

- Strong surge: the merge segment saturated near `rho_max`, so the plot showed
  gridlock/saturation rather than a clean capacity-drop loop.
- Weak surge: density never crossed `rho_crit`.

Final near-critical probe command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --out-dir outputs\capacity_drop_hysteresis_step2_final --figure reports\figures\fig_capacity_drop_hysteresis_step2_final.png --mainline-low 2100 --mainline-peak 3600 --ramp-low 0 --ramp-peak 250 --total-sec 5400 --probe-segment 3
```

Final summary:

| case | nu_cong | drop_pct | loop_gap_veh_h | overlap_bins | has_loop |
|---|---:|---:|---:|---:|---:|
| toggle_off | 250 | -0.052 | 30.690 | 4 | 0 |
| nu_cong_65 | 65 | -0.052 | 30.690 | 4 | 0 |
| nu_cong_100 | 100 | -0.041 | 34.420 | 4 | 0 |
| nu_cong_150 | 150 | -0.031 | 38.997 | 4 | 0 |
| nu_cong_250 | 250 | -5.330 | 44.101 | 4 | 0 |

### Gate Verdict

FAIL for Step 2. The final probe has density overlap between loading and
unloading branches, but no tested `nu_cong` produces the target `5-15%`
congested discharge drop or a closed hysteresis loop. Therefore Step 3
scenario redesign and 4-controller matrix rerun were not executed.

Likely cause: the local `rho > rho_crit -> nu_cong` split has no memory. The
anticipation term reduces speed when downstream density is higher, but in
unloading conditions downstream density can be lower, so increasing `nu` may
accelerate discharge rather than create a persistent capacity-drop branch.

Proposed next modification:

- Add an explicit hysteresis state with recovery threshold
  `rho_recover < rho_crit`, or
- Add a demand-supply/discharge capacity-drop term that activates after
  breakdown and recovers only below a lower threshold.

In both options, preserve the density conservation equation.

### Verification

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py"
```

Result: PASS.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_capacity_drop src.tests.test_metanet_equations
```

Result: PASS, 24 tests OK.

### Follow-up: Very-Heavy Demand With `nu_cong=150`

User requested a much heavier vehicle load while fixing `nu_cong=150`.

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --out-dir outputs\capacity_drop_hysteresis_very_heavy_nu150 --figure reports\figures\fig_capacity_drop_hysteresis_very_heavy_nu150.png --nu-values 150 --mainline-low 3000 --mainline-peak 6000 --ramp-low 500 --ramp-peak 3000 --total-sec 5400 --probe-segment 3
```

Summary:

| case | drop_pct | loop_gap_veh_h | overlap_bins | has_loop |
|---|---:|---:|---:|---:|
| toggle_off | 57.846 | -3.380 | 1 | 0 |
| nu_cong_150 | 58.673 | -2.349 | 1 | 0 |

Additional state check:

- Probe segment saturated near `rho_max`: toggle off 457/540 steps,
  `nu_cong_150` 462/540 steps above `0.9*rho_max`.
- Final speed was `v_min=5 km/h` and final probe flow was approximately
  `1751 veh/h` in both cases.
- Final mainline origin queue was about `4.6k veh`, and total ramp queue about
  `11.0k veh`.

Interpretation: under very-heavy demand, a large discharge reduction appears,
but it appears in both toggle-off and `nu_cong=150` cases and is dominated by
gridlock/saturation. This does not satisfy the hysteresis gate and does not
demonstrate an anticipation-regime capacity drop.

### Follow-up: Paper Eq. (6) Boundary-Flow Diagnostic

User asked to implement the paper's Eq. (6) as separate code and rerun the
hysteresis check. I added a diagnostic-only `--plant-mode eq6` to
`2026-06-24/diag_scripts/capacity_drop_hysteresis_probe.py`, leaving the core
plant unchanged.

Eq. (6) diagnostic rule:

- Downstream free: `q_i = min(Q_cap, v_i * rho_i * lanes)`.
- Downstream congested: `q_i = min(v_{i+1} * rho_{i+1} * lanes, v_i * rho_i * lanes)`.
- Density conservation and speed update still use the existing code units and
  functions.

Verification:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py"
```

Result: PASS.

Near-critical Eq6 run:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --plant-mode eq6 --out-dir outputs\capacity_drop_hysteresis_eq6_step2_final --figure reports\figures\fig_capacity_drop_hysteresis_eq6_step2_final.png --nu-values 150 --mainline-low 2100 --mainline-peak 3600 --ramp-low 0 --ramp-peak 250 --total-sec 5400 --probe-segment 3
```

| case | drop_pct | loop_gap_veh_h | overlap_bins | has_loop |
|---|---:|---:|---:|---:|
| toggle_off | nan | 77.840 | 3 | 0 |
| nu_cong_150 | nan | -0.734 | 3 | 0 |

Very-heavy Eq6 run:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --plant-mode eq6 --out-dir outputs\capacity_drop_hysteresis_eq6_very_heavy_nu150 --figure reports\figures\fig_capacity_drop_hysteresis_eq6_very_heavy_nu150.png --nu-values 150 --mainline-low 3000 --mainline-peak 6000 --ramp-low 500 --ramp-peak 3000 --total-sec 5400 --probe-segment 3
```

| case | drop_pct | loop_gap_veh_h | overlap_bins | has_loop |
|---|---:|---:|---:|---:|
| toggle_off | nan | 15.187 | 1 | 0 |
| nu_cong_150 | 11.550 | 26.404 | 1 | 0 |

Loop-like 10-minute aggregate Eq6 run:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --plant-mode eq6 --out-dir outputs\capacity_drop_hysteresis_eq6_best_looplike_nu150 --figure reports\figures\fig_capacity_drop_hysteresis_eq6_best_looplike_nu150.png --nu-values 150 --mainline-low 2400 --mainline-peak 3200 --ramp-low 0 --ramp-peak 500 --total-sec 9000 --probe-segment 3
```

| case | drop_pct | loop_gap_veh_h | overlap_bins | has_loop |
|---|---:|---:|---:|---:|
| toggle_off | nan | 56.477 | 1 | 0 |
| nu_cong_150 | -4.330 | 75.416 | 4 | 0 |

Generated Figure-7-style 600 s aggregate plot:

- `reports/figures/fig_capacity_drop_hysteresis_eq6_best_looplike_nu150_aggregate.png`

Interpretation:

- Eq. (6) boundary-flow makes the loading/unloading trajectory visibly more
  loop-like than the existing CTM receiving plant.
- It still does not reproduce a valid capacity-drop hysteresis loop with
  `nu_cong=150`: the best overlap case has negative drop, and the very-heavy
  case has target-sized drop but only one overlap bin.
- This supports the distinction found in the paper: Figure 7 is a 10-minute
  aggregate VISSIM no-control vs VSL-HSR plot, not a direct output guaranteed
  by Eq. (9) alone. Microscopic driver/platoon behavior, calibrated segment
  parameters, and/or explicit breakdown-recovery memory are likely needed.

### Follow-up: Eq6 `nu_cong=65..150` Step-5 Sweep

User observed that `nu_cong=65..150` looked most natural and requested a
5-unit search over that range. I reused the same loop-like Eq6 diagnostic
condition:

- `plant-mode=eq6`
- `mainline-low=2400`, `mainline-peak=3200`
- `ramp-low=0`, `ramp-peak=500`
- `T_total=9000 s`
- `probe-segment=3`
- 600 s aggregate plotting to match the paper's Figure 7 style.

Command:

```powershell
$nu = ((65..150) | Where-Object { ($_ - 65) % 5 -eq 0 }) -join ','
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --plant-mode eq6 --out-dir outputs\capacity_drop_hysteresis_eq6_nu65_150_step5 --figure reports\figures\fig_capacity_drop_hysteresis_eq6_nu65_150_step5_raw.png --nu-values $nu --mainline-low 2400 --mainline-peak 3200 --ramp-low 0 --ramp-peak 500 --total-sec 9000 --probe-segment 3
```

Summary:

| nu_cong | drop_pct | loop_gap_veh_h | overlap_bins | has_loop |
|---:|---:|---:|---:|---:|
| off/65 | nan | 56.5 | 1 | 0 |
| 70 | nan | 90.5 | 2 | 0 |
| 75 | nan | 39.1 | 1 | 0 |
| 80 | nan | 81.4 | 2 | 0 |
| 85 | nan | 83.3 | 3 | 0 |
| 90 | nan | 73.1 | 3 | 0 |
| 95 | nan | 74.0 | 3 | 0 |
| 100 | nan | 74.4 | 4 | 0 |
| 105 | nan | 65.3 | 4 | 0 |
| 110 | nan | 56.2 | 4 | 0 |
| 115 | 0.23 | 63.6 | 4 | 0 |
| 120 | 0.51 | 69.4 | 4 | 0 |
| 125 | 1.01 | 71.7 | 4 | 0 |
| 130 | 1.54 | 70.9 | 4 | 0 |
| 135 | 2.10 | 80.6 | 4 | 0 |
| 140 | 2.62 | 93.9 | 4 | 1 |
| 145 | nan | 61.8 | 4 | 0 |
| 150 | -4.33 | 75.4 | 4 | 0 |

Generated plots:

- `reports/figures/fig_capacity_drop_hysteresis_eq6_nu65_150_step5_common.png`
- `reports/figures/fig_capacity_drop_hysteresis_eq6_nu65_150_step5_autoscale.png`

Interpretation:

- Visually, the Eq6 boundary-flow diagnostic is much more plausible than the
  current CTM-receiving dynamics for reproducing a Figure-7-like loop.
- `nu_cong=115..140` is the smoothest-looking range.
- `nu_cong=140` is the only value in this sweep marked as `has_loop=1` by the
  current heuristic.
- The capacity-drop magnitude is still weak: the largest positive drop in the
  natural range is `2.62%`, below the earlier 5-15% target.

### Follow-up: Fixed-VSL Preliminary Effect In Eq6 Mode

User asked whether the modified Eq6 METANET dynamics would give VSL an
inflow-control effect. I added a diagnostic-only `--fixed-vsl` option and ran a
small sweep with the same loop-like Eq6 condition and `nu_cong=140`.

Command pattern:

```powershell
$vals = 100,90,80,70,60
foreach ($v in $vals) {
  & "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --plant-mode eq6 --out-dir "outputs\capacity_drop_hysteresis_eq6_vsl_prelim\vsl_$v" --figure "reports\figures\fig_capacity_drop_hysteresis_eq6_vsl_prelim_$v.png" --nu-values 140 --fixed-vsl $v --mainline-low 2400 --mainline-peak 3200 --ramp-low 0 --ramp-peak 500 --total-sec 9000 --probe-segment 3
}
```

Generated:

- `outputs/capacity_drop_hysteresis_eq6_vsl_prelim/vsl_prelim_comparison.csv`
- `reports/figures/fig_capacity_drop_hysteresis_eq6_vsl_prelim_aggregate.png`

Summary:

| VSL | drop_pct | loop_gap_veh_h | overlap_bins | has_loop | max_rho | mean_flow |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 2.62 | 93.86 | 4 | 1 | 38.13 | 3561.64 |
| 90 | 2.62 | 93.86 | 4 | 1 | 38.13 | 3561.45 |
| 80 | 2.73 | 101.24 | 5 | 1 | 38.21 | 3558.83 |
| 70 | 1.13 | 93.76 | 7 | 1 | 39.44 | 3550.33 |
| 60 | 0.83 | 78.94 | 7 | 0 | 39.55 | 3546.30 |

Interpretation:

- VSL 90 is effectively identical to VSL 100 in this condition, likely because
  the no-VSL desired speed is already below the cap for much of the critical
  period.
- VSL 80 produces the clearest mild inflow-control signature: slightly lower
  mean flow, more overlap bins, and a slightly larger loop gap.
- VSL 70/60 reduce mean flow further but do not reduce max density in this
  probe; they look more like stronger holding/delay redistribution.
- This is only a diagnostic fixed-VSL probe, not a closed-loop controller
  performance result.

### Follow-up: Upstream-Only VSL Preliminary Probe

User noted that VSL should be tested upstream of the bottleneck rather than on
the already-slow probe segment. I extended the diagnostic script with
`--fixed-vsl-segments` and logged `probe_inflow_veh_h` from the Eq6
inter-segment boundary flow into the probe segment.

Verification:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py"
```

Result: PASS.

Condition:

- `plant-mode=eq6`
- `nu_cong=140`
- `mainline-low=2400`, `mainline-peak=3200`
- `ramp-low=0`, `ramp-peak=500`
- `T_total=9000 s`
- `probe-segment=3`

Generated:

- `outputs/capacity_drop_hysteresis_eq6_vsl_upstream_prelim/upstream_vsl_comparison.csv`
- `reports/figures/fig_capacity_drop_hysteresis_eq6_vsl_upstream_prelim.png`

Summary:

| case | drop_pct | loop_gap | bins | mean probe inflow | mean probe flow | max rho |
|---|---:|---:|---:|---:|---:|---:|
| VSL100 all | 2.62 | 93.86 | 4 | 3552.0 | 3561.6 | 38.13 |
| VSL80 all | 2.73 | 101.24 | 5 | 3550.3 | 3558.8 | 38.21 |
| VSL80 seg0-2 | 2.73 | 101.24 | 5 | 3550.3 | 3558.8 | 38.21 |
| VSL80 seg2 | 2.73 | 101.24 | 5 | 3550.3 | 3558.8 | 38.21 |
| VSL70 all | 1.13 | 93.76 | 7 | 3548.2 | 3550.3 | 39.44 |
| VSL70 seg0-2 | 1.13 | 93.76 | 7 | 3548.2 | 3550.3 | 39.44 |
| VSL70 seg2 | 1.13 | 93.76 | 7 | 3548.2 | 3550.3 | 39.44 |

Interpretation:

- Eq6 does create a VSL inflow-control channel, but the effect is weak in this
  demand/probe condition.
- VSL80 gives the cleanest mild effect: slightly lower probe inflow/flow and
  larger loop gap/overlap.
- VSL70 lowers flow a bit more but increases max density, suggesting stronger
  holding rather than clear congestion relief.
- Applying VSL to all segments, segments 0-2, or only immediate upstream
  segment 2 gives identical results here. The key channel is segment-2 sending
  into the probe segment.

### No-Control Peak Segment FD With Storage Receiving Cap

User asked for freeway segment-level FD plots under the no-control
`peak_demand` scenario using the plant with receiving/storage cap. I added
`2026-06-24/diag_scripts/no_control_peak_segment_fd.py` to trace the actual
coupled plant at every 10 s freeway substep instead of relying on the standard
closed-loop runner's link-mean state output.

This diagnostic uses the real coupled plant path: urban substeps, on-ramp queue
sync, actual ramp release, off-ramp storage scheduling, and the existing
METANET receiving/storage cap in `src/models/metanet.py`.

Verification:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "2026-06-24\diag_scripts\no_control_peak_segment_fd.py"
```

Result: PASS.

Run:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\no_control_peak_segment_fd.py" --scenario peak_demand --out-dir "outputs\no_control_peak_segment_fd_storage_cap" --figure "reports\figures\fig_no_control_peak_segment_fd_storage_cap.png"
```

Generated:

- `outputs/no_control_peak_segment_fd_storage_cap/segment_fd_timeseries.csv`
- `outputs/no_control_peak_segment_fd_storage_cap/segment_fd_aggregate.csv`
- `outputs/no_control_peak_segment_fd_storage_cap/segment_fd_summary.csv`
- `outputs/no_control_peak_segment_fd_storage_cap/control_interval_summary.csv`
- `reports/figures/fig_no_control_peak_segment_fd_storage_cap.png`

Summary:

| link | seg | max rho | final rho | mean flow | max flow | min speed | congested samples |
|---|---:|---:|---:|---:|---:|---:|---:|
| FW_E | 0 | 175.6 | 175.5 | 1811 | 3173 | 5.0 | 609/720 |
| FW_E | 1 | 175.6 | 175.5 | 1727 | 3291 | 5.0 | 625/720 |
| FW_E | 2 | 175.1 | 175.1 | 2149 | 4781 | 5.0 | 679/720 |
| FW_E | 3 | 166.7 | 166.7 | 1945 | 4157 | 5.0 | 669/720 |
| FW_W | 0 | 175.6 | 175.5 | 1818 | 3096 | 5.0 | 561/720 |
| FW_W | 1 | 175.6 | 175.5 | 1739 | 3291 | 5.0 | 578/720 |
| FW_W | 2 | 175.1 | 175.1 | 2294 | 4762 | 5.0 | 652/720 |
| FW_W | 3 | 166.7 | 166.7 | 2082 | 4165 | 5.0 | 634/720 |

Final totals:

- freeway TTT: `4895.503`
- urban TTT: `6759.336`
- total TTT: `11654.839`
- final mainline origin queue: `2088.703 veh`
- final ramp queue total: `720.000 veh`
- accepted off-ramp arrivals: `950.397 veh`
- rejected off-ramp arrivals: `0.000 veh`

Interpretation:

- The no-control `peak_demand` run enters a severe storage-limited freeway
  state. Most segments spend the majority of the 720 ten-second samples above
  `rho_crit=33.5`, and several segments finish near `rho_max=180`.
- The receiving/storage cap prevents unbounded density growth, but under
  peak no-control it turns the freeway into a capped queue reservoir. This is
  why the segment FD plots show many points near the high-density boundary
  instead of a clean recovery loop.
- Segment 2 and segment 3 show the strongest flow variation because they are
  closest to ramp merge/off-ramp interactions; upstream segments 0 and 1 are
  dominated by high-density storage saturation.

### No-Control Peak Segment FD With Calibrated Rho Cap

User pointed out that the storage cap/kink should be near `rho≈94`, not near the
default `rho_max=180`. I estimated the kink from the previous no-control
`peak_demand` segment FD in two ways:

- analytical speed-floor kink from the desired-speed curve:
  `rho_crit * (a * ln(v_free / v_min)) ** (1/a) = 84.236`
- empirical aggregate FD largest-density-jump midpoint across all segments:
  mean `95.020`, median `96.496`

Because the user's target was the observed `rho≈94` elbow, I used the empirical
mean `rho_max=95.01964207118104` as a runtime override and reran the same
no-control `peak_demand` trace.

Verification:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "2026-06-24\diag_scripts\no_control_peak_segment_fd.py"
```

Result: PASS.

Run:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\no_control_peak_segment_fd.py" --scenario peak_demand --rho-max 95.01964207118104 --out-dir "outputs\no_control_peak_segment_fd_rhocap95" --figure "reports\figures\fig_no_control_peak_segment_fd_rhocap95.png"
```

Generated:

- `outputs/no_control_peak_segment_fd_rhocap95/segment_fd_timeseries.csv`
- `outputs/no_control_peak_segment_fd_rhocap95/segment_fd_aggregate.csv`
- `outputs/no_control_peak_segment_fd_rhocap95/segment_fd_summary.csv`
- `outputs/no_control_peak_segment_fd_rhocap95/control_interval_summary.csv`
- `reports/figures/fig_no_control_peak_segment_fd_rhocap95.png`

Comparison to default `rho_max=180`:

| metric | rho_max=180 | rho_max=95.020 | delta |
|---|---:|---:|---:|
| freeway TTT | 4895.503 | 6650.376 | +1754.873 |
| urban TTT | 6759.336 | 7170.259 | +410.923 |
| total TTT | 11654.839 | 13820.635 | +2165.796 |
| final mainline origin queue | 2088.703 | 5292.279 | +3203.575 |
| final ramp queue total | 720.000 | 720.000 | +0.000 |
| accepted off-ramp arrivals | 950.397 | 642.807 | -307.589 |
| rejected off-ramp arrivals | 0.000 | 0.000 | +0.000 |

Segment summary with calibrated cap:

| link | seg | max rho | final rho | mean flow | max flow | min speed | congested samples |
|---|---:|---:|---:|---:|---:|---:|---:|
| FW_E | 0 | 93.2 | 93.2 | 2849 | 3056 | 7.6 | 609/720 |
| FW_E | 1 | 93.2 | 93.2 | 1084 | 3291 | 5.0 | 625/720 |
| FW_E | 2 | 92.4 | 92.4 | 1453 | 4781 | 5.1 | 679/720 |
| FW_E | 3 | 90.0 | 90.0 | 1330 | 4157 | 5.0 | 669/720 |
| FW_W | 0 | 93.2 | 93.2 | 2779 | 3056 | 7.1 | 561/720 |
| FW_W | 1 | 93.2 | 93.2 | 1152 | 3291 | 5.0 | 578/720 |
| FW_W | 2 | 92.4 | 92.4 | 1653 | 4762 | 5.1 | 652/720 |
| FW_W | 3 | 90.0 | 90.0 | 1517 | 4165 | 5.0 | 634/720 |

Interpretation:

- The calibrated cap shifts the high-density boundary from `rho≈166-176` to
  `rho≈90-93`, which matches the intended elbow region.
- The no-control peak run becomes more externally queued: final mainline origin
  queue increases by about `3204 veh`, while accepted off-ramp arrivals decrease
  by about `308 veh`.
- Total TTT increases because the reduced storage cap prevents freeway segments
  from hiding demand as high internal density and pushes more vehicles into
  origin/ramp waiting states.

### No-Control Medium Segment FD With Calibrated Rho Cap

I reran the same diagnostic for `medium_demand` with
`rho_max=95.01964207118104`, no control, 7200 s, and the actual coupled plant.

Run:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\no_control_peak_segment_fd.py" --scenario medium_demand --rho-max 95.01964207118104 --out-dir "outputs\no_control_medium_segment_fd_rhocap95" --figure "reports\figures\fig_no_control_medium_segment_fd_rhocap95.png"
```

Generated:

- `outputs/no_control_medium_segment_fd_rhocap95/segment_fd_timeseries.csv`
- `outputs/no_control_medium_segment_fd_rhocap95/segment_fd_aggregate.csv`
- `outputs/no_control_medium_segment_fd_rhocap95/segment_fd_summary.csv`
- `outputs/no_control_medium_segment_fd_rhocap95/control_interval_summary.csv`
- `reports/figures/fig_no_control_medium_segment_fd_rhocap95.png`

Segment summary:

| link | seg | max rho | final rho | mean flow | max flow | min speed | congested samples |
|---|---:|---:|---:|---:|---:|---:|---:|
| FW_E | 0 | 93.2 | 93.2 | 2349 | 3056 | 5.0 | 293/720 |
| FW_E | 1 | 93.2 | 93.2 | 1520 | 3291 | 5.0 | 313/720 |
| FW_E | 2 | 92.4 | 92.4 | 2741 | 4778 | 5.1 | 443/720 |
| FW_E | 3 | 90.0 | 90.0 | 2540 | 4173 | 5.0 | 410/720 |
| FW_W | 0 | 12.6 | 8.7 | 1883 | 2301 | 88.5 | 0/720 |
| FW_W | 1 | 18.0 | 10.3 | 1887 | 3291 | 64.1 | 0/720 |
| FW_W | 2 | 32.7 | 15.6 | 3782 | 4749 | 65.3 | 0/720 |
| FW_W | 3 | 29.4 | 16.3 | 3556 | 4113 | 65.8 | 0/720 |

Final totals:

- freeway TTT: `1192.032`
- urban TTT: `971.080`
- total TTT: `2163.112`
- final mainline origin queue: `950.809 veh`
- final ramp queue total: `362.136 veh`
- accepted off-ramp arrivals: `1192.965 veh`
- rejected off-ramp arrivals: `0.000 veh`

Interpretation:

- `FW_W` remains below `rho_crit` for all 720 samples and returns to low
  density, so the calibrated cap is inactive in that direction.
- `FW_E` crosses the tipping threshold and finishes at the `rho≈90-93` storage
  boundary. The demand profile makes `FW_E` mainline demand 5% larger than
  `FW_W`; with the reduced cap this small asymmetry is enough to produce
  qualitatively different branches.
- Therefore `medium_demand` is already a near-critical/bifurcation case under
  `rho_max≈95`, while `peak_demand` saturates both freeway directions.
## 2026-06-24 No-Control Medium Surge-Unloading FD Diagnostic

### Purpose

- Test whether the calibrated storage-cap METANET plant can exhibit a complete congestion loading and unloading trajectory under a medium-demand base scenario.
- Separate the demand peak from the actual segment density peak and inspect segment-level hysteresis.

### Implementation

- Extended `2026-06-24/diag_scripts/no_control_peak_segment_fd.py` with a smooth demand-surge profile and configurable recovery demand.
- Applied the same time-varying scale to freeway, ramp, and urban demands.
- Classified each segment's loading and unloading branches using its own maximum-density time.
- Preserved raw 10 s plant samples and generated 300 s aggregated FD branches.

### Run command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\no_control_peak_segment_fd.py" --scenario medium_demand --total-sec 10800 --rho-max 95.01964207118104 --surge-start-sec 1200 --surge-peak-sec 2400 --surge-end-sec 3600 --surge-peak-scale 1.30 --recovery-scale 0.10 --aggregate-window-sec 300 --out-dir "outputs\no_control_medium_surge_unloading_fd_rhocap95" --figure "reports\figures\fig_no_control_medium_surge_unloading_fd_rhocap95.png"
```

### Result

- Total horizon: 10,800 s.
- Demand scale: 1.00 until 1,200 s, 1.30 at 2,400 s, and 0.10 from 3,600 s onward.
- All eight freeway segments exceeded their critical density and later recovered below it.
- Segment density peaks occurred at 2,740-3,040 s, after the input-demand peak.
- Recovery below critical density occurred at 4,550-9,030 s; downstream segments 2-3 recovered substantially later than segments 0-1.
- Final Total TTT: 1,997.151 veh-h (freeway 1,604.631; urban 392.520).
- Final mainline origin queue: 0.000 veh.
- Final ramp queue: 0.481 veh.
- No rejected off-ramp arrivals were observed.

The loading-minus-unloading flow gap was strongly positive for segments 0-2, showing clockwise hysteresis and capacity-drop behavior. Segment 3 had too little same-density overlap for a reliable branch-gap statistic.

### Interpretation and limitations

- A complete congestion-unloading loop is reproducible in the current plant.
- Normal medium demand after saturation was not low enough to unload the network. A prolonged recovery tail at 10% of the configured medium demand was required.
- This is therefore a plant-dynamics diagnostic rather than a representative medium-demand performance experiment.
- The result indicates that the present `low/medium/peak` demand labels should be recalibrated against realized traffic regimes under the storage-cap plant.

### Validation

- `py_compile` passed for the modified diagnostic script.
- Output preserved under `outputs/no_control_medium_surge_unloading_fd_rhocap95`.
- Figure: `reports/figures/fig_no_control_medium_surge_unloading_fd_rhocap95.png`.

### Proposed next modification

- Recalibrate low, medium, and peak demand scenarios from no-control state targets: uncongested, near-critical/recoverable, and sustained congested/storage-constrained regimes.

## 2026-06-24 Low/Medium/Peak No-Control Freeway FD Screening

### Purpose

- Run the configured `low_demand`, `medium_demand`, and `peak_demand` scenarios under identical short no-control conditions.
- Check whether the three labels create meaningfully separated freeway traffic regimes in the calibrated storage-cap plant.

### Common conditions

- Controller: no-control.
- Horizon: 1,800 s.
- `rho_max`: 95.019642 veh/km/lane.
- Raw FD sample interval: 10 s.
- Display aggregation: 180 s.
- Critical density: 33.5 veh/km/lane.

### Run commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\no_control_peak_segment_fd.py" --scenario low_demand --total-sec 1800 --rho-max 95.01964207118104 --aggregate-window-sec 180 --out-dir "outputs\no_control_low_fd_rhocap95_1800" --figure "reports\figures\fig_no_control_low_fd_rhocap95_1800.png"

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\no_control_peak_segment_fd.py" --scenario medium_demand --total-sec 1800 --rho-max 95.01964207118104 --aggregate-window-sec 180 --out-dir "outputs\no_control_medium_fd_rhocap95_1800" --figure "reports\figures\fig_no_control_medium_fd_rhocap95_1800.png"

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\no_control_peak_segment_fd.py" --scenario peak_demand --total-sec 1800 --rho-max 95.01964207118104 --aggregate-window-sec 180 --out-dir "outputs\no_control_peak_fd_rhocap95_1800" --figure "reports\figures\fig_no_control_peak_fd_rhocap95_1800.png"

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\compare_three_scenario_fd.py"
```

### Results

| Scenario | Total TTT (veh-h) | Max density | Congested FD samples | Final origin queue | Final ramp queue |
|---|---:|---:|---:|---:|---:|
| Low | 172.24 | 23.36 | 0.00% | 0.00 | 3.57 |
| Medium | 242.61 | 38.18 | 4.79% | 0.00 | 4.66 |
| Peak | 628.68 | 93.18 | 65.21% | 650.75 | 720.00 |

### Interpretation

- `low_demand` is fully uncongested in all freeway segments.
- `medium_demand` is a useful near-critical regime: only FW_E segments 2-3 briefly exceed the critical density.
- `peak_demand` is not a moderate next step above medium. It rapidly enters a storage-constrained collapse, with most FD samples congested and large unresolved origin and ramp queues.
- The current labels therefore do not provide evenly separated low/medium/peak regimes. The major discontinuity is between medium and peak.

### Outputs

- Common-axis comparison: `reports/figures/fig_no_control_three_scenario_fd_rhocap95_1800.png`.
- Vector comparison: `reports/figures/fig_no_control_three_scenario_fd_rhocap95_1800.svg`.
- Combined summaries: `outputs/no_control_three_scenario_fd_rhocap95_1800`.
- Scenario-specific raw and aggregated FD outputs are preserved in their corresponding output directories.

### Validation

- All three no-control simulations completed.
- `py_compile` passed for both diagnostic scripts.
- The comparison PNG was visually inspected; labels, common axes, direction encodings, and the critical-density reference are readable.

### Proposed next modification

- Sweep between the current medium and peak demand scales to find a sustained-but-recoverable peak regime, then lower or reshape medium only if a wider separation from low is desired.

## 2026-06-24 Medium-to-Peak Demand Transition Sweep

### Purpose

- Evaluate the proposal to use the current `medium_demand` as the new low-demand case.
- Find a new median-demand scale between the current medium and peak cases that visibly enters the freeway FD loading/congested branch without immediately saturating at the storage cap.

### Method

- No-control, 1,800 s, `rho_max=95.019642`.
- Linearly interpolated the urban, freeway, and ramp demand scales between current medium `(1.00, 1.00, 1.00)` and current peak `(1.25, 1.20, 1.25)`.
- Screened interpolation fractions 5%, 10%, 15%, 20%, 25%, 50%, and 75%.

### Results

| Medium-to-peak fraction | Urban/freeway/ramp scales | TTT (veh-h) | Max density | Congested samples | Congested segments | Final origin/ramp queue |
|---:|---|---:|---:|---:|---:|---:|
| 0% | 1.000 / 1.000 / 1.000 | 242.61 | 38.18 | 4.79% | 2 | 0.00 / 4.66 |
| 5% | 1.0125 / 1.010 / 1.0125 | 247.56 | 41.26 | 9.44% | 2 | 0.00 / 4.73 |
| 10% | 1.025 / 1.020 / 1.025 | 254.24 | 51.59 | 11.94% | 3 | 0.00 / 4.77 |
| 15% | 1.0375 / 1.030 / 1.0375 | 264.44 | 78.38 | 15.90% | 4 | 0.00 / 4.80 |
| 20% | 1.050 / 1.040 / 1.050 | 277.50 | 90.48 | 19.86% | 5 | 0.00 / 41.94 |
| 25% | 1.0625 / 1.050 / 1.0625 | 292.31 | 93.18 | 24.51% | 6 | 19.22 / 108.34 |
| 50% | 1.125 / 1.100 / 1.125 | 391.76 | 93.17 | 46.60% | 8 | 183.17 / 410.27 |
| 75% | 1.1875 / 1.150 / 1.1875 | 513.01 | 93.18 | 57.85% | 8 | 449.86 / 661.50 |

### Interpretation

- The transition is highly nonlinear. A 25% interpolation already saturates some freeway segments near the storage cap.
- The 10% interpolation is the cleanest short-run median candidate:
  - it produces a visible FD loading and post-capacity branch;
  - maximum density remains 51.59 veh/km/lane rather than approaching the 95 veh/km/lane storage cap;
  - no mainline origin queue remains at 1,800 s;
  - minimum speed remains 35.5 km/h, whereas the 15% candidate already reaches the 5 km/h floor in one or more segments.
- Proposed provisional mapping:
  - low: current medium `(1.00, 1.00, 1.00)`;
  - median: `(1.025, 1.020, 1.025)`;
  - peak: current peak `(1.25, 1.20, 1.25)`.

### Outputs

- Proposed regime comparison: `reports/figures/fig_proposed_low_median_peak_fd_rhocap95_1800.png`.
- Vector figure: `reports/figures/fig_proposed_low_median_peak_fd_rhocap95_1800.svg`.
- Candidate outputs: `outputs/demand_recalibration_alpha*_1800`.
- Proposed combined summaries: `outputs/proposed_low_median_peak_fd_rhocap95_1800`.

### Validation and next step

- Both diagnostic scripts passed `py_compile`.
- The proposed common-axis figure was visually inspected.
- Do not update the canonical scenario configuration from this 1,800 s screening alone. Validate the 0%, 10%, and current-peak cases over 7,200 s because the built-in sinusoidal demand wave is normalized by the total simulation horizon.

## 2026-06-24 Six-Scenario Canonical Demand Redesign

### Implemented

- Replaced the active scenario set with exactly six canonical scenarios:
  - `low_demand`
  - `medium_demand`
  - `peak_demand`
  - `medium_incident_east`
  - `medium_urban_west_skew`
  - `medium_surge`
- Promoted the calibrated freeway receiving/jam density
  `rho_max=95.01964207118104 veh/km/lane` to the canonical plant configuration.
- Added time-dependent, link/segment-specific freeway lane closures to
  `ScenarioConfig`, `DemandProfile`, `DemandStep`, the METANET plant, leader forecast
  aggregation, distributed followers, and WU candidate generation.
- Added a total-preserving west/east urban demand redistribution mode.
- Added a triangular common demand-surge mode shared by freeway, ramp, and urban demand.

### Canonical definitions

| Scenario | Urban scale | Freeway scale | Ramp scale | Additional condition |
|---|---:|---:|---:|---|
| `low_demand` | 1.0000 | 1.0000 | 1.0000 | Former medium/base demand |
| `medium_demand` | 1.0375 | 1.0300 | 1.0375 | Former medium-to-peak 15% interpolation |
| `peak_demand` | 1.2500 | 1.2000 | 1.2500 | Existing peak |
| `medium_incident_east` | 1.0375 | 1.0300 | 1.0375 | `FW_E` segment 3 loses one lane during 2400-4800 s |
| `medium_urban_west_skew` | 1.0375 | 1.0300 | 1.0375 | West-side entry total = 2 x east-side entry total |
| `medium_surge` | 1.0375 | 1.0300 | 1.0375 | Common scale 1.0 at 1800 s, 1.15 at 3000 s, 1.0 at 4200 s |

`FW_W` remains fully open in `medium_incident_east`. This deliberately asymmetric
incident tests directional coupling and controller redistribution rather than applying
a network-wide capacity reduction.

For the urban-skew case, the west-side entries are `in_A_left` and `in_D_left`;
the east-side entries are `in_C_right` and `in_F_right`. At 3000 s:

- medium total urban boundary demand: `10390.853427 veh/h`
- skew total urban boundary demand: `10390.853427 veh/h`
- west total: `2348.215464 veh/h`
- east total: `1174.107732 veh/h`
- west/east ratio: `2.000000`

### Files changed

- `src/config/default.yaml`
- `src/config/scenarios.yaml`
- `src/models/state.py`
- `src/models/demand.py`
- `src/models/metanet.py`
- `src/controllers/leader.py`
- `src/controllers/distributed_coordinator.py`
- `src/controllers/wu_distributed.py`
- `src/tests/test_demand_scenarios.py`
- `docs/spec/05_simulation_pipeline.md`
- `2026-06-24/diag_scripts/no_control_peak_segment_fd.py`
- `2026-06-24/diag_scripts/compare_three_scenario_fd.py`

### Standard 7200 s no-control screening

All scenarios used the same seed, horizon, canonical plant, and no-control policy.
The following totals come from the standard `run_closed_loop` path.

| Scenario | Total TTT (veh-h) | Final boundary queue | Final movement queue | Final origin queue | Final ramp queue |
|---|---:|---:|---:|---:|---:|
| `low_demand` | 2168.827 | 234.311 | 1312.147 | 950.809 | 362.136 |
| `medium_demand` | 3367.045 | 665.382 | 2640.138 | 1413.030 | 362.187 |
| `peak_demand` | 13823.810 | 3403.766 | 9472.807 | 5292.279 | 720.000 |
| `medium_incident_east` | 4608.675 | 1083.054 | 3643.401 | 1774.850 | 362.187 |
| `medium_urban_west_skew` | 3394.702 | 662.156 | 2659.296 | 1417.098 | 362.196 |
| `medium_surge` | 6583.652 | 1309.825 | 4904.428 | 3073.187 | 720.000 |

The incident and surge scenarios therefore create distinct stress levels above medium.
The urban-skew case intentionally preserves total demand, so its network-wide TTT stays
near medium while the spatial queue distribution changes.

### Surge calibration

Additional 7200 s no-control probes used surge peaks `1.03`, `1.05`, `1.08`, and
`1.15`. Even `1.03` moved the current storage-cap plant to the high-density attractor
with a final mean freeway density near `92.17 veh/km/lane`. The canonical `1.15`
therefore remains a tipping-point robustness case rather than a guaranteed unloading
case. It is still substantially less severe than `peak_demand` by total TTT.

### Validation

- `py_compile`: passed for all modified Python modules and tests.
- Scenario regression checks: 7 passed.
- METANET equation and closed-loop smoke tests: 23 passed.
- Targeted constraints tests: 3 passed.
- Full constraints suite after the final scenario-schema extension: 87 passed.
- Six 7200 s no-control simulations: completed.
- Incident plant check: `FW_E seg3=1.0 lane`, all `FW_W` segments remain `2.0 lanes`.
- Control validation and improvement rate: not applicable; this attempt redefines
  scenarios and runs no-control screening only.

### Acceptance status and next step

- Controller acceptance: not evaluated.
- Boundary queues are reported as scenario baselines, not pass/fail comparisons.
- Next: run the four controller families against the same six canonical scenarios and
  compare TTT, throughput, terminal vehicles, boundary balance, and computation cost.

## 2026-06-24 - Medium-Demand 3600 s Controller Screening on Recalibrated Plant

### Purpose

Check whether the recalibrated plant and six-scenario demand definition still preserve
controller benefits on the new canonical `medium_demand` setting before launching a
longer all-scenario batch.

### Commands

Initial 4-controller attempt:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --T-total 3600 --output "outputs\canonical_medium_4controller_3600_2026_06_24"
```

This completed `NO-CONTROL`, `WU-CD-F`, and `PROPOSED-FOLLOWERS-ONLY`, but stopped
before a completed `PROPOSED-STACKELBERG` summary was written. A follow-up
P-Stackelberg run with the default continuous leader budget and thread grid backend
completed only 8/20 steps within a 30 minute guard:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 3600 --output "outputs\canonical_medium_pstack_3600_2026_06_24" --grid-parallel-backend thread --stackelberg-leader-parallel-backend thread
```

To finish the requested medium sanity comparison, a reduced continuous leader budget
was used for P-Stackelberg while retaining process-parallel follower grid evaluation
and the fallback guard:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario medium_demand --controllers PROPOSED-STACKELBERG --T-total 3600 --output "outputs\canonical_medium_pstack_3600_fast_sanity_2026_06_24" --grid-parallel-backend process --stackelberg-leader-parallel-backend serial --leader-continuous-max-evals 1 --leader-continuous-seed-count 1 --leader-continuous-prefilter-samples 3 --leader-continuous-prefilter-top-k 1 --leader-continuous-local-iterations 0
```

### Results

The table uses each controller's `progress_summary.csv` final row. `wall sec` and
`compute sec` are sums over all 20 control steps.

| Controller | Total TTT | Urban TTT | Freeway TTT | Improvement vs no-control | mean B_sum | terminal vehicles | wall sec | compute sec |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `NO-CONTROL` | 820.582 | 360.088 | 460.495 | 0.000% | 0.168012 | 1837.4 | 0.0 | 0.0 |
| `WU-CD-F` | 573.933 | 382.922 | 191.011 | 30.058% | 0.197016 | 617.8 | 130.1 | 128.7 |
| `PROPOSED-FOLLOWERS-ONLY` | 541.957 | 328.061 | 213.896 | 33.955% | 0.175935 | 516.5 | 208.2 | 206.7 |
| `PROPOSED-STACKELBERG` | 541.957 | 328.061 | 213.896 | 33.955% | 0.175935 | 516.5 | 1078.5 | 1077.4 |

### Diagnostics

- The completed reduced-budget P-Stackelberg run selected the PFO fallback candidate
  on all 20/20 steps, so its plant trajectory matches `PROPOSED-FOLLOWERS-ONLY`.
- The partial default-budget P-Stackelberg attempt also selected `fallback_pfo` on
  every completed step 0-7 before timing out, which is consistent with the completed
  reduced-budget result.
- Computation cost remains the main issue: the completed reduced-budget P-Stackelberg
  run took about `1078.5 s` wall time for a `3600 s` simulation, while PFO took
  about `208.2 s` and WU took about `130.1 s`.
- Boundary balance is mildly degraded relative to no-control for all active
  controllers in this 3600 s screening (`mean_B_sum` increases from `0.168012` to
  `0.175935` for PFO/P-Stack and `0.197016` for WU).

### Acceptance status and next step

- The recalibrated medium plant still shows strong TTT improvement for WU and PFO.
- P-Stackelberg does not yet demonstrate distinct benefit over PFO because the
  fallback guard dominates the selected actions.
- This is a screening result, not final acceptance: the P-Stackelberg row used a
  reduced leader evaluation budget to finish the 3600 s run.
- Next: diagnose why full-budget leader candidates do not beat the PFO fallback on
  the recalibrated medium plant, then rerun P-Stackelberg without relying on the
  reduced-budget sanity setting.

## 2026-06-25 - Figure Design Guide Refactor

### Purpose

Refactor the external single-file mixed-network figure guide into a maintainable
`docs/figure_design/` chapter structure. The main design goal is to keep stable
plotting guidance separate from volatile controller and scenario definitions.

### Files added

- `docs/figure_design/README_index.md`
- `docs/figure_design/00_global_style.md`
- `docs/figure_design/01_controller_catalog.md`
- `docs/figure_design/02_scenario_catalog.md`
- `docs/figure_design/03_data_schema.md`
- `docs/figure_design/04_main_text_figure_set.md`
- `docs/figure_design/10_macro_performance.md`
- `docs/figure_design/20_congestion_transfer.md`
- `docs/figure_design/30_leader_feasibility.md`
- `docs/figure_design/40_game_coupling.md`
- `docs/figure_design/50_micro_control_behavior.md`
- `docs/figure_design/60_computation_cost.md`
- `docs/figure_design/70_appendix_figures.md`
- `docs/figure_design/90_codex_plotting_prompt.md`

### Content summary

- Controller guidance was rewritten around this repository's active comparison:
  `NO-CONTROL`, `WU-CD-F`, `PROPOSED-FOLLOWERS-ONLY`,
  `PROPOSED-STACKELBERG`, and `PROPOSED-CENTRALIZED`.
- Scenario guidance was rewritten to use a flexible registry with tags such as
  `low`, `medium`, `peak`, `incident`, `surge`, `spatial-skew`, and
  `spillback-risk` rather than hard-coding a fixed number of scenarios.
- Stable figure chapters now refer back to the controller and scenario catalogs
  instead of duplicating labels, controller authority, or scenario names.
- The PFO fallback and P-Stack leader-feasibility diagnostics are explicitly
  included in the leader and computation-cost figure chapters.

### Validation

- Confirmed `docs/figure_design/` contains 14 chapter files.
- Searched the new guide for hard-coded five-scenario assumptions; only negative
  instructions such as "do not assume exactly five or six scenarios" remain.
- No code tests were run because this was a documentation-only refactor.

## 2026-06-25 - Pre-Revision Claude Scenario Figures

### Purpose

Generate figures from Claude's pre-scenario-revision post-analysis outputs using
the modular `docs/figure_design/` guidance. This is a figure-generation pass only;
no simulations were rerun.

### Source data and scenario mapping

- `median` -> `post_analysis/stage1/medium_demand_s42`
- `peak` -> `post_analysis/stage1/peak_demand_s42`
- `incident` -> `post_analysis/stage1/incident_or_capacity_drop_s42`
- `peak_skew` raw run CSV was not found; existing post-analysis skew figures were
  copied from `reports/figures/fig03_skew_demand.png` and
  `reports/figures/fig15_skew_balance.png`.

### Files changed

- Added/updated `2026-06-25/diag_scripts/generate_pre_revision_figure_design.py`.
- Generated figures under
  `reports/figures/pre_revision_claude_2026_06_25/`.
- Wrote a machine-readable manifest at
  `reports/figures/pre_revision_claude_2026_06_25/manifest.json`.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-25\diag_scripts\generate_pre_revision_figure_design.py"
```

### Output summary

- Generated 19 new PNG/PDF figure pairs from 18 controller run files.
- Reused 2 existing skew-demand figures because the raw `peak_skew` run CSV was
  not available in `post_analysis/stage1`.
- Skipped 1 game-coupling figure because Nash diagnostics were not present in the
  pre-revision run files.

### Figure groups generated

- Macro performance and TTT decomposition.
- Per-scenario TTT time series for median, peak, and incident.
- Queue and boundary exposure summaries.
- Per-scenario queue time series.
- P-Stack leader target diagnostics for median, peak, and incident.
- Micro control behavior panels for median, peak, and incident.
- Computation cost and performance/computation tradeoff figures.

### Validation

- The script completed successfully with `generated_count=19`,
  `reused_count=2`, and `skipped_count=1`.
- Key generated PNGs were visually inspected:
  `fig01_macro_ttt_decomposition.png`,
  `fig01_queue_exposure_summary.png`, and
  `fig01_peak_demand_leader_targets.png`.
- No controller validation, py_compile, or simulation acceptance test was run
  because this task only plots historical outputs.

### Correction

This figure-generation pass is superseded by the 6/23 paper-figure packaging
below. The `post_analysis/stage1` CSVs are valid post-analysis artifacts, but the
user-requested "6/23 data" refers to the paper-figure set generated by
`2026-06-23/diag_scripts/make_paper_figures_v2.py` from
`outputs/analysis_matrix_3600` and `outputs/analysis_matrix_3600_extra`. Those raw
`outputs/` folders are present in the Desktop clone
`C:\Users\alsrj\Desktop\Numerical-Sim`, but are ignored by Git and absent from
this Documents clone.

## 2026-06-25 - Corrected 6/23 Figure-Design Packaging

### Purpose

Package the actual 6/23 paper-figure outputs into the modular
`docs/figure_design/` grouping without recomputing simulations.

### Source data and Git status

- Source report: `reports/post_analysis_results_2026-06-23.md`.
- Source script: `2026-06-23/diag_scripts/make_paper_figures_v2.py`.
- Expected raw inputs: `outputs/analysis_matrix_3600` and
  `outputs/analysis_matrix_3600_extra`.
- Raw inputs are present in `C:\Users\alsrj\Desktop\Numerical-Sim`.
- Raw `outputs/` folders are ignored by `.gitignore`, so they are not pushed to
  Git.
- The 6/23 generated figure PNGs `reports/figures/fig01_...fig17_...` are tracked
  in Git.
- Verified remote `origin/main` points to
  `08c2d2ba19df7deac097d07e910e024ccfcd0eef`; the Desktop clone had not fetched
  that commit yet and locally showed `b847df5`.

### Files changed

- Added `2026-06-25/diag_scripts/package_2026_06_23_figure_design.py`.
- Generated the structured figure package under
  `reports/figures/post_analysis_2026_06_23_figure_design/`.
- Wrote manifest:
  `reports/figures/post_analysis_2026_06_23_figure_design/manifest.json`.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-25\diag_scripts\package_2026_06_23_figure_design.py"
```

### Output summary

- Copied 17/17 existing 6/23 paper figures into figure-design chapter folders.
- Missing figures: 0.
- Scenario coverage from the 6/23 report: medium, peak, heavy1.40, heavy1.50,
  oversaturated, incident, skew-peak, and skew-heavy.
- User-requested focus scenarios covered by this set: median/medium, peak,
  peak_skew/skew-peak, and incident.

### Validation

- Confirmed Desktop raw input folders exist.
- Confirmed current Git tree tracks `reports/figures/fig01_...fig17_...`.
- Confirmed raw `outputs/` folders are ignored by `.gitignore`.
- No new simulations were run.

## 2026-06-25 - Actual Redraw From 6/23 Desktop Raw Outputs

### Purpose

Correct the previous ambiguity: the 6/23 figure-design package above only copied
the already-generated `fig01`-`fig17` PNGs into chapter folders. This pass reruns
the 6/23 plotting script against the raw Desktop output CSVs and writes a new
redrawn figure directory.

### Files changed

- Added `2026-06-25/diag_scripts/redraw_2026_06_23_figures_from_desktop_raw.py`.
- Generated `reports/figures/redrawn_2026_06_23_from_desktop_raw/fig01_...fig17_...png`.
- Added `reports/figures/redrawn_2026_06_23_from_desktop_raw/README.md`.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "C:\Users\alsrj\Documents\Numerical Simulation\2026-06-25\diag_scripts\redraw_2026_06_23_figures_from_desktop_raw.py"
```

The command was run with working directory
`C:\Users\alsrj\Desktop\Numerical-Sim` so that the script uses the Desktop clone's
code/config and raw output paths consistently.

### Inputs

- `C:\Users\alsrj\Desktop\Numerical-Sim\outputs\analysis_matrix_3600`
- `C:\Users\alsrj\Desktop\Numerical-Sim\outputs\analysis_matrix_3600_extra`

### Output summary

- Redrew 17 PNG figures from raw output files.
- The script completed with `DONE: 17 figs`.
- `fig04` through `fig17` are byte-identical to the tracked 6/23 originals,
  confirming the raw redraw path reproduces the existing analysis figures.
- `fig01` through `fig03` differ from the tracked originals because the repository
  no longer contains the exact 6/23 scenario definitions for
  `heavy_demand_140`, `heavy_demand_150`, `skew_peak`, and `skew_heavy`; the
  redraw script injects local legacy scenario definitions to let those
  demand-profile plots run.

### Validation

- Confirmed raw input folders exist in the Desktop clone.
- Confirmed 17 files were written under
  `reports/figures/redrawn_2026_06_23_from_desktop_raw/`.
- Compared SHA-256 hashes against `reports/figures/fig01_...fig17_...`:
  `fig04`-`fig17` match exactly; `fig01`-`fig03` do not.
- No new controller simulations were run.

### Superseded for figure-design purpose

This pass verified that the raw 6/23 CSV outputs reproduce the old paper figures,
but it did not satisfy the later request to redraw figures according to the new
`docs/figure_design/*.md` guide. The guide-based redraw below is the correct
figure-design output.

## 2026-06-25 - Figure-Design-Based 6/23 Redraw

### Purpose

Generate a new figure set from the 6/23 Desktop raw outputs according to the
modular `docs/figure_design/*.md` chapters. This is not a copy of the old
`fig01`-`fig17` paper figures and does not reuse their layouts.

### Focus scenarios

- `medium_demand` as `Median`
- `peak_demand` as `Peak`
- `skew_peak` as `Peak skew`
- `incident_or_capacity_drop` as `Incident`

### Controllers

- `NO-CONTROL`
- `WU-CD-F`
- `PROPOSED-FOLLOWERS-ONLY`
- `PROPOSED-STACKELBERG`

### Files changed

- Added `2026-06-25/diag_scripts/redraw_2026_06_23_by_figure_design.py`.
- Generated new PNG/PDF figure sets under
  `reports/figures/figure_design_2026_06_23_redraw/`.
- Wrote manifest:
  `reports/figures/figure_design_2026_06_23_redraw/manifest.json`.
- Wrote normalized tables under
  `reports/figures/figure_design_2026_06_23_redraw/tables/`.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-25\diag_scripts\redraw_2026_06_23_by_figure_design.py"
```

### Source data

- `C:\Users\alsrj\Desktop\Numerical-Sim\outputs\analysis_matrix_3600`
- `C:\Users\alsrj\Desktop\Numerical-Sim\outputs\analysis_matrix_3600_extra`

### Output summary

- Generated 37 new figure sets, each saved as PNG and PDF.
- Figure groups follow the guide chapters:
  macro performance, congestion transfer, leader feasibility, game coupling,
  microscopic control behavior, and computation cost.
- Representative outputs visually checked:
  `Fig1A_total_ttt_cross_scenario.png`,
  `Fig2B_queue_exposure_summary.png`,
  `Fig3A_leader_targets_response_peak_demand.png`,
  `Fig4B_coupling_response_matrix.png`, and
  `Fig6C_performance_compute_tradeoff.png`.

### Limitations

- Full rejected-candidate leader objective surfaces are unavailable because
  `decision_progress.csv` was not present in the 6/23 raw outputs. The script
  therefore plots logged best-candidate locations and selected-objective fidelity
  instead.
- Boundary queue exposure is based on available logged queue/load proxy columns;
  some controllers do not log the same boundary-in backlog quantity as P-Stack,
  so this panel should be interpreted as an exposure diagnostic, not a final
  accounting proof.
- No new controller simulations were run.

## 2026-06-25 - Figure QA and Interpretation Report

### Purpose

Inspect the figure-design redraw outputs for label/legend overlap, fix readable
layout problems, regenerate the figure set, and write a result-interpretation
report based on the assumptions used when plotting the figures.

### Files changed

- Updated `2026-06-25/diag_scripts/redraw_2026_06_23_by_figure_design.py`.
- Regenerated 37 PNG/PDF figure pairs under
  `reports/figures/figure_design_2026_06_23_redraw/`.
- Regenerated QA contact sheets under
  `reports/figures/figure_design_2026_06_23_redraw/_qa_contact_sheets/`.
- Added `reports/figure_design_2026_06_23_result_interpretation_report.md`.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-25\diag_scripts\redraw_2026_06_23_by_figure_design.py"
```

### Figure QA changes

- Moved dense legends in macro and congestion-transfer multi-panel figures to
  figure-level top legends.
- Removed per-point text annotations from
  `Fig6C_performance_compute_tradeoff`; the plot now uses controller colors and
  scenario marker shapes to avoid label overlap.
- Increased spacing and reduced tick-label crowding in
  `Fig4E_objective_coverage_audit`.
- Corrected `Fig2C_offramp_acceptance_ratio` by integrating desired off-ramp
  flow over the 180 s control interval before computing accepted/desired flow.
  The previous diagnostic used a veh/h sum directly, which compressed the ratio
  by the timestep factor.
- Visually rechecked representative corrected outputs:
  `Fig1B_urban_freeway_ttt_decomposition.png`,
  `Fig1C_delay_att_throughput.png`,
  `Fig2B_queue_exposure_summary.png`,
  `Fig2C_offramp_acceptance_ratio.png`,
  `Fig4E_objective_coverage_audit.png`,
  `Fig5_mechanism_panel_peak_demand.png`, and
  `Fig6C_performance_compute_tradeoff.png`.

### Interpretation summary

- P-Stack is nearly identical to PFO in the Median case, but it adds clear
  leader-layer gains in Peak, Peak skew, and Incident.
- Total TTT improvements vs no-control in the 6/23 3600 s raw outputs:
  WU/PFO/P-Stack are 7.8/8.7/8.7% for Median, 33.8/39.7/53.4% for Peak,
  34.4/38.1/49.7% for Peak skew, and 37.2/39.9/47.2% for Incident.
- P-Stack also increases completed vehicles and reduces terminal vehicles in
  the stressed scenarios, so the aggregate figures do not support a simple
  "vehicle hiding" interpretation for these raw summaries.
- Boundary/load exposure remains a logging-fidelity caveat because the plotted
  boundary proxy is not harmonized across all controllers in the raw 6/23 files.
- No new simulations were run in this QA/report pass.

### Figure-by-figure interpretation update

- Expanded `reports/figure_design_2026_06_23_result_interpretation_report.md`
  with per-figure interpretation notes for all generated figures.
- Each note records the main message, how it should be used in the paper, and
  any diagnostic caution such as selected-candidate-only fidelity or
  non-harmonized boundary proxy logging.
- Added Korean version:
  `reports/figure_design_2026_06_23_result_interpretation_report_kr.md`.
  This version mirrors the same assumptions, caveats, and figure-by-figure
  interpretation notes in Korean for paper drafting.

## 2026-06-25 - Future Flow-Based Coupling Analysis Requirements

### Purpose

Document the data that must be logged in future simulations to support
effect-oriented and ablation-based coordination figures. The current figure set
can show activation and aggregate outcomes, but it cannot rigorously decompose
how coordinated control changes interface flow, queue propagation, spillback,
freeway density, and urban/freeway TTT.

### File added

- `reports/future_flow_based_coupling_analysis_data_requirements.md`

### Key requirement

Future runs should support the following analysis statement:

> On-ramp와 off-ramp interface에서 발생하는 flow-based coupling을 중심으로,
> 각 제어전략이 urban-freeway 간 교통류, queue propagation, spillback,
> freeway density, 그리고 urban/freeway TTT에 미치는 영향을 정량적으로
> 분석한다.

### Required future outputs

- `interface_flow_timeseries.csv`
- `onramp_coupling_timeseries.csv`
- `offramp_coupling_timeseries.csv`
- `control_action_timeseries_normalized.csv`
- `state_response_timeseries_normalized.csv`
- `coupling_effect_summary.csv`

### Required future analysis

- Interface effect-chain figures connecting control input, accepted/rejected
  flow, queue/storage response, freeway density/speed, and TTT savings.
- On-ramp and off-ramp coupling figures.
- FD/MFD operating-point shift figures.
- Ablation-based coordination effect figures.
- Synergy index figures comparing joint-actuator gains against single-actuator
  gains.
- Marginal cost / shadow price figures showing the objective cost of admitting,
  releasing, holding, or rejecting one additional vehicle at each on-ramp and
  off-ramp interface.

### Simulation note

The report recommends starting with Peak and Incident 1800 s ablation smoke runs
before expanding to longer horizons.

### 2026-06-25 update

- Added the user-provided analysis statement:
  "On-ramp와 off-ramp interface에서 발생하는 coupling을 중심으로, 각
  제어전략이 urban-freeway 간 교통류, queue propagation, spillback,
  freeway density, 그리고 urban/freeway TTT에 미치는 영향을 정량적으로
  분석함."
- Added a marginal cost / shadow price analysis section defining on-ramp,
  off-ramp, and leader-target marginal costs.
- Documented required candidate-level perturbation logging for true interface
  marginal cost estimation.

## 2026-06-25 - Effect-Oriented Coordination Figures From Existing 6/23 Outputs

### Purpose

Check whether the existing 6/23 raw outputs can already support figures that
show coordinated-control effects, not only actuator activation. The goal is to
plot time-aligned chains such as control input -> queue/storage response ->
freeway density/speed -> TTT saving, plus FD/MFD operating-point shifts.

### Files changed

- Added `2026-06-25/diag_scripts/generate_effect_oriented_figures.py`.
- Generated effect-oriented figures under
  `reports/figures/effect_oriented_2026_06_23/`.
- Wrote manifest:
  `reports/figures/effect_oriented_2026_06_23/manifest.json`.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-25\diag_scripts\generate_effect_oriented_figures.py"
```

### Output summary

- Generated 20 PNG/PDF figure pairs.
- Figure families:
  - Four-panel mixed-network topology showing only exogenous urban boundary
    entries, ramp-bound demand, and upstream freeway entries for Median, Peak,
    Peak skew, and Incident. Values are the peak-rate snapshot at `t=1800 s`
    from the frozen 2026-06-23 3600 s scenario definitions. Ramp-bound demand
    is displayed in boxes beside boundary intersections D/F rather than on the
    ramp links, so the figure does not visually imply vehicle generation on
    the physical ramp. Split ratios remain omitted.
  - Time-aligned RM/ramp-queue/network-outcome effect chains.
  - Time-aligned VSL/speed/density/freeway-TTT effect chain for Incident.
  - Time-aligned VSL/RM/ramp-queue/freeway-state/freeway-TTT effect chain
    for Incident, added as the preferred presentation figure when explaining
    actuator coupling rather than VSL activation alone.
    The Incident-direction panel separates the Eastbound upstream ramp
    (`R_D_E`) and downstream ramp (`R_F_E`) for both metering commands and
    ramp queues, and uses Eastbound freeway speed/density rather than a
    two-direction network mean.
  - Time-aligned signal/offset/urban-service/movement-queue effect chains.
  - Freeway FD operating-point shift.
  - Urban MFD operating-point shift.
  - Logged leader candidate objective diagnostics.
  - Two-panel network effect summary with absolute completed vehicles and
    absolute terminal vehicles remaining at the end of the run. No-control was
    added to both panels; the former completed-vehicle gain was changed to the
    absolute completed count because the no-control gain would be identically
    zero. The TTT-saved panel was removed because it duplicates the separate
    Total TTT comparison figure.
  - Per-step computation-time comparison for WU-CD-F, PFO, and P-Stack across
    the four focus scenarios. Total controller computation time was divided by
    20 control decisions (`3600 / 180`), and the `180 s` control interval was
    added as a real-time reference line. Observed ranges were approximately
    `4.8-5.4 s/step` for WU-CD-F, `6.6-8.1 s/step` for PFO, and
    `60.8-67.1 s/step` for P-Stack.

### Verification

- `generate_effect_oriented_figures.py` passed `py_compile`.
- Script completed successfully with `generated_count=20`.
- Visually checked representative figures:
  - `Scenario_topology_directional_demand.png`
  - `EffectChain_RM_queue_TTT_peak_demand.png`
  - `EffectChain_VSL_speed_density_incident_or_capacity_drop.png`
  - `EffectChain_VSL_RM_speed_density_incident_or_capacity_drop.png`
  - `EffectChain_signal_service_queue_peak_demand.png`
  - `FD_operating_point_shift_peak_demand.png`
  - `Urban_MFD_operating_point_shift_peak_demand.png`
  - `Network_effect_summary.png`

### Interpretation and limitations

- These figures are immediately possible from existing raw outputs and better
  show the control-response chain than activation-only plots.
- They remain descriptive controller-comparison figures, not clean ablation
  figures.
- True ablation-based coordination/synergy claims still require new runs such
  as `SIGNAL-ONLY`, `RM-ONLY`, `VSL-ONLY`, `SIGNAL-RM`,
  `SIGNAL-RM-OFFSET`, `PFO`, and `P-STACK` under identical scenario, seed, and
  horizon.

## 2026-06-29 Figure Design Guide Update After Presentation-Figure Revisions

### Purpose

Update the modular figure-design markdown files so future plotting and analysis
instructions match the revised presentation figures and interpretations.

### Files changed

- `docs/figure_design/README_index.md`
- `docs/figure_design/02_scenario_catalog.md`
- `docs/figure_design/03_data_schema.md`
- `docs/figure_design/04_main_text_figure_set.md`
- `docs/figure_design/10_macro_performance.md`
- `docs/figure_design/20_congestion_transfer.md`
- `docs/figure_design/50_micro_control_behavior.md`
- `docs/figure_design/60_computation_cost.md`
- `docs/figure_design/90_codex_plotting_prompt.md`
- `reports/codex_run_report.md`

### What changed

- Added the current effect-oriented presentation package:
  demand topology, Total TTT, urban/freeway TTT decomposition,
  completed/terminal outcome bars, RM/VSL/signal effect chains, FD/MFD caveat
  figures, and computation-time bars.
- Added a historical/focus-scenario note for the frozen 2026-06-23 figure set
  (`medium_demand`, `peak_demand`, `skew_peak`, and
  `incident_or_capacity_drop`) while keeping the stable guide tag-based.
- Added demand-topology rules: urban boundary demand near boundary entries,
  freeway upstream demand at freeway entries, and ramp-bound demand near the
  feeding boundary/intersection rather than directly on ramp links.
- Clarified that network-effect summaries with no-control should use absolute
  completed vehicles and absolute terminal vehicles, not only gain/reduction
  bars.
- Updated RM/VSL/signal effect-chain instructions so figures show
  control input -> interface queue/flow -> state response -> TTT/throughput or
  terminal response, instead of only actuator activation.
- Added interpretation guardrails: ramp queues alone do not imply hidden
  vehicles; completed vehicles, terminal vehicles, and urban/freeway TTT
  decomposition must be checked together.
- Added the FD/MFD caveat: current numerical simulation can suggest congestion
  suppression, but clean empirical FD/MFD claims need a validated plant or a
  microscopic tool such as VISSIM.
- Added computation-cost guidance using per-step computation time and the
  180 s control interval reference line.

### Verification

- Markdown-only update; no simulation rerun was required.
- Reviewed the diff for the figure-design chapters.

## 2026-06-29 Claude-Style Sweet-190 Five-Controller Screening

### Purpose

After pulling `origin/main` commit `28ae3a2`, rerun the requested sweet_190
screening with a direct Claude-style closed-loop runner rather than the heavier
six-controller experiment wrapper. The goal was to verify that the current
P-Stack path is actually `StackelbergWuMeteredController + WuFaithfulFollower`
and to compare no-control, WU, Wu-faithful PFO, P-Stack, and the local
classical hierarchical baseline under the same 3600 s scenario.

### Files / Artifacts

- Added temporary runner: `work/run_claude_style_five_controller.py`
- Output directory: `outputs/claude_style_sweet190_3600_20260629`
- Summary CSV: `outputs/claude_style_sweet190_3600_20260629/summary.csv`
- Per-controller `run_log.csv`, `control_timeseries.csv`,
  `state_timeseries.csv`, and `decision_diagnostics.csv` were written under the
  output directory.

### Verification

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile work/run_claude_style_five_controller.py src/controllers/classical_hierarchical.py src/controllers/wu_faithful_follower.py src/controllers/stackelberg_wu_metered.py
```

Passed.

### Run Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work/run_claude_style_five_controller.py --scenario sweet_190 --T-total 3600 --output outputs/claude_style_sweet190_3600_20260629
```

Runner configuration followed the Claude local runner style:

- `relaxed_quantized_controls=true`
- `leader_search_mode=grid`
- `grid_parallel_backend=serial`
- `stackelberg_leader_parallel_backend=serial`
- direct simulator loop, not `six_controller_comparison.py`

### Results

| controller | Total TTT | Urban TTT | Freeway TTT | Total delay | TTT improvement vs no-control | Completed veh | Terminal veh | Mean solve / step |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 7166.467 | 3655.845 | 3510.623 | 6292.226 | 0.000% | 7646.8 | 15025.2 | 0.000 s |
| WU-CD-F | 6827.417 | 3505.329 | 3322.087 | 5953.175 | 4.731% | 8029.9 | 14640.7 | 13.127 s |
| WU-FAITHFUL-FOLLOWER | 4814.155 | 3697.527 | 1116.627 | 3939.913 | 32.824% | 12203.7 | 10460.2 | 2.464 s |
| P-STACK-WU-FAITHFUL | 4812.513 | 3725.321 | 1087.192 | 3938.271 | 32.847% | 12234.7 | 10429.2 | 9.058 s |
| CLASSICAL-HIERARCHICAL | 7090.540 | 3646.228 | 3444.312 | 6216.299 | 1.059% | 7774.0 | 14898.0 | 0.002 s |

### Interpretation

- The latest pulled Wu-faithful follower is fast again: PFO averaged about
  2.46 s/step and P-Stack averaged about 9.06 s/step.
- This confirms the previous 70-325 s/step P-Stack run was not representative
  of the pulled Claude state. It was run before pulling `28ae3a2` and included
  heavier local offset/joint-search experiment code plus serial heavy candidate
  evaluation.
- In sweet_190, P-Stack is almost tied with Wu-faithful PFO:
  `4812.513` vs `4814.155` veh-h, a marginal `+0.023 pp` Total TTT gain over
  PFO. It slightly lowers freeway TTT and terminal vehicles but raises urban
  TTT relative to PFO.
- Classical hierarchical control is computationally negligible but improves
  only `1.059%` over no-control, far behind WU-CD-F and the Wu-faithful proposed
  follower. This is useful as a low-cost hierarchical/gating baseline, not as a
  competitive controller in this scenario.

### Caveats / Next Step

- `CLASSICAL-HIERARCHICAL` is currently a local untracked controller file in
  this working tree; results should be treated as local-screening evidence until
  the implementation is reviewed and committed.
- This run used sweet_190 only. To evaluate robustness, repeat the same direct
  runner on sweet_220 or the final six demand scenarios.

## 2026-06-29 Claude-Style Sweet-220 Five-Controller Screening

### Purpose

Repeat the direct Claude-style five-controller comparison on `sweet_220` to
test whether the leader value becomes larger under the more saturated demand
level, as suggested by the archived Claude log
`2026-06-29/leader_sweet220_3600.log`.

### Verification

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile work/run_claude_style_five_controller.py
```

Passed.

### Run Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work/run_claude_style_five_controller.py --scenario sweet_220 --T-total 3600 --output outputs/claude_style_sweet220_3600_20260629
```

### Results

| controller | Total TTT | Urban TTT | Freeway TTT | Total delay | TTT improvement vs no-control | Completed veh | Terminal veh | Mean solve / step |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 8800.579 | 4716.835 | 4083.744 | 7788.299 | 0.000% | 7898.2 | 18309.4 | 0.000 s |
| WU-CD-F | 8496.749 | 4509.986 | 3986.763 | 7484.470 | 3.452% | 8133.0 | 18073.1 | 9.536 s |
| WU-FAITHFUL-FOLLOWER | 7161.238 | 4806.667 | 2354.572 | 6148.959 | 18.628% | 9986.8 | 16220.0 | 1.986 s |
| P-STACK-WU-FAITHFUL | 6435.117 | 5066.189 | 1368.928 | 5422.837 | 26.878% | 11698.5 | 14512.2 | 9.790 s |
| CLASSICAL-HIERARCHICAL | 8768.950 | 4707.365 | 4061.585 | 7756.671 | 0.359% | 7914.2 | 18293.5 | 0.002 s |

### Interpretation

- Unlike `sweet_190`, `sweet_220` shows a clear leader value:
  P-Stack improves Total TTT from `7161.238` to `6435.117` veh-h relative to
  Wu-faithful PFO, a marginal gain of about `8.25 pp` vs no-control.
- The gain comes mostly from freeway TTT reduction:
  freeway TTT drops from `2354.572` to `1368.928` veh-h, while urban TTT
  increases from `4806.667` to `5066.189` veh-h. This is a deliberate
  urban-freeway tradeoff, not no-action.
- Throughput and terminal burden also improve under P-Stack:
  completed vehicles increase from `9986.8` to `11698.5`, and terminal vehicles
  decrease from `16220.0` to `14512.2`.
- P-Stack computation remains in the Claude-style range:
  mean `9.790 s/step`, max `13.123 s/step`.
- The archived Claude sweet_220 log reported a stronger P-Stack result
  (`6154.839` veh-h). Re-running the original script
  `2026-06-28/run_leader_wu_metered.py sweet_220 3600` under the current pulled
  code also returns `6435.117` for P-Stack, with no-control `8800.579` and PFO
  `7161.238`. Therefore the archived stronger number should be treated as a
  previous-code/config-state result, not the current reproducible result.

### Leader Penalty Activity

Current `sweet_220` P-Stack selected candidates used nonzero penalties:

- `leader_mfd_storage_penalty`: mean `456.99`, max `1210.69`
- `leader_density_penalty`: mean `22.29`, max `70.60`
- `leader_target_penalty`: `0`
- `leader_boundary_in_queue_penalty`: `0`
- `leader_smoothness_penalty`: `0`

Thus the leader is not pure follower TTT, but the active penalty structure is
mainly all-urban half-cap storage pressure plus freeway density pressure.

## 2026-06-29 Sweet-190 vs Sweet-220 Leader Marginal Effect Diagnostic

### Purpose

Compare `WU-FAITHFUL-FOLLOWER` and `P-STACK-WU-FAITHFUL` under `sweet_190` and
`sweet_220` to explain why adding the leader is nearly neutral at `190`, but
substantially beneficial at `220`.

### Diagnostic Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\analyze_leader_190_220.py
```

This command post-processes existing run outputs:

- `outputs/claude_style_sweet190_3600_20260629`
- `outputs/claude_style_sweet220_3600_20260629`

### Key Results

| scenario | Delta Total TTT, P-Stack - PFO | Delta Urban TTT | Delta Freeway TTT | Delta completed veh | Delta terminal veh |
|---|---:|---:|---:|---:|---:|
| sweet_190 | -1.642 | +27.794 | -29.435 | +31.0 | -31.0 |
| sweet_220 | -726.121 | +259.522 | -985.644 | +1711.7 | -1707.8 |

Fallback guard columns existed in the diagnostics, but were not selected in
either run:

- `leader_fallback_guard_selected`: `0`
- `leader_fallback_guard_selected_pfo`: `0`
- `leader_fallback_guard_selected_no_control`: `0`
- `leader_fallback_guard_rejected_leader`: `0`

Therefore these two comparisons reflect the leader-selected candidates, not a
PFO/no-control fallback outcome.

### Control / State Explanation

At `sweet_190`, the follower-only solution is already close to the leader's
preferred operating region. P-Stack reduces total ramp metering command from
about `2246.2` to `1540.1` veh/h and slightly shifts greens, but the realized
freeway state barely changes: mean freeway densities are `53.68/26.57` for PFO
and `53.58/26.17` for P-Stack. The leader saves `29.435` veh-h on the freeway
but adds `27.794` veh-h in the urban network, so the net gain is only
`1.642` veh-h.

At `sweet_220`, the follower-only solution over-admits into the freeway
bottleneck regime. PFO's total ramp metering command averages `3870.0` veh/h,
while P-Stack lowers it to `1271.6` veh/h and strongly reallocates boundary
greens. This moves freeway mean density/speed from `68.98/66.59` veh/km and
`29.45/31.41` km/h under PFO to `49.69/43.58` veh/km and `45.95/52.56` km/h
under P-Stack. The urban burden increases by `259.522` veh-h, but freeway TTT
falls by `985.644` veh-h, producing a large net improvement.

### Interpretation

The leader value is demand-regime dependent. At `sweet_190`, the system is near
the controllable shoulder of congestion, so the leader mostly creates a small
urban-freeway redistribution. At `sweet_220`, the same local follower logic
crosses a nonlinear freeway congestion threshold; the leader's global
objective and active storage/density penalties select a much stricter
metering/perimeter operating point, preventing freeway breakdown and improving
throughput.

## 2026-06-29 Bounded VSL Sequence Search Diagnostic

### Purpose

Test whether VSL was inactive because the follower only evaluated a single
near-term VSL value near the previous `100 km/h` setting. In the prior local
search, the first feasible reduction was commonly `100 -> 80`, but `80 km/h`
does not necessarily bind flow in the near-critical density range. Therefore
the controller could miss the useful preventive sequence
`100 -> 80 -> 60 -> 50`.

### Implementation

Changed `src/controllers/wu_faithful_follower.py` so the freeway follower can
evaluate bounded VSL sequences over the local prediction horizon while still
applying only the first VSL vector to the plant. The sequence search respects
the configured discrete VSL set and `max_vsl_step`. It also sanitizes
bottleneck/downstream segments to the maximum VSL and only lowers upstream
segments, avoiding accidental downstream discharge suppression.

Added configuration fields in `src/models/state.py` and
`src/config/default.yaml`:

- `freeway_follower.vsl_sequence_search: true`
- `freeway_follower.vsl_sequence_horizon_steps: 4`
- `freeway_follower.vsl_sequence_candidate_limit: 12`

Added `src/tests/test_constraints.py::test_wu_faithful_vsl_sequence_reaches_lower_future_values`
to verify that the candidate generator includes the bounded future path and
respects the VSL step bound.

### Verification Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\wu_faithful_follower.py src\models\state.py src\tests\test_constraints.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_wu_faithful_vsl_sequence_reaches_lower_future_values
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_freeway_follower_expands_time_varying_vsl_sequence
```

All three commands passed.

One unrelated targeted WU distributed test was also checked:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_six_controller_comparison.WuDistributedFixesTests.test_c_capacity_drop_wired_and_upstream_vsl_available
```

It failed with `FW_W: upstream plain segment VSL was not selected`. This test
targets `WuDistributedController`, not the modified `WuFaithfulFollower` path,
so it is recorded as an existing/adjacent WU-CD-F issue rather than evidence
against the bounded sequence implementation.

### Smoke Run

Final bounded-sequence smoke command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\run_claude_style_five_controller.py --scenario sweet_220 --T-total 1800 --controllers NO-CONTROL,WU-FAITHFUL-FOLLOWER,P-STACK-WU-FAITHFUL --output outputs\bounded_vsl_sequence_sweet220_1800_limit12_20260629
```

| controller | Total TTT | delay | improvement vs no-control | completed veh | terminal veh | mean solve s/step |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 2091.134 | 1590.218 | 0.00% | 4541.1 | 8692.4 | 0.000 |
| WU-FAITHFUL-FOLLOWER | 1595.636 | 1094.720 | 23.70% | 6587.0 | 6645.8 | 3.649 |
| P-STACK-WU-FAITHFUL | 1565.932 | 1065.016 | 25.12% | 7253.8 | 5962.8 | 21.426 |

### VSL Activation Result

The bounded sequence search did activate VSL:

- `WU-FAITHFUL-FOLLOWER`: active in 9 of 10 logged control steps, minimum VSL
  `50 km/h`, mean VSL about `88.2 km/h`.
- `P-STACK-WU-FAITHFUL`: active in 4 of 10 logged control steps, minimum VSL
  `50 km/h`, mean VSL about `94.8 km/h`.

Therefore the previous lack of VSL activation was partly a search-horizon
issue: a locally evaluated one-step VSL move could not see the future
`100 -> 80 -> 60 -> 50` path.

### Regression Against Previous No-Sequence Behavior

Comparing the first 1800 s of the existing no-sequence run
`outputs/claude_style_sweet220_3600_20260629` against the bounded sequence
run:

| controller | old no-sequence first 1800 s Total TTT | bounded sequence Total TTT | delta |
|---|---:|---:|---:|
| WU-FAITHFUL-FOLLOWER | 1484.847 | 1595.636 | +110.788 |
| P-STACK-WU-FAITHFUL | 1474.109 | 1565.932 | +91.823 |

This means bounded VSL sequence search fixed the activation barrier, but it did
not improve realized Total TTT in the `sweet_220` early-horizon smoke case.
The plant/global objective still appears to prefer the previous RM/green-heavy
solution without VSL activation for this scenario window.

### Interpretation / Next Modification

Do not treat this bounded-sequence result as an accepted performance
improvement. It is a diagnostic improvement for search coverage: VSL can now
be found when the only useful action is a bounded future sequence. However,
the realized 1800 s TTT increased relative to the prior no-sequence behavior.

Recommended next step if bounded VSL sequence is retained:

- Add a VSL commit guard that evaluates the best bounded VSL sequence against
  a max-VSL reference under the same RM/green/offset/leader context and only
  applies VSL when it improves the local rollout objective and a short realized
  plant proxy.
- Alternatively, keep `vsl_sequence_search` disabled for production
  comparison runs and reserve it for incident/VSL-specific sensitivity tests
  until the guard is implemented.

## 2026-06-30 Theoretical Controller Complexity Scaling

### Purpose

Prepared a theoretical scaling explanation for the six-controller comparison,
with `n` defined as the number of distributed follower players. The goal is to
support the presentation argument that P-Stack is not a full centralized joint
search: it evaluates low-dimensional leader coupling targets and delegates the
detailed actuator decisions to distributed follower responses.

### Outputs

- `reports/theoretical_controller_complexity_scaling.md`
- `scripts/plot_theoretical_controller_complexity.py`
- `reports/figures/theoretical_complexity/controller_complexity_scaling.png`
- `reports/figures/theoretical_complexity/controller_complexity_scaling.pdf`
- `reports/figures/theoretical_complexity/controller_complexity_scaling.csv`

### Summary

Under fixed local candidate budgets, fixed Nash/Jacobi iteration count, fixed
horizon length, and fixed leader candidate budgets:

- `WU-CD-F`: `O(n)`
- `WU-MATCHED-STACKELBERG`: `O(n)` with a larger leader-candidate constant
- `PROPOSED-FOLLOWERS-ONLY`: `O(n)`
- `PROPOSED-STACKELBERG`: `O(n)` with the largest distributed-response constant
- exact `WU-CC-F` / `PROPOSED-CENTRALIZED`: exponential in `n` because exact
  joint action search scales as a Cartesian product of local action sets
- budgeted centralized implementations: `O(n)` only because the number of
  sampled/evaluated joint actions is capped, so they are approximate references
  rather than exact centralized optima.

### Verification

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B scripts\plot_theoretical_controller_complexity.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile scripts\plot_theoretical_controller_complexity.py
```

Both commands completed successfully.

## 2026-06-30 sweet_190 3600 s PFO vs P-Stack Gridlock-Penalty Check

### Purpose

The user raised a plausible interpretation: the P-Stack leader's urban
storage/MFD penalty may slightly worsen short-horizon TTT while preventing
urban gridlock and improving longer-horizon network performance. I tested this
by extending the `sweet_190` comparison from 1800 s to 3600 s.

### Commands

The preceding fair 1800 s six-controller run was allowed to complete without
interruption:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_190 --T-total 1800 --controllers NO-CONTROL,WU-CD-F,CLASSICAL-HIERARCHICAL,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG,PROPOSED-CENTRALIZED --output outputs\actual_controller_compute_time_sweet190_1800_20260630
```

Then the longer PFO/P-Stack check was run with no-control and WU context:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_190 --T-total 3600 --controllers NO-CONTROL,WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output outputs\pfo_pstack_sweet190_3600_gridlock_penalty_check_20260630
```

### 1800 s computation context

The 1800 s full run completed. `PROPOSED-CENTRALIZED` used the new SLSQP path
and was much more expensive than the distributed/Stackelberg controllers:

| controller | Total TTT | completed vehicles | terminal vehicles | compute time sec | solver evaluations |
|---|---:|---:|---:|---:|---:|
| NO-CONTROL | 1676.556 | 4451.1 | 7015.8 | 0.00 | 0 |
| WU-CD-F | 1564.171 | 4865.0 | 6600.6 | 50.17 | 1150 |
| CLASSICAL-HIERARCHICAL | 1655.038 | 4522.7 | 6944.3 | 0.02 | 10 |
| PROPOSED-FOLLOWERS-ONLY | 1191.760 | 7007.2 | 4445.0 | 45.28 | 350 |
| PROPOSED-STACKELBERG | 1202.656 | 6924.9 | 4540.2 | 179.27 | 1385 |
| PROPOSED-CENTRALIZED | 1287.234 | 6328.1 | 5134.3 | 4280.49 | 27513 |

### 3600 s results

| controller | Total TTT | total delay | completed vehicles | terminal vehicles | throughput veh/h | compute time sec |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 7166.467 | 6292.226 | 7646.8 | 15025.2 | 7646.8 | 0.00 |
| WU-CD-F | 6827.417 | 5953.175 | 8029.9 | 14640.7 | 8029.9 | 94.35 |
| PROPOSED-FOLLOWERS-ONLY | 4814.107 | 3939.866 | 12203.7 | 10460.2 | 12203.7 | 82.33 |
| PROPOSED-STACKELBERG | 5013.465 | 4139.224 | 11836.6 | 10828.2 | 11836.6 | 275.61 |

### Queue / throughput diagnostics

| controller | mean ramp q | mean on-ramp approach q | mean boundary-in | end boundary-in | mean urban vehicles | urban departures sum | mainline exit sum | ramp releases sum |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 609.9 | 1873.5 | 1202.7 | 2885.5 | 3859.1 | 16639.4 | 49835.2 | 1250.2 |
| WU-CD-F | 575.3 | 1869.1 | 1025.1 | 2617.0 | 3700.2 | 17505.6 | 53715.1 | 1297.0 |
| PROPOSED-FOLLOWERS-ONLY | 661.8 | 1921.8 | 1063.6 | 2808.7 | 3897.1 | 17502.5 | 133762.3 | 1423.1 |
| PROPOSED-STACKELBERG | 629.8 | 1837.4 | 1241.3 | 2922.9 | 3910.7 | 17552.3 | 126925.1 | 1440.7 |

### Interpretation

The longer 3600 s run does not support the hypothesis that the P-Stack
urban/MFD penalty recovers the short-horizon TTT loss in this `sweet_190`
case. P-Stack was slightly better than PFO early in the horizon, but after
control step 10 the cumulative gap grew monotonically against P-Stack. At the
end:

- P-Stack Total TTT is `199.358 veh*h` worse than PFO.
- P-Stack completed `367.1` fewer vehicles than PFO.
- P-Stack terminal burden is `368.0` vehicles higher than PFO.
- P-Stack has lower mean ramp queue and lower on-ramp approach queue than PFO,
  but higher mean/end boundary-in queue and lower mainline exit throughput.

The leader penalty did become active: `leader_mfd_storage_penalty` grew from
near zero early to `833.8` by step 19, and `leader_boundary_in_queue_veh`
increased to `9435.0`. However, this did not translate into better realized
long-horizon Total TTT. The likely issue is not that the urban gridlock penalty
is absent; it is that the leader's proxy/penalty trade-off and/or feasible-set
conditioning still does not guarantee a realized-global-TTT improvement over
the leaderless PFO response.

### Next diagnostic

Compare PFO's realized control sequence against the P-Stack leader-conditioned
feasible set at steps 10-19. If PFO's action is not feasible under the selected
leader targets, then the leader is over-constraining the follower. If it is
feasible but not selected, then the leader response objective/proxy is still
misranking realized plant TTT.

## 2026-06-30 sweet_220 3600 s PFO vs P-Stack Gridlock-Penalty Check

### Purpose

The user asked to repeat the 3600 s gridlock-penalty check at the heavier
`sweet_220` demand level. This tests whether P-Stack's leader penalty/target
structure becomes beneficial once demand pressure is high enough that
short-term TTT sacrifices can prevent larger downstream/terminal burden.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_220 --T-total 3600 --controllers NO-CONTROL,WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output outputs\pfo_pstack_sweet220_3600_gridlock_penalty_check_20260630
```

The first attempt used a 30 s shell timeout and stopped mid-run; the command was
rerun with a longer timeout and completed.

### Results

| controller | Total TTT | total delay | completed vehicles | terminal vehicles | throughput veh/h | compute time sec |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 8800.579 | 7788.299 | 7898.2 | 18309.4 | 7898.2 | 0.00 |
| WU-CD-F | 8496.749 | 7484.470 | 8133.0 | 18073.1 | 8133.0 | 103.74 |
| PROPOSED-FOLLOWERS-ONLY | 7162.880 | 6150.600 | 9986.8 | 16220.0 | 9986.8 | 71.84 |
| PROPOSED-STACKELBERG | 6388.258 | 5375.979 | 13738.2 | 12451.7 | 13738.2 | 298.41 |

### Queue / throughput diagnostics

| controller | mean ramp q | mean on-ramp approach q | mean boundary-in | end boundary-in | mean urban vehicles | urban departures sum | mainline exit sum | ramp releases sum |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 624.9 | 2334.0 | 1759.0 | 4052.7 | 4972.0 | 16899.2 | 48702.7 | 1175.4 |
| WU-CD-F | 605.8 | 2334.7 | 1473.9 | 3818.9 | 4759.2 | 17634.8 | 50654.6 | 1199.6 |
| PROPOSED-FOLLOWERS-ONLY | 674.8 | 2421.1 | 1640.3 | 4131.6 | 5069.4 | 16923.8 | 88528.2 | 1086.6 |
| PROPOSED-STACKELBERG | 675.2 | 2351.6 | 2167.7 | 4455.3 | 5469.1 | 17021.9 | 160547.6 | 1196.5 |

### Interpretation

Unlike `sweet_190`, the heavier `sweet_220` case supports the user's
gridlock-prevention interpretation. P-Stack was worse than PFO through the
first half of the horizon, but it began improving step TTT relative to PFO at
step 10 and overtook cumulative TTT at step 14. By the end:

- P-Stack Total TTT is `774.622 veh*h` better than PFO.
- P-Stack completed `3751.4` more vehicles than PFO.
- P-Stack terminal burden is `3768.3` vehicles lower than PFO.
- P-Stack has higher boundary-in and mean urban vehicles, so it does not reduce
  every queue metric; instead, it appears to keep more demand moving through
  the freeway/urban interface and strongly improves mainline throughput.

This suggests the leader/MFD penalty may be beneficial only once demand is high
enough for the follower-only policy to accumulate a large long-horizon burden.
At moderate-heavy `sweet_190`, the same structure did not recover its cost; at
heavier `sweet_220`, it did.

### Next diagnostic

Run the same 3600 s check over an ordered demand sweep (`sweet_170`,
`sweet_190`, `sweet_220`, and possibly `sweet_240`) and locate the regime where
P-Stack crosses from worse-than-PFO to better-than-PFO. The key analysis should
track the crossover step, terminal vehicles, mainline exit flow, boundary-in
load, and ramp/on-ramp queue distribution.

## 2026-06-30 P-Stack Leader Search-Area Expansion

### Purpose

The user asked to revise the P-Stack leader search area for the current
scenario set. The previous bounds used a narrow current-availability
movement-reachability window. After the plant/scenario updates, this could keep
the leader from evaluating broad feasible target regions in stress cases.

### Implementation

Changed files:

- `src/controllers/leader.py`
- `src/controllers/stackelberg_mpc.py`
- `src/tests/test_constraints.py`
- `src/tests/test_forecast_awareness.py`
- `reports/codex_run_report.md`

Main changes:

- `Leader._candidate_bounds()` now summarizes the full forecast horizon before
  building bounds.
- `N_P_star` bounds blend from current availability reachability toward a
  physical movement-capacity envelope as demand/density/ramp-queue/urban-storage
  or incident stress increases.
- `N_UF_star` upper bounds and anchors now include ramp-arrival and queue-drain
  targets, not only the conservative rho-critical headroom estimate.
- Grid/refined/continuous leader search now receives explicit stress anchors.
- Diagnostics now log `leader_search_*`, `leader_np_capacity_*`,
  `leader_nuf_arrival_target`, and `leader_nuf_queue_drain_target`.

### Verification commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src/controllers/leader.py src/controllers/stackelberg_mpc.py src/tests/test_constraints.py src/tests/test_forecast_awareness.py

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_default_leader_np_grid_covers_feasible_net_inflow_range src.tests.test_constraints.ConstraintTests.test_leader_np_candidates_use_feasible_net_inflow_range src.tests.test_constraints.ConstraintTests.test_leader_search_area_expands_under_high_stress src.tests.test_forecast_awareness.ForecastAwarenessTests.test_leader_candidates_reflect_forecast_summary
```

Result: `4 tests OK`.

### Smoke run

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_220 --T-total 360 --controllers NO-CONTROL,PROPOSED-STACKELBERG --output outputs\pstack_leader_search_area_sweet220_smoke_20260630
```

| controller | Total TTT | delay | selected leader targets |
|---|---:|---:|---|
| NO-CONTROL | 91.780 | -9.2 | none |
| PROPOSED-STACKELBERG | 94.329 | -6.7 | `N_P_star=3500`, `N_UF_star=4320` |

This smoke is not an acceptance run. It only confirms that the expanded leader
search area is active and that closed-loop P-Stack still runs.

### Search-area diagnostics from smoke

For `sweet_220`, P-Stack logged:

- `leader_search_stress_index = 1.0`
- `leader_np_movement_upper ~= 1752 veh`
- `leader_np_capacity_upper ~= 5635 veh`
- `leader_np_bound_upper = 3500 veh`
- `leader_nuf_bound_upper = 6000 veh/h`
- `leader_nuf_arrival_target ~= 6463 veh/h`
- `leader_nuf_queue_drain_target = 6000 veh/h`

So the leader is no longer restricted to the movement-only upper bound in a
high-stress case; it can evaluate the configured global/capacity side of the
target space. The next performance step is to rerun the ordered scenario set
and compare PFO vs P-Stack after this broader search-area change.

## 2026-06-30 PFO vs P-Stack 3600 s: `fwy_peak` and `urban_peak`

### Purpose

The user asked to run only PFO and P-Stack for the freeway-peak and urban-peak
stress scenarios after the leader search-area expansion.

### Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario fwy_peak --T-total 3600 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output outputs\pfo_pstack_fwy_peak_3600_search_area_20260630

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_peak --T-total 3600 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output outputs\pfo_pstack_urban_peak_3600_search_area_20260630
```

### Results

| scenario | controller | Total TTT | delay | urban TTT | freeway TTT | completed | terminal | avg delay / completed | compute sec |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `fwy_peak` | PFO | 1631.289 | 960.533 | 1168.176 | 463.113 | 13198.7 | 3195.5 | 0.072775 | 80.34 |
| `fwy_peak` | P-Stack | 1503.443 | 832.687 | 1006.457 | 496.986 | 13652.4 | 2750.3 | 0.060992 | 218.78 |
| `urban_peak` | PFO | 1674.832 | 750.711 | 1368.994 | 305.837 | 16959.7 | 2490.1 | 0.044264 | 84.96 |
| `urban_peak` | P-Stack | 1711.893 | 787.773 | 1363.320 | 348.573 | 16691.8 | 2760.1 | 0.047195 | 221.79 |

### P-Stack vs PFO deltas

| scenario | Total TTT change | TTT change % | completed change | terminal change | interpretation |
|---|---:|---:|---:|---:|---|
| `fwy_peak` | -127.846 | +7.84% better | +453.7 | -445.2 | P-Stack improves network outcome. It trades slightly higher freeway TTT for much lower urban TTT and lower terminal burden. |
| `urban_peak` | +37.061 | -2.21% worse | -267.9 | +270.0 | P-Stack worsens total outcome. Urban TTT falls only slightly, while freeway TTT and terminal burden increase. |

### Leader diagnostics

For `fwy_peak`, P-Stack selected average `N_P_star ~= 1327.9` and
`N_UF_star ~= 4803.0`; `leader_search_stress_index` averaged `0.402`.

For `urban_peak`, P-Stack selected average `N_P_star ~= 1741.0` and
`N_UF_star ~= 5662.5`; `leader_search_stress_index` averaged `0.687`.

Both scenarios had `leader_nuf_bound_upper = 6000 veh/h`, so the ramp-release
side was open. However, the continuous search evaluated only about `3.7` full
leader candidates per step on average, reflecting the active local/top-K
lightweight budget. If `urban_peak` remains important, the next diagnostic is
to increase the local continuous eval budget/top-K for that scenario and check
whether the worsening is a true leader-objective choice or a search-budget
artifact.

## 2026-06-30 PFO vs P-Stack 3600 s: `urban_med`

### Purpose

The user asked to also check the urban-median case. The configured scenario
name is `urban_med`.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --T-total 3600 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output outputs\pfo_pstack_urban_med_3600_search_area_20260630
```

### Results

| scenario | controller | Total TTT | delay | urban TTT | freeway TTT | completed | terminal | avg delay / completed | compute sec |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `urban_med` | PFO | 998.635 | 231.123 | 742.730 | 255.905 | 15663.1 | 1201.6 | 0.014756 | 86.04 |
| `urban_med` | P-Stack | 1148.707 | 381.196 | 865.832 | 282.875 | 15433.0 | 1431.3 | 0.024700 | 227.84 |

### P-Stack vs PFO delta

| Total TTT change | TTT change % | completed change | terminal change | interpretation |
|---:|---:|---:|---:|---|
| +150.072 | -15.03% worse | -230.1 | +229.7 | P-Stack worsens both urban and freeway TTT in this scenario. |

### Leader diagnostics

P-Stack selected average `N_P_star ~= 1232.7` and `N_UF_star ~= 5700.0`.
`leader_search_stress_index` averaged only `0.242`, while the leader still
often selected high ramp-release targets (`N_UF_star` 5250-6000). The average
full leader candidate count was again about `3.7` per step.

Interpretation: unlike `fwy_peak`, the urban-median case does not benefit from
the broader leader search area. The leader layer appears to add coordination
cost without producing enough downstream benefit. Next diagnostic should check
whether high `N_UF_star` in `urban_med` is being chosen because the leader
proxy underprices urban-side burden, or because the local continuous search
budget is too narrow.

### Additional diagnosis, excluding fallback guard

The user clarified that fallback should not be used as the explanation. The
P-Stack run should therefore be interpreted directly as the leader-conditioned
solution.

Key step-log differences (`P-Stack - PFO`):

| metric | mean step delta | cumulative/step-sum delta | last-step delta |
|---|---:|---:|---:|
| urban TTT | +6.155 | +123.103 | +4.805 |
| freeway TTT | +1.348 | +26.970 | +6.364 |
| ramp queue | +50.589 veh | +1011.786 veh | +190.025 veh |
| urban total vehicles | +124.502 veh | +2490.049 veh | +103.832 veh |
| urban departures | -5.245 veh/h | -104.909 veh/h | -20.347 veh/h |
| mainline exit flow | -121.178 veh/h | -2423.568 veh/h | -130.326 veh/h |

Control interpretation:

- VSL stayed neutral at `100 km/h`; offset stayed zero; mean green remained
  `56 s`. The bad outcome is not an offset/VSL artifact.
- PFO kept total ramp-metering command near capacity on average
  (`~5977.5 veh/h`), while P-Stack averaged `~5700 veh/h` and dropped to
  `5250 veh/h` in later steps.
- P-Stack selected `N_UF_star` near the upper end (`5250-6000 veh/h`) even
  though the actual command became lower than PFO, increasing ramp queue and
  terminal on-ramp burden.
- P-Stack also selected positive `N_P_star` after step 10 (`~2464 veh`), which
  increased urban accumulation without enough departure/throughput benefit.

Conclusion: in `urban_med`, PFO is already close to a low-congestion local
solution. The leader-conditioned solution adds a perimeter/ramp target that
reduces freeway residual burden in some places but stores more vehicles in the
urban/on-ramp side and lowers completed vehicles. This is a leader search /
leader-objective alignment issue under moderate urban demand, not a fallback
selection issue.

## 2026-06-30 P-Stack deep leader-search probe: `urban_med`

### Purpose

The user asked whether the `urban_med` P-Stack degradation is caused by a too
shallow leader search. This run increases the leader continuous search budget
and disables fallback so the result reflects the leader-conditioned solution
only.

### Implementation

Added CLI overrides to `src/experiments/six_controller_comparison.py` for:

- `--leader-continuous-local-max-evals`
- `--leader-continuous-local-seed-count`
- `--leader-continuous-local-prefilter-samples`
- `--leader-continuous-local-prefilter-top-k`

Syntax check:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "src\experiments\six_controller_comparison.py"
```

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --T-total 3600 --controllers PROPOSED-STACKELBERG --output "outputs\pstack_urban_med_3600_leader_deep_search_20260630" --disable-stackelberg-fallback --leader-continuous-max-evals 40 --leader-continuous-seed-count 20 --leader-continuous-prefilter-samples 101 --leader-continuous-prefilter-top-k 20 --leader-continuous-local-max-evals 30 --leader-continuous-local-seed-count 20 --leader-continuous-local-prefilter-samples 61 --leader-continuous-local-prefilter-top-k 15 --leader-continuous-min-np-step-veh 20 --leader-continuous-min-nuf-step-veh-h 50 --leader-continuous-local-iterations 6
```

### Result

| run | Total TTT | urban TTT | freeway TTT | completed | terminal | compute sec | solver evals |
|---|---:|---:|---:|---:|---:|---:|---:|
| PFO previous | 998.635 | 742.730 | 255.905 | 15663.1 | 1201.6 | 86.04 | 700 |
| P-Stack previous | 1148.707 | 865.832 | 282.875 | 15433.0 | 1431.3 | 227.84 | 2812 |
| P-Stack deep search | 1410.062 | 1162.102 | 247.960 | 15352.3 | 1513.0 | 1687.31 | 14056 |

### Diagnostics

| run | mean full leader evals | mean proxy evals | mean `N_P_star` | mean `N_UF_star` | mean ramp command | mean ramp queue | mean urban vehicles |
|---|---:|---:|---:|---:|---:|---:|---:|
| P-Stack previous | 3.7 | 23.9 | 1232.7 | 5700.0 | 5700.0 | 68.2 | 880.0 |
| P-Stack deep search | 28.7 | 78.5 | 1272.6 | 5921.7 | 5921.7 | 20.9 | 1180.4 |

Increasing the search budget did not recover the PFO-like solution. It selected
even higher `N_UF_star` and similar/high `N_P_star`, reduced ramp queue, and
improved freeway TTT slightly, but it loaded the urban side much more heavily:
urban TTT increased to `1162.102 veh-h`, completed vehicles fell, and terminal
vehicles increased. This indicates that the `urban_med` degradation is not
primarily caused by insufficient leader candidate search. The next issue is the
leader objective / rollout fidelity under moderate urban demand: the leader is
finding a solution that is better for its current predicted/follower-response
criterion than for realized plant Total TTT.

### PFO reverse-`N_P` search-space check

The user asked whether the PFO behavior, reversed into an equivalent
`N_P_star`, lies in the leader search space. The run logs record plant
`net_inflow` in veh/h, while `N_P_star` is a horizon vehicle target. From the
P-Stack logs, `urban_net_inflow_target_veh_h = N_P_star / 0.15 h`, so the PFO
reverse target was computed as:

```text
PFO_reverse_N_P_veh = PFO_run_log.net_inflow_veh_h * 0.15 h
```

Result:

| check | inside count | interpretation |
|---|---:|---|
| PFO reverse `N_P` inside leader base envelope `diag_leader_np_bound_*` | 20 / 20 | The broad leader candidate envelope covers the PFO-like target. |
| PFO reverse `N_P` inside actual continuous search bounds `diag_leader_continuous_search_bound_np_*` | 2 / 20 | The local continuous search around the previous leader target excludes the PFO-like target in most steps. |
| Deep P-Stack selected `N_P` inside actual continuous search bounds | 20 / 20 | The deep run is internally consistent with its local search bounds. |

PFO reverse `N_P` summary:

| metric | mean | min | max | last |
|---|---:|---:|---:|---:|
| PFO reverse `N_P` from plant `net_inflow` | -224.4 | -457.1 | 674.3 | -457.1 |
| P-Stack deep selected `N_P_star` | 1272.6 | -157.0 | 2623.8 | 2569.8 |
| actual continuous search width | 401.2 | 0.0 | 4505.0 | 0.0 |
| base envelope width | 4016.8 | 2505.4 | 4843.7 | 3829.6 |

Interpretation: PFO is not outside the leader's broad feasible envelope, but it
is outside the actual local continuous search region in 18 of 20 control steps.
The deep-search run therefore did not test "can the leader choose PFO-like
`N_P` at each step"; it mostly evaluated more candidates near the previous
leader target. At the global-refresh steps where the actual search was broad
(steps 0 and 10), the PFO-like target was inside the search region, but the
leader still selected the high/upper-side target. This points to a two-part
problem:

1. local incumbent search traps the leader away from the PFO-like region after
   an early choice;
2. at broad-refresh steps, the leader objective still prefers a high
   `N_P_star` solution under `urban_med`, so objective/rollout fidelity remains
   a separate issue.

### Urban signal-distributor / `N_P_star` feasibility diagnosis

The user asked whether the urban-agent signal distributor added for feasibility
could be malfunctioning. The stored deep-search logs indicate a strong mismatch
between the leader `N_P_star` target, the Wu-faithful follower's predicted
urban net-inflow response, and the realized plant net inflow.

For the P-Stack deep-search run:

| metric | mean | min | max | last |
|---|---:|---:|---:|---:|
| leader `N_P_star` target [veh] | 1272.6 | -157.0 | 2623.8 | 2569.8 |
| follower `wu_faithful_sum_nin` [veh] | 615.4 | 427.4 | 927.8 | 438.1 |
| plant reverse `N_P = net_inflow * 0.15h` [veh] | -165.0 | -562.3 | 674.3 | -562.3 |
| plant tracking error, horizon-scaled [veh] | 1512.8 | 13.8 | 3132.1 | 3132.1 |

Representative late steps:

| step | target `N_P` | follower `sum_nin` | plant reverse `N_P` | lambda |
|---:|---:|---:|---:|---:|
| 10 | 2623.8 | 830.4 | 58.2 | 0.0 |
| 15 | 2569.8 | 539.7 | -430.9 | 0.0 |
| 19 | 2569.8 | 438.1 | -562.3 | 0.0 |

Code-level cause candidate:

- `src/controllers/wu_faithful_follower.py` adds the dual term as
  `cost += lambda_p * nin`. Positive `lambda_p` can only discourage higher
  net inflow.
- `_bisect_lambda_for_np` returns `lambda=0` when `N_P_star >= nin(0)`, so a
  high positive `N_P_star` becomes slack rather than an equality target.
- The final dual commit is gated by `if dual_active and n_p_star > 0.0`, so
  negative net-inflow targets are not actively enforced either.

Interpretation: the current Wu-faithful urban signal distributor is not
implementing the current intended meaning of `N_P_star` as a signed/equality
net-inflow target. It behaves more like a one-sided upper-bound/cap mechanism:
it can suppress net inflow when the target is below the unconstrained response,
but it cannot encourage additional inflow when the leader selects a high
target, and it ignores negative targets in the final dual commit. This explains
why the leader can select high `N_P_star` while the realized plant net inflow
remains negative.

## 2026-06-30 WuFaithfulFollower `N_P_star` Signed Equality Fix

### 援ы쁽 ?댁슜

- `src/controllers/wu_faithful_follower.py`?먯꽌 `N_P_star`瑜?one-sided cap???꾨땲??  signed/equality net-inflow target[veh over horizon]?쇰줈 異붿쟻?섎룄濡??섏젙?덈떎.
- ?꾩옱 state/forecast? green feasible set 湲곗??쇰줈 follower媛 留뚮뱾 ???덈뒗
  `誇nin_min/max`瑜?`_agent_net_inflow_veh`? 媛숈? ?⑥쐞/?뺤쓽[veh]濡?怨꾩궛?섎뒗 helper瑜?異붽??덈떎.
- 理쒖쥌 dual commit 吏곸쟾??follower ?덉륫 ?곹깭?먯꽌 leader ??target??  `[誇nin_min, 誇nin_max]`濡??ъ쁺?섍퀬, plant control??臾쇰━?곸쑝濡?clipping?섏? ?딅뒗??
- `貫<0`? ?????쒖쑀?? `貫>0`? ???묒? ?쒖쑀?낆쓣 ?좊룄?섎룄濡?signed bracket怨?bisection/nearest
  response ?좏깮???ъ슜?쒕떎.
- `n_p_star > 0` final commit gate瑜??쒓굅??negative target??dual commit 寃쎈줈瑜??꾨떎.
- diagnostics 異붽?:
  - `wu_faithful_np_original_target`
  - `wu_faithful_np_projected_target`
  - `wu_faithful_np_feasible_min`
  - `wu_faithful_np_feasible_max`
  - `wu_faithful_np_projection_residual`
  - `wu_faithful_sum_nin`
  - `wu_faithful_np_target_error`

### 蹂寃??뚯씪

- `src/controllers/wu_faithful_follower.py`
- `reports/codex_run_report.md`

### ?ㅽ뻾 紐낅졊

Baseline run command: ?대쾲 ?⑥튂??follower ?대? 踰꾧렇 ?섏젙?대ŉ full baseline simulation? ?ㅽ뻾?섏? ?딆븯??

Proposed-controller run command: full proposed simulation? ?ㅽ뻾?섏? ?딆븯??

寃利?紐낅졊:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src/controllers/wu_faithful_follower.py

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_wu_faithful_vsl_sequence_reaches_lower_future_values -v
```

異붽? smoke:

```text
urban_med, T_total=180, horizon_steps=1, max_nash_iter=1,
LeaderAction(N_P_star=9999.0, N_UF_star=1000.0)
-> original=9999.0, projected=391.1, feasible=[315.675, 391.1],
   projection_residual=9607.9, sum_nin=391.1, target_error=0.0

LeaderAction(N_P_star=-9999.0, N_UF_star=1000.0)
-> original=-9999.0, projected=315.675, feasible=[315.675, 391.1],
   projection_residual=-10314.675, sum_nin=315.675, target_error=0.0,
   lambda_P=1.027069
```

### 寃곌낵

- Baseline Total TTT/TTS: N/A, full baseline simulation 誘몄떎??
- Proposed Total TTT/TTS: N/A, full proposed simulation 誘몄떎??
- Improvement rate: N/A.
- Boundary queue balancing result: N/A, closed-loop 鍮꾧탳 誘몄떎??
- Control validation summary:
  - `py_compile`: PASS
  - 湲곗〈 WuFaithful follower VSL sequence ?⑥쐞 ?뚯뒪?? PASS
  - 吏㏃? signed target smoke: PASS, original/projected/sum_nin/target_error diagnostics ?뺤씤.

### ?ㅽ뙣 湲곗? 諛??ㅼ쓬 ?섏젙

- Full acceptance???꾩쭅 ?먮떒?섏? ?딆븯?? unit smoke留??섑뻾?덉쑝硫?closed-loop smoke?
  baseline/proposed ?숈씪-demand 鍮꾧탳??誘몄떎?됱씠??
- ?ㅼ쓬 ?④퀎??`urban_med` P-Stack deep/search run???ъ떎?됲빐 projected target怨?plant realized
  net inflow 李⑥씠瑜?遺꾨━?댁꽌 ?뺤씤?섎뒗 寃껋씠?? Projection? follower predicted feasibility留?蹂댁옣?섎?濡?
  plant realized net inflow mismatch媛 ?⑥쑝硫?rollout fidelity ?먮뒗 leader objective 履쎌쓣 蹂꾨룄濡?吏꾨떒?쒕떎.
## 2026-06-30 Urban-Med 1800 s PFO vs P-Stack After Signed `N_P_star` Projection Fix

### Implementation / Verification Summary

- Fixed the Wu-faithful urban follower's Stackelberg `N_P_star` handling so the leader target is treated as a signed/equality net-inflow target in vehicles over the MPC horizon, not as a one-sided cap.
- Added a follower-predicted feasible range `[sum_nin_min, sum_nin_max]` and projected raw leader `N_P_star` into that range before the final urban follower commit.
- Added signed dual search so `lambda_P < 0` can encourage higher net inflow and `lambda_P > 0` can discourage net inflow.
- Preserved the raw leader target in `control.N_P_star` while passing the projected target to plant/logging diagnostics through `urban_net_inflow_target_veh`.
- Added a targeted constraints test for high/low infeasible `N_P_star` projection and matching `sum_nin`.

Changed files:

- `src/controllers/wu_faithful_follower.py`
- `src/models/urban_queue_model.py`
- `src/tests/test_constraints.py`
- `src/experiments/six_controller_comparison.py`
- `reports/codex_run_report.md`

Validation commands:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src/controllers/wu_faithful_follower.py src/models/urban_queue_model.py src/experiments/six_controller_comparison.py src/tests/test_constraints.py

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_wu_faithful_np_target_projects_to_signed_feasible_range src.tests.test_constraints.ConstraintTests.test_wu_faithful_vsl_sequence_reaches_lower_future_values -v
```

Verification result:

- `py_compile`: PASS.
- Targeted constraint tests: PASS.
- Direct high/low target smoke: PASS. Raw `N_P_star` remains logged, projected target lies inside the follower feasible range, and `sum_nin` matches the projected target within tolerance.

### 1800 s Problem-Scenario Run

Scenario: `urban_med`

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --T-total 1800 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output "outputs\pfo_pstack_urban_med_1800_np_projection_20260630" --disable-stackelberg-fallback
```

Results:

| Controller | Total TTT (veh-h) | Urban TTT | Freeway TTT | Delay | Completed | Terminal | Compute (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| PFO | 422.280 | 302.978 | 119.302 | 44.552 | 7603.7 | 942.7 | 42.78 |
| P-Stack | 457.313 | 338.389 | 118.924 | 79.584 | 7460.0 | 1074.3 | 232.30 |

P-Stack vs PFO:

- Total TTT is worse by `+35.033 veh-h`.
- Urban TTT is worse by `+35.411 veh-h`.
- Freeway TTT is slightly better by `-0.378 veh-h`.
- Completed vehicles are lower by about `143.7 veh`.
- Terminal vehicles are higher by about `131.6 veh`.
- Computation time ratio is about `5.43x` PFO.

### Diagnostics

The follower-internal feasibility bug is largely fixed:

- Raw/original `N_P_star` mean: `838.202 veh`.
- Projected `N_P_star` mean: `827.006 veh`.
- Follower feasible range mean: `[580.601, 917.607] veh`.
- Follower `sum_nin` mean: `826.405 veh`.
- Mean follower target error: `-0.601 veh`.

However, the plant-realized net inflow still does not match the projected follower target:

- Plant realized net inflow mean: `-701.252 veh/h`.
- Horizon-scaled realized plant `N_P` mean: about `-105.19 veh`.
- Projected plant target mean: `827.006 veh`.
- Mean target-vs-realized tracking error: about `6214.627 veh/h`.
- P-Stack urban vehicles mean: `700.676`, while PFO is `627.157`.
- P-Stack on-ramp approach queue mean: `212.272`, while PFO is `144.608`.

Interpretation:

- The previous coding issue, where high `N_P_star` was not enforced inside the follower response, is fixed at the follower prediction layer.
- The remaining issue is a prediction/plant fidelity mismatch: the urban follower's predicted `sum_nin` can be made to match the projected target, but the coupled plant dynamics realize much lower or even negative net inflow.
- Therefore the current P-Stack run is still not accepted as an improvement. The next correction should align the follower candidate net-inflow calculation with the same phase/service/storage dynamics used by the plant, or constrain leader `N_P_star` using a realized-plant feasible envelope rather than only the follower-predicted envelope.

Next modification:

- Compare `_agent_net_inflow_veh` against plant-realized net inflow step by step.
- Replace or calibrate the follower's net-inflow feasibility model with a plant-faithful phase/service calculation.
- Re-run `urban_med` 1800 s PFO vs P-Stack after the plant-fidelity fix.

## 2026-06-30 Wu-Faithful `N_P` Predictor 원인분리 Variant 실험

### 구현 내용

P-Stack `urban_med`에서 follower 내부 `wu_faithful_sum_nin`은 projected
`N_P_star`를 맞추지만 plant realized `net_inflow`가 크게 어긋나는 문제를 세 가설로
분리하기 위해 Wu-faithful follower의 `N_P` predictor를 mode화했다.

- `legacy`: 기존 served-count predictor.
- `storage_aware`: receiving-space allocation, `_effective_available_space`, off-ramp storage
  occupancy/cap을 predictor에 반영.
- `current_interval`: horizon 전체 forecast arrivals를 현재 green으로 즉시 처리 가능한
  차량으로 보지 않도록 current control interval arrival만 predictor에 사용.
- `phase_substep`: cycle-average service 대신 5초 `_phase_green_fraction` 기반 local
  substep predictor 사용.

기본값은 `legacy`로 유지했다. 이 mode들은 성능 fix가 아니라 원인분리용 diagnostic
switch이며, projected target은 follower-predicted feasibility일 뿐 plant feasibility
보장이 아님을 diagnostics와 보고서에 명시한다.

변경 파일:

- `src/controllers/wu_faithful_follower.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### 검증 명령

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src/controllers/wu_faithful_follower.py src/models/state.py src/tests/test_constraints.py src/experiments/six_controller_comparison.py

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_wu_faithful_np_target_projects_to_signed_feasible_range src.tests.test_constraints.ConstraintTests.test_wu_faithful_np_predictor_modes_project_in_vehicle_units src.tests.test_constraints.ConstraintTests.test_wu_faithful_storage_predictor_caps_blocked_receiving_space -v
```

결과:

- `py_compile`: PASS.
- targeted unittest 3개: PASS.

### 1800 s `urban_med` Run

공통 조건:

- scenario: `urban_med`
- horizon: `1800 s`
- fallback: off
- PFO reference는 같은 run에서 재생성.

명령:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --T-total 1800 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output "outputs\pfo_pstack_urban_med_1800_np_predictor_legacy_20260630" --disable-stackelberg-fallback --wu-faithful-np-predictor-mode legacy

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --T-total 1800 --controllers PROPOSED-STACKELBERG --output "outputs\pstack_urban_med_1800_np_predictor_storage_aware_20260630" --disable-stackelberg-fallback --wu-faithful-np-predictor-mode storage_aware

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --T-total 1800 --controllers PROPOSED-STACKELBERG --output "outputs\pstack_urban_med_1800_np_predictor_current_interval_20260630" --disable-stackelberg-fallback --wu-faithful-np-predictor-mode current_interval

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --T-total 1800 --controllers PROPOSED-STACKELBERG --output "outputs\pstack_urban_med_1800_np_predictor_phase_substep_20260630" --disable-stackelberg-fallback --wu-faithful-np-predictor-mode phase_substep
```

요약 결과:

| Controller / predictor | Total TTT | Urban TTT | Freeway TTT | Completed | Terminal | Compute |
|---|---:|---:|---:|---:|---:|---:|
| PFO | 422.280 | 302.978 | 119.302 | 7603.7 | 942.7 | 50.73 |
| P-Stack legacy | 457.313 | 338.389 | 118.924 | 7460.0 | 1074.3 | 265.20 |
| P-Stack storage_aware | 588.309 | 476.717 | 111.592 | 6853.5 | 1688.0 | 247.97 |
| P-Stack current_interval | 514.344 | 407.682 | 106.662 | 6953.7 | 1597.6 | 229.06 |
| P-Stack phase_substep | 559.484 | 448.229 | 111.255 | 7028.0 | 1490.4 | 882.50 |

Follower predictor/plant mismatch:

| Predictor | projected `N_P` mean [veh] | `sum_nin` mean [veh] | plant `net_inflow` mean [veh/h] | tracking error mean [veh/h] |
|---|---:|---:|---:|---:|
| legacy | 827.006 | 826.405 | -701.252 | 6214.627 |
| storage_aware | 434.503 | 434.299 | -498.085 | 3394.769 |
| current_interval | 555.415 | 555.415 | -65.156 | 3767.924 |
| phase_substep | 775.963 | 775.963 | -113.919 | 5287.003 |

Operational side effects:

| Controller / predictor | mean urban vehicles | mean urban departures | mean on-ramp approach queue | mean ramp queue | mean mainline exit flow |
|---|---:|---:|---:|---:|---:|
| PFO | 627.16 | 1375.26 | 144.61 | 16.03 | 8031.38 |
| P-Stack legacy | 700.68 | 1351.13 | 212.27 | 24.91 | 7829.96 |
| P-Stack storage_aware | 1007.13 | 1179.47 | 152.86 | 15.12 | 7879.75 |
| P-Stack current_interval | 871.39 | 1210.94 | 277.84 | 11.47 | 7365.03 |
| P-Stack phase_substep | 940.51 | 1246.53 | 354.56 | 12.27 | 7360.70 |

### 진단 결론

세 predictor variant 모두 follower 내부에서는 projected target과 `sum_nin`을 맞춘다. 따라서
이전 bug였던 "leader target이 follower에서 무시됨" 문제는 재발하지 않았다.

하지만 모든 variant에서 P-Stack은 PFO보다 나빠졌다. 특히:

- `storage_aware`는 realized tracking error를 줄였지만 Total TTT는 `588.309`로 가장 크게
  악화됐다.
- `current_interval`은 plant `net_inflow` 평균을 `-65.156 veh/h`까지 끌어올려 mismatch를
  줄였지만, completed vehicles가 크게 줄고 terminal vehicles가 늘어 Total TTT가 악화됐다.
- `phase_substep`은 계산비용이 `882.50 s`로 커졌고 성능도 PFO/legacy보다 나빴다.

따라서 현재 증거로는 세 가설 중 어느 하나가 단독 주원인이라고 보기 어렵다. predictor fidelity를
높이는 보정은 follower 내부 projection의 해석을 명확히 하지만, leader가 여전히 PFO보다 나쁜
follower response를 objective상 좋은 후보로 ranking한다. 다음 원인은 leader objective/ranking의
terminal-throughput pricing 또는 follower response objective와 realized plant TTT 간 fidelity에
있을 가능성이 더 크다.

### Failed Criteria / Next Modification

- Acceptance: FAIL. P-Stack이 PFO보다 Total TTT, completed, terminal 모두 악화.
- Boundary/queue: 일부 variant는 tracking error를 줄였지만 urban vehicles와 terminal burden을 키움.
- Computation: `phase_substep`은 비용이 커서 기본 경로로 쓰기 어렵다.

다음 수정 방향:

1. Predictor mode를 default fix로 채택하지 않는다. `legacy` default 유지.
2. leader candidate별 `leader_follower_ttt_base`, terminal vehicles, completed vehicles,
   realized rollout TTT를 같은 표로 까서 왜 PFO보다 나쁜 후보가 ranking되는지 확인한다.
3. leader objective에 terminal/throughput shortfall을 직접 넣는 방식과, follower response
   objective를 realized plant rollout TTT에 더 가깝게 바꾸는 방식 중 어느 쪽이 더 일관적인지
   360/1800 s ablation으로 비교한다.

## 2026-06-30 Wu-Faithful `N_P` Predictor Three-Way Cause Isolation

### 紐⑹쟻

`urban_med`?먯꽌 P-Stack follower ?대???`wu_faithful_sum_nin`? projected
`N_P_star`瑜???異붿쟻?섏?留? plant realized `net_inflow`???ш쾶 ?닿툔?щ떎. ?대?
??媛?ㅻ줈 ?섎늻???뺤씤?덈떎.

1. receiving storage / spillback / ramp reservoir ?쒖빟 誘몃컲??2. horizon ?꾩껜 forecast arrivals瑜?利됱떆 service 媛?λ웾?쇰줈 蹂대뒗 怨쇰??됯?
3. 5珥?phase/substep plant order ???cycle-average service瑜??곕뒗 mismatch

### 援ы쁽

蹂寃??뚯씪:

- `src/models/state.py`
- `src/config/default.yaml`
- `src/controllers/wu_faithful_follower.py`
- `src/experiments/six_controller_comparison.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

異붽? config/CLI:

- `mpc.wu_faithful_np_predictor_mode`
  - `legacy`
  - `storage_aware` / `storage_guard`
  - `current_interval` / `arrival_limited`
  - `phase_substep`
  - `combined`
- `mpc.wu_np_storage_guard`
- `mpc.wu_np_arrival_mode`
- `mpc.wu_np_phase_substep`
- CLI:
  - `--wu-faithful-np-predictor-mode`
  - `--wu-np-storage-guard`
  - `--wu-np-arrival-mode`
  - `--wu-np-phase-substep`

援ы쁽 ?댁슜:

- `legacy`: 湲곗〈 horizon-arrival + cycle-average served predictor ?좎?.
- `storage_aware`: downstream receiving space, off-ramp storage acceptance,
  ramp reservoir space瑜?candidate served 怨꾩궛??諛섏쁺.
- `current_interval`: horizon ?꾩껜 demand瑜?利됱떆 service 媛?λ웾?쇰줈 蹂댁? ?딄퀬,
  first control interval arrivals留?predictor available demand濡??ъ슜.
- `phase_substep`: 5珥?phase window 湲곕컲 local predictor瑜??ъ슜. ?꾩껜 coupled
  plant rollout? ?꾨땲吏留? service timing? `_phase_green_fraction`???곕Ⅸ??

臾몄옄??diagnostics??CSV ?덉젙?깆쓣 ?꾪빐 ?곗? ?딄퀬 numeric code/flag濡?湲곕줉?덈떎.

### 寃利?紐낅졊

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\wu_faithful_follower.py src\models\state.py src\experiments\six_controller_comparison.py src\tests\test_constraints.py

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_wu_faithful_np_predictor_modes_project_in_vehicle_units src.tests.test_constraints.ConstraintTests.test_wu_faithful_storage_predictor_caps_blocked_receiving_space -v
```

寃곌낵:

- `py_compile`: PASS.
- targeted tests: PASS.

### 360 s ?먯씤遺꾨━ smoke

怨듯넻 command ?뺥깭:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --T-total 360 --controllers PROPOSED-STACKELBERG --output <output_dir> --disable-stackelberg-fallback --wu-faithful-np-predictor-mode <mode>
```

| mode | Total TTT | completed | terminal | compute s | selected raw `N_P` | projected `N_P` | plant reverse `N_P` | tracking error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| legacy | 60.208 | 1032.5 | 786.2 | 82.78 | 2367.1 | 953.8 | 447.4 | 3375.7 |
| storage_aware | 60.474 | 1024.6 | 826.2 | 84.25 | -1348.6 | 547.7 | 255.5 | 1947.9 |
| current_interval | 58.250 | 1091.8 | 747.3 | 57.37 | 2367.1 | 640.2 | 349.9 | 1935.4 |
| phase_substep | 59.507 | 1054.6 | 797.7 | 319.27 | 2367.1 | 900.7 | 446.9 | 3025.4 |

360珥?愿李?

- `storage_aware`??feasible envelope瑜??ш쾶 以꾩씠怨?raw `N_P` ?좏깮??諛붽엥??
- `current_interval`? tracking error瑜??ш쾶 以꾩?怨?360珥?TTT??媛????븯??
- `phase_substep`? raw `N_P` ?좏깮??諛붽씀吏 紐삵뻽怨?怨꾩궛鍮꾩슜???ш쾶 利앷??덈떎.

### 1800 s ?뺤씤

湲곗〈 legacy 1800珥?寃곌낵:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --T-total 1800 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output "outputs\pfo_pstack_urban_med_1800_np_projection_20260630" --disable-stackelberg-fallback
```

異붽? ?뺤씤:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --T-total 1800 --controllers PROPOSED-STACKELBERG --output outputs\pstack_np_predictor_urban_med_1800_storage_aware_20260630 --disable-stackelberg-fallback --wu-faithful-np-predictor-mode storage_aware

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --T-total 1800 --controllers PROPOSED-STACKELBERG --output outputs\pstack_np_predictor_urban_med_1800_current_interval_20260630 --disable-stackelberg-fallback --wu-faithful-np-predictor-mode current_interval
```

| mode | Total TTT | delay | completed | terminal | compute s | raw `N_P` | projected `N_P` | plant reverse `N_P` | tracking error | urban veh | on-ramp approach q |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| legacy | 457.313 | 79.584 | 7460.0 | 1074.3 | 232.30 | 838.2 | 827.0 | -105.2 | 6214.6 | 700.7 | 212.3 |
| storage_aware | 588.309 | 210.580 | 6853.5 | 1688.0 | 258.60 | -30.1 | 434.5 | -74.7 | 3394.8 | 1007.1 | 152.9 |
| current_interval | 514.344 | 136.615 | 6953.7 | 1597.6 | 222.23 | 1929.2 | 555.4 | -9.8 | 3767.9 | 871.4 | 277.8 |

PFO reference from the same legacy comparison:

| controller | Total TTT | completed | terminal |
|---|---:|---:|---:|
| PFO | 422.280 | 7603.7 | 942.7 |

### ?댁꽍

- ??媛??以?plant-fidelity mismatch瑜?媛???ш쾶 ?ㅻ챸?섎뒗 寃껋? 1踰덇낵 2踰덉씠??
  `storage_aware`? `current_interval` 紐⑤몢 net-inflow tracking error瑜??ш쾶 以꾩???
- 洹몃윭??tracking error瑜?以꾩씠??寃껊쭔?쇰줈 ?깅뒫? 媛쒖꽑?섏? ?딆븯??
  `storage_aware`???덈Т 蹂댁닔?곸쑝濡??묐룞?섏뿬 throughput???ш쾶 ?껋뿀怨?
  `current_interval`??terminal burden??以꾩씠吏 紐삵뻽??
- 3踰?`phase_substep`? 360珥덉뿉??raw `N_P` ?좏깮??諛붽씀吏 紐삵뻽怨?怨꾩궛鍮꾩슜??  ??4諛??댁긽 而ㅼ죱?? ?⑤룆 二쇱썝?몄쑝濡?蹂닿린???대졄??
- ?곕씪???꾩옱 臾몄젣???⑥닚??`N_P` feasibility predictor瑜?蹂댁닔?곸쑝濡?留뚮뱶??臾몄젣媛 ?꾨땲??
  ???뺥솗?덈뒗:
  1. 湲곗〈 predictor??plant feasible envelope瑜?怨쇰??됯??쒕떎.
  2. ?섏?留?怨쇰??됯?瑜??쒓굅?섎㈃ leader媛 demand瑜?怨쇰룄?섍쾶 留됱븘 terminal burden??而ㅼ쭊??
  3. P-Stack??PFO蹂대떎 ?섏걶 ?듭떖? `N_P` predictor ?섎굹媛 ?꾨땲??leader objective媛
     throughput/terminal burden怨?urban-freeway service tradeoff瑜??쒕?濡?ranking?섏? 紐삵븯?????덈떎.

### ?ㅼ쓬 ?섏젙 ?꾨낫

- `N_P` target???⑥닚 projected served target?쇰줈留??곗? 留먭퀬, leader objective?먯꽌
  terminal vehicles / throughput shortfall ?먮뒗 realized plant reverse `N_P` mismatch瑜?  吏곸젒 蹂닿쾶 ?댁빞 ?쒕떎.
- `storage_aware`??hard replacement媛 ?꾨땲??feasibility diagnostic ?먮뒗 soft guard濡?  ?곕뒗 ?몄씠 ?덉쟾?섎떎.
- `phase_substep`? production search ?덉そ???ｊ린?먮뒗 鍮꾩떥?? ?꾩슂?섎㈃ cheap prefilter??  selected candidate post-evaluation ?⑸룄濡??쒗븳?댁빞 ?쒕떎.
- ?ㅼ쓬 acceptance run ?꾩뿉 P-Stack leader candidate ranking?먯꽌 PFO蹂대떎 terminal burden??  而ㅼ????꾨낫媛 ???좏깮?섎뒗吏 ?꾨낫蹂?objective table???ㅼ떆 源뚯빞 ?쒕떎.


## 2026-07-01 P-Stack PFO Incumbent Patch Candidate

### 구현 내용

- `StackelbergWuMeteredController`에서 control step 시작 시 `WuFaithfulFollower.solve(state, None, forecast, pfo_previous)`를 한 번 평가해 `fallback_pfo` 후보로 등록했다.
- PFO response의 `N_P` equivalent는 `wu_faithful_sum_nin`, `N_UF` equivalent는 `sum(ramp_metering)`으로 역산하고 leader bounds 안으로 clip한다.
- 역산한 `(N_P, N_UF)`를 `leader_pfo_incumbent_*` diagnostics로 남기고, leader local/continuous search의 previous seed/center로 사용한다.
- `stackelberg_enable_pfo_incumbent` flag를 추가했다. 기본값은 `true`이며, `stackelberg_enable_fallback=false`여도 Wu-metered P-Stack의 PFO incumbent는 평가된다.
- 기존 no-control fallback과 혼동하지 않도록 `StackelbergWuMeteredController`의 fallback candidate override는 PFO 후보만 반환한다.

### 변경 파일

- `src/controllers/stackelberg_mpc.py`
- `src/controllers/stackelberg_wu_metered.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/experiments/six_controller_comparison.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### 검증 명령

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "src\controllers\stackelberg_mpc.py" "src\controllers\stackelberg_wu_metered.py" "src\models\state.py" "src\experiments\six_controller_comparison.py" "src\tests\test_constraints.py"

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_wu_pfo_incumbent_can_be_selected_when_leader_is_worse src.tests.test_constraints.ConstraintTests.test_stackelberg_wu_pfo_incumbent_flag_can_disable_candidate -v

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -c "<StackelbergWuMeteredController one-step decide smoke>"
```

결과:

- `py_compile`: PASS.
- targeted unit tests 2개: PASS.
- one-step decide smoke: PASS. 출력 `leader_fallback_enabled=0.0`, `leader_pfo_incumbent_enabled=1.0`, `leader_pfo_incumbent_active=1.0`, `N_P=367.5`, `N_UF=6000.0`.

### Acceptance 항목

- Baseline run command: not run in this patch-candidate step.
- Proposed-controller run command: not run in this patch-candidate step.
- Baseline Total TTT/TTS: not measured.
- Proposed Total TTT/TTS: not measured.
- Improvement rate: not measured.
- Boundary queue balancing result: not measured.
- Control validation summary: compile + targeted unit/smoke only.
- Failed criteria: full closed-loop baseline/proposed acceptance was not run.

### Follow-up tie-break and computation note

After review, PFO incumbent is also used as a strict safety candidate:
if a leader-conditioned replay has the same objective as the evaluated
leaderless PFO response, `StackelbergWuMeteredController` now keeps the actual
`fallback_pfo` control. This avoids treating the aggregate `(N_P, N_UF)` match
as equivalent to the PFO `ControlAction`.

Additional validation:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest src.tests.test_constraints.ConstraintTests.test_stackelberg_fallback_guard_rejects_terminal_worse_leader src.tests.test_constraints.ConstraintTests.test_stackelberg_wu_pfo_incumbent_can_be_selected_when_leader_is_worse src.tests.test_constraints.ConstraintTests.test_stackelberg_wu_pfo_incumbent_flag_can_disable_candidate

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --controllers PROPOSED-STACKELBERG --T-total 180 --output outputs/pfo_incumbent_smoke3_urban_med_180_20260701 --stackelberg-leader-parallel-backend serial
```

Results:

- `py_compile`: PASS after the tie-break patch.
- Targeted fallback/PFO incumbent unit tests: PASS (`3 tests`, `OK`).
- 180 s `urban_med` P-Stack smoke: completed.
- Diagnostics: `leader_pfo_incumbent_active=1.0`,
  `leader_pfo_incumbent_selected=1.0`,
  `leader_pfo_incumbent_tie_break_selected=1.0`,
  `leader_selected_stage_fallback_pfo=1.0`.
- PFO equivalent target in smoke: `N_P=917.45 veh`,
  `N_UF=6000.0 veh/h`.
- Total TTT in smoke: `22.692190286956883 veh-h`.
- Computation note: deep leader search is not removed. The smoke still
  evaluated `10` full leader candidates plus `56` proxy candidates and took
  `54.24033649999183 s` for the P-Stack decision. The patch improves the
  safety floor and search centering; any computation reduction must be
  evaluated separately via top-K/local-budget tuning.

## 2026-07-01 PFO-Anchor Hybrid Search, Density-Rollout Fix, and Target Runs

### Implemented

- Added PFO-anchor hybrid leader search to `StackelbergWuMeteredController`.
  - P-Stack evaluates the PFO-equivalent point as a strict incumbent.
  - Global-refresh search is centered around the PFO-equivalent `(N_P_star, N_UF_star)`.
  - A cheap full-range scout is retained, but only a small number of distant scout candidates are full-evaluated.
- Confirmed Claude's concern in the base `DistributedCoordinator._response_tts_objective`.
  - The old density penalty used current `state.freeway_density`, so ramp-release candidates did not change the density-excess penalty.
  - Added candidate-dependent density rollout via `_estimate_freeway_density_excess_tts`.
  - The response objective now charges density-excess TTS after pushing ramp release into the merge segment.
  - Note: the active Wu-faithful P-Stack path already has its own local density rollout, so this mainly fixes the base distributed response objective and diagnostics.

### Changed Files

- `src/controllers/stackelberg_wu_metered.py`
- `src/controllers/stackelberg_mpc.py`
- `src/controllers/distributed_coordinator.py`
- `src/tests/test_constraints.py`
- `reports/codex_run_report.md`

### Validation

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m py_compile src/controllers/distributed_coordinator.py src/controllers/stackelberg_wu_metered.py src/controllers/stackelberg_mpc.py src/tests/test_constraints.py

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest src.tests.test_constraints.ConstraintTests.test_distributed_response_density_rollout_charges_ramp_release src.tests.test_constraints.ConstraintTests.test_distributed_response_objective_rewards_ramp_service src.tests.test_constraints.ConstraintTests.test_stackelberg_wu_pfo_incumbent_can_be_selected_when_leader_is_worse
```

Results:

- `py_compile`: PASS.
- Targeted tests: PASS (`3 tests`, `OK`).

### 180 s Smoke

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --controllers PROPOSED-STACKELBERG --T-total 180 --output outputs/pfo_anchor_hybrid_smoke_urban_med_180_20260701 --stackelberg-leader-parallel-backend serial
```

Results:

- Total TTT: `22.692190286956883 veh-h`.
- Hybrid search diagnostics:
  - `leader_pfo_anchor_global_hybrid_active=1.0`
  - `leader_pfo_anchor_local_full_evaluated_count=3.0`
  - `leader_pfo_anchor_scout_full_evaluated_count=1.0`
  - `leader_pfo_anchor_total_full_evaluated_count=4.0`
  - `leader_candidate_full_evaluated_count=4.0`
  - `leader_pfo_incumbent_selected=1.0`
  - `leader_pfo_incumbent_tie_break_selected=1.0`
- Computation comparison against `outputs/pfo_incumbent_smoke3_urban_med_180_20260701`:
  - Previous: `10` full leader evaluations, `56` proxy candidates, `54.24033649999183 s`.
  - Hybrid: `4` full leader evaluations, `21.38388649999979 s`.

### 1800 s urban_med Comparison

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario urban_med --controllers NO-CONTROL,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --T-total 1800 --output outputs\urban_med_nocontrol_pfo_pstack_1800_20260701 --stackelberg-leader-parallel-backend serial
```

Results:

| controller | total TTT | urban TTT | freeway TTT | delay | completed | terminal | compute |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 419.499 | 299.552 | 119.947 | 41.771 | 7614.3 | 922.2 | 0.00 s |
| PROPOSED-FOLLOWERS-ONLY | 422.280 | 302.978 | 119.302 | 44.552 | 7603.7 | 942.7 | 48.85 s |
| PROPOSED-STACKELBERG | 422.280 | 302.978 | 119.302 | 44.552 | 7603.7 | 942.7 | 202.41 s |

Interpretation:

- P-Stack selected the PFO incumbent in all 10 steps.
- P-Stack therefore exactly matched PFO.
- Both controlled variants were slightly worse than no-control in this light `urban_med` 1800 s diagnostic run.

### 1800 s sweet_155 Comparison

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers NO-CONTROL,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --T-total 1800 --output outputs\sweet155_nocontrol_pfo_pstack_1800_20260701 --stackelberg-leader-parallel-backend serial
```

Results:

| controller | total TTT | urban TTT | freeway TTT | delay | completed | terminal | compute |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 518.411 | 385.865 | 132.547 | 96.522 | 8037.2 | 1308.1 | 0.00 s |
| PROPOSED-FOLLOWERS-ONLY | 529.421 | 398.413 | 131.009 | 107.532 | 7977.5 | 1380.4 | 41.11 s |
| PROPOSED-STACKELBERG | 528.180 | 399.200 | 128.980 | 106.290 | 7964.9 | 1401.6 | 195.95 s |

Interpretation:

- P-Stack improves over PFO by `1.241 veh-h` (`0.234%`).
- P-Stack is still worse than no-control by `9.769 veh-h` (`-1.884%`).
- P-Stack improves freeway TTT relative to PFO (`128.980` vs `131.009`) but shifts burden toward urban TTT (`399.200` vs `398.413`) and leaves more terminal vehicles.
- The leader selected the PFO incumbent in 9 of 10 steps; only one step selected a non-PFO leader candidate.

### Acceptance Status

- Baseline and proposed runs used the same scenario, demand, seed, and 1800 s horizon inside each comparison.
- These are diagnostic runs, not full 7200 s acceptance runs.
- The default 8% improvement threshold is not met in `urban_med` or `sweet_155`.
- Boundary queue balancing was not separately summarized in this quick comparison; run-level CSVs are preserved for follow-up diagnostics.

## 2026-07-01 Local-Info Distributed Controller Fidelity Review

### Context

The user asked for a code review of the local-info distributed controller after
`PROPOSED-FOLLOWERS-ONLY` and Wu-faithful P-Stack became worse than no-control
in recent `urban_med` and `sweet_155` runs. The review intentionally does not
recommend no-control guards as the main fix. If PFO truly minimizes a
TTT-compatible objective, it should not need a no-control guard.

Standalone report:

- `reports/local_info_distributed_controller_review_20260701.md`

### Leader Controller Changes Already Present

- `StackelbergWuMeteredController` now uses a PFO-equivalent anchor for leader
  search.
- Global search is hybrid:
  - local refinement around PFO-equivalent `(N_P_star, N_UF_star)`;
  - limited full-range scout candidates.
- The PFO incumbent is a leader-search anchor/tie-break candidate, not a
  no-control guard.
- Prior smoke result: 180 s `urban_med` P-Stack full leader evaluations reduced
  from `10` to `4`; wall time reduced from about `54.24 s` to `21.38 s`.

### Findings

1. Urban local rollout is not plant-TTT compatible.
   - `rollout_local_tts` and `rollout_local_tts_phased` charge mostly
     `sum(q.values()) * dt_h`.
   - The plant charges urban movement queues plus storage occupancy.
   - Therefore a local candidate can look good after moving vehicles out of the
     current movement queue even when the plant still holds those vehicles in
     storage or terminal burden.

2. Ramp-aware local off-ramp drain likely has a sign mismatch.
   - Local ramp-aware rollout increases downstream available space after
     off-ramp drainage.
   - The plant consumes downstream receiving space for the same movement.
   - This can make off-ramp/green choices look artificially good locally.

3. Ramp release reaches freeway density in the plant, but local timing differs.
   - The plant computes ramp metering release from the current reservoir before
     urban green release enters the reservoir.
   - The local freeway scorer can add same-step urban-to-ramp arrivals before
     metering release.
   - This can invert ramp metering candidate ranking.

4. One-step `sweet_155` probe confirmed a ranking problem.
   - No-control full coupled horizon TTT: `104.097684`.
   - PFO-selected action full coupled horizon TTT: `104.652236`.
   - A same-state F-signal green sweep found `F_p1=62 s` gives
     `103.672590`, while PFO selected `F_p1=50 s`.
   - Feasible better candidates existed; the local scorer chose the wrong one
     under plant TTT.

5. Wu-metered P-Stack prefilter is action-blind for the Wu-faithful follower.
   - The cheap prefilter uses a current-state proxy before full evaluation.
   - Different `(N_P_star, N_UF_star)` candidates can get nearly identical
     proxy scores.
   - This is secondary to local follower fidelity, but should be revisited
     after PFO scoring is corrected.

6. P-Stack fallback/PFO-anchor rows may carry post-hoc `N_P_star/N_UF_star`
   labels.
   - A leaderless PFO solve can be relabeled with PFO-equivalent leader targets
     afterward.
   - Those labels are useful as anchors, but they were not active constraints
     during the leaderless PFO solve.

### Recommended Next Modification

1. Fix `rollout_local_tts_ramp_aware` downstream storage sign.
2. Add storage/terminal-compatible vehicle accounting to ordinary/phased urban
   local rollout cost.
3. Align local freeway ramp-release timing with the coupled plant ordering.
4. Add a rank-inversion regression test comparing local candidate ranking
   against full `run_coupled_interval` rollout ranking on the same copied state.
5. Then revisit Wu-metered P-Stack prefilter so top-K pruning is
   candidate-dependent.

### Validation

- Static review: completed with three independent sub-agent reviews.
- Read-only one-step probes: completed for `urban_med` and `sweet_155`.
- Source code changed in this step: no controller code changed; report only.
- Full acceptance run: not run in this report step.

### 다음 수정/검증

- 메인 에이전트가 이 패치 후보를 채택하면 `PROPOSED-FOLLOWERS-ONLY` vs `PROPOSED-STACKELBERG` 동일 scenario/demand/horizon closed-loop run으로 PFO incumbent가 P-Stack 악화를 실제로 줄이는지 확인해야 한다.

## 2026-07-01 Wu-Faithful Freeway Ramp Timing Fix

### Context

`2026-07-01/notes.md`의 Finding #3을 구현했다. `WuFaithfulFollower`의 freeway
local rollout은 current `u_on_{ramp}` coupling arrival을 ramp reservoir에 먼저 적재한 뒤
metering release를 계산하고 있었다. 실제 coupled plant는 Spec 3.4.3 순서대로 T_f 시작 시점의
reservoir에서 release를 먼저 결정하고, 같은 T_f 안의 urban green arrival은 그 뒤 reservoir에
적재한다.

Used specs:

- `docs/spec/04_controller.md`
- `docs/spec/03_traffic_models.md`
- `docs/spec/12_coding_style.md`
- `docs/spec/15_caveats.md`
- `docs/spec/10_tests.md`

### Implementation

Changed files:

- `src/controllers/wu_faithful_follower.py`
  - `_solve_freeway_agent_local` 내부 순서를 `release -> subtract reservoir -> add current u_on arrival`로 변경.
  - `_local_ramp_release` 자체는 이미 `include_current_arrivals=False` 의미로 구현되어 있어 변경하지 않았다.
- `src/tests/test_constraints.py`
  - `test_wu_faithful_freeway_release_uses_start_reservoir_before_current_arrivals` 추가.
  - 회귀 테스트는 `u_on=3600 veh/h`, `T_f=10 s`, 초기 ramp reservoir 0 veh 조건에서 release 계산 직전
    queue가 10 veh로 보이면 실패하고 0 veh이면 통과한다.

### Validation Commands

Compile:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "src\controllers\wu_faithful_follower.py" "src\tests\test_constraints.py" "src\tests\test_local_signal_plant.py"
```

Targeted timing/sign tests:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_wu_faithful_freeway_release_uses_start_reservoir_before_current_arrivals
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_local_signal_plant
```

Related coupling/order tests:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_simulator_uses_coupling_module_diagnostics src.tests.test_constraints.ConstraintTests.test_onramp_uses_two_reservoirs_instead_of_syncing_queues src.tests.test_constraints.ConstraintTests.test_onramp_demand_enters_urban_movement_queue_when_metering_closed src.tests.test_constraints.ConstraintTests.test_onramp_green_controls_approach_release_to_ramp_queue src.tests.test_constraints.ConstraintTests.test_coupling_passes_actual_ramp_release_to_freeway_step
```

Additional existing Wu-faithful tests attempted:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_wu_faithful_vsl_sequence_reaches_lower_future_values src.tests.test_constraints.ConstraintTests.test_wu_faithful_np_target_projects_to_signed_feasible_range
```

### Validation Results

- `py_compile`: PASS.
- New ramp timing regression test: PASS.
- `src.tests.test_local_signal_plant`: PASS.
- Related coupling/order tests: PASS (`5` tests).
- Existing `test_wu_faithful_vsl_sequence_reaches_lower_future_values`: PASS when run in the two-test batch.
- Existing `test_wu_faithful_np_target_projects_to_signed_feasible_range`: FAIL, unrelated to this timing patch.
  - Failure: `KeyError: 'wu_faithful_np_projected_target_veh'`.
  - This indicates the current `WuFaithfulFollower.solve()` diagnostics no longer expose the expected N_P projection key on that path; this should be handled as a separate diagnostics/test contract issue.

### Simulation Status

- Baseline run command: not run in this targeted implementation step.
- Proposed-controller run command: not run in this targeted implementation step.
- Baseline Total TTT/TTS: not measured.
- Proposed Total TTT/TTS: not measured.
- Improvement rate: not measured.
- Boundary queue balancing result: not measured.

### Control Validation Summary

- The local freeway follower now matches the plant's two-reservoir on-ramp timing convention for same-step urban arrivals.
- This fix removes an actually reachable candidate-scoring mismatch: same-T_f urban arrivals can no longer be released into the freeway before the plant would allow them.
- Full closed-loop performance impact is still unknown until PFO/P-Stack scenario reruns are performed.

### Proposed Next Modification

1. Separately inspect the missing `wu_faithful_np_projected_target_veh` diagnostic/test contract.
2. Run a short closed-loop comparison on a scenario where ramp timing matters (`sweet_155`, `bal_med`, or `urban_med`) for:
   - `PROPOSED-FOLLOWERS-ONLY`
   - `PROPOSED-STACKELBERG`
3. Then revisit Finding #5, the Wu-metered P-Stack action-blind prefilter.

## 2026-07-01 Sweet-155 Closed-Loop Check After Ramp Timing Fix

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers NO-CONTROL,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --T-total 1800 --output outputs\sweet155_timingfix_nocontrol_pfo_pstack_1800_20260701 --stackelberg-leader-parallel-backend serial
```

### Results

| controller | Total TTT | Urban TTT | Freeway TTT | Diff vs no-control | Improvement vs no-control | Delay | Completed | Terminal | Compute |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 518.411 | 385.865 | 132.547 | 0.000 | 0.000% | 96.522 | 8037.2 | 1308.1 | 0.00 s |
| PROPOSED-FOLLOWERS-ONLY | 529.441 | 398.404 | 131.037 | +11.030 | -2.128% | 107.552 | 7976.0 | 1382.4 | 41.46 s |
| PROPOSED-STACKELBERG | 527.533 | 402.587 | 124.946 | +9.122 | -1.760% | 105.643 | 7996.8 | 1368.8 | 199.76 s |

### Interpretation

- The ramp-timing fix does not make PFO beat no-control in this `sweet_155` 1800 s run.
- P-Stack is still worse than no-control by `9.122 veh-h` (`-1.760%`).
- P-Stack improves over PFO by `1.908 veh-h` (`0.360%` of PFO Total TTT), and also has lower terminal vehicles (`1368.8` vs `1382.4`) and higher completed vehicles (`7996.8` vs `7976.0`).
- Compared with the earlier pre-fix `sweet_155` diagnostic run, P-Stack Total TTT improved from `528.180` to `527.533`, while PFO stayed essentially unchanged (`529.421` to `529.441`). The fix helps P-Stack slightly but does not resolve the no-control gap.

### Acceptance Status

- Same scenario/demand/horizon were used inside this comparison.
- Horizon is diagnostic 1800 s, not full 7200 s acceptance.
- Main 8% improvement criterion is not met.
- Boundary balancing was not separately summarized in this quick table; raw outputs are under `outputs/sweet155_timingfix_nocontrol_pfo_pstack_1800_20260701`.

### Next Diagnostic

The remaining issue is not just the same-step ramp timing mismatch. Since PFO still loses to no-control and P-Stack only partially improves over PFO, the next likely causes are:

1. local urban own-TTS scoring still missing plant-compatible storage/terminal effects;
2. P-Stack prefilter/top-K being insufficiently action-sensitive;
3. fallback/PFO-anchor labels and leader search stages masking whether P-Stack is actually evaluating enough non-PFO candidates.

## 2026-07-01 Copy-Only Frozen Reservoir Drain Candidate

### Context

The user requested that the suspected `_frozen_reservoir_drain` fix must **not**
be applied directly to the original code. A copy-only experiment was created under:

```text
work/ns_drainfix_20260701_200642
```

Two sub-agents were used:

- coding sub-agent: implemented the copy-only patch and regression test;
- review sub-agent: verified that the patch matches plant ordering and that the
  original repo does not contain this specific frozen-drain change.

Both sub-agents were closed after completion.

### Copy-Only Implementation

Changed only inside the copy:

- `work/ns_drainfix_20260701_200642/src/controllers/wu_faithful_follower.py`
  - `_frozen_reservoir_drain()` now calls:

```python
compute_ramp_release_flows(
    state,
    control,
    demand,
    self.cfg,
    include_current_arrivals=False,
)
```

- `work/ns_drainfix_20260701_200642/src/tests/test_constraints.py`
  - Added `test_wu_frozen_reservoir_drain_ignores_current_ramp_arrivals`.

### Copy-Only Validation

Commands run in copy root:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "src\controllers\wu_faithful_follower.py" "src\tests\test_constraints.py"
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_wu_frozen_reservoir_drain_ignores_current_ramp_arrivals
```

Results:

- `py_compile`: PASS.
- New copy-only regression test: PASS.
- Reviewer verdict: PASS for plant-order fidelity and test discriminating power.

### Copy-Only Closed-Loop Run

Command run in copy root:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers NO-CONTROL,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --T-total 1800 --output outputs\sweet155_frozen_drain_copy_nocontrol_pfo_pstack_1800_20260701 --stackelberg-leader-parallel-backend serial
```

Copy-only results:

| controller | Total TTT | Urban TTT | Freeway TTT | Diff vs no-control | Improvement vs no-control | Delay | Completed | Terminal | Compute |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 518.411 | 385.865 | 132.547 | 0.000 | 0.000% | 96.522 | 8037.2 | 1308.1 | 0.00 s |
| PROPOSED-FOLLOWERS-ONLY | 531.257 | 402.141 | 129.115 | +12.846 | -2.478% | 109.367 | 7962.0 | 1400.5 | 43.95 s |
| PROPOSED-STACKELBERG | 529.788 | 401.836 | 127.952 | +11.377 | -2.195% | 107.899 | 7970.8 | 1392.3 | 208.42 s |

Compared with the current original timing-fix-only run:

| controller | original Total TTT | copy Total TTT | delta | original Urban | copy Urban | original Freeway | copy Freeway |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 518.411 | 518.411 | +0.000 | 385.865 | 385.865 | 132.547 | 132.547 |
| PROPOSED-FOLLOWERS-ONLY | 529.441 | 531.257 | +1.816 | 398.404 | 402.141 | 131.037 | 129.115 |
| PROPOSED-STACKELBERG | 527.533 | 529.788 | +2.255 | 402.587 | 401.836 | 124.946 | 127.952 |

### Decision

- The copy-only candidate did **not** improve TTT.
- It worsened PFO by `+1.816 veh-h` and P-Stack by `+2.255 veh-h` relative to the current original timing-fix-only run.
- Therefore this frozen-drain change was **not applied** to the original code.

### Interpretation

The initial diagnosis that `include_current_arrivals=True` in `_frozen_reservoir_drain`
was a direct PFO degradation cause is not supported by the closed-loop experiment.
The candidate removed one plant-order mismatch, but the PFO local scorer then selected
even more aggressive F-signal green splits (`68/44`, later `80/32`), increasing urban
TTT despite lower freeway TTT. The dominant remaining issue is likely deeper in the
D/F ramp-aware urban local objective/ranking, not just in the frozen reservoir-drain
release convention.

### Next Diagnostic

Do not apply the frozen-drain candidate. Instead, inspect D/F ramp-aware green candidate
ranking directly:

1. For a fixed state/step, evaluate each candidate `green_p1` with the local
   `rollout_local_tts_ramp_aware`.
2. Evaluate the same candidate with a short full `run_coupled_interval` horizon on
   copied states.
3. Compare whether the local argmin agrees with the plant-TTT argmin.
4. If ranking differs, decompose movement queue, ramp reservoir, on-ramp approach,
   storage occupancy, and freeway TTT terms.

## 2026-07-01 Sweet-155 7200 s Wu-Faithful PFO-Anchor P-Stack Run

### Purpose

The user clarified that the intended P-Stack run is the version that first
computes the `WuFaithfulFollower` PFO response, converts that response into
leader-space `N_P_star` / `N_UF_star` anchors, and then searches around that
PFO anchor. This is the current `StackelbergWuMeteredController` path used by
`PROPOSED-STACKELBERG`.

### Commands

Current wu-faithful no-control/WU/PFO reference:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers NO-CONTROL,WU-CD-F,PROPOSED-FOLLOWERS-ONLY --T-total 7200 --output outputs\sweet155_current_wufaithful_7200_20260701 --stackelberg-leader-parallel-backend serial
```

Wu-faithful PFO-anchor P-Stack:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\sweet155_current_pstack_7200_20260701 --stackelberg-leader-parallel-backend thread
```

Validation:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\wu_faithful_follower.py src\controllers\stackelberg_wu_metered.py src\tests\test_constraints.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_wu_faithful_freeway_release_uses_start_reservoir_before_current_arrivals
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_local_signal_plant
```

### Results

| controller | Total TTT | Urban TTT | Freeway TTT | Total delay | Completed | Terminal | Compute | TTT improvement vs no-control |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | 8611.785 | 5357.164 | 3254.621 | 6886.102 | 23379.9 | 13428.9 | 0.00 s | 0.00% |
| WU-CD-F | 8842.809 | 5497.660 | 3345.149 | 7117.126 | 23276.4 | 13529.5 | 86.93 s | -2.68% |
| PROPOSED-FOLLOWERS-ONLY | 4490.018 | 3676.465 | 813.553 | 2764.335 | 32519.3 | 4244.7 | 161.61 s | 47.86% |
| PROPOSED-STACKELBERG | 4542.423 | 3720.532 | 821.891 | 2816.740 | 32268.4 | 4491.6 | 825.49 s | 47.25% |

Relative to PFO, the PFO-anchor P-Stack is worse by:

- Total TTT: `+52.405 veh-h` (`-1.17%` relative improvement vs PFO).
- Urban TTT: `+44.067 veh-h`.
- Freeway TTT: `+8.338 veh-h`.
- Completed vehicles: `-250.9`.
- Terminal vehicles: `+246.9`.

### Anchor Diagnostics

From `outputs/sweet155_current_pstack_7200_20260701/runs/sweet_155/PROPOSED-STACKELBERG/decision_diagnostics.csv`:

- `leader_pfo_incumbent_active`: `40/40` steps.
- `leader_pfo_incumbent_local_center_used`: `40/40` steps.
- `leader_pfo_incumbent_selected`: `30/40` steps.
- `leader_pfo_incumbent_tie_break_selected`: `8/40` steps.
- `leader_pfo_anchor_global_hybrid_active`: `4/40` steps.
- Average selected-vs-PFO-anchor absolute difference:
  - `N_P_star`: `3.0 veh/h`.
  - `N_UF_star`: `85.505 veh/h`.
- Selected range:
  - `N_P_star`: `781.374` to `1495.850`.
  - `N_UF_star`: `4687.5` to `6000.0`.
- Average per-step computation time: `20.64 s`.

### Interpretation

This run confirms that the executed P-Stack is the intended wu-faithful
PFO-anchor version. However, the leader layer does not improve the full
7200 s `sweet_155` result relative to PFO. Since 30 of 40 steps select the
PFO incumbent and the remaining leader deviations are small in average anchor
distance, the measured degradation is likely caused by a few non-PFO leader
deviations that look better under the leader objective but realize slightly
worse closed-loop urban/freeway TTT.

The result supports two immediate follow-ups:

1. Compare the 10 non-PFO-selected steps against the PFO incumbent candidate
   by realized next-interval TTT, completed vehicles, terminal vehicles, and
   urban/freeway split.
2. Tighten the PFO-anchor acceptance rule so the leader can deviate from PFO
   only when the predicted gain clears a stronger margin or a realized-risk
   proxy does not worsen.

### Additional Per-Step Check

After the run, per-step realized TTT was compared against the standalone PFO
run by summing `urban_ttt + freeway_ttt` from each controller's `run_log.csv`.
This comparison is not a same-state counterfactual, but it is useful for
identifying where the closed-loop gap accumulates.

- Total P-Stack minus PFO realized TTT delta: `+52.406 veh-h`.
- Steps where P-Stack did **not** select the PFO incumbent: `10/40`.
- Delta over non-PFO-selected steps only: `-17.666 veh-h`.
- Delta over PFO-selected steps: `+70.072 veh-h`.

This indicates that the non-PFO leader deviations were not immediately worse
within their own intervals. Instead, the deviations improved several middle
steps but changed the downstream state enough that later intervals, even when
the controller returned to the PFO incumbent, realized worse TTT than the
standalone PFO trajectory. The next diagnosis should therefore treat the
PFO-anchor leader issue as a delayed-state/future-risk problem rather than a
simple one-step candidate ranking error.

### Acceptance Status

- Same scenario/demand/horizon were used for no-control, WU, PFO, and P-Stack.
- `py_compile`: PASS.
- Ramp timing regression test: PASS.
- Local signal plant test: PASS.
- PFO exceeds the default 8% improvement threshold vs no-control.
- PFO-anchor P-Stack also exceeds the threshold vs no-control, but fails the
  intended leader-value comparison because it is worse than PFO by `52.405 veh-h`.

## 2026-07-01 Sweet-155 7200 s P-Stack Full Search Without PFO Anchor

### Purpose

The user asked to compare the PFO-anchor P-Stack against the older full-search
style where the leader does not first seed itself with the Wu-faithful PFO
incumbent. This run disables the PFO incumbent/anchor path while keeping the
same current `StackelbergWuMeteredController` follower implementation.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\sweet155_current_pstack_fullsearch_no_anchor_7200_20260701 --stackelberg-leader-parallel-backend thread --disable-stackelberg-pfo-incumbent
```

### Result

| controller / variant | Total TTT | Urban TTT | Freeway TTT | Total delay | Completed | Terminal | Compute |
|---|---:|---:|---:|---:|---:|---:|---:|
| PROPOSED-FOLLOWERS-ONLY reference | 4490.018 | 3676.465 | 813.553 | 2764.335 | 32519.3 | 4244.7 | 161.61 s |
| P-Stack, PFO-anchor | 4542.423 | 3720.532 | 821.891 | 2816.740 | 32268.4 | 4491.6 | 825.49 s |
| P-Stack, full search without PFO anchor | 7765.857 | 6856.346 | 909.511 | 6040.174 | 29826.1 | 6970.7 | 520.85 s |

Relative to PFO:

- PFO-anchor P-Stack: `+52.405 veh-h` worse.
- Full-search/no-anchor P-Stack: `+3275.839 veh-h` worse.

### Diagnostics

From `outputs/sweet155_current_pstack_fullsearch_no_anchor_7200_20260701/runs/sweet_155/PROPOSED-STACKELBERG/decision_diagnostics.csv`:

- PFO incumbent/anchor active: `0/40` steps.
- Selected `N_P_star` range: `-3315.0` to `2518.020`.
- Average selected `N_P_star`: `-136.8`.
- Steps with negative `N_P_star`: `20/40`.
- Steps at the lower bound (`N_P_star <= -3314.9`): `10/40`.
- Selected `N_UF_star` range: `5250.0` to `6000.0`.
- Average selected `N_UF_star`: `5681.21`.

The full-search path repeatedly selected extreme protected-network inflow
targets:

- Steps 10-19 selected approximately `N_P_star=-2016`.
- Steps 30-39 selected `N_P_star=-3315`.

This produced much larger urban TTT and terminal vehicles than both PFO and
the PFO-anchor P-Stack.

### Interpretation

The result shows that the PFO-anchor modification is not the cause of the major
P-Stack degradation. It actually prevents the leader from falling into the much
worse extreme-target regime exposed by the no-anchor full search.

The remaining PFO-anchor gap is therefore smaller and more subtle: the anchor
version mostly selects PFO, but a few leader deviations alter the downstream
state enough that later intervals realize a slightly worse trajectory. The
full-search result points to a deeper leader-objective/search issue: wide
leader search can exploit finite-horizon/terminal-accounting weaknesses and
prefer negative `N_P_star` targets that are not good for closed-loop plant TTT.

### Next Diagnostic

The next fix should not remove the PFO anchor. Instead:

1. Keep PFO as a hard incumbent/baseline.
2. Allow leader deviation only when the predicted gain exceeds a stronger
   no-regret margin.
3. Add terminal-state guards for urban accumulation, boundary/movement queue,
   completed vehicles, and terminal vehicles.
4. Inspect same-state counterfactuals for the anchor run's 10 non-PFO-selected
   steps to see which terminal state components the 540 s rollout undervalues.

## 2026-07-01 PFO-Anchor P-Stack Gap Diagnosis

### Question

Why can the PFO-anchor P-Stack still be worse than the standalone PFO even
though PFO is used as the leader anchor/incumbent?

### Evidence From Saved Runs

Runs compared:

- PFO: `outputs/sweet155_current_wufaithful_7200_20260701`
- PFO-anchor P-Stack: `outputs/sweet155_current_pstack_7200_20260701`

The PFO-anchor P-Stack gap is:

- Total TTT: `4542.423 - 4490.018 = +52.405 veh-h`.
- Urban TTT: `+44.067 veh-h`.
- Freeway TTT: `+8.338 veh-h`.
- Completed vehicles: `-250.9`.
- Terminal vehicles: `+246.9`.

### Timing of the Gap

Stepwise comparison using each controller's `progress_summary.csv` shows:

| step | cumulative P-Stack minus PFO TTT | terminal vehicles delta | PFO incumbent selected? |
|---:|---:|---:|---:|
| 10 | `0.000` | `0.0` | 1 |
| 12 | `-0.289` | `-22.1` | 0 |
| 19 | `-7.820` | `-67.6` | 0 |
| 23 | `-21.566` | `-96.1` | 0 |
| 26 | `-34.308` | `-38.5` | 0 |
| 27 | `-34.647` | `+20.9` | 0 |
| 30 | `-28.919` | `+76.5` | 1 |
| 35 | `+8.647` | `+193.6` | 1 |
| 39 | `+52.405` | `+246.8` | 1 |

Interpretation: P-Stack is not worse from the start. It is better than PFO
through roughly step 30, but the non-PFO deviations create a terminal/backlog
burden that becomes visible after step 27 and turns the cumulative TTT negative
after step 35.

### Same-State Leader Objective Clue

For the 10 steps where the PFO incumbent was not selected, the saved diagnostics
show that the leader sometimes accepted a candidate with worse rollout TTT than
PFO because the penalized leader objective was lower:

| step | selected rollout TTT | PFO rollout TTT | PFO minus selected rollout | objective gain | selected MFD penalty | PFO MFD penalty |
|---:|---:|---:|---:|---:|---:|---:|
| 15 | `254.613` | `253.852` | `-0.760` | `+4.492` | `1.681` | `1.075` |
| 23 | `389.722` | `388.784` | `-0.937` | `+3.300` | `12.773` | `12.770` |
| 24 | `413.255` | `412.361` | `-0.894` | `+3.400` | `15.866` | `18.901` |
| 27 | `479.807` | `479.794` | `-0.013` | `+6.371` | `34.449` | `40.374` |

Other non-PFO steps had lower rollout TTT, but they also tended to trade off
urban storage/terminal state. The key point is that the leader objective is not
a pure TTT argmin; storage/MFD/non-convergence terms can dominate small TTT
differences.

### State Trajectory Clue

Compared against standalone PFO, P-Stack's mid-horizon deviations initially
lower urban vehicles and TTT but alter queue placement:

- Around steps 23-26:
  - P-Stack has lower urban TTT and lower urban vehicles.
  - Ramp queue is higher than PFO by about `+54` to `+105 veh`.
  - On-ramp approach queue is lower by about `-110 veh`.
- By step 35:
  - Urban total vehicles are higher by `+178.9 veh`.
  - Urban accumulation is higher by `+148.3 veh`.
  - Terminal vehicles are higher by `+193.6`.
- By step 39:
  - Urban total vehicles are higher by `+302.7 veh`.
  - Urban accumulation is higher by `+268.4 veh`.
  - Terminal vehicles are higher by `+246.8`.

This is consistent with a delayed-state effect: the leader deviation improves
the short/mid-horizon objective but leaves a worse terminal state that later
appears as higher urban TTT and terminal burden.

### Guard Implementation Finding

The fallback guard is intended to compare more than objective values:

- `leader_fallback_guard_leader_completed_proxy_veh`
- `leader_fallback_guard_fallback_completed_proxy_veh`
- `leader_fallback_guard_leader_terminal_proxy_veh`
- `leader_fallback_guard_fallback_terminal_proxy_veh`

However, in the PFO-anchor P-Stack run these diagnostics are all zero for all
steps:

- leader completed proxy sum: `0`
- fallback completed proxy sum: `0`
- leader terminal proxy sum: `0`
- fallback terminal proxy sum: `0`
- completed worse flags: `0`
- terminal worse flags: `0`

Code inspection shows why:

- `StackelbergMPCController._evaluation_terminal_proxy()` reads
  `distributed_response_terminal_proxy_vehicles`.
- `StackelbergMPCController._evaluation_completed_proxy()` reads
  `distributed_response_completed_proxy_vehicles`.
- `WuFaithfulFollower.solve()` fills `distributed_response_rollout_ttt`,
  `distributed_response_rollout_freeway_ttt`, and
  `distributed_response_rollout_urban_ttt`, but it does not fill the terminal
  or completed proxy diagnostics.

Therefore, for the current wu-faithful PFO-anchor P-Stack path, the
throughput/terminal fallback guard is effectively disabled even though the
metadata fields exist.

### Diagnosis

The PFO-anchor mechanism itself is working:

- PFO incumbent active: `40/40`.
- PFO incumbent selected: `30/40`.
- Non-PFO selections: `10/40`.

The observed PFO gap comes from:

1. finite-horizon leader deviations that improve the 540 s objective but leave
   worse terminal/queue state;
2. leader objective terms such as MFD/storage/non-convergence penalties allowing
   small TTT losses or queue placement changes;
3. terminal/completed guard diagnostics being zero in the `WuFaithfulFollower`
   path, so the guard cannot reject candidates that reduce short-horizon TTT
   but worsen later terminal backlog.

### Recommended Fix

Do not remove the PFO anchor. Instead:

1. Extend `WuFaithfulFollower._rollout_horizon_ttt()` or add a sibling method
   that returns terminal vehicles and completed vehicles over the same
   full-coupled horizon.
2. Populate:
   - `distributed_response_terminal_proxy_vehicles`
   - `distributed_response_completed_proxy_vehicles`
   - optionally urban/freeway split proxies.
3. Make `_select_with_fallback_guard()` reject leader deviations when:
   - rollout TTT gain is below a meaningful margin, and
   - terminal vehicles or completed vehicles are worse than the PFO incumbent.
4. Re-run `sweet_155` 7200 s PFO/PFO-anchor P-Stack to verify that the leader
   either matches PFO or improves it without creating delayed terminal burden.

## 2026-07-01 - All-Boundary Half-Cap MFD Penalty Check

### Implementation

Changed the leader `all_urban_halfcap` penalty so movement-queue half-cap
excess is counted for every urban movement, including:

- `boundary_in`
- `boundary_out`
- `off_ramp`
- `on_ramp`
- internal movements

Previously the experimental half-cap path skipped `boundary_in` and
`boundary_out`. That made the storage/MFD pressure incomplete at the urban
network boundary.

Changed files:

- `src/controllers/leader.py`
- `src/tests/test_constraints.py`

### Validation

Commands:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\leader.py src\tests\test_constraints.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_constraints.ConstraintTests.test_leader_all_urban_halfcap_penalty_counts_boundary_and_storage
```

Result:

- `py_compile`: PASS
- targeted constraint test: PASS

The targeted test now explicitly checks boundary-in movement excess,
boundary-out movement excess, internal movement excess, and link-storage excess.

### Closed-Loop Run

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\sweet155_pstack_all_boundary_halfcap_7200_20260701 --stackelberg-leader-parallel-backend thread
```

Reference current PFO/no-control command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers NO-CONTROL,WU-CD-F,PROPOSED-FOLLOWERS-ONLY --T-total 7200 --output outputs\sweet155_current_wufaithful_7200_20260701 --stackelberg-leader-parallel-backend serial
```

### Results

| controller | total TTT | urban TTT | freeway TTT | completed veh | terminal veh | compute sec |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | `8611.785` | `5357.164` | `3254.621` | `23379.9` | `13428.9` | `0.00` |
| PROPOSED-FOLLOWERS-ONLY | `4490.018` | `3676.465` | `813.553` | `32519.3` | `4244.7` | `161.61` |
| P-Stack, previous half-cap | `4542.423` | `3720.532` | `821.891` | `32268.4` | `4491.6` | `825.49` |
| P-Stack, all-boundary half-cap | `4568.062` | `3772.098` | `795.964` | `32238.1` | `4527.8` | `841.34` |

Compared with standalone PFO, the all-boundary P-Stack run is worse by:

- total TTT: `+78.044 veh-h`
- completed vehicles: `-281.2 veh`
- terminal vehicles: `+283.1 veh`

Compared with the previous PFO-anchor P-Stack run, the all-boundary half-cap
run is also worse:

- total TTT: `+25.639 veh-h`
- urban TTT: `+51.566 veh-h`
- freeway TTT: `-25.927 veh-h`
- terminal vehicles: `+36.2 veh`

### Diagnostics

The all-boundary half-cap path did affect leader ranking:

| diagnostic | previous half-cap | all-boundary half-cap |
|---|---:|---:|
| PFO incumbent selected steps | `30/40` | `33/40` |
| non-PFO selected steps | `10/40` | `7/40` |
| avg MFD penalty | `19.407` | `59.743` |
| max MFD penalty | `73.164` | `233.779` |
| avg movement excess | `388.1` | `1194.9` |

However, the performance did not improve. Including boundary-in and
boundary-out movement queues in the half-cap penalty increases the penalty
signal and makes the leader stick closer to PFO more often, but it does not
remove the delayed terminal/urban burden.

### Diagnosis

Boundary coverage in the half-cap MFD penalty was incomplete and is now fixed,
but this was not the root cause of P-Stack being worse than PFO on `sweet_155`.
The stronger remaining implementation issue is still the missing
terminal/completed proxy in the `WuFaithfulFollower` response diagnostics:

- `distributed_response_terminal_proxy_vehicles` remains unavailable for the
  wu-faithful follower response path.
- `distributed_response_completed_proxy_vehicles` remains unavailable for the
  wu-faithful follower response path.
- Therefore the fallback guard cannot reject finite-horizon leader deviations
  that look good in short-horizon TTT but worsen later terminal burden.

Next recommended modification:

1. Add terminal and completed proxy outputs to the `WuFaithfulFollower`
   full-coupled horizon rollout.
2. Re-enable the leader fallback guard against the PFO incumbent using those
   proxies.
3. Re-run `sweet_155` PFO and PFO-anchor P-Stack for 7200 s.

## 2026-07-01 - Sweet 190 All-Boundary Half-Cap 7200 s Run

### Purpose

Run the current all-boundary half-cap leader objective on `sweet_190` to check
whether the P-Stack behavior that was poor on `sweet_155` persists at a higher
demand level.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_190 --controllers NO-CONTROL,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --T-total 7200 --output outputs\sweet190_all_boundary_halfcap_7200_20260701 --stackelberg-leader-parallel-backend thread
```

### Results

| controller | total TTT | urban TTT | freeway TTT | completed veh | terminal veh | computation sec | avg sec/step |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | `25170.572` | `15393.978` | `9776.594` | `15921.5` | `29139.1` | `0.00` | `0.00` |
| PROPOSED-FOLLOWERS-ONLY | `13590.622` | `12365.455` | `1225.166` | `29731.7` | `15300.0` | `164.62` | `4.116` |
| PROPOSED-STACKELBERG | `12984.869` | `11581.681` | `1403.187` | `30808.5` | `14194.3` | `827.07` | `20.677` |

### P-Stack vs PFO

P-Stack improved over PFO on this higher-demand case:

- total TTT improvement: `605.753 veh-h` (`5.28%` vs PFO)
- completed vehicles: `+1076.8 veh`
- network throughput: `+538.4 veh/h`
- terminal vehicles: `-1105.7 veh`
- urban TTT: `-783.774 veh-h`
- freeway TTT: `+178.021 veh-h`

This means the leader traded a modest freeway TTT increase for a larger urban
TTT and terminal-burden reduction. Unlike `sweet_155`, the higher-demand case
shows a positive network-level value for the leader layer.

### Computation Cost

| comparison | value |
|---|---:|
| PFO total compute | `164.62 s` |
| P-Stack total compute | `827.07 s` |
| P-Stack / PFO compute ratio | `5.02x` |
| PFO average step compute | `4.116 s` |
| P-Stack average step compute | `20.677 s` |
| P-Stack max step compute | `25.484 s` |
| control interval budget | `180 s` |
| PFO budget share | `2.29%` |
| P-Stack average budget share | `11.49%` |
| P-Stack max budget share | `14.16%` |

The current P-Stack implementation is substantially more expensive than PFO,
but it remains below the 180 s online control interval in this run.

### Leader Diagnostics

- PFO incumbent selected: `18/40` steps
- global hybrid anchor/search active: `4/40` steps
- P-Stack selected `N_P_star` average: `1579.25 veh`
- P-Stack selected `N_UF_star` average: `4733.99 veh/h`
- P-Stack `N_UF_star` range: `3300` to `6000 veh/h`

### Diagnosis

The `sweet_190` result suggests that P-Stack is not inherently broken; the
leader layer can improve total TTT, throughput, and terminal burden when the
demand level is high enough for coordination to have clear value. The remaining
issue is scenario-dependent ranking/fidelity:

- On `sweet_155`, finite-horizon leader deviations still worsen delayed
  terminal/urban burden.
- On `sweet_190`, the same leader machinery improves network-level outcomes.

Next diagnostic target remains the same: add terminal/completed proxy outputs
to the wu-faithful follower response so the leader can reject short-horizon
choices that create delayed terminal burden in moderate-demand cases.

## 2026-07-01 - Sweet 155 East Incident 7200 s Run

### Purpose

Run a `sweet_155` demand case with an eastbound downstream incident to see
whether the leader value appears when the moderate-demand case receives a
freeway bottleneck shock.

### Scenario

Temporary scenario file:

- `work/scenarios_sweet155_incident.yaml`

Scenario definition:

- name: `sweet_155_incident_east`
- urban/freeway/ramp scale: `1.55`
- incident: `FW_E`, segment `3`, `lane_loss=1.0`
- incident window: `2400 <= t < 4800 s`

This uses the same directional incident pattern as `medium_incident_east`, but
with `sweet_155` demand levels.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenarios-config work\scenarios_sweet155_incident.yaml --scenario sweet_155_incident_east --controllers NO-CONTROL,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --T-total 7200 --output outputs\sweet155_incident_all_boundary_halfcap_7200_20260701 --stackelberg-leader-parallel-backend thread
```

### Results

| controller | total TTT | urban TTT | freeway TTT | completed veh | terminal veh | computation sec | avg sec/step |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | `10207.386` | `6217.758` | `3989.627` | `21814.4` | `14994.3` | `0.00` | `0.00` |
| PROPOSED-FOLLOWERS-ONLY | `9191.270` | `6069.016` | `3122.253` | `24756.0` | `12040.2` | `164.89` | `4.122` |
| PROPOSED-STACKELBERG | `9133.371` | `6103.706` | `3029.665` | `24610.3` | `12186.3` | `813.40` | `20.335` |

### P-Stack vs PFO

P-Stack is slightly better than PFO in total TTT, but not in throughput or
terminal burden:

- total TTT improvement: `57.899 veh-h` (`0.78%` vs PFO)
- freeway TTT: `-92.588 veh-h`
- urban TTT: `+34.690 veh-h`
- completed vehicles: `-145.7 veh`
- network throughput: `-72.9 veh/h`
- terminal vehicles: `+146.1 veh`

The leader's improvement comes mainly from reducing freeway TTT during/after
the incident. It does not dominate PFO on terminal state or throughput.

### Computation Cost

| comparison | value |
|---|---:|
| PFO total compute | `164.89 s` |
| P-Stack total compute | `813.40 s` |
| P-Stack / PFO compute ratio | `4.93x` |
| PFO average step compute | `4.122 s` |
| P-Stack average step compute | `20.335 s` |
| P-Stack max step compute | `26.147 s` |
| control interval budget | `180 s` |
| PFO budget share | `2.29%` |
| P-Stack average budget share | `11.30%` |
| P-Stack max budget share | `14.53%` |

### Leader Diagnostics

- PFO incumbent selected: `35/40` steps
- global hybrid anchor/search active: `4/40` steps
- selected `N_P_star` average: `1247.49 veh`
- selected `N_P_star` range: `828.89` to `1661.21 veh`
- selected `N_UF_star` average: `5850 veh/h`
- selected `N_UF_star` range: `3750` to `6000 veh/h`

### Diagnosis

The incident changes the `sweet_155` conclusion:

- In no-incident `sweet_155`, all-boundary P-Stack was worse than PFO.
- With the eastbound incident, P-Stack becomes slightly better in total TTT.

However, the improvement is small and comes with worse completed/terminal
metrics. This is consistent with the previous diagnosis: the leader can reduce
short-horizon/freeway TTT, but without terminal/completed response proxies it
can still accept deviations that are not clearly better at the end-state level.

## 2026-07-01 - Sweet 155 Incident High-Accuracy P-Stack Search

### Purpose

Check whether the small P-Stack gain in `sweet_155_incident_east` was limited by
leader search accuracy. This run keeps the wu-faithful PFO incumbent/anchor
enabled, but increases continuous leader search budgets.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenarios-config work\scenarios_sweet155_incident.yaml --scenario sweet_155_incident_east --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\sweet155_incident_pstack_high_accuracy_7200_20260701 --stackelberg-leader-parallel-backend thread --leader-search-mode continuous --leader-continuous-max-evals 32 --leader-continuous-seed-count 15 --leader-continuous-prefilter-samples 121 --leader-continuous-prefilter-top-k 16 --leader-continuous-local-max-evals 16 --leader-continuous-local-seed-count 9 --leader-continuous-local-prefilter-samples 61 --leader-continuous-local-prefilter-top-k 12 --leader-continuous-local-iterations 8 --leader-continuous-initial-step-fraction 0.5 --leader-continuous-shrink-factor 0.5 --leader-continuous-min-np-step-veh 20 --leader-continuous-min-nuf-step-veh-h 50 --stackelberg-prefilter-top-k 16 --stackelberg-prefilter-local-top-k 12
```

### Results

| controller | total TTT | urban TTT | freeway TTT | completed veh | terminal veh | computation sec | avg sec/step |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | `10207.386` | `6217.758` | `3989.627` | `21814.4` | `14994.3` | `0.00` | `0.00` |
| PROPOSED-FOLLOWERS-ONLY | `9191.270` | `6069.016` | `3122.253` | `24756.0` | `12040.2` | `164.89` | `4.122` |
| P-Stack, default search | `9133.371` | `6103.706` | `3029.665` | `24610.3` | `12186.3` | `813.40` | `20.335` |
| P-Stack, high-accuracy search | `8970.486` | `5939.282` | `3031.204` | `24790.3` | `12004.0` | `3671.94` | `91.799` |

### Improvement

High-accuracy P-Stack improves over:

- no-control by `1236.900 veh-h` (`12.118%`)
- PFO by `220.784 veh-h` (`2.402%`)
- default-search P-Stack by `162.885 veh-h` (`1.783%`)

Compared with PFO, high-accuracy P-Stack also improves end-state metrics:

- completed vehicles: `+34.3 veh`
- terminal vehicles: `-36.2 veh`

This is a stronger result than the default-search P-Stack run, where P-Stack
reduced total TTT but had worse completed/terminal metrics than PFO.

### Computation Cost

| comparison | value |
|---|---:|
| high-accuracy P-Stack total compute | `3671.94 s` |
| high-accuracy P-Stack average step compute | `91.799 s` |
| high-accuracy P-Stack max step compute | `103.649 s` |
| control interval budget | `180 s` |
| average budget share | `50.999%` |
| max budget share | `57.583%` |
| high-accuracy / PFO compute ratio | `22.27x` |
| high-accuracy / default P-Stack compute ratio | `4.51x` |

The high-accuracy search remains below the 180 s control interval in this run,
but the margin is much smaller. This setting is suitable as a diagnostic or
offline/high-computation variant, not yet as the default online setting.

### Leader Diagnostics

- PFO incumbent selected: `22/40` steps
- global hybrid anchor/search active: `4/40` steps
- average full leader evaluations per step: `16.10`
- max full leader evaluations per step: `17`
- selected `N_P_star` average: `1236.58 veh`
- selected `N_P_star` range: `810.35` to `1582.83 veh`
- selected `N_UF_star` average: `5793.75 veh/h`
- selected `N_UF_star` range: `3750` to `6000 veh/h`

### Diagnosis

This run changes the search-accuracy conclusion for incident cases:

- The default PFO-anchor P-Stack was conservative and selected the PFO
  incumbent `35/40` steps.
- The high-accuracy run selected the PFO incumbent only `22/40` steps and found
  additional leader deviations that improved total TTT and end-state metrics.

Therefore, for `sweet_155_incident_east`, P-Stack performance was partly limited
by leader search accuracy. The remaining trade-off is computation cost. A likely
next step is to keep the high-accuracy option for global-refresh/incident-trigger
steps only, while using cheaper local search in normal periods.

## 2026-07-02 - Sweet 155 and Sweet 190 High-Accuracy P-Stack Search

### Purpose

Run the same high-accuracy wu-faithful P-Stack search used in the incident
diagnostic on the base `sweet_155` and `sweet_190` scenarios. The PFO incumbent
anchor remains enabled; only leader search accuracy is increased.

### Commands

`sweet_155`:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\sweet155_pstack_high_accuracy_7200_20260702 --stackelberg-leader-parallel-backend thread --leader-search-mode continuous --leader-continuous-max-evals 32 --leader-continuous-seed-count 15 --leader-continuous-prefilter-samples 121 --leader-continuous-prefilter-top-k 16 --leader-continuous-local-max-evals 16 --leader-continuous-local-seed-count 9 --leader-continuous-local-prefilter-samples 61 --leader-continuous-local-prefilter-top-k 12 --leader-continuous-local-iterations 8 --leader-continuous-initial-step-fraction 0.5 --leader-continuous-shrink-factor 0.5 --leader-continuous-min-np-step-veh 20 --leader-continuous-min-nuf-step-veh-h 50 --stackelberg-prefilter-top-k 16 --stackelberg-prefilter-local-top-k 12
```

`sweet_190`:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_190 --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\sweet190_pstack_high_accuracy_7200_20260702 --stackelberg-leader-parallel-backend thread --leader-search-mode continuous --leader-continuous-max-evals 32 --leader-continuous-seed-count 15 --leader-continuous-prefilter-samples 121 --leader-continuous-prefilter-top-k 16 --leader-continuous-local-max-evals 16 --leader-continuous-local-seed-count 9 --leader-continuous-local-prefilter-samples 61 --leader-continuous-local-prefilter-top-k 12 --leader-continuous-local-iterations 8 --leader-continuous-initial-step-fraction 0.5 --leader-continuous-shrink-factor 0.5 --leader-continuous-min-np-step-veh 20 --leader-continuous-min-nuf-step-veh-h 50 --stackelberg-prefilter-top-k 16 --stackelberg-prefilter-local-top-k 12
```

### Sweet 155 Results

| controller | total TTT | urban TTT | freeway TTT | completed veh | terminal veh | computation sec |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | `8611.785` | `5357.164` | `3254.621` | `23379.9` | `13428.9` | `0.00` |
| PROPOSED-FOLLOWERS-ONLY | `4490.018` | `3676.465` | `813.553` | `32519.3` | `4244.7` | `161.61` |
| P-Stack default search | `4568.062` | `3772.098` | `795.964` | `32238.1` | `4527.8` | `841.34` |
| P-Stack high-accuracy search | `4362.055` | `3577.778` | `784.277` | `32629.5` | `4134.7` | `4254.06` |

High-accuracy P-Stack improves over:

- no-control by `49.348%`
- PFO by `127.963 veh-h` (`2.850%`)
- default P-Stack by `206.007 veh-h` (`4.510%`)

Compared with PFO:

- completed vehicles: `+110.2 veh`
- terminal vehicles: `-110.0 veh`

### Sweet 190 Results

| controller | total TTT | urban TTT | freeway TTT | completed veh | terminal veh | computation sec |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | `25170.572` | `15393.978` | `9776.594` | `15921.5` | `29139.1` | `0.00` |
| PROPOSED-FOLLOWERS-ONLY | `13590.622` | `12365.455` | `1225.166` | `29731.7` | `15300.0` | `164.62` |
| P-Stack default search | `12984.869` | `11581.681` | `1403.187` | `30808.5` | `14194.3` | `827.07` |
| P-Stack high-accuracy search | `12931.636` | `11458.212` | `1473.424` | `30924.3` | `14099.5` | `4220.06` |

High-accuracy P-Stack improves over:

- no-control by `48.624%`
- PFO by `658.986 veh-h` (`4.849%`)
- default P-Stack by `53.233 veh-h` (`0.410%`)

Compared with PFO:

- completed vehicles: `+1192.6 veh`
- terminal vehicles: `-1200.5 veh`

### Computation Cost and Diagnostics

| scenario | total compute | avg step sec | max step sec | PFO selected | avg full evals | compute/PFO | compute/default P-Stack |
|---|---:|---:|---:|---:|---:|---:|---:|
| `sweet_155` | `4254.06 s` | `106.351` | `144.835` | `20/40` | `16.10` | `26.32x` | `5.06x` |
| `sweet_190` | `4220.06 s` | `105.501` | `128.112` | `10/40` | `16.10` | `25.64x` | `5.10x` |

Both high-accuracy runs stay below the 180 s control interval on average and at
the worst step, but the computation margin is much smaller than the default
P-Stack configuration.

### Diagnosis

The high-accuracy search changes the non-incident conclusions:

- In `sweet_155`, default P-Stack was worse than PFO, but high-accuracy P-Stack
  becomes better than PFO in total TTT, completed vehicles, and terminal
  vehicles.
- In `sweet_190`, default P-Stack was already better than PFO; high-accuracy
  search adds only a small extra TTT improvement, suggesting the default search
  was already close to a good solution for that high-demand case.

This supports a search-fidelity interpretation:

- Moderate or localized cases can require more accurate leader search to avoid
  being trapped near conservative PFO-anchor choices.
- Strong high-demand cases already give a clearer leader objective landscape,
  so default P-Stack captures most of the available improvement.

The open design question is how to activate high-accuracy search selectively,
for example at global refresh steps or when incident/density/storage stress is
high, without paying the full `~5x` P-Stack computation cost every control step.

## 2026-07-02 Legacy Pre-WuFaithful P-Stack Sweet 155/190 Comparison

### Purpose

The user asked whether the pre-WuFaithful P-Stack controller had better
performance in `sweet_155` and `sweet_190`, and requested a same-condition
comparison when existing outputs were insufficient.

Existing outputs were not sufficient for a same-condition 7200 s comparison:

- `outputs/classical_hierarchical_sweet190_3600_20260629` has a pre-WuFaithful
  P-Stack partial run only through `1080 s`.
- `outputs/sweet155_legacy_distributed_pfo_7200_20260701` is legacy PFO only
  and stops at `5940 s`; it is not a completed legacy P-Stack run.

### Temporary Runner

Added temporary work scripts only:

- `work/run_legacy_pstack_compare.py`
- `work/summarize_legacy_pstack_compare.py`

The runner instantiates `StackelbergMPCController` with
`DistributedCoordinator`, matching the pre-WuFaithful follower path, and writes
the same summary fields used by `six_controller_comparison.py`. A first
`sweet_190` attempt failed at step 10 with `MemoryError` because the legacy
controller copied very large diagnostics through `previous_control`; the
temporary runner was adjusted to clear only cached diagnostics between steps.
The control values are preserved.

### Commands

Smoke / compile:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile work\run_legacy_pstack_compare.py
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\run_legacy_pstack_compare.py --scenarios sweet_155 --T-total 180 --leader-backend thread --output outputs\legacy_pstack_smoke_180_thread_20260702
```

Full runs:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\run_legacy_pstack_compare.py --scenarios sweet_155 --T-total 7200 --leader-backend thread --output outputs\legacy_pstack_sweet155_7200_20260702
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\run_legacy_pstack_compare.py --scenarios sweet_190 --T-total 7200 --leader-backend thread --output outputs\legacy_pstack_sweet190_7200_20260702
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\summarize_legacy_pstack_compare.py
```

Comparison CSV:

- `outputs/legacy_pstack_sweet155_sweet190_7200_20260702/comparison_summary.csv`

### Results

| scenario | controller | total TTT | urban TTT | freeway TTT | completed veh | terminal veh | compute sec | improvement vs no-control |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sweet_155 | NO-CONTROL | `8611.785` | `5357.164` | `3254.621` | `23379.9` | `13428.9` | `0.00` | `0.00%` |
| sweet_155 | current PFO | `4490.018` | `3676.465` | `813.553` | `32519.3` | `4244.7` | `161.61` | `47.86%` |
| sweet_155 | current WuFaithful P-Stack | `4568.062` | `3772.098` | `795.964` | `32238.1` | `4527.8` | `841.34` | `46.96%` |
| sweet_155 | legacy pre-WuFaithful P-Stack | `4051.641` | `3318.737` | `732.904` | `33243.2` | `3551.2` | `3219.54` | `52.95%` |
| sweet_190 | NO-CONTROL | `25170.572` | `15393.978` | `9776.594` | `15921.5` | `29139.1` | `0.00` | `0.00%` |
| sweet_190 | current PFO | `13590.622` | `12365.455` | `1225.166` | `29731.7` | `15300.0` | `164.62` | `46.01%` |
| sweet_190 | current WuFaithful P-Stack | `12984.869` | `11581.681` | `1403.187` | `30808.5` | `14194.3` | `827.07` | `48.41%` |
| sweet_190 | legacy pre-WuFaithful P-Stack | `10728.763` | `9201.420` | `1527.343` | `33260.2` | `11685.0` | `3661.68` | `57.38%` |

### Direct Differences

Legacy pre-WuFaithful P-Stack compared with current PFO:

- `sweet_155`: `-438.377 veh-h` total TTT, `+723.9` completed vehicles,
  `-693.5` terminal vehicles.
- `sweet_190`: `-2861.859 veh-h` total TTT, `+3528.5` completed vehicles,
  `-3615.0` terminal vehicles.

Legacy pre-WuFaithful P-Stack compared with current WuFaithful P-Stack:

- `sweet_155`: `-516.421 veh-h` total TTT, `+1005.1` completed vehicles,
  `-976.6` terminal vehicles.
- `sweet_190`: `-2256.106 veh-h` total TTT, `+2451.7` completed vehicles,
  `-2509.3` terminal vehicles.

### Diagnosis

The pre-WuFaithful P-Stack path still finds substantially better TTT/throughput
solutions on these two sweet scenarios, but it is much more expensive:

- `sweet_155`: `3219.54 s`, about `19.92x` current PFO and `3.83x` current
  WuFaithful P-Stack.
- `sweet_190`: `3661.68 s`, about `22.24x` current PFO and `4.43x` current
  WuFaithful P-Stack.

This suggests the main regression from the WuFaithful simplification is not that
the leader is useless, but that the faster follower/search path has removed or
coarsened part of the action-response space that the legacy P-Stack was
exploiting. The next useful diagnostic is to compare legacy and WuFaithful
control trajectories on the same steps, especially green allocation, offset
changes, total RM release, on-ramp queues, and urban departures.

## 2026-07-02 WuFaithful P-Stack Anchor-Off Standalone Diagnosis

### Purpose

The user clarified that the final P-Stack controller should not depend on a PFO
anchor, fallback, or scenario-specific guide. A valid Stackelberg controller
must stand alone and reproduce the target behavior from its own leader-follower
optimization. Therefore, I reran current WuFaithful P-Stack with:

- PFO incumbent anchor disabled.
- PFO/no-control fallback disabled.
- PFO fallback cache disabled.
- Threaded leader backend retained.

### Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\sweet155_pstack_standalone_no_anchor_no_fallback_7200_20260702 --stackelberg-leader-parallel-backend thread --disable-stackelberg-pfo-incumbent --disable-stackelberg-fallback --disable-stackelberg-pfo-fallback-cache

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_190 --controllers PROPOSED-STACKELBERG --T-total 7200 --output outputs\sweet190_pstack_standalone_no_anchor_no_fallback_7200_20260702 --stackelberg-leader-parallel-backend thread --disable-stackelberg-pfo-incumbent --disable-stackelberg-fallback --disable-stackelberg-pfo-fallback-cache
```

### Results

| scenario | controller | total TTT | urban TTT | freeway TTT | completed veh | terminal veh | compute sec |
|---|---:|---:|---:|---:|---:|---:|---:|
| sweet_155 | NO-CONTROL | `8611.785` | `5357.164` | `3254.621` | `23379.9` | `13428.9` | `0.00` |
| sweet_155 | current PFO | `4490.018` | `3676.465` | `813.553` | `32519.3` | `4244.7` | `161.61` |
| sweet_155 | current P-Stack, anchor/fallback on | `4568.062` | `3772.098` | `795.964` | `32238.1` | `4527.8` | `841.34` |
| sweet_155 | current P-Stack, anchor/fallback off | `7765.857` | `6856.346` | `909.511` | `29826.1` | `6970.7` | `690.28` |
| sweet_155 | legacy pre-WuFaithful P-Stack | `4051.641` | `3318.737` | `732.904` | `33243.2` | `3551.2` | `3219.54` |
| sweet_190 | NO-CONTROL | `25170.572` | `15393.978` | `9776.594` | `15921.5` | `29139.1` | `0.00` |
| sweet_190 | current PFO | `13590.622` | `12365.455` | `1225.166` | `29731.7` | `15300.0` | `164.62` |
| sweet_190 | current P-Stack, anchor/fallback on | `12984.869` | `11581.681` | `1403.187` | `30808.5` | `14194.3` | `827.07` |
| sweet_190 | current P-Stack, anchor/fallback off | `14234.171` | `12747.286` | `1486.885` | `29412.0` | `15661.2` | `680.29` |
| sweet_190 | legacy pre-WuFaithful P-Stack | `10728.763` | `9201.420` | `1527.343` | `33260.2` | `11685.0` | `3661.68` |

### Key Diagnostics

Anchor-off P-Stack is not only worse than legacy; it is also worse than current
PFO in both sweet scenarios.

Leader target behavior:

- `sweet_155`: `N_P_star < 0` in `20/40` steps; min `-3315.0`.
- `sweet_190`: `N_P_star < 0` in `10/40` steps; min `-3315.0`.
- In the negative-target windows, WuFaithful follower cannot realize the raw
  target and projects it to the feasible edge. Example in `sweet_155`:
  `N_P_star=-3315.0` but projected feasible target is roughly `884-1279 veh`
  over the horizon.

This means the leader search and follower feasible response are not using the
same coordinate system. The leader can search and seed infeasible raw targets,
while the follower silently projects them before computing green allocations.

PFO vs anchor-off P-Stack service comparison:

- `sweet_155`:
  - PFO urban total departures: `58034.3 veh`.
  - Anchor-off P-Stack urban total departures: `48237.0 veh`.
  - PFO boundary-out sink: `15967.7 veh`.
  - Anchor-off P-Stack boundary-out sink: `13747.9 veh`.
  - PFO urban TTT: `3676.5 veh-h`.
  - Anchor-off P-Stack urban TTT: `6856.3 veh-h`.
- `sweet_190`:
  - PFO urban total departures: `41777.2 veh`.
  - Anchor-off P-Stack urban total departures: `40477.2 veh`.
  - PFO boundary-out sink: `13780.9 veh`.
  - Anchor-off P-Stack boundary-out sink: `12998.9 veh`.

So the failure mode is not a clean network-level tradeoff where P-Stack stores a
small queue to improve total throughput. In the standalone run, it reduces urban
discharge and leaves more vehicles inside the system.

### Diagnosis

The PFO anchor was masking a deeper issue. It injected a feasible, good
follower response into the leader candidate set. When the anchor is removed, the
current leader search often moves to raw `N_P_star` values outside the
WuFaithful follower's actual feasible net-inflow range. The follower then
projects those targets, but the leader search state, candidate ranking, and
next-step seed remain tied to the raw intent.

Increasing search budget alone is unlikely to fix this reliably: a larger
search may simply explore the wrong raw-target space more thoroughly.

The next correction should be generic, not a runtime guide:

1. Make leader candidate generation/evaluation use the follower-realizable
   net-inflow range for the current state and demand.
2. Record and rank candidates by projected/realized follower response, not raw
   infeasible `N_P_star` intent.
3. Update WuFaithful P-Stack output closure so `leader_realized_N_P_star`
   reflects `wu_faithful_sum_nin`/projected response rather than raw intent.
4. Re-run anchor-off sweet_155/sweet_190 and compare against PFO and legacy
   targets.

This keeps the controller standalone: no PFO anchor, no fallback guard, and no
scenario-specific guide.

## 2026-07-02 Follower-Realizable Leader Target Closure

### Purpose

Implemented the generic correction proposed above: without a PFO anchor or
fallback guide, Stackelberg leader candidates should be projected/evaluated in
the net-inflow range that the current WuFaithful follower can actually realize.

### Implementation

Changed files:

- `src/controllers/wu_faithful_follower.py`
  - Added `leader_np_feasible_range(...)`, returning the current follower
    feasible `Σnin` range in horizon vehicles.
  - Added vehicle-unit diagnostics for raw/projected/realized `N_P_star`:
    `wu_faithful_np_original_target_veh`,
    `wu_faithful_np_projected_target_veh`,
    `wu_faithful_np_realized_sum_nin_veh`,
    `wu_faithful_np_feasible_min_veh`, and
    `wu_faithful_np_feasible_max_veh`.
  - Added `wu_faithful_np_predictor_mode_code` and one-hot predictor mode
    diagnostics for later audit.
- `src/controllers/stackelberg_mpc.py`
  - Added leader candidate pre-projection through
    `_project_action_to_follower_feasible_np(...)`.
  - Added response closure through `_close_nash_response_leader_action(...)`,
    preserving raw intent while committing/logging projected/realized
    follower response.
  - Added candidate metadata for intent/projected/realized `N_P_star` and
    `N_UF_star`.
  - Updated previous-control normalization and output closure to keep realized
    targets rather than raw infeasible intent.

### Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\controllers\stackelberg_mpc.py src\controllers\stackelberg_wu_metered.py src\controllers\wu_faithful_follower.py

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest -v src.tests.test_constraints.ConstraintTests.test_wu_faithful_np_target_projects_to_signed_feasible_range src.tests.test_constraints.ConstraintTests.test_wu_faithful_np_predictor_modes_project_in_vehicle_units src.tests.test_constraints.ConstraintTests.test_stackelberg_leader_evaluates_coarse_and_refined_grid src.tests.test_constraints.ConstraintTests.test_stackelberg_leader_continuous_search_evaluates_targets src.tests.test_constraints.ConstraintTests.test_stackelberg_default_objective_uses_follower_response_with_future_penalty_states

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest -v src.tests.test_constraints.ConstraintTests.test_stackelberg_wu_pfo_incumbent_flag_can_disable_candidate src.tests.test_constraints.ConstraintTests.test_stackelberg_wu_pfo_incumbent_can_be_selected_when_leader_is_worse src.tests.test_constraints.ConstraintTests.test_stackelberg_fallback_guard_rejects_terminal_worse_leader

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --T-total 1800 --output outputs\sweet155_np_feasible_projection_anchor_off_1800_20260702 --stackelberg-leader-parallel-backend thread --disable-stackelberg-pfo-incumbent --disable-stackelberg-fallback --disable-stackelberg-pfo-fallback-cache

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.six_controller_comparison --scenario sweet_155 --controllers NO-CONTROL --T-total 1800 --output outputs\sweet155_np_feasible_projection_no_control_1800_20260702
```

### Targeted Test Results

- `py_compile`: PASS.
- WuFaithful N_P projection tests: PASS.
- Stackelberg grid/continuous leader target tests: PASS.
- Fallback/PFO-incumbent flag tests: PASS.
- Mutation safety tests run separately: PASS.

Whole-suite caveats:

- `pytest` is unavailable in the bundled runtime.
- `test_centralized_slsqp_solver_path_runs_and_logs` fails because SLSQP/Scipy
  is unavailable in this runtime (`centralized_slsqp_available=0`).
- `test_allocation_batch_objective_matches_scalar_objective` fails only by
  `1.36e-12` floating-point tolerance at `places=12`.
- Some `test_six_controller_comparison.py` expectations are stale for the
  current WuFaithful controller mapping, e.g. expecting PFO/P-Stack to use
  `DistributedCoordinator`.

### 1800 s Sweet-155 Anchor-Off Results

| controller | total TTT | urban TTT | freeway TTT | completed veh | terminal veh | compute sec |
|---|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | `518.411` | n/a in summary | n/a in summary | n/a | n/a | `~0` |
| PROPOSED-FOLLOWERS-ONLY | `529.441` | `398.404` | `131.037` | `7976.0` | `1382.4` | `50.07` |
| PROPOSED-STACKELBERG, anchor/fallback off | `610.620` | `492.829` | `117.791` | `7526.5` | `1803.0` | `181.01` |

P-Stack now no longer selects negative raw/committed `N_P_star` in this 1800 s
run:

- Committed `N_P_star`: min `1069.10`, mean `1156.70`, max `1217.21`.
- Leader intent `N_P_star`: min `1045.69`, mean `1135.78`, max `1200.19`.
- Projected `N_P_star`: min `1045.69`, mean `1131.97`, max `1172.95`.
- Projection was active in `1/10` decisions.
- Realization residual mean: `-20.92 veh`; no negative committed `N_P_star`.

However, the standalone P-Stack remains worse than PFO in this short run:

- Freeway TTT improves versus PFO: `131.037 -> 117.791 veh-h`.
- Urban TTT worsens: `398.404 -> 492.829 veh-h`.
- Completed vehicles decrease: `7976.0 -> 7526.5`.
- Terminal vehicles increase: `1382.4 -> 1803.0`.
- Urban total departures decrease over the 10 control intervals:
  `14942.0 -> 13522.7 veh`.
- Boundary-in load increases: mean `106.5 -> 177.5 veh`.
- Boundary-out load increases: mean `234.5 -> 385.4 veh`.

### Diagnosis

The previous severe failure mode, where anchor-off P-Stack searched infeasible
negative `N_P_star` targets and then silently relied on follower projection, is
substantially fixed. The new logs separate intent, projected target, and
realized follower response.

The remaining failure is different: the leader now picks feasible but still
over-aggressive high `N_P`/high `N_UF` combinations. This reduces freeway TTT
and ramp queues, but it shifts too much burden into urban queues and lowers
urban departures within the 1800 s horizon. Therefore the current problem is
not raw target feasibility; it is candidate evaluation/fidelity or objective
balance around urban discharge and terminal burden.

### Proposed Next Modification

Do not reintroduce PFO anchor or fallback as the main fix. Next inspect the
leader candidate evaluation table for low/medium `N_UF` and lower feasible
`N_P` candidates:

1. Verify whether the prefilter/top-K path is discarding lower-urban-burden
   candidates before full follower evaluation.
2. Add candidate-level realized urban departures, boundary-in/out loads, and
   terminal vehicles to the leader metadata.
3. Compare leader predicted rollout TTT/terminal state against realized
   closed-loop step TTT for selected and second-best candidates.
4. If the mismatch is confirmed, adjust leader evaluation to price terminal
   urban/boundary burden or use a longer/terminal-corrected rollout, not a PFO
   guide.

## 2026-07-02 GNE Shared-Multiplier P-Stack Experimental Copy

### Purpose

WuFaithful PFO-anchor P-Stack 계열을 production controller에 직접 반영하지 않고,
실험용 copy path에서 follower 쪽 `N_P_star` 처리만 generalized Nash equilibrium
shared-multiplier 방식으로 명시했다. 핵심 가설은 leader의 hard budget을 follower
agent별로 임의 배분하거나 hard matching시키는 구조가 urban response를 왜곡한다는
것이다.

### Implemented

- `work/gne_wu_faithful_experiment.py`
  - `GNEWuFaithfulFollower`: production `WuFaithfulFollower`를 상속하는 실험 variant.
  - Urban follower는 signal agent별 hard budget split 없이 shared `lambda_P`를 사용한다.
  - 각 signal agent는 기존 local objective에 `lambda_P * nin_i`를 더해 green을 선택한다.
  - `lambda_P`, target, realized `sum_nin`, residual, iterations, objective를 `gne_*`
    diagnostics로 승격했다.
  - `N_P`는 horizon vehicles, `N_UF`는 vehicles/hour 단위임을 diagnostics에 기록한다.
  - 선택 옵션으로 N_UF hard split을 shared-price candidate scoring으로 바꾸는
    `use_shared_lambda_uf` hook을 추가했다. 기본값은 off이며, 이번 smoke에서는 urban
    GNE 우선으로만 검증했다.
- `work/run_gne_pstack_experiment.py`
  - `PROPOSED-FOLLOWERS-ONLY`와 `GNE-PSTACK`을 같은 scenario, seed, plant, horizon에서
    비교하는 실험 runner.
  - `--disable-pfo-anchor`, `--disable-fallback`으로 PFO incumbent anchor/fallback을 끌 수
    있게 했다.
  - `decision_diagnostics.csv`와 `progress_summary.csv`에 `gne_lambda_P`,
    `gne_np_target_veh`, `gne_np_realized_sum_nin_veh`, `gne_np_residual_veh`를 기록한다.

### Files Changed

- `work/gne_wu_faithful_experiment.py`
- `work/run_gne_pstack_experiment.py`
- `reports/codex_run_report.md`

Production `src/controllers/*` 파일은 이번 작업에서 수정하지 않았다. 다만 작업 시작
시점에 `src/controllers/stackelberg_mpc.py`, `src/controllers/wu_faithful_follower.py`,
`reports/codex_run_report.md`는 이미 modified 상태였다.

### Commands

Compile:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile work\gne_wu_faithful_experiment.py work\run_gne_pstack_experiment.py
```

Smoke baseline/PFO and proposed GNE-PSTACK:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\run_gne_pstack_experiment.py --scenario sweet_155 --T-total 180 --controllers PROPOSED-FOLLOWERS-ONLY,GNE-PSTACK --output outputs\gne_pstack_sweet155_smoke_180_20260702 --leader-backend serial --disable-pfo-anchor --disable-fallback
```

Suggested 7200 s experiment:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\run_gne_pstack_experiment.py --scenario sweet_155 --T-total 7200 --controllers PROPOSED-FOLLOWERS-ONLY,GNE-PSTACK --output outputs\gne_pstack_sweet155_7200_20260702 --leader-backend thread --disable-pfo-anchor --disable-fallback
```

Optional N_UF shared-price diagnostic:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\run_gne_pstack_experiment.py --scenario sweet_155 --T-total 180 --controllers GNE-PSTACK --output outputs\gne_pstack_sweet155_nuf_price_smoke_180_20260702 --leader-backend serial --disable-pfo-anchor --disable-fallback --enable-nuf-shared-price
```

### Smoke Results

| controller | Total TTT | Urban TTT | Freeway TTT | completed veh | terminal veh | compute sec |
|---|---:|---:|---:|---:|---:|---:|
| PROPOSED-FOLLOWERS-ONLY | `24.263` | `15.792` | `8.471` | `448.2` | `624.2` | `4.785` |
| GNE-PSTACK | `24.262` | `15.792` | `8.471` | `439.7` | `632.7` | `44.254` |

GNE diagnostic sample, step 0:

- `gne_lambda_P = 0.1070556640625`
- `gne_np_target_veh = 1022.82`
- `gne_np_realized_sum_nin_veh = 1003.89`
- `gne_np_residual_veh = -18.93`
- feasible N_P range: `[841.1775, 1133.945] veh`
- `gne_objective = 102.48682645150029`

Optional N_UF shared-price smoke also executed for one interval:

- Total TTT: `24.245 veh-h`
- `gne_nuf_shared_lambda_active = 1.0`
- `gne_nuf_target_veh_h = 3600.0`
- `gne_nuf_realized_sum_metering_veh_h = 6000.0`
- `gne_nuf_residual_veh_h = 2400.0`
- `gne_lambda_UF = 0.0`
- `gne_lambda_P = 0.02996826171875`

This confirms the no-hard-split N_UF hook runs, but it is not yet a converged
N_UF dual update; it is intentionally kept off by default for the 7200 s urban
GNE comparison.

### Boundary Queue Balancing Result

The smoke was only one control interval, so it is not a valid acceptance run.
Boundary balance is recorded in `run_log.csv`/`progress_summary.csv`, but no
7200 s boundary non-degradation judgment was made in this pass.

### Control Validation Summary

- `py_compile`: PASS.
- Closed-loop smoke: PASS, output written under
  `outputs/gne_pstack_sweet155_smoke_180_20260702`.
- Ramp metering, VSL, green time, offsets, and N_P GNE diagnostics are logged.
- Full 7200 s acceptance, unit-test suite, and Claude review were not run in this
  pass.

### Failed Criteria / Next Modification

This is an experimental copy-path implementation, not a final controller
acceptance. The controller is not claimed complete because:

- Unit-test suite was not rerun.
- Closed-loop full 7200 s sweet_155 comparison was not run.
- Improvement >= 8% and boundary non-degradation were not evaluated.
- N_UF shared-price mode is only a diagnostic hook and remains off by default.

Next modification: run the suggested 7200 s `sweet_155` comparison with anchor
and fallback disabled, then inspect whether the shared `lambda_P` path improves
urban discharge/terminal burden relative to the prior anchor-off P-Stack.

## 2026-07-02 - Copy-Path GNE Follower Soft-Price 7200 s Check

### What Was Implemented

Follow-up correction to the copy-path GNE experiment:

- `GNEWuFaithfulFollower` now overrides the production
  `_bisect_lambda_for_np(...)` path.
- The production hard equality/feasibility matching of `N_P_star` is disabled in
  the copy path.
- `lambda_P` is used as a soft shared-constraint price update instead of a hard
  bisection target matcher.
- `GNEPStackController` snapshots and restores follower price state around each
  leader candidate evaluation so rejected candidates do not leak `lambda_P` or
  coupling state into later candidates.
- The selected closed-loop response still warm-starts the next step.

This remains an experimental work-path implementation, not the production
controller.

### Files Changed

- `work/gne_wu_faithful_experiment.py`
- `work/run_gne_pstack_experiment.py`
- `reports/codex_run_report.md`

### Commands

Compile:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile work\gne_wu_faithful_experiment.py work\run_gne_pstack_experiment.py
```

Smoke:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\run_gne_pstack_experiment.py --scenario sweet_155 --T-total 180 --controllers PROPOSED-FOLLOWERS-ONLY,GNE-PSTACK --output outputs\gne_pstack_sweet155_soft_gne_smoke_180_20260702 --leader-backend serial --disable-pfo-anchor --disable-fallback
```

7200 s comparison:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\run_gne_pstack_experiment.py --scenario sweet_155 --T-total 7200 --controllers PROPOSED-FOLLOWERS-ONLY,GNE-PSTACK --output outputs\gne_pstack_sweet155_soft_gne_7200_20260702 --leader-backend thread --disable-pfo-anchor --disable-fallback
```

### Smoke Result

The smoke confirmed that the copy-path GNE branch disables hard bisection:

- `gne_hard_bisection_disabled = 1.0`
- `gne_lambda_update_iterations = 5`
- `gne_lambda_P = 0.0950535`
- `gne_np_target_veh = 1022.82`
- `gne_np_realized_sum_nin_veh = 1070.015`
- `gne_np_residual_veh = 47.195`

180 s plant TTT was equal at this horizon:

| controller | Total TTT | Urban TTT | Freeway TTT | completed veh | compute sec |
|---|---:|---:|---:|---:|---:|
| PROPOSED-FOLLOWERS-ONLY | `24.263` | `15.792` | `8.471` | `448.2` | `4.412` |
| GNE-PSTACK | `24.263` | `15.792` | `8.471` | `448.2` | `37.017` |

### 7200 s Result

`sweet_155`, fallback disabled, PFO-anchor disabled:

| controller | Total TTT | Urban TTT | Freeway TTT | completed veh | terminal veh | compute sec | mean step sec |
|---|---:|---:|---:|---:|---:|---:|---:|
| PROPOSED-FOLLOWERS-ONLY | `4490.018` | `3676.465` | `813.553` | `32519.3` | `4244.7` | `184.621` | `4.616` |
| GNE-PSTACK | `6657.007` | `5757.725` | `899.283` | `30486.3` | `6260.4` | `711.887` | `17.797` |

Relative to PFO, the GNE P-Stack copy path worsened Total TTT by
`2166.989 veh-h` (`-48.262%` improvement vs PFO), reduced completed vehicles by
`2033.0`, and increased terminal vehicles by `2015.7`.

### Diagnostic Notes

- `leader_fallback_enabled = 0` for all steps.
- `leader_pfo_incumbent_enabled = 0` for all steps.
- `N_UF_star` averaged `5685.25 veh/h`, ranged from `5100` to `6000 veh/h`, and
  hit the `6000 veh/h` upper bound in `16/40` steps.
- Mean absolute GNE `N_P` residual was `36.204 veh`; max absolute residual was
  `124.314 veh`.
- `lambda_P` ranged from `-0.554` to `0.630`.

Interpretation: removing the hard follower feasibility/bisection layer is
consistent with a GNE formulation, but this simple soft-price follower is not yet
a valid replacement for the old response solver. The run indicates that the
remaining leader/follower coupling evaluation still favors high `N_UF_star`
release decisions and accumulates terminal burden. The failure is therefore not
just the hard `N_P` matcher; the GNE follower response needs a stronger
shared-constraint equilibrium update or an explicit realization-aware leader
evaluation before it can replace the current Wu-faithful response.

### Control Validation Summary

- `py_compile`: PASS.
- Closed-loop 180 s smoke: PASS.
- Closed-loop 7200 s comparison: completed.
- Acceptance: FAIL for the experimental GNE copy path because P-Stack is worse
  than PFO and does not meet the configured improvement criteria.

### Proposed Next Modification

Do not promote this copy-path GNE change to production. The next diagnostic
should compare:

1. Current hard-response Wu-faithful P-Stack.
2. Soft-price GNE P-Stack.
3. A proper GNE solver with iterative shared-constraint residual minimization,
   including `N_UF` allocation, not only `N_P`.

The specific question is whether the bad result comes from the simplified GNE
price update or from the leader objective still under-pricing high freeway
release/terminal burden.

## 2026-07-02 - Option A N_P Inequality Cap, sweet_190 P-Stack Faithful 7200 s

### What Was Implemented

Tested Claude's Option A interpretation for Wu-faithful P-Stack:

- `N_P_star` is treated as an upper-bound cap in the Wu-faithful follower:
  `sum_i nin_i <= N_P_star`.
- In cap mode, `lambda_P` is constrained to be non-negative.
- If `lambda_P = 0` already satisfies the cap, the follower returns with
  `lambda_P = 0` by complementarity.
- Stackelberg pre-projection no longer raises a cap target to the follower
  feasible lower bound in cap mode. It only clips the upper side.
- Added diagnostics:
  - `wu_faithful_np_coordination_cap`
  - `wu_faithful_np_coordination_equality`
  - `wu_faithful_np_cap_violation_veh`
  - `wu_faithful_np_cap_slack_veh`
  - `leader_np_follower_feasible_projection_cap_mode`

### Files Changed

- `src/models/state.py`
- `src/config/default.yaml`
- `src/controllers/wu_faithful_follower.py`
- `src/controllers/stackelberg_mpc.py`
- `reports/codex_run_report.md`

### Commands

Compile:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile src\models\state.py src\controllers\wu_faithful_follower.py src\controllers\stackelberg_mpc.py src\controllers\stackelberg_wu_metered.py work\run_claude_style_five_controller.py
```

Run:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\run_claude_style_five_controller.py --scenario sweet_190 --T-total 7200 --controllers P-STACK-WU-FAITHFUL --output outputs\sweet190_pstack_np_cap_7200_20260702
```

### Result

`sweet_190`, `P-STACK-WU-FAITHFUL`, 7200 s:

| case | Total TTT | Urban TTT | Freeway TTT | completed veh | terminal veh | compute sec |
|---|---:|---:|---:|---:|---:|---:|
| NEW N_P cap mode | `13246.094` | `11842.611` | `1403.483` | `30365.6` | `14666.1` | `1601.971` |
| OLD default P-Stack (`outputs/sweet190_all_boundary_halfcap_7200_20260701`) | `12984.869` | `11581.681` | `1403.187` | `30808.5` | `14194.3` | `827.070` |
| OLD high-accuracy P-Stack | `12931.636` | `11458.212` | `1473.424` | `30924.3` | `14099.5` | `4220.060` |
| OLD standalone no-anchor/no-fallback | `14234.171` | `12747.275` | `1486.896` | `29579.1` | `15454.0` | `511.350` |

Compared with the closest existing default P-Stack run, cap mode is worse by
`+261.225 veh-h` (`+2.012%` Total TTT), completes `442.9` fewer vehicles, and
leaves `471.8` more terminal vehicles.

### Diagnostics

- `lambda_P` stayed non-negative:
  - min `0.0`
  - max `10.0`
  - mean `0.2511`
- Fallback/PFO incumbent was active in the default runner:
  - selected fallback/PFO in `25/40` steps
  - non-fallback selected in `15/40` steps
- Cap violation diagnostics:
  - all steps: violation in `27/40`, mean `1137.4 veh`
  - non-fallback steps only: violation in `2/15`, mean `297.1 veh`, max
    `4454.7 veh`
- `N_UF_star` averaged `4329.375 veh/h` and hit the `6000 veh/h` upper bound in
  `6/40` steps.

### Interpretation

Option A fixed the negative-lambda pathology: the follower no longer uses
negative `lambda_P` to subsidize urban admission. However, in this `sweet_190`
7200 s P-Stack-faithful run it did not improve performance relative to the
stored default P-Stack result. The Total TTT degradation is mainly urban-side
(`+260.93 veh-h` urban TTT vs old default), while freeway TTT is almost
unchanged.

This suggests that negative `lambda_P` was not the dominant cause of the current
P-Stack degradation in this scenario. The remaining issue is more likely the
leader/follower response evaluation and the frequent fallback/PFO incumbent
selection, plus residual cap infeasibility when the selected cap is below what
the follower can realize.

### Status

`py_compile`: PASS.

Closed-loop run: completed.

Acceptance: FAIL for promotion. Keep this as a diagnostic result unless a
follow-up no-fallback/no-anchor apples-to-apples run shows a different trend.

## 2026-07-02 - PFO vs Legacy Selection Width and Multi-Start Jacobi Probe

### What Was Tested

Compared saved `sweet_190` 7200 s control traces:

- PFO:
  `outputs/sweet190_all_boundary_halfcap_7200_20260701/runs/sweet_190/PROPOSED-FOLLOWERS-ONLY`
- Legacy P-Stack:
  `outputs/legacy_pstack_sweet190_7200_20260702/runs/sweet_190/LEGACY-STACKELBERG`

Then ran a PFO multi-start diagnostic at selected high-difference steps
`0,10,20,21,26,35,39`:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\compare_pfo_legacy_multistart.py --scenario sweet_190 --steps 0,10,20,21,26,35,39 --random-starts 20 --output outputs\pfo_legacy_multistart_sweet190_20260702
```

### Files Changed

- `work/compare_pfo_legacy_multistart.py`
- `reports/codex_run_report.md`

### Trace Comparison Result

Saved full-run performance:

| controller | Total TTT | Urban TTT | Freeway TTT | completed veh | terminal veh |
|---|---:|---:|---:|---:|---:|
| PFO | `13590.622` | `12365.455` | `1225.166` | `29731.7` | `15300.0` |
| Legacy P-Stack | `10728.763` | `9201.420` | `1527.343` | `33260.2` | `11685.0` |

PFO has lower freeway TTT, but much worse urban TTT and terminal burden. Legacy
appears to spend more freeway delay to discharge the urban/ramp side.

Stepwise control-profile overlap:

- Ramp-metering profile equal in only `4/40` steps.
- Link VSL profile equal in only `7/40` steps.
- Green profile equal in `0/40` steps.
- Offset profile equal in `0/40` steps.

Mean selected controls:

| control | PFO mean | Legacy mean |
|---|---:|---:|
| `R_D_E` metering | `545.6` | `1417.2` |
| `R_D_W` metering | `637.5` | `1427.5` |
| `R_F_E` metering | `1500.0` | `1432.5` |
| `R_F_W` metering | `1500.0` | `1423.2` |
| `FW_E` VSL | `74.8` | `86.4` |
| `FW_W` VSL | `81.0` | `86.6` |

Legacy uses offsets in `40/40` steps with `27` unique offset profiles. PFO uses
zero offsets in every step.

### Multi-Start Result

For each selected state, PFO was solved from:

- runtime PFO previous control
- saved PFO previous control
- default uncontrolled control
- legacy previous control
- legacy current control as seed
- 20 random feasible green/VSL/offset seeds

The best one-step TTT improved only modestly relative to runtime PFO. More
importantly, no seed moved PFO close to the legacy ramp-release regime in the
congested middle/late steps:

| step | legacy ramp sum | PFO runtime ramp sum | multi-start ramp range | legacy action 1-step TTT | best PFO multi-start 1-step TTT |
|---:|---:|---:|---:|---:|---:|
| 20 | `6000.0` | `3900.0` | `3750.0-3900.0` | `313.392` | `313.674` |
| 21 | `6000.0` | `3900.0` | `3750.0-3900.0` | `334.737` | `335.111` |
| 26 | `6000.0` | `3900.0` | `3750.0-3900.0` | `456.287` | `456.043` |
| 35 | `5756.25` | `3750.0` | `3750.0-3750.0` | `674.783` | `676.461` |
| 39 | `6000.0` | `3750.0` | `3750.0-3750.0` | `758.013` | `759.808` |

Offsets stayed inactive in all PFO multi-start solutions.

### Interpretation

The PFO-vs-legacy gap is not explained by a simple Jacobi initial-condition trap.
Even when initialized from legacy previous/current controls, PFO does not remain
near the legacy choice. It falls back to a much lower ramp-release regime and
zero offsets. This suggests the main mismatch is in the PFO/Wu-faithful local
objective/feasible response itself, not just in the Jacobi starting point.

Legacy's advantage appears to come from a follower response space that allows
high ramp release plus coordinated green/offset movement, accepting somewhat
higher freeway TTT to greatly reduce urban TTT and terminal burden.

### Proposed Next Modification

Do not focus only on leader-grid width. The next probe should compare the legacy
and Wu-faithful follower scoring functions for the same candidate ramp-release
vectors, especially high-release vectors around `5750-6000 veh/h`. If
Wu-faithful scores those candidates poorly while one-step plant TTT and legacy
score them well, the fix belongs in the freeway/ramp follower local objective or
candidate generation, not in leader search.

## 2026-07-02 - Forced Leader Response Probe for Legacy Outcome Coverage

### Purpose

The goal was to split the "leader exists but does not move toward the legacy
solution" failure into three possibilities:

1. The leader search does not include the legacy-like `N_P_star`/`N_UF_star`
   region.
2. The leader objective evaluates the legacy region incorrectly.
3. The Wu-faithful follower response map does not contain the legacy outcome set,
   so even a correct leader target cannot induce the legacy high-release/signal
   pattern.

### Command

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\forced_leader_response_probe.py --scenario sweet_190 --steps 20,21,26,35,39 --np-mode cap --output outputs\forced_leader_response_probe_sweet190_20260702
```

### Files Changed

- `work/forced_leader_response_probe.py`
- `reports/codex_run_report.md`

### Data Sources

- PFO trace:
  `outputs/sweet190_all_boundary_halfcap_7200_20260701/runs/sweet_190/PROPOSED-FOLLOWERS-ONLY/control_timeseries.csv`
- Legacy P-Stack trace:
  `outputs/legacy_pstack_sweet190_7200_20260702/runs/sweet_190/LEGACY-STACKELBERG/control_timeseries.csv`

### Result Summary

For selected congested steps, the probe replayed either the saved PFO state or
the saved legacy state, then solved the Wu-faithful follower with forced leader
targets:

- `legacy_target`: the saved legacy `N_P_star` and `N_UF_star`
- `high_release_6000`: legacy `N_P_star` and `N_UF_star = 6000`
- `pfo_zero_target`: saved PFO targets

The forced high-release target is reachable by the follower in the ramp dimension:
when `N_UF_star = 6000`, the Wu-faithful response usually produced ramp sums near
`6000 veh/h`. Therefore, this is not primarily a leader search-width failure for
`N_UF_star`.

However, the response remains far from the legacy full control profile:

| target group | mean ramp distance | mean green p1 distance | mean offset distance | mean VSL-link distance | mean composite distance |
|---|---:|---:|---:|---:|---:|
| `legacy_target` | `48.8` | `153.5` | `384.0` | `27.0` | `5308.4` |
| `high_release_6000` | `48.8` | `153.5` | `384.0` | `27.0` | `5308.4` |
| `pfo_zero_target` | `2010.0` | `165.8` | `384.0` | `36.0` | `7606.8` |

Most importantly:

- Wu-faithful response offset active count: `0` in all `120/120` probe solves.
- Legacy offset active count: `5` in all probed legacy steps.
- Even when the ramp sum matches legacy (`5756-6000 veh/h`), the follower
  response typically keeps zero offsets and a different green allocation.
- On the same replayed states, exogenously evaluating the saved legacy action
  often gives lower horizon rollout TTT than the best Wu-faithful response.

Representative best-objective rows:

| state | step | target | response horizon TTT | legacy action horizon TTT | saved PFO horizon TTT | response ramp | legacy ramp | response offsets | legacy offsets |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| legacy replay | 20 | high release | `813.71` | `784.62` | `799.86` | `6000.0` | `6000.0` | `0` | `5` |
| legacy replay | 21 | high release | `853.24` | `830.16` | `846.70` | `6000.0` | `6000.0` | `0` | `5` |
| legacy replay | 26 | high release | `1114.90` | `1090.09` | `1105.05` | `6000.0` | `6000.0` | `0` | `5` |
| legacy replay | 35 | legacy target | `1598.18` | `1594.33` | `1609.97` | `5756.25` | `5756.25` | `0` | `5` |
| legacy replay | 39 | high release | `1799.10` | `1796.25` | `1811.38` | `6000.0` | `6000.0` | `0` | `5` |

### Interpretation

The strongest current diagnosis is hypothesis 3: the leader can request a
legacy-like high-release budget, but the Wu-faithful follower response map does
not contain the legacy full outcome set because signal timing and offset choices
collapse back to the local follower optimum. A global leader can only optimize
over the response returned by the follower; if the follower response never
returns the legacy high-release plus coordinated offset/green pattern, the leader
cannot select it even when that exogenous action scores better under rollout TTT.

This also explains why PFO anchoring does not guarantee improvement. The anchor
can move the leader into a reasonable `N_UF_star` region, but the follower's
realized response still differs in the urban signal/offset dimensions.

### Proposed Next Modification

The next modification should target the Wu-faithful follower response formation,
not only leader search:

- make urban offset/green candidates phase-resolved enough that nonzero offsets
  can win when they reduce local rollout TTT;
- add a forced-candidate diagnostic where the saved legacy green/offset profile
  is injected into the Wu-faithful follower candidate set to see whether the
  local objective rejects it or the candidate generator simply never proposes it;
- then rerun the same forced response probe to verify that the response map can
  reproduce the legacy high-release plus offset operating region without using a
  scenario-specific fallback guide.

## 2026-07-02 - Forced Legacy Green/Offset Candidate Injection Probe

### Purpose

The previous probe showed that the leader can force high `N_UF_star`, but the
Wu-faithful follower still does not return the legacy green/offset pattern. This
probe checks whether that is merely a candidate-generation failure or whether
the local follower objective itself rejects the legacy-like signal timing.

### Commands

Compilation:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile work\forced_legacy_candidate_probe.py
```

Initial all-step probe attempted:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\forced_legacy_candidate_probe.py --scenario sweet_190 --steps 20,21,26,35,39 --np-mode cap --output outputs\forced_legacy_candidate_probe_sweet190_20260702
```

This exceeded the 20 minute command limit because each row includes additional
offset candidate solves plus multiple horizon rollouts. The diagnosis was then
rerun on representative congested steps:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\forced_legacy_candidate_probe.py --scenario sweet_190 --steps 20 --np-mode cap --output outputs\forced_legacy_candidate_probe_sweet190_step20_20260702
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\forced_legacy_candidate_probe.py --scenario sweet_190 --steps 35 --np-mode cap --output outputs\forced_legacy_candidate_probe_sweet190_step35_20260702
```

### Files Changed

- `work/forced_legacy_candidate_probe.py`
- `reports/codex_run_report.md`

### Probe Design

For the same replayed PFO or legacy state, the script compares:

- normal Wu-faithful response;
- Wu-faithful response with the saved legacy `green_p1` values injected into
  each urban agent's local green candidate set;
- Wu-faithful response with saved legacy offsets injected into the offset
  candidate set;
- green+offset injection with and without the offset guard;
- ex-post full-plant rollout if the normal response is manually overwritten with
  legacy green, legacy offset, or both.

### Key Results

Representative step 20:

| replay state | target | normal response | response + legacy green | response + legacy offset | response + legacy green+offset | legacy full | saved PFO |
|---|---|---:|---:|---:|---:|---:|---:|
| PFO state | legacy/high-release | `993.756` | `989.622` | `993.071` | `988.785` | `988.788` | `998.494` |
| legacy state | legacy/high-release | `813.714` | `788.574` | `807.799` | `784.709` | `784.618` | `799.859` |

Representative step 35:

| replay state | target | normal response | response + legacy green | response + legacy offset | response + legacy green+offset | legacy full | saved PFO |
|---|---|---:|---:|---:|---:|---:|---:|
| PFO state | legacy target | `2080.007` | `2077.251` | `2076.275` | `2073.471` | `2073.719` | `2095.647` |
| PFO state | high-release | `2079.546` | `2076.765` | `2075.669` | `2072.972` | `2073.719` | `2095.647` |
| legacy state | legacy target | `1598.309` | `1596.559` | `1597.179` | `1593.477` | `1594.334` | `1609.971` |
| legacy state | high-release | `1599.257` | `1597.066` | `1599.073` | `1594.394` | `1594.334` | `1609.971` |

Additional observations:

- `WuFaithfulFollower.__init__` currently sets `offset_enabled = False`, so
  ordinary Wu-faithful response never searches offset at all.
- When offset search is enabled for the probe, the local offset search finds
  only partial nonzero offsets (`1-3` signals), and the guard often zeroes them.
- Injecting legacy green values into the local candidate set does not make the
  solver choose them. For example, step 20 legacy-replayed state keeps response
  `green_p1_sum = 316` while legacy has `274`, even though ex-post overwriting
  the response with legacy green reduces horizon TTT from `813.714` to
  `788.574`.
- The same pattern appears in step 35: the normal response remains away from the
  legacy green/offset profile even though ex-post legacy green+offset lowers the
  full-plant rollout TTT to roughly the legacy action.

### Interpretation

This is not just a missing-candidate problem. The diagnostic injected the legacy
green candidate, but the Wu-faithful local follower still selected a different
green profile. Ex-post full-plant rollout shows that the legacy green/offset
profile improves network TTT, but the distributed local objective does not select
it.

Therefore the current failure is more specifically:

1. offset is disabled by design in the current Wu-faithful follower path;
2. even when offset is re-enabled diagnostically, only partial local offsets are
   selected and the guard removes them;
3. legacy green values can be made available as candidates, but the local
   follower objective/budget decomposition rejects them.

The root mismatch is the follower response formation: the leader target is an
aggregate budget, while each urban follower minimizes a local signal TTS proxy
with frozen coupling. A corridor/global green+offset pattern can reduce
full-plant TTT but still be invisible or unattractive to each local signal
player.

### Proposed Next Modification

The next productive fix is not simply widening leader search. It should modify
how the Wu-faithful urban follower evaluates signal timing under a leader target:

- evaluate green and offset jointly, not as green-first then optional local
  offset;
- make the local signal objective include a corridor-response term or a
  phase-resolved downstream queue/throughput benefit so the legacy-style green
  profile becomes locally visible;
- remove the unconditional `offset_enabled = False` only after the above
  objective is fixed, otherwise selfish offset search can reintroduce noisy
  partial offsets without reproducing the useful corridor profile.

## 2026-07-02 - Neighbor-Rollout Wu-Faithful Diagnostic Copy

### Purpose

The previous forced-candidate probe showed that the legacy green/offset profile
can reduce full-plant rollout TTT, but the Wu-faithful local follower does not
select it even when the legacy values are injected into the candidate set.

This run creates a diagnostic copy that changes only the urban signal scoring
scope:

- baseline score: each signal evaluates its own local movement/ramp-aware TTS;
- neighbor score: each signal evaluates ego + topology neighbors;
- corridor score: each signal evaluates the full signal corridor with the same
  local plant scorer.

This is not a production controller change. It is a copy-based probe to test
whether the failure is merely that each signal cannot see nearby downstream
effects.

### Files Changed

- `work/neighbor_rollout_candidate_probe.py`
- `reports/codex_run_report.md`

The implementation was drafted by a coding subagent and reviewed by a separate
review subagent. After review, the neighbor map was patched to include
freeway-interface adjacency through on-ramp/off-ramp links as well as direct
urban movement adjacency.

### Commands

```bash
python -B work/neighbor_rollout_candidate_probe.py \
  --scenario sweet_190 \
  --steps 20,35 \
  --np-mode cap \
  --score-scope ego_neighbor \
  --output outputs/neighbor_rollout_candidate_probe_sweet190_cap_ego_neighbor_20260702

python -B work/neighbor_rollout_candidate_probe.py \
  --scenario sweet_190 \
  --steps 20,35 \
  --np-mode cap \
  --score-scope corridor \
  --output outputs/neighbor_rollout_candidate_probe_sweet190_cap_corridor_20260702

python -B -m py_compile work/neighbor_rollout_candidate_probe.py
```

### Output Files

- `outputs/neighbor_rollout_candidate_probe_sweet190_cap_ego_neighbor_20260702/neighbor_rollout_summary_cap_ego_neighbor.csv`
- `outputs/neighbor_rollout_candidate_probe_sweet190_cap_ego_neighbor_20260702/neighbor_rollout_choice_details_cap_ego_neighbor.csv`
- `outputs/neighbor_rollout_candidate_probe_sweet190_cap_corridor_20260702/neighbor_rollout_summary_cap_corridor.csv`
- `outputs/neighbor_rollout_candidate_probe_sweet190_cap_corridor_20260702/neighbor_rollout_choice_details_cap_corridor.csv`

### Key Results

Default-seed results:

| step | replay state | local response | ego+neighbor response | corridor response | response overwritten by legacy green+offset | legacy full | saved PFO |
|---:|---|---:|---:|---:|---:|---:|---:|
| 20 | PFO state | `994.611` | `996.200` | `996.200` | `988.785` | `988.788` | `998.494` |
| 20 | legacy state | `814.343` | `814.478` | `814.478` | `784.618` | `784.618` | `799.859` |
| 35 | PFO state | `2080.493` | `2075.956` | `2075.956` | `2073.453` | `2073.719` | `2095.647` |
| 35 | legacy state | `1597.292` | `1598.450` | `1598.450` | `1593.477` | `1594.334` | `1609.971` |

Legacy choice counts:

- Default seed: `green_legacy_chosen_count = 0/5` and
  `offset_legacy_chosen_count = 0/5` for all tested local, ego-neighbor, and
  corridor cases.
- Legacy-current seed occasionally selects one legacy green value, but still
  never selects the full legacy green/offset profile and never matches legacy
  offsets.

Computation:

- Local scoring took roughly `5.6-7.4 s` per probe solve.
- Ego-neighbor scoring took roughly `10.5-23.9 s` per probe solve.
- Corridor scoring took roughly `15.9-37.3 s` per probe solve.

### Interpretation

The neighbor/corridor copy does not recover the legacy high-release
green/offset behavior. In step 35, ego-neighbor scoring modestly improves the
response (`2080.493 -> 2075.956` on the PFO-replayed state), but it still does
not choose the legacy green/offset bundle, while an ex-post overwrite with the
legacy green+offset values reaches `2073.453`.

Therefore the current evidence says the problem is not only insufficient
one-hop visibility. Even when the local scorer is widened to a corridor sum, the
Wu-faithful response formation still misranks the full-plant-beneficial
green/offset profile.

The review subagent recommended an even stronger oracle probe: evaluate limited
green/offset overrides through the full `run_coupled_interval` plant rollout
instead of summing local signal scorers. That would be the next diagnostic if we
need to distinguish "summed local plant is still wrong" from "only a fully
joint signal search can find the useful profile."

### Proposed Next Modification

Do not merge the neighbor scorer into production as-is. It increases online
cost and does not recover the target behavior.

The next implementation path should be one of:

1. build a full-plant limited-override oracle probe for the same steps and
   states;
2. replace per-signal green/offset Nash response with a small joint
   corridor-signal bundle search under the leader budget;
3. keep Wu-faithful local scoring for fast ramp/VSL response, but move
   green/offset coordination to a corridor-level follower/player where offset
   progression benefits are visible.

## 2026-07-02 - Candidate-Dependent 1-Hop Neighbor Rollout Probe

### Purpose

The previous neighbor-rollout copy widened the score from ego-only to
ego+neighbor/corridor, but it still used local signal scorers. This pass tests
the user's more specific hypothesis:

> A neighbor TTT scalar is not enough; for each ego candidate, neighbor queues
> and TTT must be recomputed under that ego candidate while neighbor controls
> stay frozen.

This is still a copy-based diagnostic and does not modify production `src/`
controller code.

### Files Changed

- `work/candidate_dependent_neighbor_rollout_probe.py`
- `reports/codex_run_report.md`

The new script imports the existing forced-response/neighbor-probe helpers, then
subclasses the diagnostic Wu-faithful follower. For each ego green or offset
candidate it:

1. freezes all non-ego controls in the candidate snapshot;
2. rolls a copied urban plant with `urban_substep(...)`;
3. scores vehicle TTS in the ego + 1-hop neighbor signal scope;
4. keeps neighbor controls frozen but lets neighbor queues/storage/ramp queues
   evolve under the ego candidate.

This makes the neighbor TTT term candidate-dependent instead of adding a frozen
constant.

### Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile work\candidate_dependent_neighbor_rollout_probe.py

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\candidate_dependent_neighbor_rollout_probe.py --help

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\candidate_dependent_neighbor_rollout_probe.py --scenario sweet_190 --steps 20,35 --np-mode cap --score-scope ego_neighbor --output outputs\candidate_dependent_neighbor_rollout_probe_sweet190_cap_ego_neighbor_20260702
```

### Output Files

- `outputs/candidate_dependent_neighbor_rollout_probe_sweet190_cap_ego_neighbor_20260702/candidate_dependent_neighbor_summary_cap_ego_neighbor.csv`
- `outputs/candidate_dependent_neighbor_rollout_probe_sweet190_cap_ego_neighbor_20260702/candidate_dependent_neighbor_choice_details_cap_ego_neighbor.csv`
- `outputs/candidate_dependent_neighbor_rollout_probe_sweet190_cap_ego_neighbor_20260702/candidate_dependent_neighbor_summary_cap_ego_neighbor.json`

### Verification

- `py_compile`: PASS.
- `--help`: PASS.
- Copy-path probe completed for `sweet_190`, steps `20,35`, `np-mode=cap`.

### Key Results

Legacy-current seed summary:

| step | replay state | local response TTT | candidate-dependent 1-hop response TTT | response overwritten by legacy green+offset | legacy full | saved PFO | local legacy choices | 1-hop legacy choices |
|---:|---|---:|---:|---:|---:|---:|---|---|
| 20 | PFO state | `994.611` | `996.235` | `988.785` | `988.788` | `998.494` | green `0/5`, offset `0/5` | green `0/5`, offset `0/5` |
| 20 | legacy state | `813.908` | `812.436` | `784.618` | `784.618` | `799.859` | green `0/5`, offset `0/5` | green `0/5`, offset `0/5` |
| 35 | PFO state | `2080.142` | `2074.514` | `2073.453` | `2073.719` | `2095.647` | green `0/5`, offset `0/5` | green `3/5`, offset `0/5` |
| 35 | legacy state | `1597.590` | `1597.593` | `1594.162` | `1594.334` | `1609.971` | green `0/5`, offset `0/5` | green `3/5`, offset `2/5` |

Default-seed summary:

| step | replay state | local response TTT | candidate-dependent 1-hop response TTT | local legacy choices | 1-hop legacy choices |
|---:|---|---:|---:|---|---|
| 20 | PFO state | `994.611` | `996.235` | green `0/5`, offset `0/5` | green `0/5`, offset `0/5` |
| 20 | legacy state | `814.343` | `812.436` | green `0/5`, offset `0/5` | green `0/5`, offset `0/5` |
| 35 | PFO state | `2080.493` | `2075.841` | green `0/5`, offset `0/5` | green `1/5`, offset `1/5` |
| 35 | legacy state | `1597.292` | `1597.698` | green `0/5`, offset `0/5` | green `0/5`, offset `1/5` |

Computation cost was much larger than the local scorer:

- local probe solves: roughly `5.8-7.6 s`;
- candidate-dependent 1-hop solves: roughly `178-226 s`.

### Interpretation

The candidate-dependent 1-hop rollout is directionally informative but not yet
production-ready:

- It can move choices toward the legacy profile in some congested cases.
  Example: step 35 PFO-replayed state with legacy seed improves from
  `2080.142` to `2074.514` and selects `3/5` legacy green values.
- It still does not recover the full legacy green/offset bundle. The same row
  remains above the ex-post legacy green+offset overwrite (`2073.453`) and the
  offset match remains `0/5`.
- Step 20 PFO-replayed state gets worse (`994.611 -> 996.235`), despite moving
  the green/offset aggregate closer to legacy.
- The solve time is too high for online use in its direct form.

This supports a narrower diagnosis than before: making neighbor TTT
candidate-dependent helps at the right time/region, so the idea is not wrong.
But a naive per-candidate urban plant rollout is too expensive and still not
enough to reliably find the useful full green/offset profile.

### Proposed Next Modification

Do not merge this diagnostic scorer directly into production.

The next ablation should be cheaper and more selective:

1. Keep the fast local scorer as a first-stage candidate generator.
2. Use candidate-dependent 1-hop rollout only as a top-K re-ranker for green and
   offset candidates.
3. If top-K re-ranking still fails to recover the legacy-like bundle, do not
   jump directly to a joint corridor bundle search. The user flagged that joint
   offset search creates a main-stream/reference ambiguity and can undermine
   the distributed game structure. Prefer anchored sequential offset diagnosis
   first.

This keeps the sequential diagnosis clean: neighbor candidate-dependence helps
partly, but direct use is not sufficient because it is both incomplete and too
slow.

## 2026-07-02 - Anchored Sequential Offset Probe

### Purpose

The user clarified that the desired next test is not joint corridor search.
Instead, keep the Nash/sequential follower structure and fix one intersection's
offset to zero as the phase reference. The remaining intersections then run the
ordinary sequential offset best response.

This copy-based diagnostic tests whether that gauge fixing can recover useful
offset coordination without increasing computation cost:

- no joint corridor bundle search;
- no production `src/` edits;
- one anchor signal fixed to offset `0`;
- other eligible signals use the existing `_solve_offset_local`;
- green, ramp metering, and VSL are unchanged.

### Files Changed

- `work/anchored_sequential_offset_probe.py`
- `reports/codex_run_report.md`

### Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile work\anchored_sequential_offset_probe.py

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\anchored_sequential_offset_probe.py --help

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\anchored_sequential_offset_probe.py --scenario sweet_190 --steps 20,35 --np-mode cap --state-sources pfo_replayed_state --modes offset_off,offset_free,offset_anchor --anchors A --seed default_uncontrolled --output outputs\anchored_sequential_offset_probe_sweet190_cap_anchorA_20260702

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\anchored_sequential_offset_probe.py --scenario sweet_190 --steps 20,35 --np-mode cap --state-sources pfo_replayed_state --modes offset_anchor --anchors B,C --seed default_uncontrolled --output outputs\anchored_sequential_offset_probe_sweet190_cap_anchorBC_20260702
```

### Key Results

| step | mode | anchor | response TTT | offset active | solve time |
|---:|---|---|---:|---:|---:|
| 20 | offset off | - | `993.756` | `0` | `5.38 s` |
| 20 | offset free | - | `994.611` | `1` | `5.75 s` |
| 20 | offset anchored | A | `993.756` | `0` | `5.36 s` |
| 20 | offset anchored | B | `994.611` | `1` | `5.66 s` |
| 20 | offset anchored | C | `994.611` | `1` | `5.71 s` |
| 35 | offset off | - | `2080.299` | `0` | `6.82 s` |
| 35 | offset free | - | `2080.493` | `1` | `7.14 s` |
| 35 | offset anchored | A | `2080.493` | `1` | `7.19 s` |
| 35 | offset anchored | B | `2080.299` | `0` | `6.83 s` |
| 35 | offset anchored | C | `2080.493` | `1` | `7.18 s` |

Reference full-rollout TTT:

- step 20 legacy action: `988.788`;
- step 35 legacy action: `2073.719`;
- step 20 saved PFO action: `998.494`;
- step 35 saved PFO action: `2095.647`.

### Interpretation

Anchored sequential offset keeps computation cost near the ordinary
Wu-faithful solve time (`~5.4-7.2 s`) and avoids the exponential joint-search
problem. However, it does not improve TTT in these sampled states.

The free-offset diagnostic activates only one local offset:

- step 20: signal `A` chooses `30 s`;
- step 35: signal `B` chooses `45 s`;
- signals `D` and `F` are ramp-interface local models (`model_has_ramps=True`)
  and the current Wu-faithful offset path returns `0` for them.

Anchoring the active signal simply turns that offset off and recovers the
offset-off TTT. Anchoring other signals leaves the same single offset active and
keeps the worse offset-free TTT. Therefore the missing legacy-like behavior is
not just absolute offset reference drift.

### Decision

Do not merge anchored sequential offset as a standalone production fix. It is a
valid gauge-fixing diagnostic, but it does not recover the useful multi-signal
offset/progression pattern.

The next non-joint direction should preserve sequential best response while
changing what each offset player can see:

1. keep one offset anchor as a harmless phase reference;
2. keep offset search sequential, not joint;
3. score each offset candidate with candidate-dependent downstream
   arrival/TTT for the next one-hop signal;
4. apply that only as a top-K re-ranker so the solve does not become the
   `178-226 s` direct candidate-dependent probe.

## 2026-07-06 - Wu-Faithful Joint Control and Metering-to-Urban Coupling

### Purpose

Ported the missing neighbor-coupling information into the Wu-faithful proposed
follower path and changed the proposed follower candidate evaluation so coupled
controls are selected jointly:

- freeway follower: evaluate ramp metering and VSL as joint `(RM, VSL)`
  candidates instead of independent updates;
- urban follower: evaluate green time and offset as joint `(green, offset)`
  candidates instead of separate green and offset stages;
- metering-to-urban coupling: after the freeway follower selects ramp metering,
  recompute ramp reservoir drain/space and run one additional urban follower
  sweep so the urban-side signal player sees the effect of metering before the
  plant transition.

These features are opt-in and authority-gated. They are enabled only for the
proposed controllers; `WU-CD-F` remains green/VSL-only and does not receive the
new RM/offset authority.

### Files Changed

- `src/models/state.py`
  - added `MPCConfig` flags:
    - `wu_faithful_joint_freeway_rm_vsl`
    - `wu_faithful_joint_urban_green_offset`
    - `wu_faithful_metering_to_urban_ramp_space`
    - `wu_faithful_joint_metering_split_count`
- `src/config/default.yaml`
  - added disabled-by-default config entries for the new flags.
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `src/experiments/six_controller_comparison.py`
  - added CLI switches for the new Wu-faithful joint/coupling modes.
- `src/controllers/wu_faithful_follower.py`
  - added joint freeway `(RM, VSL)` candidate search;
  - added joint urban `(green, offset)` candidate search;
  - added post-metering urban re-sweep using selected RM-dependent ramp drain;
  - added diagnostics for joint/coupling activity and post-metering eval counts.
- `src/tests/test_wu_faithful_follower.py`
  - added targeted tests for joint freeway search, post-metering urban coupling,
    and joint green/offset selection.

### Verification

Source compile was used because the sandbox denied `__pycache__` writes for
normal `py_compile`.

```powershell
python -B -c "from pathlib import Path; files=[...]; [compile(Path(f).read_text(encoding='utf-8'), f, 'exec') for f in files]; print('source compile ok')"
```

Result: `source compile ok`.

Targeted tests:

```powershell
python -B -m unittest `
  src.tests.test_wu_faithful_follower.TestJointWuFaithfulControls `
  src.tests.test_wu_faithful_follower.TestLocalRampReleaseOrdering `
  src.tests.test_constraints.ConstraintTests.test_wu_faithful_freeway_release_uses_start_reservoir_before_current_arrivals
```

Result: `5 tests OK`.

### Smoke Run

```powershell
python -B -m src.experiments.all_scenarios_four_controller_comparison `
  --scenario sweet_155 `
  --T-total 360 `
  --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG `
  --output C:\tmp\joint_wu_faithful_sweet155_360_smoke_20260706 `
  --wu-faithful-joint-freeway-rm-vsl `
  --wu-faithful-joint-urban-green-offset `
  --wu-faithful-metering-to-urban-ramp-space
```

| controller | total TTT (veh-h) | improvement vs no-control |
|---|---:|---:|
| NO-CONTROL | `63.950` | - |
| WU-CD-F | `64.052` | `-0.159%` |
| PROPOSED-FOLLOWERS-ONLY | `63.251` | `1.093%` |
| PROPOSED-STACKELBERG | `63.231` | `1.124%` |

Diagnostics confirmed that the joint/coupling flags were active for PFO and
P-Stack and inactive for WU-CD-F.

### Full Sweet Run

Interpreted "sweet" as `sweet_155`; there is no generic `sweet` scenario in the
current scenario registry.

```powershell
python -B -m src.experiments.all_scenarios_four_controller_comparison `
  --scenario sweet_155 `
  --T-total 7200 `
  --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG `
  --output C:\tmp\joint_wu_faithful_sweet155_7200_20260706 `
  --wu-faithful-joint-freeway-rm-vsl `
  --wu-faithful-joint-urban-green-offset `
  --wu-faithful-metering-to-urban-ramp-space
```

Output directory:

- `C:\tmp\joint_wu_faithful_sweet155_7200_20260706`

| controller | total TTT | freeway TTT | urban TTT | delay | improvement | completed gain | terminal avoided | wall time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | `8611.785` | `3254.621` | `5357.164` | `6886.102` | - | - | - | `2.403 s` |
| WU-CD-F | `8713.757` | `3275.752` | `5438.005` | `6988.074` | `-1.184%` | `+96.1` | `+99.2` | `115.909 s` |
| PROPOSED-FOLLOWERS-ONLY | `4394.806` | `836.284` | `3558.522` | `2669.123` | `48.968%` | `+9574.3` | `+9567.5` | `804.383 s` |
| PROPOSED-STACKELBERG | `4292.099` | `748.195` | `3543.904` | `2566.415` | `50.160%` | `+9559.4` | `+9550.5` | `1240.569 s` |

P-Stack improved over PFO by `102.707 veh-h` on total TTT in this run.

### Computation Cost

| controller | mean step wall time | max step wall time |
|---|---:|---:|
| WU-CD-F | `2.888 s` | `4.206 s` |
| PROPOSED-FOLLOWERS-ONLY | `20.102 s` | `26.026 s` |
| PROPOSED-STACKELBERG | `30.999 s` | `48.542 s` |

All controllers remained below the `180 s` control interval in this run, but the
joint proposed controllers are much heavier than WU-CD-F.

### Control Validation Summary

- `WU-CD-F`: joint RM/VSL and joint green/offset flags remain inactive by
  authority gate, as intended.
- `PROPOSED-FOLLOWERS-ONLY`: joint RM/VSL, joint green/offset, and
  metering-to-urban coupling are active.
- `PROPOSED-STACKELBERG`: same proposed joint/coupling features are active,
  with lower TTT than PFO on `sweet_155`.
- Average total RM:
  - PFO: `5801.2 veh/h`;
  - P-Stack: `5828.9 veh/h`.
- Average mean offset:
  - PFO: `55.4 s`;
  - P-Stack: `52.1 s`.
- Average post-metering urban re-sweep evals:
  - PFO: `758.2`;
  - P-Stack: `195.8`.

### Boundary Queue Balancing

Boundary balance non-degradation still fails against no-control:

- PFO mean boundary sum delta vs no-control: `+0.014451`;
- P-Stack mean boundary sum delta vs no-control: `+0.003097`.

P-Stack has a much smaller boundary-balance degradation than PFO, but the
formal non-degradation criterion is still not satisfied.

### Failed Criteria and Next Modification

The implementation passes source compile, targeted tests, smoke run, and full
closed-loop run. The controller does not fully satisfy the acceptance criteria
because boundary queue balancing is still slightly degraded.

Recommended next modification:

1. run the same joint/coupling mode on `sweet_190` and incident scenarios to
   check whether the P-Stack > PFO result generalizes beyond `sweet_155`;
2. inspect boundary-in/boundary-out queue contributions under joint mode to
   determine whether the residual boundary degradation is caused by offset
   progression, ramp metering pressure, or leader penalty weights;
3. consider a boundary-balance tie-breaker only among near-equal TTT candidates,
   rather than adding a large primary penalty that can distort TTT minimization.

## 2026-07-06 - Sweet 190 Joint Wu-Faithful 7200 s Run

### Purpose

Ran the same joint Wu-faithful proposed mode on `sweet_190` for 7200 seconds to
check whether the `sweet_155` result, where P-Stack beat PFO on total TTT,
generalizes to a stronger demand case.

The first output attempt under `C:\tmp` failed due sandbox file-write denial, so
the final run wrote results under the main workspace output directory.

### Command

```powershell
python -B -m src.experiments.all_scenarios_four_controller_comparison `
  --scenario sweet_190 `
  --T-total 7200 `
  --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG `
  --output "C:\Users\alsrj\Documents\Numerical Simulation\outputs\joint_wu_faithful_sweet190_7200_20260706" `
  --wu-faithful-joint-freeway-rm-vsl `
  --wu-faithful-joint-urban-green-offset `
  --wu-faithful-metering-to-urban-ramp-space
```

Output directory:

- `C:\Users\alsrj\Documents\Numerical Simulation\outputs\joint_wu_faithful_sweet190_7200_20260706`

### Results

| controller | total TTT | freeway TTT | urban TTT | delay | improvement | completed gain | terminal avoided | wall time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO-CONTROL | `25170.572` | `9776.594` | `15393.978` | `23055.218` | - | - | - | `2.371 s` |
| WU-CD-F | `25079.554` | `9828.510` | `15251.043` | `22964.200` | `0.362%` | `+58.0` | `+61.1` | `70.191 s` |
| PROPOSED-FOLLOWERS-ONLY | `12477.256` | `1631.078` | `10846.179` | `10361.903` | `50.429%` | `+15361.9` | `+15367.8` | `628.246 s` |
| PROPOSED-STACKELBERG | `12578.609` | `1667.691` | `10910.918` | `10463.255` | `50.027%` | `+15011.4` | `+15044.3` | `1059.802 s` |

PFO beat P-Stack by `101.353 veh-h` total TTT on `sweet_190`.

### Computation Cost

| controller | mean step wall time | max step wall time |
|---|---:|---:|
| WU-CD-F | `1.747 s` | `2.583 s` |
| PROPOSED-FOLLOWERS-ONLY | `15.699 s` | `17.632 s` |
| PROPOSED-STACKELBERG | `26.480 s` | `44.165 s` |

All controllers remained below the `180 s` control interval. The joint proposed
controllers were faster than the previous `sweet_155` run in wall-clock terms,
but P-Stack remained about `1.69x` slower than PFO.

### Boundary Queue Balancing

Boundary balance non-degradation still fails against no-control:

- WU-CD-F mean boundary sum delta vs no-control: `+0.003141`;
- PFO mean boundary sum delta vs no-control: `+0.037155`;
- P-Stack mean boundary sum delta vs no-control: `+0.036006`.

P-Stack slightly improves boundary balance relative to PFO, but not enough to
pass the formal non-degradation criterion.

### Interpretation

On `sweet_190`, both proposed controllers remain very effective relative to
no-control, cutting total TTT by about `50%` and avoiding roughly `15k` terminal
vehicles. However, the leader layer did not improve over PFO in this stronger
demand case:

- P-Stack had slightly higher freeway TTT (`+36.613 veh-h` vs PFO);
- P-Stack had slightly higher urban TTT (`+64.739 veh-h` vs PFO);
- P-Stack completed about `350.5` fewer vehicles than PFO and left about
  `323.5` more terminal vehicles.

This suggests that the current leader search/penalty combination is not
uniformly better than the PFO anchor under heavier demand. The leader is still
useful as a coordination layer in `sweet_155`, but `sweet_190` shows that the
leader adjustment can drift away from the stronger local-response solution.

### Next Modification

Diagnose P-Stack candidate selection on `sweet_190`:

1. compare selected leader targets against the reverse-engineered PFO equivalent
   `N_P`/`N_UF` trajectory;
2. inspect whether leader MFD/storage penalty and boundary penalty components
   are pushing the leader away from PFO-equivalent targets in late steps;
3. test a stricter PFO-anchor trust-region for heavy-demand cases, where leader
   search can only accept candidates that beat the incumbent PFO response on the
   same predicted objective plus a small tolerance.

## 2026-07-06 - Joint Marginal Price P-Stack Sweet-190 Run

### Implementation

Added an opt-in joint marginal-price channel for the Wu-faithful P-Stack
follower response:

- freeway follower joint control price for `(ramp metering, VSL)`;
- urban follower joint control price for `(green time, offset)`;
- scalar B2/B3/F3 price channels are disabled when joint marginal price is
  enabled to avoid double-counting;
- on-ramp metering-to-urban information remains active through
  `wu_faithful_metering_to_urban_ramp_space`, so tightening metering updates
  ramp reservoir/space before the urban follower is re-solved.

Changed files:

- `src/models/state.py`
- `src/config/default.yaml`
- `src/controllers/wu_faithful_follower.py`
- `src/controllers/stackelberg_wu_metered.py`
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `src/experiments/six_controller_comparison.py`
- `src/tests/test_b3_b4_price_channels.py`
- `src/tests/test_wu_faithful_follower.py`

### Verification Commands

Compile:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -c "from pathlib import Path; import py_compile; out=Path(r'C:\Users\alsrj\Documents\Numerical Simulation\outputs\compile_pycache'); out.mkdir(parents=True, exist_ok=True); files=['src/models/state.py','src/controllers/wu_faithful_follower.py','src/controllers/stackelberg_wu_metered.py','src/experiments/all_scenarios_four_controller_comparison.py','src/experiments/six_controller_comparison.py','src/tests/test_b3_b4_price_channels.py','src/tests/test_wu_faithful_follower.py']; [py_compile.compile(f, cfile=str(out/(f.replace('/','_')+'.pyc')), doraise=True) for f in files]; print('compile ok')"
```

Targeted tests:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_signal_marginal_price src.tests.test_b3_b4_price_channels src.tests.test_wu_faithful_follower
```

Closed-loop smoke:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario sweet_190 --T-total 360 --controllers PROPOSED-STACKELBERG --output "C:\Users\alsrj\Documents\Numerical Simulation\outputs\joint_price_wu_faithful_sweet190_smoke_20260706" --wu-faithful-joint-freeway-rm-vsl --wu-faithful-joint-urban-green-offset --wu-faithful-metering-to-urban-ramp-space --wu-faithful-joint-marginal-price
```

Sweet-190 7200 s run:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m src.experiments.all_scenarios_four_controller_comparison --scenario sweet_190 --T-total 7200 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output "C:\Users\alsrj\Documents\Numerical Simulation\outputs\joint_price_wu_faithful_sweet190_7200_20260706" --wu-faithful-joint-freeway-rm-vsl --wu-faithful-joint-urban-green-offset --wu-faithful-metering-to-urban-ramp-space --wu-faithful-joint-marginal-price
```

### Test Results

- Compile: PASS.
- Targeted tests: PASS, `28` tests, `2` skipped.
- 360 s smoke: PASS, P-Stack total TTT `77.755 veh-h` vs no-control
  `78.344 veh-h`, improvement `0.752%`.
- Constraint suite was also run and exposed three pre-existing/unrelated
  issues: one numerical tolerance issue, one SLSQP availability issue, and one
  outdated WU-CD-F adapter expectation. These are not caused by the joint-price
  implementation but should be cleaned up separately.

### Sweet-190 7200 s Result

Output:
`C:\Users\alsrj\Documents\Numerical Simulation\outputs\joint_price_wu_faithful_sweet190_7200_20260706`

| Controller | Total TTT (veh-h) | Urban TTT | Freeway TTT | Improvement vs no-control | Completed veh | Terminal veh | Computation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No control | 25170.572 | 15393.978 | 9776.594 | 0.000% | 15921.5 | 29139.1 | - |
| PFO | 12477.256 | 10846.179 | 1631.078 | 50.429% | 31283.4 | 13771.3 | 670.320 s |
| P-Stack + joint price | 18310.338 | 12928.583 | 5381.755 | 27.255% | 23812.5 | 21243.1 | 1259.050 s |

Boundary balance:

- PFO mean `B_sum` delta: `+0.037155`, non-degraded check: FAIL.
- P-Stack joint-price mean `B_sum` delta: `+0.053413`, non-degraded check:
  FAIL.

Control validation:

- Joint price diagnostics were logged:
  `diag_wu_faithful_joint_marginal_price=1.0`.
- Joint price counts at the first control step:
  green `5`, metering `4`, VSL `8`, offset `5`.
- P-Stack mean leader targets:
  `N_P=1669.990`, `N_UF=5113.571`.
- P-Stack selected the fallback/PFO incumbent stage in `23` control steps.

### Diagnosis

The joint marginal-price variant did not improve P-Stack. It is still much
better than no-control, but it is worse than both:

- the same-run PFO by `5833.082 veh-h`;
- the prior P-Stack without joint marginal price by about `5731.729 veh-h`.

This indicates that the current marginal price formulation is too blunt for the
Wu-faithful P-Stack setting. The on-ramp metering-to-urban information is
present, but the joint price appears to bias the leader/follower response toward
weaker throughput and higher terminal burden in `sweet_190`. A second limitation
is that the VSL part currently uses a raw global finite-difference gradient
instead of a fully externality-subtracted B2-style local/global difference.

### Next Modification

Do not treat this joint-price variant as the preferred controller yet. The next
target should be:

1. decompose the joint price terms by RM, VSL, green, and offset over time;
2. compare selected P-Stack actions with the same-step PFO anchor action;
3. replace the VSL price with a true B2-style local-vs-global externality price
   or keep VSL inside direct joint evaluation only;
4. test whether the joint price should be diagnostic/reporting-only instead of
   a hard additive follower objective term.

## 2026-07-06 - Joint-Action Forced Legacy Target Probe

### Purpose

Checked whether the latest Wu-faithful joint-action follower can reproduce the
legacy P-Stack action when the leader target is forced to the legacy
`N_P_star/N_UF_star` values. This separates leader search coverage from follower
response-map mismatch.

### Configuration

- Code branch:
  `C:\tmp\Numerical-Sim-joint-price-report`
- Historical traces:
  `C:\Users\alsrj\Documents\Numerical Simulation\outputs`
- Scenario/source runs:
  - current joint-action P-Stack:
    `joint_wu_faithful_sweet190_7200_20260706`
  - legacy P-Stack:
    `legacy_pstack_sweet190_7200_20260702`
- Key options:
  - `wu_faithful_joint_freeway_rm_vsl=True`
  - `wu_faithful_joint_urban_green_offset=True`
  - `wu_faithful_metering_to_urban_ramp_space=True`
  - `wu_faithful_joint_marginal_price=False`
  - serial backend for deterministic probe behavior.

### Output

`C:\Users\alsrj\Documents\Numerical Simulation\outputs\forced_legacy_candidate_probe_joint_action_step20_35_20260706`

### Probe Result

| Step | State | Forced target | Response rollout TTT | Legacy action TTT | Saved PFO TTT | Response + legacy green/offset TTT |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 20 | legacy | legacy `N_P/N_UF` | 803.737 | 784.618 | 799.859 | 785.190 |
| 35 | legacy | legacy `N_P/N_UF` | 1599.219 | 1594.334 | 1609.971 | 1594.274 |

Action differences under the forced legacy target:

- Step 20:
  - Ramp total matched: response `6000.000`, legacy `6000.000`.
  - Green phase-1 sum differed: response `279.000`, legacy `274.000`;
    absolute distance `103.000`.
  - Offset active count differed: response `3`, legacy `5`;
    offset distance `250.000`.
  - VSL mean differed strongly: response `60.000 km/h`, legacy `90.000 km/h`.
- Step 35:
  - Ramp totals were close but not identical by distribution:
    response `5756.250`, legacy `5756.250`, absolute ramp-distance `243.750`.
  - Green phase-1 sum differed: response `312.000`, legacy `346.000`;
    absolute distance `82.000`.
  - Offset active count matched at `5`, but offset distance remained large:
    `230.000`.
  - VSL mean differed: response `55.000 km/h`, legacy `75.000 km/h`.

### Diagnosis

Forcing the legacy leader target is not enough to reproduce the legacy P-Stack
control. The latest joint-action follower matches the total ramp budget fairly
well, but it still chooses different VSL, green, and offset actions. The
ex-post replacement test is especially informative: replacing only the response
green/offset with the legacy green/offset nearly recovers legacy rollout TTT at
both inspected steps. Therefore the remaining gap is not only a leader search
coverage problem; it is also a follower response/scoring problem in the
joint-action Wu-faithful follower.

### Next Modification

Add a labeled candidate-decomposition probe for selected representative steps:

1. inject the exact legacy `(RM,VSL)` and `(green,offset)` candidates into the
   current joint-action candidate sets;
2. log local objective components for selected vs legacy candidates;
3. separate local TTT, density/rho-critical terms, ramp/urban queue terms, VSL
   smoothness, offset/phase-resolved benefit, and feasibility guards;
4. verify whether the legacy candidate is missing from the candidate set or
   present but mis-scored by the current local objective.

## 2026-07-06 - Legacy-Direction Analysis for Generalizable P-Stack Design

### Purpose

The goal is not to copy legacy actions. The goal is to identify which
beneficial directions the legacy controller captured, then design
generalizable price/constraint/response terms that make the current
Wu-faithful P-Stack find similar directions without using legacy outputs.

### Added Diagnostic Scripts

- `work/joint_action_candidate_decomposition_probe.py`
- `work/legacy_direction_ablation_probe.py`

These scripts are diagnostic-only. Production controller behavior was not
changed.

### Commands

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\joint_action_candidate_decomposition_probe.py --scenario sweet_190 --T-total 7200 --steps 20,35 --np-mode cap --state-source legacy --seed legacy_current --output outputs\joint_action_candidate_decomposition_probe_sweet190_step20_35_v2_20260706

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\legacy_direction_ablation_probe.py --scenario sweet_190 --T-total 7200 --steps 20,35 --np-mode cap --state-source legacy --output outputs\legacy_direction_ablation_probe_sweet190_step20_35_20260706

& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B work\legacy_direction_ablation_probe.py --scenario sweet_190 --T-total 7200 --steps 20,35 --np-mode cap --state-source pfo --output outputs\legacy_direction_ablation_probe_sweet190_step20_35_pfo_state_20260706
```

### Outputs

- `C:\Users\alsrj\Documents\Numerical Simulation\outputs\joint_action_candidate_decomposition_probe_sweet190_step20_35_v2_20260706`
- `C:\Users\alsrj\Documents\Numerical Simulation\outputs\legacy_direction_ablation_probe_sweet190_step20_35_20260706`
- `C:\Users\alsrj\Documents\Numerical Simulation\outputs\legacy_direction_ablation_probe_sweet190_step20_35_pfo_state_20260706`

### Findings

1. Current P-Stack with forced legacy leader targets still fails to reproduce
   the legacy action. This is not just a leader search issue.
2. Ramp metering totals are feasible and mostly matched:
   - step 20: response ramp sum `6000.0`, legacy `6000.0`;
   - step 35: response ramp sum `5756.25`, legacy `5756.25`, but ramp
     distribution differs by `243.75 veh/h`.
3. Segment-level VSL is not the dominant source of the gap:
   - step 20: response segment VSL mean `90.0`, legacy `90.0`;
   - step 35: response segment VSL mean `88.75`, legacy `75.0`;
   - replacing all VSL with legacy VSL changes horizon TTT by only about
     `+0.053 veh-h` at step 20 and `-0.215 veh-h` at step 35.
4. The major missing direction is joint signal control, especially green
   allocation with offset:
   - legacy-replayed step 20:
     - current response TTT `803.737`;
     - legacy green all: `790.409` (`-13.328`);
     - legacy offset all: `796.382` (`-7.355`);
     - legacy green+offset all: `785.190` (`-18.547`).
   - legacy-replayed step 35:
     - current response TTT `1599.781`;
     - legacy green all: `1596.518` (`-3.263`);
     - legacy offset all: `1598.339` (`-1.441`);
     - legacy green+offset all: `1594.274` (`-5.507`).
   - PFO-replayed state shows the same broad pattern, although smaller:
     green all improves by `-8.589` at step 20 and `-3.297` at step 35.
5. Candidate coverage and scoring:
   - without injection, the exact legacy green/offset pair is present for only
     `1/5` signals in the final representative decision;
   - after injection, all legacy green/offset pairs are present, but the local
     objective still selects none of them in the final representative decision;
   - therefore both candidate coverage and local scoring/coverage are issues.

### Design Implication

The next controller improvement should not hard-code legacy actions. The
generalizable target is a signal-corridor externality term:

- compute candidate-dependent corridor or one-hop neighbor TTT for
  `(green, offset)` rather than pure own-signal TTT;
- keep the candidate set sparse by adding direction candidates around the
  current solution and finite-difference externality gradients;
- let RM/VSL remain joint, but treat them as secondary in this specific gap
  because the observed legacy/current gap is dominated by urban
  green/offset coordination;
- ensure the added scoring remains cheaper than legacy full grid search.

## 2026-07-06 - Sparse One-Hop Green/Offset Externality for Wu-Faithful PFO/P-Stack

### Purpose

Implement the next design implication from the legacy-direction analysis
without copying legacy actions: `(green, offset)` candidates are still generated
sparsely, but their final score can include one-hop or corridor TTS externality
so a local signal does not select a phase/offset pair that improves only its own
queue while worsening the downstream/corridor response.

### Implementation

Changed files:

- `src/controllers/wu_faithful_follower.py`
- `src/models/state.py`
- `src/config/default.yaml`
- `src/experiments/all_scenarios_four_controller_comparison.py`
- `src/experiments/six_controller_comparison.py`
- `src/tests/test_wu_faithful_follower.py`

Implemented opt-in flags:

- `mpc.wu_faithful_joint_urban_neighbor_tts`
- `mpc.wu_faithful_joint_urban_neighbor_scope`: `ego`, `ego_neighbor`, or `corridor`
- `mpc.wu_faithful_joint_urban_neighbor_weight`
- `mpc.wu_faithful_joint_urban_neighbor_max_green_candidates`
- `mpc.wu_faithful_joint_urban_neighbor_max_offset_candidates`

Controller behavior:

- Applies only when `wu_faithful_joint_urban_green_offset=true`.
- Builds one-hop signal neighbors from grid-node adjacency plus shared
  freeway interface links.
- Scores a `(green p1, offset)` pair as own local TTS plus weighted
  neighbor/corridor local TTS.
- Uses phase-resolved/platoon-aware local rollout for the candidate control,
  so downstream queue/service effects can change with the candidate.
- Keeps candidates sparse by taking feasible candidates nearest to current,
  pressure/default/price anchors and finite-difference directions
  (`±6/±12 s` green, `±cycle/8` and `±cycle/4` offset).
- Leaves RM/VSL joint search unchanged.

### Validation Commands

```powershell
$env:PYTHONPYCACHEPREFIX='C:\Users\alsrj\Documents\Numerical Simulation\.pycache_codex'
& 'C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m py_compile src\controllers\wu_faithful_follower.py src\models\state.py src\experiments\all_scenarios_four_controller_comparison.py src\experiments\six_controller_comparison.py src\tests\test_wu_faithful_follower.py

& 'C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest src.tests.test_wu_faithful_follower src.tests.test_b3_b4_price_channels

& 'C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m src.experiments.all_scenarios_four_controller_comparison --scenario sweet_190 --T-total 360 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output 'C:\Users\alsrj\Documents\Numerical Simulation\outputs\joint_urban_neighbor_sparse_smoke_sweet190_360_20260706' --wu-faithful-joint-freeway-rm-vsl --wu-faithful-joint-urban-green-offset --wu-faithful-metering-to-urban-ramp-space --wu-faithful-joint-urban-neighbor-tts --wu-faithful-joint-urban-neighbor-scope ego_neighbor --disable-stackelberg-fallback

& 'C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m src.experiments.all_scenarios_four_controller_comparison --scenario sweet_190 --T-total 1800 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output 'C:\Users\alsrj\Documents\Numerical Simulation\outputs\joint_urban_neighbor_sparse_sweet190_1800_20260706' --wu-faithful-joint-freeway-rm-vsl --wu-faithful-joint-urban-green-offset --wu-faithful-metering-to-urban-ramp-space --wu-faithful-joint-urban-neighbor-tts --wu-faithful-joint-urban-neighbor-scope ego_neighbor --disable-stackelberg-fallback
```

### Test Results

- `py_compile`: PASS
- targeted unit tests: PASS, `23` tests run, `2` skipped
- closed-loop smoke: PASS

Initial non-sparse implementation was too expensive:

- 360 s PFO computation time: `111.83 s`
- mean PFO follower solve time: about `56 s/step`
- diagnosis: full green grid by offset grid was being evaluated with neighbor
  rollout.

After sparse finite-difference candidate limiting:

| Horizon | Controller | Total TTT (veh-h) | Improvement vs no-control | Computation time (s) | Completed veh | Mean B_sum |
|---:|---|---:|---:|---:|---:|---:|
| 360 s | No-control | 78.344 | - | 0.00 | 1274.9 | 0.068166 |
| 360 s | PFO | 77.576 | 0.980% | 29.78 | 1286.2 | 0.060089 |
| 360 s | P-Stack | 77.821 | 0.668% | 71.62 | 1277.1 | 0.069490 |
| 1800 s | No-control | 1122.196 | - | 0.00 | 6518.0 | 0.068836 |
| 1800 s | PFO | 890.347 | 20.660% | 130.33 | 8507.0 | 0.066850 |
| 1800 s | P-Stack | 898.087 | 19.971% | 370.76 | 8466.9 | 0.069373 |

Mean internal follower costs for the 1800 s run:

- PFO: `1800` neighbor evals/step, `2272` local evals/step,
  `13.033 s` follower solve time/step.
- P-Stack selected responses: `780` neighbor evals/step, `1153.2` local
  evals/step, `7.893 s` follower solve time/step. Total P-Stack wall time is
  still higher because leader candidate evaluation calls follower responses
  repeatedly.

### Diagnosis

The one-hop green/offset externality path is functioning and is much cheaper
after sparse candidate limiting. It also avoids the immediate no-control
degradation observed in the first dense smoke.

However, P-Stack is still slightly worse than PFO in `sweet_190` at 1800 s:

- P-Stack urban TTT is lower than PFO (`633.171` vs `644.784` veh-h),
  which suggests the signal-side externality helps urban coordination.
- P-Stack freeway TTT is higher than PFO (`264.917` vs `245.563` veh-h),
  so the remaining loss is coming from the freeway/ramp tradeoff rather than
  only green/offset local scoring.
- Boundary balance is not fully non-degraded for P-Stack in this 1800 s run:
  mean `B_sum` is `0.069373` vs no-control `0.068836`.

### Failed Criteria / Next Modification

This is not a final controller pass:

- P-Stack does not outperform PFO in the 1800 s `sweet_190` check.
- P-Stack boundary balance is slightly degraded vs no-control.
- Full 7200 s and all-scenario acceptance runs were not rerun after this
  modification.

Next diagnostic should focus on the remaining freeway-side tradeoff:

- compare PFO and P-Stack selected `N_UF`, ramp distribution, ramp queue, and
  segment density over the 1800 s run;
- check whether the leader's N_UF target shifts freeway TTT upward despite the
  improved urban green/offset response;
- only then decide whether RM/VSL marginal price, rho-critical hard feasibility,
  or a leader objective adjustment is the right next step.

### Direct A/B Check: Externality On vs Off

The same `sweet_190`, `1800 s`, fallback-off setup was rerun without
`--wu-faithful-joint-urban-neighbor-tts`:

```powershell
& 'C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m src.experiments.all_scenarios_four_controller_comparison --scenario sweet_190 --T-total 1800 --controllers PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG --output 'C:\Users\alsrj\Documents\Numerical Simulation\outputs\joint_urban_neighbor_off_sweet190_1800_20260706' --wu-faithful-joint-freeway-rm-vsl --wu-faithful-joint-urban-green-offset --wu-faithful-metering-to-urban-ramp-space --disable-stackelberg-fallback
```

| Controller | Neighbor externality | Total TTT | Urban TTT | Freeway TTT | Mean B_sum | Computation time |
|---|---|---:|---:|---:|---:|---:|
| PFO | off | 886.582 | 640.156 | 246.427 | 0.069743 | 182.36 s |
| PFO | on | 890.347 | 644.784 | 245.563 | 0.066850 | 130.33 s |
| P-Stack | off | 888.994 | 637.064 | 251.930 | 0.081210 | 345.80 s |
| P-Stack | on | 898.087 | 633.171 | 264.917 | 0.069373 | 370.76 s |

Conclusion:

- The externality path definitely changes controller behavior and is logged
  (`wu_faithful_joint_urban_neighbor_tts=1` with positive neighbor evals).
- It did **not** improve total TTT in this `sweet_190` 1800 s A/B:
  - PFO worsened by `+3.765 veh-h`;
  - P-Stack worsened by `+9.093 veh-h`.
- It did improve boundary-balance pressure:
  - PFO mean `B_sum` improved from `0.069743` to `0.066850`;
  - P-Stack mean `B_sum` improved from `0.081210` to `0.069373`.
- Therefore the current default-weight externality behaves more like a
  boundary/corridor regularizer than a proven TTT-improving term. It should
  remain opt-in while the next calibration checks lower externality weights
  or state-conditional activation.
