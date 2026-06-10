# Claude Review Report

_검토 커밋: `1731b6a` (Implement extended distributed controller). 직전 검토는 `9ab1e44`(round-7)._
_요청: 확장망 + 독립 allocation module + distributed agent 재구현 검증. 코드·partition probe·54 테스트·distributed 풀 진단 run(peak_demand 3600s)·확장망 calibration으로 확인._

## Verdict

**FAIL (main metric PASS)** — Total TTT **+19.78%**(PASS). 구조(확장 6-grid, 5 urban+6 freeway agent,
독립 Allocation Module, band fine-tune, w_r→freeway 귀속)는 **설계대로 landing**했고 §3.2 allocation은
**자기 목적을 거의 완벽히 달성**(B_in=0.006, B_out=0). 그러나 acceptance가 `boundary_balance`에서 FAIL —
**원인은 allocation이 통제하지 않는 두 지표**다. ① gate 지표(CV_boundary)가 §3.2 objective(B_in/B_out)와
**다른 양**, ② **net inflow tracking error 3158 veh/h ≫ eps_U=100** — 리더는 drain(-744)을 명령하나 망은
계속 채워짐(+2413). 그 밑에 **stale N_P_crit(172 vs 확장망 calibration 355)** 와 **deep oversaturation**이 깔림.

## ✅ landing 확인 — 구조는 설계대로 (코드+probe+테스트)

- **독립 Allocation Module** (`inflow_outflow_allocation.py`): leader N_P→movement별 green setpoint, **decision당 1회**
  (`coordinator.solve` 223줄, Nash 진입 전 1회 호출). objective = `safe_balance_index(in)²+safe_balance_index(out)²`
  = §3.2 Eq 9 (`||k||₂²/||k||₁² − 1/dim`). Eq 10은 `_project_net_flow`(net→target, eps_U), Eq 11-14는 green
  bounds. PSO 18입자×24iter. → **doc/블록도와 일치.**
- **band fine-tune**: `urban_follower._clamp_green_to_allocation_band`가 `g* ∈ [g_setpoint±5s]`로 clamp,
  offset은 green-wave(net-neutral) — **doc의 "green은 모듈, agent는 band+offset" 구조 그대로.**
- **partition on-ramp 버그 수정**: `_urban_signal_for_movement`가 `phase`(`A_p2`→`A`)로 owner 유도 →
  probe 결과 **orphan on-ramp 0, orphan off-ramp 0**(round-7 고아 4개 해소). U_D/U_F가 ramp/off-ramp 정상 소유.
- **agent 수**: urban 5(U_A,U_B,U_C,U_D,U_F), freeway 6(F_W0..F_E2). E 제외. **확정 설계와 일치.**
- **w_r→freeway 귀속**, 54 테스트 통과, distributed run 정상 실행.

## ★ FAIL 원인 — allocation이 통제 못 하는 두 지표 (실험 증거)

검증 gate(`metrics.py:189-191`): `boundary_balance PASS ⟺ CV_boundary ≤ baseline AND OverflowRatio ≤ baseline
AND net_inflow_tracking_error ≤ eps_U`. allocation은 **B_in/B_out**를 최소화하는데 gate는 **CV_boundary·net tracking**으로 판정.

**① 지표 불일치 (metric mismatch).** §3.2 objective `B_in=0.00594, B_out=0`(거의 0=완벽 균등) — 모듈은 자기
목적을 달성. 하지만 gate의 `CV_boundary=1.041 > baseline 1.000`로 FAIL. **B(density inverse-participation,
inflow끼리/outflow끼리)와 CV(boundary 큐 std/mean, 전 gate 묶음)는 다른 양** → B를 0으로 만들어도 CV는 안 움직임.

**② net inflow tracking error 3158 ≫ eps_U=100 (31배).** run_log(20스텝) 분석:
- `net_inflow_target` mean **−744** veh/h (음수=drain, −800에 clip). `realized net_inflow` mean **+2413** veh/h (양수=채움).
- `urban_accumulation` mean **1671** veh vs `target` **157** veh → accumulation error **1514** veh.
- 즉 **리더는 빼내라는데 망은 채워짐.** 누적이 목표의 ~10배라 perimeter가 max drain을 계속 명령하나 도달 불가.

## ★ 근본 — stale N_P_crit + deep oversaturation

- **config `N_P_crit_veh = 172.225`는 옛 4-신호 망 값.** 확장망 재calibration 안 됨.
- 내가 확장망 calibration 실행(`calibrate_setpoints`, peak_demand, scales 0.75~2.5): **n_crit = 354.809**
  (max_production 7186.7). → **config 172는 실제의 절반.** 명백한 stale.
- 단 **재calibration만으론 부족**: peak_demand 실제 누적(~1671)은 calibrated crit(355)의 **4.7배**. 355로
  고쳐도 feedback target은 여전히 강한 음수(drain)·−800 clip, realized 여전히 +2413 → tracking error 거의 불변.
  → **deep oversaturation 영역의 controllability 한계**(또는 net-inflow 정의/eps_U=100이 이 영역에 비현실적).

## ★ 남은 버그 — partition neighbor map (메타데이터, run은 안 깨짐)

probe 결과: **urban→freeway neighbor가 링크 레벨 `F_W`/`F_E`를 가리키나 freeway agent는 세그먼트 레벨
`F_W0..F_W2`/`F_E0..F_E2`로 생성** → **phantom neighbor 4개**(U_D/U_F→F_W,F_E 실재 안 함), **비대칭 edge 8개**.
- 근본원인: `build_agent_specs` 101-105줄 `_freeway_agent_id(net.ramp_to_freeway[ramp])`에 **segment index 누락**.
- **단 solve 루프가 neighbor map을 안 씀**(global coupling + aggregated `freeway_response` 교환) → run은 안 깨짐.
  그러나 (a) 문서화된 per-agent neighbor 교환이 실제론 global이고, (b) partition 자동검사 테스트
  (`test_distributed_agent_partition_matches_topology`)가 **개수·on-ramp 귀속만 검사하고 doc가 요구한
  "이웃 대칭/phantom 0"은 검사 안 함** → 버그가 통과됨.

## 결론 / 권고 (영향 순)

- **P0 — N_P_crit 재calibration**: 172.225 → ~355(확장망 calibration). config가 옛 망 기준이라 perimeter
  target이 물리적으로 틀림. 필요조건(but 충분조건 아님).
- **P0 — acceptance를 §3.2와 정합**: `boundary_balance`를 **B_in/B_out 기준으로 gate**(§3.2 충실, 이미 달성)할지,
  아니면 **CV_boundary(큐 분산)가 진짜 연구 목표**라 §3.2 density-IPR이 잘못된 proxy인지 **결정**해야 함.
  현 상태는 컨트롤러가 *최적화하지 않는 지표*로 평가받아 구조적으로 FAIL.
- **P1 — net inflow controllability 진단**: peak_demand에서 drain(−744)이 물리적으로 가능한지. net-inflow
  정의에 off-ramp 도착/boundary 큐 intake가 포함돼 부풀려지는지 확인. eps_U=100이 oversaturation에서
  달성 가능한 값인지(regime-aware acceptance 검토).
- **P2 — partition neighbor map 수정**: urban→freeway neighbor를 **세그먼트 레벨 agent id**(merge=F_*1,
  off-ramp=F_*2)로. + doc가 요구한 **neighbor 대칭/phantom 0 self-check 테스트 추가**(현 테스트는 미검사).

## 다음 검토 대상
- 재calibration + acceptance 정합 후 distributed 풀 run에서 boundary_balance가 통과 가능한지.
- genuine per-agent Nash: 현재 global coupling 교환이라, neighbor map 수정 후 실제 이웃 단위 교환으로
  가는지(아니면 "분산"이 명목상인지) 확인.
