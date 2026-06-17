# off-ramp 큐 freeway 재귀속 설계 (2026-06-17)

## 0. 한 줄 요약
off-ramp 램프 큐(`OR_*_storage`)를 **urban → freeway로 재귀속**(plant 공통)한다. 그러면 urban
신호가 off-ramp leg를 못 빼줄 때 off-ramp가 backup하고, 그 큐가 **freeway agent 자기 TTT**에
잡혀 — 별도 trigger 없이 — **VSL metering이 emergent하게** 발현한다. intersection leg(urban
접근로)는 urban에 그대로 둔다.

## 1. 배경 / 문제
- N_P 보존식: `dN_P/dt = (boundary_in + off_ramp_in) − (boundary_out + on_ramp_out + 완료)`.
- 현재 off-ramp 유입은 제어가 **외란으로 고려하지 않고**, off-ramp 큐는 **urban TTT/N_P에 귀속**돼
  있다. freeway agent는 자기 TTT(segment+on-ramp 큐)만 최소화하므로 off-ramp 유입을 줄일 유인이
  없다(오히려 off-ramp로 빼면 freeway 차량↓ → 자기 TTT↓이라 더 쏟아내려 함).
- peak 진단(P-STACK 7200): leader는 N_P_star≈536(critical 근처)로 옳게 목표하나 실제 N_P
  714~1527. off-ramp 유입(≈724/interval) > perimeter 배수(≈−443) → N_P 폭증. **off-ramp가
  제어 목적함수에 안 들어간 게 핵심.**

## 2. 핵심 아이디어 (trigger 금지, emergence)
off-ramp를 **물리적 위치로 분리**해 올바른 주체의 TTT에 귀속한다.
- **off-ramp 램프(diverge~정지선, `OR_*_storage`)** → **freeway TTT/agent objective**.
- **intersection leg(off-ramp이 합류하는 urban grid 링크·신호 큐)** → **urban TTT** (현행 유지).

### emergence 인과 (trigger 없음)
1. urban 신호가 leg를 못 빼줌 → leg 참 → off-ramp 배출 막힘(이미 `_drain_offramp_storage`가
   urban 수용공간으로 gating) → off-ramp 큐 backup.
2. off-ramp 큐가 **freeway agent 자기 TTT**에 잡힘.
3. freeway agent가 자기 TTT를 줄이려 함 → off-ramp를 더 못 빼니(urban이 막아서) 남은 수단은
   **상류 VSL metering** → diverge 도달량↓ → off-ramp 유입↓ → off-ramp 큐↓ → 자기 TTT↓.
4. ⇒ **VSL이 자연히 metering.** selfish freeway agent가 자기 큐를 지키는 것뿐.

이는 실제 freeway 운영(자기 ramp 큐 spillback 방지 metering) 및 **Wu의 off-ramp 적체→
capacity-drop→VSL 계열과 동일**하다. 따라서 proposed 전용 hack이 아니라 물리 표준이며, plant
공통으로 둬도 WU와 모순 없다(오히려 WU도 off-ramp를 freeway로 일관되게 느낌 → 비교 공정).

## 3. plant 공통 귀속 결정
귀속은 **controller objective가 아니라 plant 차원의 TTT 분해**로 한다. 즉:
- `total_ttt = freeway_ttt + urban_ttt` 합은 **불변**(귀속만 이동, 총량 보존).
- off-ramp 램프 지연이 freeway 회랑 지연으로 계상됨 — 모든 controller(WU 포함)가 동일 plant에서
  같은 분해를 봄.

## 4. 변경 명세 (코드 위치별)

### 4.1 TTT 분해 (freeway_ttt ↑ / urban_ttt ↓)
- `src/models/urban_queue_model.py` (urban_ttt 계산 ≈887행, `run_coupled_interval`/coupling 경로):
  urban_ttt에서 **off-ramp storage(`OR_*_storage`) 점유분 제외**.
- freeway_ttt 계산부(`src/simulation/coupling.py` 또는 metanet TTT 집계): off-ramp storage
  점유분을 **freeway_ttt에 가산**. (off-ramp storage는 `net.off_ramp_storage_link` 집합.)
- 검증: 임의 상태에서 `freeway_ttt+urban_ttt` 합이 변경 전후 동일(보존).

### 4.2 N_P 정의 (off-ramp segment 제외)
- `src/models/state.py` `protected_accumulation_veh` (≈633행): `protected_kinds`에서 off_ramp
  관련 제거 — off-ramp storage 점유·off_ramp movement 큐를 **N_P에서 뺀다.** off-ramp 차량은
  신호를 통과해 urban grid 링크로 들어와야 N_P에 잡힌다.
- `total_urban_vehicles`(≈639행)도 off-ramp storage 점유 제외(N_P/leader base 일관).
- ⚠️ **N_P 정의가 바뀌므로 `N_P_crit_veh` 재calibration 필수**(현 556.081 무효화 → §6).

### 4.3 freeway agent local TTT에 off-ramp 큐 추가 (emergence의 핵심)
- WU: `src/controllers/wu_distributed.py` `_solve_freeway_agent`의 local TTS
  (`link_vehicles + link_ramp_queue`, ≈467-476행)에 **해당 링크의 off-ramp storage 큐 가산**.
  VSL 후보별 off-ramp 큐 변화는 기존 storage-aware probe(`_update_probe_offramp_storage`)가
  이미 예측 → 그대로 활용.
- proposed: `src/controllers/distributed_coordinator.py` freeway agent objective/`_agent_vsl`
  (≈398-478행)에 off-ramp storage 큐 반영 + VSL→off-ramp 예측 결합 보강(현재 밀도비+lane_loss
  휴리스틱이라 off-ramp 큐를 안 봄 → 추가).
- P-CENT: `src/controllers/centralized_mpc.py` total objective는 freeway+urban 합이라 §4.1
  분해 수정이 자동 반영(off-ramp가 freeway TTT로). VSL→off-ramp 결합이 plant 예측에 잡히는지 확인.

### 4.4 이중계상 방지
- off-ramp storage 큐는 **freeway에만** 계상(urban TTT·N_P·urban agent objective에서 제거).
- 직전 작업(B: urban green objective에 off-ramp leg)과 **상충 정리** — leg = urban grid 링크
  (urban), 램프 storage = freeway. 둘은 다른 큐이므로 각자 한 곳에만.

### 4.5 off-ramp 배출 gating (이미 존재 — 확인만)
- `_drain_offramp_storage`(Wu식3)가 off-ramp→urban 배출을 urban 수용공간·green으로 gating →
  urban이 막히면 off-ramp backup. 동작 확인만, 수정 불필요.

## 5. 보존·물리 불변식
- **차량 보존**: 귀속 이동이라 총 차량·총 TTT 불변. substep 보존 항등식 residual ≈ 0 유지.
- plant 동역학(METANET·movement queue·off-ramp drain)은 **변경 없음** — TTT/누적의 **집계 귀속만** 이동.

## 6. 영향 범위 / 리스크
- **N_P 정의 변경 → n_crit 재calibration 필수**(off-ramp 제외된 새 MFD 정점). 기존 556.081 폐기.
- freeway_ttt/urban_ttt 분해가 바뀌므로 **기존 모든 비교 결과 재생성** 필요(절대 비교는 변하나
  total은 불변이라 controller 간 total 비교는 유효).
- `protected_accumulation_veh`/`total_urban_vehicles` 참조 테스트 다수 갱신 필요.
- WU faithfulness: plant 공통이라 WU도 off-ramp를 freeway로 느낌 — Wu capacity-drop과 동일
  계열이라 정합. 단 WU 절대수치는 바뀜(재실행).

## 7. 성립 조건
- **transfer 수요가 충분해 off-ramp가 실제로 차야** emergence가 발현. 현 split=0.06 →
  off-ramp 점유 ≈0.011(거의 빔) → backup 無 → metering 無. **heavy-transfer 시나리오(split↑)**
  에서 검정해야 함. (기존 미해결 "off-ramp 안 참" 이슈와 동일 뿌리.)

## 8. 검증 게이트 (코더+리뷰어)
- **G1 보존**: `freeway_ttt+urban_ttt` 합 변경 전후 동일, substep residual ≈0, 전체 테스트 통과.
- **G2 재귀속 단위검사**: off-ramp storage 큐가 freeway_ttt에 잡히고 urban_ttt·N_P에서 빠짐,
  이중계상 0. off-ramp 큐 채운 상태로 freeway agent local TTT가 그만큼 커짐.
- **G3 emergence 관찰(핵심, trigger 無)**: heavy-transfer 시나리오에서 off-ramp backup 시
  **VSL이 자연히 내려가는지**(P-CENT·P-STACK·WU 각각), off-ramp 큐·N_P가 그에 따라 완화되는지
  관찰. (강제 아님 — 목적함수에서 emergent해야 함.)
- **G4 n_crit 재calibration**: 새 N_P 정의로 MFD 재측정 → config 갱신.
- **G5 회귀**: 전체 테스트, WU/P-FO/P-CENT 동작 일관.

## 9. 작업 순서
1. §4.1 TTT 분해 이동 + G1 보존 확인.
2. §4.2 N_P 정의 수정 + 참조 테스트 갱신.
3. §4.3 freeway agent local TTT에 off-ramp 큐 + VSL 예측 결합.
4. §4.4 이중계상 점검.
5. G4 n_crit 재calibration → config.
6. heavy-transfer 시나리오 마련 → G3 emergence 관찰.
7. 코더 구현 → 리뷰어 독립검증 → 통과까지 반복.

## 10. 미결 설계점 (구현 전 확정)
- off_ramp **movement 점큐**(storage와 별개의 작은 점큐)의 귀속 — 램프 측(freeway)으로 둘지
  leg 측(urban)으로 둘지. 물리적으로 "정지선 직전 대기"이므로 leg(urban)가 자연스러우나,
  storage와의 이중계상·gating 경로 확인 후 확정.
- heavy-transfer 시나리오의 split/수요 수치(off-ramp가 binding하되 과포화는 아닌 값).
