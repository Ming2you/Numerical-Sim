# Session Handoff — 2026-06-23

이 세션에서 한 일과 현재 상태 요약(컨텍스트 압축용). 전부 push 완료(origin/main).

## 완료·커밋됨
1. **P-Stack 비용 절감**: grid `process` 병렬(thread는 GIL로 무효), 예산 튜닝(global 10/local 3),
   worker 8(12는 풀런 OOM). 누적 ~2.4–2.6× 단축.
2. **leader 퇴화 근본수정**: `_movement_net_flow_bounds`를 capacity→수요/큐-aware로
   (`src/controllers/leader.py`). N_P★ 탐색범위 [−3500,3500]→reachability(~[−528,921]).
   결과 **P-Stack이 P-FO를 이김**(peak 53% vs 40%).
3. **수요 skew 파라미터**: `ScenarioConfig.urban_boundary_weight_override`(총수요 보존 renormalize,
   `src/models/demand.py`) + 시나리오 4종(`scenarios.yaml`): heavy_demand_140/150, skew_peak, skew_heavy.
4. **사후분석 리포트**: `reports/post_analysis_results_2026-06-23.md` — 8시나리오 5섹션
   (수요특성/거시/미시/결합 다층/계산) + PFO↔P-Stack 심층. 그림 17종 `reports/figures/`
   (Times New Roman + 수식, 생성: `2026-06-23/diag_scripts/make_paper_figures_v2.py`).
   핵심: **혼잡·비대칭에서 P-Stack이 PFO 대비 +10~14pp**(leader 계산비용 정당화). medium·oversat만 동률
   (oversat 동률은 용량저하 confound — 순수 heavy는 +10pp).
5. **RL 코드 검토**: `reports/rl_code_review_2026-06-23.md`. Codex `src/rl/` 감사 — 구조 정확·테스트 10/10,
   **leader·follower 둘 다 RL agent**. 보완 권고: leader N_P★ bin이 [−3500,3500] 균일이라 도달범위 밖
   → 유용영역 재배치(N_P★는 RL에선 follower 관측 신호라 퇴화는 MPC보다 약함).

## 핵심 사실 (재확인됨)
- 시뮬 deterministic(seed 무관) → 분산은 시나리오로. 수요는 게이트별 비균등(1.0–1.6× gradient).
- half-cap penalty는 요소별(0.5·cap); peak엔 거의 비활성, heavy1.50/oversat에서 활성.
- VSL은 incident에서만 작동(WU/PFO=50, P-Stack=metering 대체).
- allocation pso/simplified는 direct보다 열위(강제 net-inflow 추종). direct 유지.
- matplotlib은 런타임이 가끔 초기화 → 그림 생성 전 `pip install matplotlib` 재확인 필요.

## 미해결/다음 후보
- low_demand에서 P-Stack 단독 회귀(−21%) — 저혼잡 conditioning 또는 fallback (별도 과제).
- RL: leader N_P★ bin을 reachability로 재배치 (또는 green 권한 확대로 net-inflow 도달범위 자체 확장).
- RL 학습 루프(신경망 DDQN)는 아직 미구현(현재 action-space/env까지).
- 풀 시나리오 매트릭스 7200s 재실행(현재 3600s).

## 제약 (불변)
- plant/차량보존식 임의 변경 금지. push/commit은 요청 시. Korean 출력은 마침표로 종료(콜론 X).
- 커밋 메시지 끝: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
