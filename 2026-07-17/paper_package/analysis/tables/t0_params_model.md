# 표 0a — 플랜트/모델 파라미터 (§0 게재용)

> 출처 규약: `state.py:줄` = `Numerical-Sim-offiter/src/models/state.py`의 dataclass 필드,
> `yaml:줄` = `src/config/default.yaml`(운영값 — yaml이 dataclass 기본값을 override하는 경우
> 두 값을 병기). 런 규약(T_total·웜업)은 재현 명령(`ANALYSIS_PLAN_FINAL.md` §7,
> `work/baseline_queue.sh`)에서 확인. 값은 전부 코드/설정에서 직독 — 발명값 없음.

## 시간 격자

| 파라미터 | 값 | 단위 | 출처 |
|---|---|---|---|
| 시뮬레이션 총 길이 T_total | 10,800 (60스텝) | s | 런 인자 `--T-total 10800` (baseline_queue.sh, ANALYSIS_PLAN §7; yaml 기본 7200 yaml:2, state.py:114) |
| 웜업(공통 무제어) | 20 스텝 = 3,600 | s | `WARMUP_NC_STEPS=20` (runner:800–805) |
| 제어 주기 T_c (control_interval) | 180 | s | state.py:117, yaml:5 |
| freeway 샘플링 T_f | 10 | s | state.py:115, yaml:3 |
| urban 샘플링 T_u | 5 | s | state.py:116, yaml:4 |
| K_cu (T_c/T_u, urban substep 수) | 36 | — | state.py:166–167, yaml:15 |
| K_cf (T_c/T_f) | 18 | — | state.py:162–163, yaml:16 |
| T_u_h (T_u 환산) | 5/3600 ≈ 1.389×10⁻³ | h | state.py:141–143 |

## Freeway (METANET)

| 파라미터 | 값 | 단위 | 출처 |
|---|---|---|---|
| 본선 링크 | 2 (FW_W, FW_E) | — | state.py:180 |
| 링크당 세그먼트 수 | 8 (dataclass 기본 4를 yaml이 override) | — | yaml:22, state.py:181 |
| 세그먼트 길이 | 0.5 | km | state.py:182, yaml:23 |
| 차선 수 | 2 | lane | state.py:183, yaml:24 |
| 자유류 속도 v_free | 100 | km/h | state.py:184, yaml:25 |
| 임계밀도 ρ_crit | 33.5 | veh/km/lane | state.py:185, yaml:26 |
| 잼밀도 ρ_max | 95.0196… (Eq.6 capacity-drop FD 보정값) | veh/km/lane | state.py:186, yaml:27–29 |
| 본선 링크 용량 | 4,000 (dataclass 기본 3600을 yaml이 override) | veh/h | yaml:30, state.py:187 |
| METANET a | 1.867 | — | state.py:263, yaml:162 |
| METANET τ | 18 (=0.005 h) | s | state.py:259–260, yaml:158–159 |
| METANET ν (자유류) | 65 | km²/h | state.py:261, yaml:160 |
| METANET ν_cong (혼잡 regime) | 250, 전환 ON | km²/h | yaml:165–166 (dataclass 기본 65/OFF, state.py:267–268) |
| METANET κ | 40 | veh/km/lane | state.py:262, yaml:161 |
| 최저 속도 v_min | 5 | km/h | state.py:257 |
| VSL 격자 vsl_set | {50, 60, 70, 80, 90, 100} (간격 10) | km/h | state.py:569, yaml:313–319 |
| VSL 스텝 명목 한계 max_vsl_step | 20 | km/h/interval | state.py:570, yaml:320 |
| 본선 진입 origin 큐 (CTM receiving) | 명시적 보존 (segment 0 수용 제약) | — | state.py:830–832 |

## Off-ramp spillback capacity drop (Wu Eq.22 재현)

| 파라미터 | 값 | 단위 | 출처 |
|---|---|---|---|
| 활성 | ON | — | yaml:174, state.py:332 |
| lane_reduction | 1.0 (Wu full 1-lane 수준; dataclass 기본 0.35를 yaml이 override) | lane | yaml:178, state.py:333 |
| γ | 0.5 | — | state.py:334, yaml:179 |
| b | 2.0 | — | state.py:335, yaml:180 |

## Ramp

| 파라미터 | 값 | 단위 | 출처 |
|---|---|---|---|
| on-ramp | 4 (R_D_W, R_F_W, R_D_E, R_F_E) | — | state.py:188 |
| ramp 용량 (각) | 1,500 | veh/h | state.py:192–194, yaml:36–40 |
| ramp 큐 저장 한계 ramp_queue_max_veh | 180 | veh | state.py:198, yaml:54 |
| merge 세그먼트 (다이아몬드 IC) | D: seg3, F: seg5 | — | yaml:47–52 |
| off-ramp | 4, 세그먼트 2/4 | — | yaml:131–143 |
| off-ramp 분류율 | 0.2 (dataclass 기본 0.06을 yaml이 override) | — | yaml:151–155, state.py:251–256 |
| off-ramp storage | 60 (dataclass 기본 120을 yaml이 override) | veh | yaml:127–130, state.py:231 |
| metering 율 범위 | 0.2–1.0 ×cap | — | state.py:586–587, yaml:331–332 |

## Urban (신호·큐·저장)

| 파라미터 | 값 | 단위 | 출처 |
|---|---|---|---|
| 신호 교차로 | 5 (A, B, C, D, F) + 비통제 E | — | state.py:199–200 |
| cycle | 120 | s | state.py:204, yaml:71 |
| lost time | 8 | s | state.py:205, yaml:72 |
| 유효 녹색 총량 effective_green_total | 112 (=cycle−lost) | s | state.py:326–327 |
| green_min / green_max | 20 / 92 | s | state.py:206–207, yaml:73–74 |
| movement 용량 (allocation 비활성 시 상수 cap) | 1,400 | veh/h | state.py:220, yaml:96; local_signal_plant.py:30–31, 79–90 |
| urban 포화류 Q_sat | 1,000 | veh/h | state.py:270, yaml:168 |
| 그리드 링크 저장 | 220 | veh | state.py:226, yaml:100 |
| ramp 접근로(D_R_*, F_R_*) 저장 | 180 | veh | yaml:122–125 |
| boundary 큐 한계 | 240 | veh | state.py:214, yaml:91 |
| boundary_out(출구) 유출 상한 | 1,600 (링크당; 5개 표준 시나리오 비왜곡 보정값) | veh/h | state.py:219, yaml:95 |
