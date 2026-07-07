# 2026-07-08 작업 노트

## 1. Terminal cost 실측 근거 (리포트) — rollout-V 설계 실증

`reports/terminal_cost_empirical_evidence_20260708.md` 참조. 다른 머신의
`terminal_cost_value_function_design_20260707.md`(모든 lever price=∂(TTT+V)/∂lever, V=rollout-V 통일)의
실증 backbone. 핵심:

- **forced-VSL**(throttle-FD): 지속 VSL 100→60이면 total 12733→12441·urban −349·방류 +322. VSL은
  죽은 게 아니라 **temporal myopia로 안 켜지는** 살아있는 lever(merge 재배분 externality).
- **extended-horizon marginal**(9/30/60분): release·VSL 가치가 horizon 밖에서 **10~180× 커지고 state-의존·
  부호 뒤집힘**(step17 빈 ramp 방류는 60분서 +181 손해). → **congestion-aware V 필수**, static free-flow 불충분.
- **(C) probe**: free-flow T upside 약함 + density downside **무디고**(단일 w_D가 buildup 억제↔peak 허용
  동시 불가) throttle서 VSL **역방향**. → 해석적 terminal 실패 실증.
- **(C-2) 반증**: 실측 밀도가 역신호(step17 나쁨=밀도33~49 낮음, step23 좋음=jam95). **진짜 축은 ramp 큐**
  (7 vs 117)=고전 ramp metering. static density 형태 근본 부적합 → rollout-V 정당화.
- **두 축**: release=temporal(V), green=spatial(price), VSL=둘 다(FD+V+price), offset=joint price.
  "objective 전체 marginal 구하자"는 green/공간엔 정답이나 시간축은 J에 V 항 필요(marginal은 읽는 법이지
  고치는 법 아님).
- **다른 머신 진척**: rho_crit(VSL)을 nu_cong/receiving에 전파(내가 flag한 caveat 완료, 커밋 1a7c17e),
  ALLPRICE HORIZON sweep{3,5,8} 진행. PFO new-FD=10013(floor).
- **정정**: (2)VSL죽음·joint코어·receiving→0·free-flow T강함·C-2 전부 철회/폐기(리포트 §7).
- **열린 문제**: static 근사 부족 확정 → rollout-V 깊이 d↔legacy 회수율 frontier(설계 §4 sweep이 측정 중).
