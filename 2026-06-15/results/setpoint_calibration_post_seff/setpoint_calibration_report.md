# Setpoint Calibration Report

## 요약

- 추정 `n_crit`: `725.897 veh`
- 관측 최대 urban production: `33805.262 veh/h`
- 해당 urban scale: `3.000`
- 해당 시각: `1080.0 s`

## 방법

- 여러 urban demand scale에 대해 baseline closed-loop simulation을 실행했습니다.
- `state_timeseries.csv`에 해당하는 row에서 urban accumulation을 기록했습니다.
- run diagnostics의 `urban_total_departures_veh / T_c_h`를 production으로 기록했습니다.
- 관측 production이 최대인 지점의 accumulation을 1차 `n_crit` 추정치로 선택했습니다.

## 주의

- 이 결과는 deterministic scaffold이며, 최종 통계적 calibration은 아닙니다.
- config 값을 확정하기 전에는 더 긴 horizon과 더 촘촘한 scale point를 사용해야 합니다.
- Freeway q-rho calibration은 P1 단계로 분리했습니다.
