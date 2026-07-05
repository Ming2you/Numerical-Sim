# 2026-07-05 작업 노트 — B4 metering barrier 진단(w_f 스윕·부호·비볼록) + Codex 선형·urban판 합류

## 0. 요약

- **B4(구 제곱 barrier) 7200s 평가**(Claude 라인, sweet_190): barrier가 기본 w_f=1e-2에서 무력(B4=B3
  비트동일), w_f 키우면 **오히려 악화**. 원인 규명 → 단순 파라미터 문제 아님.
- **metering price 실패의 진짜 기전 = 상태 의존 비볼록(자기강화 나선)**. 부호 버그·urban 누락·d_own
  문제 전부 아님(아래 진단). green(볼록)은 price 통하고 metering(비볼록)은 안 통함 확정.
- **사용자 통찰 2건 → 설계 방향 확정**: (1) 제곱 barrier는 큰 초과 과대추정 → **선형이 맞음**(한계벌점
  상수 = Pigouvian 가격). (2) barrier는 hard constraint 아니라 **penalty**여야 함 — "어쩔 수 없이
  넘어야 좋은 국면"을 허용하려면. + urban 쪽에도 대칭 penalty 필요(freeway rho_crit만으론 한쪽 벽).
- **Codex(Fable5)가 병렬로 정확히 이걸 구현**(9683d4d): barrier 제곱→선형 hinge(veh·h 단위), urban
  spillback 항 추가. 제 metering 진단(과소방류·urban쪽 해악)도 독립 확인(a6a7750). **신규 선형+urban판
  7200s 평가는 미완** — 다음 과제.
- **Codex 신규 발견(중요)**: green price가 **regime 의존** — sweet_190 이득이나 sweet_155 7200s
  **+10.3% 해악**(3816d74). "3600s가 실익 은폐"가 양방향(이득·해악 모두 지평 비례 확대).

## 1. B4(구 제곱) 7200s w_f 스윕 (sweet_190, run_controller harness)

| variant | total | urban | freeway | Σmeter평균 | vs B2-ON |
|---|---:|---:|---:|---:|---:|
| B2-ON (green만) | 12891 | 11339 | 1552 | **4848** | — |
| B3 (+metering price) | 14581 | 12987 | 1594 | 3881 | +1690 |
| B4 w_f=1e-2(기본) | 14581 | 12987 | 1594 | 3881 | +1690 (=B3 비트동일) |
| B4 w_f=1e-1 | 14847 | 13205 | 1642 | 3782 | +1956 |
| B4 w_f=1e0 | 16233 | 14469 | 1764 | 3373 | +3342 |
| (참고) legacy 최적 | — | — | — | ~5668 | — |

- **핵심 반전**: metering price는 **과방류가 아니라 과소방류**로 실패. B2(green만)가 Σmeter=4848로 제일
  많이 방류·최선. metering price 켜면 3881로 **줄고** 나빠짐. barrier(방류 억제 방향)는 더 줄여 더 악화.
- Σmeter 4848→3881→3373: metering price·barrier가 방류를 계속 끌어내림 → urban 폭증(11339→14469).
- **당신이 우려한 "파라미터 문제"**: 기본 w_f는 맞음(너무 작아 무력). 그러나 키우면 악화 → sweet spot
  없음 → 파라미터 넘어선 문제.

## 2. 부호 진단 — 버그 아님, urban 누락 아님, 비볼록임

사용자 질문: "price가 −로 들어가야 하는데 +로 들어간 문제냐" / "urban price가 안 들어간 것 아니냐".

- **follower 적용 부호 정상**: `cost += g_ext·(meter−ref)` → g_ext<0 방류↑, >0 방류↓ (관례 맞음).
- **큰 양수 g_ext(+0.09)는 항상 ref=cap(1500) ramp에서만** — cap에서 유한차분이 후방차분(m_hi=cap).
- **urban은 이미 price에 지배적으로 담김**(직접 측정, legacy state step30, cap ramp R_F_E, meter 1500→1440):
  urban_ttt **+0.26**(줄이면 악화) vs freeway_ttt **−0.196**(줄이면 개선) → urban 기여가 더 큼.
  g_i(전역, urban포함) = −0.001 (방류 늘려, 정상 방향).
- **g_ext 계산도 state에 따라 옳음**: 같은 cap ramp, legacy state에서 d_own=+0.093, g_i=−0.001 →
  **g_ext=g_i−d_own=−0.094(음수=방류 늘려, 정상!)**. 그런데 B3 run의 자기(포화) state에선 g_ext=+0.09.
- **결론 = 상태 의존 비볼록 자기강화 나선**: metering price 계산 자체는 옳으나, closed-loop이 더 포화된
  나쁜 state로 흘러들면 그 지점 국소 gradient가 (그 state에선 옳게) "방류 줄여"라 하고 자기강화됨.
  B2(price 없음)는 follower 자율 own-TTS가 4848 고르고 머물러 robust. metering price가 그 좋은 자율
  선택을 **불안정화**한 것. → 사용자가 처음 Nash로 직감한 "이웃 best-response가 나쁜 basin에 갇힘".

## 3. penalty 형태 결정 (사용자 통찰)

- **penalty vs constraint**: penalty가 맞음. hard constraint("urban half-cap 절대 금지")는 "freeway
  breakdown 회피 위해 urban을 잠깐 넘는 게 전역 이득"인 국면을 봉쇄. penalty는 "넘으려면 그만한 이득을
  증명하라" → 정당한 초과 허용. (앞서 constraint 추천은 정정.)
- **제곱 vs 선형**: 제곱은 한계벌점 `2w·excess`가 초과에 비례 무한↑ → 큰 초과 **과대추정**, 정당한
  초과도 막음. 선형은 한계벌점 상수 `w` = "이득이 w보다 크면 넘김" = Pigouvian 가격 원의미. **선형이
  두 직감(과대추정 회피 + 정당초과 허용) 동시 충족**. 문턱 smooth가 필요하면 Huber(작을 땐 제곱, 크면
  선형 포화)로 fallback.
- Codex a6a7750 진단이 제곱의 실패를 정량화: ±60veh/h 섭동이 본선 밀도를 ±3대만 움직여 제곱 barrier
  차분이 g_TTT의 ~1/750로 소멸(단위 veh²·h). 선형(veh·h)으로 바꾸니 w=1이 1차정확·부활.

## 4. Codex 합류 상태 (9683d4d, a6a7750, 3816d74)

- **9683d4d**: barrier 제곱→**선형 hinge**(veh·h) + **urban spillback 항**(하류 링크 여유<0.2·cap 벌점 —
  half-cap excess의 dual). green·metering 두 채널 모두 적용. reservoir barrier는 양축 사멸이라 제외(P1
  담당). B2BAR 변형(green+barrier, sweet_155 폭발 처방 검증). 테스트 22/22.
- **a6a7750**: 구 제곱 B4 7200s inert 재확인 + B3 해악이 urban쪽(+237/+12)이라 freeway barrier는 과녁
  어긋남 규명(내 §2와 일치).
- **3816d74**: green price sweet_155 7200s **+10.3% 해악** → regime 의존 확정, default OFF.

## 5. TODO (다음)
- [x] **신규 선형+urban barrier(9683d4d) 7200s 평가** → §6(Claude): **전면 음성** — frac 0.2는
  regime 맞교환(155 +5.7%/190 +3.1%), frac 0.5(urban half-cap판)는 155 +14.4% 순수 악화.
  2026-07-04 notes §10 참조. barrier로 B2.1 풀기 마감.
- [ ] ~~선형이 안정 못 시키면 Huber로~~ → §6의 궤적 진단상 형태(shape) 문제가 아니라
  방향(runaway) 문제 — Huber도 같은 한계 예상, 보류.
- [ ] **B2.1(최우선)**: → §6에서 기전 확정. 다음 구현 = **trust region/proximal 앵커**.
- [x] metering marginal price negative 확정(비볼록) — constraint(N_UF ceiling)/자율 own-TTS 유지.

---

# 이하 Claude — barrier 판정 + B2.1 기전 확정(단조 폭주)

## 6. B2.1 기전 진단 — **진동이 아니라 단조 폭주(monotone runaway), §2 나선과 동일 족속**

sweet_155 7200s B2 런(outputs/_b2_ab_sweet155_7200)의 궤적 직독:

| step | price_C | green_C_p1 |
|---:|---:|---:|
| 0 | −0.022 | 56.0 |
| 6 | −0.118 | 62.0 |
| 14 | −0.165 | 62.0 |
| 28 | −0.240 | 68.0 |
| 36 | −0.270 | **86.0** |
| 38 | −0.357 | **92.0** |

- green_C가 56→92(상한 근처)로 **한 방향으로만** 표류, 가격은 refresh(재선형화)가 거의 매
  step 일어나는데도 **점점 더 세게 같은 방향**. 진동/limit-cycle 아님 → 감쇠(w<1)·EMA
  처방은 표류를 늦출 뿐 못 세움(우선순위 하향).
- **기전(§2의 metering 과소방류 나선과 통일)**: 가격은 매 지점에서 국소적으로 옳다
  (3-interval rollout상 C green↑이 horizon TTT↓) — 그러나 그 방향의 장기 비용은 horizon
  밖에서 청구되고, 다음 refresh가 더 강한 같은 방향 가격을 산출하는 자기강화.
  **sweet_190에선 이 표류 방향이 전역 최적(legacy C=80, B1 truth와 일치)과 우연히
  정렬**되어 이득(−3.4%), sweet_155에선 진짜 최적을 지나쳐 폭주(+10.3%). regime 판별자가
  정적 상태함수로 안 잡혔던 이유: 차이는 상태가 아니라 **표류 방향과 장기 최적의 정렬
  여부**다.
- **처방 재정렬 — trust region/proximal 앵커(다음 구현 1순위)**: 가격의 견인력을 자율
  (비가격) own-TTS argmin의 이웃으로 제한. 후보 구현: (a) 후보집합 제한 — priced argmin을
  |p1 − p1_autonomous| ≤ Δ(예: 후보 간격 1~2칸) 안에서만 허용, (b) proximal 항 —
  `+ κ·(p1 − p1_autonomous)²`를 가격과 함께 주입, (c) 가격 기여 상한 —
  |g_ext·(p1−ref)| ≤ ε·local_cost. (a)가 가장 단순·판별력 높음: 가격이 "한 칸씩만" 끌 수
  있으면 매 step 국소 검증을 통과해야 누적 표류가 가능 — 190의 정렬된 표류는 살아남고
  155의 비정렬 폭주는 plant가 되받아치는 즉시 멈출 것이 가설. 7200s 155/190 동시 검증 필수.

## 7. 결정적 진단 — 근시 아님, **선형 가격의 이웃 밖 월권**. trust region 구현(B2TR)

폭주 지점(sweet_155 B2 런 step 36, C_p1=86)을 기록 control로 replay해 전역 gradient를
horizon별로 직독:

| horizon | g_C (전역, FD 80..92) |
|---:|---:|
| 1 (3분) | −0.005 |
| **3 (9분, 가격이 쓰는 것)** | **+0.012 ("줄여라" — 옳음!)** |
| 6 (18분) | +0.106 |
| 9 (27분) | +0.272 |
| 12 (36분) | +0.532 |

- **전역 신호는 폭주 지점에서 이미 옳았다**(h=3에서 +0.012). horizon 근시 기각 — 연장은
  옳은 신호를 더 세게 할 뿐(±, 터미널 비용도 마찬가지로 보조적).
- 그런데 하달 가격은 −0.270이었다. 분해하면 g_ext = g_i − d_local = (+0.012) − (+0.282) =
  −0.270 — **두 큰 수의 차**. 이 분해는 측정 이웃(ref±6s) 안에서만 유효한데, 선형 가격은
  전체 후보 범위(±30s)에 걸린다. 이웃 밖(92)에서 국소 비용의 기울기가 +0.28보다 완만해지는
  순간 상수 가격 −0.27이 이겨 argmin을 끌어냄 — **폭주 = 선형 근사의 월권**. §6의 "국소적으로
  옳은 가격" 서사도 정정: 전역 gradient는 옳았고, 가격 적용 방식이 그것을 배반한 것.
- **구현(B2TR)**: follower `signal_marginal_price_trust_sec` — 가격 활성 시
  |p1 − p1_ref| ≤ trust(기본 δ=6s, 가격을 측정한 바로 그 이웃) 후보만 탐색(이웃 안 후보
  전무 시 전체 fallback). 컨트롤러 `signal_price_trust_sec`(기본 None=구 -B2 재현),
  러너 `P-STACK-WU-FAITHFUL-B2TR`. 원리: 가격은 측정된 구간 안에서만 유효 — 정렬된 개선은
  refresh마다 한 이웃씩 plant 검증을 통과하며 누적(190: 56→80은 4~5 refresh면 충분),
  비정렬 표류는 전역 신호가 반전되는 즉시 정지. 테스트 21/21(거대 가격도 trust 밖으로 못
  끌어냄 판별 포함).
- 7200s 판정(sweet_155: 폭발 제거 여부 / sweet_190: −3.4% 보존 여부) 진행.

## 8. B2TR 7200s 판정 — **양 regime 동시 승리, STOP 기준 첫 통과**

| 7200s | sweet_155 | sweet_190 |
|---|---:|---:|
| 가격 OFF | 4419.7 | 12846.6 |
| B2(무제한) | 4873.7(+10.3%) | 12409.5(−3.40%) |
| **B2TR** | **4391.8(−0.63%)** | **12523.0(−2.52%)** |

- sweet_155 **부호 반전**(+10.3%→−0.63%) — 게이트(P1.5 포화도)·크기 문턱·barrier(0.2/0.5)가
  전부 실패한 중부하에서 가격 채널이 처음으로 기준선을 이김. §7 진단(선형 월권)의 실증.
- sweet_190 이득 **74% 보존**(−2.52%) — trust ±6s/refresh 로도 정렬된 표류(56→80)가 누적
  도달. 부수: 후보 축소로 solve 84s(무제한 94s)로 더 쌈.
- **모든 가격 구성 중 최초로 STOP 기준(>1% 악화 금지) 통과.** 남은 실사: sweet_128 7200s
  (OFF 기준선 포함) → 통과 시 signal_price(+trust) **기본 ON 승격** 결정.
- 개념 정리: trust region은 "leader 가격 = 방향 제안, plant = 매 refresh 검증자"로 역할을
  재배치한 것 — 분산 가격의 안전한 사용 조건(측정 이웃 내 유효)을 명시한 첫 구성.

## 9. sweet_128 실사 통과 → **green 가격+trust 기본 ON 승격**

sweet_128 7200s(`outputs/_b2tr_sweet128_7200/`): OFF 1561.193 → B2TR **1530.360 (−1.98%)**.

| 7200s | sweet_128 | sweet_155 | sweet_190 |
|---|---:|---:|---:|
| B2TR vs OFF | **−1.98%** | **−0.63%** | **−2.52%** |

- **3개 regime 전부 개선 + 연산 절감(후보 축소)** — STOP 관례를 완전 충족하는 최초의 가격
  구성. `signal_price_enabled=True` + `signal_price_trust_sec=6.0(=δ)`을 P-Stack **기본값**
  으로 승격(러너 `P-STACK-WU-FAITHFUL` = 구 B2TR). 무제한 가격은 `-B2` 변형으로 강등
  (155 폭주 재현/비교용). 테스트 30/30.
- legacy 격차(sweet_190): B2TR 12523.0 → 1794.2 잔존. 무제한 B2(12409.5, 격차 1680.8)가
  190 특화로는 더 좋으나 155 폭주 리스크 — 기본값은 robust한 B2TR, 무제한은 opt-in.
- **다음 방향**: (a) trust 반경 스윕(6→9/12: 190 이득 회수 vs 155 안전 트레이드오프 지도),
  (b) metering price도 trust 걸고 재평가(비볼록 나선도 같은 월권 족속일 가능성 — §2 나선의
  Σmeter 표류도 이웃 제한이면 멈출 수 있음), (c) 남은 legacy 격차 1794의 재료(offset 등
  coordinated 레버) 탐색 재개.

---

## 10. 종합 정리 — 가격 채널 아크(B1→B2TR) 완결 보고

### 10a. 아크 타임라인 (probe → 구현 → 실패 → 진단 → 처방 → 승격)

| 단계 | 내용 | 판정 |
|---|---|---|
| B1 (07-03) | per-signal externality 가격이 offline probe에서 argmin을 truth로 이동 | 양성(ext 9/15) |
| B2 (07-03~04) | green 가격 production(동결 운영점 g_ext, hold+event-trigger) | 190 −3.4%, **155 +10.3% 폭주** |
| B3 (07-04) | metering/VSL 가격 확장 | 음성(과소방류 나선, +2.0%) |
| B4 제곱 barrier (07-04) | rho_crit 초과² 가격 | 무력(gradient 소멸 1/750) |
| B4 선형+urban (07-05) | 선형 hinge·veh·h + spillback 항(사용자 교정 2건) | probe 부활, closed-loop 음성(regime 맞교환) |
| **B2.1 진단 (07-05 §7)** | 폭주점 replay: 전역 g는 옳았음(+0.012) — 원인 = 선형 가격의 측정 이웃 밖 월권 | 기전 확정 |
| **B2TR (07-05 §8-9)** | trust region: \|p1−ref\| ≤ δ(6s) 후보만 가격 대상 | **3 regime 전부 개선, 기본 ON 승격** |

### 10b. 최종 스코어보드 (7200s, 이 머신, OFF 대비)

| | sweet_128(경) | sweet_155(중) | sweet_190(고) |
|---|---:|---:|---:|
| OFF 기준선 | 1561.2 | 4419.7 | 12846.6 |
| B2 무제한 | (+0.4%\*) | +10.3% | −3.40% |
| **B2TR(기본값)** | **−1.98%** | **−0.63%** | **−2.52%** |
| legacy 격차(190) | | | B2TR 1794 / B2 1681 (legacy 10728.8) |

\* 128은 3600s 측정. 무제한 B2는 190 특화 opt-in(`-B2`)으로 존치.

### 10c. 현재 코드 상태 (3cad304)

- **기본값**: `StackelbergWuMeteredController` — `signal_price_enabled=True`,
  `signal_price_trust_sec=6.0`(=δ). metering/VSL/barrier 가격 전부 기본 OFF(음성 판정).
- 가격 API(전 채널 공통): leader가 refresh(최초/cadence/event-trigger)마다 **같은 동결
  운영점**에서 g_i·d_local을 계산해 g_ext 완성·하달, follower는 선형 가격항 + trust 제한.
- 러너 변형: `-B2`(무제한)/`-NOB2`(OFF)/`-B3`/`-B4`/`-B2BAR(50)`/`-B2TR`(=현 기본과 동일)
  /`-NUFCAP`/`-STANDALONE(-NUFCAP)`/PFO 계열 `-NOP1`/`-P15SAT`/`-P15AUTO`.
- 테스트 30/30(+2 skip: legacy trace 머신 전용 anchor).

### 10d. 방법론 교훈 (이 아크에서 두 번 검증된 것)

1. **평가는 7200s(과포화)** — 3600s는 이득·해악 모두 은폐(155 해악 +1.66%→+10.3%).
2. **probe(open-loop)는 필요조건일 뿐** — barrier는 probe 부활 후 closed-loop에서 배반.
   반대로 closed-loop 실패도 한 점 진단(궤적 직독 + replay FD)이면 원리적 처방으로 이어짐.
3. **유한차분 가격은 측정 이웃에서만 유효** — g_ext가 두 큰 수의 차일 때 특히. trust
   region은 이 원리의 최소 구현이며, "leader=방향 제안, plant=매 refresh 검증자"로
   역할을 재배치한다.
4. regime 판별자를 정적 상태함수에서 찾는 시도는 3연속 실패(P1.5 포화도·가격 크기·barrier)
   — 차이는 상태가 아니라 **표류 방향과 장기 최적의 정렬 여부**였다.

### 10e. 다음 세션 우선순위 (§11에서 2번 항목 해소됨)

1. trust 반경 스윕(6/9/12) — 190 이득 회수 vs 155 안전 지도.
2. **metering price + trust 재평가** — §2 과소방류 나선도 월권 족속이면 부활 가능
   (성공 시 N_UF 스칼라 대역폭 문제의 가격 해법이 다시 열림).
3. legacy 잔존 격차(~1700-1800): offset 등 coordinated 레버 — 가격으로 안 닫힌 몫.
4. (보류 항목 정리) VSL 가격 g_ext화, P1.5 재검토는 우선순위 하위 유지.

## 11. B3TR(metering 가격+trust) — **최종 음성, metering 가격 채널 사망 확정**

metering에 trust를 적용한 두 번의 7200s sweet_190 판정(둘 다 실패, 서로 다른 기전):

| 시도 | total | Σmeter 평균 | freeway TTT | 기전 |
|---|---:|---:|---:|---|
| B3TR v1 (trust 0.25·cap) | 24910.5 | 6000(동결) | — | **동결 사고**: 반경 0.25 < 첫 격자 간격 0.3 → ref=cap에서 창 안에 자기 자신뿐(수정: 최근접 이웃 이동성 보장, 1219500) |
| B3TR v2 (이동성 수정) | 19078.1 | 5378(과방류) | **5613.9(붕괴)** | **비가역 절벽**: 한 칸씩 탐색 중 capacity drop을 넘음 — 신호가 반전돼도 190 수요에선 본선 미회복 |
| (비교) B2TR | 12523.0 | ~4848 | ~1460 | green만 가격 |

- **왜 trust가 green에선 통하고 metering에선 안 통하나**: trust의 전제는 "한 칸의 오류는
  가역적"(다음 refresh에서 전역 신호 반전 → 회귀). green의 오류는 큐로 쌓였다 풀리지만,
  metering의 절벽(capacity drop)은 **비가역**(2026-06-26 "과포화 비가역"과 동일) — 넘는
  순간 사후 검증으로는 못 돌아온다. **탐색 자체가 위험한 레버에는 plant-in-the-loop
  검증도 무력**(검증이 사후적이므로).
- **최종 처분**: metering marginal price는 동결/과소방류(Codex §2)/과방류-붕괴(v2) 세 모드
  전부 실패 — **아카이브**(코드 보존, 기본 OFF, 재도전 시 "절벽을 넘지 않는 제약"과 결합
  필요). metering 조정은 N_UF ceiling/equality + 자율 own-TTS(P1) 유지.
- **레버 분류 원리(3중 확인 완성)**: 완만·가역 레버(green) = 분산 가격+trust 적합 /
  절벽·비가역 레버(metering) = 중앙 constraint + 자율. Codex의 게임이론 결론(§3,
  2026-07-04)에 제어이론적 근거(비가역 전이 앞 탐색 불가) 추가.
- **확정 기본 구성 = B2TR**(green 가격+trust 6s): 3 regime 전부 개선(§9). 이 아크 종료.
- trust 설계 교훈: 반경과 격자가 안 맞으면 월권 방지가 아니라 **동결**이 된다 — 이동성
  보장(최근접 이웃 포함)은 trust region의 필수 요소.

## 12. B3CERT(비대칭 안전 증명서) — 실패, 그러나 **통일 이론의 마침표**

사용자의 통일성 요구("metering도 가격으로")에 대한 마지막 시도(8c3d29c): 조임(가역)은
trust로 자유, 풂(비가역 절벽 방향)은 leader의 +δ rollout 예측밀도 < ρ_crit·0.9일 때만
인증. CBF/safety-filter 구조, 추가 rollout 0회.

**결과(sweet_190 7200s)**: 19074.6 ≈ B3TR v2(19078.1). freeway 5607(여전히 breakdown),
Σmeter 5411. **증명서는 완벽 작동**(40 refresh 인증 0건, 상향 0회) — 그런데도 동일 붕괴.

**진단 정정(§11을 다시 뒤집음)**: v2의 실패는 "위로 걸어가서"가 아니라 **cap 시작점에서
조이지 못해서**였다. B3CERT가 그걸 드러냄: (i) 조임의 가치 = 미래 breakdown 회피 =
절벽 너머 반사실 — **1차 gradient에는 양방향 모두 안 보인다**(풀면 좋아 보이고, 조여도
좋아지는 게 안 보임). (ii) 그래서 가격은 절벽 앞에서 "방류 이득"을 외치며 자율/budget의
조임 유인을 상쇄하고, (iii) 증명서는 거부권만 있지 조임을 만들지 못한다.

**정리(이 아크의 이론적 결론)**: *절벽 레버에서 안전 증명서를 단 1차 가격 체계는 제약
체계로 퇴화한다* — 앵커를 추가해도 시스템은 앵커(=제약 해)에 고정되고 가격은 잉여가
된다(상향은 증명서가 거부, 하향은 가격이 상쇄). 즉 가격이 제약 대비 더할 수 있는 것이
구조적으로 없다. **통일 서사 완성**: 모든 레버는 일반화 가격으로 조정된다; 완만·가역
레버의 일반화 가격 = 1차 가격 + trust(B2TR), 절벽·비가역 레버의 일반화 가격 = 그
퇴화 극한인 제약(N_UF ceiling) — 중간 형태(증명서 가격)는 제약으로 수렴함을 실험으로
확인(Weitzman 가격-수량 경계의 폐쇄).

**처분**: B3CERT 코드 보존(기본 OFF, cert 인프라는 향후 다른 안전-임계 레버에 재사용
가능). metering 조정 최종 확정 = N_UF ceiling/equality + 자율 own-TTS(P1). 배포 구성
B2TR 불변. 가격 채널 아크 완전 종결.
