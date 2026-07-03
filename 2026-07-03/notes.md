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

## 4b. Step A 오라클 probe 하네스 구축 완료 (coding agent, 2026-07-03)

**작업 1 (production, None-게이트 하위호환)** — `src/controllers/local_signal_plant.py`
세 rollout 함수에 선택 인자 `s_eff_by_substep: Optional[Mapping[str, Sequence[float]]] = None` 추가.
- 각 substep 루프 맨 앞(도착·서비스 이전)에서 None 아니면 각 recv 링크
  `s_eff[recv] = float(s_eff_by_substep[recv][sub])`로 덮어씀 → ego 방출 내부감소가 매 substep
  oracle로 리셋(진짜 downstream 가시성). 키 없는 링크는 내부값 유지. None이면 legacy와 비트 동일.
- ramp_aware는 arr/gf_by_substep 뒤에 위치(키워드 전달 필요).
- 단위테스트 TestSEffBySubstepInjection: (1)None==legacy 비트동일, (2)상수 oracle 리셋이
  ego 감소 무효화해 cost 변화. 파일 전체 5/5 PASS.

**작업 2 (probe)** — `work/step_a_oracle_probe.py`
- 채점 (a)frozen(현행) (b)oracle(rollout 3개 monkeypatch로 s_eff 궤적 주입) (c)truth(ego 신호만
  green 변경·나머지·freeway legacy 고정, full plant horizon TTT).
- frozen/oracle은 production `_solve_urban_agent_local`을 단일 후보로 호출해 추출
  (`_urban_green_candidates`를 [p1]만 반환하도록 임시 몽키패치 → best_obj=그 후보 cost).
- CSV 파싱: green_{sig}_p1/p2, offset_{sig}, ramp_metering_{ramp}, vsl_{link}_seg{i}→
  vsl["{link}__seg{i}"], vsl_{link}→vsl["{link}"]. **CSV time_sec는 step 종료 후((step+1)*180)라
  demand time과 다름** → demand는 step 컬럼으로 재구성(j*180).
- oracle s_eff 궤적: state_k에서 legacy로 horizon회 전진, 각 interval **종료 후** S_eff 기록,
  piecewise-constant로 K_cu(36) substep 확장(길이 horizon*K_cu=108).

**dry-run(PFO stand-in, step 20)**: 완주. 예상대로 oracle==frozen argmin(PFO downstream≈frozen).
raw cost는 frozen≠oracle(모든 후보 ~0.01-0.02 차이)로 주입 실제 작동 확인. 부수관찰:
frozen/oracle 모두 p1≈56(대칭) 선택하나 truth는 C=68/D=62/F=56 등 크게 다름 → 국소 green 랭킹이
full-plant 최적과 어긋남(실제 legacy trace가 검증할 현상).

**실제 legacy trace 최종 실행 명령(coordinator)**:
`python -B work/step_a_oracle_probe.py --scenario sweet_190 --legacy-trace <legacy control_timeseries.csv> --steps 20,26,35 --output outputs/_stepA_probe`

## 4c. Step A oracle probe 실행 결과 — **음성(검증된 진짜 음성)**: s_eff 채널 기각

legacy P-Stack sweet_190 7200s 재생성(이 머신, total_ttt=10728.763 — Codex 수치와 정확 일치).
step 20/26/35에서 follower green 후보를 frozen / oracle(legacy s_eff(t) 주입) / full-plant truth로 채점.

**결과: oracle argmin == frozen argmin (15/15), oracle이 truth·legacy에 더 가까워진 경우 0/15.**
그리고 |frozen−oracle| cost가 **모든 후보에서 정확히 0**.

원인 규명(ZERO/HUGE 극단 주입 대조 테스트):
- 주입 메커니즘은 정상 — s_eff를 전부 0으로 밀면 cost +32/+24/+34, ∞로 밀면 −19/−19/0 변동.
- legacy oracle이 frozen과 0 차이인 진짜 이유: **s_eff 채널이 작동 범위에서 binding이 아님.**
  substep당 방출 ~1–2 veh인데 링크 여유공간 30–200 veh → 여유가 70이든 31이든(legacy가 frozen과
  다른 부분) 방출을 제약 못 함. binding하는 유일한 케이스는 완전포화(공간≈0)인데 그 링크(C_to_F)는
  frozen·legacy 양쪽 0으로 동일. 즉 legacy downstream은 오직 **non-binding 중간범위**에서만 frozen과
  다름 → 랭킹 무영향.

**함의**: downstream **정보**(s_eff/leader-rollout-되먹임의 s_eff 경로)로는 follower green 랭킹을
못 움직임. full-plant는 신호 C에 p1=80(=legacy) 원하는데 국소는 p1=47 고름 — 이 격차는 s_eff로 안 닫힘.
follower green은 자기 두 phase 큐 균형에만 반응, downstream엔 사실상 무감각.

## 4d. 방향 확정 — 정보(i)가 아니라 가격(ii). P1 재해석 + leader marginal cost

- Step A 음성으로 **재료 (i)가시성은 s_eff 경로로 전달 불가** 확정. 실효 레버는 **재료 (ii)가격**.
- P1이 작동한 이유가 여기서 분명해짐: P1은 정보(상태 입력)가 아니라 **additive 비용 항(price)**.
  blocked_q를 objective에 **더한** 것 → 가격 채널은 binding, 정보 채널은 non-binding.
- **P1 이중가격 정밀 분석**: blocked 차량이 urban(자기 큐)·freeway(blocked_q) 두 objective에 잡히나,
  분산 Nash는 합산 안 하고 각자 최소화하므로 **왜곡 아님**(Pigouvian 구조로 정당). 각 copy가 서로 다른
  결정을 몲(urban→green, freeway→metering). 실측 방향: P1으로 freeway TTT +54, urban −710 → **freeway가
  희생하고 urban 구제**(순 −656). 진짜 결함은 이중가격이 아니라 (a) frozen u_on 과대적립(과방류 편향),
  (b) 공유 externality 과응답 — 즉 P1은 "작동하나 dirty한 price". sweet_190은 freeway +54가 breakdown
  아닌 가벼운 희생이라 순이득이나, freeway-지배 시나리오선 과방류 breakdown 위험.

- **핵심 설계 합의**: P1 blocked_q는 **손코딩한 한 개 국소 externality 근사**(u_on coupling으로 계산).
  leader의 marginal cost = ∂(전역 TTT)/∂(국소 행동)은 그것의 **정확·완전 버전**(multi-hop·corridor·
  freeway↔urban 피드백 포함, 어떤 단일 coupling에도 안 담김). 이 미분은 전역 rollout이 필요해 **순수
  분산 follower가 구조적으로 계산 불가 → 환원 불가능하게 leader 전용.** 이게 "leader가 PFO가 못 하는
  것"의 airtight 정의.
- **P1은 scaffolding**: "additive 가격이 follower 결정을 움직인다"를 증명한 프로토타입. 이제 손코딩
  blocked_q를 leader 계산 marginal price로 **대체·승격** → P1은 PFO에 안 남고 P-Stack marginal price에
  흡수. PFO=순수 own-TTS(marginal price 계산 불가), P-Stack=own-TTS + leader marginal price. 대칭·원리적.
  (현재 leader가 이미 전역 rollout `_predict` + 스칼라 dual λ_P 계산 → per-follower marginal cost는 그
  자연 일반화: 집계 λ 하나 → 공간분해 가격 벡터. 스칼라 2개 대역폭 한계를 여기서 넓힘.)

- **실험 설계 — 3점 사다리**((i)/(ii)/(iii) 재료 대응, 정직한 분해):
  1. PFO 순수(own-TTS, leader 없음, tax OFF) = 무조정 Nash.
  2. PFO + tax(leader 없음, tax ON) = 가격만 [ii].
  3. P-Stack(leader + marginal price) = 가격 + leader 조정 [ii+iii].
  격차 1→2=가격 가치, 2→3=leader 순수 가치. **주의**: 현재 P-Stack(13007)이 PFO+P1(12934)보다 나쁨 →
  격차 2→3 음수 = leader가 아직 순수 가격보다 못함(leader fidelity 병목 정량). 재귀속(P1→P-Stack)하면
  headline은 "P-Stack이 순수 PFO(~13590) 이김"으로 개선되나, 이 뒤집힘은 **원리(own-TTS 순수성)의 귀결**
  이어야지 숫자 gaming으로 보이면 안 됨. 사다리로 둘 다 정직하게 보고.

## 5. TODO
- [x] Step A oracle probe 실행 → **음성 확정**(s_eff 채널 non-binding, 정보로는 조정 불가).
- [ ] **Step B marginal-price probe**: leader 전역 rollout으로 각 신호 green의 marginal 전역 TTT 민감도
  (probe는 유한차분) 계산 → follower green 비용에 `−price·(phase 방출)` 항 주입 → argmin이 full-plant
  최적(=legacy green)으로 이동하는지 확인. 이동하면 가격 채널 검증 → 저렴판(자원 shadow price, 전역
  rollout 1회) 설계 + closed-loop. 이동 안 하면 가격 형태(어느 자원에 거는가) 재설계.
- [ ] 3점 사다리 실행(P1을 leader 유무로 게이트: count_blocked_ramp_inflow) — sweet_190(+128/155).
- [ ] N_UF 등식→cap 전환(leader가 자율 metering 못 덮게, standalone 악화·bal_med 폭주 방지).
- [ ] P1.5 중부하 조건부 활성화 재검토(sweet_155 −1.47% 살리기).

## 6. Step A 하네스 production 변경 (커밋 대상)
- `src/controllers/local_signal_plant.py`(+25): 세 rollout에 `s_eff_by_substep` 선택 인자(None-게이트,
  None이면 기존과 비트 동일). Step A용 주입 통로이자 향후 Step B 재사용 가능.
- `src/tests/test_local_signal_plant.py`(+61): TestSEffBySubstepInjection 2건. 전체 13/13 PASS.
- `work/step_a_oracle_probe.py`: probe 하네스(진단용).
