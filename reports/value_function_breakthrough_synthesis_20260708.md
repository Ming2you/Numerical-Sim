# Value function terminal cost 종합 — ∂(TTT+V)/∂lever 검증, 신기록, 그리고 정직한 뉘앙스 (2026-07-08)

작성 2026-07-08. 이날 설계 추론이 **첫 end-to-end 성공**(g1df 초월)에 도달한 종합. 원래(exponential)
plant, sweet_190 7200s, 같은 머신. 절대 TTT는 환경간 FP차 있어 **구조·부호·순위**를 본다.

## 0. 한 줄 요약

**leader 목적에 value function V를 넣어 `min(TTT+V)`로 방류를 결정하니, N_UF가 legacy 수준으로 회복되고
freeway 절벽 붕괴가 사라져 g1df를 처음으로 넘었다(G1DF + leader_value_depth=6 = 11356, 격차 45% 회수).
단 정직히: 우리 구현은 진짜 "값싼 terminal cost"가 아니라 "leader의 evaluation horizon 연장"이며,
승리 요인은 깊이의 양이 아니라 "leader만 깊고 follower는 myopic 유지"라는 구조다.**

## 1. 결과 — 신기록

| controller | total | vs g1df | 격차 회수 | N_UF | solve |
|---|---:|---:|---:|---:|---:|
| g1df (기존 최선) | 11873 | — | 0% | 5084 | ~90s |
| ALLPRICE d=0 | 19065 | +7192 | 붕괴 | — | — |
| ALLPRICE d=3 | 12140 | +267 | −23% | 5010 | 150s |
| ALLPRICE d=6 | 11668 | −205 | +18% | 5269 | 196s |
| **G1DF d=6** | **11356** | **−517** | **+45%** | **5668** | 178s |
| legacy (ceiling) | 10729 | −1144 | 100% | 5700 | ~254s |

- **G1DF d=6 = 세션 첫 g1df 초월.** N_UF 5084→**5668 ≈ legacy 5700** — under-release가 사실상 해결.
- **best = clean base + V**: G1DF d=6(11356) > ALLPRICE d=6(11668). metering price는 절벽이라 미세 해로움.
  **방류 회수는 leader 목적의 V가 하지 metering price가 아니다.**

## 2. 검증된 것

### 2.1 완료차량 근거 (설계의 뿌리)
짧은 prediction horizon(9분)은 **vehicle 완료(exit)의 beyond-horizon 효과를 못 본다** — TTT는 망 안에서만
누적, 방류 이득(=결국 exit)이 9분 밖이면 rollout은 비용(freeway 부하)만 보고 이득 못 봐 under-release.
V="완료까지 남을 미래 TTT" 추정이 이를 복원 → N_UF↑.

### 2.2 절벽 해결 (사용자 직관 실증)
ALLPRICE가 d=0에서 **19065 붕괴**(=F2, metering price가 절벽 못 봄)인데 depth로 **19065→12140→11668
단조 회복.** deep leader-V가 capacity drop을 봐서 `∂(TTT+V)/∂metering`이 과방류를 억제 → 붕괴 소멸.
"linear price가 절벽 못 잡는다"는 naive 9분/static V 얘기였고, **congestion-aware deep V면 잡힌다.**

### 2.3 구조가 성패를 가른다 (사용자 지정이 정확)
- **V는 leader의 full coupled rollout(`_predict`, leader 전용)로만** 계산 → **follower는 myopic-3 유지.**
- `mpc.horizon_steps`를 통째로 8로 늘리면(follower까지 깊어짐) **+594 악화**. leader-only depth=6은 **−517.**
  **같은 깊이, 반대 결과** → "얼마나 깊냐"가 아니라 **"누가 깊냐"**가 핵심.

## 3. 정직한 뉘앙스 (사용자 지적, 2026-07-08)

**"horizon>3면 terminal cost 이유 없어지지 않나?"** — 원칙적으로 옳다:
- horizon이 완료를 덮을 만큼 길면 rollout이 완료를 직접 봐 terminal cost 불필요(Mayne et al. 2000:
  terminal cost = 긴 horizon의 값싼 대체).
- 긴 horizon이 공짜 아닌 이유: (1)비용 (2)open-loop 열화(control 고정 rollout이 replan과 어긋남).

**→ 그래서 우리 `leader_value_depth`는 진짜 "값싼 terminal cost"가 아니라 "leader의 evaluation horizon을
3+d로 늘린 것"이다.** 승리 요인 = follower decision은 3 유지(열화·비용 회피)하고 leader만 멀리 봄. 즉
**"긴 leader horizon + 짧은 follower horizon"** 이지, rollout 없는 cheap V가 아니다.

**진짜 값싼 terminal cost = horizon 3 유지 + 목적에 값싼 value function(MFD accumulation V(N)) 추가
(긴 rollout 없이).** 미구현. 깊이 frontier("leader가 얼마나 멀리 봐야 하나")를 좋은 V가 줄이는 게 다음 목표.

## 4. 남은 것

- **잔여 627**(11356 vs legacy 10729) = **spatial 협조(green+offset corridor)**. accumulation/temporal은
  (긴 leader horizon으로) 풀렸으나 spatial은 집계 V로 불가 — 별개 hard(이 세션 offset 실험 전패와 정합).
- **깊이 frontier 미완**: d=6이 최적인지 — g1df d∈{3,9,12} sweep으로 확정 필요(더 깊으면 더 회수? 열화 반전?).
- **cheap V 구현**: MFD V(N)을 목적·price에 추가해 leader horizon을 3으로 줄이며 성능 보존 — 진짜 목표.
- **교차검증**: 155/128 미실시. two_branch 재calibration(Codex rho_crit_two_branch)판 검증도 미실시.

## 5. 실험 계보 (이 세션, 왜 이게 이겼나)

| 시도 | 결과 | 왜 |
|---|---:|---|
| GLEADOFF / g1all offset | +531 / +765 | spatial 협조는 leader-joint·follower-selfish 둘 다 실패 |
| NORHO (rho_crit 캡 제거) | +380 | 캡은 under-release 원인 아님(payoff/horizon이 원인) |
| ramp-queue terminal (static) | +380~888 | static·congestion-blind·위치 무차별 |
| horizon_steps bump (전부 길게) | +594 | follower까지 깊어져 open-loop 열화 |
| **leader_value_depth (leader만 깊게)** | **−517** | **완료 효과를 leader가 보되 follower는 안 흔듦** |

## 6. 재현·산출물
- `LEADER_V_DEPTH=6 python -B work/run_claude_style_five_controller.py --scenario sweet_190 --T-total 7200
  --controllers P-STACK-WU-FAITHFUL-G1DF`
- 코드: `leader_value_depth`(state.py MPCConfig, 기본 0=비트동일), `_predict`/`_leader_evaluation_base`
  (stackelberg_mpc: leader full rollout base+V), LEADER_V_DEPTH env(runner). 커밋 528278d.
- 궤적: 2026-07-08/results/trajectories/leader_value_depth/. 판정 상세: reports/leader_value_depth_verdict_20260708.md.
- 선행 설계: reports/terminal_cost_value_function_design_20260707.md. Codex 실증: reports/terminal_cost_empirical_evidence_20260708.md.
