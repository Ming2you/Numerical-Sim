# 2026-06-24 진단 노트 (Claude) — 수요-용량 보정 / leader 가치 regime

병합 plant(rho_max=95.02, freeway_lanes=2) + low_demand leader fix(uncongested_nuf_floor_frac=0) 기준
1800s 실측. 연구 방향에 중요한 발견들.

## 1. 수요 사다리가 용량 대비 잘못 보정됨 (2차로 기준)
FW_E merge 부하 vs FD 용량(≈3,922 veh/h, rho_crit 33.5·V(rho_crit)·2lane):
- medium_demand(1.0375): merge **3,772 = 96%** → 사실상 near-peak (라벨 오류)
- peak_demand(1.25): merge **4,458 = 114%** (과포화)
- demand_15(1.5): merge **5,476 = 140%** (강한 과포화)

→ "medium"이 이미 96%라 medium에서 congestion·제어 이득이 나오는 건 당연. 진짜 free-flow~과포화를
span하려면 수요를 낮춰 재보정 필요(예: medium→merge ~75~80%). freeway_lanes는 줄곧 **2**가 맞음
(config·state·setpoint_calibration_spec 모두 2차로 기준; 3차로였던 적 없음).

## 2. leader(P-Stack) 가치는 "과포화 + capacity drop" regime에 국한
1800s, capacity drop OFF(기본):
- low/medium/1.1/peak 전부 **P-Stack == PFO** (leader가 중립 선택 또는 가드 fallback).
- 이유: capacity drop OFF면 METANET 부드러운 FD라 PFO 국소최적이 이미 near-optimal → leader 여지 없음.

capacity drop ON(eq9 anticipation, nu_cong=250):
- **demand_15(merge 140%): P-Stack 748.9 vs PFO 905.9 → leader +157 veh·h(+17.3%)** (N_UF*=1200 실제 작동)
- heavy_skew(1.4 + west/east 2.0): P-Stack == PFO (비대칭만으론 부족)

→ **leader 가치는 강한 과포화(~140%) + capacity drop 활성에서만 실재.** sharp nonlinearity(capacity
drop)가 PFO를 깨야 leader 조정이 빛남. 부드러운 anticipation/convection만으론 breakdown 안 생김.

## 3. 함의 (정직한 재정립 필요)
- 구 plant(rho_max=180) 시절 P-Stack +10~14pp(peak/heavy) 결과는 **plant 보정에 민감** — rho_max
  180→95 한 번에 사라짐. plant(rho_max) 확정 전까진 헤드라인 숫자 신뢰 불가.
- 인프라·방법론은 유효. 단 (a) 수요-용량 사다리 재보정, (b) capacity drop을 기본 모델로 확정(toggle off
  아님), (c) 그 위에서 leader 가치 재평가가 선행되어야 함.

## 4. fallback guard 메모
peak P-Stack에서 stackelberg_enable_fallback=true라 매 스텝 guard가 leader 기각→PFO 선택
(leaderObj > fallbackObj). 즉 P-Stack==PFO는 "가드가 PFO로 되돌림"으로 실현. capacity drop ON·과포화에선
leader가 PFO를 이겨 guard가 leader 채택.

## 그림 (reports/figures/)
- fig_no_control_medium_segment_fd_check.png: medium no-control per-segment FD(capdrop OFF) — 혼잡 가지 도달, loop 없음
- fig_no_control_medium_fd_capdrop_on.png: 동 capdrop ON(nu_cong=150) — 산포↑, loop 여전히 없음(메모리 없음)
- fig_pfo_vs_nocontrol_peak_fd_linkmean.png: peak PFO vs no-control link-mean FD — PFO가 ρ_crit 부근 유지
- fig_demand_patterns.png: 제안 6수요 시간프로파일(설계 초안)

## 미해결 결정
- **plant rho_max: 180(구) vs 95(Codex 보정) 중 무엇이 물리적으로 맞나** — 모든 비교의 토대.
- 수요 재보정 목표 부하율(merge %)·capacity drop 기본 채택 여부.
