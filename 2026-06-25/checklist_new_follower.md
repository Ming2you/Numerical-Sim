# 새 follower: Wu식 국소분해 + proposed 제어권한 + proposed leader 인터페이스

목표: proposed Stackelberg leader(N_P, N_UF — 검증됨 23.88%)는 그대로 두고, follower를
full-coupled 전역 그리드(DistributedCoordinator, ~300/candidate, O(n²)) 대신
**Wu식 국소분해(local agent solve + 고정 coupling + consensus, O(n))** 로 새로 짠다.
단 Wu follower엔 없는 **ramp metering/allocation 권한을 추가**(sweet_128 가치=N_UF metering).

## 설계 계약 (proposed leader가 기대하는 인터페이스)
- `solve(state, leader, demand|forecast, previous) -> NashResult`
  - `leader = LeaderAction(N_P_star, N_UF_star)` (proposed; None이면 PFO).
  - 반환: `.control`(green/offset/vsl/ramp_metering/allocation), `.objective_value`(realized TTT),
    `.converged`, `.diagnostics`(distributed_response_rollout_ttt 등 leader가 읽는 키).

## 알고리즘 (Wu §IV-D + 권한 확장)
- [ ] 초기 control=previous/fixed, coupling y 계산.
- [ ] s=1..S_max(=5): Jacobi 스냅샷 고정 →
  - urban agent i: green(+offset/allocation) 후보 국소탐색, 이웃 coupling 고정,
    **N_P conditioning**(누적>ω_i·N_P 패널티), **국소 urban rollout로 채점**.
  - freeway agent p: VSL **+ ramp metering** 후보 국소탐색, coupling 고정,
    **N_UF conditioning**(metering 합 target), **국소 freeway rollout로 채점**.
  - coupling 갱신(under-relax) → residual<tol 또는 s>S_max 종료.
- [ ] **후보·최종 선택은 realized TTT로**(WU-MATCHED 0% 버그 교훈: 누적·proxy 금지).
- [ ] 최종 control rollout 1회로 objective_value(realized TTT) + diagnostics 산출.

## 재사용 (WuDistributedController에서)
- `_build_coupling_maps`, `_coupling`, `_solve_urban_agent`(green+N_P) — 그대로/약간 수정.
- `_solve_freeway_agent`(VSL) — **ramp metering 후보 추가**, N_F→N_UF conditioning으로 교체.
- `freeway_substep`/urban local plant — 국소 rollout용.
- consensus 루프(`_solve_followers`) 구조 차용.

## 새로 짜는 것
- [ ] freeway agent에 **ramp metering 제어** 추가(N_UF target에 사영, 공급/수용 상한).
- [ ] N_UF conditioning(metering 합 ≈ N_UF) — proposed leader 의미와 일치.
- [ ] allocation(urban) — 1차엔 생략 가능, 후속 추가.
- [ ] TTT 기반 candidate 선택.

## 검증 (마일스톤)
- [ ] M1: 컴파일 + proposed leader에 plug → 실행되고 control 산출.
- [ ] M2: sweet_128에서 **TTT 개선 ~19-24%**(현 proposed 23.88% 근처) + **비용 ≪ proposed**(eval/step, time).
- [ ] M3: sweet_115/190에서도 회귀 없음(저혼잡 무해, 과포화 defer).
- [ ] 결정성(seed 고정), unittest 회귀.

## 불변/주의
- proposed leader 코드 미변경(복사/재사용만).
- plant/차량보존 식 불변. 국소 rollout은 경계(coupling) 고정 근사 — 충실도는 Nash 합의로 회복.
- 멀티-세션 작업. M1(plug+run) → M2(성능/비용) 순으로.

## 진행 상황 (2026-06-27)
- `src/controllers/wu_style_follower.py` 작성(WuDistributedController 상속, solve→NashResult).
- 통합: `_make_follower_solver`에 wu_style 모드, state.py validation, 어댑터 `PROPOSED-STACKELBERG-WU`,
  authority.py 등록. 모두 컴파일 OK.
- **M1 결과(sweet_128, T=1440)**: 플러그 OK·실행 OK. **90s / 31 eval/step** (PROPOSED-STACK
  1964s/1302 대비 22×/42× 저렴) — **아키텍처가 싸다는 건 증명.**
- **그러나 impr=0.0%** (conditioning ON·OFF 둘 다). standalone WU-CD-F=19.45%(하네스)와 다름.
  → **통합 버그**: proposed leader(StackelbergMPCController) 밑에서 `_solve_followers`가 무력화됨.
- **다음 디버깅 step (가설 순)**:
  1. 내 follower가 *실제로 산출한 control*(green/vsl)을 standalone WU-CD-F와 비교 — 같은가? (다르면
     leader가 넘기는 `previous`(normalize) 또는 candidate 가공이 follower 입력을 망침.)
  2. eval 31 vs 120 차이 — consensus가 leader 밑에서 조기종료/적게 도는지(`previous`가 cold/fixed?).
  3. 의심 1순위: leader가 solve()에 넘기는 `previous`가 follower green/vsl warm-start를 깨거나,
     leader의 closure/commit이 follower control을 덮음.
- N_P/N_UF 의미매핑(M2)은 통합버그 해결 *후* — proposed N_P=net-inflow, N_UF=metering 의미에 맞는
  conditioning + freeway agent ramp metering 추가.
