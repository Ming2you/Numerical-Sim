# 2026-06-15 체크리스트

- [ ] 1. off-ramp storage 드레인을 하류 receiving 공간에 게이트(식3) — 고정지연 release 폐지
- [ ] 2. schedule_offramp_arrivals 단순화(점유 생성만, 자동 release 제거)
- [ ] G1. 보존 항등식 테스트 통과(residual=0) — 깨지면 중단·보고
- [ ] G2. 하류 정체 시나리오에서 off-ramp 점유율 ≥50% & λ_eff<lanes 측정 입증 — 안 오르면 중단·보고
- [ ] 5. n_crit 재calibration + config 갱신
- [ ] 6. scenarios.yaml spillback 시나리오 추가/갱신
- [ ] 7. VSL ablation(on/off) freeway·total TTT 비교 입증
- [ ] 8. 메커니즘 B(p_down/downstream_coupling_weight) 제거
- [ ] 9. test_c를 자연 형성 spillback 검증으로 갱신
- [ ] 전체 unittest discover 통과 + 단계별 커밋(push 금지)
