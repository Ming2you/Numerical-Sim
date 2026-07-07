# Legacy–P-Stack 격차의 실측 분해 (sweet_190 7200s) — 2026-07-06

## 0. 목적과 원칙

목표는 **legacy(중앙 joint 평가) 없이 legacy 성능을 따라가는 분산 P-Stack**을 만드는 것.
그러려면 legacy의 *거동*을 보고 (1) 어느 방향으로 움직여야 하는지, (2) 그 방향으로 가려면
어떤 값을 더해야 하는지, (3) 그 값이 **망 규모·특징에 무관하게 일반화**되는지, (4) **계산비용이
legacy를 넘지 않는지**를 검증해야 한다. 본 보고는 그 첫 단계 — **격차의 원인을 가설이 아니라
실측으로 분해**한 결과다.

기준 수치(sweet_190 7200s): legacy **10729** (urban 9201 / freeway 1527) vs B2TR(현 기본)
**12891** (urban 11339 / freeway 1552). 총 격차 **2162**.

## 1. 방법론 선결 — plant 동일성 검증 (필수)

Jul-3 legacy run과 Jul-4~5 B2 run 사이에 VSL-활성화 등 plant 수정이 끼었는지 의심됐다(비교
무효화 위험). 검증:
- Jul-3 legacy run 이후 `src/models/` 유일 커밋 31173ea는 **state.py +7줄뿐**(물리 무변경).
- `capacity_drop_lane_loss=0`이 legacy·B2 **양쪽 동일**(legacy 아티팩트 아님).
- lambda_eff 스케일(≈1.9 유효차로) 양쪽 동일.
- **결정적**: legacy를 **현재 HEAD로 재실행 → total 10728.8 / urban 9201.4 / freeway 1527.3,
  Jul-3과 비트 동일(diff −0.00%)**. compute 3494s.

→ **plant 동일 확정. 이후 모든 비교 유효.**

## 2. 궤적 분해 — 격차는 전량 urban, freeway는 동률 (희생 아님)

동일 plant에서 legacy vs B2-ON 제어·상태 궤적 직독:

| 지표 | LEGACY | B2-ON | 해석 |
|---|---:|---:|---|
| total TTT | 10729 | 12891 | 격차 +2162 |
| urban TTT | 9201 | 11339 | **격차 전량(+2138)** |
| freeway TTT | 1527 | 1552 | **동률(B2 소폭 우위)** |
| metering flow | 5405 | 4760 | legacy +14% 방류 |
| **N_UF_star** | **5700** | **4848** | legacy가 더 방류 지시 |
| rho_FW_E mean | 37.1 | 36.2 | 둘 다 임계(33.5) 위 |
| **offset_std** | **45·45·28·44·35** | **0·0·0·0·0** | **B2 offset 완전 OFF** |
| green_p1_std | 8·4·8·15·16 | 15·15·12·18·20 | B2가 green은 더 씀 |

**핵심 결론 1 — beyond-cliff "희생 해"가 아니다.** freeway TTT가 거의 동일(1527 vs 1552).
legacy가 rho 37(임계 위)로 굴려도 freeway 비용은 B2와 같다. 즉 legacy는 **freeway를 희생해서
이기는 게 아니다.** 앞서 검토하던 "일부 지역 희생 → 전역 이득" 해는 이 망의 격차 주인공이
아님이 데이터로 반증됨(→ Route 1 폐기).

**핵심 결론 2 — legacy가 쓰는 두 lever = (A) 더 공격적 방류(N_UF 5700 vs 4848), (B) offset
green wave(std 28-45 vs 0).** 둘 다 urban을 줄이는 방향.

## 3. Step 1 — 방류 lever 격리 (N_UF 강제 ↑)

`cfg.leader.N_UF_star_range` 하한을 5500으로 올려 B2TR이 강제로 고방류하게 함.

| | total | urban | freeway | N_UF(실효) |
|---|---:|---:|---:|---:|
| baseline B2-ON | 12891 | 11339 | 1552 | 4848 |
| **N_UF 강제** | **12241** | **10744** | **1497** | 5176 |

- 방류 4848→5176으로 **총 −650 회복 = 격차의 ~30%.** urban −595 **그리고 freeway도 −55**
  (방류가 freeway를 채우는 게 아니라 throughput을 높여 둘 다 개선).
- **비용 556s ≪ legacy 3494s** (원칙 4: 6배 쌈).
- (주: floor 5500이나 feasibility clip으로 실효 mean 5176 — 완전 강제 시 더 회수 여지.)

**일반화 함의(원칙 1-3)**: 강제한 5176 해가 full-TTT로 더 좋은데(12241<12891) B2 leader는
9분 rollout으로 4848을 골랐다 → **leader 짧은 horizon이 "방류의 장기 urban 배수 이득"을 못 봐서
under-release**(절벽 때와 같은 horizon 절단). 따라서 legacy·오라클 없이 leader가 스스로 고방류를
택하게 하려면 **urban 큐/accumulation 압력을 leader 목적에 넣는 신호**(망 규모 무관한 값) 하나면
된다는 가설. ~30%를 일반적으로 회수할 후보.

## 4. Step 2 — offset lever 격리 (local best-response ON, N_UF free)

`nash_solver.offset_enabled=True`로 offset **국소** 최적화 재활성(F3의 leader 가격과 다름).

| | total | urban | freeway |
|---|---:|---:|---:|
| baseline (offset OFF) | 12891 | 11339 | 1552 |
| **offset LOCAL ON** | **12733** | **11098** | **1635** |

- 총 **−158 (격차의 ~7%)**, urban −241인데 **freeway +83(악화)** — **약하고 혼재.**
- **핵심 결론 3 — per-signal 국소 offset로 legacy green wave를 못 잡는다.** F3(offset **가격**
  무효)에 이어 offset **국소 best-response도 무효** → **offset은 per-signal 방법으론 안 되는 joint
  변수**임이 두 번째로 확증. legacy의 offset 가치는 여러 신호의 offset이 **함께** 맞는 corridor
  green-wave 패턴에 있고, 단독/국소로는 편미분·best-response가 ~0.

## 5. 격차 분해 종합 (2162)

| lever | 회수 | 성질 | 다음 |
|---|---:|---|---|
| **metering 방류**(N_UF↑) | **~650 (30%)** | 독립·값쌈·일반화 가능 | urban 압력 신호를 leader 목적에 |
| offset **국소** | ~158 (7%, freeway 악화) | **불충분(per-signal 실패)** | **joint 메커니즘 필요** |
| 나머지 ~1350 (63%) | (Step 3에서 확정 중) | **joint offset + 완전 방류** 유력 | — |

## 6. Step 3 — 확정 probe: legacy offset 값 이식은 **무효** (핵심)

legacy의 offset 궤적을 오라클 주입 + N_UF 강제로 B2TR에 얹음.

| | total | urban | freeway |
|---|---:|---:|---:|
| baseline | 12891 | 11339 | 1552 |
| Step1 N_UF 강제 | 12241 | 10744 | 1497 |
| **Step3 N_UF 강제 + legacy offset** | **12298** | **10836** | 1461 |
| legacy | 10729 | 9201 | 1527 |

- **legacy offset 값을 그대로 주입했는데 오히려 약간 나빠짐**(12298 > Step1 12241, urban 10836 >
  10744). compute 653s ≪ legacy 3494s.
- **핵심 결론 4 — offset 값 단독으로는 legacy를 못 따라간다.** legacy offset은 legacy의 green
  split과 **함께** 최적화된 값이라, B2의 다른 green 위에 얹으면 green wave가 안 맞아 어긋난다.
  즉 offset은 신호 간 joint일 뿐 아니라 **green split과도 joint** — 값만 떼서 이식 불가.
- **offset 3전패 확정**: (1) F3 per-signal 가격 무효, (2) Step2 per-signal 국소 best-response
  무효, (3) Step3 offset 값 이식 무효. → 남은 격차는 **green+offset을 함께 푸는 joint corridor
  조정**이라 per-signal 어떤 방법으로도 분해 불가.

### 6.1 최종 격차 분해 (2162) — offset은 **두 층위**

병렬 세션(Codex §17, notes 2026-07-06)이 offset을 **신호별로 분리**해 결정적 정정을 냈다:
ramp 신호(D/F)의 offset은 **국소 활성화만으로 회수**(G1DF −285, legacy 격차 1430→1144)되나,
urban 신호(A/B/C)의 offset은 국소로 켜면 **오히려 해로움**(corridor de-coordinate). 즉 Step2/3의
"offset 국소·값이식 무효"는 **A/B/C 층에만** 해당하고, D/F 층은 self-contained 레버였다.

| 몫 | 크기(추정) | 성질 | 다음 |
|---|---:|---|---|
| **방류(N_UF↑)** | **~650 (30%)** | 분리·일반화 가능 | urban 압력 신호를 leader 목적에 |
| **D/F ramp offset** | **~285** | **self-contained, 국소 활성화로 회수(G1DF)** | leader 좌표 신호로 승격(일반화) |
| **A/B/C urban corridor joint** | 나머지 | **분리 불가**(per-signal 국소·값이식 실패) | corridor joint 평가의 값싼 분산 근사 |

주의(방법론): Step3의 offset 주입은 decide 후 override(green 재최적화 없음) + **전 신호 일괄**이라,
순net 무효는 D/F(회수 가능)와 A/B/C(해로움)의 **상쇄**였다. offset "값 비이식성"은 A/B/C에 대해
확증하나, D/F는 국소 최적화(값 이식이 아니라)로 회수됨이 G1DF로 실증. A/B/C의 joint (green,offset)
공동 최적화 상한은 별도 corridor build로만 측정 가능(미해결 핵심).

## 7. 함의 — 기여와 다음 과제

- **격차의 정체가 데이터로 확정**: 희생 아님. **(A) 방류 under-release ~30%(horizon 절단 기인,
  일반화 신호로 회수 가능) + (B) JOINT urban 조정(green+offset corridor) ~70%(per-signal 3전패,
  분리 불가)**.
- **원칙 4 여유 재확인**: 두 probe 모두 556s·760s로 legacy 3494s의 1/5~1/6.
- **다음 과제 두 갈래**:
  1. **방류**: leader가 스스로 고방류를 택하게 하는 **urban 압력항/terminal 신호**(망 무관 일반화).
  2. **offset**: per-signal(가격·국소) 전부 실패 → **corridor 수준 joint 평가**의 값싼 근사(legacy식
     통째 joint의 분산판) — 미해결 핵심.

## 부록 — 재현

- 재실행 legacy: `work/run_legacy_pstack_compare.py --scenarios sweet_190 --T-total 7200`.
- Step 1/2/3 probe: `cfg.leader.N_UF_star_range` 하한 강제 / `nash_solver.offset_enabled=True` /
  legacy `control_timeseries.csv`의 `offset_*` 주입. (probe 스크립트는 scratchpad, 로직은 위 본문.)
- 비교 baseline: `outputs/_b4_7200/B2-ON`, legacy `outputs/legacy_recheck_sweet190_7200_20260706`.
