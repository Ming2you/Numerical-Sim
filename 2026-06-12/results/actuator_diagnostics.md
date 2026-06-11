# 액추에이터 동작 진단 — VSL / ramp metering / offset / green (풀 7200s ×5 시나리오)

생성: `scripts/plot_actuator_diagnostics.py` (run 출력 CSV → SVG, 의존성 없음).
그래프: `2026-06-12/results/actuator_plots/<scenario>_{vsl_FW_W, vsl_FW_E, metering, offsets, offset_progression, green_p1_fraction}.svg`
(scenario = low / medium / peak / incident / oversat)

## 1. VSL — 혼잡에 단조 반응, 올바르게 구현됨 ✓

| 시나리오 | VSL 활성 interval (40 중) | 활성 시 평균 밀도비 | 비활성 시 | 명령 분포 |
|---|---|---|---|---|
| low | 0 | — | 0.60 이하 | {100} |
| medium | 4 | — | — | {80,100} |
| peak | 14 | 0.752 | 0.708 | {80,100} |
| incident | 14 | 0.801 | 0.685 | {60,80,100} |
| oversat | 28 | 0.833 | 0.738 | {60,80,100} |

- 활성 빈도가 혼잡 수위에 정확히 단조(0→4→14→14→28).
- 활성/비활성 구간의 밀도비가 모든 시나리오에서 분리(활성 쪽이 높음) — `_agent_vsl`의
  임계 로직(비>0.95→80, >1.05 또는 lane_loss→60)이 의도대로 동작.
- 명령 깊이도 혼잡 깊이에 비례: peak는 80까지만, incident/oversat은 60까지 강하.
- incident에서 밀도비 피크 1.016(>1) — capacity drop(0.72×) 시 VSL이 실제로 개입.
- 주의: 그래프의 밀도는 링크 평균이라 segment 단위 초과(merge cell)는 과소표시 —
  `density_exceedance` 카운트와 함께 볼 것.

## 2. Ramp metering — "명령 < 용량"과 "실효 구속"의 구분이 핵심 ✓

| 시나리오 | 명령 평균 [veh/h] | N_UF 평균 | w_r 평균/최대 [veh] | x_on 평균/종료 [veh] |
|---|---|---|---|---|
| low | 4,963 | 5,407 | 8.7 / 39.6 | 30 / 29 |
| medium | 5,291 | 5,614 | 10.0 / 38.0 | 838 / 1,623 |
| peak | 4,859 | 5,173 | 9.5 / 38.9 | 1,972 / 3,892 |
| incident | 5,011 | 5,292 | 9.8 / 38.2 | 1,871 / 3,641 |
| oversat | **3,172** | **3,315** | 10.7 / 41.0 | 3,968 / 7,845 |

- 명령이 용량(6,000) 아래인 interval은 37~40/40으로 흔하지만, **실효 구속 판별 기준은
  w_r**이다. low~incident에서 w_r 평균 9~10대(즉시 배수) → metering은 수요 제한 상태로
  사실상 비구속(자유류 개방 의도대로) ✓.
- oversat에서만 명령이 3,172로 실제 제한 → w_r은 여전히 배수(10.7)되면서 적체가
  x_on(평균 3,968)으로 후퇴 — 본선을 막지 않고 상류에 적체를 세움. 결과 freeway TTT
  3,632→335(baseline 대비 10배 방어). **coordinated perimeter+metering의 교과서적 동작.**
- 명령이 N_UF_star를 정확히 추적(전 시나리오 명령≈NUF−차이는 agent의 물리 상한 투영분).

## 3. Offset — 두 가지 문제 확정 (★ 액션 필요)

### (a) plant에 offset이 반영되지 않음 (검증 불가능)
`urban_substep`은 phase별 green fraction만 사용하고 cycle 내 위상(offset)이 동역학에
들어가지 않는다(`grep offset src/models src/simulation` — 직렬화·복사뿐). 즉 **offset이
어떤 값이든 시뮬레이션 결과가 동일**하며, "offset이 잘 맞춰지는지"는 현 plant에서
원리적으로 검증 불가. offset 게이트(범위/smoothness)는 형식 검증일 뿐이고
`corridor_delay_change`는 urban TTT 차이를 그대로 쓰는 proxy다.

### (b) 휴리스틱 자체도 결함 (round-4 이슈 ③ 데이터로 확정)
- 측정: Δoffset(A→B) 평균 41~50s, Δoffset(B→C) 38~46s (전 시나리오, `*_offset_progression.svg`).
- 모델 정합 이상값: 인접 링크 1.32km(저장 220대×6m) @ urban 50km/h = **95s**.
- 측정값 ≈ `_offsets`의 "1km @ freeway 평균속도(75~80km/h) ≈ 45~48s" — **도시 진행시간이
  아니라 freeway 속도로 계산**되고 있음. 또 [A,B,C,D,F] enumerate 순서를 선형 corridor로
  가정하나 D·F는 하단 행(공간적 인접 아님).
- offset이 plant에 무효라 TTT 피해는 0이지만, smoothness 게이트·제어 벡터에 노이즈만 추가.

### 권고 (연구자 결정)
1. **(권장) 현 단계에서 offset을 control/acceptance에서 제외** — plant가 위상을 모델링하지
   않는 한 어떤 offset 정책도 검증 불가(무의미 변수 제거).
2. 또는 spillback-aware proposal §2.2(PSO 직접 phase green + offset 별도 단계) 라운드에서
   plant에 cycle 위상(플래툰 도착-green 정렬) 모델을 추가한 뒤, 그때 urban 속도·실제 인접
   기반으로 휴리스틱을 재작성.

## 4. Green split — 실제로 일하는 신호 변수 ✓
`*_green_p1_fraction.svg`: 신호별 p1(NS) 비율이 0.5 고정이 아니라 큐 압력·allocation
밴드에 따라 시나리오·시간별로 움직임(D/F는 off-ramp 방출 floor 0.35 반영). 신호 제어의
실효 채널은 green split + movement별 allocation cap이고, offset은 (a)에 따라 무효.
