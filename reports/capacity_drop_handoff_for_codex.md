# Codex 인계: Capacity Drop (modified METANET) 도입 — 진행상황과 남은 일

이 repo(`Numerical-Sim`) 루트에서 작업. 목표는 METANET plant에 **capacity drop**을 넣어
(1) VSL이 incident 외에도 의미 있게 작동하게 하고, (2) flow–density **hysteresis loop**를 관측하는 것.

## 배경 (왜 하는가)
- 현 plant는 표준 METANET 평형 FD(단일값)라 capacity drop이 없다. 그래서 flow–density에 hysteresis가
  없고, **VSL은 물리적 차로감소(incident)에서만 켜진다**(mainline VSL의 throughput 이득 = capacity-drop
  방지인데, drop이 없으니 평시엔 delay 재배치만 함).
- 채택 방식: **Arora & Kattan modified METANET** — capacity drop을 anticipation 파라미터 regime 분할
  (γ_free/γ_cong)로 표현(eq 9). 우리 plant엔 demand-supply(eq 6)·VSL speed cap(eq 7)이 이미 있어,
  **추가할 핵심은 eq 9뿐**.
- **수식 정본은 `2026-06-24/checklist.md`의 "참조 수식" 절(eq 1–11 정확 전사 + 코드 매핑)** 참고.

## 불변 규칙 (반드시 준수)
- **밀도(차량보존)식은 건드리지 말 것.** 변경은 속도식 anticipation ν 분할에 한정.
- toggle `capacity_drop_anticipation` 기본 **off** 유지 → 기존 결과 재현성 보존.
- commit 메시지: `YYYY-MM-DD: 설명` + 끝에 `Co-Authored-By: ...`. 작업 기록은 `YYYY-MM-DD/notes.md`.
- 런타임 python: `C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B`

---

## ✅ DONE — Step 1 (구현, commit 030885b)
anticipation ν regime-split + toggle. **밀도식 불변.**
- `src/models/state.py`, `src/config/default.yaml`: `metanet_nu_cong_km2_h`(=ν_cong, 기본 65.0),
  `capacity_drop_anticipation`(bool, 기본 false) 추가. (network 파라미터 그룹.)
- `src/models/metanet.py`: `select_anticipation_nu(rho, net)` — toggle on & ρ>ρ_crit면 ν_cong,
  아니면 ν_free(=`metanet_nu_km2_h`). 속도식 호출부가 이 헬퍼를 사용.
- `src/tests/test_capacity_drop.py`: 3종(toggle 분기 + 혼잡 gradient에서 ν_cong>ν_free → v↓·q↓).
- 검증: `python -B -m unittest src.tests.test_capacity_drop src.tests.test_metanet_equations` → 24/24 OK.
- **방향 주의**: anticipation 항은 음수(하류가 더 혼잡할 때 감속)이므로 **ν_cong > ν_free 여야 capacity
  drop 방향**(혼잡 시 감속↑ → v↓ → q=ρv↓). 현재 기본값은 ν_cong=ν_free=65이라 효과 0(=off 상태와 동일).

---

## ⏳ TODO — Step 2 (튜닝 + hysteresis 관측) ← **게이트. 여기서 loop 안 보이면 멈추고 보고**

### 2-1. toggle on + ν_cong 튜닝
- 활성화: config override 또는 default.yaml에서 `capacity_drop_anticipation: true`, `metanet_nu_cong_km2_h`를
  ν_free(65)보다 크게(예: 100 → 150 → 250 sweep).
- 목표: 혼잡 분기 방출량이 자유류 capacity(Q_max ≈ 3,800 veh/h, 현 figD 기준) 대비 **α≈5–15% drop**
  (즉 혼잡 discharge ≈ 3,200–3,600). field data 없으므로 **현상학적 보정**임을 보고서에 명시.

### 2-2. rise-fall(transient surge) 수요로 구동 → hysteresis 관측
- **중요**: loop를 보려면 수요가 **올랐다 내려가야** 한다(loading→unloading). 단조증가 수요로는 capacity
  drop을 넣어도 unloading 분기가 없어 loop가 안 보인다.
- 작은 standalone 드라이버를 써서(예: `2026-06-24/diag_scripts/`에 신규) 단일 freeway 구간에 rise-fall
  수요를 주입, 매 step `rho`/`speed`/`flow=rho·speed·lanes` 기록 → flow–density 산점도에 **시간 순서로
  궤적**을 그려 loop 확인. (참고: `2026-06-24/diag_scripts/penalty_analysis_figs.py`의 figD가 flow–density
  산점 예시.)

### 2-3. 게이트 판정 (성공 기준)
- [ ] toggle on에서 혼잡 분기 discharge가 자유류 capacity 대비 목표 α만큼 낮음(capacity drop 확인).
- [ ] rise-fall 수요에서 flow–density 궤적이 **닫힌 loop**(loading 경로 ≠ unloading 경로)를 그림.
- [ ] toggle off면 loop 없음(기존과 동일) — 대조 확인.
- **loop가 안 나오면**: ν 분할만으로 부족할 수 있음 → 멈추고 보고(대안: 회복 임계 ρ_recover<ρ_crit로
  이력상태 추가, 또는 discharge에 직접 drop 항). step 3 진행 금지.

---

## ⏳ TODO — Step 3 (수요 재설계 + 매트릭스 재실행) ← **2 게이트 통과 후에만**

### 3-1. 수요 패턴 재설계 (`src/config/scenarios.yaml`)
사용자 요청 패턴:
1. peak
2. peak × 1.4
3. **transient surge**(가운데 볼록 올라왔다 회복) ← hysteresis 관측의 핵심
4. freeway 수요 過多
5. urban 수요 過多
6. peak × 1.x 에서 skew(공간 비대칭)
- 기존 다수는 multiplier로 이미 가능(peak/heavy_140·150/skew_*). transient surge 시간프로파일이 신규.

### 3-2. 매트릭스 재실행 + 분석
- [ ] `capacity_drop_anticipation: true` (+ 튜닝된 ν_cong)로 4-controller 매트릭스 재실행.
- [ ] **VSL 활성 재확인**: 이제 incident 외(평시 혼잡)에서도 VSL이 켜지는지 — 이게 capacity drop 도입의
      핵심 검증. (`control_timeseries.csv`의 vsl_* 가 자유류 max 미만으로 움직이는 interval 확인.)
- [ ] 사후분석 리포트 갱신(`reports/post_analysis_results_2026-06-23.md` 또는 신규): figD를 진짜
      capacity-drop/hysteresis로 교체, VSL 단락 갱신.

---

## Codex 검증 체크포인트 (코드 정합성)
`2026-06-24/checklist.md` "검증 체크포인트" 참조. 요약:
- (3)/(8) ↔ `metanet_speed_update_kmh`: relaxation `dt/τ·(V−v)`, convection `dt/L·v·Δv`,
  anticipation `−ν·dt/(τ·L)·Δρ/(ρ+κ)` 계수·부호.
- (9) ↔ `select_anticipation_nu`: ρ>ρ_crit → ν_cong (경계 같으면 free).
- (6) demand-supply가 §3.1.2 우리 구현과 등가인지.
- (7) VSL cap의 (1+ε) ↔ 우리 `alpha_vsl` 매핑.
- (5) λ_i(검출기 보정)는 우리 미구현 — 의도적 제외.
