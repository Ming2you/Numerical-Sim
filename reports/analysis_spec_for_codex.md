# Codex 인계: 4-controller × 6-scenario 분석 실행 스펙 (최대 데이터 보존)

목적. 4개 컨트롤러 × 6개 시나리오를 돌리되, **사후에 marginal 분석·critical-value 비교·objective 분해·
hysteresis·VSL 활성**을 모두 할 수 있도록 **가능한 한 많은 raw 데이터를 per-step으로 저장**한다.
(분석 자체는 사후 스크립트로. 여기선 "무엇을 어떻게 돌리고 무엇을 남기는가"를 규정.)

repo 루트에서 작업. 런타임 python:
`C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B`

## 0. 선행 의존성
- **6개 시나리오가 `src/config/scenarios.yaml`에 존재해야 함**(아래 §2). 일부는 신규 — `reports/
  capacity_drop_handoff_for_codex.md` step 3-1(수요 재설계: peak/peak×1.4/transient-surge/freeway-heavy/
  urban-heavy/skew)에서 추가.
- capacity drop은 별도 축(off/on). step 1 구현 완료(`capacity_drop_anticipation` toggle). on으로 돌리려면
  `metanet_nu_cong_km2_h` 튜닝값 필요(capacity_drop handoff step 2). **튜닝 전이면 우선 cd_off로 baseline
  매트릭스만 돌리고, cd_on은 튜닝 후.**

## 1. 컨트롤러 (4개)
`NO-CONTROL`(러너가 자동 추가) + `WU-CD-F` + `PROPOSED-FOLLOWERS-ONLY`(PFO) + `PROPOSED-STACKELBERG`(P-Stack).
- **`PROPOSED-CENTRALIZED`는 제외**(사용자 결정: centralized 뺌).
- 실행 시: `--controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG` (no-control 자동).

## 2. 시나리오 (6개)
| key(예시) | 내용 |
|---|---|
| `peak_demand` | peak (기존) |
| `peak_140` | peak × 1.4 |
| `transient_surge` | capacity 아래→위(볼록)→아래 회복 (신규 temporal profile=surge) |
| `freeway_heavy` | freeway 수요 過多 |
| `urban_heavy` | urban 수요 過多 |
| `skew_peak_14` | peak×1.x + 공간 skew(urban_boundary_weight_override) |
※ key 이름은 scenarios.yaml 정의에 맞춰 조정. transient_surge는 loading+unloading이 핵심
(회복·hysteresis 관측 전제).

## 3. 실행 커맨드
전체 매트릭스(7200s = loading+unloading 보이도록 full horizon):
```
python -B -m src.experiments.all_scenarios_four_controller_comparison \
    --scenario all --T-total 7200 --seed 42 \
    --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG \
    --output outputs/matrix_cd_off_7200
```
capacity drop on(튜닝 후, config override로 toggle):
```
# default.yaml에서 capacity_drop_anticipation: true + metanet_nu_cong_km2_h: <튜닝값> 으로 두고
python -B -m src.experiments.all_scenarios_four_controller_comparison \
    --scenario all --T-total 7200 --seed 42 \
    --controllers WU-CD-F,PROPOSED-FOLLOWERS-ONLY,PROPOSED-STACKELBERG \
    --output outputs/matrix_cd_on_7200
```
- 출력 구조: `outputs/<run>/runs/<scenario>/<controller>/{*.csv,*.jsonl}` + `analysis/` 요약.
- 비용 주의: P-Stack은 leader 탐색이 무거움. 8 worker process 병렬 권장(`--grid-parallel-backend process
  --grid-parallel-max-workers 8`). 12+는 OOM 이력 있음.

## 4. 저장 데이터 (최대 보존 — per-step, 다운샘플 금지)
`run_closed_loop`가 컨트롤러별로 쓰는 파일. **전부 보존**할 것.

| 파일 | 핵심 컬럼 | 어떤 분석에 쓰나 |
|---|---|---|
| `state_timeseries.csv` | `rho_FW_*_mean`, `speed_FW_*_mean`, `freeway_vehicles`, `urban_vehicles`, `urban_protected_accumulation_veh`, `movement_queue_*`(78), `ramp_queue_*` | 모든 분석(밀도/속도/flow/누적/큐) |
| `progress_summary.csv` | `step_freeway_ttt`, `step_urban_ttt`, `step_total_ttt`, `cumulative_*` | marginal·TTT 분해 |
| `control_timeseries.csv` | `vsl_*`, `ramp_metering_*`, `green_*`, `offsets_*` | VSL/metering/green 활성 |
| `run_log.csv` | per-agent `*_tts`, `freeway_ttt`, `urban_ttt`, `capacity_drop_active`, `*_lambda_eff_*` | capacity drop·agent 분해 |
| `decision_diagnostics.csv` (P-Stack) | `leader_objective_base`, `leader_mfd_storage_excess_veh`/`_penalty`, `leader_mfd_movement_excess_veh`, `leader_density_excess`/`_penalty`, `leader_target_penalty`, `leader_mfd_storage_threshold_ratio` | objective 분해(권위값) |
| `decision_progress.jsonl` (P-Stack) | leader 탐색 전체 중첩 기록 | 사후 deep dive |

**주의**: `leader_*` 진단은 leader가 있는 **P-Stack에만** 존재(no-control/PFO/WU는 leader objective 없음).
→ **cross-controller 분석은 `state_timeseries`+`progress_summary`에서 동일 공식으로 재계산**할 것
(leader 공식은 `src/controllers/leader.py` `_urban_halfcap_excess`/`_density_penalty`, 수식은
`2026-06-24/checklist.md`).

## 5. 지원해야 할 사후 분석 (이 데이터로 가능해야 함)
각 (scenario, controller)에 대해 아래를 계산 가능하게 데이터가 남아야 한다. 가능하면 Codex가
**파생 테이블(`analysis/derived_<scenario>_<controller>.csv`)**로 미리 계산해 저장(재현성).

### (a) Marginal 분석
- freeway/urban **TTT 분해**: `cumulative_freeway_ttt` vs `cumulative_urban_ttt` (컨트롤러 간 비교 → P-Stack이
  freeway를 줄이고 urban을 떠안는 trade, ≈17:1).
- **누적 N**: `freeway_vehicles`, `urban_vehicles` (시간평균·peak).
- **W = TTT/N**(평균 체류), **ΔTTT/ΔN**(컨트롤러 쌍 간 한계).
- **freeway flow** = `rho_FW_*_mean · speed_FW_*_mean · lanes` → flow–density 산점(한계비용 기전).
- 핵심 해석: per-vehicle-hour 비용은 동일하나, freeway 과포화 가지에서 flow↓ → **누적 증폭**이 한계의 실체.

### (b) Critical-value 비교
- **freeway**: `rho_FW_*_mean` vs `rho_crit`(=33.5) — 임계 초과량·임계 인근 체류·**unloading 시 ρ_crit 아래로
  회복하는가**(transient_surge에서 핵심).
- **urban**: `movement_queue_*` vs **요소별 0.5·cap**(half-cap) — 요소별 초과(집중) + 집계 vs half-cap합.
  `urban_protected_accumulation_veh` vs `N_P_crit`(=509).
- 회복성: surge의 하강 구간에서 각 컨트롤러가 임계 아래로 얼마나 빨리 되돌리나.

### (c) Objective 분해(누적 stacked)
- 성분: freeway TTT + urban TTT + half-cap penalty(=excess·w·T_c_h) + density penalty(=density_excess·w_F·T_c_h).
- P-Stack은 `decision_diagnostics` 권위값, 나머지는 state에서 재계산. (참고 그림:
  `2026-06-24/diag_scripts/penalty_analysis_figs.py` figA.)

### (d) capacity drop / hysteresis (cd_on 매트릭스에서)
- `rho`–`flow` 시간순 궤적 → **loop 가시화**(loading≠unloading). `run_log.capacity_drop_active`.
- cd_off vs cd_on 대조.

### (e) VSL 활성
- `control_timeseries.vsl_*`가 **incident 외(평시 혼잡)에서도** 자유류 max 미만으로 작동하는지
  (capacity drop 도입 효과의 핵심 검증).

## 6. 데이터 보존 규칙
- **per-step 전량 저장, 다운샘플·집계 후 raw 삭제 금지.** 모든 per-segment(rho/speed/flow)·per-movement(queue)
  컬럼 유지.
- cd_off / cd_on 두 매트릭스를 **별도 output 디렉터리**로 보존(대조용).
- `outputs/`는 .gitignore라 git에 안 올라감 → **요약표·파생 CSV·그림만 `reports/`에 커밋**.
- 작업 기록: `YYYY-MM-DD/notes.md`. 커밋 메시지 `YYYY-MM-DD: 설명` + `Co-Authored-By`.

## 7. 권장 실행 순서
1. (선행) 6 시나리오 scenarios.yaml 정의 확인/추가 + transient_surge temporal profile.
2. **cd_off 매트릭스** 7200s 실행 → §5 분석 전부 수행(baseline, 회복·marginal·critical 관측).
3. capacity drop 튜닝 완료되면 **cd_on 매트릭스** 실행 → hysteresis·VSL 재확인 + cd_off 대조.
4. 파생 테이블·그림 생성 → 리포트 갱신.
