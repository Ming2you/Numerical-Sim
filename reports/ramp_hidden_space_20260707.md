# Ramp = "hidden space" — leader가 방류를 안 올리는 근본 원인 (realized TTT의 위치 불변성)

작성 2026-07-07. 모든 실측은 내 머신(legacy 10729·G1DF 12575 동일 환경). 과포화 7200s는 환경 간
FP 발산(~700) 있어 절대값이 아니라 **구조**를 봄.

## 0. 핵심 결론

- leader가 방류(N_UF)를 legacy(5700)만큼 안 올리고 4800에 머무는 근본 원인은 hinge·headroom·
  density_penalty가 아니라 **objective(realized TTT + 9분 horizon)의 구조적 결함**이다.
- **realized TTT는 차량의 "위치"를 구분 못 한다** — 네트워크 안에 있으면 ramp 큐든 freeway든 똑같이
  카운트. 그래서 **on-ramp 큐가 "hidden space"** 가 된다: 차를 여기 숨겨두면 (a) TTT엔 잡히지만
  (b) 어느 penalty에도 안 잡히고 (c) 9분 안에 complete 안 하는 한 방류해도 똑같은 TTT.
- **방류 = 차를 ramp→freeway로 "옮기는 것"이지 "빼는 것"이 아니다.** 진짜 이득(exit/완료로 TTT
  카운트 멈춤, urban 뚫림)은 **9분 밖**. → leader가 9분 안에 보면 "방류해도 TTT 같은데 freeway
  부하만 는다" → **ramp에 숨기는 게 합리적** → under-release.
- 처방 = **hidden space를 objective에 드러내기**: ramp 큐 penalty(terminal cost proxy) 또는
  terminal cost(exit까지 남은 시간) 또는 큐/accumulation 기반 목적. horizon 연장은 임시책이며
  **network 크기에 비례해 커져야 해 일반화 안 됨**.

## 1. 결정적 증거 — proxy로 N_UF 스윕(직접 채점)

fixed control로 congested state까지 전진 후, 같은 state에서 N_UF만 바꿔 `_proxy_score_candidate`
채점(`objective` 낮을수록 좋음):

| step | rampQ | N_UF 4275 → 6000 objective | follower_ttt |
|---|---:|---|---|
| 9 | 7 | 825.99 → 825.42 | 651.39 → 650.86 |
| 14 | 5 | 1506.56 → 1506.56 | 1031.72 → 1031.37 |
| 23 | 117 | 2967.28 → 2968.94 | 1830.21 → 1830.45 |

- **objective·follower_ttt 모두 N_UF에 <0.1% 변화 = 거의 flat.** leader의 9분 rollout은 저방류
  (4275)와 고방류(6000)의 TTT 차이를 **거의 못 본다.** 방류를 올릴 신호가 objective에 없음.

## 2. 메커니즘 — 왜 방류에 무감각한가

TTT = 모든 차의 **네트워크 체류시간 합**. 차가 ramp 큐에서 대기하든 freeway에서 주행하든, 네트워크
안이면 똑같이 카운트. **방류 = 차를 ramp 큐→freeway로 이동**:
- ramp 큐 대기시간 ↓ + freeway 주행시간 ↑ → **상쇄, net 0**.
- 진짜 이득 = 그 차가 **freeway 주행→off-ramp/경계 이탈로 네트워크를 떠날 때**(TTT 멈춤) = **대개
  9분 밖**.
- 그래서 9분 rollout은 방류의 **위치 이동(net 0)만 보고 exit 이득(9분 밖)은 못 봄** → 방류량에
  무감각.

비유: 대기실(ramp)의 사람을 복도(freeway)로 내보내도 짧은 시간 안엔 "건물 체류시간" 안 줄어듦
(이득은 건물을 나갈 때, 한참 뒤). 9분만 보면 "내보내나 마나 같다".

## 3. objective에 ramp 큐가 없음 (leader.py:882)

```
leader total = base(realized TTT) + target_penalty + mfd_storage_penalty(urban half-cap)
             + boundary_in_queue_penalty + density_penalty(freeway rho 초과, w_F)
```
- **on-ramp 큐는 어느 penalty 항에도 없다.** `_nuf_queue_drain_target`·`ramp_queue_stress`엔
  나오지만 참고용(bound/target)이지 objective 아님. realized TTT(base, follower ramp_queue_tts)엔
  있으나 §2대로 방류에 flat.
- **비대칭**: objective는 freeway density(방류가 늘림)를 penalize하고, ramp 큐(방류가 줄임)는
  안 함 → 방류는 objective상 **cost만 있고 benefit 없음** → 숨기는 게 이득.
- off-ramp storage도 같은 성질의 hidden buffer 후보(차 accrue TTT, 별도 penalty 부재).

## 4. 배제된 것들 (이번 세션에서 실측으로 red herring 판정)

| 후보 | 결과 |
|---|---|
| follower ρ_crit hinge (F1RHO) | 제거 시 −211(소폭). 방류 억제 주범 아님. |
| leader feasibility headroom (rho_crit 실링) | 제거 시 ~0(무효). 초반엔 binding도 아님. |
| leader density_penalty | objective의 **<1%**. 방류 결정에 무의미(legacy는 오히려 더 냄). |
| offset(leader-joint로 해도) | release를 물리적으로 이득이 되게는 하나, follower가 그 이득을 국소로 못 valance. |
| urban-side release price | 자의적(region split) + urban smooth는 plant 아티팩트(실제 urban도 절벽 가능). 일반 해법 아님. |

→ 이 모든 게 **증상**이고, 뿌리는 §2의 **realized TTT 위치 불변성 + 9분 horizon = ramp가 hidden
space**.

## 5. 처방 — hidden space를 objective에 드러내기

1. **ramp 큐 penalty (terminal cost proxy, 유력)**: ramp에 stuck된 차 = exit에서 가장 먼 차 =
   최대 deferred 비용. objective에 **ramp 큐에 선형** 항 추가 → 방류가 ramp 배수로 penalty↓
   (flat 아닌 신호) → leader가 legacy처럼 방류.
   - **선형**이 맞음(각 차가 본선 통과해야 나감 ∝ 큐 대수). 0.5*N_cap hinge는 under-count(작은
     큐도 deferred 비용) — hinge는 spillback 안전용이지 terminal cost용 아님.
   - **weight 균형 필수**: 너무 세면 freeway 절벽까지 과방류(붕괴), 균형이면 절벽 직전까지(legacy).
2. **terminal cost = exit까지 expected 남은 시간** (원리적 형태): ramp 큐는 그 proxy. 표준 MPC
   이론 — 좋은 terminal cost는 무한지평 cost-to-go 근사로 **짧은 horizon을 무한지평처럼** 만듦.
3. **큐/accumulation 기반 목적**: realized TTT 대신 큐를 벌점(store-and-forward 방식). 큐 = 미래
   TTT proxy라 forward-looking.

## 6. 일반화 함의 (중요)

realized-TTT-only면 이득(exit)이 보이려면 **rollout horizon이 network 통과시간만큼** 커야 →
**network 커질수록 horizon 폭발 → 일반화 붕괴.** terminal cost/큐목적이 이걸 끊음(horizon을 크기와
분리). **대형 network MPC 문헌도 긴 horizon이 아니라 (a) terminal cost/constraint(Mayne et al.
2000), (b) 큐/accumulation 목적(store-and-forward — Aboudolas/Diakaki/Papageorgiou), (c) 집계
accumulation 상태(MFD/perimeter — Geroliminis/Haddad)로 해결.** 우리가 realized-TTT+9분으로 간 게
예외적이고, 그래서 방류 신호가 소멸.

## 7. 다음 (다른 계정 머신)

1. **leader objective에 선형 ramp-큐 항 추가** → sweet_190 7200s에서 N_UF↑·urban 회복하나 +
   weight 스윕(과방류 붕괴 경계 찾기). 이게 §5의 핵심 검증.
2. (진행 중) **horizon 15분(h15)** — 임시 확인용(horizon 늘리면 exit를 창 안에 담아 방류 신호
   회복하나). 단 §6대로 일반화 안 됨 → ramp-큐 항이 진짜 처방.
3. off-ramp storage도 hidden buffer인지 objective 점검.

## 부록 — 이번 발견의 의의

지금까지 hinge·headroom·penalty·offset·urban-price를 다 파봤으나 전부 증상이었다. **ramp = hidden
space** 는 그 증상들의 공통 뿌리를 한 문장으로 준다 — "realized TTT는 차의 위치를 구분 못 하고,
9분 안엔 완료 안 하니, ramp에 숨긴 차와 진행 중인 차가 동일 TTT라 leader가 방류할 이유가 없다."
처방(terminal cost/ramp-큐 penalty)은 hinge류 튜닝과 질적으로 다르며 **일반화 요건까지 동시 충족**.
