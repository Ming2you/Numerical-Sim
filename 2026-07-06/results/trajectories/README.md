# G1DF 및 baseline 전체 궤적 데이터 (sweet_190/155/128, 7200s)

분석용 raw 궤적. `outputs/`는 gitignore라 여기에 tracked 사본으로 올린다.

## 폴더 (각 run: control/state/run_log/decision_diagnostics.csv + summary.json)

| run | 구성 | 비고 |
|---|---|---|
| g1df_sweet190_7200 | F1RHO + D/F offset | **분석 주 대상** |
| g1df_sweet155_7200 | 〃 | |
| g1df_sweet128_7200 | 〃 | |
| g1all_sweet190_7200 | F1RHO + 전 신호 offset | G1DF 대비(A/B/C offset 해악) |
| f1rho_sweet190_7200 | F1RHO (offset 없음) | **같은 env baseline** |
| b2tr_sweet190_7200 | B2TR (green 가격+trust) | **같은 env baseline** |

## ⚠ 머신-환경 caveat (반드시 읽을 것)

- 이 6개 run은 **전부 같은 툴 env**(mean_solve ~80–95s/step)에서 실행됨 → **이들 사이 델타는 유효**.
- 그러나 **절대값은 이식 불가**: 과포화 7200s는 혼돈적으로 FP 민감(leader argmin이 BLAS/SIMD
  반올림에 뒤집혀 40스텝 누적 발산). 다른 하드웨어(compute 51s급)에선 절대 TTT가 ~700 다를 수 있음.
- **cross-machine 단일점 비교 금지.** 델타 부호가 두 독립 env에서 일치할 때만 실물 개선으로 인정.
- 각 머신 내부는 결정론적(재실행 비트 동일). backend는 serial(병렬 FP 순서 아님).

## 주요 진단 컬럼 (control_timeseries.csv)

- `N_P_star`, `diag_wu_faithful_lambda_P`, `diag_wu_faithful_lambda_next`: N_P dual λ_P.
- `diag_wu_faithful_sum_nin`, `diag_leader_selected_realized_N_P_star`: 실현 순유입 / output closure.
- `diag_leader_response_closure_changed_N_P`: leader가 realized로 N_P 옮긴 스텝(피드백).
- `offset_A..offset_F`, `green_*_p1`, `ramp_metering_*`, `vsl_*`: 커밋된 제어.
- `rho_FW_*_mean`, `speed_FW_*_mean`: 본선 상태.

측정 예(g1df_sweet190): λ_P>0 15/40 스텝(혼잡기 step16–32, 누적 > N_P_crit 1142에서 발화),
output closure 16/40. 이 머신 G1DF total_ttt = summary.json 참조.
