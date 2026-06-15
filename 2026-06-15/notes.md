# 2026-06-15 작업 노트

## 목표
off-ramp 배출을 Wu et al.(2022) 식3에 충실하게 — 하류 수용공간에 게이트되도록 — 고쳐서,
하류 arterial 정체 시 off-ramp 큐가 backup되어 capacity-drop(식22, λ_eff 차로감소)이 실제 발동하고,
그 위에서 VSL이 의미를 갖게 만든다.

## 진단 (코드 추적 완료)
- `src/models/urban_queue_model.py::schedule_offramp_arrivals`(244-271)가 off-ramp 유입을
  storage에서 즉시 차감한 뒤 고정 시간지연(`_link_delay_steps`) 후 arrival buffer(→off_ramp
  movement 큐 β분할 주입)와 release buffer(→storage 점유 복원) 양쪽에 동시 스케줄한다.
- release(558-565)는 도착 step 도래 시 하류 정체와 무관하게 무조건 storage를 복원한다.
- 즉 off-ramp storage는 "막히면 쌓이는 큐"가 아니라 "지연만 주는 transit 링크"라
  점유가 self-limiting(평형 ~22%)이고, 이 점유가 `metanet.py::effective_lane_profile`(127)의
  λ_eff를 구동하므로 capacity-drop이 발동 안 하고 VSL이 inert다.
- 한편 off_ramp movement(`D_off*`,`F_off*`)는 stage 2(urban_substep 650-694)에서 이미
  green + 하류 receiving_link 수용공간 게이트로 방출된다. 문제는 stage 1(storage→movement)이
  receiving 무관 시간지연이라는 점.

## 설계 (Wu 식3 충실, 차량보존 최우선)
storage를 Wu off-ramp 큐 n_{m,d}로 취급한다. 고정지연 자동 release를 폐지하고,
urban_substep 안에서 storage를 off_ramp movement 큐로 **하류 receiving 공간에 게이트**해
드레인한다. 드레인량 = Σ_movement min(β·storage_avail_share, receiving_space_share).
하류(receiving_link) 정체 시 드레인이 막혀 storage 점유가 누적 → λ_eff↓. 혼잡 해소 시 복원.

차량보존: storage occupancy도 movement 큐도 둘 다 urban_total_vehicles에 포함되므로
storage→movement 이동은 점유 중립(보존 안전). schedule_offramp_arrivals는 storage 차감
(=점유 생성, inflow=accepted)만 유지, 자동 release/arrival 스케줄 제거.

## 단계 게이트
- G1 보존: residual=0 테스트 통과.
- G2 spillback: 하류 정체 시 off-ramp 점유율 ≥50% & λ_eff<freeway_lanes 측정 입증.

## 진행

### 구현 (커밋 1)
- `urban_queue_model.py::schedule_offramp_arrivals`: 고정지연 arrival/release 스케줄 제거,
  storage 점유 생성(accepted=inflow)만 유지.
- `urban_queue_model.py::_drain_offramp_storage`(신규): storage→하류 receiving_link를
  Wu 식3(green·포화유율·β몫 점유·receiving_space의 min)로 게이트 방출. 점유 중립(보존).
- `urban_queue_model.py::urban_substep`: stage 2 직전에 `_drain_offramp_storage` 호출,
  off_ramp movement는 stage 2 green 루프에서 제외(storage가 직접 방출).
- `test_grid_routing.py::test_offramp_vehicles_join_grid_not_terminate`: 신 메커니즘
  (arrival buffer 미사용, storage 드레인)으로 갱신.

### G1 보존 — 통과
- test_substep_vehicle_conservation_identity, test_closed_loop_interval_conservation_with_offramp
  모두 ok (residual=0, places=5~6). 전체 113 테스트 통과.

### G2 spillback — 통과 (수치)
하류 그리드 링크(D_to_A/D_to_E/D_left_out) 강제 정체 + OR_D_W 지속 유입:
- occ: step0 4.2% → step10 46.6% → step20 100% (≥50% 식22 발동).
- λ_eff_FW_W: 1.999 → 1.650 (< freeway_lanes=2).
복원: 하류 정체 해소 시 occ 98%→26%, λ_eff 1.702→1.955 (식22 복원 확인).
- calibration n_crit: 280.447 → 277.754 (plant 변화 확인, step5에서 갱신).

### Step 5 n_crit 재calibration — 완료 (커밋 2, 66d8c1a)
- 전체 calibration(peak_demand, scales 0.5~3.0, T=1800): n_crit 521.281→778.703,
  max production 35230 veh/h. config N_P_crit_veh 갱신, N_P_star_range 상한 600→850.

### Step 6 spillback 시나리오 — 게이트 막힘(자연 형성 불가), 수치 보고
**closed-loop에서 demand만으로는 off-ramp 점유 ≥50%가 형성되지 않는다.** 측정:
- capacity_drop(urban 2.5/fw1.45/split0.45) fixed baseline: OR occ 최대 4.0%, λ_eff 2.0.
- 공격적(urban 3.5/fw1.6/split0.7): OR occ 4.0%, grid rejoin 링크(D_to_A 등) 8~10%.
- D/F off-ramp phase(p1) green 최소 강제: OR occ 6.2%.
- grid_link_storage 30·movement_cap 400 축소: OR occ 3.6%(D_to_A는 220 유지 — 후술).

**왜 안 쌓이나(근본 원인, 계측):**
- off-ramp 유입이 작다. offramp_flow_FW_W ≈ 382~450 veh/h → 180s interval당 accepted ~40대.
  storage cap 120 대비 미미하고, 드레인(green·movement_cap·T_u, 3 rejoin movement 분산)이
  매 interval 36~60대로 유입을 따라잡는다. 점유가 0.5~4.4 사이 진동에 머문다.
- 자연 정체가 안 생긴다. boundary_out이 자유 sink고 grid green 용량(1400 veh/h·0.8)이
  수요 처리량을 크게 상회해, urban_scale 3.5에서도 모든 grid 링크 점유 ≤10.4%.
  rejoin 링크(D_to_A/D_to_E/D_left_out)가 절대 안 차므로 receiving 게이트가 안 닫힌다.
- 60대(50%)까지 쌓으려면 3개 rejoin movement의 하류가 동시에 다수 interval 동안 포화해야
  하는데, 자유 sink 토폴로지에서 불가능. (wu2022 ref §8 line 206의 "이 망은 심한
  capacity-drop을 잘 만들지 않음" 사전 진단과 일치.)
- 부수 발견: `grid_link_storage_veh` override가 D_to_A 등 자동유도 내부 링크에 반영되지
  않음(여전히 220). __post_init__에서 setdefault로 추가되는 시점/override 순서 이슈로
  추정. 이번 작업 범위 밖이나 기록.

**결론**: 메커니즘은 정상(G2 강제정체 100%·λ_eff 1.65, 복원 26%·1.955로 입증). 그러나
이 망은 demand 시나리오만으로 자연 spillback을 못 만든다. 따라서 step7(VSL ablation,
실제 spillback 필요)·step8(메커니즘 B 제거, VSL 실물리 작동 전제)·step9(test_c 자연
spillback)는 **자연 spillback 부재로 진행 불가** — forced-state 검증(현 test_c 방식)만
정직한 입증 수단이다. 지시의 단계 게이트("안 오르면 중단·보고")에 따라 중단하고 보고함.


