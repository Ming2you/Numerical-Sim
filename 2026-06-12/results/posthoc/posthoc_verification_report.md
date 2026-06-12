# 5개 시나리오 control 효과·allocation before/after 사후검증 리포트

조건: 커밋 99a914a(cycle 위상 plant) 코드 그대로, 수정 없음. 풀 7200s distributed ×5
(peak은 `outputs/phase_peak_full7200_v4` 재사용, 나머지 `outputs/posthoc_*_full7200`).
수치 원본: `*_posthoc.json`, 그래프: 본 폴더 SVG(시나리오별 allocation/추적/액추에이터 9~10장).
분석 도구: `scripts/posthoc_control_verification.py` (신규, 분석 전용).

## 1. 종합 결과 (cycle 위상 plant 기준)

| 시나리오 | improvement | TTT p/b | metering | vsl | balance | 종합 |
|---|---|---|---|---|---|---|
| low | **+5.81%** (<8% ✗) | 1,207/1,281 | ✓(21.0) | ✓ | ✗(B_in 0.101) | FAIL |
| medium | +21.05% | 3,136/3,972 | ✓(25.4) | ✗(초과 6 vs b 0) | **✓** | FAIL |
| peak (required) | +18.08% | 6,481/7,912 | ✓(28.3) | ✓(13 vs 26) | ✓ | **PASS** |
| oversat | +24.06% | 13,013/17,136 | **✓(56.5)** | **✓(23 vs 39)** | ✗(추적 300.5) | FAIL |
| incident | +8.79% | 6,084/6,671 | ✓(29.3) | ✗(초과 13 vs 0) | ✗(추적 123.7) | FAIL |

이전 plant 대비 변화: medium balance가 PASS로 전환(0.0305→0.0239), oversat의
metering(245.9→56.5)·vsl(초과 23<39)이 PASS로 전환. 반면 low(+24.6→+5.8)와
incident(+16.8→+8.8)의 improvement가 하락 — 위상 plant에서 baseline(동기 신호,
50:50)도 현실적인 신호 지연을 같이 갖게 되면서 자유류·중부하의 제어 이득이 압축됨.

## 2. Inflow-outflow allocation — before/after 사후검증 ★

### (a) 게이트 공평성: baseline(allocation 없음) vs proposed(작동)

게이트 7개의 **시간평균 밀도 편차(safe_balance_index)** — allocation의 핵심 임무.

| 시나리오 | spread before(baseline) | spread after(proposed) | 개선배율 |
|---|---|---|---|
| low | 0.1108 | 0.0047 | ×23.6 |
| medium | 0.0821 | **0.0007** | ×117 |
| peak | 0.0278 | 0.0069 | ×4.0 |
| oversat | 0.0262 | 0.0044 | ×6.0 |
| incident | 0.0329 | 0.0046 | ×7.2 |

예) peak 게이트별 시간평균 밀도: baseline 0.060~0.345(F_right가 A_top의 5.8배 대기)
→ proposed 0.063~0.153(최대/최소 2.4배). **전 시나리오에서 allocation이 게이트 간
대기 불균형을 1자릿수 배율로 압축** — 그래프 `*_alloc_B_before_after.svg`에서 부하
가중 B_in 시계열로도 동일 확인(부하 실린 구간에서 proposed가 일관되게 낮음).

### (b) 계획 vs 실현: net-inflow target 추적 (`*_alloc_plan_vs_realized.svg`)

| 시나리오 | 추적오차 [veh/h] (eps_U=100) | N_P 절대오차 [veh] | 판정 |
|---|---|---|---|
| low | 83.5 | 162.2 | ✓ (단 N_P_star 밴드 하한 469 > 자연 누적 — 상시 미달) |
| medium | 48.3 | 63.1 | ✓ |
| peak | 88.1 | 51.0 | ✓ |
| oversat | 300.5 | 147.5 | ✗ — 수요≫용량에서 drain 요청 달성 불가(구조적, round-8/9 결론) |
| incident | 123.7 | 60.1 | ✗ — 동일 계열(용량 0.72×로 부분 과포화) |

결론: **allocation은 균형화(주임무)를 전 시나리오에서 수행하고 있으며, net-inflow
계획 추적은 비과포화에서 합격, 심과포화에서는 물리적으로 불가능한 요청(클립 경계
밖 drain)이 잔차로 남는다** — 컨트롤러 결함이 아니라 시나리오의 통제 가능성 한계.

## 3. Control별 효과 사후검증

### Ramp metering ✓ (5/5 게이트 PASS)
- 잔차 21.0~56.5 ≤ 100 전 시나리오. w_r 평균 8.9~19.6대(최대 41)로 견제 —
  자유류에서는 비구속(수요 제한), oversat에서만 실제 제한하며 본선 보호.
- oversat: 명령이 N_UF_star와 함께 강하(그래프 `posthoc_oversat_metering.svg`),
  적체는 x_on으로 후퇴 — freeway TTT 17,136→13,013 중 본선 측 기여.

### VSL ✓ (반응성 검증, 게이트는 2개 시나리오에서 기존 이슈)
- 활성 빈도 0/3/13/13/24 — 혼잡 수위에 단조.
- 활성 구간 평균 밀도비 > 비활성: low —/0.43, medium 0.68/0.60, peak 0.76/0.68,
  oversat 0.85/0.71, incident 0.73/0.69 — **올바른 조건에서 켜짐**.
- 효과: peak 본선 초과시간 13 vs baseline 26(절반), oversat 23 vs 39. medium(6 vs 0)·
  incident(13 vs 0)의 게이트 FAIL은 "baseline은 차를 게이트에 세워 본선 초과 0"인
  welfare-blind 가드레일 구조(기존 결정 대기 이슈) — VSL 자체는 정상 동작.

### Green split ✓
- 큐압력(직전 상태 p1 점유율) ↔ p1 green 비율 상관: 전 신호·전 시나리오 0.58~0.996
  (중앙값 ~0.87). 신호 green이 실제 큐 상태를 따라간다.

### Offset ✓
- D−A = 95.3~96.4s 전 시나리오(설계 진행시간 95.04s) — A→D 남행 green wave 고정 수렴.
- B/C/F는 회랑 부하·split에 따라 시간 가변(std 14~44s), A 앵커(0).
  효과 정량은 직전 라운드 ablation(+346.7 veh·h)으로 입증됨.

### Perimeter(N_P 추적) ✓(비과포화)
- N_P 절대오차 51~63 veh(medium/peak/incident), oversat 147.5(과포화 위에서 운영),
  low 162.2 — low는 N_P_star 후보 밴드 하한(0.9×521=469)이 자연 누적보다 높아 상시
  미달(기존 "밴드 수요 적응형" 결정 대기 항목의 재확인).

## 4. 수정 없이 보고하는 신규 관찰 (연구자 판단 대상)

1. **low improvement +5.81% < 8%**: 위상 plant에서 자유류 제어 이득이 압축돼 main
   metric 자체가 미달. low는 "제어가 이득을 낼 여지가 구조적으로 작은" 시나리오임이
   더 분명해짐(required=false). 8% 기준의 시나리오별 적용 여부 결정 필요.
2. **incident +8.79%**: 기준(8%)을 턱걸이 통과 — 위상 plant에서 baseline이 상대적으로
   개선된 영향.
3. 기존 3범주 중 **심과포화 추적(oversat 300.5/incident 123.7)**과 **vsl 가드레일
   (medium/incident)**이 잔존 — 이전 라운드에 정리한 선택지 그대로 결정 대기.
