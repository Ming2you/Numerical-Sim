# 2026-07-03 작업 노트 — P0+P1+P1.5 + sweet_190 7200s legacy 격차 + 다음 방향

## 1. P0+P1+P1.5 커밋 (dd55468)

- **P0**: Codex f9794b0의 미커밋 follower 반쪽 복원(leader_np_feasible_range 등). anchor-off leader의
  음수 raw N_P 탐색 차단 확인. 검증 7/7 PASS.
- **P1**: freeway agent own-TTS에 blocked-inflow 가상 큐(reservoir 포화로 못 들어온 u_on을 FIFO
  가상 상류 큐로 적립·가산, 튜닝 가중치 없음). closed-loop sweet_190 3600s −3.52%, sweet_128 비트
  동일. 검증 7/7 PASS.
- **P1.5**: rollout_local_tts_ramp_aware에 phase-resolved(arr/gf_by_substep) 선택 인자. closed-loop
  게이트 sweet_190 +1.09%>1%로 STOP → 기본 OFF 휴면. sweet_155만 −1.47% 개선(중부하 조건부
  활성화가 재시도 방향). 검증 6/6 PASS.
- 3-phase 모두 코딩/검증 에이전트 분리 교차검사. 기본 경로 P1 상태와 plant 궤적 sha256 비트 동일.

## 2. sweet_190 7200s — legacy 격차 재측정 (P0+P1 반영)

| controller | total TTT | urban / freeway | no-control 대비 | legacy 격차 |
|---|---:|---|---:|---:|
| legacy P-Stack (기준, Codex 2026-07-02) | 10728.8 | 9201.4 / 1527.3 | 57.38% | — |
| PFO (P0+P1) | 12934.1 | 11654.9 / 1279.2 | 48.61% | −2205.4 |
| P-Stack anchor-on (P0+P1) | 13007.2 | 11530.8 / 1476.3 | 48.32% | −2278.4 |
| P-Stack standalone (P0+P1) | 14711.8 | 13093.6 / 1618.2 | 41.55% | −3983.0 |
| (참고) PFO 수정 전 | 13590.6 | 12365.5 / 1225.2 | 46.01% | −2861.9 |

- **P1 효과 7200s에서 확대**: PFO 13590.6→12934.1 (−4.83%, 3600s의 −3.5%보다 큼). legacy 격차의
  656.5(23%)를 닫음(blocked-inflow만으로).
- **P-Stack이 이제 개선된 PFO보다 나쁨**(13007.2 vs 12934.1). 수정 전엔 P-Stack이 PFO를 이겼음
  (12984.9 vs 13590.6). PFO가 강해지자 leader 한계효용이 음수로 뒤집힘 → leader 평가 충실도 병목.
- **standalone 악화**(14711.8): leader N_UF hard budget(4178~5250)이 follower 자율 metering을 덮어씀.
  P1으로 자율 metering이 똑똑해졌는데 budget 분기가 이를 우회 → leader 부정확 budget이 더 큰 손해.

## 3. Codex 논의 요약 — legacy 탐색영역이 PFO/anchor-P-Stack과 근본적으로 다름

(codex_run_report.md 14526~14730)
- **Multi-start Jacobi probe**: PFO를 legacy previous/current로 seed해도 legacy 근처에 안 머물고
  낮은 ramp-release + zero offset으로 복귀 → 탐색 시작점 문제 아님.
- **Forced leader response probe**: leader가 legacy target 강제해도 follower response map이 legacy
  운영점(높은 ramp release + coordinated offset)을 담지 못함 → leader가 정확한 target을 줘도
  follower가 그 응답을 반환 안 함.
- **결론**: 격차는 "leader가 어디 탐색"이 아니라 "follower가 어떤 응답집합을 반환"의 문제.

## 4. 다음 방향 — leader 전역 rollout을 follower coupling으로 되먹이기 (사용자 아이디어)

**동기**: 현재 follower 국소 rollout은 downstream 가용공간을 `_frozen_s_eff(state)` 현재 스냅샷 한
장으로 씀 → 이웃 동시 유입·downstream 시변을 못 봄. leader의 `_predict()`(stackelberg_mpc.py:1723)는
후보마다 전역 plant rollout로 시변 downstream 궤적을 이미 계산하는데 objective 스칼라에만 쓰고 버림.
이 predicted 궤적을 follower의 s_eff coupling으로 되먹이면 follower가 전역·시변 downstream 효과를
국소 rollout 안에서 봄. legacy가 이겼던 이유(=전역 응답을 후보마다 평가, 3661s)를 leader rollout
재활용으로 싸게 회수하는 길.

**검증 순서 (구현 전 오프라인 probe)**:
- **Step A (oracle 상한)**: legacy 제어를 full-plant rollout해 링크별 s_eff(t) 시변 궤적 추출 →
  follower에 frozen 대신 이 궤적을 주고 green/metering 후보를 채점. follower가 legacy green을
  argmin으로 고르는지(=downstream-궤적-인지 채점이 legacy 응답을 랭킹 1위로 올리는지) 확인.
  이건 상한 테스트: "힌트가 완벽하면 follower가 따라오는가?"
  - 움직이면 → downstream 궤적 가시성이 빠진 재료임이 확증 → Step B.
  - 안 움직이면 → 결함이 s_eff 너머(green 후보 생성 자체)에 있음 → 방향 재설정.
  - 주의(순환성): legacy 궤적은 legacy green으로 형성된 것이라 약한 순환. oracle은 "만약 이
    downstream이 실현된다면 follower가 legacy green을 지지하는가"의 필요조건 테스트로만 해석.
- **Step B (구현 가능판)**: oracle을 실제 leader 예측(부정확하나 무료)으로 대체. 힌트가 follower
  채점에 들어가는 방식 설계 — (a) s_eff 궤적 직접 대체 vs (b) 혼잡 downstream 사용에 대한 shadow
  price(marginal price). 선택된 후보 1회 rollout → follower 최종 commit sweep 단방향 힌트(순환·비용
  회피). 이후 closed-loop.

**보조 방향(상호보완)**: N_UF 등식→cap 전환(leader가 follower 자율 metering을 해치지 못하게).
standalone 악화·bal_med N_UF 폭주를 구조적으로 방지. config에 wu_faithful_np_coordination_mode:cap
이미 존재(N_P용) → N_UF 대칭 적용.

## 5. TODO
- [ ] Step A oracle probe (sweet_190 혼잡 step, legacy trace s_eff(t) 주입 → follower argmin 확인)
- [ ] probe 통과 시 Step B 힌트 통로 설계(s_eff 대체 vs shadow price) + closed-loop
- [ ] N_UF cap 전환(보조 안전장치)
- [ ] P1.5 중부하 조건부 활성화 재검토(sweet_155 −1.47% 살리기)
