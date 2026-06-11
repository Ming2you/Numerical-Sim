# 그리드 내부 라우팅 구현 제안 — turning ratio β 자연 분산 (spec §3.3.5)

대상: Codex(또는 Claude 직접). 목적: 현재 urban model은 **그리드 내부 라우팅이 미구현**이다 —
`next_movement`를 쓰는 movement가 0개, 그리드 링크(A_B/A_D/D_E…)에 storage 없음, 모든 차량이 첫
receiving link에서 "destination=grid"로 **종료**한다. 즉 교차로 사이를 흐르는 through 교통이 없어
"protected network"가 연결된 그리드가 아니라 **독립적인 경계 movement 묶음**이다. 이것이 내부 누적
부재·n_crit 왜소·off-ramp 소멸의 공통 뿌리다. spec §3.3을 제대로 구현해 **모든 차량이 교차로별
turning ratio β로 자연 분산하며 그리드를 통과**하도록 한다.

## 0. 사용자 확정 결정

1. **교차로별 고정 turning ratio β** (OD 행렬 아님).
2. **β 자연 분산** — boundary_in 진입 차량은 목적지 지정 없이 β로 흩어져 흐름.
3. **off-ramp 유입 차량도 동일하게 β 분산** — D/F에서 그리드 합류 후 일반 차량과 구분 없음(종료 처리 제거).

## 1. 토폴로지 (확장망)

- **교차로 6**: A,B,C(상) / D,E,F(하). **통제 5**: A,B,C,D,F. **E=비통제 통과 노드(신호 없음, β로 전달만).**
- **내부 양방향 링크 7**: A-B, B-C, A-D, B-E, C-F, D-E, E-F. (각 링크 = 방향별 2개 directed link.)
- **경계 게이트(외부 in/out)**: A(상·좌), B(상), C(상·우), D(좌), F(우). E 없음.
- **램프**: D·F 각각 on/off, 양 freeway(FW_W·FW_E)에 연결.

**노드별 인접(들어오고 나가는 방향)**:
```text
A: ↔B(A_B) ↔D(A_D) | 경계 in/out(top,left)
B: ↔A ↔C(B_C) ↔E(B_E) | 경계(top)
C: ↔B ↔F(C_F) | 경계(top,right)
D: ↔A ↔E(D_E) | 경계(left) | on/off-ramp(W,E)
E: ↔B ↔D ↔F(E_F) | (경계·신호 없음)
F: ↔C ↔E | 경계(right) | on/off-ramp(W,E)
```

## 2. 그리드 링크 storage + transit (신규)

- 7개 내부 도로를 **방향별 directed link 2개씩(총 14개)** storage 부여(`urban_link_storage_veh`에 추가).
  **용량 확정: 220**(경계 entry/out과 통일). 네이밍은 방향 명시: `A_to_D`/`D_to_A`, `D_to_E`/`E_to_D` 등
  (경계는 끝이 외부라 entry/out, 내부는 끝이 교차로라 X_to_Y — 둘 다 그냥 방향 링크).
- transit은 **이미 수정된 `_link_delay_steps`(spec §3.3.5, available 기반)** 를 그대로 적용 → 내부 링크도
  체류·backpressure 발생. (현재 entry/out/ramp 링크만 storage라 grid 링크 추가가 핵심.)

## 3. 내부 movement + 신호

- **movement = (incoming approach o, intersection s, outgoing direction d)** — spec §3.3 `x[o,s,d]`.
  각 교차로에서 들어온 방향 o에서 나가는 방향 d로 가는 대기 큐. **U-turn 제외**(d≠o).
- 예) D: incoming {A_D, D_E, in_D_left, off_ramp_W, off_ramp_E} × outgoing {A_D, D_E, out_D_left,
  on_ramp_W, on_ramp_E}, U-turn 빼고. 각 (o→d)가 movement.
- **신호 phase**: 통제 교차로(A,B,C,D,F)는 내부 movement도 phase로 서비스(green이 m_dep_int 결정,
  spec §3.3.1). **E는 신호 없이 통과**(green=1 상당, β로 전달만).
- 경계/램프 movement는 이 체계의 **특수 케이스**: boundary_in = 외부→그리드 진입(o=외부), boundary_out =
  그리드→외부 **system sink**(d=외부, 모델 이탈), on_ramp = 그리드→freeway **transfer**(d=ramp, sink 아님 —
  freeway로 핸드오프해 계속 system 내), off_ramp = freeway→그리드 진입(o=ramp, freeway에서 transfer).

## 4. β turning ratio (핵심)

- **β[o,s,d]**: 교차로 s에서 방향 o로 들어온 차량이 방향 d로 갈 분율. spec §3.3.5:
  `m_arr[o,s,d] = β[o,s,d] · arrived_to_queue_tail[o,s]`, `Σ_d β[o,s,d] = 1`, U-turn β[o,s,o]=0.
- **config 신규** `turning_ratios`(교차로별). **기본값(확정): 직진 우대** — 직진(있으면) 0.5, 나머지
  가용 outgoing(U-turn 제외)에 균등 분배. (직진 없는 노드는 가용에 균등.) Σ=1 보장. corridor 흐름 현실적.
- **목적지별 처리**:
  - d=boundary_out → **system sink**: 서비스 후 모델 이탈(외부세계).
  - d=on_ramp → **freeway로 transfer**: x_on→w_r→freeway(기존 coupling). 그리드는 떠나지만 system 내 계속.
  - d=내부 링크 → 다음 교차로 movement로 `next_movement` 체인(β 분산 계속).
- **자연 분산 정합성**: 모든 노드에서 출구(boundary_out 또는 on_ramp 경유 freeway 본선)로 가는 경로가
  존재하면 차량은 결국 이탈. β가 내부 순환만 만들지 않게 출구 방향 β를 0으로 두지 말 것.
- ★ on_ramp는 **sink가 아님** — freeway로 핸드오프된 차량은 freeway를 달리다 본선 유출(system sink)하거나
  off_ramp로 urban 복귀(다시 β 분산). 이 urban↔freeway 순환이 integrated 모델의 핵심.

## 5. 흐름 체인 (spec §3.3.5 — 이미 명세, 미구현)

```text
movement (o,s,d) 서비스(green) → receiving_link l_{s,d}에 deposit
  → 링크 travel delay(_link_delay_steps) 후 arrival_buffer[next_movement]에 도착
  → 다음 교차로 s'에서 β[d,s',·]로 분산 → 반복
  → d=boundary_out이면 system sink 이탈; d=on_ramp이면 freeway로 transfer(계속); 그 외 다음 교차로로
```
- `next_movement`: receiving_link이 도달하는 다음 교차로의 movement. **모든 내부 movement에 설정**(현재 0개).
- off-ramp/boundary_in 진입: arrival_buffer로 해당 교차로 movement에 주입 후 동일 체인.
- **off-ramp 종료 제거**: `OR_*_to_*_grid`의 destination을 "grid"(종료)가 아니라 **그 교차로의 내부
  movement로 연결**해 β 분산에 합류.

## 6. 수요

- boundary_in: 게이트에 유입(기존). off-ramp: D/F에 유입(기존, β 합류로 변경).
- **목적지 미지정** — β가 분산을 결정. 따라서 OD/destination 필드 불필요.

## 7. 재calibration / 영향

- 그리드 라우팅 도입 후 내부 누적 동역학이 바뀜 → **n_crit 재calibration 필수**(현 166은 임시).
- 누적이 entry 링크가 아니라 **실제 그리드 링크에 분포** → MFD가 더 현실적(자유류·혼잡 분지 모두 샘플링
  기대). calibration sweep(저수요 포함)이 곡선을 제대로 그리는지 확인.

## 8. 검증

- no-control sweep: 차량이 게이트 진입 → β로 그리드 통과 → boundary_out 이탈 또는 on_ramp로 freeway 전이
  하는 시계열. **보존(integrated)**: (urban 유입 + off_ramp 복귀) = (boundary_out 이탈 + on_ramp 전이 + Δurban누적).
  on_ramp 전이량 = freeway 유입량과 일치(차량 안 사라짐).
- `next_movement` 체인 동작(0→전체), 그리드 링크 storage 점유>0, 순환 차량 비율 유한(흡수 확인).
- off-ramp 차량이 그리드 통과 후 다른 출구(boundary_out/on_ramp)로 가는지(종료 안 함).
- 보존 단위테스트: Σβ=1, U-turn 0, **on_ramp는 freeway로 핸드오프(소멸 아님)**, system 차량수 보존.
- 통합: n_crit 재calibration 후 perimeter 누적 규제·boundary balance가 의미를 갖는지.

## 9. 주의 / 순서

- 이건 urban model 핵심 추가라 단계적으로: (1) 그리드 링크 storage + 방향 directed link, (2) 내부
  movement·β·next_movement, (3) off-ramp 종료 제거→β 합류, (4) E 통과 노드, (5) 재calibration.
- 기존 transit 버그수정(`occupied→available`)·N_P 보호영역 재정의는 **유지**(이 작업의 전제).
- β 기본=균등이나, 현실성 위해 직진 우대 등 사용자 값 받으면 반영.
