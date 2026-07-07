# Terminal cost 실측 근거 — beyond-horizon 가치의 congestion-의존·부호뒤집힘 (rollout-V 설계 실증) 2026-07-08

작성 2026-07-08. `reports/terminal_cost_value_function_design_20260707.md`(rollout-V 통일 설계)의
**실증 backbone**. 내 머신 진단, throttle-FD(two_branch OFF) 기준. 절대 TTT는 FP차 있어 **구조·부호**를 봄.

## 0. 요약 — 오늘 실측이 rollout-V 설계를 뒷받침

세 probe가 설계의 핵심 주장을 실측으로 확증했다.
1. **forced-VSL**: VSL은 죽은 lever가 아니라 **temporal myopia로 안 켜지는** 살아있는 lever(지속 강제 시 total↓).
2. **extended-horizon marginal**: release·VSL의 진짜 가치는 **horizon 밖에서 10~180× 커지고, state-의존이며 부호가 뒤집힌다** → **congestion-aware V 필수**(free-flow prior로 불충분).
3. **(C) terminal cost probe**: free-flow T(안2)는 방향만 약하게 맞고, density downside는 **무디고 역신호** → **해석적 terminal 실패 실증**(=rollout-V가 답인 이유).

## 1. forced-VSL — VSL은 temporal myopia로 안 켜질 뿐 (throttle-FD)

sweet_190 7200s, freeway 상류 VSL을 처음부터 지속 강제(closed-loop, B2TR계열).

| VSL | total | urban | N_UF mean | rho_merge |
|---:|---:|---:|---:|---:|
| 100(강제없음) | 12733 | 11098 | 4862 | 40.2 |
| 80 | 12529 | 10820 | 5093 | 42.4 |
| 60 | **12441** | **10749** | **5184** | 42.7 |

- VSL↓ 단조로 **total↓·urban↓·방류↑**. freeway가 소폭 손해(+57) 지고 urban이 크게 이득(−349) =
  **merge 재배분 externality**(mainstream metering, throttle-FD서도 실재).
- 컨트롤러는 VSL을 상한 방치 → **강제해야만** 이득 나옴 = **beyond-horizon 가치를 9분이 못 봐서**.
  (VSL memory: 무제어 시 VSL 0/20 이동.)

## 2. extended-horizon marginal — 가치는 horizon 밖·state 의존·부호 뒤집힘

fixed로 전진 후 각 state에서 rollout을 3/10/20 step(9/30/60분)으로 늘려 d(TTT)/d(lever) 측정(음=이득).

| state | lever | 9분 | 30분 | 60분 |
|---|---|---:|---:|---:|
| step10 buildup(rampQ5) | g_release | −9 | −108 | **−185** |
| step17 buildup(rampQ5) | g_release | −8 | **+3** | **+181** |
| step22 peak(rampQ56) | g_release | −1 | −16 | **−53** |
| step22 peak | g_vsl(100→60) | −0.3 | −36 | **−182** |

- **beyond-horizon 가치 실재**: 9분 ~0인데 60분서 10~180× → 9분 근시가 under-use의 주범. terminal
  cost가 잡을 게 확실히 있음(설계 §2.2 실증).
- **부호가 state 따라 뒤집힘**: step17(빈 ramp)선 방류가 60분서 **+181(손해)** — 빈 ramp에 방류=freeway
  선제 flood=장기 붕괴. peak(step22)선 방류·VSL 모두 큰 이득. → **cost-to-go는 congestion-의존, static
  weight로 못 잡음**(설계 §2.5 "congestion-aware V" 실증).

## 3. (C) terminal cost 검토 — free-flow T 약함 + density downside 무디고 역방향

(C)=9분 base TTT + V_f(=free-flow T(loc) upside + w_D·밀도초과 downside). §2의 60분을 정답 부호로 채점.

| state | lever | 정답(60분) | w_D=0 | w_D=2 | w_D=8 |
|---|---|---:|---:|---:|---:|
| step11 buildup | release | −131 | −10 ✓ | −10 ✓ | −10 ✓ |
| **step17 flood** | release | **+225** | −3 ✗ | **+128 ✓** | +523 ✓ |
| step17 | vsl↓ | −66 | +7 ✗ | +119 ✗ | +456 ✗ |
| **step23 peak** | release | **−55** | −6 ✓ | **+13 ✗** | +68 ✗ |
| step23 | vsl↓ | −235 | −4 ✓ | +37 ✗ | +159 ✗ |

- **free-flow T upside 포착 약함**(부호는 맞으나 −10 수준). 위치 불변에 가까움 — routing 그림이 담당하는 부분.
- **density downside는 개념 검증되나 무딤**: step17 flood를 w_D=2가 −3→+128로 **잡음**(방향 성공).
  그러나 **같은 w_D=2가 step23 peak release를 −6→+13으로 망침**. 단일 w_D가 buildup 억제↔peak 허용을
  동시에 못 함 = **density가 "좋은 밀도/나쁜 밀도"를 못 가림**.
- **VSL은 throttle서 통째로 역방향**: throttle VSL이 밀도를 올리므로 density penalty가 VSL↓를 벌줌
  (정답 반대). → VSL 채널은 **two-branch FD 필수**(다른 머신 검증 대상).

## 4. (C-2) 반증 — density는 역신호, 진짜 축은 ramp 큐

"near-jam만 벌점"(C-2) 가설을 실측 밀도로 검증.

| state | rampQ | release 정답 | freeway 밀도(rho_max=95) |
|---|---:|---|---|
| step17 flood | 7 | **BAD** | 33·49 (**낮음, jam서 멀다**) |
| step23 peak | 117 | **GOOD** | 93·95 (**jam에 붙음**) |

- **밀도가 정반대**: release가 나쁜 state=낮은 밀도, 좋은 state=jam. → "near-jam 벌점"은 **좋은 state를
  벌주고 나쁜 state를 봐줌** = **(C-2) 폐기.**
- **진짜 구분축은 ramp 큐(7 vs 117)**: buildup(빈 ramp)엔 조이고 peak(찬 ramp)엔 푸는 **고전적 ramp
  metering**. 밀도는 역신호. → 어떤 **static density 형태도 근본 부적합** = **설계의 "rollout-V(집계 아닌
  spatial+congestion)" 정당화.**

## 5. 두 축 지도 (설계 §3.4와 정합)

| lever | 근시 축 | 도구 |
|---|---|---|
| release | temporal | terminal cost / V(집계 MFD로 싸게 가능) |
| VSL | temporal + spatial | V(FD 필요) + price |
| green | spatial(within-horizon) | objective marginal(price) |
| offset | spatial(joint) | price(단 per-signal≈0, joint 필요) |

- **"objective 전체의 marginal 구하자"**(사용자 제안)는 **green·공간 협조엔 정답**(∂(TTT+V)/∂lever). 단
  **release/지속 VSL의 시간축은 J에 V 항이 들어가야** 그 marginal이 살아남 — marginal은 J를 "읽는 법"이지
  "고치는 법"이 아님. 순서: (1)V로 J를 맞게 → (2)그 marginal을 협조에 사용. **설계의 통일식과 동일.**

## 6. 20260707 rollout-V 설계와의 정합 (핵심)

- **설계 §2.5(congestion-aware V)**: §2의 부호 뒤집힘(step17 +181)이 직접 실증 — static free-flow(안2)로는
  방류의 나쁜 타이밍을 못 걸러냄.
- **설계 §3.4(cheap-general spatial 없음)**: §4의 "density 역신호 + ramp 큐가 진짜 축"이, 집계/static으로
  spatial·temporal 구분이 안 됨을 보여 → rollout 깊이 d가 불가피함을 뒷받침.
- **설계 §3.3(rollout-V 일반화)**: §3의 free-flow T upside 약함이 "해석적 형태의 취약성"을 실증 → plant만
  쓰는 rollout-V가 우회로.
- **정직한 잔여**: static 근사(안2/density)는 **부족** 확정. rollout-V의 **깊이 d↔legacy 회수율 frontier**가
  유일한 열린 문제(설계 §4 sweep이 그 답을 측정 중).

## 7. 정정 이력 (오독 방지)
- "(2) VSL externality 죽음" → **철회**(§1 forced-VSL이 이득 실증). throttle probe가 myopic+무제어라 오판.
- "joint price가 코어 기여" → **약화**(9분 g 왜소, hidden-space). terminal cost/V가 주.
- "receiving→0" → **철회**(peak서 0.85).
- "free-flow T(안2)가 강함" → **철회**(§3 upside 약함·downside 무딤). congestion-aware/rollout 필요.
- "near-jam downside(C-2)" → **폐기**(§4 density 역신호).

## 부록 — probe 스크립트(scratchpad, 재현용)
vsl_sustained_test.py(§1), extended_marginal_probe.py(§2), terminal_cost_C_probe.py(§3),
joint_g_probe.py(price 상보성), vsl_merge_probe.py(myopic 오판 원본).
