# 2026-06-22 작업 노트 — P-Stack 비용 절감(병렬 백엔드) + leader objective 진단

## 1. leader objective / P-Stack 퇴화 진단 (선행 분석)

핸드오프(`reports/claude_handoff_recent_leader_fidelity.md`) 이어받아 확정한 것.

- **fidelity 정상**: 선택 제어의 `leader_follower_ttt_base`가 실제 3-스텝 plant TTT와 거의 1:1(상관 0.9999, 비율 1.002). 같은-스텝 비교의 ~3.4×는 horizon(3스텝) 스케일 차이일 뿐. → 내 boundary_queue 가설, fidelity 가설 **둘 다 폐기**.
- **candidate ranking도 충실**: 혼잡 state에서 N_P 후보별 objective 랭킹 == 실제 rollout 랭킹(둘 다 argmin N_P=1400). 구현 버그 아님 = **유한-horizon/objective-설계 문제**.
- **퇴화(degeneracy) 발견**: `direct` 모드에서 N_P_star가 follower에 hard 제약이 아니라 net-inflow 위반 penalty로 들어감. 달성 가능 범위 밖 target은 모두 경계 제어로 saturate → N_P 6후보가 follower 응답 2개로 붕괴(N_P≤0→97.10, N_P≥1400→95.19). 그래서 leader 선택이 seed/tie-break로 양 끝(-3315 vs +2287/3220)을 임의로 튐. **leader가 실질적으로 leverage가 약함** → P-STACK이 P-FO 못 이김.
- **단, N_UF는 붕괴 안 함**: ramp metering 총량 N_UF는 후보마다 전부 distinct(5/5, 3/3) → dedup 여지 작음.

## 2. 비용 조사 (병렬화)

- 단일 follower solve ≈ 25s가 비용 바닥. 1800s 런 ~170s/step ≈ 스텝당 ~7개 distinct full solve.
- **thread 백엔드는 GIL로 무효**: follower grid가 순수 파이썬 dict 루프(numpy 스칼라뿐). serial=25.14s vs thread(8워커)=24.72s → 사실상 직렬.
- **process 백엔드 검증(production 하네스, peak 360s, PROPOSED-STACKELBERG)**:

  | 구성 | wall(2스텝) | total_ttt | speedup |
  |---|---:|---:|---:|
  | serial+serial | 569s | 50.526 | 1.0× |
  | leader=process(A1) | 362s | 50.526 | 1.57× |
  | **grid=process(A2)** | **229s** | 50.526 | **2.49×** |

  결과 byte-동일(B_sum=0.273802) = 정확도 무손실. leader+grid 동시 process는 중첩 pool이라 불가 → **최적 = leader=serial + grid=process**.

## 3. 변경

- `src/config/default.yaml`
  - `grid_parallel_backend: thread → process`
  - `stackelberg_leader_parallel_backend: thread → serial`
  - 근거 주석 추가.

## 4. 검증 (전체 단위테스트, process 기본값)

- `python -B -m unittest discover -s src/tests`: Ran 185, **FAILED (failures=8, errors=1)**.
- **단, 전부 기존 행동 실패이고 병렬 탓 아님**: pickling/BrokenProcessPool 0건, 전부 AssertionError/KeyError.
  - forecast-awareness 5건(Phase B 미완), post_analysis ablation 2건(`9 != 8`, fixed-player pin), six_controller 2건(`proposed_pair_differs...` = P-STACK 퇴화 그 자체), calibration smoke 1건(improvement −1.87%).
  - process는 값 byte-동일이라 이 assertion들을 바꿀 수 없음 → thread에서도 동일 실패(기존 이슈).
- distributed/coordinator 대표 3종은 process로 통과(24s).

## 5. 퇴화 근본수정 (옵션 1 — 완료·검증)

### 진단(코드로 확정)
- N_P_star는 follower 비용에 안 들어가고 `_augment_leader_target_net_inflow_candidates`가 green을
  목표 net-inflow에 맞춰 후보를 추가할 뿐. green은 [green_min,green_max]로 묶여 달성범위가 좁다.
- 코드는 이미 movement reachability로 클램프하려 했으나 `_movement_net_flow_bounds`가
  **capacity 기반(flow_max 합, 수요/큐 무시)** 이라 경계가 수천 veh로 과대 → 클램프 무력 →
  N_P_star∈[−3500,3500] 중 달성 [~260,380]뿐 → 98% saturation → 2-plateau 퇴화.

### 변경
- `src/models/urban_queue_model.py`: 공유 헬퍼 `movement_forecast_arrivals_veh(cfg, forecast)` 추가
  (boundary_in·on_ramp 도착; coordinator 로직과 동일, 단일 출처).
- `src/controllers/leader.py` `_movement_net_flow_bounds`: capacity → **수요/큐-aware**.
  movement별 `available=queue+arrivals`, `servable=min(available/horizon_h, cap_flow)`,
  경계 = [−Σoutflow servable, +Σinflow servable]. **arrivals는 first-step×horizon 스케일**로
  계산해 bounds를 forecast-미래 비의존으로 유지(설계 계약 `test_leader_candidates_reflect_forecast_summary`).
- `src/tests/test_constraints.py` 2건 갱신(옛 wide-bounds 단언 → reachability 클램프 단언):
  `test_default_leader_np_grid_covers_feasible_net_inflow_range`,
  `test_leader_np_candidates_use_feasible_net_inflow_range`,
  `test_leader_candidate_budget_covers_extremes_and_previous_action`(도달 불가 previous는 클램프 보존).

### 검증
- 혼잡 state: N_P 범위 [−3500,3500] → **[−528, 921]**, 범위 내 distinct 응답 **4/5**(이전 ~2),
  **내부 최적점 N_P≈559에서 base=93.16 < 경계 95.19/97.10** — leader가 더 좋은 내부 setpoint를
  실제로 식별 가능. (probe: `diag_scripts/_diag_fix_check.py`, `_diag_range.py`)
- 전체 단위테스트: **failures=8, errors=1 — 수정 전 baseline과 동일**(신규 회귀 0).
  남은 실패는 전부 기존 미완 이슈(forecast Phase B 5, ablation 2, six-controller 2).
  로그: `outputs/full_test_after_fix2.log`.

### End-to-end 검증 (peak 1800s, PFO vs P-STACK) — 수정 성공
로그: `outputs/pfo_vs_pstack_fixed.log` / `outputs/pfo_vs_pstack_fixed_peak_1800_20260622`

| Controller | total_ttt | no-control 대비 |
|---|---:|---:|
| NO-CONTROL | 605.83 | — |
| PROPOSED-FOLLOWERS-ONLY | 451.48 | 25.48% |
| PROPOSED-STACKELBERG | **419.95** | **30.68%** |

- **역전**: 수정 전 P-STACK 468.48(+17.0 패배) → 수정 후 419.95(**−31.5 승리**, PFO보다 ~7% 우수).
  P-STACK 상대성능 +17 → −31.5 (≈48.5 veh·h 개선). Stackelberg leader가 실질 가치 발생.
- **퇴화 소멸**: N_P_star = 487→447→407→387 (안정적 내부 setpoint, 옛 ±bound 튐 해소).
- PFO baseline 451.48는 Codex 수치와 일치 → leader만 바뀐 공정 비교.
- 설정: continuous, max_evals=8, max_nash_iter=1, direct, fallback off, grid=process.

### 남은 검증(다음)
- `test_proposed_pair_differs_by_leader_and_allocation_only`는 자체 시나리오 setup이라 별개(기존 실패).
  end-to-end는 P-STACK≠P-FO를 명확히 보여줌. 필요시 그 테스트 setup 재검토.
- 5-시나리오 풀 매트릭스 재실행으로 일반화 확인(선택).

## 6. local 탐색 예산 축소 (computation cost 추가 절감 — 완료·검증)

### 동기
full 탐색은 `leader_global_refresh_sec(1800s)`마다만 하고 나머지 스텝은 previous 인근만 보는 구조는
이미 있었으나(`_continuous_leader_search`의 global/local 분기 + local radius + sensitivity 방향),
**평가 예산(max_evals/seed/prefilter)이 global·local 공통**이라 local 스텝도 작은 영역을 촘촘히 평가했다.

### 변경
- `src/models/state.py` MpcConfig: local 전용 키 4개 추가(+검증)
  `leader_continuous_local_max_evals=6`, `local_seed_count=3`, `local_prefilter_samples=12`, `local_prefilter_top_k=3`.
- `src/config/default.yaml`: 위 키 추가.
- `src/controllers/stackelberg_mpc.py` `_continuous_leader_search`: global_refresh면 full 예산,
  아니면 local 축소 예산 사용. `_continuous_prefilter_actions`에 prefilter_samples/top_k 인자 추가.

### 검증 (peak 1800s, P-STACK)
| | total_ttt | 계산시간 |
|---|---:|---:|
| global=8/local=8(직전) | 419.95 | 1640.3s |
| global=25/**local=6**(현재 기본) | **418.35** | **1362.9s** |

- 계산 **~17% 단축** (global step 예산 8→25로 키웠는데도). 정확도 약간 향상(419.95→418.35), PFO 451.48 대비 우위 유지(30.95%).
- N_P 안정 내부 이동(487→…→367), local 스텝이 radius 내에서 천천히 추종.
- 로그: `outputs/pstack_localbudget.log` / `outputs/pstack_localbudget_peak_1800_20260622`.

## 7. 최적 예산 탐색 (computation cost 최소화 — 완료)

### 방법 (full 런 난사 대신 격리 측정)
- 기존 런 per-step 진단: **global step(step 0)이 전체 1363s의 39%(533s, 25 evals)**, local은 이미 lean(4~6 evals).
- step-0에서 global max_evals만 바꿔 격리 실행(budget 곡선):

  | max_evals | 선택 N_P | leader_obj | wall |
  |---:|---:|---:|---:|
  | 6 | 993(saturate) | 79.909 | 135s |
  | **10** | **488(최적)** | **74.238** | 214s |
  | 16 | 488 | 74.238 | 335s |
  | 25 | 488 | 74.238 | 484s |

  → max_evals=10이 25와 동일 setpoint·objective. knee=10. 6은 부족.

### 확정 값 (default.yaml)
- `leader_continuous_max_evals: 25 → 10`
- `leader_continuous_local_max_evals: 6 → 3`

### 검증 (peak 1800s, P-STACK)
| config | total_ttt | improvement | P-STACK compute |
|---|---:|---:|---:|
| global=25 / local=6 | 418.35 | 30.95% | 1362.9s |
| **global=10 / local=3** | **407.20** | **32.79%** | **714.2s** |

- 계산 **−47.6%**(1362.9→714.2s)인데 정확도 **향상**(418.35→407.20, PFO 451.48 대비 32.8%).
  (leader objective의 유한-horizon myopia상 과탐색이 오히려 closed-loop 손해인 구간이라, lean 예산이 더 좋음.)
- 원래 Codex baseline(1703s, 468.48 패배) 대비 누적: **~2.4× 빠르고 패배→승리.**
- 곡선 probe: `2026-06-22/diag_scripts/_diag_budget.py`, 로그 `outputs/pstack_tuned.log`.

### 더 줄일 여지(미검증)
- global 8(6 실패와 10 사이), local 2 — 추가 절감 가능하나 정확도 리스크. 현 10/3이 검증된 안전 최소.

## 8. TODO

- (별도) P-STACK 퇴화 근본 수정: `direct` 모드 N_P_star→follower 매핑이 2-plateau로 뭉개지는 문제. leader leverage 회복 설계 필요.
- (별도) forecast-awareness Phase B 테스트 5건 / ablation 2건 — 기존 미완 작업.
- process 기본값 회귀 모니터: 다른 진입점(스크립트)이 main-guard 없이 coordinator를 process로 호출하면 Windows spawn 재귀 위험 — 실험 하네스(`-m`)는 안전 확인됨.
