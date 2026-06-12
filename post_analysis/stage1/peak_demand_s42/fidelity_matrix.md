# Stage 1 fidelity matrix (plan §2.4)

| controller | plant | authority | objective | horizon | solver | coupling iteration | 차이의 영향 |
|---|---|---|---|---|---|---|---|
| WU-CD-F | 공유 plant(METANET+movement queue, storage-cap spillback) | green p1+VSL (offset 0, metering=용량, allocation 無) | agent local TTS+Δu | 공통 T_c×horizon | 원문 MILP/SQP 대신 결정적 후보탐색(경량 국소 큐/밀도 모델) | y 고정→교환, S_max | local 모델이 거칠어 분산해의 질이 원문 대비 보수적일 수 있음 |
| WU-MATCHED-STACKELBERG | 동일 | 동일 | local + w·pos(n_pred−ω·target) conditioning | 동일 | follower=위와 동일, leader=후보 열거+coupled 예측 | 동일 | leader 후보 9개 고정 그리드 — conditioning이 binding하지 않으면 WU-CD-F와 동일해질 수 있음 |
| WU-CC-F | 동일 | 동일(green+VSL) | J_WU_global(TTS+Δu) | 동일 | seeded random search(budget 보고) | 없음 | 보장된 전역최적 아님 — 동일 budget 수치 참조 |
| PROPOSED-FOLLOWERS-ONLY | 동일 | allocation/green+offset+metering+VSL | follower local + 균형(전역 target 無) | 동일 | 기존 distributed follower 휴리스틱 | coupling iteration | leaderless metering은 국소 1-구획 예측 후보선택 |
| PROPOSED-STACKELBERG | 동일 | 동일 full | leader J_L(16.8)+follower 휴리스틱 | 동일 | leader 후보×distributed Nash | coupling iteration | 기존 검증된 controller |
| PROPOSED-CENTRALIZED | 동일 | 동일 full | J_PROPOSED_SYSTEM(TTS+초과+Δu) | 동일 | seeded random search | 없음 | allocation을 게이트 service level로 매개변수화(차원 축소 근사) |

공통: Wu off-ramp spillback(식22 차로수 감소)은 본 plant의 storage-cap 방식으로 대응(효과 등가,
wu2022_reference §8). VSL 변화 제약은 양방향 max_vsl_step(Wu는 감소만 제한) — 기존 plant 정의 유지.
