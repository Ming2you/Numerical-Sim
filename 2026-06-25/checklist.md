# Leader↔Follower setpoint 일치(self-consistent Stackelberg) 구현 체크리스트

목표. leader가 commit하는 두 control variable(N_P*, N_UF*)이 follower가 실제로 실현하는
값과 일치하게 만든다. "연구는 정직하게" — 보고값이 실현값과 다른 현재 구조를 닫는다.

핵심 분담(2026-06-25 논의 확정).
- 층 1(출력 폐쇄): commit값 = realized, **정확 일치**. 목표 자체. 비용 0.
- 층 2(박스 타이트닝): intent 탐색을 도달집합으로 좁혀 saturation 평원 제거 + intent 잔차 축소.
  eps까지는 아님(감쇠 매핑). 탐색 정직성/효율 개선용.
- eps급 intent=realized(fixed-point/hard equality)는 leader 지렛대를 깎아 **채택 안 함**.

---

## Pre. 결정 입력(probe)
- [ ] `np_authority_probe_sweet128` 완료 → 혼잡 state에서 N_UF* 고정 시 N_P* 스윕의
      rollout_urban_ttt / total spread 확인.
- [ ] 판정. 권한 충분(spread 유의미) → 층2 N_P 박스 교체 진행 /
      권한 미미(spread≈0) → 층1만 + N_P 약채널 리포트 명시.

## 층 1 — 출력 폐쇄 (무조건 적용)
- [ ] `stackelberg_mpc.py` best_eval 선택 직후, commit control의
      `N_P_star ← distributed_grid_leader_projected_net_inflow_veh`,
      `N_UF_star ← distributed_grid_leader_selected_metering_sum_veh_h`로 덮어쓰기.
- [ ] raw intent(탐색좌표)는 진단키로 별도 보존(`leader_intent_N_P_star` 등) — 추적성 유지.
- [ ] fallback(PFO/no-control) 경로에서도 동일 폐쇄 적용(또는 N_P*/N_UF*=0 유지 확인).
- [ ] 회귀. 기존 4-controller 결과의 *선택 자체*는 불변이어야 함(보고값만 realized로 바뀜).
      → P-Stack TTT/improvement 동일, N_P*/N_UF* 컬럼만 변화 확인.

## 층 2 — 박스 타이트닝 (probe 권한 확인 시)
- [ ] N_UF: leader 후보 상한을 `N_UF_star_range[1]`(=6000) 대신 follower의
      `sum(upper)`(공급+수용 한계)로. `freeway_follower._ramp_upper_bounds`와 leader
      `_feasible_nuf_capacity` 정합성 확인(중복/불일치 없게).
- [ ] N_P: `leader._movement_net_flow_bounds`의 디커플 over-approx `[-Σout,+Σin]`를
      probe 실측 도달 net-inflow 범위로 교체(또는 결합 추정으로 대체).
      → 단순 echo 되지 않게(지렛대 보존) 주의.
- [ ] saturation 평원 제거 확인. 좁힌 박스에서 leader 후보들이 서로 구분되는지
      (candidate objective 분산 > 이전).

## 검증(공통, 완료 전 필수)
- [ ] `py_compile` 통과.
- [ ] 관련 unittest 통과(leader/coordinator/freeway_follower/stackelberg).
- [ ] sweet_128(+135) 정밀 재실행(T=3600, full budget)에서 target=actual 겹침 그림 생성
      (Fig 3A류 재생성으로 gap 사라짐 시각 확인).
- [ ] N_P/N_UF 잔차(residual) 통계: 층1 후 commit residual≈0, 층2 후 intent residual 축소량 보고.

## 기록/커밋
- [ ] `2026-06-25/notes.md`에 변경/이유/결과 기록.
- [ ] 그림 `reports/figures/`, 결과 CSV `outputs/`.
- [ ] `git add . && commit "2026-06-25: leader setpoint self-consistency (출력폐쇄+박스타이트닝)"`.

## 불변 규칙
- 차량보존/plant 식 안 건드림. 변경은 leader 후보 박스 + commit 보고로 한정.
- capacity drop 현 default(anticipation ON, nu_cong=250) 유지(leader 활성 regime).
- 선택 로직(lexicographic) 자체는 유지 — 보고값만 realized로 폐쇄.
