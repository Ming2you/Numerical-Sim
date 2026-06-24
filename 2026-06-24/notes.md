# 2026-06-24 작업 노트

## Capacity Drop Step 2 게이트 진단

- GitHub `origin/main`을 fast-forward pull해 `92ae671` 상태에서 시작했다.
- `reports/capacity_drop_handoff_for_codex.md`를 읽고 Step 2부터 진행했다.
- 관련 spec/맥락:
  - `docs/codex_implementation_spec.md`
  - `docs/experiment_acceptance_criteria.md`
  - `docs/agent_debate_protocol.md`
  - `docs/spec/03_traffic_models.md`
  - `docs/spec/12_coding_style.md`
  - `docs/spec/15_caveats.md`
  - `2026-06-24/checklist.md`
  - `reports/claude_review_report.md`
- 새 진단 스크립트:
  - `2026-06-24/diag_scripts/capacity_drop_hysteresis_probe.py`
  - default config는 수정하지 않고 runtime override만 사용한다.
  - `freeway_offramp_capacity_drop.enabled=false`, `off_ramp_split_ratio=0`으로 두어 off-ramp lane-drop 효과를 분리했다.
  - 동일한 `freeway_substep` plant를 rise-fall 본선/램프 수요로 구동하고 `rho/speed/flow=rho*v*lanes` 궤적을 기록한다.
- 최종 gate run:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --out-dir outputs\capacity_drop_hysteresis_step2_final --figure reports\figures\fig_capacity_drop_hysteresis_step2_final.png --mainline-low 2100 --mainline-peak 3600 --ramp-low 0 --ramp-peak 250 --total-sec 5400 --probe-segment 3
```

조건 선택 이유:
- 강한 수요는 merge segment가 `rho_max` 근처로 바로 포화되어 hysteresis가 아니라 gridlock/saturation을 관측했다.
- 너무 약한 수요는 `rho_crit`를 넘지 않았다.
- 최종 조건은 포화 없이 `rho_crit`를 넘고 loading/unloading density overlap bin이 4개 생기는 가장 공정한 near-critical probe로 선택했다.

최종 summary:

| case | nu_cong | drop_pct | loop_gap | overlap bins | has_loop |
|---|---:|---:|---:|---:|---:|
| toggle_off | 250 | -0.052 | 30.690 | 4 | 0 |
| nu_cong_65 | 65 | -0.052 | 30.690 | 4 | 0 |
| nu_cong_100 | 100 | -0.041 | 34.420 | 4 | 0 |
| nu_cong_150 | 150 | -0.031 | 38.997 | 4 | 0 |
| nu_cong_250 | 250 | -5.330 | 44.101 | 4 | 0 |

판정:
- 목표 `5-15%` congested discharge drop을 만족한 ν가 없다.
- loading/unloading branch가 4개 density bin에서 겹쳤지만 loop gap이 판정 임계값에 미달했고 `has_loop=0`이다.
- ν split 단독으로는 closed hysteresis loop가 확인되지 않았다.
- handoff 규칙에 따라 Step 3(수요 재설계 + controller matrix 재실행)는 진행하지 않는다.

해석:
- anticipation 항은 downstream density가 더 높으면 감속으로 작동하지만, downstream이 더 비어 있는 unloading 구간에서는 오히려 가속 방향으로 작동할 수 있다.
- 따라서 `rho>rho_crit -> nu_cong` 단일 regime split은 capacity-drop memory를 만들기에는 부족해 보인다.
- 다음 대안은 `rho_recover < rho_crit`인 이력 상태를 추가하거나, discharge/supply 쪽에 명시적 capacity-drop 항을 넣는 것이다. 단, 차량보존 density 식은 계속 건드리지 않아야 한다.

검증:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py"
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m unittest src.tests.test_capacity_drop src.tests.test_metanet_equations
```

결과: compile PASS, 24 tests PASS.

## Capacity Drop very-heavy probe 추가 확인

사용자 요청으로 차량을 훨씬 많이 넣고 `nu_cong=150`만 다시 확인했다.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --out-dir outputs\capacity_drop_hysteresis_very_heavy_nu150 --figure reports\figures\fig_capacity_drop_hysteresis_very_heavy_nu150.png --nu-values 150 --mainline-low 3000 --mainline-peak 6000 --ramp-low 500 --ramp-peak 3000 --total-sec 5400 --probe-segment 3
```

결과:

| case | drop_pct | loop_gap | overlap bins | has_loop |
|---|---:|---:|---:|---:|
| toggle_off | 57.846 | -3.380 | 1 | 0 |
| nu_cong_150 | 58.673 | -2.349 | 1 | 0 |

진단:
- `nu_cong_150`과 toggle off가 거의 같은 형태로 `rho_max` 근처까지 포화됐다.
- probe segment 기준 `sat_steps`: toggle off 457/540, `nu_cong_150` 462/540.
- final speed는 둘 다 `v_min=5 km/h`, final flow는 둘 다 약 `1751 veh/h`.
- origin queue 약 4,600 veh, ramp queue 약 11,000 veh까지 누적됐다.
- 따라서 큰 `drop_pct`는 capacity-drop loop가 아니라 과수요로 인한 포화/gridlock discharge 저하로 해석해야 한다.

## 논문 Eq. (6) boundary-flow 별도 구현 진단

사용자 요청으로 core plant를 직접 교체하지 않고, `capacity_drop_hysteresis_probe.py` 안에
`--plant-mode eq6` 진단 모드를 추가했다. 이 모드는 기존 CTM storage receiving 대신 논문 Eq. (6)의
경계 유량을 사용한다.

- downstream free: `q_i = min(Q_cap, v_i * rho_i * lanes)`
- downstream congested: `q_i = min(v_{i+1} * rho_{i+1} * lanes, v_i * rho_i * lanes)`
- density conservation과 speed update는 기존 단위계/함수를 그대로 사용했다.

검증:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py"
```

결과: PASS.

### Eq6 + `nu_cong=150` near-critical

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --plant-mode eq6 --out-dir outputs\capacity_drop_hysteresis_eq6_step2_final --figure reports\figures\fig_capacity_drop_hysteresis_eq6_step2_final.png --nu-values 150 --mainline-low 2100 --mainline-peak 3600 --ramp-low 0 --ramp-peak 250 --total-sec 5400 --probe-segment 3
```

| case | drop_pct | loop_gap | overlap bins | has_loop |
|---|---:|---:|---:|---:|
| toggle_off | nan | 77.84 | 3 | 0 |
| nu_cong_150 | nan | -0.73 | 3 | 0 |

해석: density가 `rho_crit`를 충분히 넘는 unloading 표본이 부족해 capacity-drop 판정 불가.

### Eq6 + `nu_cong=150` very-heavy

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --plant-mode eq6 --out-dir outputs\capacity_drop_hysteresis_eq6_very_heavy_nu150 --figure reports\figures\fig_capacity_drop_hysteresis_eq6_very_heavy_nu150.png --nu-values 150 --mainline-low 3000 --mainline-peak 6000 --ramp-low 500 --ramp-peak 3000 --total-sec 5400 --probe-segment 3
```

| case | drop_pct | loop_gap | overlap bins | has_loop |
|---|---:|---:|---:|---:|
| toggle_off | nan | 15.19 | 1 | 0 |
| nu_cong_150 | 11.55 | 26.40 | 1 | 0 |

해석: `nu_cong_150`에서 drop_pct는 목표 범위지만 overlap bin이 1개라 loop라고 판정하기 어렵다.

### Eq6 + `nu_cong=150` loop-like 10분 집계 조건

스캔 결과 가장 loop-like한 조건:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --plant-mode eq6 --out-dir outputs\capacity_drop_hysteresis_eq6_best_looplike_nu150 --figure reports\figures\fig_capacity_drop_hysteresis_eq6_best_looplike_nu150.png --nu-values 150 --mainline-low 2400 --mainline-peak 3200 --ramp-low 0 --ramp-peak 500 --total-sec 9000 --probe-segment 3
```

| case | drop_pct | loop_gap | overlap bins | has_loop |
|---|---:|---:|---:|---:|
| toggle_off | nan | 56.48 | 1 | 0 |
| nu_cong_150 | -4.33 | 75.42 | 4 | 0 |

추가로 논문 Figure 7과 맞추기 위해 600초 aggregate plot을 생성했다:

- `reports/figures/fig_capacity_drop_hysteresis_eq6_best_looplike_nu150_aggregate.png`

해석:
- Eq. (6) boundary-flow를 쓰면 기존 CTM receiving plant보다 loading/unloading 궤적은 확실히 더 벌어진다.
- 그러나 `nu_cong=150` 조건에서 capacity drop은 음수(`-4.33%`)라, 논문 Figure 7의 "capacity drop loop"와는 다르다.
- 즉 Eq. (6) 차이는 loop-like trajectory에는 영향을 주지만, 논문 그림 수준의 capacity-drop hysteresis를 만들기에는 충분하지 않다.
- 논문 Figure 7은 modified METANET 단독 출력이 아니라 VISSIM no-control/VSL-HSR 10분 집계 결과라, driver behavior/vehicle platoon/microscopic bottleneck memory가 같이 들어간 것으로 보는 게 맞다.

### Eq6 loop-like 조건에서 `nu_cong` sweep

사용자 요청으로 위 loop-like 조건을 고정하고 `nu_cong` 값을 다양하게 바꿔 10분 aggregate 궤적을 비교했다.

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --plant-mode eq6 --out-dir outputs\capacity_drop_hysteresis_eq6_nu_sweep_looplike --figure reports\figures\fig_capacity_drop_hysteresis_eq6_nu_sweep_looplike_raw.png --nu-values 65,100,150,200,250,300,400 --mainline-low 2400 --mainline-peak 3200 --ramp-low 0 --ramp-peak 500 --total-sec 9000 --probe-segment 3
```

요약:

| case | drop_pct | loop_gap | overlap bins | has_loop |
|---|---:|---:|---:|---:|
| toggle_off | nan | 56.5 | 1 | 0 |
| nu_cong_65 | nan | 56.5 | 1 | 0 |
| nu_cong_100 | nan | 74.4 | 4 | 0 |
| nu_cong_150 | -4.33 | 75.4 | 4 | 0 |
| nu_cong_200 | nan | -87.2 | 3 | 0 |
| nu_cong_250 | nan | -209.4 | 3 | 0 |
| nu_cong_300 | nan | -861.3 | 3 | 0 |
| nu_cong_400 | 75.18 | -528.0 | 2 | 0 |

생성 그림:

- `reports/figures/fig_capacity_drop_hysteresis_eq6_nu_sweep_looplike_aggregate.png`
- `reports/figures/fig_capacity_drop_hysteresis_eq6_nu_sweep_looplike_aggregate_autoscale.png`

해석:
- `nu_cong=100~150`에서 가장 논문 Figure 7에 가까운 loop-like 궤적이 나온다.
- `nu_cong=200~300`은 unloading 경로가 위로 말리며 loop_gap 부호가 음수로 바뀐다.
- `nu_cong=400`은 drop_pct가 75%로 과도하고, trajectory가 극단적으로 붕괴되어 calibration 후보로 부적절하다.
- 따라서 Eq6 boundary-flow + 중간 정도 `nu_cong`는 현재 plant보다 훨씬 그럴듯하지만, formal gate metric 기준 hysteresis PASS는 아직 아니다.

### Eq6 `nu_cong=65~150` 5단위 세밀 sweep

사용자 요청으로 자연스러워 보이는 `nu_cong=65~150` 구간을 5단위로 더 촘촘하게 탐색했다.

```powershell
$nu = ((65..150) | Where-Object { ($_ - 65) % 5 -eq 0 }) -join ','
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --plant-mode eq6 --out-dir outputs\capacity_drop_hysteresis_eq6_nu65_150_step5 --figure reports\figures\fig_capacity_drop_hysteresis_eq6_nu65_150_step5_raw.png --nu-values $nu --mainline-low 2400 --mainline-peak 3200 --ramp-low 0 --ramp-peak 500 --total-sec 9000 --probe-segment 3
```

요약:

| nu_cong | drop_pct | loop_gap | overlap bins | has_loop |
|---:|---:|---:|---:|---:|
| off/65 | nan | 56.5 | 1 | 0 |
| 70 | nan | 90.5 | 2 | 0 |
| 75 | nan | 39.1 | 1 | 0 |
| 80 | nan | 81.4 | 2 | 0 |
| 85 | nan | 83.3 | 3 | 0 |
| 90 | nan | 73.1 | 3 | 0 |
| 95 | nan | 74.0 | 3 | 0 |
| 100 | nan | 74.4 | 4 | 0 |
| 105 | nan | 65.3 | 4 | 0 |
| 110 | nan | 56.2 | 4 | 0 |
| 115 | 0.23 | 63.6 | 4 | 0 |
| 120 | 0.51 | 69.4 | 4 | 0 |
| 125 | 1.01 | 71.7 | 4 | 0 |
| 130 | 1.54 | 70.9 | 4 | 0 |
| 135 | 2.10 | 80.6 | 4 | 0 |
| 140 | 2.62 | 93.9 | 4 | 1 |
| 145 | nan | 61.8 | 4 | 0 |
| 150 | -4.33 | 75.4 | 4 | 0 |

생성 그림:

- `reports/figures/fig_capacity_drop_hysteresis_eq6_nu65_150_step5_common.png`
- `reports/figures/fig_capacity_drop_hysteresis_eq6_nu65_150_step5_autoscale.png`

해석:
- 공통 축과 auto-scale 모두에서 Eq6 mode는 기존 plant보다 훨씬 loop-like한 trajectory를 만든다.
- 시각적으로는 `nu_cong=115~140` 구간이 가장 자연스럽고, `nu_cong=140`은 현재 heuristic `has_loop=1`로 잡힌다.
- 다만 drop_pct는 최대 2.62%라 기존 목표였던 5-15% capacity drop에는 아직 약하다.

### Eq6 `nu_cong=140` 고정 VSL 예비분석

사용자 요청으로 Eq6 diagnostic에서 고정 VSL을 켜서 inflow-control 효과가 있는지 예비 확인했다.
조건은 loop-like 조건 그대로 두고 `nu_cong=140`으로 고정했다.

```powershell
$vals = 100,90,80,70,60
foreach ($v in $vals) {
  & "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py" --plant-mode eq6 --out-dir "outputs\capacity_drop_hysteresis_eq6_vsl_prelim\vsl_$v" --figure "reports\figures\fig_capacity_drop_hysteresis_eq6_vsl_prelim_$v.png" --nu-values 140 --fixed-vsl $v --mainline-low 2400 --mainline-peak 3200 --ramp-low 0 --ramp-peak 500 --total-sec 9000 --probe-segment 3
}
```

비교 CSV:

- `outputs/capacity_drop_hysteresis_eq6_vsl_prelim/vsl_prelim_comparison.csv`

생성 그림:

- `reports/figures/fig_capacity_drop_hysteresis_eq6_vsl_prelim_aggregate.png`

요약:

| VSL | drop_pct | loop_gap | overlap bins | has_loop | max rho | mean flow |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 2.62 | 93.86 | 4 | 1 | 38.13 | 3561.64 |
| 90 | 2.62 | 93.86 | 4 | 1 | 38.13 | 3561.45 |
| 80 | 2.73 | 101.24 | 5 | 1 | 38.21 | 3558.83 |
| 70 | 1.13 | 93.76 | 7 | 1 | 39.44 | 3550.33 |
| 60 | 0.83 | 78.94 | 7 | 0 | 39.55 | 3546.30 |

해석:
- VSL 90은 VSL 100과 거의 동일하다. 해당 조건에서는 no-VSL desired speed가 이미 90km/h 이하인 구간이 많아 cap이 잘 안 걸리는 것으로 보인다.
- VSL 80부터 평균 flow가 조금 낮아지고 loop overlap이 증가해 약한 inflow-control 효과가 보인다.
- VSL 70/60은 flow를 더 낮추지만 density를 줄이기보다는 체류/overlap을 늘리는 쪽에 가깝다. 60은 `has_loop=0`으로 떨어진다.
- 이 예비조건에서는 VSL 80 정도가 가장 부드러운 약한 제어처럼 보인다. 다만 변화 폭은 작고, 실제 controller 성능 판단은 controller가 어느 segment에 언제 VSL을 걸지 포함해서 별도 run이 필요하다.

### Eq6 upstream-only VSL 예비분석

사용자 요청으로 probe/bottleneck segment 자체가 아니라 그 직전 upstream segment에 VSL을 걸었을 때
inflow-control 효과가 더 뚜렷한지 확인했다. `capacity_drop_hysteresis_probe.py`에
`--fixed-vsl-segments` 옵션을 추가하고, probe segment로 들어가는 `probe_inflow_veh_h`
(`q_inter` into segment 3)를 로그에 남기도록 했다.

검증:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B -m py_compile "2026-06-24\diag_scripts\capacity_drop_hysteresis_probe.py"
```

결과: PASS.

실행 조건:

- `plant-mode=eq6`
- `nu_cong=140`
- `mainline-low=2400`, `mainline-peak=3200`
- `ramp-low=0`, `ramp-peak=500`
- `T_total=9000 s`
- `probe-segment=3`
- 비교: VSL100 all, VSL80 all, VSL80 segment 0-2, VSL80 segment 2 only, VSL70 all, VSL70 segment 0-2, VSL70 segment 2 only

생성 파일:

- `outputs/capacity_drop_hysteresis_eq6_vsl_upstream_prelim/upstream_vsl_comparison.csv`
- `reports/figures/fig_capacity_drop_hysteresis_eq6_vsl_upstream_prelim.png`

요약:

| case | drop_pct | loop_gap | bins | mean probe inflow | mean probe flow | max rho |
|---|---:|---:|---:|---:|---:|---:|
| VSL100 all | 2.62 | 93.86 | 4 | 3552.0 | 3561.6 | 38.13 |
| VSL80 all | 2.73 | 101.24 | 5 | 3550.3 | 3558.8 | 38.21 |
| VSL80 seg0-2 | 2.73 | 101.24 | 5 | 3550.3 | 3558.8 | 38.21 |
| VSL80 seg2 | 2.73 | 101.24 | 5 | 3550.3 | 3558.8 | 38.21 |
| VSL70 all | 1.13 | 93.76 | 7 | 3548.2 | 3550.3 | 39.44 |
| VSL70 seg0-2 | 1.13 | 93.76 | 7 | 3548.2 | 3550.3 | 39.44 |
| VSL70 seg2 | 1.13 | 93.76 | 7 | 3548.2 | 3550.3 | 39.44 |

해석:
- VSL80은 probe inflow/flow를 아주 약하게 낮추고 loop gap/bins를 조금 키운다.
- VSL70은 inflow/flow를 더 낮추지만 max rho가 증가해, 이 조건에서는 좋은 congestion relief라기보다 stronger holding에 가깝다.
- all segments, upstream 0-2, immediate upstream segment 2가 동일하게 나온다. 즉 이 조건의 Eq6 boundary flow에서는 probe segment로 들어가는 `q_inter_2`가 대부분 segment 2의 sending으로 결정되며, segment 2 VSL만으로 전체 효과가 설명된다.
- 효과 크기는 작다. 따라서 VSL이 Eq6 plant에서 inflow-control 채널을 갖는 건 맞지만, 이 demand/segment 조건만으로는 dramatic한 성능 개선을 기대하기 어렵다.
