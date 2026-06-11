# 2026-06-11 작업 노트 — 그리드 내부 라우팅 구현 (turning ratio β 자연 분산)

기준 문서: `docs/grid_routing_proposal.md` (spec `docs/spec/03_traffic_models.md` §3.3, 특히 §3.3.5).

## 무엇을 바꿨나

### 신규: `src/models/grid_topology.py`
- proposal §1 leg 표를 `default_grid_node_legs()`로 코드화 (A·B·C·D·F 4-leg, E 3-leg T자).
- movement(o,s,d)·β·내부 directed link(14개)·approach 매핑을 **leg 인접 그래프에서 자동 유도**
  (hand-list 금지 — 교차로 78 movement를 손으로 나열하지 않음).
- β 직진우대: 직진(들어온 leg의 정반대 방위)=0.5, 나머지 가용 outgoing 균등, U-turn=0, Σ_d β=1.
  직진 leg 없으면(E의 N approach) 균등. D·F 램프 leg(S)는 4갈래 — 직진 몫은 on_ramp W/E 균등
  분할(각 절반), off_ramp W/E는 각각 별도 incoming. off→on(같은 S leg 회귀)은 U-turn으로 제외.
- 2-phase(NS/EW) 확정: phase = incoming approach 축(N·S→p1, E·W→p2), 회전·직진 무관.
  램프 movement도 동일 규칙으로 재배정(off_ramp는 S 유입→p1, on_ramp행은 incoming 축).
  E는 phase=""(비통제 통과, green=1 상당).

### `src/models/state.py`
- `NetworkConfig.__post_init__`: `grid_node_legs`/`turning_ratios`/`urban_movements`/
  `on·off_ramp_to_movement`가 비어 있으면 자동 유도. turning_ratios Σ=1 검증.
- `on_ramp_to_movement`/`off_ramp_to_movement`: `Dict[str, str]` → `Dict[str, List[str]]` (1:N).
- `grid_link_storage_veh: 220.0` 신규 — 내부 14개 링크 storage 자동 추가.
- `TrafficState.initial`: 게이트(boundary_in) 큐만 초기 20대를 β로 분배, 내부 큐 0.
- `protected_accumulation_veh` 확장: N_P = 링크 in-transit 점유(cap−available)
  **+ 보호영역 내부 movement 큐(internal/boundary_out/off_ramp kind)**.
  게이트 큐(boundary_in)·on-ramp 접근 큐(x_on)는 기존대로 경계 미터링 큐라 제외.
- `ControlAction.fixed`: legacy link-level allocation을 movement-level 합과 일치시킴.

### `src/models/urban_queue_model.py`
- `approach_routing(cfg)`: approach source(내부 링크/게이트 in링크/off-ramp storage) →
  [(movement, β)] 매핑. **arrival buffer key를 movement → approach source(링크)로 변경.**
- `urban_substep` 재작성:
  - 링크 끝 도착분을 β[o,s,·]로 여러 (o,s,d) movement 큐에 분할(단일 next_movement 체인 아님).
  - 게이트 수요·off-ramp 복귀 모두 같은 β분할 체인으로 주입.
  - boundary_out 링크 끝 도착 = **유일한 urban-side system sink** (`boundary_out_sink_veh`).
  - ramp행 movement(어느 kind든 spec["ramp"] 보유)는 ramp 공간을 비례 배분해 w_r로 transfer
    (소멸 금지 — freeway 핸드오프). off-ramp destination="grid" 종료 경로 완전 제거.
  - 보존 카운터 신설: `urban_gate_inflow_veh`, `urban_demand_arrivals_veh`,
    `boundary_out_sink_veh`, `urban_link_occupancy_veh`, `urban_total_vehicles_veh`,
    `movement_queue_projection_protected_veh`.
- `schedule_offramp_arrivals`: arrival을 storage 링크 key로 예약(도착 시 β분할).
- `estimate_onramp_green_release_flows`·sync 함수: ramp당 movement 리스트 합산으로 변경.
- `_storage_occupancy`: 링크 점유만(큐 이중계상 방지 — TTT 계산 보정).

### `src/controllers/`
- `freeway_follower.py`: ramp 큐 압력·경량 x_on→w_r 예측을 movement 리스트 합산/비례 배분으로.
- `distributed_coordinator.py`: agent의 ramp/off-ramp 소유 판정 1:N 대응,
  legacy out-링크 allocation 합산에 kind 필터(corner boundary_in→out 중복 산입 방지).

### `src/config/default.yaml`
- `urban_movements`/`on_ramp_to_movement`/`off_ramp_to_movement` hand-list 제거(자동 유도).
- `A_entry_*`(7개)·`D_from_OR_*`(4개) storage 제거(구 모델 전용), 내부 14개 링크(220.0) 추가.
- `N_P_crit_veh`: 166.045(임시) → **476.801** (재calibration), `N_P_star_range` 상한 500→600
  (crit×1.05=500.6이 구 상한을 넘어서 정합 조정).

### 테스트
- 신규 `src/tests/test_grid_routing.py` (10개): Σβ=1, U-turn=0, 직진우대 값, 2-phase 배정,
  arrival→β분할 분기, off-ramp 비소멸 합류, substep/interval 차량 보존 항등식
  (Δurban = 유입−sink−ramp전이−projection; residual=0), on_ramp 전이=w_r 유입 일치,
  no-control 흐름(게이트→그리드 14링크 전부 점유→출구/램프).
- `test_constraints.py`: 구 movement 이름 → 자동 유도 이름으로 갱신(의도 유지),
  게이트→ramp 직결 신경로를 반영해 전제 보강. `test_metanet_equations.py`: N_P_crit 476.801.

## 결과

- **단위테스트 66/66 통과** (codex 런타임 python, `-m unittest discover -s src/tests`).
- **보존 검증**: 1 control interval에서 (수요유입+off_ramp복귀+ramp외생) − (sink+ramp전이)
  − projection = Δurban, residual 0.0 (정확 항등식).
- **재calibration** (`outputs/calib_gridrouting`, peak_demand, urban-scales 0.5~3.0, T=1800):
  - n_crit = **476.801 veh**, 최대 production 20045 veh/h (scale 3.0, t=720s).
  - MFD가 자유류·혼잡 양 분지를 모두 샘플링(누적 ~480–520에서 정점 후 production 하락) —
    proposal §7 기대대로 그리드 라우팅 도입 효과.
- **distributed 진단 run** (`outputs/diag_gridrouting_distributed_ncrit477`, peak_demand, 900s):
  흐름 정상(게이트 유입→그리드 통과→sink 742 veh/on-ramp 전이 1076 veh, off-ramp 복귀 226 veh
  거부 0, projection 0). baseline도 동일하게 보존.

## 이슈 / TODO

- **distributed MPC improvement −7.7% (FAIL)**: 그리드 라우팅 도입으로 plant가 바뀌어
  leader/follower 휴리스틱이 구 모델 기준으로 남아 있음(short 900s run 기준).
  → 후속: leader 후보 밴드·N_P feedback·allocation 가중 재튜닝, boundary balance 지표 재평가
  (proposal §7 후속 항목 그대로: `docs/boundary_balance_acceptance_proposal.md` 재검토 뒤 진행).
- 외생 on-ramp 수요는 ramp당 on_ramp movement들에 균등 분배(방향 정보 없음) — 필요 시 config화.
- `D_R_W` 등 ramp 접근 storage 링크는 현 모델에서 점유 미사용(기존과 동일, receiving_link
  명목 유지). 정밀화하려면 x_on→D_R_W transit→w_r 3단계로 확장 가능.
- 4-phase 정밀화는 proposal대로 후속 옵션(현행 2-phase 확정).
