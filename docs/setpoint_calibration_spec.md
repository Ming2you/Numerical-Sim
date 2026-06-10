# Setpoint 캘리브레이션 사양 (N_P_star / N_UF_star / rho_crit)

대상: Codex. 목적: round-4 진단(`reports/claude_review_report.md`, peak_demand 풀 run에서
proposed가 baseline보다 Total TTT −10.64%, 피해 전부 urban)의 **근본 원인**인 "리더 setpoint가
분석 없이 임의로 정해진 값"을 캘리브레이션으로 바로잡기 위한 구현 지시.

핵심 판단: 제어 로직 버그(가짜 압력·offset·green 진동)보다 **이 setpoint 미캘리브레이션이
상류 원인**이다. 타겟 자체가 임계점과 무관하면 control law가 옳아도 망을 혼잡 가지로 민다.

---

## 1. 문제 — setpoint가 임의값이고, N_P_star는 단위까지 불일치

증거(코드):
- `src/controllers/leader.py:26`: `N_P_star`는 `np.linspace(N_P_star_range=[0,500], n_np)`의
  **균등 그리드 점**일 뿐(MFD/수요 분석 근거 없음). run에서 `N_P_star=333.33` 고정으로 선택됨.
- `src/controllers/leader.py:54`: `_heuristic_nuf_target = frac · total_ramp_capacity`
  (`frac∈[0.82,1.0]`) → `N_UF_star`를 **freeway 수용량이 아니라 총 램프용량(=4920~6000)** 에 고정.
  그래서 초기 N_UF_star=6000 같은 추적불가 타겟 발생 → metering residual 폭증 → urban "가짜 압력".
- **★ N_P_star 단위 불일치(버그)**:
  - 리더: `leader.py:92-93` `n_p = s.total_urban_vehicles()`(누적 veh)와 비교
    `target_penalty += w_P·max(0, n_p − N_P_star)` → **N_P_star = 누적대수(veh)**.
  - 도시: `src/models/urban_queue_model.py`의 `net_inflow_tracking_error = |net_inflow − N_P_star|`
    (`net_inflow`=veh/h)와 `src/controllers/urban_follower.py:151-152`의
    `desired_in=(total_service+N_P_star)/2`, `desired_out=desired_in−N_P_star` → **N_P_star = 유량(veh/h)**.
  - 같은 333을 한쪽은 "333대", 다른쪽은 "333대/h"로 사용. **차원 모순.**

참고(자기일관적인 부분): freeway는 METANET 지수형 V(ρ)에서 유량이 ρ=rho_crit에서 peak이며,
`rho_crit=33.5, v_free=100, a=1.867, lanes=2`로 계산하면 용량 ≈ `33.5·100·exp(−1/1.867)·2
≈ 3922 veh/h`(config `freeway_capacity_veh_h=4000`과 ~2% 차이). 즉 **freeway rho_crit/용량은
대체로 맞다** — 실측 검증은 하되 우선순위는 낮다. **우선순위는 urban n_crit + N_P_star.**

---

## 2. 캘리브레이션 절차 (no-control 수요 sweep)

### 2.1 도시 MFD → n_crit (최우선)
- baseline(예: `no_control` 또는 `fixed_signal_fixed_speed`)으로 **수요 배율 sweep**
  (`urban_scale`를 여러 단계, 예 0.5~3.0)을 각각 풀 길이 run.
- 매 control step 기록: 도시 **누적** `n = TrafficState.total_urban_vehicles()`,
  도시 **유출(production)** = 단위시간당 망을 빠져나간 차량(예: off-ramp/boundary-out 배출
  + 통과 완료). diagnostics의 `outbound_service_veh`/완료 흐름을 활용.
- (n, 유출) 산점도 → **유출이 최대가 되는 누적 = n_crit**. (작은 망이라 noisy할 수 있으니
  여러 시드/수요로 평균. 매끈한 MFD를 과신하지 말 것.)
- 산출물: `n_crit` 추정치 + MFD 플롯을 `reports/` 또는 `outputs/`에 보존.

### 2.2 freeway q–ρ → rho_crit / capacity (검증, 우선순위 낮음)
- baseline으로 freeway mainline·ramp 수요 sweep run.
- 세그먼트별 (ρ, q=ρ·v·lanes) 기록(이미 `state.freeway_flow` 1급 상태 존재).
- q–ρ 산점도의 peak에서 `rho_crit`, `capacity` 확인 → config 값(33.5 / 4000)과 대조.
  큰 차이 없으면 유지, 있으면 reconcile.

---

## 3. 코드 수정 방향 (값 캘리브레이션 + 의미 통일)

### 3.1 N_P_star 의미를 하나로 통일 (버그 수정)
- 권장: **N_P_star = 도시 목표 누적(veh)** 으로 통일(perimeter/MFD 제어의 표준).
- 그러면 도시 쪽을 누적 추적으로 바꿔야 함: `urban_follower._allocation`이 net-inflow를
  N_P_star(유량)로 맞추는 현재 로직을, **"현재 누적 n을 n_crit로 되돌리는 net-inflow"** 를
  계산하도록 변경. 즉 setpoint는 누적, 제어량은 거기서 유도한 유입.
- `urban_queue_model`의 `net_inflow_tracking_error`도 동일 의미로 재정의.

### 3.2 리더를 고정 setpoint가 아니라 accumulation feedback으로
- 현재 `leader.candidates`는 N_P_star를 `[0,500]` 그리드에서 고름. 이를
  **n_crit 기반 동적 목표**로: 목표 누적 = n_crit, 후보는 n_crit 근방(또는 n_crit 단일값)으로
  좁히고, 누적이 n_crit에 가까울수록 허용 net-inflow→0이 되도록 매핑.
- 즉 "n_crit 값을 넣는 것"만으로 부족하고, **n_crit를 제어목표로 변환하는 법(피드백)** 까지 구현.

### 3.3 N_UF_star를 수용량 기반으로
- `leader._heuristic_nuf_target`을 `total_ramp_capacity` 대신
  **"mainline ρ ≤ rho_crit를 유지하는 추가 유입량"** 으로 유도(현재 mainline 밀도·용량 여유에서
  역산). 추적불가 타겟(6000)을 애초에 후보에서 배제.
- `config/default.yaml`의 `N_UF_star_range`도 그 수용량 범위로 조정.

### 3.4 config 반영
- `src/config/default.yaml`: 2.1/2.2 결과로 `network.rho_crit`(검증), `freeway_capacity_veh_h`(검증),
  `leader.N_P_star_range`(= n_crit 근방), `leader.N_UF_star_range`(= 수용량) 갱신.
- 캘리브레이션 출처를 주석/리포트에 명시(임의값 재발 방지).

---

## 4. 검증 (end-to-end)
1. no-control sweep로 MFD(n_crit)·q–ρ(rho_crit) 추정, 플롯 보존.
2. 위 값으로 setpoint·의미 수정.
3. 동일 시나리오(peak_demand 7200s) proposed 재run → **Total TTT가 baseline 대비 개선되는지**
   (최소한 −10.64%가 양수 방향으로) 확인. boundary CV/ MaxMin이 더 이상 단조 발산하지 않는지,
   `net_inflow_tracking_error`가 의미 있게 줄었는지 확인.
4. freeway 제어(VSL/metering) 효과는 freeway가 혼잡해지는 시나리오(oversaturated/incident)에서
   별도 검증(현재 peak_demand는 freeway 유휴, VSL 0회 활성).

---

## 5. 우선순위 요약
1. (P0) 도시 MFD로 **n_crit** 추정 + **N_P_star 단위/의미 통일** + 리더 accumulation feedback.
2. (P0) **N_UF_star를 수용량 기반**으로(추적불가 타겟 제거) → urban "가짜 압력" 악순환 차단.
3. (P1) freeway q–ρ로 rho_crit/capacity 검증(대체로 자기일관적이라 minor).
4. (P1, 별건) round-4에서 지적한 control-law 버그(가짜 압력 부호·offset=freeway속도·green 진동)는
   setpoint 캘리브레이션 후에 잡아야 진단이 깨끗함.
