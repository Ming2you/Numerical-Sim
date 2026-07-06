# 가격 채널 연구 아크 종합 레포트 (B1 → B2TR → B3/B4/CERT → 이론 → F1)

작성: 2026-07-06, Claude (근거: 2026-07-03 notes §4~§12, 2026-07-04 notes §0~§9,
2026-07-05 notes §1~§14, 결과 사본 각 날짜 results/)

## 1. 한 문단 요약

leader가 전역 rollout으로 계산한 marginal price를 follower 목적함수에 내려보내는 조정
채널을 probe(B1)→production(B2)→확장(B3/B4)으로 전개한 결과: **green(완만·가역 레버)
가격은 trust region과 결합해 3개 수요 regime 전부에서 개선**(B2TR, 현 기본값)됐고,
**metering(절벽·비가역 레버) 가격은 게인·차수·barrier·안전증명서 어떤 보강으로도 실패**
했다. 실패의 기전을 3개 층위에서 규명했고(미분의 3국면 붕괴 / 권한-안전 분리 / 누적
인과의 한계기여 소실), 그 결과 "어떤 레버에 어떤 조정 수단을 쓸 것인가"가 임의 선택이
아니라 **레버의 가역성에서 도출되는 정리**로 정리됐다. 다음 단계(F1)는 안전 페널티를
follower 목적함수로 이관해 절벽 정보가 미분을 통과하지 않게 하는 아키텍처다.

## 2. 최종 스코어보드 (7200s, 동일 머신, P-Stack 가격 OFF 대비)

| 구성 | sweet_128(경) | sweet_155(중) | sweet_190(고) | 판정 |
|---|---:|---:|---:|---|
| B2 무제한 green 가격 | (+0.4%, 3600s) | **+10.3% 폭주** | −3.40% | 155 STOP |
| B2BAR(+spillback barrier 0.2) | — | +5.7% | +3.1% | regime 맞교환 |
| B2BAR50(0.5cap barrier) | — | +14.4% | — | 순수 악화 |
| **B2TR(green 가격+trust) — 현 기본값** | **−1.98%** | **−0.63%** | **−2.52%** | **전 regime 개선** |
| B3(+metering 가격) | — | — | +2.0%(vs B2) | 과소방류 나선 |
| B3TR(+trust) | — | — | 붕괴(19078) | 동결→과방류 |
| B3CERT(+안전증명서) | — | — | 붕괴(19075) | cert 무력(§14 정정) |
| B4(+ρ_crit barrier 가격) | — | — | =B3 비트동일 | gradient 소멸 |

절대값 기준(sweet_190 7200s): legacy P-Stack 10728.8 ≫ **B2TR 12523.0** > 가격 OFF
12846.6 > PFO+P1 12885.7. legacy 잔존 격차 ~1794(가격으로 안 닫히는 몫).

## 3. 세 가지 이론 결과

### 3.1 정리 — 절벽 레버에서 가격은 제약으로 퇴화한다 (07-05 §12)

절벽(capacity drop, 비가역) 레버에서 유한 차수 국소 가격 체계는 — 게인(w)·차수(2차)·
barrier·안전증명서 어떤 보강을 얹어도 — 제약 체계와 같은 행동으로 수렴하며, 가격
성분의 제약 대비 한계 기여는 0이다. 근거: 게인은 정보가 아니라 이득(w·0=0, 쓰레기도
w배); 차수는 같은 9분·±δ 반사실의 급수 전개일 뿐(절벽 도달시각을 ~10초 이동시키는
섭동에 모든 차수가 비례); barrier의 미분도 같은 한계.

### 3.2 실증 — 미분의 3국면 붕괴 (07-05 §13, B3CERT 시계열 직독)

receding horizon은 절벽을 창 안에 넣는다(사용자 반론이 옳았음). 문제는 미분의 언어:

| 국면 | ρ | 측정된 가격 | 상태 |
|---|---|---|---|
| 절벽 전 | 25→31 | +0.01~+0.05 (옳으나 약함) | 30분 누적 반사실이 9분 ±δ에 압축 |
| 경계 | 39→53 | **−0.447 (역방향!)** | 불연속 가로지르는 secant의 부호 붕괴 |
| 절벽 후 | 88→92 | **정확히 0 영구** | jam에서 metering non-binding — 섭동 무효 |

"창이 못 보는 것"이 아니라 "**보는 순간 미분이 무의미해지는 것**". 누적 인과(끓는
개구리)에서 각 결정의 한계 기여는 거의 0이고 마지막 한 방울만 무한대 — 미분(한계
기여의 언어)이 원리적으로 담지 못하는 인과 구조.

### 3.3 원리 — 안전은 권한을 따라 이사해야 한다 (07-06 §14)

leader objective의 페널티(N_P_crit·density)는 **등식 budget이 연결돼 있을 때는 실제로
breakdown을 막고 있었다**(B2TR onset기: N_UF 4500~4800 하향 → metering 750~1050 추종).
가격 모드가 budget을 soft로 풀자 어떤 N_UF 후보든 follower 응답이 같아져 후보 차등이
소실 — 페널티는 눈이 아니라 손을 잃었다. **안전 페널티는 결정이 실제로 내려지는 곳에
붙어야만 작동한다.**

## 4. 레버 분류 (이 아크의 실용 산출물)

| 레버 성질 | 조정 수단 | 검증 |
|---|---|---|
| 완만·가역 (green) | 분산 1차 가격 + trust region(측정 이웃 내 유효) | B2TR 3 regime 개선 |
| 절벽·비가역 (metering) | 중앙 제약(N_UF equality/ceiling) + 자율 own-TTS(P1) | 가격 3모드 전부 실패 |
| 미분류 (offset, VSL) | offset=leader-coordinated 레버로 보존(F3 후보), VSL=가격 opt-in(d_local 미차감 미해결) | — |

경제학 대응: Weitzman(1974) prices-vs-quantities의 경계를 경험적으로 도출 + 경계
중간형(증명서 가격)이 수량 쪽으로 수렴함을 실험으로 확인.

### 4.1 보강 해석 — 스칼라 가격이 아니라 결합 레버 단위의 response가 필요하다

위 분류는 "metering은 반드시 hard constraint여야 한다"는 뜻이 아니다. legacy 계열이 잘했던
것은 `rho_crit`을 절대 넘지 못하게 막은 것이 아니라, **RM/VSL/green/offset이 결합된 후보를
통째로 rollout**해 일시적 밀도 초과와 queue relief, throughput 증가의 교환을 평가했다는 점에
가깝다. 따라서 F2의 음성 판정은 metering 자체가 price에 부적합하다는 최종 명제라기보다,
**per-ramp 1차 스칼라 가격**이 freeway bottleneck에서 RM과 VSL이 만드는 대체/보완 관계를
표현하지 못했다는 진단으로 읽어야 한다.

동일한 논리가 F3에도 적용된다. offset은 단독 신호 하나의 편미분으로는 거의 0이지만, 여러
신호 offset과 green split이 함께 맞을 때 green-wave/progression 가치가 생긴다. 즉:

| 결합 레버 묶음 | 스칼라 가격의 한계 | 다음 설계 방향 |
|---|---|---|
| RM + VSL | 둘 다 bottleneck 유입/충격파를 조절하지만 ramp queue와 mainline speed라는 부작용이 다름. per-ramp price와 per-segment VSL price를 따로 주면 cross term을 잃음. | bottleneck-level shadow price 또는 `(RM, VSL)` joint candidate response |
| green + offset | green은 서비스량, offset은 서비스 시점을 정하므로 progression 효과는 두 변수의 곱/패턴에서 발생. per-signal offset 가격은 단독 편미분이 0에 가까움. | corridor-level phase pattern 또는 `(green, offset)` joint candidate response |

따라서 이 아크의 더 안전한 결론은: **완만한 단독 green 조정에는 B2TR식 marginal price가
효과적이지만, 물리적으로 결합된 레버는 per-actuator scalar price보다 결합 묶음 단위의
candidate-level response 평가가 필요하다**는 것이다. `N_UF` 등식/ceiling과 F1RHO hinge는
그 joint response를 안전하게 좁히는 quantity-guided coordination으로 해석한다.

## 5. trust region의 성공 기전과 설계 규칙 (B2TR)

- 폭주(155: green_C 56→92 단조 표류, 재선형화된 가격이 매번 더 세게 같은 방향)의
  기전 = **두 큰 수의 차(g_ext = g_i − d_local)를 측정 이웃(±δ) 밖으로 선형 외삽하는
  월권**. 폭주점에서 전역 g_i는 옳았음(+0.012, "줄여라") — 적용 방식이 배반.
- 처방 = 가격 유효 범위를 **측정한 바로 그 이웃**으로 제한(|p1−ref|≤δ=6s). 운영점이
  움직이면 창이 재중심(sliding) — 정렬된 표류는 매 refresh plant 검증을 통과하며 누적,
  비정렬 표류는 전역 신호 반전 즉시 정지.
- 설계 규칙 2건: (i) 반경과 후보 격자가 안 맞으면 월권 방지가 아니라 **동결**(B3TR v1
  사고) — 이동성 보장 필수. (ii) 허용 이동폭만큼을 측정하라(δ=trust).

## 6. 방법론 교훈

1. **평가는 7200s(과포화)** — 3600s는 이득·해악 모두 은폐(155 해악 +1.7%→+10.3%).
2. **probe(open-loop)는 필요조건일 뿐** — barrier는 probe 부활 후 closed-loop 배반.
   역으로 closed-loop 실패도 한 점 진단(궤적 직독+replay FD)이면 원리적 처방으로 이어짐.
3. regime 판별자를 정적 상태함수에서 찾는 시도는 4연속 실패(P1.5 포화도·가격 크기·
   barrier 0.2/0.5) — 차이는 상태가 아니라 표류 방향과 장기 최적의 정렬 여부.
4. 협업: 동일 기능 병렬 구현 충돌은 같은 머신·같은 기준 A/B로 판정(07-03 §12),
   크로스머신 절대값은 ±0.4~1.2% FP 차이 유의.

## 7. 다음 단계 — F1 아키텍처 (사용자 제안, 07-06 §14 합의)

- **leader**: 순수 TTT의 가격(green/offset/metering/VSL) + N_P/N_UF만 하달.
- **urban follower**: own-TTS + 0.5cap 초과 hinge(선형·차량수·veh·h).
- **freeway follower**: own-TTS + ρ_crit 초과 hinge.
- 근거: 절벽 정보가 미분을 통과하지 않고 follower의 **후보 단위 비선형 평가**(국소 정책
  비교)로 전달 — 3국면 병리가 발생할 자리가 없음. 자율 PFO가 190에서 무붕괴인 것이
  방증(국소 METANET이 자기 절벽을 이미 봄 — 페널티는 명시적 마진 + budget 거부권).
  B2BAR과 달리 후보 간 상수 페널티는 argmin 중립이라 190 회귀 위험이 구조적으로 낮음.
- 검증 순서: **F1**(페널티 이관, 원본 보존 사본으로, 무회귀 확인) → **F2**(metering
  가격+trust 재도전 — 절벽은 follower가 지키므로 가격은 매끈한 몫만) → **F3**(offset
  가격 — legacy 잔존 격차 ~1794의 재료).

## 8. 코드·재현 포인터

- 기본값: `StackelbergWuMeteredController` = green 가격 ON + trust 6s(=B2TR). metering/
  VSL/barrier 가격·cert 전부 opt-in(러너 변형 -B2/-B3/-B3TR/-B3CERT/-B4/-B2BAR(50)).
- 커밋 사슬: 31173ea(B2)→7ccaf9a(병합)→688ec92(교차검증)→f1a8176(B3 포팅+B4)→
  3816d74(155 7200s)→a6a7750(B4 판정)→9683d4d(barrier 개정)→cb81a87→0d461b8(B2TR)→
  3cad304(기본 ON)→5759d66(B3TR 판정)→8c3d29c(B3CERT)→1d00a8a→fb9a776(§13)→a1fccc3(§14).
- 원 결과: outputs/(비추적) + 각 날짜 results/ 사본. 테스트: src/tests/test_signal_
  marginal_price.py, test_b3_b4_price_channels.py, test_nuf_cap_mode.py, test_p15_auto_gate.py.
