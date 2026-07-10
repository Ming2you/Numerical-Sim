# 13-Player 재구축 계획 (옵션 3) — freeway segment agent 분할

## 배경

2026-07-10 사용자 발견: 설계 문서(docs/wu2022_distributed_reference.md §7)의 분할 지시는
urban 5 + freeway **segment** agent인데, 구현(WU-CD-F·WuFaithfulFollower)은 freeway를
**link 단위 2개**로 만들어 총 7-player로 이탈(2026-06-14 Option C에서 변수 분할로 대체,
무승인). 사용자 결정: 현 7-player 결과(플래그십 SPLIT-v2 d3 = 11893)는 **보험으로 동결**하고,
플래그십을 13-player로 재구축한다(옵션 3).

## 원칙 (이번에 지킬 것)

- 구조 결정(agent 수·귀속·분해 단위)은 전부 이 문서에 명시하고 **사용자 승인 후** 구현.
- 보험 보존: main = 7-player 동결. 수술은 `feature/segment-agents-13p` 브랜치에서만.
- **3점 비교런(base/A-only/A+B)이 도는 동안 src/ 수정 금지** — 후속 런이 시작 시점의
  디스크 코드를 import하므로 오염됨. 체인 종료 후 착수.
- 변수 하나씩: 입자도(7→13)를 먼저 검증된 채널 구성(equality+SPLIT-v2)으로 바꾸고,
  N_UF dual은 그 위에서 ablation으로 재검증.

## 13-Agent 매핑 (2026-07-10 사용자 수정 반영 — 확정)

사용자 지정 매핑. 초안(F_L2가 ramp 2개 + off-ramp를 freeway 소유)은 기각됨.

| agent | 소유 | 결정변수 | 가격 |
|---|---|---|---|
| U_A, U_B, U_C | 자기 교차로 + 진입 movement | green (+offset) | green×offset joint (현행) |
| U_D, U_F | 교차로 + on-ramp movement + **자기 교차로로 들어오는 off-ramp storage 2개(W/E)** | green (+offset) | green 단일 (현행) |
| F_W0 / F_E0 | seg0 + mainline origin queue | VSL(seg0) | VSL 단일 |
| F_W1 / F_E1 | seg1 | VSL(seg1) | VSL 단일 |
| F_W2 / F_E2 | seg2 + **on-ramp R_D(merge seg2)** | VSL(seg2) + metering(R_D) | **vsl×meter joint** |
| F_W3 / F_E3 | seg3 + **on-ramp R_F(merge seg3)** | VSL(seg3) + metering(R_F) | **vsl×meter joint** |

- off-ramp는 전부 urban 소속(D가 OR_D_W/E, F가 OR_F_W/E) — Wu §IV-A 원문("i로 들어오는
  off-ramp도 agent i 소속") 및 §7 지시와 정합. 초안이 오히려 이탈이었음.
- ramp 소유 agent가 link당 2개(F_L2·F_L3)로 분리 → **link 예산 Σmeter = ω_F·N_UF*가
  진짜 cross-player 공유 제약이 됨**(GNE의 "G"가 실체화). 집행 메커니즘은 아래 fork.

### 필요한 물리 망 변경 (2026-07-10 승인 완료)

현 config는 R_D·R_F **둘 다 seg2 merge**(`ramp_merge_segment_index` 전부 2). F_L3가
R_F를 소유하려면 **R_F_W/R_F_E merge index 2→3** 변경 필요(안 바꾸면 F_L3의 own-TTS가
자기 metering 효과를 못 봄 — 27%p 함정 재현). 기하학적으로도 D 인터체인지(off seg1/on
seg2)·F 인터체인지(off seg2/on seg3)가 되어 오히려 일관적. **단, plant 변경이므로 기존
결과와 직접 비교 불가** → 새 망에서 7-player 플래그십 1회 재실행으로 보험 앵커 갱신
(sweet_190 d3, ~1h). 구 결과는 구 망 보험으로 그대로 보존.

### metering 예산 집행 메커니즘 (2026-07-10 (ii) 승인 완료)

- **(ii) 2-agent 예산 합의(채택)**: Jacobi 안에서 F_L2·F_L3가 상대 meter 동결값을 보고
  own-TTS+가격으로 best-response → (m_D, m_F)를 예산 simplex에 사영(under-relaxation).
  공유 제약이 진짜 GNE 기제로 작동 — 논문의 GNE 주장 실체화. 리스크: 합의 진동(S_max=5
  절단 + 사영으로 방어).
- (i) leader가 per-ramp 수량 직접 하달: leader가 g_ext+링크셰어로 ramp별 B를 갈라서
  각 agent는 집행만. 가장 안전하나 follower 배분 지능이 leader로 이동(SPLIT-v2 서사 약화).
  (ii) 실패 시 fallback.

## 결합변수 y (agent 간 교환, Jacobi + under-relaxation α=0.5 + S_max=5 유지)

- f↔f (동일 link 인접 seg): 경계 (ρ, v, 유출 q) — METANET 상류 유입 + 하류 밀도(anticipation).
- u→f: U_D/U_F green release → F_L2/F_L3의 ramp reservoir 유입 (기존 u_on 채널, 수신자만 변경).
- **u→f 신설**: U_D/U_F의 off-ramp storage 가용공간(supply) → 해당 boundary segment
  (F_L1: OR_D, F_L2: OR_F)의 유출 제약.
- f→u: F_L1/F_L2 off-ramp 유출 → urban D/F의 storage 유입 (기존 _last_offramp_flow 채널).
- f-f 예산 사영: F_L2↔F_L3 meter 교환 (메커니즘 (ii) 채택 시).
- FW_W ↔ FW_E는 비인접(기존과 동일, 결합 없음).

## Local plant

`freeway_substep_local`(link 전체 전진)을 **segment-local 전진**으로 분해 — 자기 seg만
전진, 이웃 경계는 동결 y. 대안(각 agent가 link 전체 전진, 자기 seg만 채점)은 Wu 원칙
("자기 서브망만 전진") 위반 + 4× 비용이라 배제. λ-recovery/off-ramp drain 모델은 소유
agent(F_L1/F_L2)의 local plant로 이동.

## 채널 배치 (플래그십 SPLIT-v2 정합 유지)

- **Metering = 수량(equality) 유지**: leader가 B_link = ω_F·N_UF* 하달 → F_L2가 자기
  2 ramp에 SPLIT-v2 배분(own_TTS + g_ext 랭킹). N_UF dual은 8단계 ablation으로만.
- N_P = urban 공통 dual λ_P (step 간 적분) — 불변.
- 가격층 = leader 측 전역 rollout이라 **계산 불변**. follower 적용처만 소유 agent로 매핑.
  (A/B 컴퓨트 패키지·SPSA 게이트도 leader 측이라 이식 무관.)

## 핵심 리스크와 대응

1. **VSL externality 재발** (실측 전례: uniform VSL ΔTTS=0). seg0/1 감속은 자기 TTS를
   올리고 이득은 seg2/3에 감 — link agent는 벡터 탐색으로 내부화했지만 segment agent는
   시야 밖. **대응 = leader의 per-segment VSL 가격(E2 externality)이 정확히 이 외부성을
   내부화.** 7-player에서 VSL 가격이 중립이었던 이유가 "외부성이 이미 link 내부화돼
   있어서"였다는 가설의 검증 겸. 논문 서사: 분해 입자도↑ → 외부성↑ → 가격 조정 가치↑.
2. Metering 창발: F_L2가 ramp+merge seg 동시 소유라 own-TTS에 이득 직접 반영(27%p
   사건과 구조적으로 다름 — 그땐 urban 소유라 freeway 시야 0). 검증으로 확인.
3. 합의 수렴: 13 agent에서 S_max=5 내 잔차 수렴 — 진단 계측으로 확인.

## 단계

0. [완료] main 동결 + `feature/segment-agents-13p` 브랜치. 3점런 종료 대기
   (**src/뿐 아니라 config도 체인 종료까지 수정 금지** — 후속 런이 디스크 상태를 로드).
0.5. R_F merge index 2→3 (config) + 새 망 7-player 플래그십 1회 재실행 → 보험 앵커 갱신.
1. segment-local METANET 전진 + y 스키마 + 단위테스트(동결 y에서 link 전진과 질량보존
   일치, Jacobi 반복 시 경계 전파 확인). off-ramp storage 동역학은 urban D/F local로 이동.
2. WuFaithfulFollower agent registry 13개 + `_solve_followers` 루프 개편 + 소유맵.
3. metering equality/SPLIT-v2 → F_L2 이식.
4. VSL per-segment best-response + VSL 가격 적용 + mainstream-metering 창발 검증
   (Option-C payoff 테스트의 segment판).
5. 회귀 전체 + sweet_190 d3 폐루프 vs 보험 11893 + 채널 활성 확인.
6. 벤치마크(WU-CD-F) 분할 여부 결정 — 플래그십 결과 본 후.
7. A/B 컴퓨트 패키지 재검증(dedupe 키 N_UF는 유효 예상) + 필요 시 depth 재스윕.
8. **N_UF dual ablation** — env `wu_faithful_nuf_coordination_mode=dual`로 재검증.

## 성공 기준

- (a) 진단에서 13 agent 개별 solve + 합의 iteration>1 확인
- (b) sweet_190 d3 TTT ≤ 11893+300 (노이즈 밴드 내 무손실) — 초과 시 원인 진단 후 채택 결정
- (c) VSL·metering 채널 활성 유지(비활성 이력 재발 체크)
- (d) 전체 단위테스트 통과
