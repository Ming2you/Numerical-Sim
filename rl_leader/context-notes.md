# RL Leader — Context Notes (결정과 근거)

세션 인계용. 각 결정의 **왜**를 기록. 이 프로젝트 고유 findings에 근거함.

## 아키텍처 결정
- **RL은 리더(조정)만, 실행은 optimizer follower.** manager(학습)–worker(고정·안전) 하이브리드.
  - **왜**: 리더 탐색이 P-Stack의 비용·병목(계산 스케일링 그림 참조). follower는 싸고 로컬. RL을 저차원 조정에만 쓰면 tractable하고, follower가 제약·feasibility를 지켜 교통 RL 최대 약점(안전)을 구조로 회피.
- **액션 저차원 유지** (budget 2 + 볼록 price (λ,ρ) 소수). NN 가격/전액추에이터 end-to-end 금지.
  - **왜**: P-Stack의 "구조적 차원 축소"를 RL 친화적으로 재활용. 고차원 RL은 불안정.

## price 함수형 = 볼록(1차 아님), 단 incident 특효 아님
- **곡률 진단 (2026-07-22)** 결과: J(N_UF)를 1차 vs 2차 적합 → **nonlinearity ~0.32 (R²l~0.6→R²q~0.9)로 선형 부족·볼록이 맞음.** 
- **그러나 incident 폐쇄구간(0.331) ≈ 그 외(0.325) ≈ 170(0.325)** — 곡률이 **어디서나 비슷**, 클리프 특화 아님. follower 응답의 일반적 diminishing returns.
- **⚠️ 함의**: 볼록 price는 "**전역 정확도 개선**"으로 팔 것. "incident 특효"로 팔면 **데이터가 기각**함. (curv 프로브 첫 2회는 표본협소·feasible 밖 clamp로 오염 → dedup 후 위 결론이 진짜.)
- **왜 (λ,ρ≥0)**: augmented-Lagrangian형 = 선형 dual의 자연스러운 일반화, follower 볼록 유지, "체증 한계비용" 해석 보존.

## 보상 = dense −ΔTTT, γ≈0.99 (+옵션 shaping)
- **왜**: 리더 액션의 진짜 비용은 **회복기(2.5h 뒤)**에 나타남 — SLSQP가 3-step 지평서 못 본 바로 그 문제(myopic MPC 지평은 회복 실패 못 봄, whole-sim 3배 파국으로 실증). RL episodic return이 그걸 bootstrap → 잠재적 성능 승. shaping(스텝말 잔여큐/ρ>ρc 벌점)은 credit assignment 가속용, ablate.

## 학습 = BC warm-start → SAC (이 프로젝트 최대 강점)
- **왜 BC**: optimizer-leader가 매 스텝 (state→최적 budget/λ)를 산출 → **teacher 데이터가 이미 있음.** 대부분 교통 RL엔 없는 강한 teacher. 스크래치 학습 리스크 제거. ρ(곡률)만 teacher에 없어 0(=선형)서 시작하거나 2차 FD로 seed.
- **왜 SAC**: env step이 비쌈(follower 응답). off-policy replay가 표본효율적.

## 강건성 (교수 지적 "특정상황만 강건")
- domain randomization(수요·skew·incident·노이즈) + **held-out 평가**. RL은 과적합 쉬우므로 필수.

## 코드 인터페이스 (env.py가 의존)
- cfg: `ExperimentConfig.from_file(default.yaml)` + `apply_scenario_network_overrides` + Wang 물리(v115/ρc31.5/τ.0056111/ν22.5/κ10/δ0.9) + FW_BUFFER=8 + TERM_ZG.
- follower: `StackelbergWuMeteredController(cfg).nash_solver.solve(state, LeaderAction(N_P,N_UF), forecast, previous).control`.
- 전진: `log = sim.step(control, forecast[0], step)`, reward=−(log.urban_ttt+log.freeway_ttt), 누적 `sim.total/urban/freeway_ttt`.
- forecast: `DemandProfile(cfg, scenario).horizon(t, K)`.
- **Phase 0 단순화**: budget만(price/far/closure 처리 생략) — nash_solver.solve 원 control 사용. 충실판은 `_evaluate_full_candidate` 경유(closure·far 포함)로 Phase 3에서.

## 환경 제약 (중요)
- **torch·sklearn 둘 다 없음**(codex-runtime python). Phase 1 BC는 **순수 numpy MLP**로 구현(`bc_train.py`).
- **Phase 2 SAC는 torch 필요** → 별도 셋업(pip install torch, 또는 numpy로 SAC 구현은 큰 비용). RL 학습 본격화 전 결정 필요.
- teacher decide ~36s/스텝 → BC 데이터 수집이 비쌈(시나리오당 ~45–90분). 다양성 위해 여러 시나리오 필요하니 밤샘 배치 고려.

## 미해결/주의
- env._observe 정규화 상수는 임시(1000/100 등) — Phase 1 전 러너 스케일과 정렬 필요.
- np/nuf action bound (0~400 / 0~8000)는 잠정 — feasible box 실측으로 조정.
- follower.solve가 leader price를 어떻게 받는지(Phase 3): StackelbergWuMetered의 signal/metering_price 경로 확인 필요.
