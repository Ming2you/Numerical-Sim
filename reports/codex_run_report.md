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
