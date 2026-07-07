# GLEADOFF vs G1DF vs LEGACY 3자 비교 — 왜 legacy를 못 따라잡나 (2026-07-07)

## 0. 한 줄 결론

격차는 두 조각이다: **(A) N_UF under-release ~650(30%)** — leader가 짧은 horizon + 3중 rho_crit
억제로 방류를 덜 지시 — 와 **(B) arterial green×offset 공동설계 ~나머지** — legacy는 offset을
**균등 green**과 함께 쓰는데(green_std A/B/C=8/4/8), 우리 follower는 offset을 얹어도 green을
selfish하게 skew(16/15/12)해서 **green이 offset과 싸운다**. GLEADOFF가 g1df보다 나쁜 이유가 바로
(B): legacy 크기 offset(42/43/30)을 걸었지만 green이 안 따라와 green-wave가 깨졌다.

## 1. 3자 제어변수 나란히 (sweet_190 7200s, 같은 plant)

| | total | urban | freeway | N_UF | green_p1_std A B C D F | offset_std A B C D F |
|---|---:|---:|---:|---:|---|---|
| **LEGACY**(중앙 joint) | **10729** | **9201** | 1527 | **5700** | **8 4 8** 15 16 | **45 45 28** 44 35 |
| g1df(분산, D/F offset) | 11873 | 10258 | 1615 | 5084 | 16 10 11 11 11 | 0 0 0 23 20 |
| **GLEADOFF**(leader A~F offset) | 12404 | 10873 | 1531 | 4984 | 16 15 12 19 12 | **42 43 30** 30 39 |
| (참고) g1all(follower A~F) | 12638 | 11095 | 1543 | 4980 | 15 14 13 17 15 | 8 16 7 12 10 |
| (참고) b2tr(offset 없음) | 12523 | 10919 | 1604 | 5057 | 16 15 13 17 15 | 0 0 0 0 0 |

freeway는 전부 동률(1527~1615) — **격차는 전량 urban.**

## 2. 어디서 분기하나 — 두 결정 지점

Stackelberg는 (leader: N_P·N_UF 예산) → (follower: green split·metering·offset)로 순차 분해된다.
legacy는 이 전부를 **한 번에** 푼다. 분기점 둘:

### 분기 1 — leader의 N_UF (방류 예산): 5700 vs ~5084
- legacy는 5700 방류, 우리 leader는 ~5084(−12%). Step1 probe(N_UF 강제 5176)로 **−650 회복** 확인
  (urban·freeway 동시 개선 = 방류가 freeway를 채우는 게 아니라 throughput을 높임).
- **왜 under-release**: leader 목적함수(leader.py:882)는
  `TTT + w_P·(N_P−N_P_crit)_+ + urban_storage + w_boundary_in·boundary_q + w_F·(ρ−ρ_crit)_+`,
  horizon 3스텝(9분). 방류의 이득(urban 큐 장기 배수)은 9분 밖이고, 방류의 손해(freeway ρ 상승
  → `w_F·density_penalty`)는 horizon 안이다. → **비대칭 시야로 under-release**. 게다가 방류를
  막는 rho_crit gate가 **3중**: (i) follower F1 ρ_crit hinge, (ii) leader `density_headroom` 캡
  (feasible N_UF 상한), (iii) **leader 목적의 `w_F` density penalty**. (i)(ii)는 NORHO가 제거 중,
  (iii)은 목적함수라 별개.

### 분기 2 — follower의 green vs leader의 offset: 공동설계 실패
- legacy: arterial green **거의 균등**(std 8/4/8) + **큰 offset**(45/45/28). green-wave가 throughput을
  나르니 green을 skew할 필요가 없다.
- 우리 follower: green을 **selfish skew**(자기 큐 최소화 → std 16/10~15/11~13). offset은 g1df서 0.
- GLEADOFF: leader가 legacy 크기 offset(42/43/30)을 걸었으나 **follower green은 여전히 skew(16/15/12)**.
  → **offset(progression 원함: platoon이 하류 green window에 도착)과 green-skew(자기 큐 우선)가 충돌**
  → platoon이 skew된 green에 안 맞아 green-wave 붕괴 → offset이 순해악(urban +615 vs g1df).

## 3. leader payoff와 실제 control 선택 → 결과 (핵심 인과)

- **leader가 고르는 것**: N_P*, N_UF*(예산 2개)뿐. green/offset/metering은 follower가 정한다.
- **leader가 못 보는 것**: (a) 방류의 horizon-밖 배수 이득(→ under-release), (b) green과 offset의
  **공동최적성**. leader가 offset을 held-green rollout으로 골라 하달해도, follower는 그 offset에서
  green을 **selfish 재-solve**한다. leader offset은 *옛 green* 기준 최적, follower green은 *새 offset*
  기준 최적 — 한 번의 Gauss-Seidel sweep이라 (green,offset)가 **co-converge 안 된다**. legacy는 joint라
  이 cross-coupling(∂²TTT/∂green∂offset)을 내부화한다.
- **결과**: offset을 상위단이 잡을수록(GLEADOFF) green과 더 어긋난다 = 사용자 지적 그대로.
  "offset을 상위단에서 잡으면 follower가 그 externality를 못 봐서" → 정확히 green이 offset을 못 보고
  skew를 유지하는 것.

## 4. 이걸 green price / metering externality로 표현 가능한가

**부분만 가능. 핵심(arterial joint)은 per-follower 가격으로 불가.**

- **N_UF 방류(분기1)**: **가능**. leader 목적에 **urban accumulation/drainage 항**(망 무관 신호)을
  더하면 leader가 스스로 고방류를 택한다(Step1이 −650 실증). 이건 externality라기보다 leader의
  cost-to-go 보정(horizon 절단 교정). + 억제 gate 3종 완화.
- **arterial green×offset(분기2)**: **per-signal 가격으로 표현 불가**(F3·probe 확증). 이유:
  - green price `g_ext=∂(globalTTT)/∂green`은 *현재 offset에서* 평가되니 follower가 green 방향은
    본다. 그러나 (i) follower own-TTS(자기 큐)의 skew 유인이 price nudge(±6s trust)를 압도하고,
    (ii) 진짜 이득은 **inter-signal**(A의 offset이 보낸 platoon이 B의 green window에 도착) — 이건
    A·B의 offset과 B의 green의 **joint** 함수라 단일신호 ∂/∂green_B로 못 나른다. green×offset
    cross-term은 intra-signal ≈0(probe 0.14%), 값은 inter-signal에 있다.
  - 즉 arterial 조정은 **"가격화 불가능한 joint 조정"** — Weitzman 관점에서 offset은 절벽/이산이
    아니라 **강결합 연속 joint**라, 분산 가격이 아니라 **corridor 수준 joint 평가**가 필요하다.

## 5. 어떻게 따라잡나 — 추가 검토 요소(기존 논의 넘어)

### Route A — 방류(~30%, 독립·값쌈·일반화): 가장 가까운 레버
1. **leader 목적에 urban-pressure/terminal 항**: urban 총 accumulation(또는 boundary+storage 큐)에
   비례한 cost-to-go를 더해, 방류의 장기 배수 이득을 horizon 안으로 당김. (w_boundary_in이 현재 **0**
   — 켜는 것부터.)
2. **rho_crit 억제 3종 재조정**: F1 hinge / density_headroom 캡 / w_F density penalty. **NORHO
   최종 결과(F1 hinge + density_headroom 캡 2종 제거) = 12252.9, g1df 대비 +380(+3.2%) 악화,
   STOP 위반.** 결정적: **N_UF가 4983으로 오히려 g1df(5084)보다 낮음** — 캡을 풀어도 leader가
   방류를 더 안 한다. → **rho_crit 캡은 under-release 원인이 아니다**(leader의 horizon+payoff가
   원인). 캡 제거는 freeway 안전만 잃어 late-congestion서 +380 악화. → **캡 제거가 아니라 목적함수
   보정(1)이 정답**임을 실증. leader가 *원해서* 고방류를 *선택*하게 하는 payoff 항이 핵심.

### Route B — arterial green×offset 공동설계(~70%): 진짜 남은 격차
사용자 가설의 처방 = **green을 offset과 함께 움직이게** 만들기. 후보(비용 오름차순):
1. **corridor 수준 (green,offset) joint 블록**: A-B-C를 한 sub-problem으로 green split+offset을
   **동시** 최적화(legacy식이되 corridor로 국한, corridor 간은 분산). green이 progression에 맞춰
   균등화되어 offset과 상보. **가장 유력** — probe가 "값은 inter-signal corridor에 있다"고 지목한 자리.
2. **leader offset ↔ follower green 반복(co-convergence)**: 한 sweep이 아니라 (offset|green)↔(green|offset)
   를 수렴까지. 단 per-signal green이 여전히 inter-signal platoon을 못 보면 불충분 → (3)와 결합 필요.
3. **green 목적에 platoon-arrival 정렬 항**: 상류 offset이 만든 도착 window에 green phase를 맞추는
   보상(∂TTT/∂(green_phase vs platoon))을 corridor 평가자가 per-signal directive로 하달. green price와
   다른 종류의 신호(위상 정렬) — legacy joint가 암묵적으로 쓰는 것을 명시화.
4. **green 균등화 유도**: offset을 걸 때 follower green을 offset-호환(더 균등/위상정렬)으로 nudge —
   leader가 (offset, green-target) **쌍**을 하달. GLEADOFF 실패의 직접 처방(offset만 주지 말고 green도).

### 추가로 검토할 요소(새로 부상)
- **green×offset 상보성 자체가 새 프레임**: 문제는 "offset 추가"가 아니라 "green+offset 공동설계".
  legacy의 낮은 green skew(8/4/8)가 목표 상태 — 우리 follower의 높은 skew(16/15/12)를 낮추는 게 핵심.
- **w_boundary_in=0**: 경계 유입 큐가 leader 목적에서 무가중 — legacy가 경계큐를 관리하면 여기서도
  격차가 샐 수 있음(§CLAUDE.md 요구항목: boundary queue balancing 명시 평가). 켜서 측정 필요.
- **leader 시야(horizon 3스텝/9분)**: 방류·큐 배수의 장기성을 못 봄. terminal value/긴 유효 horizon이
  Route A의 근본. (레버가 아니라 payoff의 시간지평 문제.)

## 6. 산출물
- 데이터: 2026-07-06/results/trajectories/{g1df,g1all,b2tr}_sweet190_7200/,
  2026-07-07/results/trajectories/gleadoff_mpc_sweet190_7200/. legacy는 보고서 집계(§1, legacy raw는
  outputs, gitignore).
- 선행: reports/legacy_gap_decomposition_20260706.md(Step1/2/3),
  reports/leader_offset_verdict_20260707.md(GLEADOFF 판정).
