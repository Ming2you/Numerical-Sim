# 2026-06-17 작업 노트 — off-ramp 큐 freeway 재귀속(B) + 후속 계획

## 한 일 (이번 커밋)
설계 `docs/offramp_queue_reattribution_design.md`대로 **변경 B(off-ramp 램프 storage를
urban→freeway 재귀속, plant 공통)** 구현. 코더+리뷰어 루프로 검증.

- TTT 분해: 램프 storage(`OR_*_storage`) 점유를 urban_ttt에서 빼고 freeway_ttt로 이동
  (`urban_queue_model._storage_occupancy` 제외 + `coupling`이 freeway_ttt에 가산).
- N_P/total_urban: 램프 storage 제외, **leg(off_ramp movement 점큐)는 urban·N_P에 유지**.
- freeway agent local TTT(WU/proposed/P-CENT)에 램프 storage 가산.
- 보존: `freeway_ttt+urban_ttt` 합·총차량 불변(리뷰어 1e-14 확인), 이중계상 0.
- **`_agent_vsl` off-ramp 트리거 제거**(이번 Phase A) — trigger 스타일 + dead-branch(점유비율
  ≤1.0인데 >1.25 분기)라 폐기. objective의 `+offramp_storage_veh` 가산은 유지.

## 같이 들어간 것 (변경 2, 그대로 둠 — 추가 작업 보류)
- leader objective에 `w_boundary_in × Σ(boundary_in 큐)` 비용 항(anti-gaming, 기본 1.0).
- **사용자 지시로 지금은 더 건드리지 않고 그대로 둠.** docs/proposed_forecast_awareness_diagnosis.md
  권고("leader penalty는 follower forecast-aware 후에")에 따라, **follower forecast-aware化
  완료 후 효과 재해석·튜닝**할 것. → 다음 할 일.

## ⚠️ 다음 할 일 (DEFERRED / TODO)
1. **[다음 작업] Phase B — 분산 follower forecast-aware化 (full, 사용자 결정).**
   근거: `docs/proposed_forecast_awareness_diagnosis.md` — 현재 분산 follower가 `forecast[0]`만
   보는 myopic이라 leader가 myopic 응답을 forecast-aware인 양 오평가. 권고 순서:
   - (1) `DistributedCoordinator.solve`가 full forecast를 agent에 전달(first_demand 축소 제거).
   - (2) **freeway VSL = horizon objective 최소화**(off-ramp storage 포함) — 휴리스틱 `_agent_vsl`
     폐기, emergent. = 사용자가 고른 "option 2". 계산비용은 relaxed-quantization(연속 target +
     10단위 floor 양자화 repair, `relaxed_quantization.py`)으로 후보 소수화해 bound.
   - (3) proposed urban green에 horizon arrival pressure(`q0 + 예측도착×horizon`).
   - (4) allocation target을 forecast-호환(예측 유입 반영).
   - (5) proposed leaderless ramp metering 고정(no-metering 보호 baseline + 큐 비용 가격화).
2. **[필수] N_P_crit_veh 재calibration** — N_P 정의가 램프 storage 제외로 바뀜(현 556.081 무효,
   calibration probe ≈210 관측). forecast-aware化 후 새 정의로 MFD 재측정.
3. **[연기] heavy-transfer 시나리오**(off-ramp가 실제 차는 split/수요) — emergence 관찰용.
4. **[보류 재검토] 변경 2(leader boundary 비용)** — follower forecast-aware 후 효과 재해석/튜닝.

## 비고
- relaxed-quantized 모드는 LP가 아니라 "연속 target(휴리스틱 closed-form) + 10단위 floor
  양자화 + vsl_set 투영"이며 기본 OFF. proposed VSL을 emergent로 만들진 않음(repair만).
- emergence는 WU(local TTS 최적화)·P-CENT(total objective)에서만 진짜이고, proposed 분산은
  Phase B에서 VSL을 objective-min으로 바꿔야 진짜 emergent.
