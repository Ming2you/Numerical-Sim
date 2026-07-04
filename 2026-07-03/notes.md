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

## 4e. Step B1 marginal-price probe 실행 결과 — **가격 채널 양성 확정**

sweet_190 step 20/26/35 × 신호 5개. 각 신호 green 후보를 국소 own-TTS로 채점하고, leader-계산가능
per-signal marginal price를 유한차분으로 뽑아 `local(p1)+w·g·(p1−p1_0)` argmin이 truth로 이동하는지.
(work/step_b_marginal_price_probe.py, Step A 하네스 재사용, step_a 재현 오차 0.0)

**truth로 이동한 signal-step 수(15개 중)**:
| w | full gradient g_i | externality g_ext=g_i−d_local/dp1 |
|---|---|---|
| 0.0(=frozen) | 0 | 0 |
| 0.5 | 0 | 8 |
| **1.0(1차 정확)** | 1 | **9** |
| 2.0 | 2 | 7 |

- **가격 채널 작동**(ext 9/15) — 정보 채널(Step A 0/15)과 결정적 대조. A·C는 w=1에서 argmin이
  truth에 **정확 착지**(A:46→68, C:47→80 등).
- **externality 가격 ≫ full 가격**(9 vs 1). full g_i는 자기 own-TTS 변화가 상쇄해 거의 0(무력).
  g_ext=g_i−d_local/dp1로 own-TTS 몫을 빼야 부호·크기가 살아남 — **P1 이중가격 우려의 정확한 처방을
  수치로 확증**(순수 Pigouvian이 정답). 예: D@20 g_i=−0.19(부호 틀림)→g_ext=+0.93(부호 맞음).
- **w≈1.0이 sweet spot**(1차 정확값, 튜닝 fudge 아님). w=2는 overshoot(9→7).

**한계**: step 35 실패 군집(truth 곡선이 p1_0 근처 non-monotone/flat) — 단일 operating point의 1차
선형 가격이 부족. 처방 = **iteration**(operating point가 움직이며 재선형화 = dual ascent/SQP, 곧
event-trigger refresh cadence). 신호별 g_ext 크기가 달라 단일 전역 w는 부적절 → 신호별 w=1(자기 g_ext).

## 4f. 종합 — (i)정보 기각, (ii)가격 채널 검증. 다음=B2 구현

세 재료 실증 완료: (i)가시성=s_eff 채널 non-binding(기각), (ii)가격=per-signal externality price가
argmin을 전역최적으로 이동(양성), (iii)조정=부호가 신호마다 반대(A/C 고p1·D/F 저p1)라 스칼라 하나로
불가·**per-signal 가격 벡터 필수**. 이 벡터=∂(전역TTT)/∂(신호 행동)은 전역 rollout 필요 → leader 전용.

**Step B2(구현) 설계**:
- leader가 refresh마다 per-signal `g_ext_i = d전역TTT/dp1 − d_local/dp1`(유한차분, 전역 rollout)을
  계산해 follower에 하달. follower는 green 비용에 `g_ext_i·(p1−p1_0)`(w=1) 추가.
- **leader 있을 때만 활성**(P-Stack) → PFO는 순수 own-TTS 유지(4d 프레이밍 해소).
- refresh: event-trigger(또는 기존 global_refresh cadence 재사용). 사이엔 hold+국소 적분보정(A1+A2 λ의
  벡터 일반화). 비용: 5신호×2섭동×3interval=30 run_coupled_interval/refresh(현 leader 탐색보다 저렴).
- non-monotone(step35)은 operating point 이동에 따른 재선형화로 흡수.
- N_P/N_UF 스칼라를 이 가격 벡터로 대체/보완할지는 B2 설계 결정.

## 4g. Step B2 production 구현 결과 — 가격 채널 end-to-end 검증(양성, modest)

leader가 decide_with_info에서 operating point(=previous)에 대해 per-signal `g_i=d(전역TTT)/dp1`을
`_predict` 유한차분(±δ=6)으로 계산해 follower.green_price에 하달. follower는 `g_ext=g_i−d_local/dp1`
(own-TTS 기울기 차감, 중심차분)를 green 비용에 `g_ext·(p1−prev_p1)` 항으로 주입. leader 있을 때만
활성(PFO 게이트 off). base stackelberg_mpc.py 미변경(subclass decide_with_info override). refresh=매 step
(=successive linearization). (구현: 코딩 에이전트가 세션 종료로 검증 전 중단 → 코드는 완성돼 있어
coordinator가 직접 검증.)

**검증(전부 PASS, B2 신규 파손 0)**:
- **probe 앵커 테스트**: probe g_i 주입 시 follower argmin이 probe ext@w=1과 일치(A→68, C→80) → production이 검증된 메커니즘 동일 재현.
- **PFO 순수성**: sweet_128 3600s = **742.210 비트동일**(PFO는 green_price 안 받음, own-TTS 보존).
- **하위호환**: green_price=None이면 기존과 동일. follower 10/10 PASS.
- **회귀**: constraints+six_controller 6실패는 전부 pre-existing stale/env(DistributedCoordinator assert·SLSQP·float tol·VSL). B2 무관.
- **closed-loop**(sweet_190 3600s, deterministic): green_price OFF=3075.473 → ON=**3052.001**(−23.5 veh·h, **−0.76%**), 시간 362→393s(+8.5%, 30 rollout/step).

**해석**: 가격 채널이 closed-loop에서 **양성**(개선 방향, deterministic이라 노이즈 아님). 다만 **modest**.
이유: (a) urban green만 가격화(metering·freeway 미포함 — 큰 레버는 그쪽, P1이 metering으로 23% 회수),
(b) 3600s는 혼잡 onset이라 초반 gradient≈0(7200s 전체혼잡이면 더 클 여지), (c) green misranking의
per-step 비용 자체가 작음(probe: step20 C 3.5 veh·h). **가치는 구조적** — leader만 계산 가능한 per-signal
marginal externality price가 실제 closed-loop 조정을 제공함을 end-to-end 입증(PFO는 원리적으로 불가).

## 5. TODO
- [x] Step A oracle probe → **음성 확정**(s_eff 채널 non-binding, 정보로는 조정 불가).
- [x] Step B1 marginal-price probe → **가격 채널 양성**(ext 9/15, w=1), externality≫full, P1 이중가격 처방 확증.
- [x] **Step B2 구현·검증** → probe 앵커·PFO 비트동일 PASS, closed-loop sweet_190 3600s −0.76%(modest, deterministic).
- [ ] **B3(큰 레버)**: 같은 marginal-price 메커니즘을 metering/VSL로 확장 — P1의 손코딩 blocked_q를 정확한 per-actuator externality price로 대체(metering이 23% 레버였음 → 큰 이득 여지).
- [ ] sweet_190 7200s On/Off(전체혼잡서 green-price 효과 확대 여부).
- [ ] 3점 사다리(P1 leader 게이트) + N_UF cap + P1.5 중부하 재검토.
- [ ] ~~Step B marginal-price probe~~ (완료, 위)
- [ ] (구 항목) leader 전역 rollout으로 각 신호 green의 marginal 전역 TTT 민감도
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

---

# 이하 Claude 세션 (2026-07-03 후반) — Step B2 구현 + 사다리 + N_UF cap + P1.5 재검토

## 7. Step B2 구현 완료 (§4f 설계대로, TODO 1번)

- **follower** (`wu_faithful_follower.py`): `signal_marginal_price`(Optional[Dict], None=완전 휴면·
  비트 동일)/`signal_marginal_price_ref`/`_weight` 신설. `_solve_urban_agent_local` 후보 루프의
  smoothness 뒤에 `+ w·g_ext_i·(p1 − p1_ref_i)` 선형 가격항(B1 검증 형태 그대로). 외부 채점용
  `candidates_override` 인자와, leader가 d_local 유한차분에 쓰는 `local_green_costs()`(프롤로그 1회
  구성 + 단일후보 채점, **가격항 일시 비활성** — g_ext가 자기 가격을 다시 빼는 순환 방지) 추가.
- **controller** (`stackelberg_wu_metered.py`): `decide_with_info` 훅에서 refresh 판정 →
  `_maybe_refresh_signal_prices`가 per-signal 중심차분(δ=6.0, B1과 동일)으로
  `g_ext_i = d(전역TTT)/dp1 − d(local)/dp1` 계산. 전역항은 `_predict` 재사용(ego green만 p1±δ,
  나머지는 previous를 horizon hold — closed-loop라 미래 legacy trace 대신). **refresh 트리거** =
  최초 ∨ `leader_global_refresh` cadence ∨ event-trigger(운영점 p1이 기준점에서 ≥3s 이동 시
  재선형화 = §4e non-monotone 처방). 사이엔 hold. 비용 실측 ~3.8s/refresh(솔브 ~90s 대비 미미).
- **게이트**: 순수 PFO 러너는 가격을 설정할 수 없음(leader 전용 채널 유지). P-Stack 내부의 PFO
  incumbent solve도 가격을 봄 → tie-break이 incumbent를 골라도 가격이 plant에 도달한다.
- 진단: `wu_b2_price_{sig}`/`_ref_{sig}`/`_refreshed`/`_refresh_count`(runner decision_diagnostics로 수집).
- 테스트: `src/tests/test_signal_marginal_price.py` 5건(0가격=비트동일, 부호가 argmin을 밈,
  local_green_costs 가격 무시+복원, refresh/hold/event-trigger, disable 게이트) + 기존 회귀 전부 PASS.

## 8. 3점 사다리 결과 (sweet_190) — **leader 순수 가치(2→3) 첫 양수**

3600s (`outputs/_b2_ladder_sweet190_3600/`, 요약 `results/b2_impl/`):

| rung | controller | total TTT | 격차 |
|---|---|---:|---|
| — | NO-CONTROL | 5240.041 | |
| 1 | PFO 순수 (P1 OFF, `WU-FAITHFUL-FOLLOWER-NOP1`) | 3176.156 | |
| 2 | PFO + tax (P1 ON) | 3063.715 | 1→2 = **−3.54%** (가격[ii] 가치; §1의 −3.5% 재현=회귀 무결성) |
| 3 | P-Stack (leader + marginal price, B2) | **2999.663** | 2→3 = **−2.09%** (leader[iii] 순수 가치) |
| A/B | P-Stack B2 OFF (구 P-Stack) | 3055.811 | B2 단독 −1.84% |

- §4d의 우려(2→3 음수 = leader가 순수 가격보다 못함)가 **해소**: NOB2(3055.8)는 PFO(3063.7)와
  사실상 동률 — 잔여 leader 가치 ~0 — 인데 B2가 −2.09%를 만든다. 개선은 전부 가격 채널.
- B2 refresh 18/20 step(event-trigger 실작동: 운영점이 매 step 3s 이상 이동).

7200s **완전 사다리** (`outputs/_b2_sweet190_7200/`, `_b2_ladder_sweet190_7200/`; 로컬 재측정 —
§2의 Codex 수치와 PFO −0.37%/구 P-Stack −1.2% 차, 크로스머신 부동소수로 판단. legacy는 §4c에서
이 머신 정확 재현이므로 이하 전부 로컬 기준):

| rung | controller | total TTT | vs no-control | legacy 격차 |
|---|---|---:|---:|---:|
| — | NO-CONTROL | 25170.572 | — | |
| 1 | PFO 순수 (P1 OFF) | 13627.344 | 45.86% | −2898.6 |
| 2 | PFO + P1 | 12885.668 | 48.81% | −2156.9 |
| A/B | P-Stack B2 OFF | 12846.631 | 48.96% | −2117.9 |
| 3 | **P-Stack B2** | **12409.520** | **50.70%** | **−1680.8** |
| 기준 | legacy P-Stack | 10728.763 | 57.38% | — |

- 1→2 P1 가격 가치 **−5.44%**(3600s −3.54% → 지평 비례 확대, §2 관찰 재확인).
- 2→3 leader 순수 가치 **−3.70%** — 7200s에서도 양수. **B2 단독(NOB2→3) −3.40%**로 3600s
  (−1.84%)의 ~2배 — B2도 P1처럼 지평에 비례하는 구조적 개선(transient 아님).
- NOB2 ≈ PFO+P1(−0.30%): 가격 없는 leader의 잔여 가치는 장기 지평에서도 사실상 0.
- 격차 서사: 순수 Nash(1)↔legacy 2898.6 중 가격 채널 둘(P1 741.7 + B2 437.1)이 **41%를 닫음**.
  잔여 1680.8(58%)이 가격 이외의 몫(§11 다음 방향).

## 9. N_UF 등식→cap (TODO 5번) — 구현 완료, **기본은 equality 유지 결정**

- 구현: `mpc.wu_faithful_nuf_coordination_mode: equality|cap`(기본 equality=기존 거동).
  cap = 자율 metering 좌표하강(PFO 분기와 동일 후보)을 돌리되 모든 후보를 link 합 ≤ budget으로
  비례 투영 — 자율이 budget보다 덜 흘리면 leader가 안 덮어씀. `src/tests/test_nuf_cap_mode.py` 2건.
- 3600s A/B (모두 B2 ON):

| 구성 | equality | cap | Δ |
|---|---:|---:|---|
| standalone sweet_190 | 4229.831 | **4092.995** | **−3.24%** |
| anchor-on bal_med | 926.689 | 926.689 | 0 (committed control 동일) |
| anchor-on sweet_190 (헤드라인) | **2999.663** | 3074.194 | **+2.48% 악화** |

- **결론: cap의 가치는 leader 품질에 반비례.** leader가 나쁜 standalone에선 등식 budget이 자율
  metering을 덮어쓰는 손해를 cap이 처방하지만, B2로 leader가 좋아진 anchor-on에선 등식 budget이
  생산적이라 cap이 손해. §2의 standalone 악화 진단은 맞았으나 처방은 "cap 전환"이 아니라
  "leader를 고쳐라(B2)"였던 것. cap은 standalone-류 구성 opt-in으로 보존. (cap 모드 solve
  +20~35% 느림: 투영 후보의 중복 skip이 덜 걸림.)

## 10. P1.5 중부하 조건부 활성화 (TODO 7번) — **음성(포화도로 분리 불가), 기본 OFF 유지**

- 계측 인프라: step당 1회 ramp 신호별 phase 포화도
  `x = max_p (q0_p/horizon_h + arr_p)/(Σ cap_flow·g_p/total)` 계산(`wu_p15_sat_{sig}` 진단,
  계측 전용 모드 = band 불발 시 비트 동일). 3600s PFO 계측(`results/b2_impl/p15_sat_*.csv`):

| 시나리오 (P1.5 상시효과) | D 대역 | F 대역 |
|---|---|---|
| sweet_128 (+0.94%) | 0.68–0.96 미포화 | 0.95–1.37 |
| sweet_155 (−1.47%) | 0.83–1.69 | 1.0–2.1 |
| sweet_190 (+1.09%) | 1.0→**2.6–4.3** 과포화 | 1.1–3.2 |

- AND-게이트(모든 ramp 신호 x∈[1.0, 2.2)일 때만 활성, `ramp_aware_phase_auto`) 3600s A/B:
  sweet_128 **−0.19%**(악화 제거), sweet_155 **−0.52%**(이득 1/3 보존), sweet_190 **+1.09%
  그대로**(활성 7/20 초반 step에서 해악 전부 발생 — STOP 기준 여전히 위반).
- **기각 근거**: sweet_190 초반(해악 구간)의 x 1.0–2.0이 sweet_155 이득 대역과 정확히 겹침 —
  포화도는 필요조건일 수 있으나 판별자가 아니다. 게이트/계측 인프라는 유지(기본 OFF),
  향후 판별자는 다른 축(큐 증가율·freeway 여유 등) 필요. `src/tests/test_p15_auto_gate.py` 2건.

## 11. TODO 갱신 + 프로세스 기록

- [x] Step B2 구현 + closed-loop (§7–8). **다음 개선 여지**: w 스윕/신호별 w≠1, refresh threshold
  튜닝, N_P/N_UF 스칼라의 가격벡터 통합(§4f 마지막 항 — 미착수).
- [x] 3점 사다리 (§8). 7200s에서 legacy 격차 1680.8 잔존 — 남은 재료는 leader 조정(iii) 심화
  (offset 등 legacy 운영점의 coordinated 레버, §8에서 가격만으로는 닫히지 않은 몫).
- [x] N_UF 등식→cap (§9) — 기본 equality 유지, cap은 opt-in.
- [x] P1.5 조건부 (§10) — 음성 확정, 기본 OFF.
- **프로세스 사고 1건**: 러너(run_claude_style_five_controller)는 **컨트롤러마다 default.yaml을
  디스크에서 재로드**한다 — 백그라운드 런 중 yaml에 새 키를 추가하면 (구버전 state.py를 로드한)
  실행 중 프로세스가 `MPCConfig.__init__() got an unexpected keyword` 로 죽는다. 실제 첫 사다리
  런이 이걸로 크래시(완료분 NO-CONTROL/rung1은 유효, 나머지 재실행). **런 중 config/yaml 편집 금지.**
- 러너 변형 ID 추가: `WU-FAITHFUL-FOLLOWER-NOP1`/`-P15SAT`/`-P15AUTO`,
  `P-STACK-WU-FAITHFUL-NOB2`/`-NUFCAP`/`-STANDALONE`/`-STANDALONE-NUFCAP`.

## 12. B2 병렬 구현 충돌 해소 — 같은 머신 A/B로 signal_marginal_price 채택

Codex도 B2를 독자 구현해 푸시(eed5c51, §4g: `green_price` — 매 decide 재계산, g_i 하달·follower가
d_local 차감, leader-present 게이트). 이쪽 구현(31173ea: `signal_marginal_price` — g_ext 하달,
refresh hold+event-trigger, P-Stack 내부 전체 가격화)과 분기 → **같은 머신·같은 기준 A/B**로 판정
(worktree `Numerical-Sim-codex-b2`에서 eed5c51 그대로 실행):

| 구현 | sweet_190 3600s | B2 OFF(3055.811) 대비 |
|---|---:|---:|
| Codex eed5c51 (`green_price`) | 3056.758 | **+0.03% (효과 소멸)** |
| 이쪽 31173ea (`signal_marginal_price`) | **2999.663** | **−1.84%** |

- eed5c51의 자기머신 −0.76%(OFF 3075.5 대비)는 이 머신에서 재현 안 됨(닫힌루프 FP 궤적 민감성 —
  같은 이유로 이쪽 수치도 타 머신 재검이 바람직). 유력한 기전 차이: eed5c51은 g_i를 직전 commit
  운영점에서, d_local을 Jacobi 라운드마다 움직이는 snapshot green에서 각각 평가해 **서로 다른
  점의 기울기를 혼합**(g_ext = g_i(A) − d_local(B)); 이쪽은 두 항을 같은 동결 운영점에서 계산.
- 참고: 양쪽 다 incumbent 선택 0/20(sweet_190은 leader 후보가 원래 tie-break을 뚫음) → 게이트
  차이는 이 시나리오에선 무관. B2 ON이면 leader 후보가 매 step 승리하는 것도 동일.
- **병합 해소**: src 두 파일은 31173ea 버전 채택, eed5c51의 probe 앵커 테스트 2건은
  `signal_marginal_price` API로 포팅해 보존(probe JSON은 커밋 사본 fallback; legacy trace 있는
  머신에서 실행됨). eed5c51의 §4g·modified_code 사본은 기록으로 유지.
- **후속 확인 필요**: (a) 이쪽 B2의 sweet_128/155 교차검증(현재 sweet_190만 측정),
  (b) Codex 머신에서 31173ea 재측정(크로스머신 재현성).

### 12b. 교차검증 (a) 결과 — B2는 regime-의존, **STOP 관례로 기본 OFF(opt-in) 전환**

3600s B2 ON/OFF A/B (`outputs/_b2_ab_sweet{128,155}_3600/`):

| 시나리오 | B2 OFF | B2 ON | Δ |
|---|---:|---:|---:|
| sweet_128 (경부하) | 742.210 | 744.890 | +0.36% |
| sweet_155 (중부하) | 1390.659 | 1413.719 | **+1.66%** |
| sweet_190 (고부하) | 3055.811 | **2999.663** | **−1.84%** |
| sweet_190 7200s | 12846.631 | **12409.520** | **−3.40%** |

- sweet_155 +1.66%는 P1.5를 내렸던 STOP 기준(>1% 악화)을 위반 → 같은 관례로
  `signal_price_enabled` **기본 False**, 러너 opt-in `P-STACK-WU-FAITHFUL-B2` 신설
  (`-NOB2`는 재현용 별칭으로 유지). §8의 사다리 headline은 opt-in 구성 기준으로 읽을 것.
- 판별자 후보 기각 2건: 가격 크기(155 max|g_ext| 0.07–0.50 vs 190 0.10–1.79 — 대역 겹침),
  refresh 빈도(155도 14/20으로 정상 발화). P1.5의 포화도 게이트 실패와 같은 패턴 —
  regime 판별자는 미해결 공통 문제.
- **다음 조사(B2.1)**: 중부하에서 가격이 해로운 기전 — 유력 가설은 (i) 중부하 truth 곡선의
  non-monotone/flat 구간(B1 step35 군집과 동일 병리)에서 1차 가격이 잘못된 방향 지시,
  (ii) horizon 3 rollout의 gradient가 중부하 transient에 민감. w<1 스윕·신호별 deadband·
  가격 신뢰구간(±δ 재평가 잔차) 게이트가 후보 처방.
