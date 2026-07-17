# paper_package/data — 런 산출물 (2026-07-17)

구조: `<arm>/<cell>/{run_log, control_timeseries, state_timeseries, decision_diagnostics}.csv`

| arm | 구성 | 역할 |
|---|---|---|
| walk_mvg | 최종 컨트롤러(BOX_WALK+VG+VSL_BOX+METER_BOX+PD4+③) | 논문 본문 |
| farsa_ref | ③ (구 동결: PD·박스 없음) | §5 비교 앵커, 200_w 서사 |
| pd4_ref | PD4 (박스 없음) | 진동·bang-bang의 원인 상태(§2a·§3a) |
| box300_vsl10_ref | 박스만 (walk 없음) | walk ablation 짝(§2b intent 고착) |

셀: 논문 5셀(155_w, 170_w, 170_skew15_w, 170_incident_w, 190_w) + **200_w(§5 한계 전용)**.
채점: wTTT = cum_total_ttt[끝] − cum_total_ttt[step20 행]. PFO 기준선 수치는
ANALYSIS_PLAN_FINAL.md §0.4. **컬럼 함정 사전(§0.5) 필독.**
