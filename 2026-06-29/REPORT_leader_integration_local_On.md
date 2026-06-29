# [리포트] Wu 충실 follower — leader 통합 + 완전 O(n) 분해 (#1·#2·#3)

2026-06-29. 코더↔검토 서브에이전트 루프로 세 작업을 무에러까지 수행, 전부 검토 PASS.
모든 변경은 **새 파일 + 새-세션 파일(`wu_faithful_follower.py`)에만**, 기존 코드 미변경.

## 배경
직전 마일스톤(commit f329696): Wu 충실 per-signal 국소 follower + freeway **ramp metering** →
sweet_128 T=3600 **−1.19% → +56.63%**(분해손실 27%p 해결). 단 (a) freeway는 아직 whole-rollout,
(b) leader의 N_UF는 풀-탐색+soft 페널티(이중작업), (c) leader의 N_P는 고정 페널티라 follower가
target을 못 따라감(최초 Fig 3A 문제). 이번에 이 셋을 사용자 지적대로 수정.

## #1 — freeway도 per-link 국소 rollout
- 신규 `src/controllers/local_freeway_plant.py`(`freeway_substep_local`): 자기 freeway link 세그먼트만
  METANET 전진. **발견: `freeway_substep`은 link 간 결합이 없음**(상류경계=v_free 상수, 하류=자기) →
  whole-freeway 비용은 순전히 루프 오버헤드. per-link stepper가 실제 plant와 **bit-exact**(1-substep
  Δρ=Δv=0, free-flow·near-jam·capacity-drop 분기 모두 검증).
- `wu_faithful_follower.py`: `_solve_freeway_agent_local`로 교체(VSL·metering 탐색은 per-link plant 채점).
- **결과**: sweet_128 +56.63%(무회귀), **solve 8s → 1.5s(5×)**. per-link locality 증명(타 link jam해도 목적 불변).

## #2 — leader N_UF = 예산(budget), metering을 simplex 배분
- N_UF_star = urban→freeway 총 교환차량 target. metering 풀-그리드(5⁴) 대신 **{owned ramp 합 = ω_F·N_UF}
  simplex 배분**만 탐색(2 ramp이면 1-D 7점). soft 페널티 제거.
- **결과**: leader present시 committed Σmetering == ω_F·N_UF **정확 실현**(N_UF=2000/4000/6000 검증).
  PFO(leader=None) 자율 metering 경로 불변 → +56.63%. 탐색 9→≤7 probe.

## #3 — leader N_P = net-inflow target, dual 분해로 추적 (핵심)
- 최초 문제(follower가 leader target 못 따라감)의 원인 = **고정 가중치 페널티**. 이를 **적응 가격 λ
  (Lagrange multiplier, dual 분해)** 로 교체: 각 urban agent 비용에 `+λ·nin_i`(가격×자기 net-inflow).
- 직접 λ-sweep으로 확인: Σnin(λ)은 **단조 비증가·조각상수**(이산 green), 임계 λ≈1, 가용범위 내에서만
  감소. 그래서 gain-정규화 subgradient는 부적합(측정 gain≈0) → **bisection**(`_bisect_lambda_for_np`)으로
  교체: Jacobi 결합 수렴 후 λ를 [0,λ_max] 이분탐색해 Σnin≈N_P, 최종 sweep으로 commit. slack(N_P≥자연)→λ=0,
  infeasible(N_P<floor)→λ_max clamp.
- **결과(검토자 독립재현)**: realized Σnin이 **N_P target을 따라 내려가다 floor에서 clamp, λ 상승**.
  고정값 flat이던 게 해결됨. PFO +56.63% 무회귀.
- 부수: leader 통합 래퍼 `src/controllers/stackelberg_wu_metered.py`, 러너 `2026-06-28/run_leader_wu_metered.py`.

## 검증(전부 PASS)
- #1: bit-exact, +56.63%, 1.5s, per-link locality. #2: 예산 정확실현, PFO 무회귀. #3: N_P 추적+clamp,
  bisection 정확(slack/infeasible/final-commit), PFO 무회귀, 국소·비용 bounded.
- 회귀: sweet_170 +39.61%, sweet_190 +32.92%(모든 단계 동일). 기존파일 미변경 확인.

## 알려진 한계 / 다음
- dead code: `_measure_dual_gain`/`dual_step_c` 잔존(무해, 정리 가능).
- **N_P 추적은 단일-state 검증**; live leader가 N_P를 구동하는 **closed-loop TTT 영향은 미측정**.
- 직전 leader 가치 테스트(−0.30pp)는 N_P 추적이 깨진 상태였음. **이제 perimeter가 작동하니, 고부하
  (sweet_220+) 과포화에서 leader perimeter 가치 재측정**이 다음 단계(사용자 가설).
- leader-coupled run은 bilevel(연속 탐색 × follower)이라 느림(48s→#1·#2로 단축 여지). #1·#2가 follower를
  싸게 만들어 leader도 빨라짐.
