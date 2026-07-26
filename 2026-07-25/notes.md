# 2026-07-25 작업 노트 — P-Stack(4) 자율 재설계: Mod1 URBAN_CLF (공정 목적함수 수정)

## 목표
P-Stack(4)가 PFO(분산 기준선)에 지는 문제를 **depth를 안 건드리고**(PFO·P-CENT 공정비교 위해)
목적함수/terminal cost/가격만으로 고쳐서 PFO를 5셀 전부 이기게 한다.

## 공정성 제약 (사용자 지시)
- **LEADER_V_DEPTH(리더 rollout 깊이) 변경 금지.** 깊이를 늘려 이기면 "더 멀리 봐서" 이긴 것이지
  계층 구조가 좋아서가 아님 → PFO/P-CENT 대비 불공정.
- terminal cost(cost-to-go)의 존재 이유가 "짧은 지평으로도 올바로 판단" → 공정한 정도(定道).
- Round2의 E 콤보(LEADER_V_DEPTH=6)는 **폐기**(불공정).

## Round 2 결과 (far reshape만, depth 불변 = 공정)
| cell | PFO | PS4 base | D(far공정) | P-CENT | D−PFO |
|---|---|---|---|---|---|
| Low | 2961 | 2966 | 2966 | — | +5 동률 |
| Med | 3862 | 3781 | 3781 | 3729 | **−82 승** |
| Skew | 3835 | 3808 | 3808 | — | **−26 승** |
| Inc | 5497 | 5826 | 5683 | 5498 | +186 패(329→186 개선) |
| High | 5970 | 6131 | 6129 | 5599 | +160 패(거의 그대로) |
→ far reshape는 incident만 개선, High는 손 못 댐. Med/Skew 승리는 보존.

## 핵심 측정 (base PS4, 시나리오별)
### urban n_u 분해 = protected(실제 도심차) + boundary 큐(gating 유입대기)
| cell | protected peak/mean | boundary peak/mean | 합 peak/mean |
|---|---|---|---|
| Low | 416/212 | 426/178 | 839/390 |
| Med | 496/230 | 1396/303 | 1880/533 |
| Skew | 465/227 | 1678/360 | 2138/587 |
| Inc | 975/334 | **4397/1432** | 5372/1766 |
| High | 969/342 | **5065/1767** | 6008/2109 |

- **protected(실제 도심 차량)은 전 시나리오 <1000 (jam 1540의 63%↓) — 과포화 아님.**
  (이전 "urban 과포화, demand 손봐야" 주장은 측정오류로 철회됨)
- 폭발하는 건 **boundary 큐**(gating이 만든 유입 대기) — Inc/High서 4400~5100.
  = **과-metering 병리의 직접 신호.** P-Stack이 세게 조여 차를 경계에 쌓음 → TTT 폭발 → PFO한테 짐.

### High 손실은 100% urban (freeway 아님)
step별 (PS4−PFO) cum_ttt 격차 분해:
- freeway diff: 내내 음수(−13~−54) = **PS4가 freeway는 항상 더 좋음**.
- urban diff: step40 +64 → step75 +199 = **urban 희생이 총 손실(+161)을 만듦**.
- 즉 PS4는 urban 희생/freeway 보호 = **P-CENT와 정반대**(P-CENT는 urban 보호·freeway 양보).
- → CLF(urban 축적 벌점) 방향이 정확히 맞음.

### FAR_GATE 타임라인 (freeway capdrop 기준)
- High: ON step41→OFF49 (창 8스텝) — 그런데 urban 손실은 step40~75 지속 → gated는 후반 놓침.
- Inc: ON step20→OFF48 (창 넓음) — 커버리지 양호.
- Med: ON step44→OFF46 (창 2스텝, brief).
→ 구조적 부정합: gate는 freeway capdrop 기준인데 urban 문제는 더 오래 지속(특히 High).
  urban CLF는 excess=max(0,n_u−n_ref)가 자체 urban 게이트 → always-on+n_ref가 더 정합적일 수 있음.

## Mod1 URBAN_CLF 구현
- `mfd_far_cost_to_go`(stackelberg_mpc.py): old far_urban(n²/(2·g), n_crit1700)을
  볼록 production-curve CLF로 교체: `far_urban = excess²·tc/(2·g_eff)`,
  excess=max(0, n_u_hat−n_ref), g_eff=production drain(n_crit 지나면 붕괴→gmin),
  n_u_hat=n_u+max(0,dn)·t_tail (기울기 외삽 — H 밖 urban buildup 선반영, depth 안 늘림=공정).
- gated 플래그(`leader_urban_clf_gated`, 기본 True): far gate 동조 → Low/Med/Skew(gate닫힘)
  base와 비트동일 보존, Inc/High(gate열림)만 CLF. False면 always-on.
- env: URBAN_CLF=1, URBAN_CLF_GATED=0(always-on), URBAN_CLF_NREF/NCRIT/NJAM/PMAX/GMIN/TTAIL.
- 기본 파라미터: n_ref450, n_crit550, n_jam1540, pmax640, gmin60, t_tail0.5[h].

## Round 3 (진행 중): gated CLF, 5셀, far가중 1.0/1.0 (CLF 효과 격리)
- 성공기준: PFO 5셀 전부 이김.
- 예상 리스크: gated라 High 후반(49-75) 못 잡을 수 있음 → 그러면 always-on 변형 시도.

## far 규모·CLF 개념 결함 (오프라인 분석)
- base PS4 gate창서 **far가 이미 목적 지배**: far/rollout_ttt = Inc 1.67, High 1.42 (far ~60%).
  (best_objective: Inc 1140/High 1285, rollout_ttt: Inc 427/High 531, far: Inc 713/High 754)
- old far_urban은 죽지 않았음(gate창 mean Inc 604/High 1469) — 이전 "far dead" 주장(protected-only
  측정)은 오류. n_u는 boundary 포함 5000+라 old far도 유의미했음.
- **CLF 개념 결함**: CLF가 n_u=protected+boundary(~5000)에 urban 생산곡선 적용 → n_u>n_jam(1540)이면
  prod=0·g_eff=gmin60 → far_urban 거대(8600+, old의 6.6~7×).
  - protected(~975)는 urban MFD 생산율 배수 = gridlock 리스크(맞음).
  - **boundary 큐(4000+)는 metering 유입률(~1000-2000)로 배수** = gridlock율 60 아님 → CLF가 ~25× 과벌점.
  - → R3 gated가 과교정(병리 under-gating) 나올 수 있음. 그러면 "protected(MFD)+boundary(metering배수)"
    분리 CLF로 정련 예정.

## Round 3 결과 (gated CLF, 5셀)
| cell | PFO | PS4base | G-CLF | 판정 |
|---|---|---|---|---|
| Low | 2961 | 2966 | 2966 | base와 비트동일(gate 닫힘) |
| Med | 3862 | 3781✓ | 3781 | 비트동일(승리 보존) |
| Skew | 3835 | 3808✓ | 3808 | 비트동일(승리 보존) |
| Inc | 5497 | 5826 | 5818 | **−7뿐**(N_UF@25 2400→5400 바뀌었으나 TTT 개선無) |
| High | 5970 | 6131 | 6138 | **+7 악화**(gate창41-48 너무 좁아 무력) |
→ **gated CLF 실패.** Low/Med/Skew는 안전 보존, 하지만 Inc/High 못 고침.
  실증된 실패원인: (1)boundary+protected 합산 벌점의 dump 역인센티브, (2)freeway-capdrop gate가
  High urban 캐스케이드(step49-75)에 원천적으로 못 닿음.

## Probe 결과 (far_fw 하향가중, ground truth)
| cell | PS4base | FW03(far_fw0.3) | FW00(far_fw off) | PFO | PCENT |
|---|---|---|---|---|---|
| Inc total | 5826 | 5683(−143) | 5647(−179) | 5497 | 5498 |
| Inc fw/ur | 2584/3242 | 2633/3051 | 2745/2902 | 3995/1503 | 2874/2625 |
| High total | 6131 | 6129 | 6129 | 5970 | 5599 |
→ far_fw 하향은 Inc만 부분개선(오라클 균형쪽 이동, 여전히 +150 패)·**High 완전 무력**.
  ★확증: (1)순수 재가중은 불충분(진단의 "재가중 함정"), (2)freeway-gated 수정은 High 못 닿음.

## ★★ 잠긴 진단 (워크플로우 Phase1-2, 원자료 재검증) — 전문 results/LOCKED_DIAGNOSIS.md
PS4는 **시간분리된 두 실패, 하나의 구조적 뿌리**로 진다:
- **(A) 온셋**: Inc st25 리더가 N_UF 5700→2400 슬램 → 3스텝 rollout 안 값싼 freeway 완화를 얻으나
  차를 경계에 쏟음. 이게 씨뿌린 urban 캐스케이드 정점은 **step42-43 = 결정보다 17스텝(~3000s) 뒤
  = 540s 지평 밖**이라 rollout이 원천적으로 못 봄.
- **(B) 회복(정정!)**: 오라클의 진짜 승리 행동은 metering 아니라 **도심 green 서비스 확대**
  (PCENT green 60-70 vs PS4 45-56 → 동부하 배출 +72~85%). "metering 후퇴"는 하류 결과였음
  (회복기 metering setpoint는 PS4≈PCENT 동일; PS4는 도심이 안 빠져 내보낼 차가 없을 뿐).
- **구조 뿌리**: far_urban이 boundary+protected를 단일 g_eff로 합산배수 + N_UF는 도심 저수지에
  지렛대 없음(R3 실증) + urban 가격이 배출 flow 아닌 축적 stock(n²/2g)에 걸림.

**설계 지침(깊이 불변)**: (1) far_urban 탈합산(protected/boundary 분리, 경계 홀딩을 하류 urban TTT로
과금), (2) stock 아닌 **배출-flow(green throughput) 가격화** — 오라클의 green 확대를 리더가 선택하게,
(3) 레버↔가격 정합(urban 가격은 N_P·green에, boundary-holding 가격은 N_UF/metering에),
(4) 경계성장 leading 터미널 항 always-on(freeway-gate 비의존, High 커버).
**피할 함정**: R3 boundary-dump, n_ref≈운영점(기울기0), 순수 재가중, stock-vs-flow, 온셋 N_UF 슬램.

## ★핵심 정정 (경계 큐 TTT 계상)
`boundary_in_queue_vehicles` = urban_movement_queue(kind=="boundary_in")의 합이고
`urban_ttt = sum(urban_movement_queue)+storage`(urban_queue_model.py:1042). → **경계 큐 대기시간은
이미 scored TTT·rollout_ttt 둘 다에 계상됨.** 즉 리더 맹점은 "경계 큐를 안 봄"이 아니라 **순수 시간성**:
경계 큐 비용이 결정보다 ~17스텝 뒤에 커져 3-스텝 rollout 창엔 작게만 보임(far도 말단서 평가하니 그때 경계 미충전).
→ 올바른 수정 = **성장률 투영 leading 항**(경계가 커질 것을 선반영).

## Round 5 (진행중): 대칭 성장-투영 spillback 항 — 사용자 균형 직관 구현
- 사용자 지적(정당): freeway 벌점 제거는 틀림. P-CENT는 freeway/urban을 **거의 대등**(High 2768/2831)
  하게 나눠 가짐 = 균형. PS4는 freeway 과보호(2584/3547). → 목표=freeway 벌점 유지하되 urban을 대등·
  gating불가능하게 만들어 **대칭 균형** 회복. calibration이 균형점을 조절(구조 먼저→calibration).
- **구현 `leader_spillback_cost`**(stackelberg_mpc.py): rollout 말단 성장률로 큐를 T_lead 선형투영,
  urban(protected+**boundary포함** → gating으로 못숨김)·freeway(over-critical veh+ramp큐) **대칭** 벌점.
  선형(veh·h, hinge와 동일격리), 후보랭킹만. env SPILLBACK=1 등, 기본 off=비트동일. 스모크 통과.
  노브: SPILLBACK_W(전체)·SPILLBACK_WU/WF(★균형)·SPILLBACK_LEAD(투영)·SPILLBACK_NREF_U/F.
- **R5 1차**: A(urban-only WF=0)·B(대칭 WF=1) × Med/Inc/High, nref_u=800 lead=0.5. 성공기준 PFO 이김.

## Round 5-6 결과 (spillback) + Inc 포화 진단
- R5: A(urban-only wf0)가 **작동** — High +161→+32(거의 동률), Inc +328→+257, Med 보존.
  B(대칭 wf1)는 역효과(freeway 항이 과보호 심화). → **base가 이미 freeway 과대평가(시간적)라
  freeway 항 추가 금물; 덜 보이는 urban만 끌어올리는 게 균형 회복법**(사용자 균형직관 정교화).
- R6(w_u 스윕 2/3/4): **Inc +255서 포화**(w_u 무관), High +32~108(비단조), Med 마진 침식(wu4 -6).
- ★Inc 포화 근본원인=**metering whipsaw**: 오라클 P-CENT는 회복기 metering 매끈 지속(|Δ|~300,
  4700→4000 완만), 리더는 slam↔release 진동(|Δ|~600). spillback이 st25 슬램은 막았으나(2400→4787)
  st30에 새 슬램(2534) → 진동 자체는 못 없앰. per-step 재최적화 whipsaw(메모리 기존 관측 재확인).
- 부수확인: spillback raw 배출은 이미 PCENT보다 높으나(부하가 더 많아서), **동부하 서비스율(green)**은 낮음.

## Round 7 (진행중): control-move penalty (whipsaw 억제)
- `leader_move_cost`(stackelberg_mpc.py): 이전 committed budget 대비 |ΔN_UF| 급변 벌점 → 매끈 유도
  (표준 MPC Δu, 깊이 불변). env MOVE=1/MOVE_W/MOVE_WNUF/MOVE_WNP, 기본 off=비트동일.
- R7: spillback(wu2)+move(w∈{0.5,1,2}) × Inc/High/Med. 성공기준 Inc 포화 돌파 + 평활(|Δ|→300).

## Round 7-11 결과 및 ★★공정성 제약의 물리적 한계 증명
- **R7 control-move penalty 기각**: metering 진동은 N_UF budget이 아니라 follower realized metering에서
  옴 → budget 평활은 진동 못 줄이고(|Δ| 721 그대로) 리더만 경직 → High 파국(+1095)·Med 붕괴(+150).
- **R8 spillback+far_fw하향**: far_fw 0.5/0.25/0 **전부 bit-identical**(5758) — 무효.
- **R9 spillback+SUP_PFO**: Low -6✓/Med -108✓/Skew -39✓ 이나 **Inc +342 악화**(3/5).
- **R10 감독자 채점에 spillback 추가**(리더 목적과 동형화): Inc **+739로 더 악화**(3/5).
- **★가설 반증**: "camp_s10off는 감독자 덕에 Inc 이김"은 **틀림** — camp의 Inc PFO위임 **0/80(0%)**.
- **★Inc 승패 지표 발견**: urban 축적(uAcc)을 400대로 묶느냐. 승자 PFO 428→427→220(bndQ 55~159),
  camp 428→457→386(bndQ 68~247) / 패자 base 421→921→886(bndQ→691), spill 423→860(bndQ→840).
- **R11 nref_u calibration(400/500/600)**: **전부 bit-identical**(5752, uAcc_peak 879 동일).
  이유(수학): n_u가 이미 nref를 한참 초과(step40 n_u=6421 vs nref 400~800) → excess=n_u−nref에서
  nref는 **모든 후보에 동일한 상수** → **argmin 불변**. hinge 포화 구간이라 nref는 순위에 무영향.
  (far_fw 하향이 bit-identical이었던 것도 같은 이유.)

### ★★★핵심 실증: 3스텝 지평에 구별 정보가 물리적으로 없다
spillback은 선택을 **바꾼다**(base 대비 21/80 스텝 다름, 항은 작동). 그런데:
```
step25: ΔN_UF = +2700 (metering 2400→5100, 2배 이상 개입) → 다음스텝 uAcc 변화 = +10 veh (435 vs 445)
step30: ΔN_UF = -750                                      → 다음스텝 uAcc 변화 = -14 veh
```
**리더의 가장 강한 개입조차 단기 urban 상태를 거의 안 바꾼다** — 차이는 수천 초 뒤에 나타난다.
→ 목적함수에 어떤 항을 더하거나 어떻게 calibrate해도, **그 항이 3스텝 말단 상태에서 평가되는 한**
   Inc의 좋은 결정과 나쁜 결정을 구별할 수 없다. **공정성 제약(depth 불변)의 수학적·물리적 한계.**
   (지평을 늘리면 넘을 수 있으나 PFO/P-CENT 대비 불공정이라 사용자 금지.)

## ★H3(공정 기본지평) 최종 5셀 스코어보드 — 확정
| cell | PFO | PS4base | spillback | spill+SUP | PCENT |
|---|---|---|---|---|---|
| Low | 2961 | 2966 | 2966 (+5) | **2948 (-13)✓** | — |
| Med | 3862 | 3781 | 3781 (-82)✓ | **3755 (-108)✓** | 3729 |
| Skew | 3835 | 3808 | 3808 (-26)✓ | **3795 (-39)✓** | — |
| Inc | 5497 | 5826 | 5752 (+255) | 6236 (+739) | 5498 |
| High | 5970 | 6131 | **6048 (+78)** | 6076 (+107) | 5599 |
→ **H3 최고 = spillback+SUP_PFO 3/5** (Low/Med/Skew 승, Inc/High 패). spillback 단독 2/5.
   spillback이 High를 base +161 → +78로 절반 개선(단독 기준).

## Round 13 (진행중): ★공정 지평 심화 = 옵션 B (사용자 승인)
- 동기: H3엔 Inc 구별정보가 물리적으로 없음(위 실증). 목적함수로는 못 넘음.
- **공정성 확보**: `HORIZON=k` env가 `cfg.mpc.horizon_steps` 전역 설정 → PFO(WuFaithfulFollower)·
  P-Stack·P-CENT **모두 동일 지평**. "리더만 깊게"(LEADER_V_DEPTH, 사용자 금지)와 근본적으로 다름.
  leader_value_depth=0 불변 유지.
- R13: H=6(1080s) × {PFO, P-Stack+spillback} × {Inc, High, Med}.
- **핵심 질문**: 같은 만큼 깊어지면 계층이 분산보다 더 얻는가? PSgain > PFOgain 이면
  **"조정의 가치는 lookahead가 있어야 발현"** 논문 스토리 성립(H3 미승보다 강한 기여 —
  계층 제어가 언제 유효한지 조건 규명).
- 계산비용: P-Stack H6 = 33s/step (H3 31s와 거의 동일, early-stop pruning) → H9/H12도 현실적.

## ★★R13 공정 지평 심화(옵션 B) 결과 — 가설 반증
같은 H에서 PFO vs P-Stack(spillback). 음수=계층 승.
| cell | H3 | H4 | H6 | H9(PFO만) | H12(PFO만) |
|---|---|---|---|---|---|
| Med PFO/PS | 3862/**3781**✓ | 3840/**3762**✓ | 3825/**3791**✓ | 3803 | 3792 |
| Inc PFO/PS | 5497/5752(+255) | 5501/5918(+417) | 5513/5890(+377) | 5527 | 5515 |
| High PFO/PS | 5970/6048(+78) | 5935/6081(+146) | 5877/6199(+322) | **8691** | **8859** |

**깊이 이득(H3 대비, 양수=개선)**
| cell | PFO H3→4 | H3→6 | PS H3→4 | H3→6 |
|---|---|---|---|---|
| Med | +22 | +38 | +19 | **−10** |
| Inc | −4 | −16 | **−166** | **−138** |
| High | +35 | +93 | **−33** | **−151** |

→ **공정하게 깊게 하면 PFO가 이득, P-Stack이 손해 → 격차 확대**(High +78→+146→+322).
   "조정 가치는 lookahead 필요" 가설 **반증**. 계층은 모든 지평에서 Med 승·Inc/High 패(패턴 일관).

### 부수 발견: PFO도 H9/H12 High서 파국(5877→8691→8859)
검증: step32부터 발산(끝단 예보 아티팩트 아님). 원인=H9 PFO가 metering 더 조임(3750 vs H6 4650)
→ urban 축적(1070 vs 898) 캐스케이드. **분산 제어서 지평↑ → 각 에이전트가 자기구간 더 보호 →
외부효과 증폭**(내부화 주체 없음). "조정 없는 lookahead는 해롭다".

### 교란요인 검증중(대조군 실행)
spillback의 lead_h=0.5h·nref_u=800은 **H3 말단 기준 calibration** → H6 말단(1080s)선 과투영 가능.
"깊이가 리더에 해롭다" vs "spillback이 H6서 miscalibrated" 분리 위해 **fh_psbase_H6_*(spillback 없는
base@H6)** 실행. 또 held-plan rollout 오차 누적 가능성(기존 메모리 관측)도 후보.
적대검증 워크플로우 wf_042bb540-35c 병행(주장 C1~C6 원자료 독립검증·대안설명·버그탐색).

## ★★★2026-07-26 레버 전환: terminal cost → 가격 채널 (GPT 접근 참고)
**전환 근거(데이터)**: Inc에서 리더 N_UF가 PFO incumbent와 다른 스텝 = **5/80(6%)**뿐인데 +255~328 짐.
가격 채널은 전부 활성(meter |max|=1500, VSL 115, offset 1.0). → **손실은 예산이 아니라 가격 채널로 들어옴.**
이번 세션에 만든 far/CLF/spillback/감독자는 전부 "예산 후보 랭킹"만 바꿔서 여지가 없었음(bit-identical의 진짜 이유).

**채널별 토글 구현+훅 검증**(run_claude L295~): METER_PRICE=0 / VSL_PRICE=0 / METER_PRICE_W.
- `METER_PRICE=0` → meter 가격 컬럼 소멸 + 물리 135컬럼 변화 ✓
- `VSL_PRICE=0` → vsl 컬럼 소멸 + 물리 33컬럼 변화(green 가격까지 연동) ✓
- **`METER_PRICE_W`는 불발**(물리 bit-identical, 타이밍 2컬럼만) — 선형항이라 argmin 불변(nref와 같은 포화).
- 참고: GPT가 겪은 "weight=0인데 trust/cert 살아있음" 함정은 이 레포엔 없음
  (stackelberg_wu_metered.py:1096-1098이 채널 gate 시 price+metering_release_certified 동시 제거).

### ★R14 돌파: GREEN_TRUST_SEC=1.5가 Incident를 +328 → +44
| Inc | total | fw/ur | vsPFO |
|---|---|---|---|
| **gt15(GREEN_TRUST_SEC=1.5)** | **5541** | 2673/**2868** | **+44** |
| both(METER+VSL price off) | 5644 | 2576/3068 | +147 |
| mtd60(METER_PRICE_DELTA=60) | 5656 | 3484/2173 | +159 |
| base | 5826 | 2584/3242 | +328 |
→ gt15가 urban 3242→2868·fw 2584→2673으로 **P-CENT 균형(2874/2625) 방향**으로 이동.

| High | total | vsPFO |
|---|---|---|
| **both** | **6081** | **+112** |
| base | 6131 | +161 |
| **gt15** | 6262 | **+292(악화)** |
→ **GPT 보고 패턴 재현: Inc/저부하는 작은 green authority, High는 큰 authority.**
   단일 고정 authority로는 둘을 동시에 만족 못 함 → 수요/상태 기반 adaptive gate 필요(깊이 불변=공정).

## 현재 스코어보드 (best, vs PFO)
- Low ~+5(동률) · Med 승(저w_u 완전보존) · Skew 승(-27) · **High +32(거의 동률)** · **Inc +255(포화, 유일 확실한 패)**.
- Inc가 마지막 난관(PFO=near-oracle 5497≈PCENT 5498). whipsaw 억제로 돌파 시도 중.

## 진행/미결
- [진행중] 워크플로우 Phase3-5: 위 지침에 재조준한 4개 공정 수정안 설계 → 적대검증 → 랭킹·구현스펙.
- [다음] 종합 스펙대로 구현 → 5셀 실행 → PFO 5셀 전부 이기는지 판정 → flagship 재실행 → 메모리 갱신.
- **핵심 방향 확정**: freeway 재가중(사망)이 아니라 **urban 배출-flow 가격화 + far_urban 탈합산 +
  always-on(freeway-gate 비의존)**. depth는 절대 불변(공정).
