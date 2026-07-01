# 2026-07-01 작업 노트 — local-info distributed controller 재구성 검증

## 배경

`9581fcd`(local-info 분산 controller 전면 재구성: `WuFaithfulFollower`/`StackelbergWuMeteredController`)
이후 성능이 재구성 이전보다 나빠지는 현상이 있어, "rollout/Nash equilibrium 탐색 과정에 코딩 버그가
있는 게 아닌가"를 검증했다. `9581fcd`를 pull하고 `reports/local_info_distributed_controller_review_20260701.md`
(외부 리뷰 리포트, 6개 finding)를 읽고 각 finding이 실제로 맞는지 코드+실행으로 직접 검증했다.

작업 방식: 사용자 지시에 따라 코딩과 검증을 **서로 다른 서브에이전트**로 분리해 교차검사했다.

## Finding별 결과

### Finding #1 — 큐만 세는 비용(cost)이 그리드 과충전을 놓칠 수 있다
- `total_urban_vehicles`의 기존 docstring이 이미 경고하던 것과 동일한 패턴(움직임 큐만 세면 링크
  transit에 있는 차량이 비용 0으로 보임).
- `rollout_local_tts`/`_phased`는 실제로 이 패턴을 가짐. 그러나 실제 closed-loop(sweet_155, PFO)에서
  monkeypatch로 "고쳤을 때 candidate argmin(green)이 바뀌는가"를 검증 → **0/150 sweep에서 변화 없음**.
  → 이 시나리오에서는 실제 의사결정에 영향 없는 것으로 판단, **수정하지 않음**.

### Finding #2 — off-ramp drain 시 s_eff 부호 오류 (수정 완료, 커밋 대기)
- `rollout_local_tts_ramp_aware`의 (b) off-ramp 유출 단계에서 자기 own_origin_link로 흘러들어갈 때
  `s_eff[recv] += actual`(점유 감소로 취급)로 되어 있었음. 실제 plant(`_drain_offramp_storage`)는
  반대로 `storage -= actual`(점유 증가=향후 여유공간 감소).
- **수정**: `src/controllers/local_signal_plant.py`의 해당 줄을 `s_eff[recv] = max(0.0, s_eff[recv] - actual)`로 교체.
- 신규 단위테스트 `src/tests/test_local_signal_plant.py::test_offramp_drain_decreases_receiving_space` 추가
  (실토폴로지는 이 분기를 안 타서 손수 최소 `LocalSignalModel`을 구성해 buggy=25.0 vs fixed=35.0으로 판별력 확인).
- **독립 검증 에이전트**가 실제 코드로 재확인, 회귀 없음 확인.
- 현재 5개 신호(A,B,C,D,F) 토폴로지 전부에서 own_origin_links가 자기 own_origin_link로 재진입하는
  경우가 **위상적으로 존재하지 않아**(movement는 항상 하류/다른 신호로만 흐름) 이 버그는 현재 실행에서
  **inert**함을 3중 독립 확인(직접 스크립트 1회 + 중첩 서브에이전트 2건 각각 재확인). 그래도 정합성
  버그이므로 수정은 유지.

### Finding #2 연장 후보 — s_eff 소진을 own_origin_links 조건 없이 모든 recv에 적용
- 검토했으나 실측(sweet_155 PFO 실행) 결과 **0/150 sweep에서 argmin 변화 없음** → 구현하지 않기로 결정.

### Finding #3 — freeway agent의 reservoir-arrival이 release 결정보다 먼저 반영됨 (미수정)
- `_solve_freeway_agent_local`(`wu_faithful_follower.py` 약 1091-1102줄)에서 로컬 모델은
  `u_on_{ramp}` coupling inflow를 `ramp_q`에 먼저 더한 뒤 `ramp_release`를 계산 — 실제 plant
  (`src/simulation/coupling.py::run_coupled_interval`)는 반대 순서(release는 유입 반영 **전**
  reservoir 기준으로 결정, `include_current_arrivals=False`).
- 정확히 진단됨(라인 특정, 실제 plant 순서와 대조 완료)이나, **finding #4(green rank-inversion)의
  원인이라는 최초 가설은 기각**됨 — VSL을 채점하는 함수와 green을 채점하는 함수가 서로 다르고
  VSL 효과 크기가 green 효과 크기보다 훨씬 작아 인과관계가 성립하지 않는다는 지적이 맞았음.
  finding #3은 finding #4와 **분리된, 별도의(더 작은 스코프) 정정 대상**으로 재분류. 아직 수정 안 함.

### Finding #4 — local rollout과 full-plant 사이 green(p1) 랭킹 역전 (재현 실패 → 리포트 원 주장 기각)
직접 재현을 시도하며 두 번 연속으로 **내 재현 스크립트 자체의 방법론 버그**를 발견/수정했다.

1. **1차 시도**: local rollout(1회, 3-interval horizon 상당)과 full-plant를 `run_coupled_interval`
   1회만 호출해 비교 → horizon 불일치로 가짜 "p1=32가 최적"이라는 결과. `horizon_steps=3`번 반복
   누적으로 고치자 "p1=50이 진짜 full-plant 최적"으로 바뀜.
2. **2차 시도(사용자가 직접 지적)**: "PFO는 local info만 쓰는데 왜 50을 선택해? 니 말대로면 56을
   골라야 하지 않아?"라는 모순 발견. 원인 추적 결과 — `_solve_urban_agent_local`은 **Jacobi 합의
   루프 안에서 라운드마다(이 케이스 5라운드) 반복 호출**되며, coupling이 under-relaxation(α=0.5)으로
   라운드마다 갱신된다. 내가 처음 캡처한 건 **1라운드(초기 coupling)**의 인자였는데, 실제 최종
   커밋값은 **5라운드(수렴 직전)**의 인자에서 나온 것 — 서로 다른 시점의 상태를 섞어 비교한 것이
   원인이었다.
   - 1라운드 args로는 p1=56이 이김(내가 처음 관찰한 "모순").
   - 5라운드(최종) args로 다시 계산하면 p1=50이 이김(rollout=1.1922, +smoothness=1.7922) —
     **실제 `solve()` 결과와 정확히 일치**.
3. **결론**: 이 시나리오(sweet_155)에서 finding #4가 주장한 local-vs-full-plant rank-inversion은
   **재현되지 않음**. 최초 리포트/내 재현 모두 "다른 시점(round/horizon)의 상태를 섞어 비교"하는
   같은 종류의 방법론 오류로 가짜 불일치를 만들어낸 것으로 판단.
   재현 스크립트: `scratchpad/reproduce_finding4.py`(1차, horizon 수정 포함),
   `scratchpad/reproduce_finding4_v2.py`(2차, Jacobi round 수정 포함),
   `scratchpad/decompose_finding4.py`(비용 항별 분해, 참고용).

### Finding #5 — Wu-metered P-Stack prefilter가 action-blind (미착수)
- 리포트가 "follower fidelity 수정 이후에" 다루라고 명시. 착수 안 함.

### Finding #6 — post-hoc PFO 라벨이 leaderless solve 결과를 덮어씀 (진단만 확인, 미수정)
- `StackelbergWuMeteredController._pfo_equivalent_action`/`_evaluate_fallback_candidates`가
  leaderless solve 후 `pfo_nash.control.N_P_star`/`N_UF_star`를 덮어쓰는 부분.
- 사용자가 이 수정의 원 의도를 확인: "global searching을 너무 넓게 돌리면 PFO도 못 찾고 비용도
  커져서, 가벼운 PFO를 먼저 돌리고 그 값을 역산한 N_P/N_UF를 anchor로 인근 탐색을 돌리려던 것" —
  즉 **PFO-anchor 탐색 속도 최적화 설계 자체는 문제 없음**, finding #6은 그 부수효과로 생기는
  **라벨링 문제**만 지적한 것으로 재확인. 코드 수정은 아직 안 함.

## 부수 조사 (finding과 별개, 사용자 질문 대응)

- **ramp vs urban 수요 비율**: 균일-스케일 시나리오에서 약 29.2%(1:3.43). `bal_med`는 46.6%(1:2.14)로 다름.
- **leader에 on-ramp penalty가 명시적으로 없는 이유**: `base=follower_ttt`가 `_agent_queue_tts_terms`를
  통해 ramp_queue_tts를 이미 암묵적으로 포함하기 때문. 단, `_response_tts_objective`의
  `density_excess_veh`가 candidate-dependent rollout이 아니라 static `state.freeway_density`로
  계산되는 스코어링 버그를 별도로 발견(이건 옛 `DistributedCoordinator` 코드 경로였고, 실제 활성
  controller는 `WuFaithfulFollower`라 이 발견은 현재 architecture에는 직접 적용 안 됨 — 참고용으로만 기록).
- **capacity drop과 breakdown 방지**: myopic 분산 controller는 network 관점의 breakdown을 못 막지만
  Stackelberg(리더가 있는 P-Stack)는 막을 수 있다는 메커니즘을 확인(FD/density 시각화로 검증).
- **sweet-spot 시나리오 탐색**: demand 1.15~1.35 스윕에서 sweet_128/135/155가 P-Stack이 PFO를 이기는
  성공 사례. `bal_med`(총수요는 sweet_128과 비슷하나 FW_E merge 149% vs 119%, ramp 비중 더 높음)는
  반대로 leader가 N_UF*=6000(최대)을 선택해 freeway breakdown을 유발 — 실패 사례. 수요 "총량"이
  아니라 **freeway 대비 ramp 비중과 병목(merge) 압력**이 성공/실패를 가르는 것으로 판단.

## 코드 변경 사항 (이 세션)

- `src/controllers/local_signal_plant.py`: off-ramp drain 시 s_eff 부호 수정(finding #2).
- `src/tests/test_local_signal_plant.py`: 신규 — off-ramp drain 방향성 단위테스트.

## 프로세스/안전 관련 유의사항 (이번 세션에서 확인된 것, 계속 준수)

- 서브에이전트에게 열린 형태로 "조사해서 고쳐줘"를 주면 (a) 계획만 서술하고 실행 안 하거나
  (b) 불필요하게 중첩 서브에이전트를 또 띄우는 실패가 반복됨 → 정확한 라인/코드까지 명시한 스펙을
  주고, "Agent tool로 재위임 금지", "실제 명령 실행 결과를 인용하라"를 명시해야 함.
- **`git stash`(및 `git stash drop`)는 이 저장소에서 어떤 에이전트 작업에도 금지** — 검증 에이전트가
  자체 A/B 테스트용으로 `git stash`를 쓰다가 동시에 실행 중이던 `git pull`과 충돌해 자기 작업을
  날릴 뻔한 사고가 있었음(실제 사용자 작업 손실은 없었음, `git fsck`로 확인). 이후 before/after
  비교는 파일 복사나 `git show HEAD:path`로 하도록 지시.
- 백그라운드 에이전트가 저장소에서 작업 중일 때는 같은 디렉터리에서 직접 git 명령을 실행하지 않는다
  (레이스 컨디션 방지).

## 다음 단계 (미결)

1. finding #3(freeway VSL reservoir-timing 버그)을 finding #4와 무관한 별도 정정으로 수정할지 결정.
2. finding #4를 다른 시나리오/신호에서도 한 번 더 확인해 완전히 기각할지, 아니면 특정 조건에서만
   재현되는지 확인.
3. finding #5, #6 코드 수정 착수 여부 결정(#5는 리포트가 #3/#4 이후로 순서 지정).
4. Fix #2(off-ramp drain 부호) 커밋/푸시 — 이번 커밋에 포함.
