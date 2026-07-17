# 2026-07-17 — "190은 왜 dual 재계산에서 나빠지나" 추적 / wave2 무효 판명

## 요약

| 항목 | 판정 |
|---|---|
| 내 λ 판독(0.425→0.450) | **오독** — 그 컬럼은 boolean 플래그였다 |
| λ의 실제 거동 | **bang-bang {0, 10}** — 400스텝 중간값 0개 |
| ③의 N_P dual | **inert** (λ_P ≡ 0). 두 경로로 독립 확인 |
| 가설 (c) 위반 게이팅 | **기각, 부호 반대** |
| wave2 (BUDGET_OFF/pricesonly 20런) | **무효** — 훅이 SEG13 경로를 못 막음 |
| 예산이 몫인가 가격이 몫인가 | **미측정** — 재실행 중 |

---

## 1. 컬럼 오독 — `leader_lambda_np_committed`는 가격이 아니다

```python
# stackelberg_wu_metered.py:2399
metadata["leader_lambda_np_committed"] = float(lam_next is not None)
```

`float(<bool>)`. 데이터 고유값 `{0.0, 1.0}`, 400/400 스텝. 내가 읽은 **0.4250 → 0.4500은
가격이 아니라 커밋 duty cycle 17/40 → 18/40**이었다. 이름이 가격처럼 생겼고 코드는 boolean을
넣는 **네이밍 함정**. 서브에이전트 2인이 독립적으로 같은 지점을 찾았고, 반증 리뷰어가 재확인.

이로써 "λ가 올랐는데 유입도 올랐다"는 **모순은 존재하지 않았다** — 내가 만든 것이었다.

형제 컬럼(같은 함정):
- `wu_faithful_np_cand_lambda_applied` — **또 다른 0/1 플래그**
- `wu_faithful_np_cand_lambda` — `wu_faithful_lambda_P`의 **정확한 별칭**(같은 변수, 두 이름)
- **진짜 λ = `wu_faithful_lambda_P`** (wu_faithful_follower.py:3937)

## 2. λ는 bang-bang — 그리고 ③엔 dual이 안 돈다

`wu_faithful_lambda_P`: 10셀 400스텝에서 값이 **{0.0, 10.0} 둘뿐, 중간값 0개**.
- ③: `{0.0}` 하나뿐 — **전 셀 전 스텝 λ≡0**
- PD4: 0이 80.7%, cap(10)이 19.3%

**로깅 아티팩트 아님**(리뷰어 검증): `np_pd_active=True`면 L3719가 `lambda_p = lam_curr`로
쓰고 L3714-3718이 **그 λ에서 green을 재수렴**시킨다("off-equilibrium commit 금지").
로그의 값이 **커밋된 green에 실제로 작용한 가격**이다. 반올림도 아님(`np_pd_residual`은
97개 고유값, −499.719~400.117 풀 정밀도).

**③의 λ≡0은 dual이 꺼져서가 아니다.** `np_candidate_lambda` 기본 **True** — dual은 켜져
돌고 있다. λ=0인 건 (51) corrector가 **실현-공간** 잔차로 λ를 재유도하는데 그 잔차가
**음수 → `max(0,·)`에 잘려서**다(L3113). λ_next는 141스텝 중 3스텝에서 nonzero(최대 3.1164)로
계산되지만 corrector가 도로 0으로 만든다.

⇒ 정확한 서술: **dual은 active지만 커밋 가격이 항상 0이다.**

### 행동으로 독립 확인 (wave2의 유일한 생존 결과)
`_pricesonly`(BUDGET_OFF+**NP_OFF**)가 `_budgetoff`와 **bit-identical 10/10**.
두 arm 다 사실상 ③였으므로(§4), 이건 **NP_OFF가 ③에서 진짜 무효**라는 뜻.
λ_P를 꺼도 아무것도 안 바뀐다 — λ_P≡0 측정과 **정합**.

**⇒ N_P dual은 플래그십에서 inert.** "V ⊥ N_P"(7/16), "N_P 축 붕괴 4/49"와 앞뒤가 맞는다.

### 2b. ★λ_UF도 죽어 있다 — 사용자 지적("dual도 죽인거 맞아?")

NP_OFF는 `nash_solver.np_price_enabled=False`만 세우므로 **λ_UF는 안 건드린다**. 그런데 재보니
**λ_UF도 항상 0**이었다.

| ③, 190_w, 웜업 후 40스텝 | 고유값 | 비영 |
|---|---|---|
| `wu_faithful_lambda_P` | `[0.0]` | **0/40** |
| `leader_lambda_uf_committed` | `[0.0]` | **0/40** |
| `wu_b2_price_*`(green) | — | **40/40** |
| `wu_b3_meter_price_*` | — | **40/40** |
| `wu_b3_vsl_price_*` | — | 24~40/40 |
| `wu_seg13_budget_*`(hard budget) | — | 17/40 |

이유: `nuf_dual_active`가 `wu_faithful_nuf_coordination_mode`를 보는데 **기본값이 `"equality"`**
(L3898·L2732) → dual 모드가 아니라 λ_UF는 **갱신조차 안 된다**. `dual_standing`도 항상 False.

**⇒ ③에 살아있는 dual 가격은 하나도 없다.** 실제 조정 수단은 **N_UF hard budget +
marginal price(green/meter/VSL, 58컬럼 전부 비영)** 둘뿐이다. Stackelberg dual 기계장치는 통째로 논다.

**⇒ `_budgetoff_fix`의 이름이 틀렸다.** 큐 주석에 "λ_UF·가격 전부 유지"라고 썼는데 **λ_UF는
유지할 게 없다**(공허). 실험 자체는 유효하지만 정확한 질문은 "예산 몫 vs 가격 몫"이 아니라
**"hard budget 채널이 필요한가"**다.

논문 §5(한계)에 **dual 2종 모두** 들어가야 한다.

## 3. 게인 산수 — 정정판

| 주장 | 리뷰어 판정 |
|---|---|
| 상수 0.01 × 25.0 = 0.25 | **확인**(follower L346, state.py:472, L3693-3695) |
| "잔차 324~580" | **기각** — 갱신에 들어가는 `np_pd_residual`은 **31.6~400.1**(평균 182.7), **33/99가 음수**. 324~580은 `np_target_error`를 **PD가 안 돈 301스텝까지 평균**낸 값 |
| "Δλ 81~145, cap 12배 초과" | **기각** — 실제 **7.9~100.0**, **0.79~10.0배** |
| "한 방에 포화" | **확인** — 양수잔차 PD스텝의 **63/66(95%)**가 Δλ≥10. gain 0.01이면 **0/66** |
| "25배가 내부 dual을 죽인다" | **PD4 한정 확인** — 내부 warm-start **77스텝 전부(77/77)** 다음 스텝 λ가 0 또는 cap |
| ③에 대해 | **공허** — `np_primal_dual_iters` 기본 0 → `np_pd_gain_mult`를 **읽지도 않음** |

### 새 진단으로 직접 관측(오늘 심음)
```
wu_faithful_np_pd_lam_path = 0.0000|10.0000
wu_faithful_np_pd_exit     = 2.0    # 고정점 break
wu_faithful_np_pd_residual = 48.07
```
**λ가 한 번의 갱신으로 0→cap, 그리고 "고정점 수렴"으로 종료.** 즉 **수렴이 아니라 경계 고착**인데
`run_log`에선 둘이 구분 불가였다. `wu_faithful_np_pd_{exit,lam_entry,lam_path}` 추가로 해소.
- exit: -1=루프 미실행, 0=K소진(미수렴), 1=잔차수렴, 2=λ고정점
- **exit=2 & 최종 λ=cap → 경계 고착**(수렴 아님)

## 4. ★wave2(20런)는 무효 — BUDGET_OFF가 SEG13 경로를 못 막았다

**증상**: `_budgetoff`, `_pricesonly` 모두 ③와 **30/30 bit-identical**. 전 컬럼 중 다른 건
`computation_time_sec`/`wu_faithful_solve_time_sec`(벽시계 잡음)뿐.

**원인**: 훅은 발화했다(`leader_budget_off=True` 스파이 확인). 그런데 그게 막는 건
`wu_faithful_follower.py:2886`의 **비-SEG13 링크별 분기**다. 플래그십은 **SEG13=1**이라
**L2592의 별도 SEG13 예산 경로**를 타는데 거긴 게이트가 **없었다**:

```python
# L2592 (수정 전)
if leader_present and nuf_mode == "equality" and preferred_meter:
    ...
    budget = min(max(omega_f * n_uf_star, 0.0), cap_sum)   # 똑같은 N_UF hard budget
```

**결정적 증거**: `wu_seg13_budget_FW_E/W`(③에서 비영 17/40)가 `_budgetoff`와 **완전 동일**.
예산은 한 번도 안 꺼졌다.

**수정**: L2592에 `not _budget_off_seg13` 추가.
**검증**: BUDGET_OFF=1 → `wu_seg13_budget_*` 키가 진단에서 **소멸**(분기 미진입).
BUDGET_OFF=0 → 2647/2678로 존재.

**이건 메모리의 "SEG13은 PFO 기준선을 깨뜨린다"와 같은 종류다** — SEG13이 코드 경로를
갈아치우는데 플래그는 옛 경로만 본다. **훅이 cfg에 도달한 것과 훅이 작동한 것은 다르다.**

**부수 관측(미해명)**: BUDGET_OFF=1이면 같은 상태(step 20)에서 `np_pd_exit`이 −1(PD 미실행),
BUDGET_OFF=0이면 2(실행). BUDGET_OFF가 N_P PD 활성화까지 건드린다 — 표본 2개라 미확정,
`_budgetoff_fix` 결과에서 확인할 것.

## 5. 가설 (c) 위반 게이팅 — 기각, 부호 반대

| | 리뷰어 재현값 |
|---|---|
| corr(Δ%TTT, viol_mean) | **+0.4390** (에이전트 주장 −0.351은 **③ 위반을 PD4 대신 쓰고 + 부호까지 뒤집어야** 재현) |
| 승자 vs 패자 위반 | 412.72 vs 441.72 — **위반 클수록 손해** |
| 190의 위반 순위 | **2위**(496.27). 최대는 200_w(571.78) |
| 190의 PD 발동 | 18/40 — **최다**(확인) |

**"손해가 cap 스텝에 안 몰린다"(C6)도 시간 교락**: corr(step, ΔTTT)=**+0.84**, λ=10 스텝은
초반(평균 idx 31.9) λ=0은 후반(42.8). step<40 층화하면 **역전** — λ=10 **+7.47** vs λ=0 **+3.05**
(190_w), **+8.36** vs **+4.26**(200_w).

⇒ 게인 가설은 내가 말한 것보다 **오히려 잘 서 있다**. 내가 댄 반증 근거(C5·C6)가 둘 다 틀렸고
바로잡으면 **반대 방향**을 가리킨다.

## 6. 진행 중

| 큐 | 내용 | 비고 |
|---|---|---|
| `_pd4_gain1` | PD4 + `NP_PD_GAIN=1.0`, 10셀 | 00:27 발주. **해석 주의**: mult=1/K=4는 Δλ≈1.83/iter×4 → 조기수렴 ①②를 못 걸고 **K만 소진** = "포화 vs **덜 풀린 상태**"(수렴 아님). 이기면 "내부 dual이 좋다"와 "dual이 해롭다"를 **구분 못 함** |
| `_budgetoff_fix` | BUDGET_OFF(게이트 수정), 10셀 | 00:47 발주. `_pricesonly` arm은 **불필요**(NP_OFF 무효 증명됨) |

## 7. TODO

- [ ] `_pd4_gain1` 판정 — **`np_pd_exit` 분포부터** 볼 것(0=K소진이면 리뷰어 예측 적중 = 해석 불가)
- [ ] 리뷰어 권고: mult 스윕 {25, 5, 1} × **K·gain 고정**(mult↓면 K↑) + `np_price_enabled=False` arm
- [ ] `_budgetoff_fix` 판정 — 예산 몫 vs 가격 몫
- [ ] BUDGET_OFF가 PD 활성화를 건드리는 부수효과 규명
- [ ] 단위테스트 미실행(pytest 없음, `src/tests` unittest는 10분 초과) — 백그라운드로 돌릴 것
- [ ] 논문 §5: **N_P dual inert**를 한계로 명시

## 8. 오귀속 기록

**오늘 추가된 것**(누적 1/22 → 여전히 갱신 중):
1. "λ가 0.425→0.450" → **boolean duty cycle 오독**
2. "λ 올랐는데 유입도 올라 모순" → **모순 자체가 없었음**
3. "잔차 324~580 → cap 12배 초과" → **PD 미실행 스텝까지 평균낸 값**, 실제 0.79~10배
4. "③엔 dual이 아예 없다" → **켜져 있고 커밋 가격만 0**
5. "손해가 cap 스텝에 안 몰림 → 후폭풍" → **시간 교락**, 층화하면 역전
6. "wave2가 예산 무용을 보였다" → **훅 불발**, 측정 자체가 없었음

**교훈**: bit-identical은 "효과 없음"이 아니라 **"훅 불발"일 수 있다.** 플래그 A/B는
**반드시 바뀌어야 할 진단이 실제로 바뀌는지**로 검증할 것 — cfg에 값이 꽂혔는지가 아니라.

## 9. 레버별 이동 한계 준수 감사 (사용자 질문, 2026-07-17 오후)

| 레버 | 명목 한계 | 실측 최대 |Δ|/step | 판정 |
|---|---|---|---|
| green | trust 6s (follower L1542 필터) | **6.00 — 정확히 경계** | 준수 |
| offset | max_offset_step 15s | 0 (190_w에서 동결) | 준수(자명) |
| **VSL** | **max_vsl_step 20 km/h** | **50 (2.5배)** | **위반** |
| metering | (박스 도입 전 한계 부재) | 박스 후 300.0 준수 | 박스로 해결 |

**VSL 위반 상세**: ③ 10셀 전체에서 112회/7,020관측(1.6%), 전 셀 최대 50.
seg 레벨에서도 확인(vsl_FW_E_seg0 40, vsl_FW_W_seg3 50) — link=min(seg) 아티팩트 아님.

**원인(코드 확정)**: VSL 후보 필터(L2371-2377)의 앵커가 직전 step commit이 아니라
**Jacobi 반복 내부 snapshot** — sweep마다 ±20씩 재앵커 → 스텝당 20×sweep수.
실측 40~50 = 2~2.5 sweep분과 정합. METER-BOX가 previous 앵커를 쓴 이유가 바로 이 구멍.

**판단**: ③에 원래 있던 것(전 구성 공유 → 기존 A/B 판정 무오염). 고치면 ③가 바뀌어
전 셀 재실행 + 동결 원칙 충돌 → 지금은 안 고침. §5에 한 줄 기재 + 필요시 previous 앵커
A/B를 별도 팔로. 
