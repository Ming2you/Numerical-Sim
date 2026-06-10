# Claude Review Report

_검토 커밋: `ee85ee1` "Implement lightweight freeway boundary forecast" (직전 검토는 `ed1c7c6`)._
_요청 관점: 수정 ①(follower 탐색에서 full coupled 재시뮬 제거) 반영 여부, 계산복잡도 실측, 그리고 그것이 현재 모델 진단 run을 가능케 했는지. 코드·테스트·실측으로 검증._

## Verdict

**FAIL** — 인증 미달. 단, **4라운드간 1순위 블로커였던 계산복잡도(#1)가 실제로 해소**됐다.

`freeway_follower`가 후보 평가에서 full `run_coupled_interval`을 버리고, **고정된 urban
control로부터 on-ramp/off-ramp 경계만 예측하는 경량 plant**(`_lightweight_transition`)로
바뀌었다. 이는 docs/wu2022_distributed_reference.md가 제시한 "경계변수 고정 + 자기
서브망만 평가"(Wu §IV-D) 방식과 정확히 일치한다. 실측 결과 **한 MPC decision이 78.7s →
17.5s(약 4.5배)** 로 떨어져, 이제 풀 진단 run이 현실적(7200s 시나리오 ≈ 12분)이다.

**현재 모델 풀 진단 run(peak_demand, 7200s)을 직접 실행**해 4라운드만에 증거를 확보했다.
결과 **Total TTT −10.64%(proposed가 baseline보다 나쁨)**. 그리고 **피해가 전적으로 urban
쪽**이며 컨트롤러가 자기 목표(boundary balance)를 오히려 악화시키는 명확한 이상 징후가
드러났다(아래 "진단 run 결과" 절). 공간 분할(#2)은 미착수. 따라서 인증 보류이며, 다음
과제는 비용이 아니라 **urban 제어 로직이 baseline보다 나쁜 원인**이다.

테스트: `python -m unittest discover -s src/tests` → **38개 통과(OK)**. 타이밍 실측:
default config 첫 decision **17.54s**(horizon=3, leader=15, nash=10).

## ✅ 닫힌 것 — #1 계산복잡도 (검증 완료)

- `_transition_node`(`freeway_follower.py:379-439`)가 `run_coupled_interval` 대신
  `_lightweight_transition`(`:334-377`)을 호출. `run_coupled_interval` import 자체가 제거됨.
- `_lightweight_transition`은 K_cf freeway substep만 돌리며, 각 substep에서:
  - `_apply_onramp_boundary_forecast`(`:239-268`): **고정 urban green**으로부터
    `estimate_onramp_green_release_flows`로 `x_on→w_r` 유입을 예측·반영(=Wu의 결합변수 고정).
  - `_actual_metering_release`(`:270-311`): `w_r`에 **실제 존재하는 차량만** metering으로
    freeway에 주입(요청량이 아니라 actual). 보존 정확도 개선.
  - `off_ramp_capacity_by_freeway_link` + `freeway_substep`(freeway-only) +
    `_consume_lightweight_offramp_storage`로 off-ramp 경계 갱신.
  - diagnostics `freeway_follower_lightweight_prediction=1`, `coupled_prediction=0`.
- 효과: 후보 루프에서 urban 전체 재시뮬(K_cu×movement 루프)이 제거됨. **78.7s→17.5s 실측.**
  → **현재 모델 진단 run이 비로소 실행 가능**(이 4라운드 핵심 블로커 해소).

## 진단 run 결과 — 이상 징후 (peak_demand, 7200s, seed 42)

Claude가 직접 실행(`outputs/claude_diag_peak_full/`). baseline=fixed_signal_fixed_speed,
proposed=stackelberg_mpc. **Total TTT 2889.8 → 3197.3 (−10.64%)**. 분해와 이상 징후:

| 지표 | baseline | proposed | 판정 |
|---|---:|---:|---|
| Total TTT | 2889.8 | 3197.3 | −10.64% (악화) |
| Freeway TTT | 187.8 | 195.8 | 거의 동일(uncongested) |
| **Urban TTT** | **2702.0** | **3001.5** | **+11.1% 악화 ← 피해의 전부** |
| Boundary CV | 0.145 | 0.305 | 2배 악화 |

**이상 징후 (control/state timeseries 근거):**
1. **VSL이 한 번도 활성화되지 않음** — `vsl_active_steps=0`, control_timeseries 전 step
   `vsl_FW_W=vsl_FW_E=100`. freeway가 혼잡하지 않아서(`density_exceedance_duration=0`,
   freeway TTT 188로 미미) VSL이 할 일이 없음. → 이 시나리오는 **freeway 제어가 무의미한
   urban-dominated 문제**. VSL/ramp 효과를 보려면 freeway를 혼잡시키는 시나리오 필요.
2. **Leader가 초기에 추적 불가능한 N_UF_star를 고름** — step0=4000, step1=6000(=용량 전체)
   인데 실제 ramp release는 step1에 ~4230뿐 → `mean_total_metering_error=624`,
   `max_metering_violation=3884`. 이후 N_UF_star=2000으로 떨어지면 4×500=2000으로 추적됨.
   즉 leader N_UF_star 선택이 **초기 비현실적**이라 metering이 "active"여도 무의미.
3. **★ 핵심: urban 컨트롤러가 자기 목표(boundary balance)를 역으로 악화시킴.**
   - `CV_boundary` 0.145→0.305, `boundary_queue_balance_improvement=−110%`,
     `OverflowRatio_boundary=0.5`, `net_inflow_tracking_error=84.5`(>eps_U=100 근접).
   - `MaxMin_boundary`가 **시간에 따라 단조 증가**(20→33.7→47.3→50.7→55.5→62→70+) —
     경계 큐 불균형이 누적 발산. urban follower의 green/allocation이 baseline 균등분배보다
     **경계 큐를 더 벌림**.
   - offset 제어도 역효과: `corridor_delay_change=+299.5`(corridor 지체 증가).
4. **green split이 초기에 심하게 진동** — A_p2: 90.6(step0)→89.9→47.5(step2)→53→...
   큐비례 분배가 불안정. 초기 과도 진동이 urban TTT를 키움.

**해석**: 비용(①)이 풀려 드러난 진짜 문제는 **urban 제어 로직이 fixed 베이스라인보다 나쁘다**는
것이다. freeway 쪽은 (이 시나리오에서) 유휴. 따라서 −10.64%의 원인은 거의 전부 urban follower의
green/offset/allocation 휴리스틱이 boundary balance·corridor 지체를 **악화**시키는 데 있다.

## Critical Issues

1. **proposed가 baseline보다 −10.64% 나쁨, 원인은 urban 제어.** 위 이상 징후 3·4 참조.
   urban follower(green 큐비례 분배, offset, inflow-outflow allocation)가 자기 목표인
   boundary balance를 역으로 악화. **최우선 수정 대상.**
2. **Leader N_UF_star 선택이 초기 비현실적**(이상 징후 2) → metering tracking 무의미.
   leader 후보·목적함수에 ramp 용량 현실성 반영 필요.
3. **현재 시나리오가 freeway 제어를 검증 못 함**(VSL 0회 활성, freeway 유휴). 통합 제어
   효과를 보려면 **freeway를 혼잡시키는 시나리오/수요**(oversaturated, incident)에서 재검증 필요.
   (`codex_run_report.md`는 여전히 stale → 위 현재 모델 결과로 갱신 권장.)

## ❌ 미착수 — #2 공간 분할 (다음 마일스톤)

여전히 FreewayFollower 1개(전 링크·램프 합동) + UrbanFollower 1개(전 신호) 구조이고,
리더(15)×Nash(10) 열거 안에서 직렬로 푼다. 경량화로 freeway 블록은 싸졌지만, 교차로/링크
단위 agent로 **분해되지는 않았다**. Wu식 진짜 분산(병렬 local solve + 경계변수 교환)은
docs/wu2022_distributed_reference.md §7대로 후속 구현 필요. 단, 이번 ①은 그 문서의
"경계변수 고정" 원리를 먼저 적용한 옳은 첫 단계다.

## Methodological Issues

- **경량 예측 ≠ 실제 plant(허용된 trade-off).** follower는 이제 추정 경계로 최적화하므로
  실제 coupled plant와 다소 괴리된다. 이는 의도된 비용↔충실도 교환(Wu도 동일, iteration
  합의로 보정). 단 현재 Nash는 반복 간 plant 재시뮬이 없어 이 괴리를 좁히는 메커니즘이
  약함 → ② 분산화 시 결합변수 교환으로 자연 해소될 부분.
- (직전과 동일) one-shot Nash, state 고정 — 문서화 권장.

## Code-Level Issues (긍정)

- 2저수지 보존·TTT 소유권·중첩 결합 순서·경량 경계예측 모두 코드·테스트로 검증됨.
- on-ramp metering이 actual drained 차량 기준으로 freeway에 주입되도록 정정(보존 정확).
- 38/38 테스트 통과.

## Recommended Fixes for Codex (우선순위)

- **① (완료) follower 경량화** — 검증됨. 추가로 leader_candidate_count·max_nash_iter도
  낮추면 풀 run이 더 빨라짐(현재 ~12분, 보조 최적화).
- **② 공간 분산화(다음 마일스톤·정공법)** — docs/wu2022_distributed_reference.md §3~7대로
  신호 A/C/D/F→urban agent 4, FW_W/FW_E→freeway agent 2, 경계변수 교환·S_max 반복.
- **③ (1순위·신규) urban follower가 baseline을 악화시키는 원인 수정** — 풀 run −10.64%의
  주범. green 큐비례 분배의 초기 진동·offset 역효과(corridor +299.5)·allocation의 boundary
  balance 악화(CV 0.145→0.305, MaxMin 단조증가)를 잡아야 함. 최소한 "fixed 베이스라인보다
  나쁘지 않게"가 1차 목표. 의심처: `_green_times` 큐비례 분배, `_offsets` 진행 계산,
  `_allocation`의 N_P_star/boundary 균형 로직.
- **④ leader N_UF_star 후보 현실화** — 초기 4000/6000 같은 추적불가 타겟 억제(ramp 용량·
  receiving 반영).
- **⑤ freeway 제어 검증용 혼잡 시나리오** — 현재 peak_demand는 freeway 유휴(VSL 0회 활성).
  oversaturated/incident 시나리오로 VSL·metering 효과를 별도 검증.

## Should Codex Rerun Simulation?

**진단 run은 Claude가 이미 실행함**(`outputs/claude_diag_peak_full/`, peak_demand 7200s,
−10.64%). 따라서 다음은 rerun이 아니라 **③(urban 제어가 baseline보다 나쁜 원인) 수정 후
재실행**이다. Codex는 `codex_run_report.md`를 위 현재 모델 결과로 갱신하고, ③ 수정 →
재run → 개선 확인 순으로 진행할 것. 8% 인증은 그 이후.
