# 결과 절 초안 v2 — 그림·캡션·본문 (현재 데이터 한정)

> 작성일 2026-07-18. 동결 프레임 = `ANALYSIS_PLAN_FINAL.md`(§0~§5), 수치 출처 =
> `analysis/tables/t1_macro_full.md`(2026-07-18 확정 런)과 `2026-07-17/notes.md`(측정 사실).
> 그림 파일은 전부 `analysis/figures/`에 실존하는 것만 인용한다. 본문은 국문, 캡션은 영문.
> §4는 런 미도착으로 구조만 배치한다.
> v2(2026-07-18) — 사용자 결정 5건 반영: ① 고수요 본선 셀 = 190_w(200_w는 §5 전용 보조),
> ② P-CENT = 의도적 rate-limit-free 상한 프레이밍, ③ 하드웨어·솔버 명세 확정,
> ④ 표 1b/1c(urban/freeway 분해 + N_end) 추가, ⑤ ramp 큐 그림 기준선 = 저장 한계 180 veh.

---

## §0. 실험 설정 (Experimental Setup)

### §0.1 채점 규약

모든 성능 수치는 windowed total travel time(wTTT)으로 보고한다. 시뮬레이션 총 길이는
T_total = 10,800 s(제어 주기 180 s × 60스텝)이고, 최초 20스텝(WARM = 20)은 전 구성이
무제어(NC)로 공유하는 웜업 구간이다. wTTT는 웜업 이후의 누적 총 통행시간으로 정의한다.

> wTTT = TTT_cum(t = T_total) − TTT_cum(step = 20)  [veh·h]

본문 표의 개선율 규약은 NC 대비 백분율이다.

> 개선%(NC) = (J_NC − J_ctrl) / J_NC × 100

제안 계열 내부 비교(§2·§3·§5)에서는 PFO 대비 백분율을 병용하며, 사용하는 곳마다 분모를
명기한다. wTTT에는 on-ramp 대기 차량의 통행시간이 포함된다 — 즉 차량을 램프에 세워 두는
것으로는 wTTT를 낮출 수 없다(§2c 각주 참조). Delay 계열 지표는 free-flow reference 런이
시나리오별로 확보된 뒤 추가한다 [런 대기].

시뮬레이터와 전 컨트롤러는 결정적(deterministic)이며 모든 수치는 단일 실행에서 얻었다.
따라서 시드 반복·유의성 검정 대신 5개 시나리오에 걸친 방향 일관성으로 강건성을 평가하고,
개별 셀 수치는 시나리오별 사례 연구로 해석한다. 결정론 매크로 제어 문헌(Wu 2022; Hegyi
2005; Van den Berg 2007)의 보고 관례와 동일하다. 아울러 본 연구의 예측 모델은 플랜트와
동일하다(model–plant match). 이 두 선언의 함의와 한계는 §5에서 논한다.

### §0.2 시나리오

논문 본문 시나리오는 5개 — sweet_155_w(저수요), sweet_170_w(중수요·freeway 병목),
sweet_170_skew15_w(urban 경계 불균형), sweet_170_incident_w(본선 폐색·용량 강하),
sweet_190_w(고전달·복합 스트레스) — 이며, 190_w는 메커니즘 절(§2·§3)의 대표 해부 셀을
겸한다. sweet_200_w(극단 부하)는 §5 한계 서사 전용의 보조 행으로 표에 유지한다.

- **그림 0a — 네트워크 스키매틱**: `analysis/figures/f0_network_schematic.pdf` —
  2×3 그리드(신호 A–D,F / 비제어 E / 경계 게이트 7쌍) + 8-seg × 2링크 freeway,
  다이아몬드 IC(D·F: off-ramp seg 2/4 → 60-veh urban 저장, on-ramp 합류 seg 3/5,
  용량 1,500 veh/h, 큐 ≤ 180 veh), **21-player 소유권 오버레이**(urban 신호 5 +
  세그먼트별 freeway 16; 합류 seg 소유자가 metering, seg 0이 origin 큐 소유.
  코드 플래그명 SEG13은 4-seg 시절 레거시).
- **표 0a·그림 0b — 수요·사고 명세**: `analysis/tables/t0_demand_scenarios.md`,
  `analysis/figures/f0_demand_profile.pdf` — 전 셀 공통 사다리꼴(base 0.5, 65–125분
  plateau), 클래스 배율 1.55/1.70/1.90/2.00, skew15는 서:동 = 1.5:1 부피보존.
  **사고 명세**: FW_E seg 6, 차로 폐쇄 2→1(lane_loss 1.0), 4,500–6,300 s(75–105분,
  plateau 내 30분).
- **표 0b·0c — 파라미터**: `analysis/tables/t0_params_model.md`(플랜트 — 시간 격자·
  METANET·capacity-drop·ramp·urban, state.py/default.yaml 줄 병기),
  `analysis/tables/t0_params_controller.md`(P-Stack 전체 스펙 — horizon 3 +
  value_depth 3 = rollout 6스텝(18분), 이동 한계 meter ±300 / VSL ±10 / green ±6 —
  및 기준선 5행).
- **튜닝·공정성·Wu 충실도**: `analysis/setup/fairness_tuning.md` — 10셀 A/B 사다리
  공개(R=300 = 가격 FD 측정폭, VSL ±10 = 격자 간격, 기각 8팔), **정직성 조항**
  (평가 셀 = 개발 셀, held-out 부재), PFO 재현 게이트 Δ<0.6(6/6), P-CENT 상한
  프레이밍(structured grid 직렬 — SLSQP 아님), Wu 2022 충실도 6행 매트릭스
  (SUMO 플랜트 vs 모델=플랜트 등 편차 명시).

### §0.3 비교 컨트롤러 — 각 기준선이 격리하는 격차

베이스라인마다 "어떤 격차를 격리하는 도구인지"를 선언한다(권한/조정 분해는 Hegyi et al.
2005의 등화 실험 계보를 따른다).

| 컨트롤러 | 격리하는 격차 |
|---|---|
| NC | 무제어 참조 — 모든 개선율의 분모 |
| WU-CD-F | 문헌(Wu 2022) 재현 분산 제어 — **권한 격차**의 하한. NC↔WU-CD-F 간극 = 문헌 권한 집합으로 얻는 가치, WU-CD-F↔PFO 간극 = 권한 확장(특히 ramp metering 소유권)의 가치 |
| PFO | 제안 팔로워 단독(리더 없음, 이동 무제한) — **조정 격차**의 분리. PFO↔P-Stack 간극 = 리더 조정의 가치 |
| PFO+box | PFO에 제안과 동일한 이동 한계(meter ±300 / VSL ±10 / green ±6) 부과 — **공정 액추에이터 기준선**. 동일 이동 한계 하에서 조정의 가치를 격리 |
| P-CENT | 중앙집중·이동 한계 무적용(rate-limit-free) 컨트롤러 — 무제약 이동의 **성능 상한(upper bound)**을 재는 도구. 이동 한계는 의도적으로 적용하지 않는다 |
| P-Stack | 제안 계층(Stackelberg) 컨트롤러, walk-MVG 구성 |

**[검토 필요 — §0]**
1. [TODO-P1] 4건의 삽입 순서와 본문/부록 배분.
2. 사고 시나리오 수치 명세(A5)를 수요 표에 통합할지 별도 문단으로 둘지.
3. 결정론·model-plant match 선언의 §0 배치 위치(채점 규약 뒤 vs 절 서두).

---

## §1. 거시 성능 (Macroscopic Performance)

### 표 1 — 5컨트롤러 × 6셀 wTTT [veh·h] (괄호 안 = NC 대비 개선%)

| 셀 | NC | WU-CD-F | PFO | PFO+box | P-CENT | P-Stack(제안) |
|---|---|---|---|---|---|---|
| sweet_155_w | 8,977 | 6,427 (+28.4) | 1,776 (+80.2) | 1,689 (+81.2) | 1,614 (+82.0) | 1,685 (+81.2) |
| sweet_170_w | 13,028 | 8,754 (+32.8) | 3,021 (+76.8) | 7,967 (+38.8) | 2,488 (+80.9) | 2,684 (+79.4) |
| sweet_170_skew15_w | 13,175 | 12,183 (+7.5) | 2,957 (+77.6) | 2,838 (+78.5) | 2,517 (+80.9) | 2,667 (+79.8) |
| sweet_170_incident_w | 9,581 | 9,111 (+4.9) | 2,367 (+75.3) | 7,413 (+22.6) | 2,354 (+75.4) | 2,295 (+76.0) |
| sweet_190_w | 16,518 | 16,277 (+1.5) | 5,689 (+65.6) | 5,491 (+66.8) | 4,705 (+71.5) | 5,156 (+68.8) |
| sweet_200_w *(보조)* | 18,115 | 17,955 (+0.9) | 7,195 (+60.3) | 17,474 (+3.5) | 7,480 (+58.7) | 8,684 (+52.1) |

표 각주 — ① 개선% = (J_NC − J_ctrl)/J_NC × 100, wTTT는 §0.1 정의(WARM = 20 이후 창).
190_w까지의 5개 행이 본선 시나리오이고 200_w는 §5 한계 서사 전용 보조 행이다.
② 이동 한계 준수 여부: P-Stack과 PFO+box는 meter ±300 / VSL ±10 / green ±6을 준수.
PFO는 무제한(실측 per-step 최대 meter 1,125 / green 57 s). P-CENT는 상한(upper bound)
도구로서 의도적 미적용(실측 meter 628 / VSL 30 / green 41). WU-CD-F(문헌 재현)도
미적용(VSL 50 / green 36). ③ wTTT에는 on-ramp 대기 통행시간이 포함된다. ④ delay 열은
free-flow reference 확보 후 추가 [런 대기].

### 표 1b — wTTT의 urban/freeway 분해 [veh·h] (표기 = urban / freeway)

| 셀 | NC | WU-CD-F | PFO | PFO+box | P-CENT | P-Stack(제안) |
|---|---|---|---|---|---|---|
| sweet_155_w | 4,106 / 4,872 | 3,411 / 3,016 | 884 / 891 | 844 / 845 | 885 / 728 | 952 / 733 |
| sweet_170_w | 6,545 / 6,483 | 5,205 / 3,549 | 1,925 / 1,096 | 4,616 / 3,351 | 1,275 / 1,213 | 1,559 / 1,125 |
| sweet_170_skew15_w | 6,689 / 6,486 | 6,192 / 5,990 | 1,895 / 1,062 | 1,751 / 1,087 | 1,397 / 1,121 | 1,515 / 1,152 |
| sweet_170_incident_w | 4,764 / 4,817 | 4,555 / 4,556 | 1,363 / 1,004 | 4,168 / 3,245 | 1,395 / 959 | 1,323 / 972 |
| sweet_190_w | 8,779 / 7,739 | 8,608 / 7,670 | 4,405 / 1,284 | 4,137 / 1,354 | 3,273 / 1,432 | 3,745 / 1,411 |
| sweet_200_w *(보조)* | 9,845 / 8,269 | 9,693 / 8,262 | 5,781 / 1,415 | 9,720 / 7,754 | 5,420 / 2,060 | 6,373 / 2,311 |

### 표 1c — 종단 잔존 차량 N_end [veh] (보조행)

| 셀 | NC | WU-CD-F | PFO | PFO+box | P-CENT | P-Stack(제안) |
|---|---|---|---|---|---|---|
| sweet_155_w | 7,950 | 5,502 | 264 | 264 | 262 | 286 |
| sweet_170_w | 10,859 | 7,187 | 277 | 6,262 | 262 | 278 |
| sweet_170_skew15_w | 10,962 | 10,301 | 284 | 272 | 263 | 281 |
| sweet_170_incident_w | 8,332 | 8,006 | 267 | 6,011 | 262 | 281 |
| sweet_190_w | 13,342 | 13,280 | 1,496 | 1,243 | 606 | 1,107 |
| sweet_200_w *(보조)* | 14,556 | 14,579 | 2,740 | 14,182 | 5,056 | 6,532 |

표 1c 각주 — N_end = 마지막 180 s 스텝의 TTT 증분 × 20 = 종단 시점 망 내 차량 수(각
스텝의 TTT 증분은 N/20 veh·h이므로). 이 보조행은 큐를 채점창 밖으로 미뤄 wTTT를 낮추는
회계가 없는지 검사한다.

**분해와 종단 회계.** NC는 창 종료 시점에 7,950~14,556대가 망 내에 잔존하는(미배수)
반면, 제어군은 저·중부하 셀에서 약 260~290대 수준으로 배수를 완료한다 — 표 1의 개선이
큐를 창 밖으로 미룬 결과가 아님을 보이는 회계다. 190_w에서 잔존은 P-CENT 606 <
P-Stack 1,107 < PFO 1,496대의 순서로 wTTT 순위와 일치한다. 분해를 보면 P-Stack은
190_w에서 urban TTT를 PFO 대비 4,405 → 3,745 veh·h로 크게 줄이는 대신 freeway에
1,284 → 1,411 veh·h의 소폭 비용을 지불한다 — 총량이 양수(5,689 → 5,156)인 트레이드
오프의 증거다. 보조 셀 200_w에서는 P-Stack 잔존 6,532대가 PFO 2,740대를 상회하며, 같은
셀의 TTT 열세와 정합하는 정직한 회계로서 §5에서 부검한다.

**Fig. 1 — `f_ttt_traj_sweet_170_w.png`** (대표 셀; 나머지 5셀은
`f_ttt_traj_sweet_155_w.png`, `f_ttt_traj_sweet_170_skew15_w.png`,
`f_ttt_traj_sweet_170_incident_w.png`, `f_ttt_traj_sweet_190_w.png`,
`f_ttt_traj_sweet_200_w.png` — 보조 자료 후보)

> **Caption.** Cumulative total travel time over the scoring window for scenario
> sweet_170_w. Black curves denote reference controllers and colored curves the proposed
> hierarchy, following the black-reference/colored-proposal convention used throughout.
> The controllers separate shortly after control activation, and the terminal offsets
> correspond to the wTTT entries of Table 1 (improvement computed as
> (J_NC − J_ctrl)/J_NC × 100).

### 본문 서술

**권한 격차.** WU-CD-F는 문헌의 권한 집합을 재현한 분산 제어로, 저·중수요에서는 NC 대비
2,550 veh·h(+28.4%)와 4,274 veh·h(+32.8%)를 회수하지만, 사고·고수요 셀에서는 NC에
근접한다 — 170_incident +4.9%, 190_w +1.5%, 200_w +0.9%이며 경계 불균형 셀에서도
+7.5%에 그친다. 같은 셀에서 PFO 계열이 +60~81%를 회수하는 것과 대비하면, 이 간극의
대부분은 조정 방식이 아니라 권한 집합 — 특히 ramp metering의 소유 — 에서 나온다.
즉 WU-CD-F와 PFO의 비교는 권한 격차를, PFO와 P-Stack의 비교는 조정 격차를 각각 격리한다.

**조정 격차 (P-Stack vs PFO).** 이동 무제한 PFO 대비 P-Stack은 155_w에서 91 veh·h(+5.1%),
170_w에서 337 veh·h(+11.1%), 170_skew15_w에서 290 veh·h(+9.8%), 170_incident_w에서
72 veh·h(+3.0%), 190_w에서 533 veh·h(+9.4%)를 추가로 회수해 본선 다섯 셀 전부에서
이긴다(분모 = PFO). 반면 보조 극단 셀 200_w에서는 P-Stack 8,684가 PFO 7,195 대비
1,489 veh·h(−20.7%) 열위이며, 이 셀은 침묵하지 않고 §5에서 rate-limit 물리로 부검한다 —
어디서 이기고 어디서 지는지를 함께 그리는 것이 이 표의 목적이다.

**공정 액추에이터 관점 (PFO+box).** PFO에 제안과 동일한 이동 한계를 부과하면 본선 두
셀 — 170_w 7,967(PFO의 2.6배), 170_incident_w 7,413(3.1배) — 과 보조 셀 200_w
(17,474, 2.4배)가 붕괴한다.
같은 한계 아래에서 P-Stack은 여섯 셀 모두 정상 동작하며, PFO+box 대비 개선율 평균은
+33.0%에 이르고 200_w는 −20.7%의 급소에서 +50.3%의 승리 셀로 반전된다(분모 = PFO+box).
무제한 PFO가 스텝당 최대 1,125 veh/h의 이동으로 문제를 풀던 컨트롤러였음을 감안하면,
동일한 액추에이터 물리가 강제될 때 리더 조정의 가치가 가장 크게 드러난다 — 단, 이는
동일 이동 한계라는 조건 하의 결론이다.

**중앙 상한 (P-CENT).** P-CENT는 중앙집중·이동 한계 무적용 구성으로 성능 상한(upper
bound)을 재는 도구다 — 이길 수 없는 대상은 상한으로 명명하는 보고 관례를 따른다. 본선
5셀 중 4셀(155_w, 170_w, 170_skew15_w, 190_w)에서 전 컨트롤러 최저 wTTT를 기록하며,
P-Stack과의 격차는 NC 대비 개선율 기준 0.8~2.7%p에 그친다. 170_incident_w에서는 이동
한계를 지키는 P-Stack(2,295)이 상한 참조(2,354)를 0.6%p 근소 상회하고, 보조 셀
200_w에서는 PFO(7,195)가 최저다(6.6%p, §5 부검 대상). 즉 제안은 본선 전역에서 무제약
중앙 상한에 등가에 가까운 성능을 이동 한계 준수 하에 달성하며, "중앙을 상회한다"는
주장은 하지 않는다. 계산 면에서는 본 데이터에서 P-CENT(평균 44.1 s/step)가 P-Stack
(평균 69.1 s/step)보다 오히려 짧아, "계산을 아끼면서 중앙에 근접"이라는 통상 서사는
현재 수치로 지지되지 않음을 함께 기록한다.

**계산 시간.** 채점창 기준 per-step 계산 시간(동일 머신, 20런 병렬 조건)은 다음과 같다.

| [s/step] | WU-CD-F | PFO | PFO+box | P-CENT | P-Stack |
|---|---|---|---|---|---|
| 평균 | 15.9 | 4.6 | 2.8 | 44.1 | 69.1 |
| 최대 | 34.5 | 5.0 | 3.5 | 96.6 | 132.4(20런 병렬 부하 조건) | 팔 간 병렬 부하가 달라(6~20런) 배치 수치는 상한으로만 읽어야 하며, 단독 동일 조건 재측정(190_w)에서는 P-CENT 40.4 s/step vs P-Stack 45.7 s/step로  근사 동급이다(P-CENT 솔버 = coarse→fine structured grid 직렬 — scipy 부재로 SLSQP 미가동, 런 진단 serial=1.0 확정) — 두 값 모두 제어주기 180 s를 큰 여유로 하회한다.

실시간성 판정은 최대값으로 건다 — 전 컨트롤러의 최악 스텝(132.4 s, P-Stack)이 제어 주기
180 s를 하회하므로, 관측된 전 구성이 실시간 제약 안에 있다. 전 실험은 12th Gen Intel
Core i7-12700K(물리 12 / 논리 20코어), 16 GB RAM, Windows 11, Python 3.12.13에서
수행했다. 최적화는 전부 순수 Python으로 구현한 자체 coordinate-descent/격자 탐색이며
외부 LP/QP 솔버는 사용하지 않는다. 팔로워 Jacobi 합의는 최대 5 sweep, 리더는 정제 후보
최대 25개(격자 최대 49)를 평가하고, N_P primal–dual 루프는 K = 4 반복으로 상한을 둔다.
표의 계산 시간은 동일 머신에서 20런 병렬 조건으로 측정한 벽시계(wall-clock) 값이므로,
같은 조건의 런끼리만 비교 가능하다.

**[검토 필요 — §1]**
1. delay 열 — free-flow reference 런 도착 후 일괄 갱신.
2. Fig. 1의 곡선 구성(NC/WU-CD-F/P-CENT/P-Stack 4곡선 vs 6컨트롤러 전부) 확정.

---

## §2. 메커니즘 (Mechanism)

이 절은 대표 셀 sweet_190_w(고전달·복합 스트레스)의 단일 런을 해부해, §1의 스칼라 격차가
어떤 액추에이터 거동에서 나오는지를 시점 정렬 서사로 보인다. 비교 팔은 pd4_ref(박스 이전
구성, 진동 원인 상태)이며, 회복 서사(e)만 sweet_200_w를 사용한다 — 후자는 §5의 한계
서사와 소재를 공유한다. 인과 서술은 조작·측정된 채널에만 사용하고, 미측정 정합은
"~와 정합한다"로 구분한다.

### (a) 임계 밀도선 운영

**Fig. 2a — `f_rho_FW_E_sweet_190_w.png`** (서향 대응 그림 `f_rho_FW_W_sweet_190_w.png`)

> **Caption.** Density of the eastbound freeway bottleneck under the proposed controller
> (colored) and the pd4 reference (black) for scenario sweet_190_w; the horizontal dashed
> line marks the critical density ρ_crit = 33.5 veh/km/lane. The proposed controller holds
> the peak density at 32.0 veh/km/lane, just below criticality, whereas the reference
> overshoots to 34.5 veh/km/lane and crosses into the congested regime.

관찰 — 제안 컨트롤러의 병목 밀도 최대값은 32.0 veh/km/lane으로 임계 밀도
ρ_crit = 33.5 veh/km/lane을 넘지 않는 반면, pd4 기준 팔은 34.5까지 상승해 임계선을
넘는다. 해석 — metering이 유입을 임계 접근 시점에 제한한 결과이며(§2b의 명령 시계열과
시점 일치), 임계선 바로 아래에서의 운영은 §2d의 FD 운영점 분포와 정합한다. 임계 초과
1.0 veh/km/lane과 미달 1.5 veh/km/lane의 차이가 §1의 190_w 격차(533 veh·h, PFO 대비
+9.4%)로 이어진다는 서술은 측정된 두 끝(명령과 wTTT)을 잇는 해석이며, 중간 매개의 정량
분해는 Stage 2 이벤트 감사에서 다룬다 [런 대기].

### (b) 평활한 metering vs 풀스팬 진동

**Fig. 2b — `f_meter_R_D_E_190w.png`** (나머지 램프 — `f_meter_R_D_W_190w.png`,
`f_meter_R_F_E_190w.png`, `f_meter_R_F_W_190w.png`)

> **Caption.** Ramp-metering command (zero-order hold) at ramp R_D_E in scenario
> sweet_190_w; black denotes the pd4 reference and color the proposed controller. The
> reference exhibits full-span jumps of up to 1,125 veh/h per step, whereas the proposed
> command moves by at most ±300 veh/h per step under the box constraint. Time axis
> identical to Fig. 2a.

관찰 — 같은 트리거(merge 밀도 상승) 앞에서 pd4 팔은 스텝당 최대 1,125 veh/h의 풀스팬
점프를 반복하고, 제안 컨트롤러는 ±300 veh/h 이내로 이동한다. pd4의 진동은 λ 점프
스텝에 몰리며(해당 스텝 Σ|Δ| = 2,218), 이는 §3에서 진단하는 선형 가격 × 이산 후보의
bang-bang과 정합한다. 해석 — 박스 제약은 명령의 외삽을 제거해 같은 트리거에 침착한
반응을 만들고, 이것이 (a)의 임계선 미달 운영을 가능하게 한다.

### (c) ramp 큐 — 이득의 비용 회계

**Fig. 2c — `f_rampq_R_D_E_190w.png`** (나머지 램프 — `f_rampq_R_D_W_190w.png`,
`f_rampq_R_F_E_190w.png`, `f_rampq_R_F_W_190w.png`)

> **Caption.** On-ramp queue at R_D_E under the proposed controller (colored) and the pd4
> reference (black), scenario sweet_190_w; the horizontal line marks the storage
> constraint (the ramp storage limit, 180 veh). The proposed controller dissolves the queue by about 145 min,
> whereas the reference still carries a residual queue at 178 min, effectively until the
> end of the window. Ramp waiting time is included in the TTT objective, so the gain in
> Table 1 is not obtained by parking vehicles on the ramp.

관찰 — 제안 컨트롤러의 램프 큐는 약 145분에 해소되는 반면 pd4 팔의 큐는 178분까지
잔류해 사실상 창 종료까지 남는다. 각주 — wTTT에는 램프 대기 통행시간이 포함되므로
(§0.1), "차량을 램프에 세워 번 이득"이라는 비판은 정의상 성립하지 않는다. metering
이득의 비용(램프 대기)을 명시적으로 보고하는 것은 HERO 계보의 관례를 따른 것이다.

### (d) FD 운영점

**Fig. 2d — `f_mfd_FW_E_190w.png`** (서향 대응 그림 `f_mfd_FW_W_190w.png`)

> **Caption.** Operating points of the eastbound freeway on the flow–density plane,
> scenario sweet_190_w; the vertical dashed line marks ρ_crit = 33.5 veh/km/lane, black
> points the pd4 reference and colored points the proposed controller. The proposed
> controller confines operation to the uncongested branch, consistent with the density
> trajectory of Fig. 2a.

관찰 — 제안 컨트롤러의 운영점 구름은 비혼잡 가지에 갇혀 있고, 기준 팔은 임계 우측으로
넘어간 점들을 남긴다. 이는 (a)의 시계열 관찰을 상태 평면에서 재확인하는 것으로, 별도의
새 주장을 담지 않는다.

### (e) 회복 서사 — 박스 끝 너머를 보게 하기 (sweet_200_w)

**Fig. 2e-1 — `f_intent_200w.png`**

> **Caption.** Leader metering intent during the recovery phase of sweet_200_w. The
> box-only configuration locks at the box edge (intent 3,190–3,374), while the walk-enabled
> leader recovers the full-release request (5,805–6,000). Modeling multi-step reachability
> inside the leader rollout removes the box-edge myopia.

**Fig. 2e-2 — `f_meter_total_200w.png`**

> **Caption.** Total commanded metering rate in sweet_200_w. The unconstrained anchor
> (black) reaches full release within a single step at the demand turn (≈ step 40), whereas
> the rate-limited configurations approach it at ±300 veh/h per step.

**Fig. 2e-3 — `f_tttgap_200w.png`**

> **Caption.** Cumulative TTT gap relative to the unconstrained anchor in sweet_200_w.
> The gap stays flat until the demand turn and accumulates only afterwards, consistent
> with the rate-limit physics discussed in §5 rather than a scoring artifact.

관찰 — 수요 하강기(≈ step 40) 진입 시 박스 단독 구성의 리더 의도(intent)는 3,190~3,374에
고착되어 전량 방류(6,000)를 요청조차 하지 않는다. 리더 rollout에 다중 스텝 도달을 모델링
(BOX-WALK)하자 의도는 5,805~6,000으로 회복된다 — 조작(rollout 수정)과 반응(intent 회복)이
모두 측정되었으므로, 박스-끝 근시는 채점 맹점이 야기한 것이라고 서술한다. 그러나 TTT
격차는 턴 이후에만 누적되며(Fig. 2e-3), 의도가 회복된 뒤에도 ±300 veh/h의 물리 한계
때문에 앵커의 한 스텝 점프를 5~8스텝에 걸쳐 따라간다. 채점 맹점(교정됨)과 액추에이터
물리 한계(남음)의 분리는 §5에서 비용 회계와 함께 마저 다룬다.

**[검토 필요 — §2]**
1. 대표 램프 선택 — R_D_E 1개 본문 + 3개 보조인지, 4램프 격자 1그림인지.
2. (e)의 §2/§5 배분 — 그림 3장을 §2에 두고 §5는 수치 재인용만 할지, 분할할지.
3. Stage 2 이벤트 감사(counterfactual replay) 도착 후 (a)~(c)의 매개 정량 문장 보강.

---

## §3. 가격 채널 (Price Channels)

이 절은 계층 내부의 조정 신호를 감사한다. 결론을 먼저 요약하면 — 명목상의 dual 가격은
작동하지 않고, 실제 조정은 수량형 수단이 수행하며, 선형 가격과 이산 후보의 조합은
구조적으로 bang-bang을 낳는다. 이 진단이 §2의 박스·walk 처방으로 이어진다.

### (a) λ의 실측 거동 — bang-bang

**Fig. 3a — `f_lambda_190w.png`**

> **Caption.** Committed follower price λ_P over time in scenario sweet_190_w. The price
> alternates between 0 and the cap (10) with no interior value in any of the 400 logged
> steps across cells — the committed price is bang-bang, never interior.

PD가 활성인 구성에서 커밋된 가격 λ_P(`wu_faithful_lambda_P`)는 전 셀 400스텝에서
{0, 10}의 두 값만 가지며 중간값은 0회다. 한 번의 갱신으로 0에서 cap으로 이동한 뒤
"고정점 수렴"으로 종료하는 스텝이 관찰되는데(`np_pd_exit = 2` & λ = cap), 이는 수렴이
아니라 경계 고착이다.

### (b) dual 감사 — 살아 있는 dual 가격은 없다

③ 앵커 구성, sweet_190_w, 웜업 후 40스텝의 비영(非零) 빈도 감사는 다음과 같다.

| 채널 | 비영 빈도 | 판정 |
|---|---|---|
| λ_P (`wu_faithful_lambda_P`) | 0/40 | inert — corrector가 실현-공간 음수 잔차를 max(0,·)로 절단 |
| λ_UF (`leader_lambda_uf_committed`) | 0/40 | inert — 조정 모드 기본값 equality라 갱신 자체가 없음 |
| green marginal price (`wu_b2_price_*`) | 40/40 | 활성 |
| meter marginal price (`wu_b3_meter_price_*`) | 40/40 | 활성 |
| VSL marginal price (`wu_b3_vsl_price_*`) | 24~40/40 | 활성 |
| N_UF hard budget (`wu_seg13_budget_*`) | 17/40 | 활성 |

행동 검증도 일치한다 — λ_P를 끄는 NP_OFF 팔은 앵커와 10/10 bit-identical이다. 따라서
계층을 실제로 조정하는 수단은 dual 가격이 아니라 N_UF hard budget(제거 시 −79%)과
marginal price 두 가지다. Stackelberg dual 기계장치가 통째로 논다는 사실은 §5의 한계
(1)로 정직하게 기재한다.

### (c) 구조 진단 — 선형 가격 × 이산 후보

**Fig. 3b — `f_rung_hist_190w.png`**

> **Caption.** Histogram of selected candidate rungs in scenario sweet_190_w. Interior
> rungs are never selected (0/160); 80–85% of selections land on the sign-determined
> endpoint of the candidate ladder — the signature of a linear price acting on a discrete
> candidate set.

내부 rung 선택은 0/160이고, 가격 부호가 결정하는 끝점으로의 집중이 80~85%다. 선형
가격은 이산 후보 집합 위에서 항상 끝점을 고르므로 bang-bang은 파라미터 문제가 아니라
구조의 귀결이다. 흥미롭게도 시간 평균 명령은 내부값(~1,295)에 위치한다 — bang-bang이
시간 분할로 내부 최적을 흉내 내는 것과 정합하며, 다만 그 대가가 §2b의 풀스팬 진동이다.

### (d) 처방 사다리와 기각 계보

탈선형화 사다리는 다음과 같이 종결됐다 — 박스(외삽 제거, 폭 = 가격 FD 측정폭 300) 채택,
walk(리더 시야 확장) 채택, cross 항 부활 기각, metering 가격 가중 0.5 기각, 2차 자기항
사전 기각. cross와 가중은 박스 끝 선택률(85~100%)을 바꾸지 못한 채 서로 다른 극단 셀을
깨뜨렸고(crossON은 200_w를 +11.0으로 구제하나 190_w를 −47.2로, pw0.5는 170_incident를
−77.9로), 2차항은 기존 fd3 3점 진단으로 곡률을 직접 측정해 구현 전에 기각했다 — 볼록
61%(동전 수준), 이차차분 부호 반전율 31%(잡음), 표적 셀 200_w의 동향(E) 램프 2개는
75% 이상 오목으로 2차항이 끝점 선택을 오히려 강화한다. 비용 곡선의 실구조는 곡률이
아니라 문턱-절벽이다. 요약하면, 측정 불확실성이 큰 한계비용 곡선 아래에서 가격 수단보다
수량 수단이 강건하다는 Weitzman의 prices-versus-quantities 논리와 정합하는 결과다 —
본 시스템에서 조정을 실제로 수행하는 것은 가격이 아니라 수량형 수단(hard budget과
박스 폭)이다.

**[검토 필요 — §3]**
1. rung 히스토그램 모수(0/160, 80~85%)의 캡션 수치를 그림 원본과 대조.
2. Weitzman 문장의 위치(§3 결미 vs 논의 절 이동)와 인용 형식.
3. dual 감사 표의 컬럼명 노출 수준 — 본문에 코드 컬럼명을 남길지 부록으로 뺄지.
4. "제거 시 −79%"(hard budget)의 분모·셀 명세를 본문에 병기할지.

---

## §4. 네트워크 임계성 (Network Criticality) — [런 대기]

이 절은 구조만 배치한다. 계획된 분석은 두 가지다. 첫째, leave-one-out 소거 — 21개
에이전트 × 5셀 = 105런으로 에이전트별 한계 기여의 히트맵을 구성한다 [런 대기]. 둘째,
coupling flux — Stage 3 소거 8케이스 × 5셀(40런)로 방향별 한계가치와 Φ_{U→F}/Φ_{F→U}
분해를 산출한다 [런 대기]. 구 컨트롤러에서의 선행 관찰(u→f 주채널 등)은 재확인 프레임
으로만 인용하고 새 표에는 혼입하지 않는다. 임계점 주장은 구간(bracket) 형식으로 서술할
예정이며, "본 네트워크에 한정"의 조건 한정어를 소절당 1회 부착한다.

**[검토 필요 — §4]**
1. 런 도착 후 전면 재작성 — 현재는 자리 표시.
2. 히트맵 축 설계(x = 시나리오, y = agent)와 diverging 컬러 중심(ρ/ρ_crit = 1) 확정.

---

## §5. 한계 (Limitations)

실패 영역을 결과 블록으로 보고한다 — 지도의 가치는 어디서 작동하지 않는지도 그리는 데
있다. 각 항목은 측정된 사실, 원인 귀속(측정된 경우에 한함), 운영 처방의 순서로 서술한다.

### (1) dual 가격 2종의 inert

§3(b)에서 보인 대로 λ_P와 λ_UF 모두 커밋 가격이 항상 0이다(비영 0/40). λ_P는 dual이
꺼져서가 아니라 corrector가 실현-공간 음수 잔차를 절단하기 때문이고, λ_UF는 조정 모드
기본값이 equality라 갱신 루프 자체가 돌지 않기 때문이다 — 두 원인 모두 코드 경로로
확정했다. 처방 — 계층 조정의 서술은 dual이 아니라 hard budget + marginal price 위에
세워야 하며, dual 재설계는 후속 과제로 남긴다.

### (2) sweet_200_w — rate limit의 물리적 비용

**Fig. 5a — `f_rho_FW_E_sweet_200_w.png`** (서향 대응 그림 `f_rho_FW_W_sweet_200_w.png`)

> **Caption.** Density of the eastbound freeway in scenario sweet_200_w. The density rises
> to 92.3 veh/km/lane — about 93% of jam density — so recovery requires release swings of
> up to +815 veh/h per ramp per step, which the ±300 veh/h box cannot deliver.

**Fig. 5b — `f_rampq_R_D_E_200w.png`** (나머지 램프 — `f_rampq_R_D_W_200w.png`,
`f_rampq_R_F_E_200w.png`, `f_rampq_R_F_W_200w.png`)

> **Caption.** On-ramp queues during the recovery phase of sweet_200_w; the horizontal
> line marks the storage constraint (the ramp storage limit, 180 veh). Under the rate-limited
> configuration the queue reaches a mean of 2,763 and a peak of 4,317 veh, 2.4× the
> unconstrained anchor — the queueing cost of the ±300 veh/h release limit at extreme
> load, far beyond the storage reference.

200_w에서 P-Stack은 PFO 대비 −20.7%로 유일하게 진다(표 1, 보조 행). 종단 잔존 회계도
이와 정합한다 — 창 종료 시점의 망 내 차량은 P-Stack 6,532대로 PFO 2,740대를 상회한다
(표 1c). 부검 결과 손실은 두 성분으로
분리된다. 첫째, 채점 맹점 — 박스 단독 구성에서 리더 의도가 박스 끝(3,190~3,374)에
고착되는 현상은 BOX-WALK 실험이 확증했고(의도 3,190 → 5,805), rollout에 다중 스텝
도달을 모델링하면 교정된다(§2e). 둘째, 잔여 손실은 액추에이터 물리다 — 밀도가
92.3 veh/km/lane(jam의 약 93%)까지 오른 상태의 회복은 스텝당 +815 veh/h의 방류 스윙을
요구하는데 박스는 +300으로 제한하고, 무제한 앵커가 한 스텝에 도달하는 전량 방류를
5~8스텝에 걸쳐 따라가는 동안의 과소 방류가 램프 큐(평균 2,763, 최대 4,317 veh — 앵커의
2.4배)와 urban 축적으로 눈덩이가 된다. 큰 up-jump의 허용은 이미 기각된 방향이다(up600은
파국을 2셀에서 5셀로 확산, up900 폐기 — 아래 기각 계보). 처방 — rate-limited actuation은
평활성·중간 부하 이득과 극단 부하 회복 속도를 교환하므로, jam 근방 운영이 예상되는
망에서는 박스 폭의 상향이 아니라 회복 국면 전용 규칙(예: 무제한 앵커 병기 운영)을
검토해야 한다. 잔여 격차의 추가 귀속은 유보한다.

### (3) VSL 앵커 위반과 VSL_BOX 교정

**Fig. 5c — `f_vsl_seg_190w.png`**

> **Caption.** Per-segment VSL commands in scenario sweet_190_w under VSL_BOX = 10.
> Steps are bounded by ±10 km/h relative to the previous commit, closing the re-anchoring
> loophole of the anchor configuration, whose per-step change reached 50 km/h — 2.5× the
> nominal 20 km/h limit.

앵커 구성의 VSL 후보 필터는 직전 커밋이 아니라 Jacobi 반복 내부 snapshot에 앵커되어,
sweep마다 ±20씩 재앵커된 결과 스텝당 실측 최대 50 km/h(명목 20의 2.5배, 발생 112회/7,020
관측)의 이동이 존재했다. 이 결함은 전 구성이 공유하므로 기존 A/B 판정을 오염시키지
않으며, 제안 구성에서는 VSL_BOX(previous 앵커, ±10)로 교정했다. 교정의 단독 효과는 구
box300 → 300+vsl10의 단일 변경 비교에서 170_w가 −140.85%에서 +11.72%로 반전된 것으로
확인된다.

### (4) 리더 trust region — 우회가 load-bearing

리더의 명목 trust region 반경 1500은 앵커 우회로 사실상 무효이며(후보는 항상
[1,200, 6,000] 전역), 이를 강제(STRICT)하면 독립 2회 모두 파국이었다(−19.99% / −32.31%).
즉 현 제안의 성능은 trust region의 부재-우회에 의존한다. 처방 — trust region을 살리려면
§2e의 walk와 같은 도달 모델링이 선행되어야 하며, 단순 강제는 금지된다.

### (5) 기각 계보

사후 튜닝이 아니라 사전 등록식 A/B였고 전부 데이터로 기각됐음을 표로 남긴다.

| 팔 | 가설 | 측정 결과 | 판정 |
|---|---|---|---|
| gain 1.0 (내부 착지) | λ를 내부값에 착지시키면 개선 | 평균 −5.32% | 기각 |
| STRICT trust region ×2 | 명목 반경 강제 | −19.99% / −32.31% | 기각 |
| 구 box300 | metering 박스 단독 | 170_w −140.85 (VSL 구멍) | VSL_BOX로 대체 |
| up600 / up900 | 올림 확대로 회복 가속 | 파국 2셀 → 5셀 확산 / 첫 셀 동궤적 | 기각·폐기 |
| BUDGET_OFF | hard budget 제거 | −79% | 기각(budget은 필수) |
| crossON | 박스 위 cross 항 부활 | 200_w +11.0, 190_w −47.2 | 기각 |
| pw0.5 | metering 가격 가중 반감 | 170_incident −77.9, 5/10셀 bit-identical | 기각 |
| 2차 자기항 | 곡률 항 추가 | fd3 진단 — 볼록 61%, 반전율 31%, 200_w E램프 오목 | 구현 전 기각 |
| walk-M | metering 단독 walk | 사용자 지시로 중단(절연 미측정) | 중단 |

### (6) 결정론·model-plant match — 재서술

§0.1에서 선언한 대로 본 결과는 결정적 시뮬레이터의 단일 실행이며 예측 모델이 플랜트와
동일하다. 따라서 여기서의 개선율은 모델 불일치·외란 하의 성능을 보증하지 않으며, 주장의
범위는 "본 네트워크·본 시나리오 집합에서의 사례 연구 + 5셀 방향 일관성"으로 한정된다.
새 데이터는 이 절에 투입하지 않았다 — 전 항목이 §2·§3과 notes의 측정 사실의 재서술이다.

**[검토 필요 — §5]**
1. 기각 계보 표의 포함 범위 — 파일럿 팔 전부 나열 vs 대표 축약(현재는 전부).
2. VSL 앵커 결함의 코드 수정 여부 — 수정 시 전 셀 재실행과 동결 원칙 충돌(현재 미수정
   유지 + 기재).
3. (2)의 처방 문장(회복 국면 전용 규칙)의 수위 — 제안으로 남길지 후속 과제로 밀지.
4. walk-MVG의 170_skew15 비용(+12.87 → +0.58, M/VG 기여 미절연)을 (2)에 병기할지.

---

*그림 사용 총괄 — §1: f_ttt_traj_sweet_*(6종, 대표 1 + 보조 5). §2: f_rho_FW_E/W_sweet_190_w,
f_meter_R_{D,F}_{E,W}_190w(4), f_rampq_R_{D,F}_{E,W}_190w(4), f_mfd_FW_E/W_190w,
f_intent_200w, f_meter_total_200w, f_tttgap_200w. §3: f_lambda_190w, f_rung_hist_190w.
§5: f_rho_FW_E/W_sweet_200_w, f_rampq_R_{D,F}_{E,W}_200w(4), f_vsl_seg_190w.
`analysis/figures/`의 30개 기본 그림 전부가 1회 이상 인용됨.*
