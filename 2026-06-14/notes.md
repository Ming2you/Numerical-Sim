# 2026-06-14 작업 노트 — WU-CD-F 치명 2건 수정

## 목표
WU-CD-F(Wu et al. 2022 분산제어 벤치마크)의 치명 결함 2건 수정.
1. 분산 협상 단발 퇴화(residual=0, iteration=1 즉시 종료).
2. freeway 항상 max VSL(no-control과 동일).

## 변경 파일
- `src/models/urban_queue_model.py`: 신규 헬퍼 `estimate_onramp_reservoir_inflow`
  (기존 `estimate_onramp_green_release_flows` 바로 아래, ramp_space 캡만 제거).
  기존 함수는 다른 호출처(leader/freeway_follower/distributed_coordinator)가 있어 불변.
- `src/controllers/wu_distributed.py`:
  - `__init__`/`_build_coupling_maps`: `_upstream_leaving_map`·`_offramp_drain_flow`·
    `_last_offramp_flow` 토폴로지 자동 유도 캐시. `_signal_leaving_rate` 헬퍼.
  - `_coupling`: u_on을 reservoir inflow로, arr를 상류 후보 green leaving(주)+점유(보조<1)로,
    off-ramp inflow를 `_last_offramp_flow` 재사용으로 교체(후보 반응형).
  - `_solve_freeway_agent`: storage-aware probe(`_update_probe_offramp_storage`),
    비-Wu density_penalty 항 제거, 선택 VSL off-ramp flow를 `_last_offramp_flow`에 캐시.
  - `_solve_followers`: Jacobi 스냅샷 고정 + under-relaxation(α=0.5) + S_max=min(.,5).
- `src/experiments/six_controller_comparison.py`: FIDELITY_MATRIX_MD WU-CD-F 행 갱신.
- `docs/spec/16_six_controller_comparison.md` §16.4: Jacobi 후보 반응형 coupling + f↔f moot.
- `docs/wu2022_distributed_reference.md` §8: density_penalty 제거 + storage-aware probe.
- `src/tests/test_six_controller_comparison.py`: `WuDistributedFixesTests` 5개 추가.

## 검증 수치
- 전체 단위테스트: `unittest discover -s src/tests` 113개 통과(OK).
- 신규 5개(a,b,c,d + 캐시) 통과.
- (a) 단위: 혼잡 state `_solve_followers` iterations=5, 1-iter residual=0.00827>tol(0.001).
- (b) 단위: coupling y 변화 key 2개(arr_D_p1 922→1450 등).
- (c) 단위: prev_vsl=70 혼잡에서 VSL이 max-0.5 미만 유지(작동).
- (d) 단위: off-ramp storage 98% state에서 λ_eff_last≈1.71<2.0(capacity-drop 진입).
- (f) authority_ok=True.
- (h) 방향성(peak fs=1.3, T=1800s closed-loop):
  - 수정 전: iter>1 = 0/10(전부 단발), max_iter=1.0, total_delay=622.7.
  - 수정 후: iter>1 = 9/10, max_iter=5.0, total_delay=622.7.

## 위험요소 실현 여부
- **발산**: 없음. under-relaxation+점유 보조항(가중0.5)+S_max=5로 안정. 수렴(converged=True).
- **VSL 미작동(closed-loop)**: 부분 실현. capacity-drop이 발생하는 state에서는 probe가
  올바르게 VSL을 작동시킴(단위 c/d 입증). 그러나 peak/oversat closed-loop에서는 off-ramp
  storage 점유 최대 ~3.6%(λ_eff≈2.0)로 capacity-drop이 자연 발생하지 않아 VSL이 max 유지.
  - 원인: off_ramp_split_ratio=0.06으로 작고 drain(receiving-space 제약 포함)이 유입을 늘
    소화 → storage 정체 안 됨. 이는 시나리오 특성이지 코드 결함이 아님.
  - 대응: drain receiving-space 캡까지 적용(위험요소3 fallback 1단계). 그 이상(drain 인위
    축소)은 plant 동역학 왜곡이라 미적용(plan "plant 보존식 변경 금지").
  - 의미: total_delay 불변은 "Wu 권한(green+VSL)의 정직한 한계"로 해석 가능(plan 의도 충족).
    협상 퇴화는 해소됐고, 이 시나리오에서 VSL로 줄일 capacity-drop이 없을 뿐.

## TODO (이 작업 이후, plan §이후순서)
1. λ_eff(t) 수정 — leader.py/centralized_mpc.py objective 고정 차로수 → λ_eff(t).
2. 4-controller 풀 매트릭스 7200s 재실행.

## 커밋
a241d84 신규 헬퍼 / 19089f1 캐시 / 6c85cc5 u_on 교체 / 0acb4fc storage probe /
0d3f85a density_penalty 제거+drain 캡 / e077e77 coupling+Jacobi / 7413b2b 문서 / a79b3af 테스트

---

# 2026-06-14 (2) 작업 노트 — capacity-drop 유발 시나리오 추가 + VSL 반응 측정

## 목표
WU-CD-F의 freeway VSL이 작동하는 capacity-drop 무대를 시나리오로 추가하고, 실제로 VSL이
반응하는지 실측. (현 peak/oversat/incident에서는 off-ramp 점유 최대 ~3.4%로 미발동.)

## 변경 파일·함수·라인
- `src/models/demand.py`:
  - `ScenarioConfig`에 `off_ramp_split_ratio_override: Optional[Dict[str,float]]=None` 추가(L26 부근).
  - `ScenarioConfig.from_mapping`이 yaml의 `off_ramp_split_ratio_override`를 파싱.
  - 신규 `apply_scenario_network_overrides(cfg, scenario)`: override를
    `cfg.network.off_ramp_split_ratio`에 병합한 새 cfg 반환. None이면 cfg 그대로(no-op).
- **단일 주입 지점**: `off_ramp_split_ratio`는 plant(metanet.py:299) + 모든 controller
  (wu_distributed/freeway_follower/distributed_coordinator/coupling/centralized_mpc) +
  free_flow_reference가 전부 `cfg.network.off_ramp_split_ratio`만 읽는다. 따라서 cfg.network에
  한 번 병합하면 모든 사용처에 일관 적용. β합류·차량보존식은 불변(split 값만 주입).
- 배선 지점: `six_controller_comparison.main`(scenario 로드 직후) +
  `closed_loop_runner.run_closed_loop`(함수 진입부). 둘 다 `apply_scenario_network_overrides` 호출.
- `src/config/scenarios.yaml`: `capacity_drop` 추가
  (urban_scale=2.5, freeway_scale=1.45, ramp_scale=1.25, off_ramp_split_ratio_override 전 0.45).
  현실성 근거: 고off-ramp 수요(도심 진입 집중) + 포화 arterial(urban_scale 2.5)로 off-ramp
  하류 신호 배출이 막혀 spillback 누적되는 첨두 상황.
- `src/tests/test_six_controller_comparison.py`: `test_c` 정직화(아래).

## 측정 (capacity_drop, T=1800, WU-CD-F)
명령: `... -m src.experiments.six_controller_comparison --scenario capacity_drop
--T-total 1800 --controllers WU-CD-F --output 2026-06-14/results/wu_capdrop_probe`
- (1) off-ramp 점유 최대 = **21.8%** (목표 50% **미달**).
- (2) λ_eff_last min=1.9796(lanes=2.0), capacity_drop_active=10/10 step. 단 lane loss는
  ~0.02 (미미). gamma는 하드임계 아니라 지수감쇠 분모(metanet.offramp_spillback_lambda_eff):
  점유 0이면 무감소, 점유↑면 연속 감소. 21.8%서 감소량 ~0.02 lane.
- (3) **VSL이 max-0.5 미만으로 내려간 interval = 0/20** (vsl_FW_W/FW_E 항상 100).

## 점유율 50% 미달의 구조적 원인 (실측 스윕)
- off_ratio = Σ(같은 링크 off-ramp split)는 metanet.py:302에서 [0,1] 클립. 링크당 off-ramp 2개라
  split≥0.5면 off_ratio→1.0 포화. split 0.55/0.65/0.75 전부 동일 점유(24.6%).
- 점유는 **demand·storage·time 무관하게 ~22-25%에서 평형**(us 2.5→6.0, T 1800→3600, storage
  120→40 전부 24.6% 이하). 원인: off-ramp inflow는 항상 drain(하류 신호 off_ramp movement
  service over 180s)에 의해 소화됨. offramp_blocked=0(inflow throttle 미발동). 즉 120-veh
  storage가 180s 신호 service 대비 작아 capacity-drop 임계까지 차오를 수 없음.
- 결론: **현 plant drain 동역학에서 split-only(또는 storage 축소) 시나리오 조정으로는 50%
  점유 도달 불가.** 이는 plant 구조 특성이지 튜닝 실패가 아님.

## VSL 미반응 진단 — 이득/페널티 정량 (핵심, directive 4·5)
스크립트: `2026-06-14/vsl_cost_diagnostic.py` (_solve_freeway_agent 후보 루프 복제, TTS항/
smoothness항 분리). vsl_smoothness_weight=0.1.
- **capacity_drop 최혼잡 interval(점유 21.8%, λ_eff 1.98)**: prev=100→80 시
  TTS_gain = **음수**(FW_W +0.129, FW_E +0.011 veh·h 오히려 증가), smooth_penalty=+2.0.
  → VSL↓가 TTS를 줄이지 못함. penalty/gain 음수.
- **강한 capacity-drop(98% 점유, λ_eff 1.701)**: prev=100→80/90 시
  TTS_gain = **정확히 0.00000** (FW_W·FW_E 둘 다), smooth_penalty=+2.0.
  → "이득이 smoothness에 묻힌다"보다 더 강함: **묻힐 이득 자체가 0**.
- 근본 원인: 단일링크 probe TTS 모델에서 VSL↓는 마지막 segment의 off-ramp capacity-drop
  병목 앞 segment 차량수를 horizon(=1)×K_cf substep 내에 줄이지 못함. desired speed만
  낮출 뿐 이미 존재하는 차량은 그대로 → link_vehicles 합 불변 → TTS 불변. smoothness만 순손실.

## test_c 정직화 (directive 3)
- 기존: prev_vsl=70(이미 <99.5)에서 출발 → "VSL<max-0.5"가 trivially 통과(거짓 안심).
- 신규 `test_c_vsl_actively_steps_down_when_capacity_drop_active`: prev_vsl=max(=100)에서
  출발, 98% 점유 state(λ_eff≈1.70)에서 (전제: capacity-drop active 먼저 단언) VSL이
  max-0.5 미만으로 **능동 하강**하는지 검증.
- **현재 FAIL** — capacity-drop이 강하게 active한데도 prev=100에서 VSL이 100 유지.
  억지 통과 금지(directive 3·8). 이것이 정직한 신호. 전체 suite 112 pass / 1 fail(=test_c).

## 보정 판단 (directive 5 — 연구자 결정 대기)
VSL 미반응의 원인은 smoothness 페널티가 아니라 **probe TTS 모델이 VSL↓의 이득을 0으로
계산**하는 것. 따라서 단순 smoothness_weight↓로는 해결 안 됨(0×무엇=0). gradient/probe
모델 보정 방향(예: 후보 horizon 연장, off-ramp 병목 앞 segment 메타넷 속도 효과 반영,
혹은 VSL→다운스트림 유입↓→λ_eff 회복 경로의 명시적 모델링)은 연구자 결정 필요.

## 커밋 (이번 작업)
0afa450 split override 배선 / bd2292e capacity_drop 시나리오 / 7f9dd80 test_c 정직화

---

# 2026-06-14 (3) 작업 노트 — Option C: per-segment VSL + 다운스트림 결합

## 목표
WU-CD-F freeway VSL이 capacity-drop 시 작동하도록 per-segment VSL(plant 입자도 세분화)
+ 다운스트림 결합을 구현. 직전 실패: link당 VSL 1값 uniform → 병목 seg2까지 늦춰 mainstream
metering 불가 + probe TTS 모델이 VSL↓ 이득을 0으로 계산(98% 점유서도 ΔTTS=0.00000).

## 변경 (단계별 커밋)
1. plant per-segment VSL: `state.segment_vsl(control, link, i, cfg)` 헬퍼(segment 키
   `{link}__seg{i}`→link 키→max fallback). `metanet.freeway_substep`이 segment 루프 안에서
   vsl_i/vsl_active_i 읽음. 차량보존식 불변. (235ac7d)
2. 직렬화: `simulator.control_row`에 `vsl_{link}_seg{i}` 열 추가, 기존 `vsl_{link}`는
   min-over-segment로 유지(하위호환). (b54dca3)
3. controller: `_solve_freeway_agent` segment 벡터 탐색 재작성. 후보=병목 seg{max,prev}
   ×상류 seg(max_vsl_step 내 vsl_set). 메커니즘 A(storage-aware probe→λ_eff 회복 TTS 내생화)
   + 메커니즘 B(coupling p_down_{link}, objective에 w_couple·p_down·누적 seg1→seg2 유입).
   반환 (vsl_dict,obj,evals), _solve_followers는 new_vsl.update(). w_couple=0.05(fallback). (97bca51)
4. test_c: _congested_state를 현실적 프로파일([15,20,40], 상류 free-flow)로, demand fs=1.0/rs=0.8.
   상류 VSL↓ + 병목 seg2 max 유지 단언. (320e299)
5. 문서: spec 16.4 Option C 절, fidelity matrix WU-CD-F 행, wu2022_reference §8 갱신.

## 핵심 측정 (강제 98% state, λ_eff=1.7013, p_down=58.5, smoothness=0)
- **seg0 sweep ΔTTS(obj)**: 50→512.4, 60→519.2, 70→525.7, 80→532.2, 90→537.1, 100→537.3.
  → 상류 VSL↓ ΔTTS **음수**(100→80: −5.16, 100→50: −24.9). **직전엔 0.00000**.
- **seg1 sweep**: 50→530.0, ..., 100→537.3 (100→50: −7.28). 역시 음수.
- 실제 solve 선택 벡터(prev=100, max_vsl_step=20): **[80, 100, 100]** — 상류 seg0=80(metering),
  병목 seg2=100(유지). FW_E도 동일.

## closed-loop (capacity_drop, T=1800, WU-CD-F)
- VSL 움직인 interval = **9/10**(직전 0/20). FW_W seg0→70, seg1/seg2=100 유지. FW_E=100.
- λ_eff_last min: FW_W 1.9804, FW_E 1.9796(lane loss ~0.02, 약함). 점유 ~22%(직전과 동일).
- ttt=1764.4 delay=1108.9 authority_ok=True.

## 근본 원인 규명 (정직)
직전 "ΔTTS=0"의 진짜 원인은 smoothness가 아니라 **VSL이 물리적으로 inert**한 것:
- METANET 평형속도: ρ=40 → 47.4 km/h, ρ=50 → 32.3. vsl_set 최저=50 > 47.4라 congested
  가지에서 VSL이 binding 안 됨. 또한 congested 가지는 q=ρ·v 거의 보존 → 속도↓해도 유량 불변.
- 따라서 VSL metering은 **free-flow 가지(ρ<ρ_crit=33.5)에서만 성립**. 상류가 free-flow를
  유지(현실적 capacity-drop: 상류 흐름+병목만 막힘)할 때만 ΔTTS 음수. 본선 전체 과포화 시
  이득 다시 0(정직 한계). 직전 fixture는 전 segment ρ=40으로 상류까지 congested로 밀어
  VSL inert였음 → 현실적 프로파일로 교체.

## 회귀
- 전체 unittest 113 통과(직전 112+1fail→113 OK). 다른 3 controller는 link 키 fallback로
  무변경(smoke improvement -0.91% 비트 동일). test_c 정상 통과(억지 아님 — 측정으로 입증).

## 커밋
235ac7d plant per-seg / b54dca3 직렬화 / 97bca51 controller / 320e299 test_c / (docs 다음 커밋)
