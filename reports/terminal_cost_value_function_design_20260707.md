# Terminal cost = value function 설계 확정 — 모든 lever를 ∂(TTT+V)/∂lever로 통일 (2260707)

작성 2026-07-07. 이 문서는 이날의 긴 추론이 수렴한 **확정 설계**와 그 근거·일반화 분석·실험 계획을
담는다. 절대 TTT는 환경 간 FP차 있어 **구조**를 본다. legacy·PFO는 같은 머신 baseline.

## 0. 한 줄 요약

**모든 제어 lever(green·offset·VSL·metering)의 marginal price를 `∂(TTT + V)/∂lever`로 통일하고,
leader는 `min(TTT + V)`로 예산 결정한다. 여기서 V는 rollout 기반 value function(cost-to-go)이며,
near는 spatial rollout(green/offset 협조·drop), far는 집계 MFD tail(배수)로 hybrid 근사한다.**
V의 rollout 깊이 d가 유일한 효율 knob이고, d=0(집계만)이 temporal, d↑가 spatial 협조를 산다.

## 1. 왜 여기 왔나 — 실패의 계보 (이 세션 실측)

sweet_190 7200s, 같은 머신, g1df=11872.9(구 FD 최선), legacy=10728.8.

| 시도 | 결과 | 교훈 |
|---|---:|---|
| GLEADOFF (leader-joint offset) | +531 | offset 단독은 arterial서 해악(green과 공동설계 필요) |
| g1all (follower 전 offset) | +765 | per-signal offset de-coordinate |
| NORHO (rho_crit 캡 2종 제거) | +380 | 캡은 under-release 원인 아님(N_UF 안 오름) |
| ramp-queue terminal cost (w1~8) | +380~888 | uniform 큐 항은 peak flat(freeway 수용)+congestion-blind |

→ 단일 lever·캡·naive 항 전부 실패. 두 축으로 분해: **(A) under-release ~30%(temporal), (B) urban
green+offset corridor 협조 ~70%(spatial).**

## 2. 추론 사슬 (설계가 나온 과정)

1. **leader marginal price가 자연스러운 전달**(P-Stack의 맛): leader가 전역 평가→price 압축→follower
   국소 사용. green/VSL/metering 모두 기존 B2/B3 price 채널 존재.
2. **9분 price는 myopic**: Codex proxy 스윕 — N_UF에 objective flat(hidden-space). 이득이 항상
   horizon 밖. → terminal cost(cost-to-go) 필요.
3. **capacity drop 실재**(정정): `capacity_drop_anticipation=True` + `freeway_offramp_capacity_drop
   lane_reduction=1.0`(default.yaml). 제어 가치=전략적 drop 회피=**congestion-의존**. free-flow
   terminal(안 2)은 drop 못 봐 방류만 밀다 drop 유발.
4. **receding replan은 systematic myopia 못 고침**: 9분 창을 3분마다 굴려도, 이득이 매 스텝 항상
   horizon 밖이면 매 plan이 같은 근시안 반복(=under-release 지속). Mayne et al.(2000): 짧은
   receding MPC는 terminal cost 없으면 tail 중요할 때 suboptimal. **reactive는 9분 OK, systematic
   tail은 terminal cost 필수.**
5. **terminal cost = value function V**, congestion-aware여야(안 1 measured), free-flow(안 2)는 방향
   prior일 뿐.
6. **freeway만 V는 비정합**: 혼잡 하 urban도 9분 넘게 갇힘 → urban도 systematic myopia. **V는
   uniform(urban+freeway).**
7. **일반화 문제**(urban 내부 sink/source): free-flow T(loc)는 routing/OD 필요, MFD V(N)은 집계라
   robust하나 **공간 blind**(∂V(N)/∂green≈0, green은 재분배라 N 불변). → **rollout 기반 V**는 plant만
   쓰므로 일반화 trivial + 공간해상(∂V/∂green≠0) + congestion-aware. **일반화 문제는 해석적 형태에만
   있었고, rollout V는 없다. 남는 건 rollout 깊이(비용)뿐.**
8. **통일**: 모든 lever price = ∂(TTT+V)/∂lever, V=rollout 기반. urban=∂(TTT+V)/∂(green,offset),
   freeway=∂(TTT+V)/∂(VSL,RM). leader=min(TTT+V).

## 3. 확정 설계

### 3.1 목적·price
```
leader 목적       :  min ( TTT_horizon + V(terminal) )
모든 lever price  :  ∂( TTT + V ) / ∂ lever    (green·offset·VSL·RM)
```
- V = terminal state의 value function(cost-to-go = 앞으로 쌓일 미래 TTT 추정, veh·h).
- 단위 정합(V도 veh·h=TTT) → weight=1 자연.
- leader가 계산(전역 congestion-aware) → follower 국소 사용(P-Stack 구조 유지).

### 3.2 V의 hybrid 근사 (효율)
```
V  =  near: 짧은 spatial rollout (depth d)      → green/offset 협조 + drop, ∂V/∂spatial ≠ 0
   +  far : 집계 MFD tail  V(N_region)          → 배수 tail, 싸게(공간 blind여도 되는 부분)
```
- **near(d스텝)**: plant를 d스텝 더 굴린 spatial rollout. green-wave·offset·VSL-drop을 봄.
- **far**: region accumulation N의 MFD cost-to-go(Geroliminis/Haddad). peak(N_crit=1142) 넘으면
  outflow↓→drain 느림→V 급증 → gridlock 회피(perimeter/gating). 이미 leader의 N_P_crit·target_penalty가
  그 씨앗.
- **d=0**: 순수 MFD(집계) → temporal(방류/drop)만, spatial 0.
- **d↑**: spatial 협조를 점점 삼. d=∞ ≈ legacy full rollout.

### 3.3 일반화 근거 (핵심 기여)
- rollout V: **plant model만** → routing/OD/sink **불필요** → 내부 sink/source 있는 실 urban에도 일반화.
- MFD tail: **집계 accumulation만** → sink-robust.
- 해석적 형태(free-flow T)의 취약성 회피. **일반화 = O, 비용 = rollout 깊이 d(효율 frontier).**

### 3.4 정직한 경계
- **temporal(방류·drop·gating)**: MFD V(N)로 **싸게·일반화되게** 해결(집계로 충분).
- **spatial(green+offset corridor)**: 집계 V로 **원리적 불가**(∂V(N)/∂green≈0) → **near rollout 깊이
  d가 드는 문제**. d 얕으면 못 삼, 깊으면 legacy 비용. **cheap-general한 spatial 해는 없다** —
  이번 세션 offset/green 실험 전패의 근본.

## 4. 실험 (진행 중) — depth vs legacy 회수율 frontier

VSL-FD plant(two_branch + rho_crit(VSL) 전파, 커밋 1a7c17e) + sweet_190 7200s, 같은 머신.

- **ALLPRICE** = F1RHO(rho_crit(VSL) 반영) + green·metering·VSL price 전부 = 모든 lever ∂(TTT+V)/∂lever.
- **V 깊이 = HORIZON env**(horizon_steps↑ → leader eval + 모든 price rollout + follower 동시 (9+d)분).
- **sweep**: HORIZON ∈ {3, 5, 8} (=9/15/24분). 실행 중(커밋 b0f686e).

**baseline(new-FD regime, 같은 머신):**
| | total | 역할 |
|---|---:|---|
| PFO new-FD (WuFaithful follower only) | **10013** | floor |
| legacy new-FD (Stackelberg+DistributedCoordinator full rollout) | (진행) | ceiling |
| 구-FD legacy | 10728.8 | 문서값 재현 확인 |

**판정 기준:** 깊이 d↑ → (ALLPRICE − PFO)가 (legacy − PFO)의 몇 %를 회수하나. 얕은 d로 대부분
회수되면 "싼 local price로 legacy 재현" 성립. temporal만 회수되고 spatial 안 되면 §3.4 경계 실증.

**다음 refine:** near rollout + **명시적 MFD tail** 구현(far-V를 집계로 싸게) → 깊이 비용 절감.

## 5. 방법론 정정 이력 (오독 방지)
- "capacity_drop off" → **철회**. dataclass 기본값만 보고 판단한 오류. 실 config는 anticipation·off-ramp
  drop 둘 다 ON(lane_reduction=1.0). 과방류는 **유계 아님**(drop 유발 가능).
- "ramp-큐 terminal cost" NO-GO → 원인 = peak flat + **congestion-blind**(drop 못 봄). 위치-graded도
  아니고 congestion-aware도 아닌 반쪽.
- "urban은 terminal-complete(green price로)" → **혼잡 하에선 철회**. urban도 systematic myopia → V에 포함.

## 6. 선행연구 (설계 근거)
- **MFD/perimeter(집계 V, urban 일반화)**: Daganzo(2007); Geroliminis & Daganzo(2008); Haddad &
  Geroliminis(2012); Geroliminis, Haddad, Ramezani(2013, MPC perimeter); Aboudolas & Geroliminis(2013,
  multi-reservoir); Keyvan-Ekbatani et al.(2012, gating).
- **store-and-forward(큐 목적)**: Gazis & Potts(1963); Diakaki et al.(2002, TUC); Aboudolas et al.(2009).
- **MPC terminal cost(정석)**: Mayne, Rawlings, Rao, Scokaert(2000).
- **통합 urban-freeway MPC / VSL·RM**: Hegyi et al.(2005); van den Berg et al.(2007); Carlson et al.(2010).
- **capacity drop**: Cassidy & Bertini(1999); Hall & Agyemang-Duah(1991); ALINEA(Papageorgiou et al. 1991).
- **plant**: METANET(Messmer & Papageorgiou 1990); anticipation ν(Arora & Kattan); Wu(프로젝트 spec,
  offramp spillback Eq.22 — docs/codex_implementation_spec.md).

## 7. 재현
- ALLPRICE sweep: `VSL_FD=1 HORIZON=k python -B work/run_claude_style_five_controller.py --scenario
  sweet_190 --T-total 7200 --controllers P-STACK-WU-FAITHFUL-ALLPRICE --output outputs/_allprice_h{k}...`
- baseline: PFO=`VSL_FD=1 ... --controllers WU-FAITHFUL-FOLLOWER-NOP1`; legacy=`VSL_FD=1 python -B
  work/run_legacy_pstack_compare.py --scenarios sweet_190 --T-total 7200`.
- 선행: rho_crit(VSL) 전파 1a7c17e, VSL-FD Codex a511be0, ramp-queue verdict 0a3d4fc,
  three_way 분석 057fe7e.
