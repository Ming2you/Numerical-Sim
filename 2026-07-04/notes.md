# 2026-07-04 작업 노트 — B3 metering/VSL price 검증 + 7200s 사다리(과포화) 발견

## 0. 요약

- **핵심 방법론 발견**: 평가는 반드시 **7200s(과포화 포함)**로 해야 한다. 3600s는 혼잡 onset만 잡아
  leader와 green price의 실익을 통째로 숨긴다(step_ttt 280→678, 후반부가 진짜 과포화).
- **green price(B2)**: 3600s에선 노이즈(+6, 0.2%)로 보였으나 7200s에선 **실질 레버(−388, 3.0%,
  urban·freeway 동시 개선)**. B2 유지·강화 정당. default ON(코덱스 f18e920).
- **metering/VSL price(B3)**: 두 horizon 모두 **악화**(3600s +37, 7200s +436). 절벽(capacity drop)
  lever라 1차 price가 과방류. default OFF(코덱스 f18e920).
- **다음 방향**: 사용자 제안 — 목적함수를 TTT + freeway rho_crit **barrier penalty**로 나눠 각각의
  marginal price를 따로 하달. barrier gradient가 절벽을 1차로 예고 → 정상 방류는 price로 유도,
  과방류만 차단. price(유연)와 constraint(안전)의 통합(interior-point/soft-constraint 발상).

## 1. 코덱스 B3 vs 내 B3 시도 — 왜 코덱스가 이겼나(라고 오해했나)

사용자가 "코덱스는 개선이 강한데 7200s 차이냐 구현 차이냐" 질문. 코덱스 f18e920을 pull해 비교.
- **내 시도(로컬, 미커밋 → revert)**: N_UF 분기를 **우회**(autonomous, cap 없음) → 가격이 최대까지
  과방류 → 악화. 원인: bypass가 leader-follower N_UF 결합을 끊어 leader의 N_UF 탐색이 degenerate
  (N_UF=6000 과방류 선택) → soft penalty 참조점도 6000이라 무력.
- **코덱스**: N_UF hard equality → **ceiling(상한)**. `Σmeter ≤ ω_F·N_UF` 아래 좌표하강, priced 모드는
  ceiling을 soft로 완화 + budget penalty(w=T_c_h). follower가 N_UF를 상한으로 존중 → leader N_UF
  탐색이 살아있음. P1은 PSTACK-B3에서 끔.
- **결론(코덱스 코드 직접 실행)**: 3600s PSTACK-B3=3082 > B2-ON=3046(+1.2% 악화), 7200s
  PSTACK-B3=12838 > B2-ON=12402(+3.5% 악화). **코덱스 B3도 metering price는 B2보다 나쁘다.**
  코덱스의 "강한 개선"은 metering price가 아니라 전체 컨트롤러(분산 follower)의 no-control 대비였다.

## 2. 사다리 분해 (sweet_190, run_price_channel_experiments.py, 같은 harness)

| variant | 3600s total | 7200s total | 3600 u/f | 7200 u/f |
|---|---:|---:|---|---|
| NO-CONTROL | 5240.0 | — | 2934/2306 | — |
| PFO-PURE (분산 own-TTS, leader×) | 3176.2 | 13627.3 | 2630/546 | 12404/1223 |
| PFO-TAX-B3 (price만, leader×) | 3200.7 | — | 2590/610 | — |
| PSTACK-B2-OFF (leader, price×) | 3052.0 | 12789.7 | 2479/573 | 11326/1464 |
| PSTACK-B2-ON (+green price) | 3045.6 | 12401.8 | 2453/593 | 11113/1289 |
| PSTACK-B3 (+metering/vsl) | 3082.2 | 12838.0 | 2434/648 | 11483/1355 |

**증분 분해**:
| 증분 | 3600s | 7200s |
|---|---:|---:|
| 분산 follower (no-control→PFO-PURE) | −2064 (−39%) | (지배적) |
| leader (PFO-PURE→B2-OFF) | −124 (3.9%) | **−838 (6.1%)** |
| green price (B2-OFF→B2-ON) | −6 (0.2%) | **−388 (3.0%)** |
| metering/vsl price (B2-ON→B3) | **+37 (악화)** | **+436 (악화)** |

- **leader·green price 실익이 과포화(7200s)에서 크게 확대** — 3600s만 보면 과소평가(사용자 캐치).
  green price 7200s 분해: urban −212, freeway −175(둘 다 개선, 깨끗한 승리).
- **metering price는 과포화에서 더 악화** — 7200s urban +370, freeway +66(과방류 breakdown 역류).
- PFO-TAX-B3(3200.7) > PFO-PURE(3176.2): price를 leader ceiling 없이 주면 과방류로 오히려 나쁨.

## 3. metering price가 실패하는 이유 — 절벽(capacity drop) lever

- probe(2026-07-03): `d(전역TTT)/d(metering) < 0`(방류 이득)은 legacy operating point(방류 ~1500)의
  **국소 1차 기울기**. capacity drop 절벽(과방류 지점)은 그 접선에 안 나타남 → 1차 price가 절벽 너머로
  외삽 → 과방류 → freeway breakdown.
- urban/freeway 분해가 이를 실증: total만 보면 "무익"이나, 3600s는 urban −18(작은 이득)·freeway +55
  (breakdown 손해)의 **나쁜 트레이드오프**, 7200s는 breakdown이 ramp 역류로 urban까지 삼켜 둘 다 악화.
- **게임이론 관점**(사용자 논의): 완만 lever(green)는 Jacobi가 잘 수렴해 Nash≈social-opt → price 통함.
  절벽 lever(metering)는 강결합·비선형이라 Nash 수렴·품질 보증이 깨짐 → 분산 price로는 과방류.
  → 절벽 lever는 분산 price가 아니라 **중앙 constraint**로. leader 필요성의 게임이론적 근거.

## 4. 다음 실험 설계 — freeway barrier penalty의 marginal price (사용자 제안)

목적함수를 독립 3항으로: `J = TTT + w_f·barrier(freeway rho_crit 초과)` (+ 필요시 urban 항).
leader가 `g_TTT`(기존) + `g_fwy = d(barrier)/d(metering)`를 **따로 계산**해 metering price에 합산.
- barrier(예: `w_f·max(0, rho−rho_crit)²`)의 gradient는 밀도가 rho_crit 근처일수록 급증 → **1차 price가
  절벽을 예고**. 정상 구간엔 g_TTT만(방류 유인), 절벽 근처엔 g_fwy가 과방류 상쇄.
- 이는 hard constraint의 딜레마(정상 방류도 억제) 없이 절벽만 차단 — interior-point/soft state
  constraint의 marginal-price 실현. TTT를 쪼개는 게 아니라(그건 합=total로 동어반복) **TTT 밖 별도 항**의
  marginal을 추가하는 것이 핵심(사용자 통찰).
- **평가는 7200s(과포화)로** — 3600s는 leader/price 실익 은폐.

## 5. 코드 상태 (커밋 f18e920, 코덱스)
- StackelbergWuMeteredController: green_price_enabled=True(default), metering_price_enabled=False,
  vsl_price_enabled=False. → 실운영 P-Stack은 green만 ON(findings와 일치, 안전).
- work/run_price_channel_experiments.py: 사다리 러너(NO-CONTROL/PFO-PURE/PFO-TAX-B3/PSTACK-B2-*/B3).
- metering price 코드는 남기되 default OFF(negative finding 문서화, barrier 실험에 재사용).

## 6. TODO
- [ ] freeway rho_crit barrier penalty의 marginal price 구현(위 §4) — 7200s 평가.
- [ ] barrier 형태(quadratic vs exponential)·w_f 스윕.
- [ ] 안정되면 4-controller 풀 매트릭스 7200s(no-control/PFO/P-Stack/legacy) 재실행.
- [ ] (보류) 3점 사다리 정식 보고: 분산 follower가 지배적, leader·green price는 과포화서 실익.
