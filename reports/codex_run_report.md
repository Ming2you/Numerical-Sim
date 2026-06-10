# Codex 실행 리포트

## 현재 상태

현재 모델은 아직 인증 기준을 만족하지 못합니다.

Claude가 `ee85ee1` 기준으로 `peak_demand`, `7200 s` full diagnostic run을 수행했고,
결과는 proposed Stackelberg MPC가 fixed baseline보다 **Total TTT 기준 10.64% 악화**였습니다.

이번 run의 핵심 의미는 계산 병목이 아니라 다음 병목을 확인했다는 점입니다.
Freeway follower 경량화 이후 full run은 가능해졌고, 이제 실패 원인은 주로 urban setpoint와
urban follower 제어 로직으로 좁혀졌습니다.

## 현재 Full Diagnostic 결과

- 검토 커밋: `ee85ee1`
- 시나리오: `peak_demand`
- Baseline mode: `fixed_signal_fixed_speed`
- Controller mode: `stackelberg_mpc`
- Simulation horizon: `7200 s`
- Claude 확인 출력: `outputs/claude_diag_peak_full/`

| 지표 | Baseline | Proposed | 결과 |
|---|---:|---:|---:|
| Total TTT | 2889.8 | 3197.3 | -10.64% |
| Freeway TTT | 187.8 | 195.8 | 소폭 악화 |
| Urban TTT | 2702.0 | 3001.5 | +11.1% 악화 |
| Boundary CV | 0.145 | 0.305 | 악화 |

## 해결된 부분

- Freeway follower 후보 평가에서 full `run_coupled_interval` 재시뮬레이션을 제거했습니다.
- 후보 평가는 고정 urban control에서 on-ramp/off-ramp boundary만 예측하는 lightweight plant를 사용합니다.
- on-ramp metering은 요청량이 아니라 `w_r`에서 실제 drain된 차량만 freeway에 주입합니다.
- 관련 regression test가 추가됐고, `python -m unittest discover -s src/tests` 기준 38개 테스트가 통과했습니다.
- 첫 default MPC decision 실측은 약 `78.7 s -> 17.5 s`로 감소했습니다.

## 현재 실패 진단

1. `peak_demand`에서는 freeway가 거의 혼잡하지 않아 VSL이 한 번도 활성화되지 않습니다.
   - `vsl_active_steps = 0`
   - freeway density exceedance도 사실상 없습니다.
   - 이 시나리오는 freeway 제어 검증보다는 urban 제어 진단에 가깝습니다.

2. Leader의 `N_UF_star`가 초기에 추적 불가능한 값을 선택합니다.
   - 예: `4000`, `6000 veh/h`
   - 실제 ramp release capacity와 downstream receiving을 반영하지 않아 metering residual이 커집니다.

3. 가장 큰 문제는 `N_P_star` 의미가 코드 내에서 불일치한다는 점입니다.
   - leader objective에서는 `N_P_star`를 urban accumulation, 즉 누적 차량 수처럼 사용합니다.
   - urban follower와 diagnostics에서는 `N_P_star`를 net inflow, 즉 `veh/h`처럼 사용했습니다.
   - 같은 값이 한쪽에서는 `veh`, 다른 쪽에서는 `veh/h`로 해석되어 urban control target이 물리적으로 꼬였습니다.

4. Urban follower가 baseline보다 boundary balance를 악화시킵니다.
   - Boundary CV가 `0.145 -> 0.305`로 증가했습니다.
   - MaxMin boundary queue가 시간에 따라 누적 증가했습니다.
   - offset control도 corridor delay를 증가시키는 징후가 있습니다.

## 이번 구현 방향

이번 단계의 수정 범위는 다음과 같습니다.

1. no-control 또는 fixed baseline demand sweep으로 도시 MFD calibration scaffold를 만듭니다.
2. `N_P_star`를 도시 목표 누적 차량 수, 단위 `veh`로 통일합니다.
3. Urban follower는 `N_P_star`를 직접 net inflow target으로 쓰지 않고, 현재 urban accumulation과 목표 accumulation의 차이에서 허용 net inflow를 유도합니다.
4. `N_UF_star` 후보는 total ramp capacity가 아니라 현재 ramp queue, on-ramp green forecast, downstream receiving, mainline density 여유를 반영한 feasible capacity 기반으로 만듭니다.

## 검증 계획

1. Unit tests
2. 짧은 `peak_demand` smoke, 예: `T_total=360`
3. `peak_demand 7200 s` full rerun
4. `oversaturated_demand` 또는 `incident_or_capacity_drop`에서 VSL/ramp metering activation 별도 확인

## 결론

계산 병목은 닫혔습니다. 다음 병목은 setpoint calibration과 urban accumulation control입니다.
이제 목표는 "controller가 켜지는지"가 아니라 "물리적으로 의미 있는 target을 주고,
fixed baseline보다 urban queue balance를 악화시키지 않는지"를 확인하는 것입니다.
