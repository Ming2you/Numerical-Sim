# Claude Review Report

_검토 커밋: `a4910dd` "Align leader objective with N_P_crit" (직전 검토는 `a785494`)._
_요청: 사용자가 발견한 root cause(leader objective가 임계 대신 결정변수를 penalty 기준으로 사용)
수정이 반영됐는지, 그리고 풀 7200s run에서 −6.57%가 개선되는지. 코드 + 풀 진단 run으로 확인._

## Verdict

**FAIL (단, main metric는 처음으로 PASS)** — Total TTT **+15.14%** (≥8% 임계 초과). 4라운드만에
**처음으로 baseline을 이겼다.** root cause 수정이 결정적이었다. 전체 verdict가 FAIL인 건
이제 **freeway VSL/density 검증**과 boundary overflow 때문이며(아래), 핵심 문제가 urban
setpoint에서 freeway 쪽으로 **이동**했다.

## ✅ root cause 수정 검증 (사용자 발견 → 정확히 반영)

- **스펙 대칭 복원**: `docs/spec/04_controller.md:39`이 `n_P(t) − n_P_crit`으로 수정(이전 `n_P_star` 오타).
  freeway 항 `rho − rho_crit`과 대칭.
- **코드**: `leader.py:182` `target_penalty += w_P·max(0, n_p − lc.N_P_crit_veh)` — 고정 임계 기준
  (자기참조 `N_P_star` 제거). freeway `max(0, rho − rho_crit)`과 대칭.
- **config**: `N_P_crit_veh: 172.225`(= 캘리브레이션 n_crit), 밴드 factor `[0.9, 1.05]`, 그리고
  `_np_candidate_bounds`가 누적 ≥ crit이면 상한을 crit로 캡(`leader.py:65-66`) — overshoot 차단.
- **결과**: run_log에서 N_P_star 후보가 **172.2로 수렴**(N_P_max=N_P_min=172.2). round-5의 임의
  목표 333이 사라지고 목표가 임계와 일치. objective_mode도 spec 기본형 `state_accumulation`으로.

## 풀 진단 run 결과 (peak_demand 7200s, `outputs/claude_diag_peak_full_r6/`)

| 지표 | baseline | r5 (−6.57%) | **r6 (+15.14%)** |
|---|---:|---:|---:|
| **Total TTT** | 2889.8 | 3079.6 | **2452.1 (+15.14%, PASS)** |
| Urban TTT | 2702.0 | 2881.6 | **2184.5** (대폭 개선) |
| Freeway TTT | 187.8 | 198.0 | 267.7 (악화 ↓) |
| Boundary CV | 0.145 | 0.228 | **0.064** (baseline보다 좋음) |
| corridor_delay_change | +179.6 | — | **−517.5** (progression 개선) |
| boundary_balance_improvement | — | −56.8% | **+56.1%** (양전환) |

urban이 극적으로 좋아졌다(TTT −19%, CV·corridor·balance 모두 baseline 우위). root cause 수정 하나로
round-5에서 본 "목표 333 → 누적 폭주" 메커니즘이 사라졌다.

## ❌ 남은 FAIL — 문제가 freeway로 이동 + 과포화 artifact

1. **★ 신규 1순위: freeway가 악화됐는데 VSL이 안 켜짐.** freeway TTT 188→268(+43%),
   `density_exceedance_duration=23`(freeway가 rho_crit 초과)인데 **`vsl_active_steps=0`**.
   dominant failure = `freeway_density_or_vsl_validation_failed`. 원인 해석: urban 처리량이
   좋아지며 **on-ramp로 더 많은 흐름이 freeway에 실림** → freeway 혼잡↑. 그런데 freeway
   follower의 VSL이 활성화 임계(`vsl_activation_density_ratio=0.95`)나 후보 로직에서 안 걸림.
   CLAUDE.md §5 기준 "density 초과인데 VSL 미활성 = controller-objective 실패". **다음 라운드 핵심.**
2. **boundary_balance FAIL은 일부 과포화 artifact.** `CV_boundary=0.064`(개선)인데
   `OverflowRatio_boundary=0.5`, `urban_accumulation_abs_error_veh=765.7`,
   `urban_net_inflow_tracking_error=701`로 FAIL. 누적이 ~1000(target 172의 ~6배)로 여전히 높음 —
   이는 **peak_demand가 demand>>capacity인 과포화**라 누적을 172에 못 잡는 시나리오 성질이지
   컨트롤러 결함이 아니다(그럼에도 baseline보다 처리량은 우수). **제어 가능한(비포화) 시나리오에서
   재평가** 필요(이전 권고 유지).
3. metering 여전히 느슨(mean error 475→262 개선, max 2235) — freeway 부하 증가와 맞물림.

## ★ 다음 요구사항 2건 (제안 문서 작성 완료, Codex 한 번에 구현)

VSL이 안 켜지는 근본 원인은 "이 METANET에 capacity drop이 없어 VSL이 켜질 유인이 없음"이고,
follower는 여전히 2-블록 중앙집중이다. 두 제안 문서를 만들어 두었다 — Codex가 spec 통합 + 코드
구현을 함께 수행할 것. **우선순위: ① capacity-drop(성능 직결) → ② 분산화(아키텍처).**

- **① capacity-drop**: [docs/capacity_drop_proposal.md](../docs/capacity_drop_proposal.md) — Wu(2022)
  식(22) off-ramp spill-back 차로수 감소(`lambda_eff`)를 마지막 세그먼트에 적용해 mainline
  through-capacity까지 떨어뜨림 → VSL/metering이 통합적으로 의미를 가짐. plant·예측 둘 다 적용 필수.
- **② follower 공간 분산화**: [docs/distributed_followers_proposal.md](../docs/distributed_followers_proposal.md)
  — urban 4(A/C/D/F) + freeway 2(FW_W/FW_E) agent로 분해, `NashSolver`→Wu §IV-D `DistributedCoordinator`
  (이웃 결합변수 고정+교환). 이 망 크기엔 속도 이득 없음 — 가치는 genuine Nash·연구 충실도·확장성.

## Recommended Fixes for Codex (우선순위)

- **① (신규 1순위) freeway VSL/metering이 새로 생긴 freeway 혼잡에 반응하게.** density_exceedance=23인데
  VSL 0회 활성 — 근본 원인은 위 capacity-drop 제안(VSL이 켜질 유인 부재). capacity-drop 도입 후
  VSL/metering이 freeway 밀도에 반응하는지 점검. urban 개선으로 freeway에 실린 부하(+43%)를 받아야 함.
- **② 제어 가능한 시나리오로 재평가** — peak_demand는 urban 과포화(누적~1000)라 accumulation 추적·
  overflow 지표가 구조적으로 FAIL. demand가 용량 근처인 시나리오로 perimeter 효과를 공정 판정.
- **③ metering N_UF 추적 안정화**(mean error 262, max 2235) — ①과 연동.
- (유지) green damping/offset 도시링크 기반 — 단 corridor_delay가 이미 −517로 좋아져 우선순위 낮음.

## Should Codex Rerun Simulation?

**①(freeway VSL 반응) 수정 후 재실행.** main metric는 이미 +15.14%로 PASS이므로, 남은 건
freeway density/VSL 검증과 boundary overflow다. ①을 고치면 freeway TTT 악화가 줄어 전체 verdict가
PASS로 갈 가능성이 큼. 그리고 ②(비포화 시나리오)로 boundary 지표가 artifact인지 확인할 것.
**이번 라운드는 setpoint root cause가 닫혔고 컨트롤러가 처음으로 baseline을 이긴, 결정적 전환점이다.**
