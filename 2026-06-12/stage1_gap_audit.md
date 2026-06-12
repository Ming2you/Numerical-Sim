# Stage 1 구현 gap audit — 6-controller 비교 (spec 16 기준)

기준: HEAD `1ab003b`(≥ 2f8664c ✓), `docs/spec/16_six_controller_comparison.md`,
`docs/literature_grounded_post_analysis_plan.md` §2, `docs/wu2022_distributed_reference.md`.
원칙: plant·차량 보존식 무변경(spec 16.2). 추가 가능한 것은 진단 로깅뿐.

## A. 컨트롤러별 gap

| # | Controller | 기존 자산 | gap |
|---|---|---|---|
| 5 | PROPOSED-STACKELBERG | `StackelbergMPCController`+`DistributedCoordinator` 그대로 | 계산시간·solver evaluation·수렴 진단 래핑만 |
| 4 | PROPOSED-FOLLOWERS-ONLY | follower 구조 동일 재사용 | **leaderless 모드 신설**: allocation은 net-target 항 제거(관측 큐·storage·불균형만으로 결정), freeway agent는 N_UF 대신 local objective로 metering 후보 선택. 숨은 고정 target 금지 자동검사 |
| 6 | PROPOSED-CENTRALIZED | 없음 | **budgeted centralized MPC 신설**: full authority 제어벡터(게이트 service 7+metering 4+VSL 2+offset 5+green 5)를 coupled plant 예측으로 직접 탐색(seeded random+coordinate refine). evaluation budget·수렴 보고 |
| 1 | WU-CD-F | coordinator 골격(결합변수 추출·iteration) 재사용 가능 | **Wu authority agent 신설**: urban agent=green p1 후보 탐색(국소 큐 예측, 이웃 결합 고정), freeway agent=VSL 후보 탐색. offset 고정 0, metering=용량(no-metering 물리 유출), allocation 미사용(움직임 cap=포화유율) |
| 2 | WU-MATCHED-STACKELBERG | #1 + 기존 leader 후보 열거 패턴 | leader action을 (N_P_star, N_F_star[veh])로 교체, follower local objective에 `w×pos(n_pred−ω×target)` conditioning(ω 고정 가중), leader는 coupled 예측으로 system objective 평가 |
| 3 | WU-CC-F | #6 엔진 공유 | 동일 centralized 엔진을 green+VSL 차원으로 제한, `J_WU_global`(16.6) 사용 |

## B. 공통 인프라 gap

1. **Free-flow reference** (spec 16.11): 없음 → 신설. β 흡수 마르코프 체인으로 진입원별
   기대 자유류 여정시간(urban 링크 95.04s/링크, freeway L/v_free, ramp 전이 포함)을 계산하고
   horizon 내 수요 적분으로 TTT_ref(total/urban/freeway)를 산출. 시나리오·seed당 1회, 6개 공통.
2. **completed vehicles/throughput**: urban 완료=`boundary_out_sink_veh`(있음 ✓),
   freeway 완료=마지막 세그먼트 `(1−off_ratio)×q_out` — **로깅 없음** → `metanet.py`에
   `mainline_exit_flow_*` 진단 추가(동역학 무변경).
3. **terminal state**: 최종 TrafficState에서 추출(자산 있음) — 집계 helper만.
4. **Stage-1 metrics 묶음**(TTT/delay/throughput/terminal/계산량) 조립기 + paired comparison
   (16.10의 6쌍, low-delay NA 규칙·음수 delay=회계오류 판정) — 신설.
5. **authority 자동검사**: control trace에서 Wu group(offset 상수·metering=용량·allocation 부재),
   proposed group(4계열 모두 가동), leader 유무, centralized 플래그 검증 — 신설.
6. **runner**: `src/experiments/six_controller_comparison.py` — 시나리오/seed별 reference 1회
   계산→6개 실행→`post_analysis/stage1/` CSV·fidelity matrix 출력.
7. **테스트**: spec 16.13의 17개 — 신설.

## C. 의도적 근사(fidelity matrix에 기록할 항목)

- Wu local solver: 원문 MILP/SQP 대신 **결정적 후보 탐색**(국소 큐/밀도 경량 예측, 이웃
  결합변수 고정) — wu2022_reference §8의 기존 허용 노트와 동일 계열.
- Wu off-ramp spillback: 본 plant는 storage-cap 방식(차로수 감소 식22와 효과 등가, §8 명시).
- VSL 변화 제약: 본 plant는 양방향 `max_vsl_step`(Wu는 감소만 제한) — 기존 차이 유지.
- PROPOSED-CENTRALIZED 탐색 차원 축소: movement별 allocation을 게이트 단위 service level로
  매개변수화(β 비례 배분) — "보장된 최적 아님, 동일 budget의 수치 참조"로 보고(16.9).
- demand scenario: plan §2.5의 8유형 중 기존 5종(low/medium/peak/oversat/incident)으로 1차
  실행. on-ramp surge·high transfer는 ramp_scale 기반 신규 시나리오로 추가 가능(후속).

## D. 구현 순서

1. 공통 인프라: mainline exit 로깅 → free-flow reference → Stage-1 metrics 조립기.
2. Wu agent 모듈(`src/controllers/wu_distributed.py`): WU-CD-F → leader conditioning(WU-MATCHED).
3. leaderless 모드(`distributed_coordinator`/allocation에 leaderless 분기): PROPOSED-FOLLOWERS-ONLY.
4. centralized 엔진(`src/controllers/centralized_mpc.py`): PROPOSED-CENTRALIZED → WU-CC-F.
5. runner+authority 자동검사+테스트 17종.
6. smoke run(peak, 단축 horizon, 6개 전부) → 결과 보고 → 커밋.
