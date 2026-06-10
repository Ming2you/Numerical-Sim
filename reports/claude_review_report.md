# Claude Review Report

_검토 커밋: `a785494` "Calibrate setpoints and feasible ramp targets" (직전 검토는 `ee85ee1`)._
_요청: setpoint 캘리브레이션·N_P_star 단위통일·feasible N_UF가 실제로 반영됐는지, 그리고
round-4의 −10.64%(urban 악화)가 개선됐는지. 코드 검증 + 풀 진단 run으로 확인._

## Verdict

**FAIL** — Total TTT **−6.57%**(여전히 baseline보다 나쁨). 단, round-4 **−10.64% → −6.57%로 개선**.
setpoint 재설계(누적목표·단위통일·feasible N_UF)는 코드로 검증됐고 방향이 맞으며 효과도 있다.
그러나 **캘리브레이션 결과가 리더에 절반만 연결**돼, 핵심 버그가 남아 있다 — 도시 누적목표가
측정된 n_crit의 약 2배다.

## 진단 run 결과 (peak_demand 7200s, `outputs/claude_diag_peak_full_r5/`)

| 지표 | baseline | r4 proposed | **r5 proposed** | r4→r5 |
|---|---:|---:|---:|---|
| Total TTT | 2889.8 | 3197.3 | **3079.6 (−6.57%)** | 개선 |
| Urban TTT | 2702.0 | 3001.5 | 2881.6 | 개선 |
| Boundary CV | 0.145 | 0.305 | 0.228 | 개선(여전히 악화) |
| MaxMin_boundary | — | 215.1 | 145.7 | 개선 |
| mean metering error | — | 624 | 475.6 | 개선 |
| max metering violation | — | 3884 | 1028 | 개선(feasible cap 효과) |

## ✅ 검증된 수정 (코드 대조)

- **N_P_star = urban accumulation target(veh)로 단위통일.** config `N_P_star_unit: veh`,
  `urban_follower._allocation`이 `urban_accumulation_feedback_flow`로 목표 net_inflow를
  **유도**(직접 setpoint 추적 아님). → round-3/4에서 지적한 단위 불일치 해소.
- **누적 피드백(MFD perimeter)**: `urban_accumulation_feedback_flow`(`urban_queue_model.py:232`)
  = `(N_P_star − 현재누적)/feedback_horizon`, clip[±limit]. 게인은 `N_P_feedback_horizon_h(0.5)`
  하나뿐 — 위치별 게인 증식 없음(우리가 합의한 "단순 boundary + MPC 피드백"과 일치).
- **N_UF_star = feasible headroom 기반.** `leader._feasible_nuf_capacity`(`leader.py:59`)가
  per-ramp `min(cap, available, q_cap·receiving, density_headroom_flow)` × margin(0.95)으로 상한.
  `density_headroom = max(0, rho_crit − ρ)`라 **임계 overshoot도 차단**(우리 보정 ② 반영). → 초기
  추적불가 6000 타겟 사라짐(max metering violation 3884→1028).
- **캘리브레이션 스크립트** `experiments/calibrate_setpoints.py` 추가, smoke에서
  **n_crit=172.2 veh, max production=1306.7 veh/h** 추정.

## ★ 핵심 잔존 버그 — 누적목표(333)가 n_crit(172)의 2배

run 시계열(`proposed/run_log.csv`)에서 확정:
- `urban_accumulation_target_veh = 333.33` (전 step 고정) — 그런데 캘리브레이션 **n_crit = 172.2**.
- step0 누적 80 → step1 **171**(≈n_crit)인데, 목표가 333이라 피드백이 **계속 admit**
  (`urban_net_inflow_target_veh_h`>0) → 누적이 n_crit를 넘어 계속 증가.
- run 끝(step38) `urban_accumulation_veh = 1726`(≈n_crit의 10배), `error=+1393`,
  net_inflow_target은 −800에 clamp(못 비움), `onramp_approach_queue=960`, `queue_overflow=216`.

원인: **`leader.py:33`이 N_P_star를 여전히 `linspace([0,500])`에서 고름**(333.3은 그 그리드 점).
**캘리브레이션의 n_crit=172가 `N_P_star_range`/후보에 연결되지 않았다.** 즉 N_UF엔 headroom 밴드를
적용했지만 **N_P엔 미적용** — 우리가 합의한 "n_crit 근방으로 후보 좁히기"가 빠졌다.

**이게 "짧은 smoke +6.85% vs 풀 run −6.57%"의 정체다.** 초반(누적 ≤171, ≤n_crit)엔 admit이 도움
→ 2-step smoke는 +. 풀 run은 목표 333을 향해 계속 admit → 누적이 n_crit를 지나 1726까지 폭주
→ 도시망 포화 → proposed가 baseline보다 나쁨. **2-step smoke(+6.85%)는 신뢰 금지.**

## 기타 이상 징후

- **VSL 0회 활성(`vsl_active_steps=0`)** — freeway 유휴(density_exceedance=0), round-4와 동일.
  freeway 제어 검증엔 부적합한 시나리오.
- **시나리오가 urban 과포화.** 누적 1726 >> n_crit 172 (baseline·proposed 둘 다). peak_demand가
  도시 수용량을 압도 → perimeter 제어로도 n을 n_crit에 못 잡음. **demand가 용량 근처인
  "제어 가능한" 시나리오에서 재평가** 필요(현재는 10× 과포화라 공정한 시험이 안 됨).
- **`net_inflow_tracking_error=721.8`은 stale 진단.** net_inflow(veh/h)를 N_P_star(veh 누적)와
  비교하는 옛 식이 남음. Codex가 올바른 `urban_net_inflow_target_veh_h`/`urban_accumulation_error_veh`를
  추가했으니, 리포트의 옛 metric은 제거/교체할 것.
- 메터링 여전히 느슨(mean 475, `metering_target_infeasible=1`) — feasible cap으로 나아졌으나
  freeway 유휴라 영향 미미.
- round-4 control-law(offset이 freeway 속도로 도시 진행 계산 `urban_follower.py:131`, corridor
  +179.6) 잔존.

## Recommended Fixes for Codex (우선순위)

- **① (1순위) 캘리브레이션 n_crit를 N_P_star에 실제 연결.** `N_P_star_range`(또는 후보 생성)를
  측정된 n_crit(≈172) 근방으로 좁힐 것(우리 headroom±밴드를 N_P에도 적용). 지금은 목표 333으로
  망을 임계 2배까지 민다. config `N_P_star_range: [0,500]` → n_crit 기반으로.
- **② 제어 가능한 시나리오로 재평가.** peak_demand는 10× 과포화라 perimeter 효과를 못 봄. demand가
  용량 근처인 시나리오(또는 urban_scale 낮춤)에서 baseline 대비 개선을 확인.
- **③ stale `net_inflow_tracking_error` 제거/교체**(누적 기준 metric으로).
- **④ offset을 도시 링크 통행시간 기반으로**(freeway 속도 아님), green 진동 damping.
- **⑤ freeway 제어(VSL/metering)는 freeway 혼잡 시나리오(oversaturated/incident)에서 별도 검증.**

## Should Codex Rerun Simulation?

**①(n_crit 연결) 수정 후 재실행.** 누적목표를 n_crit로 맞추면 풀 run에서 −6.57%가 양수로 갈
가능성이 큼(초반 +6.85%가 그 방향 신호). 단 ②(제어 가능한 시나리오)도 함께 봐야 perimeter
제어의 실제 효과를 공정히 판정 가능. 8% 인증은 그 이후.
