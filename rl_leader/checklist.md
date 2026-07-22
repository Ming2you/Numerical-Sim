# RL Leader — Checklist

**목표**: P-Stack의 리더 온라인 탐색을 RL 정책으로 대체. RL은 저차원 **(budget + 볼록 price)**만 출력하고, principled follower가 detailed control을 실행(feasibility·안전 보장). 학습 신호 = episodic TTT.

**주장 3개 (분리해서 검증)**
- (1) 계산 승: RL leader = O(1) inference (온라인 탐색 제거). *[확실]*
- (2) near-optimal: RL ≈ optimizer-leader P-Stack (조정 상한 도달). *[BC로 거의 보장]*
- (3) 장기지평 승: 회복중심 시나리오서 episodic RL > myopic optimizer. *[검증 대상]*

---

## Phase 0 — Env 래퍼
- [x] Gym형 `RLLeaderEnv` (`rl_leader/env.py`): reset/step/observe, action=[-1,1]²→budget box
- [x] follower = `StackelbergWuMeteredController.nash_solver` 재사용
- [x] reward = −Δ(step TTT), Wang 물리, warmup no-control
- [x] smoke: 랜덤정책 5스텝 굴러감 (검증 게이트 통과)
- [ ] obs 정규화 상수 점검(러너 스케일과 일치), obs_dim 확정
- [ ] episode 완주(80스텝) + optimizer-leader와 동일 시나리오 TTT 대조(환경 충실성 확인)

## Phase 1 — BC 사전학습
- [ ] optimizer-leader 결정 로그 수집: (state, N_P*, N_UF*, λ) — 다양한 시나리오서 P-Stack 실행
- [ ] state 추출을 env._observe와 동일 정의로 정렬
- [ ] BC 정책(MLP) 학습 → 검증: BC정책 closed-loop TTT ≈ optimizer TTT (±few%)

## Phase 2 — SAC 미세조정 (선형가격/budget만)
- [ ] SAC 구현/연결(off-policy, replay), BC 가중치로 init
- [ ] reward=−ΔTTT, γ=0.99, 다중시드
- [ ] 검증: 학습셋서 optimizer 매치/초과, 파국 없음

## Phase 3 — 볼록 price 액션 추가
- [ ] action에 (λ_c, ρ_c≥0) 추가(softplus), follower가 볼록 penalty 반응하도록 배선
- [ ] 검증: 선형 vs 볼록 price ablation — 볼록 이득(전역, incident 특효 아님)

## Phase 4 — Domain randomization + 일반화
- [ ] 에피소드마다 수요레벨(연속)/skew/incident(위치·길이·강도)/노이즈 랜덤
- [ ] held-out 시나리오 평가 → 교수 "특정상황만 강건" 반박

## Phase 5 — 장기지평 승 검증
- [ ] 회복중심 시나리오(긴 cooldown) 구성
- [ ] episodic RL vs myopic optimizer 대조 → (3) 주장 확정 여부

## 평가·집필
- [ ] baselines: optimizer-leader(상한), Wu, PFO, Centralized, NC
- [ ] ablation: 선형 vs 볼록 price / BC vs 스크래치 / shaping on-off
- [ ] 다중시드 mean±std, 계산비용 표(inference O(1)), 스케일링 그림 갱신
