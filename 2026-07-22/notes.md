# 2026-07-22 작업 노트 — RL leader Phase 4 (연속분포 일반화)

## 목표
P-Stack의 leader 탐색을 RL로 대체(가격+budget만 RL, 배분은 local follower 그대로).
Phase 4 = **연속 수요분포 + 랜덤 stressor로 한 번 학습 → 학습에 없던 190+stressor에서 일반화 검증**.

## 설계 결정
- 관측 = 13-dim 물리량 압축벡터(시나리오 라벨 없음 → scenario-agnostic). 일반화 유리.
- action = (N_P, N_UF) budget, [-1,1]→feasible box. follower=P-Stack nash_solver 그대로.
- reward = −ΔTTT(step), γ=0.99. SAC + BC warm-start.
- **hold-out 프로토콜**: stressor(skew/incident) 활성 시 수요 ≤ 1.80으로 제한.
  → 190(=1.90)+stressor는 학습분포에 절대 없음(test 전용). 순수 일반화 측정.

## 구현 (이번 세션)
1. `rl_leader/env.py` — `make_random_scenario(rng, holdout_demand=1.80)`:
   수요 U[1.55,2.40], stressor∈{none,skew,incident}(p=.4/.3/.3), stressor면 수요 cap,
   ×노이즈 U[0.98,1.02]. skew: ratio U[1.3,2.0]. incident: seg∈[3,8), 시작/길이 랜덤, lane_loss=1.0.
   `make_cfg`가 dict도 수용(`ScenarioConfig.from_mapping`).
2. `rl_leader/sac.py` — `--continuous` 모드: 에피소드마다 `make_random_scenario`로 env 재생성.
   스모크(T=1080, 4 ep) 통과: d1.59/d1.82/d1.56 서로 다른 수요로 env 재생성 확인, exit 0.
3. `src/config/scenarios.yaml` — held-out 2종 추가: `sweet_190_incident_w60`, `sweet_190_skew15_w60`.
4. `rl_leader/eval_holdout.py` — windowed TTT(warmup 5 제외)로 RL vs NC/PFO/P-Stack/P-CENT 비교.
   baseline은 `outputs/_wang3/ho_{ctrl}_{tag}/{CTRL}/run_log.csv`에서 동일 방식 계산.
5. `rl_leader/run_phase4.sh` — 자동 체인: 파일럿(actor_sac.pt) 대기 → 연속 SAC(BC init, 3000 steps)
   → held-out baseline 대기 → eval(BC-raw, SAC-continuous).
6. `work/ho_baseline_jobs.txt` — held-out baseline 8잡(NC/PFO/P-Stack/P-CENT × inc/skew).

## 진행 상황 (20:05 시점)
- BC 수집기 5개 실행 중(155/170/skew15/incident/190), npz 미생성.
- 파일럿(run_rl_pipeline.sh) alive: BC 데이터 대기 → BC train → 5셀 SAC → eval.
- phase4(run_phase4.sh) alive: actor_sac.pt 대기 중.
- held-out baseline: NC/PFO 완료, P-Stack/P-CENT 실행 중.

## 예비 관찰 (windowed TTT)
- **190-incident**: NC=8555.9, PFO=9230.0 → **PFO가 NC보다 악화**(고부하+사고서 개입과잉 병리 재현).
- **190-skew**: NC=6881.9, PFO=6299.3 → PFO 개선(+8.5%).
- P-Stack/P-CENT 결과 대기 중.

## TODO
- [ ] 파일럿 5셀 결과 확인(BC/SAC vs optimizer/NC)
- [ ] 연속 SAC 학습 완주 + held-out 평가 결과
- [ ] P-Stack/P-CENT held-out baseline 완료 확인
- [ ] RL이 학습에 없던 190+stressor에서 P-Stack 대비 우세/동급인지 판정
