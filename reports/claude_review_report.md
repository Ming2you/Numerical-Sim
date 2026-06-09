# Claude Review Report

_검토 커밋: `e5caadb` "Implement nested coupled plant" (직전 검토는 `c4e68b3`)._
_요청 관점: 게임(Stackelberg/Nash) 구조와 on-ramp/off-ramp 결합이 plant뿐 아니라 게임 안에서도 닫혔는지 검증. 직전 리포트의 P0/P1 지적과 사용자 제안 2저수지 결합안(ⓐ~ⓔ) 대조._

## Verdict

**FAIL** — 인증 단계는 아직 미달. 다만 직전 대비 구현-검증이 크게 전진했다.

핵심 P0(중첩 결합 순서)와 P1#3(팔로워 예측을 결합 plant로 통일)은 **실제로 닫혔고 36/36 테스트 통과로 뒷받침**된다. 남은 블로커는 좁다. (1) **on-ramp 결합이 여전히 물리적으로 작동하지 않음**(사용자 제안 2저수지 미구현 — urban green이 ramp 유입을 제어하지 못함), (2) **현재 모델 기준 시뮬레이션 증거가 여전히 없음**(`codex_run_report.md` stale, `outputs/` git-ignore), (3) **결합-예측 팔로워의 실행 비용(feasibility) 미검증.**

테스트 증거: `python -m unittest discover -s src/tests` → **36개 통과(OK)** (numpy 2.3.5 / Python 3.12).

## 게임 구조 / 결합 검증 (요청 핵심)

플레이어 배치는 동일하다. 리더 1(`leader.py`, N_P_star·N_UF_star) + 팔로워 2(freeway=ramp/VSL, urban=green/offset/배분), `nash_solver.py`가 중재.

**닫힌 것:**
- **세로축 Stackelberg**: 정상 유지(`stackelberg_mpc.py`, 후보 열거→`run_coupled_interval` 평가→최소 선택).
- **① freeway가 urban 제어를 반영**: `freeway_follower._transition_node`가 이제 `run_coupled_interval`로 예측하고(`freeway_follower.py:217`) `last_control`의 green/offset/allocation을 prediction에 포함(`:213-215`). `freeway_follower_coupled_prediction=1`. → P1#3 닫힘.
- **② urban이 freeway 응답을 사용**: `urban_follower._freeway_pressure(freeway_response)`(`urban_follower.py:35-74`)가 freeway infeasibility를 스칼라 압력으로 변환해 green/allocation에 반영(`:102-104`, `:153-171`). 직전엔 인자만 받고 안 쓰던 부분.
- **off-ramp 결합(물리적으로 실재)**: urban storage가 freeway off-ramp 유출을 제약(`off_ramp_capacity_by_freeway_link` → `freeway_substep`의 `offramp_capacity_veh_h`), urban green/allocation이 off-ramp storage를 비워 freeway 유출 용량을 회복. 중첩 루프 안에서 urban substep이 freeway substep보다 먼저 돌아 같은 interval 내에 반영됨(`coupling.py:75-99`).

**여전히 비어 있는 것 (게임 결합의 핵심 절반):**
- **on-ramp 2저수지(사용자 제안 ⓒ/ⓓ) 미구현.** `urban_substep`은 `demand.ramp_arrival`을 on-ramp movement queue에 넣고(`:270-273`) ramp metering release로 빼지만(`:275-286`), **on-ramp movement는 green 게이트 출발 루프에서 여전히 skip**된다(`:291`). 즉 urban green(`u_on`)이 ramp 유입을 제어하지 못한다. 큐를 urban으로 옮긴 **단일 저수지**일 뿐, `x_on → (green) → w_r` 2저수지가 아니다.
- 그 결과 urban follower가 freeway 압력에 반응해 on-ramp phase에 green을 더 줘도(`urban_follower.py:102-104`) **물리 효과가 없다(cosmetic)** — 그 phase가 배출하는 차량이 없기 때문. urban→freeway 결합 중 **실효는 off-ramp 쪽 하나뿐**이다.
- 근본 원인은 토폴로지: on-ramp로 유입되는 urban 접근부 movement가 없어 유일한 공급원이 외생 `demand.ramp_arrival`이다. `u_on`을 만들려면 green으로 on-ramp에 방출하는 urban movement를 추가하고 `ramp_arrival`을 그 movement의 수요로 옮겨야 한다.

**결합 강도의 비대칭:** freeway는 urban 제어를 **전체 결합 plant로(고충실도)** 보지만, urban은 freeway를 **거친 스칼라 압력으로(저충실도)** 보고 그나마 두 채널 중 on-ramp green은 무효다. 따라서 J_U의 freeway-행동 의존성은 약하고 일부 cosmetic이다.

## Critical Issues

1. **현재 모델 기준 시뮬레이션 증거 부재(직전과 동일, 미해결).** `reports/codex_run_report.md`는 이번 커밋에서 변경되지 않아 여전히 METANET 재작성 이전 실행이다. `.gitignore:8`이 `outputs/` 제외, 산출물 0건. smoke가 `improvement=-5.67%`를 출력하나 이는 축소 config의 스모크라 인증 근거가 못 된다. CLAUDE.md §5의 `control_timeseries.csv` 활성도 검증 불가.
2. **on-ramp 결합이 게임에 실재하지 않음.** 위 "비어 있는 것" 참조. "통합(integrated) urban-freeway" 주장은 off-ramp 한쪽으로만 성립한다.

## Methodological Issues

1. **Nash 반복 사이 plant 재시뮬 없음(③ 부분 잔존).** `nash_solver.py:61-124`는 매 iteration 동일 `state`를 두 팔로워에 전달한다. 다만 이제 freeway 응답이 urban 제어에(결합 예측), urban 응답이 freeway 압력에 의존하므로 **상호 의존은 생겼다** — best-response 사상이 비자명해졌다. "고정 state 위의 one-shot Nash"라는 점은 명시 문서화 권장.
2. **결합-예측 팔로워의 비용(신규 우려).** `_transition_node`가 beam 전개의 매 노드마다 `run_coupled_interval`(K_cf·K_fu=36 subiter)을 호출하고, 이게 Nash(≤10)×리더 후보(15+) 안에 중첩된다. 직전 권고했던 "경량 결합 예측"이 아니라 full plant를 썼다. 기본 config 전체 실행이 매우 느릴 수 있고, smoke가 통과하는 건 CLI override로 horizon/search를 줄였기 때문이다 → 인증 rerun의 실행가능성 위험.
3. **수렴/진동(⑤) 현실화 가능.** 결합이 실제로 생겼으므로 fixed-point 진동·`max_nash_iter` 도달·`non_convergence_penalty` 지배 가능. `residual_control`은 여전히 mixed-unit max라 약함.

## Code-Level Issues (주장 검증 — 대부분 긍정)

- **중첩 결합 순서(P0#1) 정확히 구현.** `coupling.py:69-122`가 `for K_cf` 안에서 on-ramp 동기화→ramp release→`for K_fu` urban substep→off-ramp 용량→`freeway_substep`→off-ramp 도착 스케줄 순으로 돈다. spec 3.4.3 순서와 일치. `coupling_nested_order_active=1`.
- **TTT 이중계상(직전 ① 잠복버그) 해소.** coupled 모드에서 `freeway_substep(update_ramp_queues=False, include_ramp_queue_ttt=False)`로 ramp 큐 보존·TTT를 urban 쪽 1회로 일원화(`coupling.py:102-104`, `metanet.py:171-175,259-260`). on-ramp 큐는 `urban_substep`이 소유.
- `freeway_step`/`urban_step`은 substep wrapper로 분해돼 하위호환 유지(`metanet.py:314`, `urban_queue_model.py:416`).

## Simulation Validity Issues

1. baseline/proposed 동일 결정론적 수요는 유지(구조적으로 OK).
2. 현재 모델 결과 부재로 개선율·활성도·경계 균형을 증거로 평가 불가(Critical 1).
3. 결합 예측 비용 때문에 전체 시나리오 rerun 자체가 시간상 가능한지 먼저 확인 필요.

## Recommended Fixes for Codex

- **(우선) on-ramp 2저수지 실구현 또는 명시적 scope-out.** urban에 on-ramp 방출 movement(`u_on`)를 추가하고 `u_on ≤ min(green·포화유율, x_on+d_on, (ramp_queue_max−w_r)+r_ramp_drained)` receiving-space 제약으로 묶기. 안 할 거면 "on-ramp는 freeway-only 외생수요"임을 리포트/문서에 명시(현재의 cosmetic green 결합 제거).
- **결합 예측 경량화.** 팔로워 내부 예측을 full `run_coupled_interval` 대신 off-ramp 용량+on-ramp 동기화만 반영한 축소 plant로, 또는 follower horizon/beam 축소. 인증 rerun 실행가능성 확보.
- **urban→freeway 결합 충실도 보강.** 스칼라 pressure 대신 실제 ramp_metering/off-ramp 용량을 쓰고, on-ramp green이 무효인 현 상태를 제거.
- **현재 모델 진단 rerun + 산출물 보존**, `codex_run_report.md`를 현재 커밋 기준으로 갱신(지금 stale).
- (유지) baseline 모드 구분/문서화, 누락 metric(`speed_drop_reduction`, `number_of_stops_proxy`).

## Should Codex Rerun Simulation?

**진단용은 Yes, 인증용은 아직 No.**
중첩 결합 plant가 들어왔으니 현재 모델 진단 run은 의미가 있다. 단 (a) 실행시간이 기본 config에서 현실적인지 먼저 확인(또는 축소 config로), (b) on-ramp 결합이 실구현/scope-out으로 정리되기 전까지 결과는 진단용으로만 해석하고 8% 인증 판단은 보류.
