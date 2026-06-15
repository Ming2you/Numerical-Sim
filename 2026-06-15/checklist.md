# 2026-06-15 체크리스트

- [x] 1. off-ramp storage 드레인을 하류 receiving 공간에 게이트(식3) — 고정지연 release 폐지
- [x] 2. schedule_offramp_arrivals 단순화(점유 생성만, 자동 release 제거)
- [x] G1. 보존 항등식 테스트 통과(residual=0) — 통과
- [x] G2. 강제 하류 정체에서 off-ramp 점유 100% & λ_eff 1.65(<2), 복원 26%/1.955 — 통과
- [x] 5. n_crit 재calibration(521→778) + config 갱신 + 의존 테스트 갱신
- [~] 6. scenarios.yaml spillback 시나리오 — 파라미터 갱신했으나 **자연형성 불가**(계측 기록)
- [ ] 7. VSL ablation(on/off) — **중단**: 자연 spillback 부재로 closed-loop 입증 불가
- [ ] 8. 메커니즘 B 제거 — **중단**: VSL 실물리 작동(자연 spillback) 전제 미충족, 제거 시 회귀
- [~] 9. test_c — 기존 forced-state 검증 유지(자연 spillback 불가로 갱신 불가). 통과 확인.
- [x] 전체 unittest discover 통과(113) + 단계별 커밋(push 금지)

## 게이트 판정
G1·G2(핵심 하드게이트) 통과. 메커니즘은 정확하고 보존 안전. step6에서 "이 망은 demand만으로
자연 spillback을 못 만든다"가 계측으로 확정 → 지시의 단계 게이트("안 오르면 중단·보고")에 따라
step7~9를 중단하고 보고. step8(메커니즘 B 제거)은 자연 spillback이 없으면 VSL이 실물리로 작동할
무대가 없어 제거 시 회귀하므로 보류함.
