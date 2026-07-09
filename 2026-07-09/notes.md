# 2026-07-09 작업 노트 — Joint bilinear cross-term 가격

## 무엇을 / 왜

per-lever 선형가격(`own_TTS(a) + w·g_a·(a−a_ref)`)이 못 담는 **lever쌍 교차곡률**
∂²(TTT+V)/∂a∂b를 bilinear cross-term 가격으로 하달하고, follower가 해당 쌍을 2D 공동탐색.
사용자 결정("신규 bilinear 가격 대공사"). 두 쌍:
- **green×offset**(도시 신호쌍, non-ramp): 현재 coordinate descent(green은 offset 동결
  1D, offset은 green 동결 1D)라 cross가 퇴화 → 진짜 gap. follower를 2D 공동탐색으로 전환.
- **vsl×metering**(freeway 합류쌍): primal joint은 follower가 이미 포착
  (metering 후보마다 VSL best-response) → 탐색 구조 불변, cross 가격만 추가.

cross 규약은 per-lever와 동일한 externality 차감: `h_ext = h_global − h_local`(4-corner
스텐실). 가격 rollout은 기존 per-lever와 동일하게 `_predict`(leader_value_depth로 3+d 깊이,
analytic far 미포함) TTT 사용.

## 변경 파일
- `src/controllers/wu_faithful_follower.py`: cross 속성 + `_solve_urban_agent_joint`(2D
  공동탐색) + orchestration 배선 + `local_green_offset_costs`/`local_vsl_meter_costs` probe
  + `_solve_freeway_agent_local`에 `vsl_override` param & vsl×metering cross항.
- `src/controllers/f1_wu_faithful_follower.py`: F1 override에도 `vsl_override` + cross항.
- `src/controllers/stackelberg_wu_metered.py`: gate 플래그 2종 + `_global_rollout_ttt_with_
  green_offset`/`_global_rollout_ttt_with_vsl_meter` + 두 cross-price 계산 블록.
- `work/run_claude_style_five_controller.py`: `P-STACK-WU-FAITHFUL-ALLPRICE-JOINT`.
- `src/tests/test_joint_cross_price.py`: 신규 4테스트.

## 검증
- 전체 단위테스트 회귀 0: before/after 실패목록 완전 동일(14건, 전부 기존 Wu 작업 진행중
  실패 — metanet/constraints/forecast/post_analysis/six_controller). 내 변경 회귀 없음.
- 신규 4테스트 통과: defaults dormant, green×offset probe=offset probe 일관성, vsl_override
  유한, controller refresh가 non-ramp 신호·ramp에 cross 하달(유한).
- 스모크(sweet_190 4스텝, d3+far): green×offset cross A/B/C 모두 nonzero, vsl×metering
  cross 초기 저부하라 0(metering/vsl ±δ 밀도무변 → externality 0, 피크서 nonzero 가능),
  joint 탐색 정상 작동.

## 비교 baseline (sweet_190 7200s, +far)
| controller | d3 | d4 |
|---|---:|---:|
| G1DF (green price만) +far | 11283 | **11230** |
| ALLPRICE per-lever +far | 12279 | 12036 |
| **ALLPRICE-JOINT +far** | (실행중 bxhhvh0x3) | (실행중 bt3mzb3re) |
| legacy(ceiling) | — | 10729 |

관전: per-lever ALLPRICE(전방위 가격)는 green-only G1DF보다 일관되게 나쁨. joint cross가
그 손해를 회복하는지가 핵심 판정.

## E1+E2 (bda8b49) — 사용자 지시: "price에 far도 모두, own TTT는 빼서 externality만"

진단(사용자 질문 "freeway는 externality 고려 terminal cost 넣었는데도 나빠지냐"에 대한 답):
far는 leader **후보 채점에만** 있었고 follower에 하달되는 **가격 rollout엔 없었다** —
"far는 수량 신호(N_UF_star)만 똑똑하게 하고, G1DF는 수량(hard 예산)을 전송해 far를 100%
상속하는데, ALLPRICE는 gradient를 전송하고 gradient엔 far가 없다". 격차가 d6 no-far ~300
→ d3/d4+far ~1000으로 벌어진 것과 정합(가격이 보는 깊이는 줄고 예산 채널만 far 보상).

- **E1**: `price_far_enabled`(runner `MFD_FAR_PRICE=1`) — 모든 가격·cross rollout이
  `_price_ttt` = TTT + far(terminal state)로 채점. far는 leader 전용 항이라 d_local 차감
  없음(B4 barrier와 동일 규약). 기본 OFF=비트동일.
- **E2**: VSL 가격 g_ext화 — `local_vsl_costs`(vsl_override 고정벡터 own-TTS probe)로
  d_local을 차감. 기존 raw g_i의 own 성분 이중계상 결함(코드에 "선행 과제"로 명시돼
  있었음) 해소. vsl_price_enabled 자체가 기본 OFF라 기본 비트동일.
- E3(barrier)는 사용자 질문으로 정리: leader payoff 항이 아니라 **가격에 합산되는 hinge
  gradient 채널**(이미 구현, ALLPRICE 미사용). E1과 철학 동일(leader 전용 항의 gradient를
  가격에). 선택지로 보류.
- 검증: 신규 2테스트(E1 가산 확인, E2 유한·키 정합) + 가격채널/follower 회귀 30/30.

## 결과 (sweet_190 7200s, leader far ON)

| 구성 | d3 | d4 |
|---|---:|---:|
| G1DF (수량 equality) | 11283 | **11230** |
| ALLPRICE per-lever (raw VSL, far-in-price 없음) | 12279 | 12036 |
| ALLPRICE-JOINT (cross 추가, E1/E2 없음) | 11854 | 11879 |
| ALLPRICE per-lever + E1E2 (dual 없음) | — | **12376(악화!)** |
| legacy | — | 10729 |

판정 중간값.
- joint cross 실효: per-lever 대비 d3 −425, d4 −157 회복. 그러나 G1DF에 아직 뒤짐.
- E1E2 단독(수량 가드 없는 far-in-price): 12036→12376 **악화**. far가 gradient를 방류로
  세게 밀지만 선형 가격이라 절벽 가드 부재 → 사용자 지시의 N_UF dual(수량 적분 피드백)이
  정확히 이 빠진 조각이라는 가설과 정합.

## 표준 구성 전환 (2026-07-09, 사용자 지시)

"terminal cost(urban+freeway far) 기본 + price에 far 포함 + N_UF dual"을 **디폴트**로.
- state.py: `leader_mfd_far_enabled: bool = True`(정식 필드 선언), `leader_mfd_far_weight=1.0`,
  `wu_faithful_nuf_coordination_mode = "dual"`.
- default.yaml: `wu_faithful_nuf_coordination_mode: dual`.
- stackelberg_wu_metered: `price_far_enabled = True` 기본.
- **DUAL×PRICE 결합(신규)**: 가격 분기(`_price_metering_cost`)에서 dual 모드면 soft
  anchor(|Σ−budget|, w≈0.05, 사실상 무력) 대신 **λ_UF·Σmeter** — ALLPRICE 계열에서도
  leader의 수량 target을 λ_UF(적분 피드백)로 추적. λ_UF commit 경로는 기존(1398-1401).
- 스모크: far가 가격에 들어가자 **vm_cross(vsl×metering)가 nonzero로 살아남**(이전 0) —
  ramp 큐 배수 효과가 gradient에 잡히기 시작.
- 검증: 타깃 회귀 41/41(E1 테스트만 새 기본값 반영해 OFF 기준선 명시로 수정).

## PRICE-TR (f940d02, 사용자 지시)

"1차식 가격이면 smoothness(마찰) 빼고 trust boundary로 제약" — SLP/Frank-Wolfe 표준형.
- 실측 근거: green g_ext 0.03~0.055 < smooth_w 0.1 → **가격 신호가 마찰 deadband에
  검열**되고 있었음(테스트 입증: 1e6 마찰에서도 PRICE-TR ON이면 가격이 green을 움직임).
- 가격 활성 레버만 smoothness=0(자기게이트 — PFO/무가격 레버는 마찰 유지).
- VSL trust ±10km/h 신설(`vsl_price_trust_kmh`, 기존엔 smoothness가 유일 damper).
- 레거시 앵커 테스트 2건(0가격≡None, B2 probe 앵커)은 flag OFF로 옛 의미론 고정.

## 실행 중 런 매트릭스 (전부 d3, far+pricefar+dual 디폴트)
| run | smoothness | 목적 |
|---|---|---|
| G1DF (btqteov88) | ON(마찰) | dual 전환 효과 vs 11283(equality) |
| APJOINT (b6w0cc24n) | ON(마찰) | cross+E1E2+dual vs 11854(cross만) |
| G1DF (b5sjjfsfu) | **OFF(PRICE-TR)** | 마찰 검열 해제 효과 |
| APJOINT (bwwseo6gc) | **OFF(PRICE-TR)** | 풀스택(사용자 표준 구성) |

## λ_UF BOOTSTRAP DEADLOCK 발견·수정 (641f0bf)

dual(마찰 ON) 결과: G1DF 11665(+382 vs equality 11283), APJOINT 12260(+406 vs 11854).
**원인은 dual 자체가 아니라 자기잠금**: λ=0 → dual 항 0 → leader 후보 ≈ PFO incumbent
→ tie-break가 incumbent 선택(31/40, tie 19) → incumbent 경로는 λ 미commit(9/40만)
→ λ 영영 0. APJOINT는 anchor를 λ로 대체했으므로 **수량 신호 전무** 상태로 퇴화.
수정: incumbent 선택 스텝에도 실현 Σmeter − leader-stage 최선 N_UF*로 λ 무조건 적분
(수량 오차는 커밋 주체 무관 관측되는 새 정보 — "λ는 새 정보 없다"던 기존 주석이
λ_UF에는 오류). 스모크: incumbent 스텝 bootstrap=1, 오차 0 구간 λ=0 유지(정상).

## bootstrap 결과 = WINDUP (2차 구조 결함, 2d067ce로 수정)

boot 런: G1DF 11909(+626 vs equality), APJOINT 13116(+1262). λ 궤적: 0→cap(1.0) 단조
windup, incumbent 전 스텝 선택, 실현 Σmeter는 λ 무반응. **원인: incumbent(PFO probe)가
λ-면제**(dual 항이 leader-게이트) → 적분 루프에 액추에이터 부재 → λ는 leader 후보만
오염(metering→0) → incumbent 고착 심화. 교훈: 가격 조정은 모든 경로가 같은 가격을
마주해야 한다(green/vsl 가격은 follower 속성이라 이미 그랬음 — λ만 예외였다).

수정(DUAL-STANDING): λ≠0이면 leader 부재 solve에도 dual 적용(영속 가격 규약).
검증: leader=None, λ=0.5 → Σmeter 6000→1500(루프 닫힘); λ=0 → PFO 비트동일. 45/45.

## dual 시도의 누적 실측 (d3, sweet_190)
| 세대 | G1DF | APJOINT | 병리 |
|---|---:|---:|---|
| equality (기준) | **11283** | 11854(cross) | — |
| dual v1 | 11665 | 12260 | bootstrap deadlock(λ 영영 0) |
| dual v2 (+bootstrap) | 11909 | 13116 | windup(λ→cap, incumbent λ-면제) |
| dual v3 (+standing) | 실행중(ba5rp8sew) | 실행중(b1z9e7h3y) | ← 첫 공정한 테스트 |

v3도 equality에 밀리면: 디폴트를 equality로 되돌리고 dual은 3단 병리(deadlock→windup→?)
와 함께 부정결과로 문서화하는 게 정직한 수순(Weitzman: 절벽 레버는 수량이 지배).

## v3 판정 = dual 최종 부정결과, equality 복귀 (2f08e3b)

v3(dual-standing): G1DF 11866(+583), APJOINT 13184. **λ는 정상 작동**(G1DF: λ 0~0.037
오르내리며 Σmeter 6000→4575 실반응, windup 없음 — 공정 테스트 성립). 그래도 패배.
기계적 원인 확정: **leader target(N_UF*)이 매 스텝 이동**(6000→5550→5100→4800…)하는데
적분 dual은 저역통과 전송이라 항상 지연 — equality는 무지연. 논문 한 줄: "수량 도구 =
비정상 target의 무지연 전송, dual 가격 = 저역통과 — target이 빨리 움직이는 피크 과도기에
정확히 진다"(Weitzman 보강). APJOINT v3의 λ≈0(오차 부호 교대)이므로 13184의 참사는
dual이 아니라 **E1E2+PRICE-TR 스택**이 원인(11854 → 13116/13184 일관 악화).

디폴트 equality 복귀(사전등록 기준 이행). dual 코드는 NUFDUAL로 보존(3결함 수정 완료
상태 — deadlock/windup/standing 모두 해결된 "정상 작동 dual"로 문서화).

## 실행 중: equality 기반 ablation (d3)
- G1DF (b9zywwail): equality + far + pricefar(green) + PRICE-TR(green) — vs 11283.
  pricefar/PRICE-TR가 챔피언 위에서 득인지 실인지 격리.
- APJOINT (bz9hn2qzb): equality(soft anchor 복원) + cross + E1E2 + PRICE-TR — vs 11854.
  E1E2/PRICE-TR가 anchor 레짐에서도 해로운지 격리.

## 마찰/E1 디폴트 복귀 + DEFAULT P-STACK 지정 (사용자 결정)

ablation 판정 반영: 마찰 복원(deadband=암묵적 신호검정), E1 디폴트 OFF(far 증분의
저SNR — G1DF +139, APJOINT eq 13493). E2(VSL g_ext화)는 공식 교정이라 채널에 내장 유지.

**DEFAULT P-STACK = APJOINT + density link-share** (사용자 결정, 논문 정합성 기준):
전 lever 통일 marginal price(g_ext) + 2쌍 cross + N_UF equality anchor + headroom 비례
link 배분. 성능 챔피언은 G1DF(11283 d3)이며 ablation 상한으로 병기 — "통일 가격 체계
(주 구성) vs 최소 구성(성능 상한)"의 대비 자체가 조정 지도의 본문.

## 실행 중 (판정 대기)
- G1DF+E1(마찰 ON) d3 (b739car6z) vs 11283 — far 증분 순수 격리
- APJOINT+E1E2(마찰 ON) d3 (b8cbbog8d) vs E2-only — E1 효과
- APJOINT+E2(마찰 ON) d3 (bd72iimrg) vs 11854 — E2+trust 교정 효과
- G1DF density link-share d3 (b68c3rezt, 구 스택 베이스) vs 11422

## TODO
- [ ] 4런 판정 → APJOINT 교정판 최종 수치 확정
- [ ] 오늘 전체 서사 리포트 작성

---

# (별도 세션) Stage1 5×4 매트릭스 + incident 재모델 + VSL 발화 원리

## A. sweet_155_incident 재모델 — 본선 차로 폐쇄
- incident_capacity_factor(유입만 조임 → no-control 역설적 개선 8612→4823) 폐기,
  freeway_lane_closures로 FW_E seg3 1차로 2400~4800s 폐쇄. no-control 8612→10207(+1595) 스트레스 실재.

## B. Stage1 매트릭스 (docs/literature_grounded_post_analysis_plan §2.6/§15 규격)
- 산출: 2026-07-09/results/stage1_matrix/{stage1_summary,paired_comparisons}.csv,
  집계기 work/aggregate_stage1_matrix.py. exponential, 7200s, 동일머신.

| scenario | NO-CTRL | PFO | APJOINT(d3+far) | G1DF(d3+far) | LEGACY |
|---|---:|---:|---:|---:|---:|
| sweet_122 | 1434 | 1384 | 1357 | 1357 | 1331 |
| sweet_155 | 8612 | 4514 | 4385 | 4292 | 4052 |
| 155_incident | 10207 | 9169 | 9011 | 8962 | 8879 |
| sweet_190 | 25171 | 13627 | 12014 | 11283 | 10729 |

- 갭 회수율(vs PFO→legacy): APJOINT 28~56%, G1DF 48~81%. 전 시나리오 PFO<x<legacy 순위 보존.
- throughput/terminal 동반 개선(190: completed 29.7k→31.7k→32.4k→33.3k) — §2.6 규칙 충족.
- compute/step: PFO ~5s, G1DF 58~72s, APJOINT 72~79s, legacy 28~96s.
- ⚠ sweet_122 delay 음수(G1DF/APJOINT −2, legacy −27) — §2.6상 개선 주장 금지, 경부하 reference 간극.
- 타임시리즈: outputs/_4x3/, _apjoint/, _3way/, legacy_pstack_*/runs/ (fig2~5 소스 완비).

## C. 부속 발견
- WU-CD-F sweet_190=18618: no-control 대비 −26%(악화 아님), PFO 대비 +4990=권한 결핍(metering)의 값.
- VSL 발화 원리(ablation): 중간 밀도 band(임계초과~jam이전)서 국소 own-TTS capacity-drop 회피로
  자발 발화(hinge 무관·seg0 우선). jam선 cap 안 물려 무차별, 자유류선 순비용. incident서
  P-Stack/legacy 0%=metering이 band 아래로 눌러놔서.
- incident jam은 1스텝 내 완성(rho 29→85) → 반응형 VSL 불가. far는 경보 정확(ramp항 폭증)하나
  leader lever gradient 0 → action space 결함. 선제 VSL 검증은 far×VSL price 세션에 이관.
