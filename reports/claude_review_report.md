# Claude Review Report

_구현 커밋: `b0f2a6c` 위에 Claude 직접 구현(코덱스 토큰 소진). 미커밋(사용자 승인 대기)._
_요청: urban model이 queue/누적을 못 만드는 게 설계 의도인지 코딩 버그인지 spec 검토 + (A) N_P 재정의._

## ★ 결론 — urban model의 누적 부재는 **코딩 버그**였다 (spec §3.3.5 위반)

spec `03_traffic_models.md §3.3.5`는 내부 link travel delay를 명확히 규정한다:
```
travel_distance_to_queue_tail = S[u,v] * average_vehicle_length     # S = available(여유공간)
```
물리적으로 맞다 — 들어온 차량은 **큐 꼬리까지의 빈 공간**을 주행해 도달하므로, **빈 링크일수록 꼬리가
멀어 통과시간↑ → 체류 → 내부 누적 형성**.

그러나 구현 `_link_delay_steps`는 **`S`(available) 대신 `occupied = capacity − available`** 를 거리로 썼다.
→ 거리 관계가 **반전**: 빈 링크(occupied≈0)→거리≈0→**즉시 통과→누적 안 됨**. 이것이 보호영역이 늘
~9 veh로 텅 비고 n_crit이 ~10(degenerate MFD)이던 단일 근본 원인이다. **설계는 내부 누적을 의도했고
공식도 맞게 적혀 있었다; 구현이 한 단어(`occupied`↔`available`)를 뒤집었다.**

## 수정 (spec 충실)

- **`_link_delay_steps`: `occupied` → `available`(=S).** spec §3.3.5 그대로. (한 줄 버그 수정.)
- **(A) N_P 재정의**(병행): `TrafficState.protected_accumulation_veh(net)`=내부 storage 점유. perimeter
  accumulation 사용처만 교체(leader penalty/밴드, feedback, accumulation_error, 진단, calibration). TTT base·총량 로그는 total 유지.
- **n_crit 재calibration**: 354.809(stale) → **166.045**(버그 수정 후 실제 MFD). config·테스트 갱신. 56 테스트 통과.

## Verdict

**버그 수정으로 진짜 MFD 복원.** n_crit 10→**166**, 내부 누적 9→~150 veh, 리더가 누적을 critical 근처로
규제(tracking error **20**, target 166). Total TTT **+18.69%**(3600s, PASS). perimeter 제어가 비로소
"규제할 누적"을 갖게 됐다. acceptance는 아직 FAIL이나, 남은 2개는 **이 버그와 무관한 지표/구조 문제**
(net_inflow 정의, boundary_out 공큐).

## 진행 경로 (이번 세션)

1. **round-8~9**: acceptance를 §3.2 movement-level B로 정합 + degenerate 가드(Codex). 정직한 FAIL 도달.
2. **진단(7200s)**: 누적 N_P = `total_urban_vehicles`(=진입·램프 대기열)이 보호영역이 아님을 발견. 내부 그리드
   99.8% 텅 빔. → 사용자 (A) 결정.
3. **(A) 구현**: N_P = 내부 link storage 점유로 재정의. → accumulation error 1743→1.36. 그러나 n_crit=**9.968**
   판명 = **내부 그리드 체류≈0, MFD 동역학 부재**(즉시 통과). → 사용자 (i) 결정.
4. **(i) 구현**(이번): 링크를 고유 길이를 가진 transit 링크로.

## 진단 경로 (이번 세션)

1. **round-8~9**: acceptance를 §3.2 movement-level B로 정합 + degenerate 가드(Codex). 정직한 FAIL 도달.
2. **진단(7200s)**: 누적 N_P=`total_urban_vehicles`(=진입·램프 대기열)이 보호영역 아님 발견, 내부 그리드 99.8% 텅 빔.
3. **(A) 구현**: N_P=내부 storage 점유로 재정의 → accumulation error 1743→1.36. 그러나 n_crit=9.968 = MFD 부재 판명.
4. **spec §3.3.5 검토(이번)**: 내부 누적 부재가 **코딩 버그**(`occupied`↔`available`)임을 확인. spec대로 수정.

## 결과 (distributed peak_demand 3600s, spec 수정판)

| 지표 | round-9 (버그·총량 N_P) | **spec 수정 + (A)** |
|---|---:|---:|
| Total TTT | +14~20% | **+18.69%** (PASS) |
| n_crit (calibration) | 354.8(stale)·9.968(버그) | **166.045 (real MFD)** |
| 내부 점유(veh) | ~9 | **~150** |
| **accumulation error** | 1743 | **20.5** (target 166) |
| ramp metering error | 1346 | **789** (개선) |
| net_inflow_tracking | 3141 | 2597 (잔존) |
| boundary degenerate | 1 | 1 (잔존) |

- **✅ 버그 수정 효과**: 내부 누적이 9→~150으로 실재, 리더가 누적을 critical(166) 근처로 추적(error 20).
  진짜 MFD. perimeter 제어가 규제할 대상이 생김. (참고: 같은 효과를 내는 Greenshields 대안도 시험했으나
  spec 충실한 `occupied→available`을 채택.)
- MFD 주의: calibration sweep(scale 0.5~3.0)이 거의 같은 내부 점(accum~101)으로 saturate — 대부분 혼잡/평형
  분지만 샘플링, n_crit=166은 peak transient. 내부 누적 실재(목표)는 달성이나 MFD 곡선 정교화는 후속 가능.

## 남은 2개 (이 버그와 무관 — acceptance PASS를 위한 다음 작업)

**① net_inflow_tracking=2597 ≫ eps_U=100 (지표 정의).** `net_inflow_target≈0`(N_P가 target에 붙음)인데
realized `net_inflow=inbound−outbound`(**gross 경계 throughput**, d(N_P)/dt 아님). gate가 처리량을 페널티.
→ **realized net_inflow을 d(protected_accumulation)/dt로 재정의**, 또는 gate서 제거(accumulation tracking이 규제 담음).

**② boundary_balance degenerate(구조적).** outflow set = boundary_out(자유 유출→공큐 7개) + on_ramp(포화 4개)
→ empty_ratio 0.636 → 가드 발화. boundary_out은 외부로 자유 유출이라 안 쌓임 → §3.2 outflow 균등화 ill-posed.
→ outflow balance 대상에서 자유유출 boundary_out 제외하거나 균형 정의 재검토.

## 결론 / 권고

- **근본은 코딩 버그였다**: §3.3.5의 `S`(available)를 `occupied`로 구현 → 내부 누적이 안 생김. spec대로
  한 줄 수정으로 진짜 MFD 복원(n_crit 10→166, 누적 규제 error 20, TTT +18.69%).
- **다음(즉시)**: net_inflow을 d(N_P)/dt로 재정의(가장 명확한 잔여 gate 블로커). 그다음 boundary_balance의
  outflow 구성 재검토(자유유출 제외).
- **후속(선택)**: MFD calibration이 free-flow 분지도 샘플링하도록(저수요·uncongested 초기조건) 정교화.
- 코드 변경은 **미커밋**(사용자 승인 대기). src 7개 + config + 2 테스트.
