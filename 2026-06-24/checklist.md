# Capacity Drop (Arora & Kattan modified METANET) 도입 — 체크리스트

근거: Arora & Kattan, *Operational and safety impacts of integrated VSL with dynamic HSR*,
J. Intelligent Transportation Systems. capacity drop = anticipation 파라미터 regime 분할
(γ_free/γ_cong, eq 9). eq 6(demand-supply)·eq 7(VSL speed cap)은 우리 plant에 이미 존재.

## Step 1 — 구현 (anticipation ν regime-split + toggle)
- [ ] state.py: `metanet_nu_cong_km2_h`(ν_cong), `capacity_drop_anticipation`(bool, 기본 False) 추가
- [ ] default.yaml: 동일 키 추가(기본 off → 기존 결과 불변)
- [ ] metanet.py: `select_anticipation_nu(rho, net)` 헬퍼 + 호출부에서 ν 선택
- [ ] 단위테스트: toggle off=불변, on+ρ>ρcr → ν_cong, 혼잡 gradient에서 v(ν_cong)<v(ν_free)
- [ ] 전체 회귀 통과(toggle 기본 off라 기존 테스트 영향 없어야 함)

## Step 2 — 튜닝 + hysteresis 관측 (게이트)
- [ ] ν_cong 튜닝: 목표 capacity drop α≈5–15% 확보(현상학적 보정, field data 없음 명시)
- [ ] rise-fall(transient surge) 수요로 plant 구동
- [ ] flow–density 궤적에서 **hysteresis loop 가시화** 확인 (figD류)
- [ ] loop 안 보이면 → 여기서 멈추고 재검토(3 진행 전)

## Step 3 — 수요 재설계 + 매트릭스 재실행 (loop 확인 후에만)
- [ ] 수요 패턴: peak / peak×1.4 / transient-surge(가운데 볼록 회복) / freeway-heavy / urban-heavy / skew(peak×1.x)
- [ ] capacity_drop on 매트릭스 재실행
- [ ] VSL 활성 재확인(이제 incident 외에도 켜지는지)
- [ ] 리포트 갱신

## 불변 규칙
- 밀도(차량보존)식은 안 건드림 — 변경은 속도식 anticipation ν 분할에 한정.
- toggle 기본 off로 기존 결과 재현성 보존. commit/push는 요청 시.

---

## 참조 수식 — Arora & Kattan modified METANET (논문 eq 1–11, 정확 전사)

표기. ρ=밀도(veh/km), q=flow(veh/h), v=속도(km/h), T=time step, L_i=segment 길이,
k_i=차로수, r_i/s_i=on/off-ramp flow. **논문 기호→우리 코드: s(반응시간 τ)→`metanet_tau_h`,
g(anticipation ν)→`metanet_nu_km2_h`, K(밀도상수 κ)→`metanet_kappa_veh_km_lane`,
a_i→`metanet_a_m`, ρ_cr→`rho_crit`, v_f→`v_free`.** (논문은 밀도도 'q'로 표기하나 아래선 ρ로 통일.)

### 기본 METANET (eq 1–4)
- **(1) 밀도 동역학(차량보존)**
  `ρ_i(k+1) = ρ_i(k) + (T/L_i)·[ q_{i-1}(k) − q_i(k) + r_i(k) − s_i(k) ]`
- **(2) 평형 desired speed (FD)**
  `V[ρ_i(k)] = v_{f,i} · exp( −(1/a_i)·(ρ_i(k)/ρ_{cr,i})^{a_i} )`
- **(3) METANET 속도식**
  `v_i(k+1) = v_i(k)`
  `           + (T/s)·{ V[ρ_i(k)] − v_i(k) }`                         ← relaxation
  `           + (T/L_i)·v_i(k)·[ v_{i-1}(k) − v_i(k) ]`              ← convection
  `           − (T·g)/(s·L_i)·( ρ_{i+1}(k) − ρ_i(k) )/( ρ_i(k) + K )` ← anticipation
- **(4) flow–density**  `q_i(k) = v_i(k)·ρ_i(k)`

### 수정 METANET (eq 5–10)
- **(5) 수정 밀도 동역학** (검출기 flow 보정 파라미터 λ_i 도입)
  `ρ_i(k+1) = ρ_i(k) + (T/L_i)·[ q_{i-1}(k) − λ_i·q'_i(k) + r_i(k) − s_i(k) ]`
  ※ λ_i는 *루프검출기 실측 flow 보정용*. **우리는 검출기 미사용·flow를 demand-supply로 직접 계산하므로
     λ_i 불필요(구현 제외).**
- **(6) 경계 flow = demand–supply(sending)**
  `q_i(k) = min( Q_{cap,i+1}, v_i(k)·ρ_i(k) )           if 하류 free:  ρ_{i+1}(k) < ρ_{cr,i+1}`
  `q_i(k) = min( v_{i+1}(k)·ρ_{i+1}(k), v_i(k)·ρ_i(k) )  if 하류 congested: ρ_{i+1}(k) > ρ_{cr,i+1}`
  ※ 우리 plant의 §3.1.2 sending=min(상류 demand, 하류 supply)와 동일 취지. **우리 구현과 등가인지 검증.**
- **(7) 수정 desired speed (VSL cap)**
  `V[ρ_i(k)] = min( v_{f,i}·exp(−(1/a_i)(ρ_i(k)/ρ_{cr,i})^{a_i}),  (1+ε)·v_{lim,i}(k) )`
  ※ ε=단속수준 상수. 우리 `effective_desired_speed_kmh`의 VSL cap과 매핑(우리 `alpha_vsl` ↔ ε) **검증**.
- **(8) 수정 METANET 속도식**: (3)과 형태 동일, 단 s,g,K를 link별 s_i,g_i,K_i로, **g_i는 (9)로 regime 분할**.
- **(9) capacity drop = anticipation regime 분할**  ★우리 step 1의 핵심★
  `g_i(k) = g_free   if 자유류:  ρ_i(k) < ρ_{cr,i}`
  `g_i(k) = g_cong   if 혼잡:    ρ_i(k) > ρ_{cr,i}`
  ※ (8)의 anticipation 항은 음수(하류가 더 혼잡할 때 감속)이므로 **g_cong > g_free 면 혼잡 시 감속↑
     → v↓ → q=ρv↓ = capacity drop 방향.** 우리 `select_anticipation_nu`가 정확히 이 분기.
     (`g_free`=`metanet_nu_km2_h`, `g_cong`=`metanet_nu_cong_km2_h`.)
- **(10) flow–density**  `q_i(k) = v_i(k)·ρ_i(k)` (=eq 4)

### 목적함수 (eq 11) — 참고용(우리 leader objective와 별개)
- **(11) TTT**  `TTT = T·Σ_{k=1}^{Η-1} Σ_{i=1}^{N} k_i·L_i·ρ_i(k)`  (+ 논문은 TTD 최대화를 더해 bi-objective)

### 검증 체크포인트 (Codex 검토용)
- [ ] (3)/(8) ↔ 우리 `metanet_speed_update_kmh`: relaxation `dt/τ·(V−v)`, convection `dt/L·v·Δv`,
      anticipation `−ν·dt/(τ·L)·Δρ/(ρ+κ)` — 계수·부호 일치 확인.
- [ ] (9) ↔ `select_anticipation_nu`: ρ>ρ_crit → ν_cong, 경계 포함 규칙(우리는 `ρ>ρ_crit` 엄격, 같으면 free).
- [ ] g_cong>g_free가 실제로 q를 떨어뜨리는지(부호/방향) — step 2에서 수치 확인.
- [ ] (6) demand-supply가 우리 §3.1.2 구현과 등가인지.
- [ ] (7) VSL cap의 (1+ε) ↔ 우리 alpha_vsl 매핑.
- [ ] (5) λ_i는 우리 미구현(검출기 미사용) — 의도된 제외임을 확인.
