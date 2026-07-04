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
- [x] freeway rho_crit barrier penalty의 marginal price 구현(위 §4) — §7(B4). 7200s 평가 진행.
- [ ] barrier 형태(quadratic vs exponential)·w_f 스윕.
- [ ] 안정되면 4-controller 풀 매트릭스 7200s(no-control/PFO/P-Stack/legacy) 재실행.
- [ ] (보류) 3점 사다리 정식 보고: 분산 follower가 지배적, leader·green price는 과포화서 실익.

---

# 이하 Claude 세션(병합·포팅) — B2 API 통일 + B3 포팅 + B4 구현

## 7. B2 병렬구현 정리 + B3 포팅(f18e920→signal_marginal_price 흐름) + B4

- **B2 API 확정**: 같은 머신·같은 기준 A/B(2026-07-03 notes §12)에 따라 `signal_marginal_price`
  구현(31173ea)을 canonical로 채택. eed5c51의 green_price·f18e920의 B3는 이 API로 포팅.
- **B3 포팅에서 흐름 통일**(이 병합의 핵심 변경):
  - **기울기 평가점**: g_i(전역)·d_local(국소) 모두 leader가 refresh 시점의 **같은 동결
    운영점(previous)**에서 계산해 g_ext를 완성·하달. Codex 원안은 g_i를 commit점에서,
    d_local을 Jacobi 라운드마다 움직이는 snapshot점에서 빼는 혼합이었고(solve당 rollout
    2회/ramp 추가 비용), 그 혼합이 같은 머신 A/B에서 green price 효과 소멸(+0.03% vs
    −1.84%)의 유력 원인으로 지목됐다(§12).
  - **갱신**: 매 decide 재계산·폐기 → hold + event-trigger(green 3s / metering 30 veh/h /
    VSL 5 km/h 이동 시 재선형화) + 기존 cadence.
  - **d_local 계산**: follower 신설 `local_metering_costs()`(local_green_costs와 동일 규약 —
    프롤로그 1회, 가격 일시비활성, 영속상태 미변경)를 leader가 refresh당 1회 호출.
  - **N_UF**: metering 가격 활성 시 hard budget → soft |Σ−budget|(w=T_c_h) + 자율 후보
    sweep(Codex soft-budget 설계 유지). 가격 비활성 시엔 기존 config 게이트
    (`wu_faithful_nuf_coordination_mode`: equality 기본/cap opt-in) 그대로.
  - **VSL**: raw g_i 그대로(국소 고정-VSL 채점 프리미티브 부재로 d_local 미차감 — Codex
    원안 유지). 기본 OFF이며 활성화 전 g_ext화가 선행 과제.
- **B4 구현**(§4 사용자 제안): `barrier_price_enabled` 시 metering 유한차분의 **같은 rollout
  상태**에서 barrier = Σ w_f·(max(0,ρ−ρ_crit)·L_seg·lanes)²·T_c_h를 함께 계산(추가 rollout
  0회), g_ext += Δbarrier/Δx. barrier는 leader 전용 목적항이라 d_local 차감 없음. w_f 기본
  1e-2(스윕 대상). 러너 변형 `P-STACK-WU-FAITHFUL-B3`/`-B4`, price_channel 러너에 `PSTACK-B4`.
- 검증: 신규 `src/tests/test_b3_b4_price_channels.py` 5건(가격 0=비트동일, 부호→방류 반응,
  d_local 가격격리, barrier 0/양수, B4 refresh가 metering 가격을 위로 밈) 포함 전체 29/29
  PASS. 테스트 설계 주의: 기본 수요에선 rho_crit+20 초기밀도도 한 interval에 임계 아래로
  배수(9~23) — barrier 테스트는 지속 과수요(fw/ramp ×4)+ρ_c+40이 필요했다.
- B4 스모크(sweet_190 720s): 정상 작동, solve +50s/step(metering 유한차분 몫).
- **주의(기본값 차이)**: green price는 Codex default ON이었으나 이 라인에선 **기본 OFF 유지**
  (sweet_155 3600s +1.66% STOP, 2026-07-03 §12b). 단 §0의 "3600s가 실익을 은폐" 발견이 이
  STOP 판정에도 적용될 수 있어 sweet_155 **7200s** A/B로 재검 중 — 결과에 따라 기본값 재결정.

## 8. sweet_155 7200s B2 A/B — **STOP 확정, 중부하 해악은 지평 비례로 폭발**

`outputs/_b2_ab_sweet155_7200/`: B2 OFF **4419.748** vs B2 ON **4873.692** = **+10.3% 악화**
(완료 차량 32757.9→31495.1, 터미널 잔존 +1261).

- §0의 "3600s가 실익을 은폐"는 **양방향**이었다: sweet_190 이득이 지평 비례로 커지듯
  (−1.84%→−3.40%), sweet_155 해악은 +1.66%→**+10.3%**로 ~6배 폭발. 잘못된 가격 → 큐 적체 →
  운영점 이동 → 재선형화된 가격이 더 오염되는 복리 loop로 추정(진단 필요).
- **함의**: (a) green price 기본 OFF는 확정(성급이 아니라 필수) — **Codex 라인의 default
  ON은 중부하 시나리오에서 위험**, 이 노트로 정정 공유. (b) **B2.1(중부하 해악 기전 규명 +
  regime 판별자)이 최우선 미해결 문제로 승격** — 이것 없이는 가격 채널(green이든 B4든)을
  실운영 기본값으로 못 켠다. (c) B4 평가 해석도 sweet_190 단독이 아니라 sweet_155 교차검증을
  반드시 동반할 것.

## 9. B4/B3 7200s 평가 — **B4 무력(inert), 기전 규명 완료**

결과(`outputs/_b4_sweet190_7200/`, `_b4_sweet155_7200/`; 비교기준 §8·2026-07-03 §12b):

| 7200s | sweet_190 | sweet_155 |
|---|---:|---:|
| P-Stack(가격 OFF) | 12846.6 | **4419.7** |
| B2(green) | **12409.5** | 4873.7(+10.3%) |
| B3(+metering TTT price, 이 포팅) | 12658.7(B2 대비 **+2.0%**) | — |
| B4(+rho_crit barrier) | 12658.7(**B3와 비트 동일**) | 4887.7(+10.6%) |

- **B3 음성 재확인**: 포팅판(+2.0%)이 Codex 원안 측정(+3.5%, 자기 머신)보다는 덜 나쁘지만
  여전히 음성. 해악 분해 urban +237 / freeway +12(B2 대비) — **이 망에서 metering 가격의
  해악은 본선 breakdown이 아니라 urban 쪽**. 본선은 max ρ 41.8(>ρ_c 33.5)·최저 42.9 kph로
  임계를 넘긴 하나 얕게 넘는다.
- **B4 무력의 기전**(scratchpad probe, ρ=ρ_c+8·혼잡기 수요 운영점): barrier가 metering
  가격에 더하는 몫이 w_f=1에서도 g_TTT의 **~1/750**(1.3e-4 vs 9.8e-2). metering ±60 veh/h
  섭동이 9분 horizon 본선 밀도를 ±3대분밖에 못 움직여 제곱 barrier의 유한차분이 소멸 —
  §4의 "barrier gradient가 절벽을 1차 예고" 전제가 **이 전달 경로(metering 유한차분)에선
  수치적으로 불성립**. w_f를 ~10⁴로 올리면 그냥 둔탁한 페널티가 된다(가격이 아님).
- **처분**: B4 코드는 보존(기본 OFF), metering/VSL/barrier 가격 전부 opt-in 유지.
- **수렴 결론**: green(중부하 +10.3%)·metering(+2.0%)·barrier(무력) — 가격 채널들이 같은
  부류의 벽에 부딪힌다. 채널 추가(B5…)보다 **B2.1(닫힌 루프에서 1차 가격의 복리 피드백
  기전 + regime 판별자)**이 선행 과제. §3의 게임이론 결론(절벽/강결합 레버는 분산 가격이
  아니라 중앙 constraint)이 강화됨 — barrier도 가격으로 하달하는 순간 같은 한계를 공유한다.
- 부수 수정: 러너 진단 수집 필터에 wu_b3_/wu_b4_ 추가(이번 런들은 metering 가격 미로깅 —
  비트동일 판정은 궤적 완전일치로 대체 확인).
