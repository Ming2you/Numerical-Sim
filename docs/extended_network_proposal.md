# 확장 네트워크 정의 제안 — 6-교차로 grid + 2 freeway

대상: Codex. 목적: 현재 config의 urban 토폴로지(통제신호 A/C/D/F 4개, grid 없음, 램프 6개)가
의도된 **확장 네트워크**(Van den Berg 2007을 확장한 6-교차로 grid)와 맞지 않으므로, 올바른
토폴로지로 `src/config/default.yaml`의 network 정의와 `docs/spec/03_traffic_models.md`의 네트워크
설명을 정정한다. **canonical 반영은 Codex가 코드와 함께 한 커밋에서.**

배경: 현재 config는 Van den Berg의 "통제 교차로 A·C 2개 + 횡단도로 B·D·E + 램프 4개"를
임의로 변형해(통제 4개·램프 6개·grid 없음) 토폴로지 자체가 어긋나 있다. 사용자 확정 설계는
아래 확장 grid이다.

## 1. 네트워크 구조 (확정)

```
   ↑in/out   ↑in/out   ↑in/out
    [A]──────[B]──────[C]
 ←in│         │         │in→
    [D]──────[E]──────[F]
 ←in│       (내부)       │in→
   on/off              on/off   ← D·F 램프 (각 on+off, FW_W·FW_E 둘 다에 연결)
   ══ FW_W: W0─W1─W2 ══   ══ FW_E: E0─E1─E2 ══   (두 freeway 독립)
```

**교차로 6개**: A,B,C(상단) / D,E,F(하단).
- **통제(controlled) 교차로 = A,B,C,D,F (5개)**. 각각 신호 제어.
- **E = 비통제(내부 라우팅 노드)**. 흐름은 통과시키되 신호 결정 없음(고정/우회).

**Grid 내부 링크 7개(양방향)**: A-B, B-C, A-D, B-E, C-F, D-E, E-F.

**경계(외부) in/out**:
- 상단: A, B, C (각 위쪽 유입/유출)
- 좌측: A, D (각 왼쪽 유입/유출)
- 우측: C, F (각 오른쪽 유입/유출)
- → 노드별: A=상+좌, B=상, C=상+우, D=좌, F=우, E=없음.
- perimeter 제어 관점: A·B·C·D·F가 gate, E(및 내부)가 보호 영역.

## 2. Freeway + 램프

- **Freeway 2개 독립**: FW_W(세그먼트 W0,W1,W2), FW_E(E0,E1,E2). 각 3세그먼트.
- **램프 4개**: D에 on+off, F에 on+off. **D·F의 램프는 각각 FW_W·FW_E 둘 다에 연결**(on-ramp는
  두 freeway로 split, off-ramp는 두 freeway에서 merge).
- **램프-세그먼트 위치(현 코드 관례 유지)**: on-ramp는 **중간 세그먼트(W1, E1)** 에서 merge,
  off-ramp는 **마지막 세그먼트(W2, E2)** 에서 분기.
  - 따라서 FW_W의 W1 merge = D·F의 on-ramp 유입(둘 다), W2 = D·F off-ramp(둘 다). FW_E도 동일.

## 3. on-ramp 2저수지 + delay 귀속 (확정)

on-ramp 흐름은 2저수지로 유지하되 **delay를 "제어 주체"에 귀속**한다.
```
교차로 D/F의 on-ramp 회전 movement(x_on)  ──[D/F green]──▶  on-ramp 큐(w_r)  ──[ramp metering]──▶  freeway 합류
       (urban이 green으로 게이트)                          (freeway가 metering으로 제어)
```
- `x_on`(접근부 회전 큐) → **urban agent** delay.
- `w_r`(램프 큐) → **freeway agent** delay. ← (현 코드는 w_r을 urban TTT에 넣음. 정정 필요.)
- off-ramp(storage + 배출 movement) → **urban agent** delay (현 상태 유지).
- Wu §IV-C와 일치: freeway agent 목적에 on-ramp 큐 `n_{i,m}`(=w_r) 포함 → metering 유인.

## 4. config 변경 지시 (대표 항목)

- `network.signals`: `[A,B,C,D,F]` (통제). E는 별도 `uncontrolled_nodes: [E]` 또는 movement에
  신호 없는 통과 노드로 정의.
- `network.urban_links`(신규): grid 7링크 + 방향/저장용량.
- `network.urban_movements`: grid 흐름(예: in_A→A→B/D, A→on-ramp 등) + on-ramp(D/F)·off-ramp(D/F)
  movement. on-ramp movement의 **제어 신호를 phase 기준으로 명시**(D_p?, F_p? — `signal` 필드를
  실제 통제신호로). 기존 `signal=R1..R4` 같은 오용 제거.
- `network.boundary_in_links`/`boundary_out_links`: A(상·좌), B(상), C(상·우), D(좌), F(우).
- 램프: `ramp_to_freeway`를 D·F 각각이 FW_W·FW_E **둘 다**에 연결되도록(또는 on-ramp split ratio로
  두 freeway 배분). `off_ramp_from_freeway`도 D·F가 양 freeway에서 수취.
- `freeway_links`: FW_W, FW_E (각 3세그먼트, 독립 — 직렬 결합 없음).

## 5. 검증
- no-control sweep로 grid가 의도대로 흐르는지(E 통과, 경계 유입/유출, D·F 램프 교환) 시계열 확인.
- 램프 delay 귀속: 동일 시나리오에서 freeway TTT에 w_r이, urban TTT에 x_on·off-ramp가 잡히는지
  (총 TTT 불변, 귀속만 재배분) 단위/통합 테스트.
- 이 토폴로지 위에서 [distributed_followers_proposal.md](distributed_followers_proposal.md)의
  agent 배치(urban 5 + freeway 6)가 일관되는지.
