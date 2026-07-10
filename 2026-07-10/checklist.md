# 2026-07-10 체크리스트

## A/B 계산비용 (진행 중)
- [x] A1 dedupe + A2 early-stop + B price-lite 구현·커밋(6e65991)
- [x] 스모크(rollout 62→30, dedupe 발화, 가격 유한)
- [x] 회귀 13/13 (lite 키셋 테스트 추가)
- [ ] 3점 비교런 완료 대기(base/A-only/A+B, sweet_190) → 결과표·무손실 판정
- [ ] 무손실 시 디폴트 채택 결정 + push

## 13-Player 재구축 (옵션 3, plan-13player-rebuild.md)
- [x] 보험 브랜치 feature/segment-agents-13p 생성(main 동결)
- [x] **사용자 승인**: 매핑 수정안(F_L2=R_D/F_L3=R_F, off-ramp→urban D/F) + R_F merge 2→3 망 변경 + 2-agent 예산 합의 + equality-first
- [x] worktree 사본(Numerical-Sim-13p)으로 체인과 격리 — 코딩 즉시 착수(사용자 지시)
- [x] 1단계: segment_local_plant.py + y 스키마 + 테스트(비트 일치·반응성·소유) — 34db7de
- [x] 부수: 기존 stale 테스트 4건 수정(N_P_crit·adapter·1e-12·scipy) — main도 깨져 있던 것
- [ ] 2단계: agent registry 13 + _solve_followers 개편 + 소유맵
- [ ] 3단계: metering SPLIT-v2 → F_L2 이식
- [ ] 4단계: VSL per-segment + 가격 적용 + 창발 검증
- [ ] 5단계: 회귀 + sweet_190 d3 vs 11893 + 채널 활성 확인
- [ ] 6단계: WU-CD-F 분할 여부 결정
- [ ] 7단계: A/B 패키지 재검증
- [ ] 8단계: N_UF dual ablation
