# 2026-07-07 작업 노트

## 1. Offset 소유권 아키텍처 (리포트) — offset은 leader 결정이어야

`reports/offset_ownership_architecture_20260707.md` 참조. 핵심:

- 격차는 전량 urban(freeway 동률 1527 vs ~1600, 스코어보드). **freeway LOO 진단은 무효**
  (legacy urban 오라클 open-loop replay → 궤적 발산 → total 43125 파국. 교훈: full 제어 주입은
  궤적-특이적이라 LOO 부적합).
- **offset은 follower로 분산 불가**(joint 3중 벽): per-signal 가격≈0(F3) + 국소 best-response
  de-coordinate(g1all 12638>b2tr) + 양방향 mesh bandwidth trade-off(MAXBAND 전역). D/F만
  self-contained라 국소 회수(g1df). skew면 분산 가능(원리적 경계).
- **처방 = 소유권 재배치**: green(국소)→follower, **offset(joint)→leader**. SCOOT/MAXBAND 표준
  위계(중앙 offset+국소 split)와 일치. leader 명분 재정의 = "모든 걸 가격화"(죽음) 아니라
  "one-hop이 못 보는 전역"(예산·연쇄·절벽·균형선택).
- **방법**: SCOOT 휴리스틱 아님, **MPC**(Van den Berg>SCOOT). 단 **MAXBAND-LP offset**이 follower
  rollout 탐색보다 싸고(LP vs rollout) 협조적(joint vs 이기적)일 수 있음 → 하이브리드(offset=LP,
  예산·절벽=MPC). 과포화선 MPC rollout 우위.
- **정합성**: price/penalty/constraint 섞어도 **전부 global TTT(veh·h) 단위 보정**하면 일관
  (공통 통화=TTT). arbitrary 가중치·double-count이 위험.
- **재현성 caveat**: 과포화 7200s는 환경 FP차로 머신 간 ~700 발산(G1DF 내 12575 vs 코덱스 11872).
  단일점 비교는 동일 머신만.
- 다음(다른 계정): leader-offset(MPC/MAXBAND-LP) 채널 구현 + LP vs rollout cost-perf frontier +
  joint cross-term probe + skew 검증.
