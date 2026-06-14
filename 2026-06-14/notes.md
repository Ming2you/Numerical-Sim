# 2026-06-14 작업 노트 — WU-CD-F 치명 2건 수정

## 목표
WU-CD-F(Wu et al. 2022 분산제어 벤치마크)의 치명 결함 2건 수정.
1. 분산 협상 단발 퇴화(residual=0, iteration=1 즉시 종료).
2. freeway 항상 max VSL(no-control과 동일).

## 변경 파일
- `src/models/urban_queue_model.py`: 신규 헬퍼 `estimate_onramp_reservoir_inflow`
  (기존 `estimate_onramp_green_release_flows` 바로 아래, ramp_space 캡만 제거).
  기존 함수는 다른 호출처(leader/freeway_follower/distributed_coordinator)가 있어 불변.
- `src/controllers/wu_distributed.py`:
  - `__init__`/`_build_coupling_maps`: `_upstream_leaving_map`·`_offramp_drain_flow`·
    `_last_offramp_flow` 토폴로지 자동 유도 캐시. `_signal_leaving_rate` 헬퍼.
  - `_coupling`: u_on을 reservoir inflow로, arr를 상류 후보 green leaving(주)+점유(보조<1)로,
    off-ramp inflow를 `_last_offramp_flow` 재사용으로 교체(후보 반응형).
  - `_solve_freeway_agent`: storage-aware probe(`_update_probe_offramp_storage`),
    비-Wu density_penalty 항 제거, 선택 VSL off-ramp flow를 `_last_offramp_flow`에 캐시.
  - `_solve_followers`: Jacobi 스냅샷 고정 + under-relaxation(α=0.5) + S_max=min(.,5).
- `src/experiments/six_controller_comparison.py`: FIDELITY_MATRIX_MD WU-CD-F 행 갱신.
- `docs/spec/16_six_controller_comparison.md` §16.4: Jacobi 후보 반응형 coupling + f↔f moot.
- `docs/wu2022_distributed_reference.md` §8: density_penalty 제거 + storage-aware probe.
- `src/tests/test_six_controller_comparison.py`: `WuDistributedFixesTests` 5개 추가.

## 검증 수치
- 전체 단위테스트: `unittest discover -s src/tests` 113개 통과(OK).
- 신규 5개(a,b,c,d + 캐시) 통과.
- (a) 단위: 혼잡 state `_solve_followers` iterations=5, 1-iter residual=0.00827>tol(0.001).
- (b) 단위: coupling y 변화 key 2개(arr_D_p1 922→1450 등).
- (c) 단위: prev_vsl=70 혼잡에서 VSL이 max-0.5 미만 유지(작동).
- (d) 단위: off-ramp storage 98% state에서 λ_eff_last≈1.71<2.0(capacity-drop 진입).
- (f) authority_ok=True.
- (h) 방향성(peak fs=1.3, T=1800s closed-loop):
  - 수정 전: iter>1 = 0/10(전부 단발), max_iter=1.0, total_delay=622.7.
  - 수정 후: iter>1 = 9/10, max_iter=5.0, total_delay=622.7.

## 위험요소 실현 여부
- **발산**: 없음. under-relaxation+점유 보조항(가중0.5)+S_max=5로 안정. 수렴(converged=True).
- **VSL 미작동(closed-loop)**: 부분 실현. capacity-drop이 발생하는 state에서는 probe가
  올바르게 VSL을 작동시킴(단위 c/d 입증). 그러나 peak/oversat closed-loop에서는 off-ramp
  storage 점유 최대 ~3.6%(λ_eff≈2.0)로 capacity-drop이 자연 발생하지 않아 VSL이 max 유지.
  - 원인: off_ramp_split_ratio=0.06으로 작고 drain(receiving-space 제약 포함)이 유입을 늘
    소화 → storage 정체 안 됨. 이는 시나리오 특성이지 코드 결함이 아님.
  - 대응: drain receiving-space 캡까지 적용(위험요소3 fallback 1단계). 그 이상(drain 인위
    축소)은 plant 동역학 왜곡이라 미적용(plan "plant 보존식 변경 금지").
  - 의미: total_delay 불변은 "Wu 권한(green+VSL)의 정직한 한계"로 해석 가능(plan 의도 충족).
    협상 퇴화는 해소됐고, 이 시나리오에서 VSL로 줄일 capacity-drop이 없을 뿐.

## TODO (이 작업 이후, plan §이후순서)
1. λ_eff(t) 수정 — leader.py/centralized_mpc.py objective 고정 차로수 → λ_eff(t).
2. 4-controller 풀 매트릭스 7200s 재실행.

## 커밋
a241d84 신규 헬퍼 / 19089f1 캐시 / 6c85cc5 u_on 교체 / 0acb4fc storage probe /
0d3f85a density_penalty 제거+drain 캡 / e077e77 coupling+Jacobi / 7413b2b 문서 / a79b3af 테스트
