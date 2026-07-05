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
- [ ] **신규 선형+urban barrier(9683d4d) 7200s 평가** — sweet_190(과소방류 나선을 urban barrier가 막아
  B2로 회복하는지) + **sweet_155**(green+barrier=B2BAR가 +10.3% 폭발을 잡는지). w 스윕.
- [ ] 선형이 안정 못 시키면 **Huber**로.
- [ ] **B2.1(최우선)**: green price의 regime 의존 기전 + regime 판별자 — 왜 sweet_190 이득/sweet_155
  해악인지. 1차 가격의 닫힌루프 복리 피드백(§2 비볼록 나선과 동류일 가능성).
- [ ] metering marginal price는 negative 확정(비볼록) — constraint(N_UF ceiling)/자율 own-TTS 유지.
