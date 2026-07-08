# leader-full-rollout value function 판정 — ∂(TTT+V)/∂lever 설계 검증, 신기록 (2026-07-08)

작성 2026-07-08. `terminal_cost_value_function_design_20260707.md` 설계의 **첫 end-to-end 검증**.
원래(exponential) plant, sweet_190 7200s, 같은 머신.

## 0. 핵심 결론 — 설계가 작동한다, 신기록

- **G1DF + leader_value_depth=6 = 11356 = 세션 첫 신기록**(g1df 11873 대비 −517, legacy 격차 1144의
  **45% 회수**). **N_UF=5668 ≈ legacy 5700** — deep V가 방류를 legacy 수준으로 회수(under-release 해결).
- **freeway 절벽 해결**(사용자 직관 실증): ALLPRICE가 depth=0에선 **19065 붕괴**(=F2, metering price가
  절벽 못 봄)인데 depth로 **19065→12140→11668 단조 회복** — deep leader-V가 capacity drop을 봐서
  `∂(TTT+V)/∂metering`이 과방류를 억제 → 붕괴 소멸.
- **왜 이번엔 됐나(=이전 horizon-bump 실패와의 차이)**: V를 **leader의 full coupled rollout(`_predict`)
  로만** 계산 → `_predict`은 leader 전용이라 **follower는 myopic-3 유지.** leader만 멀리 보고(V) follower를
  안 흔든다. horizon_steps bump(+594 악화)은 follower까지 깊어져 열화된 것. **사용자 지정("V는 follower
  myopia 아니라 leader full rollout하에서")이 정확히 그 차이.**

## 1. 결과

| run | total | vs g1df | 격차 회수 | N_UF | solve |
|---|---:|---:|---:|---:|---:|
| ALLPRICE d=0 (기존) | 19065 | +7192 | 붕괴 | — | — |
| ALLPRICE d=3 | 12140 | +267 | −23% | 5010 | 150s |
| ALLPRICE d=6 | 11668 | −205 | +18% | 5269 | 196s |
| **G1DF d=6** | **11356** | **−517** | **+45%** | **5668** | 178s |
| g1df (baseline) | 11873 | — | 0% | 5084 | ~90s |
| legacy (ceiling) | 10729 | −1144 | 100% | 5700 | ~254s |

- **깊이 단조**: d↑ → N_UF↑ → total↓ (ALLPRICE 19065→12140→11668, N_UF 5010→5269). horizon-bump의
  비단조와 대조 — leader-only 깊이라 안정적.
- **best = clean base + deep V**: G1DF d=6(11356) > ALLPRICE d=6(11668). metering price는 절벽이라
  (deep V가 붕괴는 막아도) 미세 해로움 → **방류 회수는 leader 목적의 V가 하지 metering price가 아님.**
- **비용**: follower 불변이라 ~1.3-2×(g1df 90s → d=6 178s). legacy(254s)보다 쌈.

## 2. 메커니즘 (설계 §3.1 실증)

- leader 목적 `min(TTT_3 + V)`, V = leader full rollout(3+d) tail TTT. → leader가 방류의 **horizon-밖
  배수 이득**을 봄 → N_UF 5084→5668(≈legacy).
- price `∂(TTT+V)/∂lever` → deep V가 절벽을 담아 metering 과방류 억제(붕괴 소멸).
- **V가 절벽을 "접근할수록 급증하는 연속 비용"으로 만들어** linear price가 국소 gradient로 절벽을 표현
  → 사용자의 "value function이 절벽 해결" 확인.

## 3. 남은 것 (정직)

- **잔여 627**(11356 vs legacy 10729): §설계 §3.4의 **spatial 협조(green+offset corridor)** — V(leader
  full rollout) price가 부분 회수하나 완전치 않음. accumulation/temporal은 V로 풀렸고, spatial은 hard.
- **깊이 sweep 미완**: d=6이 best인지, 더 깊으면 더? g1df d∈{3,9,12} 후속으로 frontier 확정 필요.
- **교차검증**: 155/128 미실시.

## 4. 재현
- `LEADER_V_DEPTH=6 python -B work/run_claude_style_five_controller.py --scenario sweet_190 --T-total 7200
  --controllers P-STACK-WU-FAITHFUL-G1DF`
- 코드: `leader_value_depth`(state.py MPCConfig), `_predict`/`_leader_evaluation_base`(stackelberg_mpc,
  leader full rollout base+V), LEADER_V_DEPTH env(runner). 커밋 528278d. 기본 0=비트동일.
- 궤적: 2026-07-08/results/trajectories/leader_value_depth/.
