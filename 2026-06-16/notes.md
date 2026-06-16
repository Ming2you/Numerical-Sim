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

---

# 2026-06-16 (오후) — n_crit 재calibration (4-세그먼트 토폴로지 반영)

## 배경
Codex가 push한 `e94cd1f`(상류 plain seg0 추가, freeway_segments_per_link 3→4)로 plant가
바뀌었는데 leader의 `N_P_crit_veh`는 옛 값(725.897) 그대로였다. smoke 테스트가 출력하던
`n_crit=212.121`은 정상 calibration이 아니라 **smoke 인자(scale 0.75,1.0 / T_total 180s)**
산물이라 무효. 실제 값을 재확인.

## 정상 calibration 결과 (peak_demand, scale 0.5~3.0, T_total 7200)
- `calibrate_setpoints.py` argmax: **n_crit=556.081** (max production 34601 @ scale 3.0).
- MFD binned 곡선도 accumulation ~528에서 production 정점(26588) 후 급락(641→16923) —
  congested branch 확인. binned 정점(528)과 argmax(556) 일치 → **n_crit≈530~560 신뢰**.
- 옛 725.897은 정점을 지난 congested branch라 과대(leader setpoint 밴드가 항상 정점 위 →
  perimeter 과소개입). 354.809(state.py 기본)는 config가 덮어써 미사용.

## 변경 (파일:라인)
1. `src/config/default.yaml`: `N_P_crit_veh: 725.897 → 556.081` (+ 재calibration 근거 주석).
2. `src/tests/test_metanet_equations.py:89`: config 단언 725.897 → 556.081.
3. `src/tests/test_constraints.py` `test_leader_candidate_budget_...`: previous N_P_star
   하드코딩 750.0 → `0.95×cfg.leader.N_P_crit_veh`(밴드 중앙). 미래 재calibration에 견고.

## WU VSL 확인 (요청)
- **중요**: n_crit은 leader 전용. WU-CD-F는 `leader_enabled=False`라 n_crit이 WU VSL에 무영향.
- WU-CD-F peak 3600s 재실행: total TTT=2474.4 (재calibration 전후 동일 — 무영향 확인).
- VSL 활성: `seg0`만 — FW_E 17/20, FW_W 15/20, min 50 km/h. seg1~3은 항상 100.
- (정정 아래 참조) 최초엔 "net-neutral 재확인"이라 적었으나, 그건 3-seg(이전) vs 4-seg(이후)
  교란된 비교였고 틀렸음.

## ★ 정정 — VSL은 net-neutral 아님(같은 토폴로지 counterfactual)
앞 절의 "net-neutral"은 오류. 근거가 3-세그먼트(2474.438) vs 4-세그먼트(2474.384)
**교란 비교**였고, "entry 큐로 밀린다"도 측정 아닌 추론이었다. 같은 4-세그먼트에서 VSL만
on/off한 깨끗한 counterfactual 결과:

| 시나리오 | VSL 활성 | Δtotal(자유−고정) | % | Δurban | Δfreeway |
|---|---|---|---|---|---|
| low_demand | 0/20 | 0.0 | 0.00% | 0.0 | 0.0 |
| medium_demand | 4/20 | −6.4 | −1.20% | +0.2 | −6.6 |
| peak_demand | 17/20 | −48.6 | **−1.93%** | −28.0 | −20.6 |
| oversaturated_demand | 0/20 | 0.0 | 0.00% | 0.0 | 0.0 |
| incident_or_capacity_drop | 16/20 | −45.1 | **−1.99%** | −25.4 | −19.6 |
| capacity_drop | 0/20 | 0.0 | 0.00% | 0.0 | 0.0 |

- VSL은 **혼잡하되 회복 가능한** regime(medium/peak/incident)에서 total을 **실제로 줄인다**(−1.2~2.0%).
  저수요(혼잡無)·과포화/capacity_drop(metering 불가)에선 VSL 자체가 안 켜지고 효과 0 — 정직한 한계.
- peak에서 **urban·freeway가 동시에 개선**(−28/−20.6) — tradeoff 상쇄가 아니다.
- **urban green은 불변(Δ=0)** — urban agent가 결정을 바꿔서가 아니라, VSL 상류 metering이
  freeway→off-ramp→urban 유입을 줄이는 **plant 물리**로 urban이 이득. entry 큐(mainline_origin_queue)는
  오히려 −4.8로 감소(밀려나지 않음 — 이전 추론 반증).
- 메커니즘: off-ramp capacity-drop 회복 아님(storage binding=0, lane loss~0). 순수 mainstream
  metering(CTM receiving 하 하류 유입 완화). Codex의 상류 plain seg0 추가가 metering 지점을
  만들어 VSL을 비로소 유효화. (이전 세션 net-neutral은 그 seg0 없던 옛 토폴로지 결과.)

## 게이트
- 전체 `unittest discover` 통과(아래 실행 확인). 수정 전 1건 실패(750.0 하드코딩)→상대값으로 해결.

## 다음
- proposed(leader) 4-controller는 n_crit 556으로 **재실행 필요**(현 +26~37%는 옛 n_crit 기반 잠정치).
- capacity_drop에서 proposed 열위 원인(leader) 진단.
