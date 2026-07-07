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

## 2. Ramp = hidden space (리포트) — 방류 under-release의 근본 원인

`reports/ramp_hidden_space_20260707.md` 참조. 핵심:

- leader가 방류를 legacy(5700)만큼 안 올리는(4800) 근본 = **objective(realized TTT + 9분)의 결함.**
- **realized TTT는 차의 위치 구분 못 함** → ramp 큐가 **hidden space**: 차 숨기면 (a)TTT엔 잡히나
  (b)어느 penalty에도 없고(leader.py:882 objective에 ramp 큐 항 부재) (c)9분 안 complete 안 하면
  방류해도 같은 TTT. → **방류=ramp→freeway 이동(net 0)**, 진짜 이득(exit)은 9분 밖 → leader가
  ramp에 park(합리적) → under-release.
- **증거**: proxy로 N_UF 스윕 시 objective·follower_ttt가 4275→6000 내내 <0.1% flat(방류 무감각).
- **배제 확정**: hinge(−211 소폭)·headroom(무효)·density_penalty(<1%)·offset·urban-price 전부 증상.
- **처방**: objective에 **선형 ramp-큐 항**(terminal cost proxy — ramp=exit 가장 먼 차=deferred
  비용) 추가 → 방류가 신호를 가짐. weight로 freeway 절벽 균형. 0.5*N_cap hinge는 under-count(선형이 맞음).
- **일반화**: realized-TTT-only면 horizon이 network 통과시간에 비례해야 → 일반화 붕괴. terminal
  cost/큐목적이 horizon을 크기와 분리. 대형망 MPC 문헌도 terminal cost/큐목적/집계상태로 해결(긴 horizon 아님).
- 다음: leader objective에 선형 ramp-큐 항 + weight 스윕(다른 계정). h15는 임시 확인용.

## 3. VSL two-branch FD 구현 + 두 terminal cost 계획 (리포트)

`reports/vsl_fd_and_terminal_cost_plan_20260707.md` 참조. 핵심:

- **forced-VSL 실측**: 지속 VSL 100→60이면 total −292·urban −349·방류 +322. VSL은 살아있는 lever인데
  컨트롤러가 상한 방치(temporal myopia — 이득이 9분 밖).
- **two-branch VSL-FD 구현(완료, gated OFF 기본)**: `metanet.py` `two_branch_vsl_speed_kmh` +
  `effective_desired_speed_kmh(two_branch,rho_jam)`. Newell/삼각형, VSL=자유류속도, 혼잡branch 고정,
  ρ_crit=접점. 단위검증 PASS(VSL 100→50: ρ_crit 33.5→49.5↑, capacity 3350→2475↓).
- **caveat 2건**: (1) 삼각형 capacity 3350≠exponential 1961 → ON시 전면 재baseline. (2) nu_cong·
  receiving가 아직 고정 ρ_crit 사용 → ρ_crit(VSL) 전파 필요(안 하면 FD 이득 부분만).
- **두 terminal cost**: 안2=free-flow time-to-exit(Bellman T(loc), release/hidden-space, generalize·
  no legacy), 안1=measured marginal(혼잡-aware, VSL 채널, 무겁다). 둘 다 구현해 비교.
- **joint g probe 판정**: metering 안 죽음이나 작고 peak flat, VSL 상보 약함 → price 부차, terminal
  cost 주. receiving→0/(2)죽음/joint코어 **철회**.
- baseline: PFO 실행중, legacy는 process-pool로 harness 필요.
- 다음: FD coupling(ρ_crit(VSL) 전파) → 안2 구현·verdict 재판정 → 안1 → 4-컨트롤러 풀런.
