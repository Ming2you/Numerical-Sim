# 결과 절 초안 v3 — 그림·캡션·본문 (5컨트롤러·통용 시나리오명·urban 추가)

> 작성일 2026-07-18. 동결 프레임 = `ANALYSIS_PLAN_FINAL.md`(§0~§5), 수치 출처 =
> `analysis/tables/t1_macro_full.md`(2026-07-18 확정 런)과 `2026-07-17/notes.md`(측정 사실).
> 그림 파일은 전부 `analysis/figures/`에 실존하는 것만 인용한다. 본문은 국문, 캡션은 영문.
> §4는 런 미도착으로 구조만 배치한다.
> v3(2026-07-18) — 컨트롤러 5종 확정(No control / Wu / PFO (box) / Centralized /
> P-Stack (walk-MVG); 무제한 PFO 제거), 시나리오 통용명(Low / Med / Med (skewed) /
> Med (incident) / High demand), sweet_200_w 제외, urban 분석 신규(§2e: green 배분·
> urban 큐). P-CENT = 의도적 rate-limit-free 상한. 표 1b/1c(urban/freeway 분해 + N_end).
>
> **★[결과 갈음 예정 — 초안 지금 작성 가능, 아래 1건만 나중에 추가]**
> 1. ~~§1 계산시간 표~~ **완료(2026-07-18)**: 0단·전 컨트롤러 1코어 직렬 재측정 반영
>    (Wu 6.3 / PFO(box) 1.6 / Centralized 22.7 / P-Stack 30.5 s/step 평균, max 최대 50.6).
> 2. **§5 상한 tightness 문단** — dense 그리드(후보 조밀·global 매스텝)로 P-CENT를 더
>    뒤졌을 때 현행(4,705 등) 대비 개선폭 = 상한 빡빡함. **진짜 grid+dense로 재실행 중**
>    (직전 dense는 default가 slsqp라 SLSQP로 샜던 것 — config를 structured_grid로 고정해 수정).
>    완료 시 §5에 추가. 그 외(표1 성능·계산표·urban·§2~§4·그림)는 확정.

---

## §0. 실험 설정 (Experimental Setup)

### §0.1 채점 규약

모든 성능 수치는 windowed total travel time(wTTT)으로 보고한다. 시뮬레이션 총 길이는
T_total = 10,800 s(제어 주기 180 s × 60스텝)이고, 최초 20스텝(WARM = 20)은 전 구성이
무제어(NC)로 공유하는 웜업 구간이다. wTTT는 웜업 이후의 누적 총 통행시간으로 정의한다.

> wTTT = TTT_cum(t = T_total) − TTT_cum(step = 20)  [veh·h]

본문 표의 개선율 규약은 NC 대비 백분율이다.

> 개선%(NC) = (J_NC − J_ctrl) / J_NC × 100

제안 계열 내부 비교(§2·§3·§5)에서는 PFO(box) 대비 백분율을 병용하며, 사용하는 곳마다
분모를 명기한다. wTTT에는 on-ramp 대기 차량의 통행시간이 포함된다 — 즉 차량을 램프에 세워 두는
것으로는 wTTT를 낮출 수 없다(§2c 각주 참조). Delay 계열 지표는 free-flow reference 런이
시나리오별로 확보된 뒤 추가한다 [런 대기].

시뮬레이터와 전 컨트롤러는 결정적(deterministic)이며 모든 수치는 단일 실행에서 얻었다.
따라서 시드 반복·유의성 검정 대신 5개 시나리오에 걸친 방향 일관성으로 강건성을 평가하고,
개별 셀 수치는 시나리오별 사례 연구로 해석한다. 결정론 매크로 제어 문헌(Wu 2022; Hegyi
2005; Van den Berg 2007)의 보고 관례와 동일하다. 아울러 본 연구의 예측 모델은 플랜트와
동일하다(model–plant match). 이 두 선언의 함의와 한계는 §5에서 논한다.

### §0.2 시나리오

논문 본문 시나리오는 5개 — **Low demand**(저수요), **Med demand**(중수요·freeway
병목), **Med demand (skewed)**(urban 경계 불균형, 서:동 = 1.5:1), **Med demand
(incident)**(본선 폐색·용량 강하), **High demand**(고전달·복합 스트레스) — 이며,
High demand는 메커니즘 절(§2·§3)의 대표 해부 셀을 겸한다. 이하 본문·그림·표는 이
통용 이름을 사용한다(내부 셀명 sweet_155_w / sweet_170_w / sweet_170_skew15_w /
sweet_170_incident_w / sweet_190_w에 각각 대응).

- **그림 0a — 네트워크 스키매틱**: `analysis/figures/f0_network_schematic.pdf` —
  2×3 그리드(신호 A–D,F / 비제어 E / 경계 게이트 7쌍) + 8-seg × 2링크 freeway,
  다이아몬드 IC(D·F: off-ramp seg 2/4 → 60-veh urban 저장, on-ramp 합류 seg 3/5,
  용량 1,500 veh/h, 큐 ≤ 180 veh), **21-player 소유권 오버레이**(urban 신호 5 +
  세그먼트별 freeway 16; 합류 seg 소유자가 metering, seg 0이 origin 큐 소유.
  코드 플래그명 SEG13은 4-seg 시절 레거시).
- **표 0a·그림 0b — 수요·사고 명세**: `analysis/tables/t0_demand_scenarios.md`,
  `analysis/figures/f0_demand_profile.pdf` — 전 셀 공통 사다리꼴(base 0.5, 65–125분
  plateau), 클래스 배율 1.55/1.70/1.90, skewed는 서:동 = 1.5:1 부피보존.
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
  프레이밍(structured grid 직렬), Wu 2022 충실도 6행 매트릭스
  (SUMO 플랜트 vs 모델=플랜트 등 편차 명시).

### §0.3 비교 컨트롤러 — 각 기준선이 격리하는 격차

베이스라인마다 "어떤 격차를 격리하는 도구인지"를 선언한다(권한/조정 분해는 Hegyi et al.
2005의 등화 실험 계보를 따른다).

| 컨트롤러 | 격리하는 격차 |
|---|---|
| No control | 무제어 참조 — 모든 개선율의 분모 |
| Wu | 문헌(Wu 2022) 재현 분산 제어(WU-CD-F) — **권한 격차**의 하한. No control↔Wu 간극 = 문헌 권한 집합으로 얻는 가치, Wu↔PFO(box) 간극 = 권한 확장(특히 ramp metering 소유권)의 가치 |
| PFO (box) | 제안 팔로워 단독(리더 없음)에 제안과 **동일한 이동 한계**(meter ±300 / VSL ±10 / green ±6) 부과 — **공정 액추에이터 기준선**. PFO(box)↔P-Stack 간극 = 동일 이동 한계 하에서 리더 조정이 만드는 가치를 격리 |
| Centralized | 중앙집중·이동 한계 무적용(rate-limit-free) 컨트롤러(P-CENT, structured grid) — 무제약 이동의 **성능 상한(upper bound)**을 재는 도구. 이동 한계는 의도적으로 적용하지 않는다 |
| P-Stack (walk-MVG) | 제안 계층(Stackelberg) 컨트롤러, walk-MVG 구성 |

PFO는 **이동 한계 부과(box) 버전만** 사용한다 — 제안 컨트롤러와 액추에이터 이동 폭을
맞춘 공정 기준선이므로, 조정 격차(PFO(box)↔P-Stack)가 권한·이동 한계 차이가 아니라
순수 리더 조정에서 나옴을 보장한다.

**[검토 필요 — §0]**
1. 사고 시나리오 수치 명세(A5)를 수요 표에 통합할지 별도 문단으로 둘지.
2. 결정론·model-plant match 선언의 §0 배치 위치(채점 규약 뒤 vs 절 서두).

---

## §1. 거시 성능 (Macroscopic Performance)

### 표 1 — 5컨트롤러 × 5시나리오 wTTT [veh·h] (괄호 안 = NC 대비 개선%)

| Scenario | No control | Wu | PFO (box) | Centralized | P-Stack (walk-MVG) |
|---|---|---|---|---|---|
| Low demand | 8,977 | 6,427 (+28.4) | 1,689 (+81.2) | 1,614 (+82.0) | 1,686 (+81.2) |
| Med demand | 13,028 | 8,754 (+32.8) | 7,967 (+38.8) | 2,488 (+80.9) | 2,683 (+79.4) |
| Med demand (skewed) | 13,175 | 12,183 (+7.5) | 2,838 (+78.5) | 2,517 (+80.9) | 2,667 (+79.8) |
| Med demand (incident) | 9,581 | 9,111 (+4.9) | 7,413 (+22.6) | 2,354 (+75.4) | 2,295 (+76.0) |
| High demand | 16,518 | 16,277 (+1.5) | 5,491 (+66.8) | 4,705 (+71.5) | 5,096 (+69.2) |

표 각주 — ① 개선% = (J_NC − J_ctrl)/J_NC × 100, wTTT는 §0.1 정의(WARM = 20 이후 창).
② 이동 한계 준수: P-Stack과 PFO(box)는 meter ±300 / VSL ±10 / green ±6을 준수한다
(PFO는 이동 한계 부과 버전만 사용). Centralized는 상한(upper bound) 도구로서 의도적
미적용(실측 meter 628 / VSL 30 / green 41). Wu(문헌 재현)도 미적용(VSL 50 / green 36).
③ wTTT에는 on-ramp 대기 통행시간이 포함된다. ④ delay 열은 free-flow reference 확보 후
추가 [런 대기].

### 표 1b — wTTT의 urban/freeway 분해 [veh·h] (표기 = urban / freeway)

| Scenario | No control | Wu | PFO (box) | Centralized | P-Stack (walk-MVG) |
|---|---|---|---|---|---|
| Low demand | 4,106 / 4,872 | 3,411 / 3,016 | 844 / 845 | 885 / 728 | 952 / 733 |
| Med demand | 6,545 / 6,483 | 5,205 / 3,549 | 4,616 / 3,351 | 1,275 / 1,213 | 1,555 / 1,128 |
| Med demand (skewed) | 6,689 / 6,486 | 6,192 / 5,990 | 1,751 / 1,087 | 1,397 / 1,121 | 1,515 / 1,152 |
| Med demand (incident) | 4,764 / 4,817 | 4,555 / 4,556 | 4,168 / 3,245 | 1,395 / 959 | 1,323 / 972 |
| High demand | 8,779 / 7,739 | 8,608 / 7,670 | 4,137 / 1,354 | 3,273 / 1,432 | 3,672 / 1,424 |

### 표 1c — 종단 잔존 차량 N_end [veh] (보조행)

| Scenario | No control | Wu | PFO (box) | Centralized | P-Stack (walk-MVG) |
|---|---|---|---|---|---|
| Low demand | 7,950 | 5,502 | 264 | 262 | 286 |
| Med demand | 10,859 | 7,187 | 6,262 | 262 | 279 |
| Med demand (skewed) | 10,962 | 10,301 | 272 | 263 | 281 |
| Med demand (incident) | 8,332 | 8,006 | 6,011 | 262 | 281 |
| High demand | 13,342 | 13,280 | 1,243 | 606 | 1,020 |

표 1c 각주 — N_end = 마지막 180 s 스텝의 TTT 증분 × 20 = 종단 시점 망 내 차량 수(각
스텝의 TTT 증분은 N/20 veh·h이므로). 이 보조행은 큐를 채점창 밖으로 미뤄 wTTT를 낮추는
회계가 없는지 검사한다.

**분해와 종단 회계.** No control은 창 종료 시점에 7,950~13,342대가 망 내에 잔존하는(미배수)
반면, 제어군은 저·중부하 셀에서 약 260~290대 수준으로 배수를 완료한다 — 표 1의 개선이
큐를 창 밖으로 미룬 결과가 아님을 보이는 회계다. High demand에서 잔존은 Centralized 606 <
P-Stack 1,020 < PFO(box) 1,243대의 순서로 wTTT 순위와 일치한다. 분해를 보면 P-Stack은
High demand에서 urban TTT를 PFO(box) 대비 4,137 → 3,672 veh·h로 줄이면서 freeway는
1,354 → 1,424 veh·h로 소폭만 늘려 총량을 5,491 → 5,096 veh·h로 낮춘다 — 계층 조정이
urban·freeway를 함께 관리해 총 통행시간을 줄이는 증거다.

**Fig. 1 — `f_ttt_traj_sweet_170_w.png`** (Med demand 대표; 나머지 4셀은
`f_ttt_traj_sweet_155_w.png`, `f_ttt_traj_sweet_170_skew15_w.png`,
`f_ttt_traj_sweet_170_incident_w.png`, `f_ttt_traj_sweet_190_w.png`)

> **Caption.** Per-step total travel time over the scoring window for the Med demand
> scenario, comparing the five controllers (No control / Wu / PFO (box) / Centralized /
> P-Stack). The controllers separate shortly after control activation; No control and Wu
> keep accumulating while PFO (box), Centralized, and P-Stack suppress and then drain the
> queue. Terminal offsets correspond to the wTTT entries of Table 1 (improvement computed
> as (J_NC − J_ctrl)/J_NC × 100).

### 본문 서술

**권한 격차 (Wu).** Wu(WU-CD-F)는 문헌의 권한 집합을 재현한 분산 제어로, 저·중수요에서는
No control 대비 2,550 veh·h(+28.4%)와 4,274 veh·h(+32.8%)를 회수하지만, 사고·고수요
셀에서는 No control에 근접한다 — Med (incident) +4.9%, High demand +1.5%이며 경계
불균형 셀에서도 +7.5%에 그친다. 같은 셀에서 이동 한계를 지키는 PFO(box)·P-Stack이
+66~81%를 회수하는 것과 대비하면, 이 간극의 대부분은 조정 방식이 아니라 권한 집합 —
특히 ramp metering의 소유 — 에서 나온다.

**조정 격차 (P-Stack vs PFO (box)).** 제안과 **동일한 이동 한계**를 부과한 팔로워 단독
PFO(box)와 비교하면, 리더 조정을 더한 P-Stack의 가치가 부하·구조에 따라 극적으로 갈린다.
팔로워 단독으로도 안정적인 셀 — Low demand(+81.2 vs +81.2), skewed(+78.5 vs +79.8) —
에서는 두 컨트롤러가 근접하지만, Med demand와 Med (incident)에서는 PFO(box)가 붕괴한다
— 각각 7,967(P-Stack 2,684의 3.0배), 7,413(P-Stack 2,295의 3.2배). 종단 회계도 이를
뒷받침한다(표 1c): PFO(box)는 두 셀에서 6,262·6,011대를 배수하지 못한 채 창을 마치는
반면 P-Stack은 278·281대로 배수를 완료한다. 즉 동일한 액추에이터 물리 아래에서 팔로워
단독이 램프·urban 큐를 조율하지 못해 스필백에 빠지는 구간을, 리더의 metering·green
조정이 방지한다 — **동일 이동 한계 조건에서 조정의 가치가 가장 크게 드러난다.**

**중앙 상한 (Centralized).** Centralized(P-CENT)는 중앙집중·이동 한계 무적용 구성으로
성능 상한(upper bound)을 재는 도구다 — 이길 수 없는 대상은 상한으로 명명하는 보고 관례를
따른다. 5셀 중 4셀(Low, Med, skewed, High demand)에서 전 컨트롤러 최저 wTTT를 기록하며,
P-Stack과의 격차는 NC 대비 개선율 기준 0.8~2.7%p에 그친다. Med (incident)에서는 이동
한계를 지키는 P-Stack(2,295)이 상한 참조(2,354)를 0.6%p 근소 상회한다. 즉 제안은 전
시나리오에서 무제약 중앙 상한에 등가에 가까운 성능을 이동 한계 준수 하에 달성하며,
"중앙을 상회한다"는 주장은 하지 않는다.

**계산 시간.** 채점창 기준 per-step 계산 시간(High demand, **전 컨트롤러 1코어 직렬**,
동일 머신)은 다음과 같다.

| [s/step] | Wu | PFO (box) | Centralized | P-Stack |
|---|---|---|---|---|
| 평균 | 6.3 | 1.6 | 22.7 | 30.5 |
| 최대 | 13.1 | 2.0 | 46.4 | 50.6 |

공정성 — 러너가 전 컨트롤러의 탐색 백엔드를 **serial(1코어)로 고정**하므로(진단
`*_parallel_workers = 1` 확정) 벽시계 비교는 동일 코어 예산에서 이뤄진다. P-CENT의
"그리드"는 전수 열거가 아니라 구조적 적응 탐색(스텝당 ~450 후보, 후보당 중첩 follower가
없어 저렴)이고, P-Stack은 리더 후보마다 follower Nash 해를 중첩해 후보당 비용이 크다 —
그래서 후보 수는 P-CENT가 많아도 총 시간은 비슷한 자릿수다. No control은 계산이 사실상
0이라 표에서 생략한다. (수치는 0단 = `_sync_legacy_queues` 인덱스 캐시 적용판; 성능 wTTT는
0단이 비트동일이라 표1과 동일.)

실시간성 판정은 최대값으로 건다 — 전 컨트롤러의 최악 스텝(50.6 s, P-Stack)이 제어 주기
180 s를 하회하므로, 관측된 전 구성이 실시간 제약 안에 있다. 전 실험은 12th Gen Intel
Core i7-12700K(물리 12 / 논리 20코어), 16 GB RAM, Windows 11, Python 3.12.13에서
수행했다. 최적화는 전부 순수 Python으로 구현한 자체 coordinate-descent/격자 탐색이며
외부 LP/QP 솔버는 사용하지 않는다. 팔로워 Jacobi 합의는 최대 5 sweep, 리더는 정제 후보
최대 25개(격자 최대 49)를 평가하고, N_P primal–dual 루프는 K = 4 반복으로 상한을 둔다.

**[검토 필요 — §1]**
1. delay 열 — free-flow reference 런 도착 후 일괄 갱신.

---

## §2. 메커니즘 (Mechanism)

이 절은 대표 셀 High demand(sweet_190_w)의 단일 런을 해부해, §1의 스칼라 격차가 어떤
액추에이터 거동에서 나오는지를 시점 정렬 서사로 보인다. (a)~(d)는 freeway 액추에이터
거동(밀도·metering·램프 큐·FD)을 pd4_ref(박스 이전 구성, 진동 원인 상태) 대비로 해부하고,
(e)는 5컨트롤러의 urban 저수지 관리(green 배분·urban 큐)를 다룬다. 인과 서술은 조작·측정된
채널에만 사용하고, 미측정 정합은 "~와 정합한다"로 구분한다.

### (a) 임계 밀도선 운영

**Fig. 2a — `f_rho_FW_E_sweet_190_w.png`** (서향 대응 그림 `f_rho_FW_W_sweet_190_w.png`)

> **Caption.** Density of the eastbound freeway bottleneck under the proposed controller
> (colored) and the pd4 reference (black) for the High demand scenario; the horizontal dashed
> line marks the critical density ρ_crit = 33.5 veh/km/lane. The proposed controller holds
> the peak density at 32.0 veh/km/lane, just below criticality, whereas the reference
> overshoots to 34.5 veh/km/lane and crosses into the congested regime.

관찰 — 제안 컨트롤러의 병목 밀도 최대값은 32.0 veh/km/lane으로 임계 밀도
ρ_crit = 33.5 veh/km/lane을 넘지 않는 반면, pd4 기준 팔은 34.5까지 상승해 임계선을
넘는다. 해석 — metering이 유입을 임계 접근 시점에 제한한 결과이며(§2b의 명령 시계열과
시점 일치), 임계선 바로 아래에서의 운영은 §2d의 FD 운영점 분포와 정합한다. 임계 초과
1.0 veh/km/lane과 미달 1.5 veh/km/lane의 차이가 §1 High demand에서 P-Stack의 우위
(PFO(box) 대비 335 veh·h, +6.1%)로 이어진다는 서술은 측정된 두 끝(명령과 wTTT)을 잇는
해석이며, 중간 매개의 정량 분해는 Stage 2 이벤트 감사에서 다룬다 [런 대기].

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
> reference (black), the High demand scenario; the horizontal line marks the storage
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
> the High demand scenario; the vertical dashed line marks ρ_crit = 33.5 veh/km/lane, black
> points the pd4 reference and colored points the proposed controller. The proposed
> controller confines operation to the uncongested branch, consistent with the density
> trajectory of Fig. 2a.

관찰 — 제안 컨트롤러의 운영점 구름은 비혼잡 가지에 갇혀 있고, 기준 팔은 임계 우측으로
넘어간 점들을 남긴다. 이는 (a)의 시계열 관찰을 상태 평면에서 재확인하는 것으로, 별도의
새 주장을 담지 않는다.

### (e) urban 저수지 관리 — green 배분과 urban 큐

앞의 (a)~(d)가 freeway 액추에이터를 다뤘다면, 이 소절은 계층이 urban 저수지를 어떻게
관리하는지를 5컨트롤러 비교로 보인다 — §1 표 1b의 urban/freeway 분해를 메커니즘 궤적으로
뒷받침한다.

**Fig. 2e-1 — `f_urban_green_split.png`** (Med demand (skewed))

> **Caption.** Phase-1 green split at signal D over the scoring window for the Med demand
> (skewed) scenario, across the five controllers. No control and PFO (box) hold a
> near-fixed split, Wu swings it widely, and Centralized/P-Stack apply moderate,
> load-following adjustments — the urban signal lever the hierarchy actuates.

**Fig. 2e-2 — `f_urban_queue.png`** (High demand)

> **Caption.** Total urban movement queue over the scoring window for the High demand
> scenario, across the five controllers. No control and Wu let the urban reservoir grow
> essentially unbounded (peak ≈ 7,940 veh, undrained at window end), whereas PFO (box),
> Centralized, and P-Stack cap the peak at 3,000–3,700 veh and drain to 250–760 veh.

관찰 — green 배분(Fig. 2e-1): No control과 PFO(box)는 신호 D의 phase-1 배분을 거의
고정한 채 두는 반면, Wu는 부하를 좇아 넓게 흔들고(관측 범위가 가장 큼) Centralized·P-Stack은
절제된 폭으로 조정한다. urban 큐(Fig. 2e-2): 고수요에서 No control·Wu의 urban 총 큐는
사실상 무한 증가해(정점 ≈ 7,940 veh, 창 종료까지 미배수) — Wu가 green을 흔들어도 ramp
metering 권한이 없어 urban 저수지를 배수하지 못하는 것과 정합한다 — 반면 PFO(box)·
Centralized·P-Stack은 정점을 3,000~3,700 veh로 억제하고 250~760 veh까지 배수한다.
해석 — 계층 컨트롤러(및 PFO(box))는 freeway뿐 아니라 urban 저수지도 함께 관리하며,
이것이 표 1b에서 P-Stack이 고수요 urban TTT를 No control 대비 8,779 → 3,672 veh·h로
줄이는 분해의 메커니즘적 근거다.

**[검토 필요 — §2]**
1. 대표 램프 선택 — R_D_E 1개 본문 + 3개 보조인지, 4램프 격자 1그림인지.
2. Stage 2 이벤트 감사(counterfactual replay) 도착 후 (a)~(c)의 매개 정량 문장 보강.

---

## §3. 가격 채널 (Price Channels)

이 절은 계층 내부의 조정 신호를 감사한다. 결론을 먼저 요약하면 — 명목상의 dual 가격은
작동하지 않고, 실제 조정은 수량형 수단이 수행하며, 선형 가격과 이산 후보의 조합은
구조적으로 bang-bang을 낳는다. 이 진단이 §2의 박스·walk 처방으로 이어진다.

### (a) λ의 실측 거동 — bang-bang

**Fig. 3a — `f_lambda_190w.png`**

> **Caption.** Committed follower price λ_P over time in the High demand scenario. The price
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
| offset marginal price (비램프 A/B/C, `wu_f3_offset_price_*`) | 40/40 | **계산은 되나 한계가치 무시** — ‖가격‖≈0.01 |
| ramp-aware offset (램프 D/F, `ramp_offset_enabled`) | High·Med서 활성 | **혼잡 구간서 실질 기여**(High −1.0%) |
| N_UF hard budget (`wu_seg13_budget_*`) | 17/40 | 활성 |

행동 검증도 일치한다 — λ_P를 끄는 NP_OFF 팔은 앵커와 10/10 bit-identical이다. 따라서
계층을 실제로 조정하는 수단은 dual 가격이 아니라 N_UF hard budget(제거 시 −79%)과
marginal price 두 가지다. Stackelberg dual 기계장치가 통째로 논다는 사실은 §5의 한계
(1)로 정직하게 기재한다.

**offset — 비램프 신호는 죽은 채널, 램프 신호(D/F)는 혼잡 구간서 살아 있다.** offset
조정은 두 갈래로 나뉜다. (i) 비램프 신호(A/B/C)의 offset marginal price는 매 스텝
계산·하달되지만(40/40, SQP식 inner-walk 4회) 이 망에서 그 TTT 기울기가 극히 작아
(‖가격‖≈0.008~0.03) 단독으로는 신호 위상을 거의 못 움직인다 — **비램프 offset 가격 단독의
wTTT 효과는 평균 −0.02%로 사실상 무차별**하다. (ii) 반면 램프 신호(D·F, 다이아몬드 IC)의
ramp-aware offset(램프 저장 동역학을 반영한 위상 탐색)은 **혼잡 구간에서 실질적으로 기여**한다
— D/F offset을 켜면 High demand wTTT가 5,148 → 5,096(−1.0%, 52 veh·h) 개선되고 Med에서도
−0.04%이며, D/F 활성화가 같은 셀의 비램프 offset까지 함께 각성시킨다(Med에서 A/B/C/D/F 5신호
전부 이동, 이전엔 High만). 저·경계불균형·사고 셀에서는 여전히 offset이 부동이다. 즉 offset은
**균일하게 죽은 채널이 아니라, 램프 접속부 혼잡이라는 특정 레짐에서만 살아나는 상태-의존
채널**이며, 제안 컨트롤러는 두 갈래를 모두 포함한다(비램프 가격 + D/F ramp-aware). 어떤
채널이 어디서 조정을 수행하는지 지도를 그리는 것이 §3의 목적이다.

### (c) 구조 진단 — 선형 가격 × 이산 후보

**Fig. 3b — `f_rung_hist_190w.png`**

> **Caption.** Histogram of selected candidate rungs in the High demand scenario. Interior
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
사전 기각. cross와 가중은 박스 끝 선택률(85~100%)을 바꾸지 못한 채 서로 다른 셀을
깨뜨렸고(crossON은 High demand를 −47.2로, pw0.5는 Med (incident)를 −77.9로), 2차항은
기존 fd3 3점 진단으로 곡률을 직접 측정해 구현 전에 기각했다 — 볼록 61%(동전 수준),
이차차분 부호 반전율 31%(잡음), 고부하 셀의 동향(E) 램프 2개는 75% 이상 오목으로 2차항이
끝점 선택을 오히려 강화한다. 비용 곡선의 실구조는 곡률이 아니라 문턱-절벽이다. 요약하면, 측정 불확실성이 큰 한계비용 곡선 아래에서 가격 수단보다
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

### (2) 이동 한계(box)의 부하 민감도 — rate limit의 물리적 비용

이동 한계(metering box 반경 R = 300, 예측 지평 H = 3)는 임의로 고른 하이퍼파라미터가
아니라 물리적으로 결정되는 좁은 안정 구간이다(표 B8, `analysis/tables/t_sensitivity_b8.md`).
High demand에서 R을 225로 좁히면 wTTT가 +112%, 375로 넓히면 +37% 악화된다(Med demand는
±3% 내로 둔감). 좁은 박스는 수요 하강기 회복에 필요한 방류 이동폭을 잃고, 넓은 박스는
선형 가격 × 이산 후보의 bang-bang(§3)을 재유입한다 — **고부하에서 양쪽 극단이 모두 파국**
이므로 R = 300은 두 실패 사이의 좁은 안정 구간이다. 예측 지평도 같은 U자를 그린다
(H = 2에서 +90~226%의 파국, H = 4는 이득 없음). 처방 — rate-limited actuation은 평활성·
중간 부하 이득과 극단 부하 회복 속도를 교환하므로, jam 근방 운영이 예상되는 망에서는
박스 폭·지평을 임의로 늘리지 말고 이 민감도 스윕으로 안정 구간을 먼저 확인해야 한다
(단일 시드, 본 망 기준). 큰 up-jump의 허용은 이미 기각된 방향이다(up600은 파국을 2셀에서
5셀로 확산, up900 폐기 — 아래 기각 계보).

### (3) VSL 앵커 위반과 VSL_BOX 교정

**Fig. 5c — `f_vsl_seg_190w.png`**

> **Caption.** Per-segment VSL commands in the High demand scenario under VSL_BOX = 10.
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
| crossON | 박스 위 cross 항 부활 | High demand −47.2(다른 극단셀 구제하나 상충) | 기각 |
| pw0.5 | metering 가격 가중 반감 | Med (incident) −77.9, 5/10셀 bit-identical | 기각 |
| 2차 자기항 | 곡률 항 추가 | fd3 진단 — 볼록 61%, 반전율 31%, 고부하 E램프 오목 | 구현 전 기각 |
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

*그림 사용 총괄 — §0: f0_network_schematic, f0_demand_profile. §1: f_ttt_traj_sweet_*
(5종, 5컨트롤러 비교). §2: (a~d, freeway 메커니즘) f_rho_FW_E/W_sweet_190_w,
f_meter_R_{D,F}_{E,W}_190w(4), f_rampq_R_{D,F}_{E,W}_190w(4), f_mfd_FW_E/W_190w;
(e, urban) f_urban_green_split, f_urban_queue. §3: f_lambda_190w, f_rung_hist_190w.
§5: f_vsl_seg_190w. `analysis/figures/`의 그림 전부가 1회 이상 인용됨(sweet_200_w 그림·
무제한 PFO 비교 그림은 제거됨).*
