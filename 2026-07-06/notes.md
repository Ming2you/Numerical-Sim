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

## 6. TODO
- [ ] **기본값 전환 여부 = 사용자 결정 대기**(이번 지시는 "사본으로 관찰" — 원본 무수정
  유지 중). 메뉴: (a) F1RHO05를 기본으로(약우월, 안전) + -F1RHO(w=1)는 중부하-희박
  배치용 opt-in, (b) 현상 유지(B2TR). (c) w=0.75 knee 정밀화 후 결정.
- [ ] F2(metering 가격+trust 재도전)는 F1RHO 채택 후 재평가 — ρ hinge가 절벽을 지키는
  상태에서 가격이 매끈한 몫만 나르는지. F3(offset 가격, legacy 격차 1430~1794) 대기.
