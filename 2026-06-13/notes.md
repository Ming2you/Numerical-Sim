# 2026-06-13 작업 노트

## 1. Codex Wu/baseline 수정 검토·push (4dc1380)

사용자(Codex 폴더 `Documents/Numerical Simulation`)의 수정을 diff·리포트 대조로 검토.
전부 타당한 버그 수정으로 판정, 106 테스트 통과 확인 후 push.

- `ControlAction.uncontrolled` 신설 — no-control baseline의 allocation 이중 게이팅 제거
  (fixed()의 0.5cap allocation × green fraction 중복). no_control/fixed_signal/Wu 중립
  action 물리 통일 + 동일성 테스트.
- Wu u_on coupling: 큐 합·용량 합의 min(분리 합산)이 phase split 효과를 소거하던 것을
  movement 단위 green release(`estimate_onramp_green_release_flows`)로 수정.
- Wu freeway local solve: 단일 평균밀도 근사(항상 최고 VSL 선택 편향)를 multi-segment
  METANET rollout으로 교체.
- WU-CC-F objective: proposed leader penalty 혼입 제거 — horizon 실제 TTT + 단위 정규화
  variation.
- leader 후보 farthest-point 선택(corner/직전 보존), segment→link VSL min 합의,
  leaderless metering에 본선 상류 유입 포함, centralized coordinate bound probe.
- **파급**: 기존 풀 매트릭스(6807ef4) 수치는 구버전 구현 기준 — 4-controller 재실행으로
  대체 예정.

## 2. 비교군 재정의 (스펙 37d1fee + 구현)

연구자 결정에 따라 spec 16 개정.

- **주 비교군 6→4**: WU-CD-F / PROPOSED-FOLLOWERS-ONLY / PROPOSED-STACKELBERG /
  PROPOSED-CENTRALIZED. WU-MATCHED·WU-CC는 보조 참고군(구현 유지).
- **P-FO 재정의**: allocation module은 Leader target을 입력으로 갖는 coordination
  기구이므로 leaderless에서는 module 자체를 제거. active controls = green 자유탐색
  ([green_min, green_max]) + offset + ramp metering + VSL. movement service는 plant
  포화유율 fallback(Wu와 동일). 구 정의(모듈 유지+균형/drain objective) 결과는
  6807ef4 이력에 보존.
- **pair 재정의**: ProposedLeaderValue = Leader+allocation **결합** 효과(단독 해석 금지),
  FullPackageValue(WU-CD-F vs P-STACK) 신설, FollowerPackageDifference는 "양쪽 다
  allocation 없음" 해석으로 갱신. Wu 계열 3쌍은 부록 전용.

## 3. P-FO 재구현 (이 커밋)

- `urban_follower.py`: `solve(leader=None)` → `_solve_leaderless` 분기 —
  `_search_green_times`(신호별 후보 p1 ∈ linspace(green_min, green_max, 7), 경량 큐
  모델 = green/cycle×Σ포화유율, horizon rollout, 잔여 큐+Δgreen 비용; freeway 압력의
  off-ramp phase 가중은 full follower와 동일 경로 유지) + `_offsets` + allocation {}.
- `distributed_coordinator.py`: leaderless에서 allocation 모듈 미호출(plan=None),
  초기 reference = `ControlAction.uncontrolled`(숨은 게이팅 방지), merge 시
  allocation {} 고정(legacy 합산 생략), agent 추출 가드.
- `inflow_outflow_allocation.py`: leaderless 분기 제거(이번 변경으로 호출처 소멸) —
  모듈은 항상 leader target 필요.
- `authority.py`: `NO_ALLOCATION = WU_GROUP ∪ {P-FO}`(P-FO allocation 열 0 강제),
  `PRIMARY_CONTROLLERS` 4종 추가.
- runner: PAIRED 4주쌍+부록 3쌍(실행된 쌍만 계산), 기본 --controllers=주 4종,
  fidelity matrix P-FO 행 갱신. `aggregate_post_analysis.py` PAIRS도 주 4쌍.
- 테스트: spec 16.13 개정명 반영 — primary_four / no_allocation_control /
  green_searched_within_bounds / differs_by_leader_and_allocation_only 추가·개명.
  **108/108 통과.**

## 4. P-FO smoke (peak 1800s, `2026-06-13/results/pfo_redef_smoke`)

- TTT 594.8, authority_ok=True.
- 검증: allocation_* 전열 0 / N_P_star=N_UF_star=0(숨은 목표 없음) / offset 활성
  (D 95s 부근 corridor 정렬) / metering 국소 활성(580~824 veh/h) / green 탐색 범위 내
  (균형 큐에서 56 유지, 큐 편중 시 이동은 단위테스트로 확인).

## TODO

- 4-controller 풀 매트릭스 재실행(7200s × 5 시나리오 × s42 + peak s123/s7) — Codex
  수정 + P-FO 재정의 반영판. 이후 집계·리포트 전면 갱신.
- Stage 2·3도 수정된 코드 기준 재실행 여부 결정(leader/coordinator 수정이 P-STACK에도
  영향).
