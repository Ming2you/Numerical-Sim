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

