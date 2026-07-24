# PROMPT — Stackelberg 작동 입증 3패널 그림 + best-response 통계 (VSL 수정·최종 코드 재실행 후)

프로젝트 `Desktop/Numerical-Sim-offiter`, controller `P-STACK-WU-FAITHFUL-ALLPRICE-JOINT`.
showcase = medium-skew (`sweet_170_skew15_w`), T=14400, env=최종 flagship 플래그.
먼저 메모리 [[price-channel-ablation-and-vsl-fix-pending]], [[numerical-sim-nash-coupling-gap]] 참고.

## ★ 재실행 시 먼저 (2026-07-23 조사 결과)
1. **S_max=10 사용** (`NASH_SMAX=10` env — wu_faithful_follower.py:3888에 override 추가돼 있음, 기본 5). skew서 S_max=5→10 시 **conv율 54.5%→100%, TTT 완전 동일(Δ0.00%), 계산시간 +1%(30.7→31.1s)** = 무손실 free win. iter 최대 10, 대부분 조기수렴.
2. **5셀 × S_max{5,10} A/B로 일반화 확인** (base_*는 구코드라 못 씀 — 현 코드 conv 54.5% vs base 20%, 새로 10런 필요). TTT 불변·conv 100% 전 셀 유지되는지 확인.
3. **PRICE_CF를 메인 궤적에 쓰지 말 것.** 반사실 솔브가 솔버 상태 누수 → 궤적(cf_190 +11%)·수렴율(7% vs 깨끗 54.5%)·자기일관성(N_UF 갭 1250 vs 깨끗 0) 전부 오염. 반사실 필요하면 솔브 전 솔버 clone/snapshot.

## 3 패널
- **(a) [중심] Candidate-wise leader objective.** 한 대표 혼잡 스텝서 (N_P, N_UF) **격자**를 `_evaluate_full_candidate()`로 채점해 J_L heatmap, 선택 candidate 별표. ★ 자연 candidate는 operating point 근처 ~5점만이라 부족 → **frozen 2D 격자 probe 필요**(stackelberg_mpc.py:654 `LEADER_CURV_SWEEP`가 1D N_UF sweep 기존구현, 2D로 확장). 참고: `LEADER_CAND_LOG` env는 자연 candidate 전부를 `.allcand.csv`로 남기나 클러스터돼 heatmap엔 부족.
- **(b) Selected targets vs realized.** N_P*/N_UF* target vs realized 오버레이 + realized ramp/merge flow/Q_P. **깨끗한 런(PRICE_CF 없이)이면 채점=실행(갭 0) = 자기일관성 정상** — 이걸 보여주면 됨.
- **(c) Best-response residual (실시간 안정화).** nash residual control-epoch CDF + 평균/최대 iter + ε(0.001)·S_max(10). **S_max=10이면 conv 100%** → 깔끔한 수렴 스토리. "180s 구간 내 안정화", TABLE 3 연결.

## best-response 통계 문단 (숫자 몇 개)
convergence rate, 평균/최대 iteration, 최종 residual 평균/95th, S_max 도달 비율, infeasible/target-violation 비율. **"algorithmic response convergence/stabilization" 사용, "exact GNE convergence" 금지**(follower 분리형 best-response).

## 데이터 맵 (run_log.csv, 확인됨)
- (b) `leader_realized_N_P/UF_star`, `leader_candidate_best_N_P/UF_star`(target), `leader_candidate_best_realized_N_UF_star`(채점예측 realized), `ramp_metering_releases_veh`, `mainline_exit_flow_total`, `leader_boundary_in_queue_veh`.
- (c) `nash_converged`/`nash_iterations`/`nash_residual_control`/`nash_residual_objective`. per-iteration 곡선 원하면 follower Nash 루프에 로깅 추가.
- (a) 전체 candidate J_L: `LEADER_CAND_LOG` env로 `.allcand.csv`(자연 candidate, 클러스터). heatmap용 격자는 frozen probe.

## 제약
(a) 중심·(c) 보조·(b) 교통 물리량 연결. GNE 주장 금지. 추측 금지 — 실제 run 데이터 검증 후 서술.

## 산출물 (이번 세션 프로토타입, 참고)
- work/proto_algo_verification.py (b+c 프로토), work/analyze_smax_ab.py (S_max A/B), work/analyze_green_sweep.py
- 2026-07-23/results/fig_proto_algo_verification.png, fig_a_candidate_heatmap.png(격자 부족 예시)
