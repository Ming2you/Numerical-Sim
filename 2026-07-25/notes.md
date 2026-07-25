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

## 진행/미결
- [진행중] 워크플로우 Phase3-5: 위 지침에 재조준한 4개 공정 수정안 설계 → 적대검증 → 랭킹·구현스펙.
- [다음] 종합 스펙대로 구현 → 5셀 실행 → PFO 5셀 전부 이기는지 판정 → flagship 재실행 → 메모리 갱신.
- **핵심 방향 확정**: freeway 재가중(사망)이 아니라 **urban 배출-flow 가격화 + far_urban 탈합산 +
  always-on(freeway-gate 비의존)**. depth는 절대 불변(공정).
