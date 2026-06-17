# Proposed controller refactor 실행 로그

작성 시작: 2026-06-17 21:51 KST

## 목적

Proposed Stackelberg controller가 연구 수식과 Wu distributed controller의 neighbor-coupling 구조에 맞게 동작하도록, 아래 순서로 순차 수정한다.

```text
D -> C -> B -> E -> A
```

각 단계는 다음 절차를 따른다.

1. Codex가 해당 step의 구체 작업 범위를 확정한다.
2. 코딩 subagent가 지정 파일 범위 안에서 구현한다.
3. 리뷰 subagent가 구현과 테스트를 검토한다.
4. Codex가 최종 검토하고 필요 시 보정한다.
5. 이 MD에 구현 결과, 리뷰 결론, 검증 결과를 기록한다.
6. 해당 step 변경만 커밋하고 GitHub에 push한다.

## 단계 요약

| Step | 주제 | 상태 | 커밋/푸시 |
|---|---|---|---|
| D | Leader objective를 제안 수식과 정합화 | 완료 | Step D 커밋으로 완료 |
| C | Wu식 full neighbor coupling을 Proposed distributed follower에 이식 | 완료 | Step C 커밋으로 완료 |
| B | Leader forecast 테스트를 후보집합이 아닌 평가/선택 기준으로 수정 | 대기 | 미완료 |
| E | `N_P_crit_veh` 재보정 | 대기 | 미완료 |
| A | VSL forecast-aware 테스트 및 objective saturation 조정 | 대기 | 미완료 |

## 공통 원칙

- 작업 브랜치: 현재 체크아웃된 브랜치에서 진행한다.
- 각 step은 가능한 한 작게 유지한다.
- 서로 다른 step의 변경을 한 커밋에 섞지 않는다.
- working tree에 사용자 또는 다른 에이전트의 변경이 보이면 되돌리지 않고 먼저 diff를 확인한다.
- 테스트 실패는 숨기지 않고 이 문서와 `reports/codex_run_report.md`에 남긴다.
- full 7200s simulation은 코딩/단위 검증 이후 필요 시 별도 step으로 실행한다.

## Step D: Leader objective 정합화

### 의도

현재 기본 leader objective는 `state_accumulation` base를 사용하고, `boundary_in_queue_penalty`와 `non_convergence_penalty`를 total objective에 포함한다. 사용자가 제시한 수식에 맞추기 위해 다음을 수정한다.

- 기본 objective base를 follower-response TTT/TTS로 둔다.
- `boundary_in_queue_penalty`는 total objective에서 제거한다.
- `non_convergence_penalty`는 total objective에서 제거하고 diagnostic으로만 유지한다.
- spec/config/test가 같은 수식을 가리키도록 갱신한다.

### 담당/검토 기록

- 코딩 subagent: `Ptolemy` (`019ed5a4-fbdc-78e2-a256-f6f1aef36629`)
- 리뷰 subagent: `Hypatia` (`019ed5ad-2842-71e1-815c-8d23a8a47f8a`)
- Codex 최종 판정: PASS. 리뷰어가 지적한 `boundary_in_queue_vehicles()` 주석 불일치와 run report 누락을 보정했다.
- 검증:
  ```text
  C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_constraints src.tests.test_metanet_equations src.tests.test_offramp_reattribution -v
  ```
  결과: `70 tests, OK`.
- 구현 요약:
  - 기본 `leader.objective_mode`를 `follower_ttt`로 변경했다.
  - `leader_total_objective`는 follower TTT/TTS base + `N_P` 초과 penalty + freeway density penalty + leader action smoothness만 포함한다.
  - `leader_boundary_in_queue_penalty`와 `leader_nonconvergence_penalty`는 diagnostic으로 남기되 total objective에는 더하지 않는다.
  - `docs/spec/04_controller.md`, `docs/spec/09_configuration_requirements.md`, `docs/spec/07_auto_diagnosis.md`, 관련 unit tests를 같은 의미로 갱신했다.
- 리뷰 결론:
  - `Hypatia`: PASS_WITH_NOTES.
  - 지적 1: `boundary_in_queue_vehicles()` 주석이 이전 objective 비용 의미를 유지하고 있었음. Codex가 수정 완료.
  - 지적 2: `reports/codex_run_report.md`에 Step D 기록 필요. Codex가 수정 완료.
- 커밋/푸시: 이 Step D 변경 커밋으로 완료

## Step C: Proposed distributed coupling 정합화

### 의도

Wu controller의 neighbor-coupling 철학을 Proposed distributed follower에도 맞춘다. 단순히 urban -> freeway on-ramp만 보는 것이 아니라, 아래 결합을 함께 검토한다.

- urban -> freeway: urban green decision 이후 on-ramp reservoir inflow를 `u_on_*` coupling으로 전달
- freeway(off-ramp) -> urban: predicted off-ramp flow/storage pressure를 urban phase arrival/pressure에 반영
- urban -> urban: upstream green release가 downstream phase arrival pressure로 전달
- freeway -> freeway: 인접 freeway segment/link의 density, speed, flow, lane-drop/spillback pressure를 VSL/metring 판단에 반영

### 담당/검토 기록

- 코딩 subagent: `Anscombe` (`019ed5b4-50ac-78e3-950b-3b127b25e357`)
- 리뷰 subagent: `Meitner` (`019ed5c3-9082-78c1-9eb0-48987be3b78a`)
- Codex 최종 판정: PASS. 리뷰 지적을 반영해 beta 집계, lane-loss consumption, metering factor, ablation diagnostics, metric semantics를 보정했다.
- 구현 요약:
  - urban -> freeway: `u_on_*` coupling을 ramp-space cap 없는 `estimate_onramp_reservoir_inflow(..., interval_h=T_c_h)` 기반으로 변경했다.
  - freeway(off-ramp) -> urban: freeway agent가 선택한 VSL의 off-ramp별 predicted arrival/storage pressure를 UrbanFollower phase forecast/pressure로 전달한다.
  - urban -> urban: upstream green release rate를 downstream phase arrival pressure `arr_*`로 전달하되, 같은 origin/phase의 beta 합을 사용한다.
  - freeway -> freeway: 인접 segment density/speed/flow/lane-loss를 coupling으로 내보내고, neighbor pressure를 VSL cost와 ramp metering upper에 약하게 반영한다.
  - ablation diagnostic을 `distributed_u_to_f_coupling_active`, `distributed_f_to_u_coupling_active`, `distributed_u_to_u_coupling_active`, `distributed_f_to_f_coupling_active`로 분리했다.
- 검증:
  ```text
  C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile src\controllers\distributed_coordinator.py src\controllers\urban_follower.py src\tests\test_forecast_awareness.py src\tests\test_constraints.py
  ```
  결과: OK.
  ```text
  C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_forecast_awareness.ForecastAwarenessTests.test_onramp_coupling_preserves_green_difference_when_ramp_full src.tests.test_forecast_awareness.ForecastAwarenessTests.test_upstream_green_release_enters_downstream_phase_coupling src.tests.test_forecast_awareness.ForecastAwarenessTests.test_urban_follower_uses_selected_offramp_arrival_response src.tests.test_constraints.ConstraintTests.test_distributed_freeway_agent_reports_neighbor_pressure src.tests.test_constraints.ConstraintTests.test_distributed_ablation_diagnostics_report_blocked_coupling -v
  ```
  결과: `5 tests, OK`.
  ```text
  C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m unittest src.tests.test_forecast_awareness src.tests.test_constraints -v
  ```
  결과: `52 tests, 50 OK, 2 expected pending failures`.
  - `test_leader_candidates_reflect_forecast_summary`: Step B에서 후보집합이 아닌 평가/선택 기준으로 수정 예정.
  - `test_freeway_vsl_uses_future_offramp_inflow`: Step A에서 VSL saturation fixture/objective 조정 예정.
- 리뷰 결론:
  - `Meitner`: 1차 PASS_WITH_NOTES.
  - Codex 보정 후 재리뷰: PASS_WITH_NOTES. 이전 findings는 실질적으로 해소됨.
  - 남은 note: `LOCAL_ONLY_COUPLING_PLAYERS` active flag는 전역 요약이며 per-agent 차단 상태까지 표현하지 않는다. Stage 3 정밀 진단이 필요하면 후속으로 per-agent flag를 추가한다.
- 커밋/푸시: 이 Step C 변경 커밋으로 완료

## Step B: Leader forecast 테스트 수정

### 의도

현재 실패 테스트는 forecast가 바뀌면 leader 후보 집합 자체가 달라져야 한다고 가정한다. 그러나 후보 집합은 같아도 되며, 중요한 것은 forecast에 따라 후보 평가값, ranking, 최종 선택이 달라지는지다.

수정 방향:

- 후보 집합 차이를 요구하는 assertion 제거
- candidate evaluation/ranking/selected leader action 기준의 테스트로 변경
- 필요 시 Stackelberg decision metadata에 후보 평가 diagnostic 추가

### 담당/검토 기록

- 코딩 subagent: 미배정
- 리뷰 subagent: 미배정
- Codex 최종 판정: 미완료
- 검증: 미실행
- 커밋/푸시: 미완료

## Step E: `N_P_crit_veh` 재보정

### 의도

off-ramp storage 재귀속과 objective/coupling 변경 이후 기존 `N_P_crit_veh = 556.081`이 stale일 가능성이 크다. D/C/B가 완료된 뒤 같은 plant/controller 기준으로 재보정한다.

### 담당/검토 기록

- 코딩 subagent: 미배정
- 리뷰 subagent: 미배정
- Codex 최종 판정: 미완료
- 검증: 미실행
- 커밋/푸시: 미완료

## Step A: VSL forecast-aware 테스트 및 objective saturation 조정

### 의도

현재 VSL forecast-awareness 테스트는 off-ramp storage를 거의 포화 상태로 만들기 때문에 low/high forecast 모두 최저 VSL 후보로 붙는다. C/E 이후 실제 VSL behavior를 다시 본 뒤 다음을 조정한다.

- forecast magnitude sensitivity를 볼 수 있는 중간 storage fixture로 테스트 수정
- objective가 너무 빨리 최저 VSL로 saturate되는지 검토
- 필요한 경우 VSL objective weight/normalization 조정

### 담당/검토 기록

- 코딩 subagent: 미배정
- 리뷰 subagent: 미배정
- Codex 최종 판정: 미완료
- 검증: 미실행
- 커밋/푸시: 미완료
