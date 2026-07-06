# 2026-07-06 작업 노트 — F1(안전 페널티의 follower 이관): 구현·분해·w-지도

(선행 문서: reports/price_channel_arc_report_20260706.md, 2026-07-05 notes §12~§14)

## 1. F1 구현 (사본, 원본 무수정 — 사용자 지시)

`src/controllers/f1_wu_faithful_follower.py` 신설(7982984): 세 urban rollout의 F1 사본
(0.5cap spill hinge) + `F1WuFaithfulFollower`(urban은 probe 규약으로 F1 rollout 주입해
부모 로직 재사용, freeway는 `_solve_freeway_agent_local` 사본에 ρ_crit 초과차량 선형
hinge) + `F1StackelbergWuMeteredController`(가격 구성은 기본 B2TR 그대로).
`local_signal_plant.py`/`wu_faithful_follower.py` 원본 무수정. 가중치 0 = 부모 비트동일
(사본 무결성 테스트). 러너 변형: -F1/-F1RHO/-F1RHO05, WU-FAITHFUL-FOLLOWER-F1.

## 2. 7200s 결과 + 분해

| 구성 | sweet_155 | sweet_190 |
|---|---:|---:|
| B2TR(현 기본, hinge 없음) | 4391.8 | 12523.0 |
| F1(spill+ρ, w=1) | 4447.0(+1.26%) | **12158.6(−2.91%, 신기록)** |
| F1RHO(ρ만, w=1) | **4447.0(F1과 비트동일)** | **12158.6(F1과 비트동일)** |
| F1RHO05(ρ만, w=0.5) | **4372.5(−0.44%)** | 12442.2(−0.64%) |

- **sweet_190 신기록**(w=1): legacy 격차 1794→**1430**(−20%). 분해: urban −586 /
  freeway +171 / Σmeter 4848→5001 — ρ hinge가 "절벽만 넘지 마라"의 정확한 경계를
  제공하자 freeway agent가 **절벽 직전까지 자신 있게 방류**해 urban을 구제하는 교환이
  성립(안전이 권한 있는 곳에 있으면 성능도 는다).

## 3. spill hinge 전역 무력 — 위상적 원인 (중요한 구조 발견)

F1RHO == F1 **비트동일**(양 시나리오): spill hinge가 어떤 argmin도 바꾸지 않았다.
원인은 버그가 아니라 위상: 국소 rollout의 s_eff는 **자기 origin 링크만 갱신·이웃
동결**인데, 이 망에서 movement는 항상 하류/타 신호 링크로만 흐른다(2026-07-01 finding
#2의 위상 사실) — **내 green이 채우는 링크는 전부 동결된 이웃**이라 후보 간 페널티
차이가 구조적으로 0.

**함의 — 절벽의 소유 구조가 처방을 결정한다**:

| 절벽 유형 | 소유 구조 | 처방 | 실증 |
|---|---|---|---|
| freeway ρ_crit | 자기 레버가 자기 절벽 통제 | **follower own-objective hinge** | F1RHO 190 −2.91% |
| urban spillback | cross-agent(보내는 쪽은 못 보고, 받는 쪽은 못 막음) | **leader 제약 채널(N_P + λ 적분)** | 기존 구조가 이미 정답 |
| 완만 조정 | — | 가격 + trust | B2TR |

F1의 urban 항은 이관 불가(위상적 무력)이자 불필요(N_P가 담당) — 사용자 제안의 freeway
반쪽이 정확히 적중했고, urban 반쪽은 "왜 안 되는가"의 구조적 이유를 밝혀냈다.

## 4. ρ hinge w-지도 (hinge는 가격이 아니라 마진 항 — w는 정당한 노브)

155: w=0→4391.8, **0.5→4372.5(최선)**, 1.0→4447.0 (비단조, 최적 0.25~0.75 사이).
190: w에 단조 개선(마진 가치는 절벽 근접도에 비례 — 원리적으로 자연).

- **w=0.5 = STOP-clean 승격 후보**: 측정된 두 시나리오 모두에서 현 기본(B2TR) 대비 개선.
- **w=1.0 = 190 특화 opt-in**: 최대 이득(−2.91%), 155 비용(+1.26%).
- sweet_128 실사(F1RHO05) 진행 중 → §5에 추가 예정.

## 5. sweet_128 실사 + 최종 표

F1RHO05 sweet_128 = **1530.360, B2TR과 비트 동일**(경부하에선 본선이 임계 근처에 안 가
hinge 무발화 — 위험 0의 이상적 실사 결과).

| 7200s | sweet_128 | sweet_155 | sweet_190 |
|---|---:|---:|---:|
| B2TR(현 기본) | 1530.4 | 4391.8 | 12523.0 |
| **F1RHO05(w=0.5)** | **1530.4(동일)** | **4372.5(−0.44%)** | **12442.2(−0.64%)** |
| F1RHO(w=1.0) | (무발화→동일) | 4447.0(+1.26%) | **12158.6(−2.91%)** |

**F1RHO05는 B2TR을 약우월(weakly dominate)** — 전 시나리오 STOP-clean.

## 6. F2·F3 판정 (sweet_190 7200s, 기준 F1RHO 12158.6)

**F2(metering 가격 + hinge 방어) = 음성**: 19074.1 — B3CERT와 동일 붕괴(freeway 5607,
Σmeter 5411). 같은 hinge로 등식 budget이면 신기록(F1RHO 5001)인데 가격이면 붕괴 —
**차이는 hinge가 아니라 권한(07-05 §14)**: 가격 모드의 soft budget이 leader 권한을 끊고,
follower 국소 onset 창은 좁으며 거기서 절벽-맹인 가격이 hinge와 싸우고, jam 후엔 국소
hinge도 후보 불변(3국면의 국소판). **metering 가격 = 4구성(B3/TR/CERT/F2) 전패, 영구
아카이브.** metering 조정 최종 = leader 등식/ceiling + hinge-informed 응답(F1RHO).

**F3(offset per-signal 가격) = 무효(null)**: 12158.622 — F1RHO와 비트 동일, 커밋 offset
0/120. 이중 무효화: (i) **leader의 offset 한계가치 ≈ 0**(전 신호·전 step 0.0000 — 신호
하나의 ±14s는 9분 전역 TTT를 안 움직임), (ii) 가격 0이라 탐색이 selfish로 퇴화(103회
비영 제안) → corridor 가드가 전부 기각(2026-06-29 판정의 가드 작동). **기전: offset은
joint 결합 변수** — green wave 가치는 여러 신호의 offset이 함께 맞을 때 생기고 단독
이동의 편미분은 ~0. per-signal 가격(편미분)은 구조적으로 결합 패턴을 발견 불가. legacy가
offset을 쓴 것은 전역 응답의 통째 평가(joint) 덕분.

**조정 수단 분류 최종판**:

| 레버 | 성질 | 정답 수단 | 실증 |
|---|---|---|---|
| green | 완만·가역·개별 | 가격+trust | B2TR(3 regime 개선) |
| metering | 절벽·비가역 | leader 등식 + hinge-informed 응답 | F1RHO(190 신기록) |
| offset | **joint 결합** | per-signal 가격 불가 — 패턴 수준 조정 필요(미해결) | F3 null |
| urban spillback | cross-agent | N_P 제약 채널 | F1 분해 |

### 6.1 보강 해석 — per-actuator price의 한계와 joint response

F2/F3 판정은 "metering은 hard constraint만 가능" 또는 "offset은 무가치"라는 의미가 아니다.
legacy가 성능을 냈던 구조는 `rho_crit`을 절대 제약으로 둔 것이 아니라, RM/VSL/green/offset
후보를 더 joint하게 rollout해 **일시적 밀도 초과, ramp/urban queue relief, throughput 증가**의
교환을 직접 평가했다는 쪽에 가깝다.

따라서 F2 음성의 더 정확한 해석은: metering의 한계가치는 VSL과 함께 정의되는 freeway
bottleneck-level joint value인데, 이를 ramp별 1차 scalar price로 투영하면서 RM-VSL의
대체/보완 관계(cross term)를 잃었다는 것이다. 마찬가지로 F3의 offset null은 offset이
무의미해서가 아니라, green split과 여러 신호 offset이 함께 맞을 때만 progression 가치가
나오는 **joint corridor variable**을 per-signal 편미분으로 본 결과다.

다음 설계 원칙:

| 묶음 | 권장 response 단위 | 이유 |
|---|---|---|
| RM + VSL | bottleneck-level `(RM, VSL)` joint candidate 또는 shadow price | 둘 다 유효 유입/충격파를 조절하지만 ramp queue와 mainline speed 부작용이 달라 cross term 필요 |
| green + offset | corridor-level `(green, offset)` phase pattern 후보 | green은 서비스량, offset은 서비스 시점 — progression은 결합 패턴에서 발생 |

즉 현재 결론은 "가격 채널 폐기"가 아니라 **단독·완만 레버(green)는 B2TR scalar price,
결합 레버(RM/VSL, green/offset)는 joint candidate-level response**로 분류하는 쪽이 더 안전하다.

## 7. TODO
- [ ] **기본값 전환 여부 = 사용자 결정 대기**(원본 무수정 유지 중). 메뉴: (a) F1RHO05
  기본(약우월) + -F1RHO(w=1) opt-in, (b) 현상 유지(B2TR), (c) w=0.75 knee 후 결정.
- [ ] **offset의 남은 길 = joint/패턴 조정**: per-signal 가격이 아니라 leader가 corridor
  위상 패턴(예: A·C 동시 offset 조합 후보)을 직접 후보 평가 — legacy식 joint 평가의
  저렴판. 잔여 legacy 격차(F1RHO 기준 1430)의 유력 재료이나 별도 설계 필요.
- [ ] 러너 -F2/-F3/-F23은 기록용 보존(전부 음성/무효 판정).
