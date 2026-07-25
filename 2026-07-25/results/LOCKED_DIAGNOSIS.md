# 잠긴 진단 (워크플로우 Phase2 종합, 2026-07-25)

All four lenses verified against raw CSV. The far-active proxy (best_obj−rollout>1) is nonzero at all steps 5-70 in both cells, so I cannot corroborate a narrow far-gate window from CSV alone and won't claim one. I have everything needed to lock the mechanism.

---

# 확정 메커니즘 종합 (원자료 CSV 재검증 완료)

네 렌즈는 **결과층**(PS4 freeway 과보호·경계 과-holding·urban linger)에는 모두 일치하나 **원인 귀속**이 갈렸다. 원자료로 재확인해 다음과 같이 판정한다.

## 1) 확정 메커니즘 — 왜 PS4가 지는가

PS4는 **시간적으로 분리된 두 실패**로 지며, 둘 다 하나의 구조적 뿌리(리더의 지평 내 유효 레버가 freeway/경계에만 닿고, 그 레버가 미루는 urban 비용이 3-스텝 rollout에도 far/urban 터미널 항에도 안 보임)로 환원된다. **(A) 온셋**: 사고 순간(Inc st25) 리더가 freeway 예산 N_UF를 5700→2400으로 슬램(metering 2400, 동시각 PFO 5792·PCENT 4706)해 **3-스텝 rollout 안에서 값싼 freeway 완화**를 얻지만, held 차량을 경계큐로 쏟아 bndQ가 50→286(st33)로 폭발하고 경계 적분이 PS4 18,646 vs PFO 3,400으로 최대가 된다. 이 슬램이 씨 뿌린 urban 캐스케이드의 정점은 step42–43로 결정 시점(st25)보다 **17스텝(~3,000s) 뒤 = 540s 지평 밖**이라 rollout이 원천적으로 못 본다. **(B) 회복**: 오라클이 실제로 이기는 행동은 **회복기 도심 green 서비스 확대**(PCENT green_p1 60–70 vs PS4 45–56)이며, 같은 urban 부하에서 step50 배출이 PS4 575→PCENT 987(Inc, +72%)·PS4 528→PCENT 975(High, +85%)로 격차가 난다. 브리핑이 "metering throughput 후퇴(리더 선택)"로 본 것은 **하류 결과**다 — 회복기 metering setpoint는 PS4≈PCENT로 사실상 동일(Inc 5887 vs 5790, shortfall~0)이고, PS4는 도심이 안 빠져 **램프로 내보낼 차 자체가 적을 뿐**이다. 두 실패를 리더에게 안 보이게 만드는 **구조적 뿌리**: far_urban이 경계큐와 protected 저수지를 하나의 n_u로 합쳐 단일 g_eff로 배수(code L128, L155-156)하므로 경계에 붙잡아 두기가 자유류 도심만큼 값싸 보이고, freeway 예산 N_UF는 도심 저수지에 지렛대가 없으며(R3에서 N_UF@25를 5400으로 올려도 rampQ 179→31일 뿐 urban 421→425 불변), urban 가격이 **배출 flow가 아닌 축적 stock(n²/2g)**에 걸려 있다. **far 재가중은 이미 sweep됐고 이를 확증한다** — Incident에선 freeway↔urban 트레이드를 부분 유도(+328→+150)하나 여전히 PFO에 지고, High에선 freeway가 이미 바닥(2584)이라 **무력(+162→+160)**하다. 즉 목적 가중이 순진한 의미로 틀린 게 아니다(근시 rollout이 이미 urban을 freeway보다 무겁게 봄, ur/fw=1.23/1.91; far는 목적의 60%). **결함은 터미널 항이 틀린 urban 물리량(합산된 stock)을 가격화하고, 리더의 지평 내 유효 레버가 freeway/경계에만 닿는다는 것**이다.

## 2) 리더가 P-CENT처럼 행동하려면 — 목적/가격 설계 지침 (깊이 불변)

1. **far_urban 탈-합산(4렌즈 만장일치).** protected 저수지와 boundary 큐를 **서로 다른 배수율의 별도 항**으로 분리한다. `far_urban = protected_excess²·tc/(2·g_prot) + boundary_excess²·tc/(2·g_bnd)`. protected는 느린 MFD 생산율, boundary는 metering 처리율로 배수하되 **boundary 항의 터미널 비용을 그것을 비우는 데 필요한 metering throughput에 연동**해, metering 슬램이 남긴 미배수 경계차를 "즉시 배수 가능"이 아니라 **그것이 유발할 하류 urban TTT로 과금**한다. 이러면 온셋 N_UF 슬램(st25 2400)이 값비싸진다.

2. **urban 쪽에 stock 벌점이 아닌 배출-flow(서비스율) 보상을 추가.** stock 가격(n²/2g)은 "안 들여보내기(metering/gating)"와 "내보내기(green)"를 동일하게 만족시켜 리더가 freeway-값싼 전자를 고른다. **urban 배출율(=green-split 서비스 throughput)을 직접 가격화**하면 오라클이 쓰는 "내보내기"가 터미널 비용을 낮추는 더 싼 길이 되어 리더가 회복기 green 확대로 정렬된다.

3. **레버↔가격 정합.** N_UF는 도심 저수지를 못 뺀다(R3 실증). 따라서 urban 가격은 **실제로 urban을 움직이는 레버(N_P·green-split 가격)에 붙이고**, N_UF/metering 레버엔 한계 boundary-holding 가격(=그 shortfall이 유발하는 하류 urban TTT)을 걸어라.

4. **지평 밖 지연 비용의 선반영(깊이 아님, 터미널 항 shaping).** urban 정점이 결정보다 17스텝 뒤이므로, 터미널 항이 **경계큐 증가율과 urban state**에 연동된 leading 성분을 갖게 해 freeway capdrop뿐 아니라 **경계큐가 쌓이는 국면에서 리더의 확장 시력이 켜지게** 한다.

## 3) 반드시 피할 함정

- **R3 boundary-dump 함정 (재발 금지).** protected+boundary를 단일 n_u/g_eff로 합쳐 **합만 벌점화하지 마라.** R3 CLF가 정확히 이걸 했고, 190서 pour 서명(dSUM +0.04, urban +1.94, TTT +6.8 악화)·Inc서 무개선(Δ−7.3)을 냈다. 합산은 리더가 실제 배출 대신 저수지 간 이동(또는 유입 gating)으로 벌점을 회피하게 한다.
- **n_ref ≈ 운영점 함정.** R3는 n_ref=450인데 운영점 n_u≈470이라 볼록 기울기(∝excess)가 ~0으로 붕괴해 urban 벌점이 죽고 리더가 far_fw를 N_UF로 쫓았다. 볼록 CLF의 기준/임계는 운영점보다 확실히 아래(또는 운영점에서 steep한 한계)여야 한다.
- **순수 재가중 함정.** w_urban↑/w_fw↓ 단독으로 고쳐질 거라 기대 마라 — 이미 sweep됐고 Inc 부분·High 무력이다. freeway는 이미 바닥(2584)이고, urban 권한이 없는 레버를 구동하는 flat stock 기울기를 스케일해도 트레이드를 명령 못 한다.
- **stock-vs-flow 함정.** urban stock 가격은 inflow-gating(freeway-값쌈)을 outflow-boosting과 동일 취급 → 오라클의 green 행동을 선택시키려면 배출 flow를 가격화/보상해야 한다.
- **온셋 N_UF 슬램.** capdrop 감지 시 freeway 예산을 경계/urban 외부성 과금 없이 크래시(5700→2400)시키지 마라 — 이 단일-스텝 슬램이 경계 백로그 전체의 씨앗이다.

## 검증 수치 (windowed TTT, warm5–14400; 재현 경로 outputs/_diag/{pstack4,pfosplit,pcent,redesign_G}_{170inc,190})
| 셀 | PFO | PS4 | G(R3) | PCENT |
|---|---|---|---|---|
| Inc tot | 5497.3 | 5825.7 | 5818.4 | 5498.4 |
| Inc fw/ur | 3994.5/1502.8 | **2584.0**/3241.8 | 2595.5/3222.9 | 2873.7/2624.8 |
| High tot | 5969.6 | 6131.1 | 6137.9 | 5598.8 |
| High fw/ur | 2621.8/3347.7 | **2584.3**/3546.8 | 2584.7/3553.2 | 2767.7/2831.0 |

핵심 이벤트: 온셋 Inc st25 N_UF 5700→2400(meter 2400) vs PFO 5792/PCENT 4706 · 경계적분 PS4 18,646/23,003(양 셀 최대) · 회복 등부하배출 step50 Inc 575→987/High 528→975 · far/rollout 1.66/1.43(far=목적 62.4%/58.8%), 근시 ur/fw 1.18~1.91 · R3 N_UF@25 5400서 rampQ 179→31·urban 421→425 불변 · far-재가중 sweep 최선 Inc +150(패)/High +160(무력).

## 미해결·주의 (CSV로 확정 불가, 정직 보고)
- **far_fw vs far_urban 터미널 절대크기**는 집계 CSV로 확정 불가(far가 평가되는 held-plan 말단 상태 미로깅). 방향(far=목적 60%·리더 freeway 보호)은 확실하나 말단 fw/urban far 우열은 CSV로 못 가린다(렌즈3과 동일 판정).
- **정확한 FAR_GATE on/off 스텝창**(렌즈3의 stderr "[FAR_GATE m3]" 근거)은 CSV-only 지침상 미개봉. CSV 프록시(best_obj−rollout)는 양 셀 step5–70 전부 >0이라 좁은 게이트창을 CSV로 corroborate 못 하며, 좁은 창을 주장하지 않는다.
- 브리핑 per-step "urbΔ" 컬럼(120/371/532/650/457)은 urban_accumulation_veh·step_urban_ttt 어느 것과도 절대값 불일치(렌즈1 지적 확인). 질적 서사(st25 PS4≈PFO 후 발산)는 유지되나 그 컬럼의 정확한 출처는 미확인.