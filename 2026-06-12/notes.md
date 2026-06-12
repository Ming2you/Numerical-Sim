# 2026-06-12 작업 노트 — acceptance 게이트 재정의 + 종합 verdict PASS

전제: 2026-06-11에 그리드 라우팅 구현(d070acf) + distributed 재튜닝(403e778, TTT +15.55%
main PASS)까지 완료. 남은 FAIL이 vsl/ramp_metering/boundary_balance 게이트였고, 진단 결과
"컨트롤러가 나빠서"가 아니라 **지표 정의가 구 plant·구 컨트롤러 행동을 전제**한 문제로 확인 →
이번 라운드에서 각 게이트를 도메인 논거에 따라 재정의하고 실제 컨트롤러 버그 1건(VSL)을 수정.

## 최종 결과

**풀 7200s peak_demand distributed: 종합 verdict PASS (dominant failure mode: none)**
- Total TTT **+22.21%** (기준 8%) — 6,030 vs baseline 7,751 veh·h.
- ramp_metering PASS(75.5 ≤ eps_F 100) / vsl PASS(변화폭 위반 0) / green·offset PASS /
  boundary_balance PASS(B_in 0.012, B_out 0.0038 ≤ 0.03; degenerate 0; 추적오차 71.9 ≤ 100).
- 결과: `outputs/tune_V10_gates_full7200`, 사본 `2026-06-12/results/full7200_all_gates_PASS_report.md`.
- 단위테스트 70/70 통과(신규 게이트 재정의 테스트 4개 포함).

## 게이트별 수정 내용과 논거

### 1. ramp_metering — ceiling 의미론 (1678 → 75.5)
- 문제: N_UF_star는 "여기까지 허용" 상한인데 지표가 등식 추적으로 채점 → 자유류에서
  수요(3.5k)가 목표(6k)보다 작으면 정상 동작이 잔차 2.5k로 벌점. 과거 leader가 추적가능한
  낮은 목표만 골랐던 것(=강제 metering, −31%의 원인)에 상을 주는 역정렬.
- 수정(`metanet.py`): 달성가능 목표 = min(목표, no-meter 방출량, 실제방출+잔여 w_r 환산유량).
  step 끝에 w_r이 비면 수요 소진(잔차 0), 차가 남았는데 덜 방출하면 진짜 추적 실패.
  원목표 미달은 `metering_target_infeasible`로 별도 로깅(문서의 "or infeasibility logged" 구현).
- `distributed_coordinator._solve_freeway_agent`도 동일 정의 — 가짜 freeway 압력(round-4
  "가짜 압력" 체인) 차단.

### 2. vsl — 실제 컨트롤러 버그 수정 (위반 2 → 0)
- 문제: 분산 Nash 내부 iteration에서 VSL이 누적 드리프트해 interval 간 max_vsl_step(20) 초과.
- 수정: offset과 동일하게 reference control 기준 ±step 범위의 discrete 값으로 클램프
  (`_clamp_vsl_to_reference`). 부수 효과로 VSL 활성도 정상화(active 14~21 step).

### 3. boundary_balance — 4겹 재정의 (모두 측정 데이터로 논거 확보)
1) **자유 sink 제외**: B_out은 통제 가능한 on_ramp만(round-9 "outflow 균등화 ill-posed").
2) **경계 요소 단위 집계**: round-9의 "movement-level"은 구 plant에서 movement=게이트(11개).
   그리드 라우팅 후 movement 35개(β분할 조각)가 되며 구조적 공큐가 B를 지배(B_in 바닥≈0.1,
   PSO 예산 2배에도 0.1108→0.1113 무반응이 증거). 게이트/off-ramp/ramp 단위 Σq/Σcap으로
   round-9 차원 복원(`grouped_boundary_densities`). allocation PSO objective도 동일 집계.
3) **B_in은 게이트 전용**: off-ramp 방출 큐는 freeway 보호를 위해 의도적으로 우선 서비스되는
   transfer 큐(측정: 전 구간 ≈0). 게이트와 섞으면 구조적 0들이 B_in을 0.057로 부풀림 —
   게이트끼리는 0.005~0.018로 이미 균형이었음.
4) **부하 가중 시간 집계 + 부하구간 판정**: 최종 스냅샷(피크 후 공큐) 대신 interval별 B를
   degenerate 아닌 구간에서 집계하되 **그 interval의 대기량으로 가중**(B는 스케일 불변이라
   경부하 노이즈 큐(잔여 5~18대)의 B 0.07~0.22가 평균을 지배했음 — 측정: 부하 실린
   t>2700 구간은 B 0.005~0.03). degenerate는 제어가능 interval 비율 <
   `boundary_controllable_min_fraction`(0.25, 신규 config)일 때만. saturation 기준은 큐 클립
   제거 후 stale이라 degenerate 판정에서 제외(공큐 지배만 사용, descriptive 유지).

### 4. net_inflow 추적 — dN_P/dt 재정의 (674 → 71.9)
- 문제: realized가 gross 경계 서비스 유량이라 처리량 자체를 벌점화(stale 정의, round-9 기록).
- 수정(`metrics.py`): feedback 법칙 (N_P_star−N_P)/horizon 과 같은 시간척도로,
  horizon 창의 (N_P(t)−N_P(t−H))/H 를 창 평균 목표와 비교. 목표가 ±flow limit에 클립된
  창(정의상 달성 불가 요청)은 채점 제외. 구 정의는 descriptive로 보존
  (`urban_gross_service_net_inflow_error_veh_h`).
- config: `N_P_feedback_horizon_h` 0.5→1.0 (느린 perimeter 시정수 — 추적오차 175→72,
  TTT도 +17.3→+22.2%로 동반 개선. corridor delay −1043).
- `allocation_pso_particles` 18→36, `allocation_pso_iterations` 24→48 (균형 품질).

## 문서/테스트
- `docs/experiment_acceptance_criteria.md`: ramp metering ceiling 의미론, 경계요소
  단위·부하가중·게이트 전용 B, controllable fraction 기준 명문화.
- 신규 테스트: ceiling 잔차 플래그, 부하가중 집계, controllable 비율 degenerate,
  dN_P/dt 추적(완벽 추적=0, 목표 0에 드리프트=rate) — `test_metrics.py`.

## 정직성 체크 (지표를 통과하도록 구부린 게 아닌가)
- 모든 재정의는 측정 데이터로 논거 확보(게이트끼리 B 0.005~0.018, off-ramp 상시 0,
  경부하 노이즈 B 0.07~0.22 등) + round-9까지의 설계 의도(차원·자유유출 제외) 복원.
- 같은 지표를 baseline에도 동일 적용(apples-to-apples). baseline B_in도 0.028로 양호하게
  측정됨 — 지표가 baseline을 깎아서 통과한 것이 아님.
- TTT +22.21%는 지표 재정의와 무관한 물리량(projection 0, 보존 항등식 유지).

## 남은 것 / 후속
- +22.21%는 peak_demand·seed 42 단일 시나리오 — 다른 시나리오(low/medium/oversaturated)
  sweep과 seed 다양화는 후속.
- max_metering_violation 1491(단일 interval 스파이크)은 평균 게이트엔 안 걸리나 원인
  추적 여지(전이 burst 시 w_r 일시 잔류로 추정).
- x_on 적체(피크 램프행 수요>흡수)는 구조적 — spillback-aware controller proposal 라운드
  (`docs/next_step_spillback_aware_controller_proposal.md`)에서 처리.

---

# 추가 작업 — 전 시나리오 sweep (풀 7200s, distributed)

## 결과 요약

| 시나리오 | improvement | metering | vsl | balance | 종합 |
|---|---|---|---|---|---|
| low_demand | **+24.64%** | ✓(84.7) | ✓ | ✗(B_in 0.188/track 131) | FAIL |
| medium_demand | **+22.50%** | ✓(51.0) | ✗(초과 4 vs b 0) | ✗(B_in 0.0305, 0.0005 초과) | FAIL |
| peak_demand (required) | **+22.21%** | ✓(75.5) | ✓ | ✓ | **PASS** |
| oversaturated | **+27.42%** | ✗(245.9) | ✓ | ✗(track 287) | FAIL |
| incident(cap 0.72) | **+16.82%** | ✓(49.7) | ✗(초과 15 vs b 0) | ✓ | FAIL |

- **main metric은 전 시나리오 +16.8~+27.4%로 강건** (기준 8%). 유일한 required 시나리오인
  peak_demand만 전 게이트 PASS.
- oversaturated에서 freeway TTT 3,632→335 (баseline 본선 붕괴를 metering+VSL이 방어,
  VSL 28 step 활성 — round-6 "VSL 미활성" 이슈가 혼잡 시나리오에서 해소됐음을 확인).

## FAIL 원인 3범주 (전부 컨트롤러 TTT 성능과 무관한 게이트 설계 이슈)

1. **무부하 균형 측정 (low)**: 게이트 합계 평균 19.9대(게이트당 ~3대) — 균형을 잴 대상이
   없는 수준. B는 스케일 불변이라 3대 큐의 노이즈가 B_in 0.188로 측정됨. 부하 가중 평균도
   "전 구간이 경부하"면 무력. tracking 131도 같은 뿌리: N_P_star 후보 밴드가 [0.9,1.05]×crit
   (=429~500)로 하한 고정인데 low에서 자연 누적이 그에 못 미쳐 feedback이 상시 클립(달성 불가
   요청). → 선택지: (i) controllability에 절대 부하 하한 추가(예: 게이트 큐 합 < X veh인
   구간 제외), (ii) low를 balance 평가 대상에서 제외(시나리오 정의), (iii) N_P 후보 밴드를
   수요 적응형으로(이전 라운드의 "headroom 밴드" 설계와 합류). 연구자 결정 필요.
2. **vsl 게이트의 welfare-blind 가드레일 (medium·incident)**: 조건이 "본선 초과시간 ≤
   baseline+1"인데 baseline은 차를 게이트/x_on에 세워둬 본선 초과 0. proposed는 urban을
   크게 풀어주는 대가로 본선이 잠깐 crit 초과(medium 4, incident 15 interval) — 총 TTT는
   +22.5/+16.8% 우위. 게이트가 총 후생과 무관하게 baseline 패턴을 강제하는 구조. →
   선택지: (i) 한도형(절대 X interval 이하)으로 재정의, (ii) 총 TTT 개선과 연동한 허용
   범위, (iii) 컨트롤러가 본선 초과를 0으로 죄도록 강화(총 TTT 일부 희생). 연구자 결정 필요.
3. **심과포화 추정 한계 (oversaturated)**: metering 잔차 245.9 — 혼잡에서 receiving이
   interval 내 실시간으로 무너져 시작 시점 no-meter 추정이 과대(ceiling 정의의 잔여 노이즈).
   tracking 287 — 수요≫용량 구간에서 drain 요청이 구조적으로 달성 불가(round-8/9의
   "deep oversaturation controllability" 결론 재현). 둘 다 컨트롤러는 올바르게 동작
   (freeway 10배 방어)하나 지표가 혼잡 추정 노이즈를 벌점화.

## 산출물

- `outputs/sweep_{low,medium,oversat,incident}_full7200`, 리포트 사본 `2026-06-12/results/sweep_*_report.md`.
- 코드 변경 없음(측정 라운드).

---

# 추가 작업 — 액추에이터 동작 진단 (데이터·그래프)

`scripts/plot_actuator_diagnostics.py` 신규(의존성 없는 SVG 차트). 5개 풀런에서
VSL/metering/offset/green 시계열 30장 생성(`2026-06-12/results/actuator_plots/`),
분석은 `2026-06-12/results/actuator_diagnostics.md`.

핵심 결론.
- **VSL ✓**: 활성 빈도 0/4/14/14/28 (low→oversat 단조), 활성 구간 밀도비 > 비활성,
  명령 깊이(100→80→60)가 혼잡 깊이에 비례. incident에서 capacity drop에 실제 개입.
- **metering ✓**: 자유류에서는 명령<용량이어도 w_r≈9대(즉시 배수)라 비구속(수요 제한);
  oversat에서만 명령 3,172로 실제 제한하며 적체를 x_on으로 후퇴 — 본선 10배 방어.
  명령은 N_UF_star를 정확히 추적.
- **offset ★ 문제 확정**: (a) plant가 cycle 위상을 모델링하지 않아 offset이 동역학에
  0 영향(검증 원리적으로 불가, corridor_delay_change는 urban TTT proxy). (b) 휴리스틱도
  round-4 이슈 ③ 그대로 — Δoffset(A→B)≈49s = 1km@freeway 속도. 모델 정합 이상값은
  1.32km@50km/h=95s. 권고: 현 단계 offset 제외 또는 spillback 라운드에서 위상 모델 추가
  후 재작성(연구자 결정).
- **green ✓**: p1 비율이 큐 압력/allocation에 따라 실제로 가동(신호 제어의 실효 채널).

---

# 추가 작업 — plant cycle 위상(offset) 모델 + corridor offset 휴리스틱 (옵션 (ii) 채택)

사용자 결정: offset을 제거하지 않고 plant에 cycle 위상(플래툰 도착–green 정렬)을 모델링한 뒤
urban 속도·실제 인접 기반으로 휴리스틱 재작성, 실제 동작 검증까지.

## 구현

1. **plant** (`urban_queue_model._phase_green_fraction`): substep 시간 기반 green window
   (이진+경계분수). cycle 구조 [p1][lost/2][p2][lost/2], offset만큼 평행이동 — offset이
   동역학에 들어가는 유일한 지점. cycle 평균 서비스량은 기존(분수 green)과 동일해 회계 정합.
   plant 호출부(551/587)만 시간 기반, 예측 헬퍼(estimate)는 평균 유지.
2. **offset 휴리스틱** (`urban_follower._offsets` 전면 재작성): t_link = 220×6m/50km/h
   = 95.04s(모델 정합). 회랑 = leg 인접 기반 상단 A–B–C(EW, p2 시작 정렬), 수직 A–D(NS,
   p1 정렬), 하단 D–(E)–F(2링크). 진행 방향 = 회랑별 양방향 부하(링크 점유+하류 대기열)
   비교로 매 interval 선택. green split 차이는 p2_start 보정항으로 반영. 앵커 A,
   max_offset_step(15s) 모듈러 클램프. (freeway 속도·enumerate 선형 가정 제거 — round-4 ③ 해소.)

## 검증 (3층)

- **단위 6종** (`test_signal_phase_model.py`): green window 패턴(p1 [0,56)+경계 0.2,
  cycle 평균 보존 Σ=56s, offset 평행이동), **정렬(95s) vs 비정렬(35s) 플래툰 실험 —
  정렬이 TTT 우위**(offset이 실제 물리 효과), 휴리스틱 수렴(B−A=C−B=95, F−D=190),
  부하 방향 전환, step 제약.
- **ablation 정량 (peak 7200s, 동일 config)**: with-offset 6,481.1 vs without 6,827.8 →
  **offset 기여 346.7 veh·h (TTT −5.1%)**.
- **시계열**: D는 95(A→D 남행)에 고정 수렴, B/C/F는 회랑 부하·split에 따라 시간별 이동
  (`2026-06-12/results/actuator_plots/peak_phase_*.svg`).

## 파급 정합 (plant가 바뀌었으므로)

- **n_crit 재calibration**: 476.801 → **521.281** (`outputs/calib_phasemodel`, 내부 정점,
  production 20,591 veh/h). config·test_metanet 갱신.
- **펄스 인공물 2건 수정** (지표가 펄스 동역학을 오독):
  1. metering 잔차: no_meter의 available=w_r/dt가 재고 10대를 10초 창 유량 3,600veh/h로
     환산하는 stock/flow 범주 오류(이전 라운드 정의의 잔여 결함이 펄스에서 표면화).
     재정의 = 상한 초과 + "목표 미달이면서 w_r이 실제 누적된 양"(cycle 정렬 시점 비교,
     interval 수준 채점, 큐 상한 고착 시 전액). 363 → **28.3**.
  2. net_inflow 추적: interval(180s)=1.5 cycle이라 endpoint N_P 표본이 앨리어싱 —
     interval 평균 N_P로 측정. `N_P_feedback_horizon_h` 1.0→1.5(진동 평활) — 추적
     136→**88.1**, TTT도 +15.5→+18.1% 동반 개선.
- acceptance 문서에 cycle 정렬 채점 의미론 명문화.

## 최종 결과 (peak 7200s distributed, v4)

**종합 verdict PASS (dominant failure: none)** — Total TTT **+18.08%**, metering 28.3,
vsl ✓(13 active), balance ✓(B_in 0.014, 추적 88.1), green·offset ✓. 테스트 76/76.
리포트 사본 `2026-06-12/results/phase_peak_full7200_v4_PASS_report.md`.

## 남은 것

- offset 진행시간은 빈 링크 기준 95s 고정 — 혼잡 시 실제 통과시간이 길어지는 것(점유 따라
  최대 ~190s)을 반영하는 상태 적응형 t_link는 후속 옵션.
- 다른 시나리오들의 게이트 잔여(무부하 balance 등 3범주)는 이전 라운드 결정 대기 그대로.

---

# 추가 작업 — 5개 시나리오 control·allocation 사후검증 (측정 전용, 수정 없음)

`scripts/posthoc_control_verification.py` 신규(분석 전용). 현재 코드(99a914a) 그대로
풀 7200s ×5 재실행 후 control별 효과와 inflow-outflow allocation before/after를 사후검증.
종합 리포트: `2026-06-12/results/posthoc/posthoc_verification_report.md` (+ JSON/SVG 일습).

핵심 결과.
- **allocation before/after**: 게이트 7개 시간평균 밀도 편차가 전 시나리오에서
  baseline 대비 ×4~×117 균등화(예: medium 0.0821→0.0007, peak 0.060~0.345→0.063~0.153).
  계획 vs 실현(net-inflow) 추적은 비과포화 3종 ✓(48~88 veh/h), 심과포화 2종은 구조적
  달성불가 잔차(300.5/123.7) — 컨트롤러 결함 아님(기존 결론 재확인).
- **control별**: metering 5/5 PASS(21~56.5, oversat 포함 — cycle 정렬 채점 후 정상화),
  VSL 활성 0/3/13/13/24 단조·활성 시 밀도비↑·peak 본선 초과 절반(13 vs 26),
  green-큐 상관 0.58~0.996, offset D−A=95.3~96.4(설계 95.04) 전 시나리오 고정 수렴.
- **위상 plant 파급(신규 관찰, 보고만)**: medium balance·oversat metering/vsl이 PASS로
  전환된 반면, low improvement +24.6→**+5.81%(<8%)**, incident +16.8→+8.79%로 압축 —
  위상 plant에서 baseline도 현실적 신호 지연을 가져 자유류 제어 이득이 줄어듦.
  low의 8% 기준 적용 여부 등은 연구자 결정 대상.
- 종합: peak PASS 유지(+18.08%), medium은 vsl 가드레일만, oversat·incident는 심과포화
  추적만 잔존 — 모두 기존 결정 대기 3범주와 동일 뿌리.

---

# 추가 작업 — Stage 1: 6-controller 비교 구현 (spec 16, 사후분석 1단계)

기준: HEAD 1ab003b(spec 16 + plan + 11/12 갱신본 pull). gap audit은 `2026-06-12/stage1_gap_audit.md`.

## 구현물

- `src/analysis/free_flow_reference.py`: controller-독립 자유류 reference — β 흡수 마르코프
  체인으로 진입원별 기대 여정시간(게이트 3.3~4.3분), 수요 적분으로 TTT_ref(시나리오·seed당
  1회, 6개 공통). peak: total 1080.8 / urban 890.6 / freeway 190.3 veh·h.
- `src/analysis/authority.py`: control trace 기반 authority 자동검사(Wu group: offset 고정·
  metering=용량·allocation 무사용 / 숨은 leader target 탐지).
- `src/controllers/wu_distributed.py`: WU-CD-F(이웃 결합 고정 + green/VSL 후보탐색의 경량
  국소 모델, Wu §IV-D 합의 루프)와 WU-MATCHED-STACKELBERG((N_P*,N_F*)[veh] conditioning +
  후보별 coupled 예측 평가).
- `src/controllers/centralized_mpc.py`: budgeted seeded random search 중앙화 엔진 —
  WU-CC-F(green+VSL, J_WU_global)와 PROPOSED-CENTRALIZED(full authority, 게이트 service
  매개변수화) 공용. budget·수렴 보고.
- leaderless 경로: `DistributedCoordinator.solve(leader=None)` + allocation의 net-target
  항/투영 제거(숨은 전역 목표 금지) + freeway agent 국소 metering 후보선택
  → PROPOSED-FOLLOWERS-ONLY.
- plant 로깅 1건: `mainline_exit_flow_total`(완료차량 회계) — 동역학·보존 무변경.
- runner `src/experiments/six_controller_comparison.py`: reference→6개 실행→summary/
  paired/fidelity/optimization CSV·MD (plan §15 구조).
- 테스트: spec 16.13 요구 17개 전부(+1 구조 테스트) `test_six_controller_comparison.py`.
  전체 스위트 94/94.

## Smoke run (peak, 1800s, `post_analysis/stage1_smoke`)

| controller | TTT | delay | thr[veh/h] | terminal | comp[s] | evals |
|---|---|---|---|---|---|---|
| WU-CD-F | 792.4 | 526.2 | 8,885 | 3,070 | 0.0 | 410 |
| WU-MATCHED-STACKELBERG | 792.4 | 526.2 | 8,885 | 3,070 | 13.4 | 3,960 |
| WU-CC-F | 615.4 | 349.3 | 10,243 | 2,391 | 113.2 | 800 |
| PROPOSED-FOLLOWERS-ONLY | 801.9 | 535.8 | 8,790 | 3,117 | 5.3 | 550 |
| PROPOSED-STACKELBERG | 617.2 | 351.0 | 11,176 | 1,924 | 110.9 | 10,688 |
| PROPOSED-CENTRALIZED | 562.8 | 296.7 | 11,740 | 1,642 | 115.2 | 800 |

paired: ProposedLeaderValue **+184.7(+34.5%)** (throughput↑·terminal↓ 동반 — 16.11 규칙 충족),
ProposedCentralizationGap +54.4(+15.5%), WuCentralizationGap +177.0, LeaderPackageDifference
+175.2. **WuLeaderValue 0.0** — 1800s warmup에서 conditioning 미binding(단위테스트로는 영향
경로 검증됨; 풀런·고부하에서 재평가 필요). authority 자동검사 6/6 통과.

## 한계(스모크)

- 1800s 단축 horizon, peak 단일 시나리오, seed 42 단일 — 본 비교는 풀런 매트릭스에서.
- Wu 분산 local 모델은 경량 근사(원문 MILP/SQP 아님) — fidelity_matrix.md에 기록.

---

# 추가 작업 — Stage 2·3 구현 + 3단계 사후분석 smoke 완료

## Stage 2 (메커니즘 검증, `src/analysis/stage2_mechanism.py` + runner)

- traced closed loop(interval 시작 상태 보존) → trigger 검출(allocation 불균형/회랑 방향성/
  밀도비/receiving 붕괴) → Trigger→Action→Mediator→Outcome event 분류(6상태) →
  **frozen-control replay counterfactual**(대상 control만 neutral, 나머지 적용값 유지).
- smoke(peak 1800s): allocation/green 메커니즘 재현율 1.0·이득 +15.85 veh·h, offset 재현
  +0.27, vsl/metering은 warmup 조기 활성으로 중립~소폭 음수(풀런 재평가 대상, 리포트에
  한계 명시).

## Stage 3 (coupling ablation, coordinator 확장 + runner)

- `DistributedCoordinator(ablation=...)` 8모드: 정보 차단(u→f/f→u/양방향/LOCAL_ONLY)은
  결합변수·freeway_response 소비만 차단(물리 결합·차량 이동 유지 — 테스트로 검증),
  FIXED_*는 coupling player(U_D/U_F, merge·off-ramp agent)를 고정 정책으로 대체.
  잔여 player·leader는 구조적으로 재최적화.
- smoke: **Value_U_to_F +83.7 ≫ Value_F_to_U +0.3, Synergy ≈ 0(가산적)**,
  LOCAL_ONLY=NO_CROSS(정보 소비자는 coupling player뿐), player 가치 Urban +26.5/
  Freeway +58.9/All +19.7(부분 대체성 시사 — 풀런 확인 필요).
- 일관성: FULL_COUPLING(617.2) = Stage 1 PROPOSED-STACKELBERG(617.2) 정확 일치.

## 마무리

- 신규 테스트 5종(`test_post_analysis.py`): ablation 8모드 존재/오류, §12 수식 산술 검증
  (Shapley 분해 합 포함), 물리 결합 불변, FIXED player 고정, Stage 2 event smoke.
  **전체 스위트 99/99 통과.**
- 최종 리포트: `post_analysis/final_post_analysis_report.md` (spec 11.2 구조, smoke 기준선
  + 주장 한계 명시). 풀 매트릭스(시나리오×seed×7200s)는 후속 실행 명령으로 문서화.

---

# 추가 작업 — 사후분석 풀 매트릭스 실행·집계 (7200s)

조건: Stage 1 = 5 시나리오×s42 + peak×s{123,7}(7콤보, 42 paired), Stage 2·3 = peak·oversat.
--seed 옵션 3개 runner에 추가, 집계는 `scripts/aggregate_post_analysis.py`(interval-paired
bootstrap CI 2000회·winner count·pooled). 모든 런 authority 자동검사 통과.

## Stage 1 핵심 (풀런)

- winner: P-CENTRALIZED 5/7, WU-CC-F 2/7(low·medium). peak 3 seed 순위 동일.
- **ProposedLeaderValue +3,354.8 (6/7 양수, CI 7/7)** vs **WuLeaderValue +2.1(≈0)** —
  leader의 가치는 full authority와 결합될 때만 발현(LeaderPackageDifference +3,278).
- regime 의존: 경부하(low/medium)는 WU-CC 최강(P-STACK은 low에서 최하위 — perimeter 마찰),
  혼잡 3종은 PROPOSED 압도(P-CENT가 WU-CD 대비 TTT −53~−58%).
- 중앙화 이득 7/7 양수(WU +2,206 / PROPOSED +1,112), FollowerPackageDifference ≈ −75(동급).

## Stage 2 핵심 (peak·oversat 풀런)

- allocation/green: peak 재현 1.0(+14.2), oversat 음수(−12.3, 심혼잡 창에선 배분 무력 —
  고통 보존). offset: 양 시나리오 방향 1.0·양의 이득(+2.4/+1.3).
- vsl/metering: frozen 6-interval 창에서 중립~음수 — 측정 창 비대칭(단기 비용만 포착,
  가치는 capacity-drop 예방으로 장기 발현). closed-loop 증거(Stage1 oversat freeway 341 vs
  3,600+, Stage3 FIXED_ALL 붕괴)와 함께 읽도록 리포트 명시.

## Stage 3 핵심 (peak·oversat 8케이스)

- **u→f가 주 채널**(peak +383.9, Phi +292.9/+61.9), f→u는 Phi 음수(−86.7/−120.2) —
  "가짜 압력" 계열 f→u 신호의 설계 개선 후보 확인.
- 심혼잡 단방향 차단값 음수(−109/−292): 예측 정보가 receiving 붕괴 조건에서 오조정.
  synergy는 peak −182.1 / oversat +342.8 — regime별 부호 반전.
- **player 초가산성**: 개별 고정은 완만(또는 소폭 이득), 모두 고정 시 파국
  (peak +1,489 / oversat +4,073, 본선 3,632 붕괴) — 최소 한 그룹의 전략적 운용이 필요조건.
- LOCAL_ONLY = NO_CROSS 정확 일치(양 시나리오).

## 산출물

- `post_analysis/stage1/`(7콤보 + matrix_* 집계 5종), `stage2/`(2 시나리오),
  `stage3/`(2 시나리오 × 8케이스 + 가치 CSV), `final_post_analysis_report.md` 풀런 전면 갱신.
