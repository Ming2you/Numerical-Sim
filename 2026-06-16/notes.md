# 2026-06-16 작업 노트 — A″-1: urban 유한 출구용량(boundary_out)

## 목표
urban 네트워크 출구(boundary_out)를 유한 용량으로 제약. 자유 sink(시간지연만)에서
유한 출구용량 게이트로 전환해 off-ramp 홍수가 urban을 포화시키고, 유입 차단 시 urban이
회복되는 채널을 연다(roadmap §4 A″-1). Wu의 유한용량 실제 도시망에 충실한 correctness 수정.

## 변경 (파일:라인)
1. `src/models/urban_queue_model.py` `urban_substep`
   - release pop 루프(~683행): sink(boundary_out) 링크는 release pop에서 storage available을
     복원하지 않고 `continue` — 차량을 out 링크 점유 상태로 유지(in-transit→링크 끝 대기).
     내부 링크는 기존대로 복원(다음 노드로 이동).
   - 유한 출구용량 게이트(~693행 신설): 각 sink 링크에서 시스템 이탈량 =
     `min(out 링크 점유, boundary_out_capacity_veh_h·T_u_h)`. 못 나간 차량은 점유로 남아
     `_effective_available_space`(receiving 게이트)에 반영 → exit movement 막힘 → backup이
     grid·off-ramp 상류로 전파. `boundary_out_sink_veh`에는 실제 이탈량만 기록(보존 유지).
   - `boundary_out_capacity_veh_h <= 0`이면 자유 sink(점유 전량 이탈)로 동작(하위호환).
2. `src/models/state.py` NetworkConfig: `boundary_out_capacity_veh_h: float = 500.0` 추가.
3. `src/config/default.yaml` network: `boundary_out_capacity_veh_h: 500.0` 추가.

## 핵심 버그(개발 중 발견·수정)
초기 구현은 release pop이 sink 링크 available을 복원하면서 exit gate가 또 occupancy를 빼,
release된 차량이 점유에서 사라지고 sink로도 기록 안 돼 **보존 위반**(residual 3.4 veh).
→ sink 링크 release pop을 건너뛰어(`continue`) 차량을 점유로 유지하도록 수정. residual≈0 회복.

## exit_capacity 적정값 = 500 veh/h (out 링크당)
- 근거: 정상 운영(test 시나리오 us=1.0, split=0.06)의 개별 out 링크 정상상태 유출은 최대
  ~278 veh/h. cap=500은 그보다 충분히 커서 binding하지 않음(정상상태 N_P가 무제한 sink와
  동일: cap≥500 → N_P=1990, cap=400 → 2094로 binding 시작). exit movement 포화유율
  (green_fraction 0.467 × movement_capacity 1400 ≈ 653 veh/h)보다 작아 강한 off-ramp 홍수
  시에는 출구가 binding함. "정상엔 무영향, 홍수엔 binding"을 동시 만족하는 값.
- cap 200~700 전 구간에서 G2 결과 동질(강한 홍수 regime에선 어느 값이든 binding). 500은
  정상 운영 안전마진을 둔 선택.

## 단계 게이트 결과 (직접 closed-loop, uncontrolled 균등 green 계측)
### G1 보존 (하드)
- substep 보존 항등식 residual: cap=0/500 모두 **2.27e-13 ≈ 0**.
- `test_grid_routing` 10/10 통과(substep·closed-loop 보존 포함).
- 전체 `unittest discover` **113/113 통과**.

### G2 regime 형성 (us=0.2, freeway_scale=3.0, off_ramp split=0.6, cap=500, 150 step 정상상태)
주의: S_eff 모델에서 backup은 grid storage 점유가 아니라 movement 점큐로 잡히므로(b8a029a),
포화는 **유효 점유**(1 − S_eff/cap, movement 점큐 포함)로 측정. off-ramp storage는 in-transit
점유라 그대로 측정.
- (a) 포화: off-ramp storage **100%**(max·mean), off-ramp 하류 grid 유효점유 mean **99%** — ≥50% 충족.
- (b) 회복: off_ramp split=0 차단 시 off-ramp storage 100→**0%**, 하류 grid 유효점유 99→**34%**
  (−0.65), 보호영역 누적 N_P **2883→1258 (−1626, 56% 회복)**.
- "urban 혼잡 주원인=off-ramp 홍수, 차단 시 relief" 회복 채널이 열림. us=0.3에서도 N_P 47% 회복.
- urban_scale은 **낮게(0.2~0.3)** 둬야 함 — urban 자기 수요가 높으면(us≥0.4~1.0) grid가 자체
  포화해 off-ramp 차단해도 안 풀림(drain-blocked, roadmap §3 경고). off-ramp 홍수가 포화의
  주원인이 되도록 자기 수요를 낮춤.

## 비고 / 다음 단계
- N_P=1990(정상 운영, us=1.0)은 변경 전후 동일(cap 무영향). n_crit 재calibration은 A″-5에서.
- VSL 작동 자체는 A″-2/3(메커니즘 B 제거 + λ-recovery coupling). 여기선 regime만 형성.
- roadmap §4 A″-1 부수 항목("grid_link_storage_veh override가 자동유도 내부 링크에 미반영")은
  자동유도 링크가 setdefault로 grid_link_storage_veh(220) 채택 중이라 별도 결함 아님(점검 완료).

## 커밋
- (아래 커밋 해시 참조) push 금지.
