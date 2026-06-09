# Claude Review Report

_검토 커밋: `ed1c7c6` "Reduce default MPC horizon" (직전 검토는 `e5caadb`). 이번 구간 변경: `0da5b02` two-reservoir on-ramp coupling, `ed1c7c6` horizon 8→3._
_요청 관점: (1) on-ramp 2저수지 결합이 실제로 닫혔는지, (2) 계산복잡도 폭발, (3) 공간 분할(교차로/링크 단위 agent) 부재. 코드·테스트로 직접 검증._

## Verdict

**FAIL** — 인증 미달. 단, on-ramp 결합은 이번에 실질적으로 닫혔다.

좋은 소식: **사용자 제안 2저수지 on-ramp 결합(ⓒ/ⓓ)이 정확히 구현**됐고 37/37 테스트 통과로 뒷받침된다. 직전 라운드의 "cosmetic on-ramp green" 지적은 해소됐다.
블로커: **계산복잡도가 이제 1순위 블로커다.** horizon 8→3으로 완화했을 뿐 근본원인(follower 탐색 안 full coupled 재시뮬)은 그대로라, 기본 config full run이 여전히 완료 불가(Codex도 자인). 따라서 현재 모델 시뮬레이션 증거는 이번에도 없다. 그리고 **공간 분할(교차로/링크 단위 agent)은 착수되지 않았다.**

테스트: `python -m unittest discover -s src/tests` → **37개 통과(OK)** (numpy 2.3.5 / Python 3.12).

## ✅ 닫힌 것 — on-ramp 2저수지 결합 (검증 완료)

직전 라운드 "비어 있던 절반"이 실제로 채워졌다. `urban_substep`(`urban_queue_model.py:288-323`)에서:
- `demand.ramp_arrival` → 접근부 저수지 `x_on`(=`urban_movement_queue[R*_onramp]`)에 먼저 적재(`:289-291`).
- urban green이 `x_on → w_r` 전송을 게이트: `u_on = min(x_on, T_u·green_fraction·cap_flow, ramp_space)`, `ramp_space = ramp_queue_max − w_r`(`:313-315`). **receiving-space 제약(ⓓ)까지 정확.**
- ramp metering은 `w_r(=state.ramp_queue) → freeway` release만 담당(`:295-303`).
- sync helper는 더 이상 두 큐를 복사하지 않고 각 reservoir를 독립 유지(`:56-85`).
- **TTT 소유권 정확**: `urban_ttt`가 `movement + ramp_queue(w_r) + storage`를 1회 합산(`:383-387`), freeway는 coupled 모드에서 `include_ramp_queue_ttt=False`. 이중계상·누락 없음.

결과: urban green이 **실제로 ramp 유입을 메터링**한다(green↑ → u_on↑ → w_r↑ → freeway 영향). 사용자 제안식 `x_on(k+1)=x_on+d_on−u_on`, `w_r(k+1)=w_r+u_on−r_ramp`와 일치. round-2 "cosmetic" 지적 해소.
- (경미) urban follower가 freeway 압력↑일 때 on-ramp green을 늘리는데(`urban_follower.py:102-104`), 이는 혼잡 시 ramp로 더 밀어넣는 방향이라 제어 의도 재검토 권장(정확성 버그 아님, 로직 선택).

## Critical Issues

1. **계산복잡도 폭발 — 이번 1순위 블로커이자 증거 부재의 직접 원인.**
   - 분해: 리더후보 15 × Nash 10 × freeway follower 빔서치 transition. horizon 8→3으로 transition 405→135, decision당 coupled 호출 **60,750→20,250**으로 완화(`ed1c7c6`). 그러나 근본원인은 그대로 — `freeway_follower._transition_node`(`freeway_follower.py:217`)가 후보마다 full `run_coupled_interval`(K_cf·K_fu=54 sub-iter, urban substep 포함)을 재시뮬.
   - 실측: **기본 config 첫 control decision 78.7초**(Codex log). decision ≈40개 × baseline+proposed면 full run 비현실적. Codex도 "proposed 단계는 여전히 무거워 추가 경량화 필요"라 자인, full default run 미완료.
   - 따라서 현재 모델 기준 baseline/proposed 결과를 **이번에도 생성 못 함**. `codex_run_report.md` 여전히 stale, `outputs/` gitignore.

2. **공간 분할(분산화) 부재 — 사용자 의도와 불일치.** 현재 follower는 2개뿐 — FreewayFollower 1개(R1~R4·FW_W·FW_E를 한 solve, 빔서치가 전 링크 VSL을 `product`로 결합) + UrbanFollower 1개(A·C·D·F 전부). 즉 **"1 freeway + 1 urban 블록(중앙집중)"** 이지, 사용자가 의도한 **교차로 1개=urban agent / 링크 묶음=freeway agent** 구조가 아니다. 게다가 두 블록이 리더열거+Nash 안에서 직렬로 풀리고, freeway 블록은 후보마다 전체망 재시뮬. → granularity와 분산-solve 원리 둘 다 없음.

## 참고 — Wu et al.(2022)과의 구조적 차이 (왜 그쪽은 가벼운가)

Wu의 분산 통합제어(§IV-D, §V-C)는 CC(중앙) 최대 CPU >400s를 CD(분산) <40s로 **100배** 줄인다. 차이의 핵심:
- 공간 분할: 도시 agent 15개(교차로 1개씩)+고속 agent 2개. 각자 **자기 변수만** 최적화, **병렬**.
- 이웃 결합변수를 **풀이 동안 상수로 고정**(step3), iteration 사이에만 교환 — 이웃을 재시뮬하지 않음.
- local 문제를 SQP/CPLEX(gradient)로 1회 풀이 — brute-force rollout 아님.
- 핵심 통찰: "결합 정확 반영"을 *이웃 재시뮬*이 아니라 *경계변수 고정 + iteration 합의*로 달성(충실도·비용 동시 해결).

현재 코드는 이 스펙트럼의 정반대(중앙집중 + 후보마다 전체망 rollout) 끝에 있어 무겁다.

## Methodological / Code-Level Issues

- (직전과 동일) Nash 반복 내 plant 재시뮬 없음(state 고정), one-shot Nash로 문서화 권장.
- (긍정) 중첩 결합 순서·TTT 소유권·2저수지 보존식은 코드·테스트로 검증됨. 하드코딩 relaxation 없음 유지.

## Recommended Fixes for Codex (우선순위)

- **① (1순위·즉효) follower 탐색에서 full coupled 재시뮬 제거.** `_transition_node`(`freeway_follower.py:217`)를 freeway-only `freeway_substep` 평가로 바꾸고, off-ramp 수용용량·on-ramp 결합을 **Nash iteration당 1회 urban 응답에서 계산해 고정 경계로 주입**(=Wu의 경계변수 고정). 빔 후보 루프에서 urban substep×K_cu 제거. 이게 horizon 축소보다 본질적이며 인증 run을 가능케 함.
- **② 공간 분산화(다음 마일스톤·정공법).** "2블록 중앙집중 → 교차로/링크 단위 agent가 local 문제 풀고 경계변수만 교환·S_max 반복(병렬)". Wu의 100배 절감 원천. 사용자가 원래 의도한 분할.
- ③ 추가 탐색 축소(beam_width, vsl/ramp 후보수, leader_candidate_count, max_nash_iter) — ①의 보조.
- ④ ①/③로 full run 가능해지면 현재 모델 진단 rerun + `control_timeseries.csv` 등 산출물 보존, `codex_run_report.md` 갱신(현재 stale).
- ⑤ (경미) 혼잡 시 on-ramp green↑ 방향이 ramp 유입을 늘리는 게 의도와 맞는지 재검토.

## Should Codex Rerun Simulation?

**아직 No (인증·진단 모두).** 현재 기본 config는 full run이 완료되지 않으므로(첫 decision 78.7초) 진단 run조차 생성 불가다. **먼저 ①(follower 재시뮬 제거)로 실행가능성을 확보**한 뒤에야 현재 모델 진단 rerun이 의미를 가진다. 8% 인증 판단은 그 이후.
