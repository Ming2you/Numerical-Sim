# two-branch VSL-FD 구현 + 두 terminal cost 비교 계획 (2026-07-07)

/ 내 머신 진단·구현. 절대 TTT는 환경 FP차 있어 **구조·부호·단조**를 봄.

## 0. 왜 여기까지 왔나 (한 줄 요약들)

- **forced-VSL 실측**(sweet_190 7200s, 지속 강제): VSL 100→60에서 **total 12733→12441(−292), urban
  11098→10749(−349), 방류 N_UF 4862→5184(+322)**. VSL은 **살아있는 lever**인데 컨트롤러는 상한 방치.
- **두 축 myopia 지도**: release=시간축, **VSL=시간+공간 둘 다**, offset=공간축, green=자유.
  terminal cost(시간)와 externality price(공간) 중 무엇을 언제 붙일지의 체계.
- **joint g_meter×g_vsl probe**: metering은 안 죽음(g<0)이나 **작고 peak서 flat**(−9 buildup→−1 peak,
  hidden-space), **VSL의 상보 증폭 약함**(3/4 step, 0.4~1.3). → 9분 price(단독·joint)로는 부족.
  **주처방은 terminal cost(시간)**, price는 부차.
- **정정**: receiving_factor는 peak서 0.85(안 죽음). 예전 "receiving→0" 과장 철회. metering이 flat한
  건 receiving 절벽이 아니라 hidden-space(9분 내 ramp→freeway 이동 net-zero).

## 1. two-branch VSL-FD 구현 — 완료(gated), 단위검증 PASS

### 문제
기존 VSL은 `min(desired(ρ, 고정 ρ_crit), VSL)` = **순수 속도 throttle**(`alpha_vsl=0`, ρ_crit
불변). VSL을 내려도 **capacity를 보존 못 함** → VSL의 교과서 이득(감속으로 임계밀도↑, capacity-drop
회피)을 구조적으로 못 냄. VSL 무력의 절반이 물리가 아니라 **모델 결함**이었음.

### 구현 (Anchor B — Newell/삼각형 FD, VSL=자유류 속도)
- `src/models/metanet.py`: `two_branch_vsl_speed_kmh()` 신규 + `effective_desired_speed_kmh()`에
  `two_branch`·`rho_jam` 인자 추가(기본 False → **기존 동작·테스트 불변**).
- 호출처 2곳(`metanet.py` freeway_substep, `local_freeway_plant.py`)에서
  `getattr(net,"vsl_fd_two_branch",False)`, `net.rho_max`를 넘김. **config 스키마 무변경**, 런타임
  `net.vsl_fd_two_branch=True`로 활성.
- 물리: 혼잡(right) branch를 (ρ_crit, ρ_jam)로 고정, 자유류(left) branch 기울기=VSL, ρ_crit(VSL)=
  두 branch 접점. backward-wave 속도 `w = v_free·ρ_crit/(ρ_jam−ρ_crit)`를 앵커해 VSL=v_free서
  접점=nominal ρ_crit.

### 단위검증 (합성 FD, `2026-07-07/results/two_branch_vsl_fd_curve.csv`)
| VSL | ρ_crit(VSL) | capacity(veh/h/lane) | free_speed |
|---:|---:|---:|---:|
| 100 | 33.5 | 3350 | 100 |
| 80 | 38.5 | 3078 | 80 |
| 60 | 45.0 | 2700 | 60 |
| 50 | 49.5 | 2475 | 50 |

**PASS** — VSL↓ → ρ_crit↑ + capacity↓ 단조, VSL=100 앵커가 nominal 33.5에 정확. 이게 당신이 말한
"right 고정, left가 VSL로, ρ_crit=접점" 그대로.

### 두 가지 caveat (반드시 다음에 처리)
1. **재baseline 비용**: 삼각형 nominal capacity=3350 vs 기존 exponential=1961(자유류 branch 형태
   차이). two_branch ON시 no-control 포함 **전면 재calibration** 필요(demand·ρ_crit 등).
2. **미완 coupling(핵심)**: `select_anticipation_nu`의 capacity-drop 트리거와 `compute_ramp_release_flows`
   의 receiving_factor가 **여전히 고정 ρ_crit=33.5** 사용. FD에서 VSL이 ρ_crit을 올려도 capacity-drop은
   33.5서 발화 → **FD 이득이 closed-loop서 부분만 실현**. → 다음: `ρ_crit(VSL)`을 이 둘에 전파해야
   완전. (그래야 VSL이 merge를 subcritical로 지켜 nu-drop을 실제로 피함.)

## 2. 두 terminal cost — 둘 다 구현해 비교

myopia 지도상 **주처방은 terminal cost(시간축)**. 두 형태를 만들어 어느 게 나은지 실측 비교.

### 안 2 (유력·먼저) — free-flow time-to-exit
- **아이디어**: off-ramp diversion(β)·free-flow 통과시간을 알므로 각 위치의 exit까지 기대시간
  `T(loc)`를 **Bellman 선형해**로 오프라인 계산. `T(exit)=0`, `T(loc)=tt(loc)+Σ P(loc→next)·T(next)`.
- **terminal 항**: `V_f = Σ_loc N_loc(x_N)·T(loc)` — leader objective(`leader.py:objective_terms`)에
  terminal(마지막 예측상태) 항으로 가산.
- **왜 강한가**: (a) **hidden-space 직격** — realized TTT는 위치 불변이나 T(loc)는 위치별 상이(ramp
  큐=T큼, exit근처=T≈0) → release=ramp(T큼)→freeway(T작음)가 terminal cost를 실제로 낮춤. (b)
  **generalize** — routing에서 해석적, 네트워크 커져도 재해. (c) **no legacy·no tuning**(가중치=routing).
  (d) verdict의 ramp-큐 항을 **위치-graded로 일반화한 상위판**.
- **한계**: free-flow T는 **혼잡 무시** → release/위치는 잡으나 **VSL의 capacity-drop 가치 못 잡음**.
- **담당 채널**: release / ramp hidden-space.

### 안 1 — measured marginal cost (혼잡-aware)
- **아이디어**: `T(loc)`를 static이 아니라 짧은 rollout로 측정한 **shadow price**(∇V)로 → 혼잡 반영.
  VSL이 하류를 뚫으면 measured T↓ → VSL이 terminal cost에 걸림.
- **terminal 항**: 같은 `Σ N_loc·T_measured(loc)`, 단 T를 주기적 rollout로 갱신.
- **비용**: rollout 추가 계산 + **legacy-근접 우려**(예전 value-function 회귀 걱정). VSL 채널용 2층.
- **담당 채널**: VSL / capacity(혼잡 반응).

### 채널 매핑
| terminal cost | 잡는 것 | 성격 | FD 의존 |
|---|---|---|---|
| **안 2 free-flow T** | release·위치(hidden-space) | 해석적·싸다·generalize | 무관 |
| **안 1 measured T** | VSL·capacity(혼잡) | rollout·무겁다 | FD 수정 후 강해짐 |
| (대안) freeway 밀도-초과 terminal | VSL·capacity | 단순·기존 density_penalty 확장 | **ρ_crit(VSL) 필요** |

## 3. 비교 프로토콜 (동일 머신, sweet_190 7200s)

### 컨트롤러 라인업
- **legacy** = `PROPOSED-CENTRALIZED`(CentralizedMPC mode="proposed") — 천장.
- **PFO(Pure)** = `PROPOSED-FOLLOWERS-ONLY`(WuFaithfulFollower) — 바닥.
- **P-Stack + 안 2**(free-flow time-to-exit terminal).
- **P-Stack + 안 1**(measured marginal terminal).
- (부속) FD OFF/ON 대조로 FD 기여 분리.

### baseline 현황 (현재 FD, 레퍼런스)
- **PFO**: total=**12934**, urban=**11655**, freeway=**1279** (현재 FD, 내 머신, 134s). 바닥.
- **legacy**: 최소 스크립트에서 `CentralizedMPC` **process-pool 파손**(BrokenProcessPool) →
  standalone 부적합. **`six_controller_comparison` harness로 실행 필요**(pool 정상 처리). TODO.
- 참고(이전 측정, 내 머신): legacy≈10729, G1DF≈12575.
- **격차 확인**: PFO 12934 vs legacy≈10729 → ~2200, **urban 지배**(PFO urban 11655 vs legacy urban
  ≈9201). freeway는 오히려 PFO가 낮음(1279) — 격차의 원천은 freeway 아니라 urban. 재확인.

## 4. 다음 실행 순서

1. **FD coupling 완성** — `ρ_crit(VSL)`을 `select_anticipation_nu`·receiving_factor에 전파(§1 caveat 2).
   이래야 VSL이 closed-loop서 capacity-drop을 실제로 피함.
2. **안 2 구현·시험** — leader에 free-flow time-to-exit terminal 항 → sweet_190서 **방류↑·urban↓**
   나오나(verdict의 flat 실패가 "terminal cost 자체"인지 "위치-graded 아님"이었는지 재판정).
3. **안 1 구현·시험** — measured marginal terminal(VSL 채널).
4. **legacy baseline을 harness로** 확보 → 4-컨트롤러 풀런 → 안 1 vs 안 2 우열 판정.
5. FD 전면 재baseline(§1 caveat 1)은 별도 대작업(다른 계정 머신).

## 부록 — 이번 세션 판정 이력(오독 방지)
- "(2) VSL externality 죽음" → **철회**. throttle probe가 myopic+무제어라 오판. 지속 VSL은 이득.
- "joint price가 코어 기여" → **약화**. 9분 g가 왜소(hidden-space). terminal cost가 주.
- "receiving→0" → **철회**. peak서 0.85.
- 확정: VSL lever 실재(재배분+capacity), 주병목=temporal myopia, 주처방=terminal cost(안 2 우선).
