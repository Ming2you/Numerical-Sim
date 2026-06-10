# Claude Review Report

_검토 커밋: `9ab1e44` (capacity-drop `5630e4a` + VSL probe `2b5cf64` + distributed coordinator `9ab1e44`).
직전 검토는 `a4910dd`._
_요청: capacity-drop(lane closure) 구현 검증 + 풀 진단 run. 코드·테스트·풀 run·stress probe로 확인._

## Verdict

**FAIL (main metric는 PASS 유지)** — Total TTT **+14.00%**(round-6 +15.14%에서 미세 하락).
capacity-drop 구현은 정확하나 **현실 시나리오에선 무발화(dormant)**, 강제 발화시켜도 **VSL이
TTT를 개선하지 않음**. 즉 capacity-drop은 올바르지만 이 망에선 **저효용(low-ROI)** 이다.

## ✅ capacity-drop 구현 — 정확 (코드+테스트 검증)

- **N 보존**: `freeway_substep`이 `N=ρ·L·λ`를 보존량으로 다룸(`vehicles→rho_for_flow→vehicle_raw→rho_new`).
  λ 변화 시 차량 증발 없음. ρ_max 클리핑 제거(차량 삭제 방지).
- **속도식이 `rho_for_flow`(λ 보정 밀도) 사용**: `effective_desired_speed_kmh(rho,…)`·METANET 속도식
  모두 λ 보정 밀도 → λ↓ → 밀도↑ → 속도↓ → capacity drop이 실제로 문다. (제가 강조한 핵심 반영)
- **테스트**: 차량 보존(λ 2→1.65), lambda_eff 경계값, lane-corrected speed, VSL 속도 반응 — 49개 통과.

## ✅ 메커니즘 end-to-end — capacity drop 발화 시 VSL 활성 (stress probe)

Codex stress probe(`capacity_drop_vsl_probe`, split 0.90·storage 20·urban_avg_speed 3·lane_reduction 0.75):
- `capacity_drop_active_steps=4`, `vsl_active_steps=4`, `overlap_steps=4`, `lambda_min=1.25`.
→ **off-ramp가 실제로 막히면 capacity drop이 발화하고, follower가 VSL을 활성화함.** "capacity drop이
VSL을 의미있게 만드는가"의 메커니즘은 입증됨.

## ★ 그러나 두 가지 한계 (실험적 사실)

1. **현실 시나리오에선 무발화.** 풀 peak_demand run + 내 spill-back probe(split 0.45·storage 40·고수요)
   모두 **off-ramp 점유율 정확히 0, `lambda_eff=2.0`, `capacity_drop_active=0`**. off-ramp는 urban이
   바로 비워서 **현실적 방출 속도에선 절대 안 막힘**. Codex가 발화시키려고 `urban_avg_speed=3km/h`
   (비현실적)까지 낮춰야 했음. → **realistic peak_demand에선 VSL-off가 정상**이고, freeway 혼잡은
   on-ramp 합류 → ramp metering 영역. VSL validation FAIL은 비-spillback 시나리오에선 false alarm.
2. **VSL이 켜져도 TTT 개선 안 함.** stress probe: proposed `250.111` > proposed_without_vsl `249.763`
   > baseline `249.168`. VSL 활성이 **오히려 미세하게 나쁨**. 이유: off-ramp capacity drop은
   **urban이 해소**하는 거라 VSL은 상류 큐를 옮길 뿐 off-ramp-제한 용량을 회복 못 함 → throughput
   이득 없음(자유류 차량만 늦춤). 즉 off-ramp-only drop에선 VSL이 transient 관리는 해도 TTT를 못 줄임.

## 결론 / 권고

- capacity-drop은 **정확히 구현·검증**됐고 VSL 활성 메커니즘도 작동. 하지만 이 망에선
  **(a) 현실 수요에선 off-ramp가 안 막혀 무발화, (b) 발화해도 VSL이 TTT 개선 못 함** → **저효용.**
- **realistic peak_demand에선 VSL-off가 맞는 거동**이다. validation을 "off-ramp spill-back이 실제
  발생할 때만 VSL 활성 기대"로 바꾸거나, VSL FAIL을 이 시나리오에선 false alarm으로 처리할 것.
- **VSL이 TTT에 도움되려면**: off-ramp 큐가 through 교통/merge를 막는 **spillback 외부효과**가
  지배적이어야 하거나, **merge(on-ramp)측 capacity drop**(VSL이 직접 해소 가능)이 필요. 현재
  off-ramp-only drop으론 한계. — 단 freeway TTT(~270)가 urban(~2200)에 비해 작아 **ROI 낮음**.
- **높은 ROI 다음 작업**: ① urban 측(지배적 TTT), ② **distributed coordinator(#2, 1차 구현됨)**
  검증 — genuine per-agent Nash. VSL 강도/penalty 튜닝은 후순위.

## 다음 검토 대상 — distributed coordinator (이번에 1차 landing)

`distributed_coordinator.py`가 추가됨(`mpc.follower_solver_mode: distributed`, 기본 `two_block`).
- ✅ agent partition·이웃맵을 config에서 **자동 유도**(검증함: U_D=[F_W,F_E], F_E=[U_D,U_F] 올바름).
  proposal doc의 손-작성 이웃맵 오류는 코드와 무관(문서만 정정 push 완료).
- Codex 자인 남은 차이: urban agent가 MILP 아님(기존 휴리스틱서 자기 변수만 추출), freeway agent SQP
  아님, agent별 N_P_star 분담 약해 distributed smoke의 boundary tracking 실패.
- → 다음 라운드: `follower_solver_mode: distributed`로 풀 run 돌려 (a) coordinator가 실제 agent별
  local solve+ỹ 교환으로 도는지, (b) 2-블록 대비 동등 이상인지, (c) genuine 상호 best-response 확인.
