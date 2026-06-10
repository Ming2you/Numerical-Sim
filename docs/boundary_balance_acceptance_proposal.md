# Boundary-Balance Acceptance 정합 제안 — §3.2 밀도 균등 지표로 gate 통일

대상: Codex. 목적: `boundary_balance` acceptance가 컨트롤러가 **최적화하지 않는 지표**로 판정해
구조적으로 FAIL한다(round-8). 사용자 결정 = **§3.2 밀도 균등(B)이 연구 목표**. 이에 맞춰 (1) 평가 지표를
**allocation objective와 동일한 movement-level 밀도 B**로 통일하고, (2) **degenerate(포화/공큐) 가드**를
넣는다. **단 의미 있는 평가는 망이 제어 가능한 regime에서만** — N_P_crit 재calibration + 제어 가능
시나리오는 별도 선행작업(아래 §4).

## 1. 문제 — "균형 지표"가 3종류이고 서로 불일치 (round-8 증거)

현재 코드에 balance를 재는 양이 **세 개**, 서로 다른 벡터다.
1. **Allocation objective B** (`inflow_outflow_allocation.py:163-165`): 11 inflow / 11 outflow **movement의
   post-service 밀도**`(queue−flow·dt)/storage` 기준. → **모듈이 실제 최소화하는 것.**
2. **Validator/리포트 B_in/B_out** (`urban_follower.py:270-271`): **boundary_in/out 링크 큐**`state.boundary_queue`
   raw 값 기준. movement도 post-service도 아님.
3. **Gate 판정 지표** (`metrics.py:189-191`): **CV_boundary**(전체 14 boundary 큐 std/mean) + OverflowRatio
   + net_inflow_tracking.

→ 컨트롤러는 #1을 최적화, 리포트는 #2를 표시, **합격은 #3로 판정.** 셋이 달라 컨트롤러가 자기가
최적화하는 지표로 평가받지 못한다.

## 2. ★ 그러나 현재 regime에선 B가 degenerate (gate를 그냥 B로 바꾸면 안 됨)

round-8 distributed run(peak_demand 3600s) 마지막 스텝 boundary 큐 실측:
```
IN 큐 : A_left=168.7, A_top=125.5, B_top=C_right=C_top=D_left=F_right=240.0 (cap 최대치)
OUT 큐: 전부 0.0
→ B_in=0.00594(작음), B_out=0(0), CV_boundary=1.041(큼)
```
- **B_out=0**: out 큐가 항상 0(차량이 빠져나가 boundary에 안 쌓임) → 무조건 0. **trivially 통과.**
- **B_in 작음**: 균형이라 작은 게 아니라 **7개 중 5개가 cap(240)에 박혀** 균일 → **gridlock된 균일.**
- → 지금 gate를 B로 바꾸면 **의미 없이 자동 통과**(CV→B goalpost 옮기기). **부적합.**

**진짜 병목 = 포화 자체.** IN 큐가 cap에 박힌 건 망이 막혀 gate가 더 못 받는 상태. 큐가 cap/0에
박혀 있으면 "밀도 균형"은 **자유도가 없어 논할 수 없다.**

## 3. 코드 변경 지시 (정합 + 가드)

> 전제: 아래는 §4(포화 해소)가 된 **뒤에** 의미를 가진다. 지표/가드는 지금 넣되, "통과"는 제어 가능
> regime에서만 신뢰한다.

1. **단일 §3.2 B 정의로 통일** — 평가 지표를 #2(boundary 큐 B) 말고 **#1과 동일한 movement-level
   밀도 B**로 한다. 즉 `safe_balance_index`에 들어가는 벡터를 **11 inflow / 11 outflow movement의 밀도**
   `(movement 큐)/(movement storage)`로(allocation objective와 같은 함수·같은 movement 집합·같은 정규화).
   - allocation objective와 gate가 **글자 그대로 같은 B**를 보게 한다(한 helper로 계산해 양쪽 호출).
2. **gate 교체** (`metrics.py:189-191`): `CV_boundary ≤ baseline` 조건을 **`B_in ≤ eps_balance` AND
   `B_out ≤ eps_balance`**(movement-level)로 교체. `OverflowRatio ≤ baseline`·`net_inflow_tracking_error
   ≤ eps_U`는 **유지**(이건 B/CV와 무관한 별개 항목). `eps_balance`는 config 신규 파라미터.
   - CV_boundary·MaxMin은 **삭제하지 말고 descriptive 지표로 강등**(리포트엔 계속 표기, 합격 판정엔 미사용).
3. **★ degenerate 가드** — balance 평가 전 다음을 검사해 **무의미할 때 trivial PASS를 막는다**:
   - inflow/outflow movement 큐 합이 ≈0(공큐) **또는** 큐가 cap에 포화(예: ≥`saturation_frac`·storage,
     `saturation_frac`~0.95)인 비율이 높으면 → balance를 PASS로 치지 말고 **`balance_degenerate=true`
     플래그 + 해당 step을 balance 집계에서 제외**(또는 별도 `controllable_steps`에서만 B 평가).
   - 진단에 `boundary_saturation_ratio`(cap 박힌 movement 비율), `boundary_empty_ratio`(공큐 비율) 추가.
4. **리포트 표기**: B_in/B_out(movement-level, 합격 기준), CV_boundary/MaxMin(descriptive), saturation/empty
   ratio, controllable_steps 수를 함께. "B가 작아도 포화면 무의미"가 드러나게.

## 4. 선행 prerequisite (별도 작업 — 이번 범위 밖, 다음 라운드)

지표/가드를 넣어도 **제어 가능 regime이 아니면 통과는 신뢰 못 함**. 다음 두 가지 선행 필요:
- **N_P_crit 재calibration**: config `172.225`는 옛 4-신호 값. 확장망 calibration = **354.809**(`calibrate_setpoints`).
  → config `leader.N_P_crit_veh`(+ 연동 밴드/타겟) 갱신.
- **제어 가능 시나리오 선정**: peak_demand는 누적이 critical의 4.7배(deep oversaturation)라 boundary 큐가
  cap에 박혀 balance 평가가 무의미. 누적이 critical 근처에서 움직이는 시나리오(중간 수요/조절 가능)에서
  acceptance를 평가하도록. (시나리오는 사용자와 다음에 결정.)

## 5. 검증
- objective와 gate의 B가 **같은 helper·같은 벡터**로 계산되는지(코드 일치) 단위 테스트.
- degenerate 가드: 인위적 입력(① 모든 movement 큐=0, ② 모든 큐=cap)에서 `balance_degenerate=true`가 뜨고
  trivial PASS가 **안 나는지**.
- round-8 재현 run(peak_demand)에서 `boundary_saturation_ratio`가 높게 잡히고 balance가 degenerate로
  표시되는지(현 B_in/B_out=거의0의 정체가 포화임이 드러나는지).
- (선행 후) 제어 가능 시나리오에서 movement-level B가 **실제로 감소**(큐비례 대비)하고 gate가 의미 있게
  통과/불통과하는지.

## 주의
- 이 작업은 **acceptance 정의를 §3.2와 일치**시키는 것이지, FAIL을 인위적으로 PASS로 만드는 게 아니다.
  degenerate 가드가 핵심 — 포화 상태를 "통과"로 위장하지 않게 한다.
- `net_inflow_tracking_error`(drain 추적, round-8 3158≫eps_U=100)는 이 doc 범위 밖의 별개 문제
  (N_P_crit + controllability). 여기선 건드리지 않는다.
