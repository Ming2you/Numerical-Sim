# ramp-queue terminal cost 판정 — NO-GO (항은 발화하나 freeway 수용력에 막혀 방류 회수 실패) 2026-07-07

## 0. 핵심 결론

- Codex "ramp = hidden space" 처방(leader objective에 선형 ramp-큐 terminal cost 추가 → 방류
  회수)을 NORHO 베이스 + weight 스윕 w∈{1,2,4,8}로 sweet_190 7200s 실행. **전 weight가 g1df
  (11872.9)보다 나쁘고, 항 없는 NORHO(12252.9)보다도 나쁨.** → **closed-loop NO-GO.**
- **항은 정상 발화**(ramp_queue_penalty mean w1=63 → w8=445, 8× 스케일). 그런데 **peak N_UF이
  w=1이든 w=8이든 똑같이 ~4500** — penalty를 7배 키워도 방류 안 늘어남.
- **이유 = 큰 penalty인데 N_UF 방향 gradient가 0(flat).** peak엔 freeway merge 포화
  (receiving_factor = (rho_max−rho_merge)/(rho_max−rho_crit) → 0)라 budget 무관하게 차가 못
  건너감 → `ramp_queue_veh`가 N_UF에 flat → **큰 상수 penalty ≠ lever**.
- **Codex의 static proxy(_proxy_score_candidate, state 복사본) 한계 노출**: proxy는 freeway
  포화를 못 봐 objective만 flat이라 봤으나, 실제는 **항 자체가 peak서 N_UF에 flat**. 방류의 진짜
  병목은 objective가 아니라 **freeway 수용력**.

## 1. 응답곡선 (sweet_190 7200s, 같은 머신 = 실제 델타)

| | total | urban | N_UF mean | peak N_UF | ramp penalty mean |
|---|---:|---:|---:|---:|---:|
| g1df (baseline) | **11872.9** | 10258 | 5084 | — | — |
| NORHO (항 없음) | 12252.9 | — | 4983 | — | 0 |
| RQ w=1 | 12713.7 | 11333 | 4906 | ~4500 | 63 |
| RQ w=2 | 12650.0 | 11345 | 4972 | ~4500 | — |
| RQ w=4 | **12381.9** | 11061 | 5029 | ~4500 | — |
| RQ w=8 | 12760.6 | 11445 | 4972 | ~4500 | 445 |

- 전 weight worse. w=4가 미세 best(N_UF mean 5029로 근소 최대)지만 **여전히 +509 vs g1df, +129 vs
  NORHO**. 비단조(w4 dip)는 노이즈 수준.
- **N_UF mean이 4906~5029로 NORHO(4983)와 사실상 동일** — 항이 방류를 못 늘림.

## 2. N_UF 궤적 (w=8) — 항이 buildup 선제 방류조차 못 만듦

```
step: 0    1    2    3    4    5   ...  12   ...  20-29(peak)  ...  30  31 ...
N_UF: 6000 6000 6000 6000 5550 5100 ... 4575 ...  ~4500        ...  5700 5700
```
- 초반 **빈 망(step0-3)엔 6000 방류**(ramp 큐 없어 무의미), 정작 큐 형성 buildup·peak엔 **4500으로
  컷**. "buildup 선제 방류로 peak 예방"이라는 의도가 실현 안 됨.
- peak서 방류를 컷하는 건 freeway가 차서(density_penalty + 물리적 수용 한계) — 항이 이걸 못 이김.

## 3. 왜 항이 무력한가 (calibration + closed-loop 일치)

- **보정(rampq_calib, FP-면역)**: buildup(step20)선 w↑→argmin N_UF↑(약한 gradient), **peak(step26/32)
  선 ramp_queue_veh가 N_UF에 flat**(2157 vs 2155). closed-loop이 이를 확증 — peak N_UF가 weight
  무관 ~4500.
- **penalty는 크나(445) flat이라 argmin 불변**: leader는 "ramp 큐 비용이 4275 방류든 6000 방류든
  똑같이 445" → 더 방류할 이유 없음. gradient가 0인 곳에 큰 상수를 얹은 셈.
- total이 오히려 **악화**된 건, 유효하지 않은 항이 N_P·초반 N_UF 등 다른 결정을 미세 교란(무의미한
  step0-3 과방류 등)하기 때문.

## 4. 함의 — 방류 lever는 leader payoff가 아니다

- legacy는 **같은 밀도(rhoE 37.1)에서 N_UF 5700**을 낸다. 물리적으로 불가능한 게 아님 — legacy의
  **전체 협조 제어**(freeway 관리로 merge를 jam 안 시키며 방류 유지, 또는 buildup서 포화 전에 방류)로
  달성. 우리 분산 제어는 freeway를 jam시켜 merge가 닫히고 → 방류 불가 → ramp 큐 backup.
- 즉 under-release는 **objective 결함(Codex)만이 아니라, freeway가 포화되도록 둔 협조 실패의 하류
  증상**. leader objective 항으로는 못 고침(freeway가 안 받는 걸 유인 못 함).
- **다음 lever 후보**: (a) freeway merge를 acceptant하게 유지하는 freeway 제어(metering/VSL 협조로
  merge cell을 rho_crit 근처로 유지), (b) buildup서 포화 전에 방류(선제) — 단 leader 항이 아니라
  freeway 상태를 직접 보는 제약/제어, (c) 결국 green+offset+metering joint 협조(§three_way 보고서).

## 5. 산출물
- 궤적: 2026-07-07/results/trajectories/rampq_NORHO_w{1,2,4,8}_sweet190_7200/.
- 코드: leader.py w_ramp_queue 항(flag 기본 0=비트동일), 러너 NORHO-RQ/GLEADOFF-RQ(env RAMPQ_W).
- 선행: reports/ramp_hidden_space_20260707.md(Codex 처방), reports/three_way_legacy_gap_analysis_20260707.md.
