# 2026-06-28 작업 노트 — ramp-aware per-signal 국소 rollout

## 무엇을 바꿨나
SPEC_ramp_aware_local_rollout.md 구현. freeway-인접 신호 D/F의 국소 rollout을 ramp-aware로
확장해 검증된 분해손실을 회복했다. 기존 파일은 미변경, 새 follower 파일 2개만 수정.

### 1. `src/controllers/local_signal_plant.py`
- `LocalSignalModel`에 ramp 인터페이스 정적 데이터 추가: `kind_of`, `offramp_movements`(off_ramp→
  movement), `offramp_storage_cap`, `onramp_movements`(ramp→movement), `ramp_queue_max`, `has_ramps`.
- `build_local_model`: on-ramp 귀속을 **kind=="on_ramp"가 아니라 spec["ramp"] 태그**로 한다.
  실제 plant `ramp_requests` 루프가 ramp 태그가 있는 **모든** movement(예: ramp행 boundary_in
  `D_W_to_on*`)를 처리하기 때문. 이게 핵심 버그픽스였다(아래 참조).
- 새 함수 `rollout_local_tts_ramp_aware`: D/F용. substep마다 실제 plant 회계 순서 복제.
  - (a0) reservoir 배출(freeway pull, frozen `compute_ramp_release_flows`): w_r -= drain·dt.
  - (a) on_ramp 적재(`ramp_requests` 복제): green·cap·reservoir 여유로 movement 큐→reservoir,
        ramp_queue_max로 cap, 못 넣으면 큐에 backup. + de facto ramp metering 패널티
        (released·w_fw·weight).
  - (b) off_ramp drain(`_drain_offramp_storage` 복제): green·cap·하류 frozen S_eff로 storage→urban.
  - (c) off-ramp storage 유입(frozen freeway→off-ramp 유출): occupancy += inflow·dt, cap clamp.
  - (d) 나머지 urban movement(internal/boundary_in/boundary_out): green·cap·S_eff 게이트(기존 로직).
  - own-TTS = Σ_substep(Σ movement 큐 + Σ off-ramp storage 점유 + Σ reservoir 큐)·dt + smoothness.
- A/B/C(ramp 없음)는 `has_ramps=False`라 기존 `rollout_local_tts` 그대로 사용(미변경).

### 2. `src/controllers/wu_faithful_follower.py`
- 헬퍼 추가: `_frozen_offramp_inflow`(per-off_ramp freeway 유출), `_offramp_occupancy`(cap−available),
  `_frozen_reservoir_drain`(compute_ramp_release_flows), `_frozen_freeway_congestion`(w_fw=1−receiving_factor).
- `_solve_urban_agent_local`: has_ramps 신호는 off-ramp 유입을 phase 큐 도착에서 분리(storage로),
  storage 점유·reservoir 큐 스냅샷을 잡아 ramp-aware rollout 호출. arr 재정규화 target에서
  phase별 off-ramp 기여를 뺀다(보존).
- `_solve_followers`: reservoir_drain·freeway_congestion을 step당 1회 계산해 전달.
- `self.ramp_metering_weight = 10.0` (de facto ramp metering 계수, 폐루프 sweep으로 결정).

## 왜 — 근본 메커니즘
- plant 실험(D/F 고정 green): p1=56 → +0.00%, **p1=20(p2-heavy) → +41.82%**. 이유는
  **freeway TTT**: p1-heavy는 on_ramp movement(`*_N_to_on*` 등)를 많이 서비스해 reservoir를
  꽉 채우고 freeway 본선을 정체시킨다(merge ρ≈92.5 ≫ ρ_crit 33.5, receiving_factor≈0.04).
  p2-heavy면 on_ramp을 굶겨 reservoir·freeway가 풀린다.
- 순수 국소 own-TTS는 이 freeway 비용을 못 본다(자기 큐는 어느 split에서도 비워짐 → cost flat).
  그래서 SPEC line 28의 **de facto ramp metering**(막힌 freeway로 가는 reservoir 적재에
  w_fw 가중)을 추가해 p1을 억제. ramp 그룹핑 버그(boundary_in ramp movement 누락)를 고치니
  per-ramp w_fw 비대칭이 split 선호를 만들어 폐루프에서 작동.

## 결과 (closed-loop sweet_128 T=3600)
- improvement: **−1.19% → +30.67%** (WU-CD-F +25.6% 초과, 전역채점 ceiling +29.23% 도달).
- total_ttt 3089.5 → 2142.1 (urban 1251.8→1202.4, **freeway 1837.7→939.7**).
- D green mean 27.5(min 20), F mean 27.2(min 20) — **확실히 p2-heavy**. A/B/C=56.0 불변.
- solve ~3.99s/step (full-coupled 78s/step 대비 ~20× 저렴), evals ~501/step.

## ramp_metering_weight sweep (sweet_128 T=3600)
| W | impr% | D_mean | F_mean |
|---|---|---|---|
| 0 | +0.04 | 55.5 | 53.4 |
| 2 | +19.95 | 31.7 | 31.4 |
| 5 | +19.95 | 31.7 | 31.4 |
| 10 | +30.67 | 27.5 | 27.2 |
| 15–30 | +30.67 | 27.5 | 27.2 |
→ W≥10에서 +30.67% 평탄(불감). W=10 채택(평탄 도달 최소값).

## 회귀 (demand 스윕 T=3600, W=10)
| scenario | impr% | D_mean | F_mean | A_mean |
|---|---|---|---|---|
| sweet_170 | +3.12 | 37.1 | 37.4 | 56.0 |
| sweet_190 | +1.54 | 37.7 | 39.5 | 52.1 |
| sweet_220 | +1.52 | 39.9 | 41.1 | 45.1 |
→ 전부 양(무해). 고수요일수록 개선폭 작아지나 음수 없음. A drift(고수요)는 ramp 없는
A의 **기존 비-ramp 국소 rollout** 거동(내 ramp 코드 무관).

## 약점 / 검토자용
- de facto ramp metering 패널티는 plant 회계의 직접 복제가 아니라 **근사**(reservoir 적재량을
  frozen w_fw로 가중). 계수 10.0은 폐루프 튜닝값이고 sweet_128 한 시나리오 기준. W≥10 평탄해
  민감하진 않으나 다른 demand에서 재확인 필요(아래 회귀 참조).
- reservoir 배출률(`compute_ramp_release_flows`)·off-ramp 유입은 step당 1회 frozen.
  Jacobi 내부에서 freeway green 후보 변화에 따른 갱신은 안 함(SPEC "최소 step당 1회" 충족).
- off-ramp drain의 하류 S_eff 갱신은 자기 origin 링크에만 적용(이웃 링크 frozen). 실제 plant는
  storage→receiving_link 점유를 직접 감하지만 국소에선 자기 권역만 추적.

---

# 2026-06-28 (오후) — freeway agent 실제 ramp metering 탐색 (튜닝 패널티 제거)

## 무엇을 / 왜
de-facto metering hack(urban-green 패널티 `ramp_metering_weight=10.0`)을 제거하고, freeway
agent에 진짜 `control.ramp_metering` 액추에이터(metanet.py:230) 탐색을 부여했다. metering이
freeway agent의 own-TTS 최소화에서 **창발(emerge)**한다. urban agent는 순수 demand-responsive로 복귀.

## 구현 (src/controllers/wu_faithful_follower.py만 수정, local_signal_plant.py 무변경)
1. `ramp_metering_weight = 0.0` — urban-green metering 패널티 비활성화(이중 metering 제거).
2. `ramp_metering_fractions = (1.0, 0.7, 0.5, 0.35, 0.25)` ×capacity.
3. `_solve_freeway_agent_metered(link,...)`: 이 link 소유 ramp(`ramp_to_freeway[ramp]==link`)에
   대해 분율을 좌표하강으로 훑고, 채점은 기존 `_wu._solve_freeway_agent` probe-rollout 재사용
   (후보 metering을 snapshot.ramp_metering에 주입→candidate_control→compute_ramp_release_flows
   →own-TTS=link 차량+on-ramp ramp_queue+off-ramp storage). 인위적 패널티 없음.
4. 비용: metering 스캔은 Jacobi 루프 **밖 step당 1회**(루프 안 freeway는 VSL-only). 8.1s/step.

## 결과 (closed-loop T=3600)
- sweet_128: 3089.532 → 1339.914 = **+56.63%** (이전 튜닝패널티 +30.67%, 검증천장 +41.8% 상회)
  metering frac mean: R_D_W 0.42 / R_F_W 0.99 / R_D_E 0.39 / R_F_E 0.97
  greens mean: A/B/C=56 / D=55.5 / F=58 (balanced 회복, starvation 제거)
  solve ms/step mean 8148, max 10189
- 회귀: sweet_170 +39.61% / sweet_190 +32.92% / sweet_220 +18.62%
  (이전 회귀 +3.12/+1.54/+1.52 대비 대폭 향상; metering이 부하에 따라 0.25~0.66 적응)

## 약점 / 검토자용
- solve 8s/step은 이전 3.7s보다 무겁다(metering 스캔=freeway probe ×~9회/link). 78s 한계엔
  한참 못 미쳐 local이나, free-flow ramp는 cap 고정하는 congestion-gating으로 더 줄일 수 있음.
- metering 스캔은 step당 1회(수렴 coupling 기준)라 Jacobi와 완전 동기는 아님.
- 좌표하강 1패스(ramp 2개/link라 상호작용 영향 작음).
- 후보 분율 5점 격자(연속 최적이 격자 사이면 약간 손해 가능).
