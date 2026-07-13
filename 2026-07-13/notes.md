# 2026-07-13 작업 노트

## 1. r̂ 편향 보정 구현 (커밋 c1c5b9b, NP_BIAS=1, 기본 OFF)

### 배경 — λ̂ 휴면 근본원인
NP-CAND-λ̂ 채널이 전 셀에서 λ̂=0으로 휴면. 원인은 **계획 공간 vs 실현 공간 불일치**.
- 예측(계획) Σnin ≈ 2,123 > target 1,730 (+368, 40/40 스텝) — 모델은 항상 초과를 예측.
- 실현 ΔN_P×H ≈ 1,500 < σ_min — 실측은 상한에 닿은 적 없음(모델 낙관 편향 ~30%).
- corrector가 실현 Q를 계획 target과 비교하므로 λ가 오를 수 없는 구조.
- 등식제약/음수 λ 대안은 실측으로 기각(28,242 파국·보조금 병리, 07-12 기록).

### 구현
- `wu_faithful_follower.py` — `_np_bias_ratio` EWMA 추적. 스텝 시작 1회 블록에서
  ratio = clip(실현 Q / |예측 Σnin|, 0.05, 2.0), EWMA β=0.3.
  corrector: `λ = Π[λ + γ(Q_real − r̂·Ñ_committed)]`, predictor: target을 `r̂·Ñ^(c)`로 환산.
  플래그 OFF면 r̂=1.0 곱 → **비트동일**(IEEE754 1.0*x 정확).
- `state.py` — `mpc.np_bias_correction: bool = False` (동결 헤드라인 매트릭스 보호).
- 러너 — `NP_BIAS=1` 훅, 진단 `wu_faithful_np_bias_ratio` 수출.

### 스모크 (sweet_190, 720s=4스텝, NP_BIAS=1)
- bias_ratio: 1.0 → 0.866 → 0.702 → 0.542 (EWMA 정상 추적, 워밍업이라 실현/예측 비율 낮음).
- λ̂=0 유지 — 워밍업 구간 실현 유입(≈1,200) < r̂·1,730이므로 정상 거동.
- 발동 실측(혼잡 피크 도달 셀)은 사용자 지시로 제외 — 디폴트 전환 전 A/B 별도 결정.
- 출력: `outputs/_npbias_smoke/on/`.

### 주의
- 활성화 시 190 계열 거동이 바뀔 수 있음(실현 ~1,500 > r̂·1,730 ≈ 1,211 → λ̂ 발동 예상).
  **디폴트 ON 전환은 반드시 5-suite A/B 후 결정.**

## 2. WU-CD-F 컬럼 완료 → 4컬럼 메인 표 확정 (results/main_table_4col.md)
- 문헌 Wu(green+VSL only, metering 용량 고정) 12셀 완료: sustained 7(T=7200) + suite pulse 5(T=3600).
  (중간보고 때 22,901.8을 190으로 오기 — 실제는 170_skew. 190 = 28,324.3. 정정.)
- 비교 유효성: 셀별 free_flow_reference 전 컬럼 일치 확인(190=2507.448 등). NC 원자료는
  컨트롤러 무관이므로 λ수선 전 xval(155계열)·_8seg/nc(190)·_170(170계열) 값 사용 가능.
- 핵심: WU-CD-F는 sustained −1.2~−9.4%(155_skew만 −20.8%, green 재배분 레짐), 펄스 169%+
  사실상 NC 동급 → **권한 격차(metering, −40%p↑)와 조정 격차(P-Stack−PFO-link, sustained 7/7승
  −23~−1,281)가 표에서 분리**. 구 "WU" 컬럼은 PFO-link(권한 동등 ablation)로 재라벨 확정.
- P-CENT 8-seg 재측정 반영: 190 = 18,527.4 (계층 −15.5% 우위, 계산 1/8). 구 4-seg 17,929 대체.

## 3. P-CENT 8-seg 전셀 발주 + 계산비용 집계 (사용자 지시)
- P-CENT SLSQP 나머지 11셀 3체인 병렬 발주(suite 5 / 155계열 3 / 170계열 3,
  outputs/_pcent/slsqp_8seg_{suite,155fam,170fam}.log). 단독 실측 475s/스텝 기준
  sustained 셀당 ~5.3h — 병렬 경합 감안 총 16~30h 예상.
- 계산비용 사다리(12셀 mean_step_compute_sec): PFO-link 3.6s < WU-CD-F 11.1s <
  계층 59.2s < P-CENT 475.3s. **계층만 ci 180s 실시간 경계 내(33%), P-CENT는 2.6배 초과.**
  상세는 results/main_table_4col.md 계산비용 절.

## TODO
- [ ] P-CENT 11셀 완료 → 메인 표 P-CENT 컬럼·계산비용 행 갱신
- [ ] 8-seg oracle 재실행(open-loop bound, 구 14,223은 4-seg 값)
- [ ] ε-gap probe 프로덕션 1셀
- [ ] 원고 수정시트 일괄 적용(Word 닫힌 후) + notation rename 실행
