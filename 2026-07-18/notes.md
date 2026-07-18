# 2026-07-18 작업 노트 — P-Stack 계산량 사다리

## 배경

프로파일(1 결정스텝, 302.9s, 배경부하 14프로세스): `run_coupled_interval` ×690 = 88%.
분해 — `_sync_legacy_queues` 38%(162,925회, dict.get 495M) / 가격 refresh 41%(FD rollout 51회) /
proxy prefilter 38%(49회 × 2.35s) / full eval 17%(5회 × 10.3s).
사다리(사용자 승인): 0단 sync 캐시 → 1단 proxy 축소 → 2단 가격 refresh 간격 → 3단 PD4 K 축소.
**각 단마다 성능 검증(비트동일 또는 A/B + 벽시계) 통과 후 다음 단 진행.**

## 0단 — _sync_legacy_queues 정적 역인덱스 캐시 (커밋 0af5167) ✅ PASS

- 원인: 호출마다 `movement_specs()`가 78-movement dict 사본을 재조립 + 14링크×78무브먼트
  전수 스캔(호출당 dict 연산 ~2,200). 토폴로지(origin/destination)는 런 중 불변.
- 수정: `_legacy_sync_index(cfg)` — network 객체 참조 동일성 키로 link→movements 역인덱스
  1회 구축(합산 순서 = urban_movements 삽입 순서 보존 → 부동소수 비트동일).
  `ensure_urban_state`엔 초기화 완료 시(4개 dict 키 개수 충족) setdefault 전수 루프 스킵
  fast-path. 안전조건: 해당 dict들에 pop/clear/del 경로 전무(전역 grep 확인).
- 검증(190_w, T=4680, 26스텝, walk-MVG 플래그):
  - 비트동일: `cumulative_total_ttt` 26/26행 완전 정밀도 문자열 일치 (최종 535.316).
  - 벽시계: 결정스텝 solve 평균 **81.6s → 54.1s (−33.8%)**, 6스텝 균일 감소.
    (주의: after 런 중 B8 h2_170 종료로 부하 14→13 — 감소가 전 스텝 균일해 최적화 효과 지배.)

## 1단 — proxy prefilter 축소 = 후보 수 축소 (leader_candidate_count 49→25) ✅ 부분검증

- 대상: `_prefilter_leader_candidates`→`_proxy_score_candidate` ×49(proxy가 full rollout 수행).
- proxy rollout depth 축소는 이미 OPT3(leader_proxy_near_far)로 기각(far 랭킹 불가, 단독 +1036).
  dedupe(candidate_dedupe)는 `_evaluate_full_candidate`(full 5회)에만 붙어 proxy 미적용·부적합.
- 유일 경로 = 후보 수 축소. 후보 = local `refined_candidates(count=leader_candidate_count)`
  49개(+global 스텝 75개). CAND env로 override(runner:707).
- **A/B(190_w·170_w, CAND 49 vs 25, T=4680 26스텝)**: cum_ttt **26행 완전 비트동일**
  (190=535.3158633714312, 170=499.2302325151652), solve **−13~14%**(41.8→35.8 / 40.4→35.0s).
  후보 24개(global 75→51)는 순수 낭비 — prefilter top_k=7 선택이 25개 격자로도 동일.
  → 0단처럼 **행동 불변 최적화**(비트동일이라 TTT 무손실 확정).
- **확대 검증 완료**: 후보 **25 = 안전 하한**. 155/170/170_skew15/190 = 완전 비트동일,
  170_incident만 0.001% 차이(499.3194 vs 499.3243 — 선택 미세 갈림, 사실상 무손실).
  후보 **15는 과도**: 비트동일 깨짐(190 +0.14% 악화 536.04 vs 535.32, 170 −0.004%).
  결론: leader_candidate_count 49→**25** 채택 가능(solve −13~14%, 4/5셀 비트동일+1셀 0.001%).
  단, state.py 기본값(49) 변경은 **사용자 승인 대기**(무손실이나 완전 비트동일은 아님).
## 2단 — 가격 refresh 스텝 간격 (PRICE_REFRESH_INTERVAL, 커밋 41a20c1) ✅ 채택가능

- 구현: `decide_with_info` single-shot 경로(:466)에 스텝 간격 게이트. interval=1=매스텝
  (비트동일 기본, base=perf_before 완전 일치로 편집 안전성 확인). N>1이면 step_idx%N!=0
  스텝은 `_maybe_refresh_signal_prices` 스킵→follower 잔존 가격 재사용. 훅 `PRICE_REFRESH_INTERVAL`.
- 진단 검증: interval=2에서 `wu_b2_price_skipped` **3/6 결정스텝 발화**(홀수 스텝 스킵) — 훅 작동 확증.
- A/B(190/170, interval 1 vs 2, T=4680): solve **−25.9%/−17.9%**, TTT **+0.123%/+0.089%**(무시 가능).
- 결론: 채택 가능(큰 절감·미미한 TTT). 기본값 interval=2 전환은 **사용자 승인 대기**(비트동일 아님).

## 3단 — PD4 K=4→2 (NP_PD_ITER=2) ❌ 기각(무효)

- A/B(190/170, K 4 vs 2): TTT **완전 비트동일**, solve **무변화**(−0.1%/+0.6%=잡음).
- 진단으로 "훅 불발 vs 무효" 판별: `wu_faithful_np_pd_iters`가 K=4·K=2 **둘 다 {0,2}** —
  PD 루프가 K 상한과 무관하게 **최대 2회 조기종료**(dual-inert: λ 잔차 조기수렴/포화).
  즉 K=4가 3~4회를 쓴 적이 없어 K=2로 낮춰도 자를 게 없음 → 훅은 배선됨, 효과가 없음.
- 결론: **기각**. PD 반복은 이미 2회로 짧아 절감 여지 없음(K=1 강제는 TTT 리스크·소이득이라 미추구).

## 사다리 총결

| 단 | 변경 | solve | TTT | 판정 |
|---|---|---|---|---|
| 0단 | sync 인덱스 캐시 | −34% | 비트동일 | ✅ 채택(적용·커밋 0af5167) |
| 1단 | 후보 49→25 | −14% | 4/5 비트동일+0.001% | 채택가능(승인대기) |
| 2단 | refresh 격스텝 | −18~26% | +0.09~0.12% | 채택가능(승인대기, 41a20c1) |
| 3단 | PD K=4→2 | 0% | 비트동일 | ❌ 기각(2회 조기종료) |

0단만 적용 상태. 1·2단 채택 시 누적 절감 대략 solve −34% 위에 후보·refresh 축소 중첩
(env: CAND=25 PRICE_REFRESH_INTERVAL=2). 기본값 전환은 사용자 결정.

## ★★1·2단 채택 철회 — 60스텝 전체 실행이 파국 폭로 (커밋 fe6d78e)

**사용자 "1·2단 채택 후 재실행" 지시로 state.py candidate 49→25, controller interval 1→2
기본값 전환 후 walk-MVG 5셀 전체 길이(T=10800, 60스텝) 재실행 → 전 셀 +60~152% 파국:**

| 셀 | 기존wTTT(패키지) | 신wTTT(1+2) | ΔTTT | Δsolve |
|---|---|---|---|---|
| 155 | 1685 | 3080 | **+82.8%** | −62.1% |
| 170 | 2684 | 5819 | **+116.8%** | −64.3% |
| 170_skew15 | 2667 | 6723 | **+152.1%** | −58.9% |
| 170_incident | 2295 | 4630 | **+101.7%** | −59.9% |
| 190 | 5156 | 8249 | **+60.0%** | −64.1% |

진단상 candidate=25·skip=20 정상 적용 — 최적화는 걸렸고 결과가 파국. **원인 = 검증 창이
너무 짧았음.** 1·2단 A/B는 T=4680(26스텝, 결정스텝 6개=20~25)로 초기 plateau만 봐
+0.1%였으나, 논문 실런 T=10800(60스텝, 결정 40개=20~59)은 혼잡 plateau(65~125분)+회복
전 구간을 겪고 여기서 가격 스킵(2단)·후보 축소(1단) 근사가 눈덩이. solve −60%지만 컨트롤러
성능을 거의 다 소실.

**즉시 조치**: 두 기본값 원복(candidate 49, interval 1). 패키지 walk_mvg 원본 데이터는
미변경(안전). env 플래그(CAND/PRICE_REFRESH_INTERVAL)는 실험용으로 남김.
**주범 격리 완료**(전체 60스텝, vs baseline):
| 셀 | baseline | 1단 단독(cand25) | 2단 단독(int2) | 1+2 |
|---|---|---|---|---|
| 190 | 5156 | 5156 (−0.0%) | 8249 (+60.0%) | 8249 (+60.0%) |
| 170 | 2684 | 5084 (+89.4%) | 5819 (+116.8%) | 5819 (+116.8%) |
- **2단(가격 스킵)=두 셀 모두 파국**(균일). **1단(후보25)=셀 의존**(190 무해·170 +89.4% 파국).
  170의 26스텝 "비트동일"은 **가짜 음성** — 첫 6 결정스텝만 선택 같고 나머지 34스텝서 격자축소가 발산.
- 둘 다 전체 길이서 부적합. **0단(비트동일)만 안전** — 지평 무관.

**방법론 교훈(★)**: 계산 최적화(근사) 검증은 **반드시 전체 60스텝**으로 — 짧은 창은
근사 오차의 누적을 못 봐 파국을 은폐한다. [[measure-before-claiming-mechanism]]·
"closed-loop+replay만 신뢰" 계보. 0단은 비트동일이라 창 길이 무관(안전), 근사 단(1·2단)만
이 함정. 3단은 무효(기각 유지).

## ★SLSQP 밤샘 결과 — 가정 반전: SLSQP는 천장이 아니라 grid보다도 나쁨

6셀 완주(190_w는 밤샘 런이 60스텝 완주·백업 run_log.BACKUP.csv, 내 불필요 재발주 PID는
정리). 게이트(scipy 실가동): 6셀 전부 available=1.0·fallback=0·mode_slsqp=1.0 = PASS.
windowed wTTT = cum_ttt[last]−cum_ttt[19] (WARM=20; grid 6셀 표1값 정확 재현으로 정의 확정).

| 셀 | grid(P-CENT) | SLSQP | P-Stack | SLSQP/grid | mean_solve | 수렴% |
|---|---|---|---|---|---|---|
| 155 | 1614 | 6326 | 1685 | 3.92× | 516s | 85% |
| 170 | 2488 | 7877 | 2684 | 3.17× | 507s | 70% |
| 170_skew15 | 2517 | 7922 | 2667 | 3.15× | 507s | 80% |
| 170_incident | 2354 | 7820 | 2295 | 3.32× | 511s | 65% |
| 190 | 4705 | 9989 | 5156 | 2.12× | 548s | 92% |
| 200 | 7480 | 11137 | 8684 | 1.49× | 528s | 80% |

**SLSQP는 grid보다(1.49~3.92×), 제안 컨트롤러 P-Stack보다도 나쁘다.** "offline ceiling"
가정 붕괴. mean_solve 507~548s ≫ 180s 제어주기 → 실시간 불가(예상대로).

원인 = 비수렴 + closed-loop 누적 (measure로 확증; "매 스텝 로컬 갇힘"은 probe가 반증):
- grid·SLSQP는 같은 `_predict_with_ttt`·`_objective` 공유(centralized_mpc.py:602,707).
  예측모델이 원인이면 grid도 나빠야 하는데 grid는 우수 → 예측모델 무죄.
- **probe_slsqp_vs_grid_obj.py (155_w, 동일 no-control 전진 state, 단일 스텝 목적값)**:
  step20 grid1565.5/slsqp1644.2(+5.0%), step30 6534.2/6501.7(−0.5%), step40 21113.8/
  21154.4(+0.2%) — 전부 slsqp_success=1.0. **단일 스텝 목적값은 grid와 거의 대등**
  (gap 0.2~5.0%, 2:1 grid 근소우세). 즉 "SLSQP가 매 스텝 크게 나쁜 로컬에 갇힌다"는 틀림.
- 그런데 closed-loop wTTT는 2~4배 벌어짐 → 괴리의 원인:
  (a) 결정스텝의 8~35%가 **비수렴**(success_count=0, 5-start 전멸, grid 폴백 없이 SLSQP
      best 사용) → 그 스텝의 나쁜 제어,
  (b) 오차가 closed-loop에서 누적·발산(단일 스텝 5% 열화가 다음 state를 악화, 눈덩이).
- non-smooth 목적(metering_shortfall/target_infeasible/projection_protected 등 kink 다수)라
  gradient SQP가 (a) 비수렴에 취약. (b) 발산은 실측(2~4배)+단일스텝대등에서 추론 —
  no-control probe라 self-previous 갇힘은 미측정("consistent with"로만 서술할 것).

논문 처리 = **사용자 서사 결정 대기**(반전이라 기계적 숫자교체 부적절). 옵션:
(A) SLSQP 열 제거 + §5/방법론에 "gradient SQP도 시험, grid보다 열등한 로컬 수렴 → grid 채택" 1문단.
(B) 표에 "gradient 기준선(로컬해)"로 정직 게재 — grid·P-Stack 대비 열등을 보여
    "non-convex 교통 문제엔 구조적 전역탐색 필수"라는 방법론 기여(VdB07/Haddad13 실패 정직게재 계보).
→ 기존 "ceiling 컬럼/§0 offline-ceiling 선언/§1 ceiling-tightness" 계획은 전부 무효.

## B8 민감도 8런 완료 — horizon·box R 모두 기본값이 최적 구간(U자형)

walk-MVG 기준 170_w=2684 / 190_w=5156 대비 (wTTT, 결정스텝 60):
| arm | 170_w | 190_w | 해석 |
|---|---|---|---|
| h2(horizon 2) | 8741 (+225.7%) | 9805 (+90.2%) | **파국** — 예측 시야 부족 |
| h3(기본 3) | 2684 | 5156 | 기준 |
| h4(horizon 4) | 2554 (−4.8%) | 5274 (+2.3%) | 이득 없음(혼조) |
| r225(box R 225) | 2592 (−3.4%) | 10942 (+112.2%) | 190 **파국** — 고부하 회복 시야 상실 |
| r300(기본 300) | 2684 | 5156 | 기준 |
| r375(box R 375) | 2622 (−2.3%) | 7068 (+37.1%) | 190 악화 — bang-bang 재유입 |

핵심: **고부하 190_w가 양쪽 극단에서 파국** → 기본값(h3/R300)은 튜닝이 아니라 물리적 최적
구간. §4 민감도 그림 서사(U자, "for the network considered here" 한정, 단일시드 진술).

## 배경 런 현황 (이 날 시점)

- SLSQP P-CENT 6셀: 완주·게이트 PASS(위 표). 190_w 재발주 중복 프로세스 정리(6h 절약).
- B8 민감도 8런: 완료(위 표).
- 코드 편집은 이미 임포트를 마친 실행 중 프로세스에 영향 없음(전 런 serial/thread, 재임포트 스폰 없음).
