# Offset 소유권 아키텍처 — offset은 follower가 아니라 leader의 결정이어야 한다 (2026-07-07)

## 0. 핵심 결론

- legacy 대비 격차는 **전량 urban**(freeway 동률). 그 몸통 = **corridor offset(green-wave) 조정**.
- **offset은 follower로 분산 불가**: joint 변수라 per-signal 가격≈0(F3), 국소 best-response는
  이기적 Nash로 **de-coordinate**(g1all 악화), 양방향 mesh는 offset 하나로 두 방향 못 맞춤(MAXBAND
  전역 문제).
- **처방 = 레버를 구조에 맞춘 소유권 재배치**: **green(국소·개별) → follower**, **offset(joint·
  corridor) → leader**. 이는 SCOOT/SCATS/MAXBAND의 표준 위계(중앙 offset + 국소 split)와 일치.
- **방법은 SCOOT 휴리스틱이 아니라 MPC**(Van den Berg: MPC>SCOOT). 단 **MAXBAND-LP offset**이
  follower rollout 탐색보다 **싸고 협조적**일 수 있어 cost-performance 후보.
- **정합성**: price/penalty/constraint를 섞어도, **모두 global TTT(veh·h) 단위로 보정**하면
  하나의 목적의 성분들로 일관. 공통 통화가 TTT.

## 1. 격차는 urban (freeway는 문제 아님) — 근거와 실패한 진단

동일-머신(코덱스) 스코어보드(sweet_190 7200s):

| controller | total | urban | freeway | N_UF | rhoE | offset_std(A B C D F) |
|---|---:|---:|---:|---:|---:|---|
| b2tr | 12523 | 10919 | 1604 | 5057 | 35.4 | 0 0 0 0 0 |
| f1rho | 12159 | 10527 | 1631 | 5001 | 34.9 | 0 0 0 0 0 |
| g1df | 11873 | 10258 | 1615 | 5084 | 33.4 | 0 0 0 23 20 |
| g1all | 12638 | 11095 | 1543 | 4980 | 34.8 | 8 16 7 12 10 |
| legacy | 10729 | 9201 | 1527 | 5700 | 37.1 | 45 45 28 44 35 |

- **freeway TTT 동률**(legacy 1527 vs 우리 ~1600) → freeway는 격차의 ~5%. 몸통은 urban.
- **freeway LOO 진단은 실패**(무효): urban=legacy 오라클 고정 + freeway=우리 → total 43125/
  freeway 12775 파국. 원인 = **open-loop 제어 replay는 궤적 발산 시 무효**(legacy urban 제어는
  legacy 궤적에 최적인데 우리 freeway 아래선 궤적이 달라져 그 제어가 붕괴). 교훈: full 제어
  오라클 주입은 궤적-특이적이라 leave-one-out 도구로 부적합. → freeway 판정은 스코어보드 동률로.

## 2. 왜 offset은 follower로 안 되나 (joint 변수의 3중 벽)

1. **per-signal 가격 ≈ 0**(F3): ∂(global TTT)/∂(single offset)=0.0000. green wave는 여러 신호
   offset이 함께 맞을 때만 가치 → 편미분 소멸. 단일신호 민감도 A=0.30, B=0.12(≈0), F=10.7(ramp,
   self-contained라 예외).
2. **국소 best-response는 de-coordinate**(g1all 12638 > b2tr): follower가 자기 지연만 최소화 →
   이웃 externality 미내부화 → 이기적 Nash가 협조 baseline(0)보다 나쁨. (D/F만은 self-contained라
   국소로도 회수 = g1df.)
3. **양방향 mesh = 전역 bandwidth trade-off**: offset 하나로 A→B와 B→A wave 동시 만족 불가.
   반응 추종은 일방향엔 되나 양방향엔 전역 최적화(MAXBAND) 필요. → per-signal·국소·pairwise
   교환 모두 못 넘음.

**부수 발견 — skew 게이팅**: 대칭 양방향이라 joint가 강제된 것. demand skew(일방 지배)면 trade-off
소멸 + 단일신호 민감도 상승 → 분산 offset 회수 가능(green split이 포화+skew서 살아난 것과 동형).
현실 peak는 대개 skew라 실배포선 분산이 살 수 있음. **원리적 경계**(regime 상실 아님).

## 3. 처방 — 레버 소유권 재배치

| 레버 | 구조 | 소유 | 근거 |
|---|---|---|---|
| green split | 국소·볼록·개별 | **follower**(가격) | 자기 큐 서비스, marginal≠0 |
| **offset** | **joint·corridor** | **leader**(중앙) | joint라 중앙 평가자만 |
| N_P·N_UF 예산 | 전역 자원 | leader | 네트워크 합 제약 |
| metering 절벽 | 비가역·전역 | leader constraint | capacity drop 회피 |

**leader의 명분 재정의**: "모든 걸 가격화"(죽음 — metering/offset 가격 실패)가 아니라 **one-hop
이웃이 못 보는 전역**(예산·장거리 연쇄·절벽·균형선택). offset은 joint/전역이라 leader; green은
국소라 follower. offset을 follower로 강제한 게 F3·g1all 실패의 근원.

## 4. 방법 — SCOOT 아님, MPC (Van den Berg) / MAXBAND-LP

- **분담**(중앙 offset + 국소 split)은 SCOOT/SCATS/MAXBAND의 표준. **방법**은 다름:
  Van den Berg(2007, 통합 urban-freeway MPC)가 SCOOT/SCATS 휴리스틱을 이김(예측>반응).
  → 우리 leader의 offset 결정은 **MPC joint rollout**(=legacy 방법), SCOOT 증분 아님.
- **지형**: SCOOT(휴리스틱·위계·약함) < full 중앙 MPC(Van den Berg/legacy·성능 천장·비쌈).
  우리 = **국소(green) 분산 + joint(offset·예산) 중앙 MPC** → 천장 근접 + 국소 확장성.
  즉 MPC를 버리는 게 아니라 **joint는 중앙, 국소는 분산**으로 나눔.
- **cost 후보 — MAXBAND-LP offset**: follower offset rollout 탐색(신호×후보×rollout, g1df 44-55s/
  step 비용원)을 **LP 한 번**으로 대체 → 더 쌈. 게다가 joint라 de-coord 회피(국소 탐색보다 협조도↑).
  **양쪽에서 follower 탐색을 이길 수 있음.** 단 **과포화선 MPC rollout이 우위**(progression 가정
  붕괴, capacity/spillback 예측 필요 — Van den Berg 지점). → 하이브리드: **offset=MAXBAND-LP(싸고
  joint) + 예산·절벽=MPC rollout(예측 필요처)** 로 leader 경량화.

## 5. 정합성 — 공통 통화는 TTT

price(green)+penalty(offset)+constraint(metering)를 섞으면 "통일 가격 프레임"이 깨진다는 우려.
해법: **모든 항을 global TTT(veh·h) 단위 추정치로 보정**하면 형태가 달라도 **하나의 목적(전역 TTT)의
성분들**로 일관. marginal price=∂TTT/∂lever(이미 veh·h). arrival-red/queue penalty도 실제 지연
(veh·h)으로 보정하면 합산·trade-off 정합. **arbitrary 가중치·double-counting이면 비정합** — 거기가
위험. 통일 원리 = "전부 가격"이 아니라 **"전부 같은 TTT 통화 + 구조에 맞는 형태"**(Weitzman
prices-vs-quantities + taxonomy).

## 6. 방법론 caveat — 과포화 7200s는 환경 간 재현 불가

- G1DF: 내 머신 12575.6 vs 코덱스 11872.9(같은 코드·config·후보수 74). 각 머신은 결정론적(재실행
  비트동일)이나 **환경 간 FP 차(numpy/BLAS/CPU, compute 51s vs 94.5s)가 혼돈적 과포화서 leader
  argmin을 갈라 ~700 발산.**
- **함의**: 단일점 7200s 비교는 **동일 머신·환경**에서만 유효. 논문은 (i) 환경 고정 또는 (ii)
  섭동 다중런 mean±std로, "신기록 −285" 등은 발산폭(~700) 대비 유의성 명시 필요.

## 7. 다음 (다른 계정 머신)

1. **offset을 leader MPC joint(또는 MAXBAND-LP)로 결정**하는 채널 구현 — green은 follower 유지.
   G1ABC를 leader-offset으로 돌려 A/B/C 회수 확인.
2. **MAXBAND-LP vs MPC-rollout offset cost-performance frontier**(과포화): LP가 몇 % 성능을
   몇 분의 1 비용으로 잡나 → offset을 값싼 LP로 둘지 결정.
3. (병렬) 코덱스 joint (green×offset) cross-term probe(∂²TTT/∂g∂off) — intra-signal 보완재.
4. skew 시나리오에서 분산 offset 회수 검증(원리적 경계 실증).
