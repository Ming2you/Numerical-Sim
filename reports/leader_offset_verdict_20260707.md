# LEADER-OFFSET 판정 — offset을 leader가 소유해도 격차는 안 닫힌다 (오히려 +4.5% 악화) 2026-07-07

## 0. 핵심 결론

- **GLEADOFF-MPC(leader가 전 신호 offset을 joint 결정) = 12403.978 vs g1df baseline 11872.919
  → +531 (+4.5%) 악화.** 성공 기준(< g1df) 실패 + STOP 기준(>1% 악화) 위반.
- **메커니즘은 완전히 작동했다**: offset_A~F 전부 적용, std 30~43(= legacy 28~45 수준),
  offsets_kept 4.12/5(follower 가드 우회로 실제 커밋). "안 걸림" 실패가 아니라 **"legacy 크기의
  offset을 실제로 걸었는데 urban을 +615 악화"**.
- **누적 이득 가설 기각(사용자 가설 실증 검증)**: 초반(step≤17)엔 g1df 대비 −8~10 앞섰으나,
  혼잡 누적 구간(step 24~40)에서 단조 악화(+45→+121→+229→+366→+531). 작은 초기 이득이
  혼잡 피크에서 **역전**. 단일-스텝 proxy 이득은 closed-loop 오버새처레이션에서 반대 부호가 된다.
- **격차 ≠ offset (closed-loop 확정)**: FP-면역 corridor-joint probe(offset 상한 ≈ 격차의 7~11%,
  노이즈 하)를 7200s closed-loop이 확증하고, 한발 더 나아가 **부호가 반대**(offset은 돕는 게
  아니라 해친다)임을 보인다.

## 1. 궤적 (같은 머신, 같은 env — 델타는 FP 노이즈 아닌 실제값)

| step | g1df cum_ttt | GLEADOFF cum_ttt | Δ |
|---:|---:|---:|---:|
| 15 | 1489.06 | 1480.06 | −9.0 |
| 17 | 1898.06 | 1889.61 | −8.4 |
| 20 | 2631.46 | 2636.03 | +4.6 |
| 24 | 3849.67 | 3895.07 | +45.4 |
| 28 | 5370.91 | 5492.08 | +121.2 |
| 32 | 7226.67 | 7455.66 | +229.0 |
| 36 | 9403.64 | 9769.79 | +366.1 |
| 40 | 11872.92 | 12403.98 | **+531.1** |

분해: urban 10872.8(g1df ~10258 대비 **+615 악화**), freeway 1531.1(g1df ~1615 대비 −84 개선),
N_UF mean 4984(g1df 5084). 악화는 전량 urban — offset이 urban corridor를 de-synchronize.

## 2. 왜 해쳤나 (오버새처레이션서 progression 가정 붕괴)

- leader는 offset을 **held-green open-loop horizon rollout**으로 고른다. 하지만 (i) follower가
  새 offset에서 green을 재-solve하며 green×offset 결합이 완전히 반영 안 되고, (ii) 오버새처레이션
  에선 offset(green-wave progression)이 전제하는 자유류 platoon 진행이 붕괴한다(큐 포화 → MAXBAND/
  progression 무효, 보고서 §4 Van den Berg 지점). 그래서 horizon proxy에 대한 offset "최적화"가
  포화 네트워크를 실제로는 어긋나게 한다.
- legacy가 offset_std 45/45/28/44/35로 10729를 내는 건 **offset이 legacy의 전체 제어(중앙 green·
  metering)와 공동 설계**됐기 때문. 같은 크기 offset을 우리 분산 follower에 얹으면 나머지 제어가
  공동적응 안 돼 해가 된다. → **격차는 offset 단독이 아니라 joint 공동설계에 있다.**

## 3. 소유권 함의

- offset을 follower(g1df: D/F 국소)에서 leader(A~F joint)로 옮기니 **더 나빠졌다**. leader-joint가
  follower-국소보다 협조적이라는 기대와 반대. 이유: leader의 joint 평가도 held-green open-loop
  proxy라, 오버새처레이션의 진짜 결합(green×offset×metering×큐)을 못 본다. probe(단일 스텝)든
  leader rollout(held-green)이든 **오버새처레이션 offset 가치를 신뢰성 있게 못 잰다**는 동일 한계.
- GLEADOFF는 follower의 D/F offset(g1df 이득원)도 끄므로, offset을 leader가 다 죽이면 f1rho(12159)
  방향으로 가야 하나 실제 12404로 더 나쁨 → 걸린 A~F offset이 순해악.

## 4. 비용

mean_solve 100.7s(> legacy 94s) — 단 NORHO와 병렬 실행 경합값. 무경합 smoke는 56~65s/step.
성능 기각이라 비용 논점은 무의미(어차피 채택 안 함).

## 5. 재현·산출물

- 러너: `python -B work/run_claude_style_five_controller.py --scenario sweet_190 --T-total 7200
  --controllers P-STACK-WU-FAITHFUL-GLEADOFF-MPC`
- 궤적: `2026-07-07/results/trajectories/gleadoff_mpc_sweet190_7200/`(control/state/summary + 콘솔).
- 코드: `leader_offset_enabled`/`_solve_leader_offset`(stackelberg_wu_metered.py),
  `offset_directive_authoritative`(wu_faithful_follower.py), 러너 GLEADOFF-MPC. off=비트동일.

## 6. 함의 — 다음 레인

offset은 (분산이든 leader-joint든) 오버새처레이션 격차의 몸통이 아니다. 2B(MAXBAND-LP)는 2A의
저비용 근사인데 2A가 이미 순해악이라 **무의미**(더 싸게 나쁜 걸 얻을 뿐). 격차는 offset이 아니라
**공동설계(green split·metering budget·offset의 동시 최적화)** 또는 다른 레버(N_UF 예산·rho_crit
게이팅)에 있을 가능성 → 사용자 요청 G1DF-NORHO(rho_crit 2종 제거)로 유입 여력 가설을 병렬 검증 중.
