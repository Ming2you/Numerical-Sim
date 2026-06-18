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
