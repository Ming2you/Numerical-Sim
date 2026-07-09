# 2026-07-09 컨텍스트 노트 — Joint bilinear price

## 설계 결정 (근거 포함)

### 왜 bilinear cross-term 가격인가
per-lever 선형가격 `own_TTS(a) + w·g_a·(a−a_ref)`는 lever쌍의 교차곡률 ∂²V/∂a∂b를 못 담는다.
follower가 두 lever를 함께 움직일 때 선형근사가 cross-curvature만큼 어긋난다. 2차 확장:
`priced(a,b) = own_TTS(a,b) + w·[g_a(a−aref) + g_b(b−bref) + h_ab·(a−aref)(b−bref)]`.
여기서 h_ab는 **externality 교차** = h_global − h_local(follower가 own_TTS로 이미 보는 h_local은
빼서 이중계상 방지 — per-lever의 g_ext = g_i − d_local와 동일 철학).

### 왜 follower 2D 공동탐색이 필수인가
현재 green은 offset 동결로 1D 탐색(wu_faithful_follower.py:669), offset은 green 동결로 1D
탐색(_solve_offset_local) = coordinate descent. bilinear 항 h·(g−gref)(o−oref)는 한 변수가
동결되면 다른 변수의 선형항으로 퇴화 → cross가 무력. 따라서 (green,offset)을 2D 격자로 함께
채점해야 cross가 실제 작동. non-ramp 신호는 own_TTS(green,offset)를 rollout_local_tts_phased로
직접 계산 가능(셋업 arr_by_substep는 ego green·offset 불변 → 1회 계산 후 이중루프).

### vsl×metering은 primal joint을 이미 포착
`_solve_freeway_agent_local`이 주어진 metering(probe_prev)마다 VSL 전 후보 best-response를
돌리므로 min_meter min_vsl = 격자 전역최소를 이미 얻음(joint_wu_controllers.py:10-13 주석).
따라서 여기선 **탐색 구조 변경 불요**, bilinear externality 가격만 vsl 채점(1761행)에 추가.

### 가격 rollout은 far(analytic MFD tail) 미포함 — 기존 per-lever와 동일 규약
기존 green price는 `_predict` TTT(=leader_value_depth로 3+d 깊이 rollout, analytic far 없음)를
씀. cross도 동일하게 `_predict` TTT의 4-corner 스텐실로 → deep tail은 depth로, far는 leader
후보선택(_leader_evaluation_base)에서만. 일관성·비트동일 유지.

### 범위 한정
- green×offset joint: **non-ramp 신호(A/B/C)만**. ramp 신호(D/F)는 storage 동역학 복잡
  (_solve_offset_local_ramp) → 기존 coordinate descent 유지. A/B/C corridor가 green-wave
  green×offset 결합의 이론적 무대라 방어 가능. ramp 신호 한계는 notes에 명시.
- 기본 OFF: 새 게이트 전부 False → 기존 경로 그대로(비트동일).

## 진행 로그
- (작성 중)
