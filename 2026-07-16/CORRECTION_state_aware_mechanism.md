# 2026-07-16 ★정정 — ③의 이득은 g_fw가 아니라 **ramp 통과시간**에서 왔다 (오귀속 8번째)

## 무엇이 틀렸나
어제 보고: "far의 `g_fw=300` 상수가 차선폐색을 못 봐서 리더가 freeway 유입 비용을 과소평가.
`g_fw = min_i cap(lanes_i)`로 고쳐서 170_incident가 −10.45% → +1.21%."

**틀렸다. 그 코드는 한 번도 실행된 적이 없다.**

## 근거
1. `mfd_far_cost_to_go`의 freeway **본선** 블록(`t_trav`, `g_fw`)은 전부
   `if getattr(cfg.mpc, "leader_mfd_far_freeflow_offset", False):` 안에 있다.
2. **`leader_mfd_far_freeflow_offset` 필드는 `state.py`에 존재하지 않는다** → `getattr` 기본
   False → **죽은 분기**. `FAR_FF=1` env를 줘야만 켜지고, 우리 런은 준 적 없다.
3. 내 `state_aware` 수정 중 `g_fw`·`t_trav`는 **그 죽은 분기 안**이었다.

## 실제로 작동한 것 (그 분기 **밖**)
```python
if state_aware:
    t_ramp_traverse = Σ_{i≥midx} ℓ / V(ρ_i)     # 실제 밀도 속도(METANET FD)
else:
    t_ramp_traverse = (I−m)·ℓ / v_free           # 자유류 가정
far += (q*q)*tc_h/(2*merge_interval) + q * t_ramp_traverse
```
**ramp 합류 후 하류 통과시간의 자유류 가정만 고쳐졌다.** 과포화면 V(ρ) ≪ v_free → 통과가
오래 걸림 → far ↑ → 리더가 램프 방류에 신중. 사고 셀에 정확히 필요한 신호였고, 그래서
170_incident가 뒤집혔다.

**부수 확인**: skew 셀 Δ=0.0(완전 동일)도 이걸로 설명된다 — skew엔 ramp 큐(q)가 안 쌓이니
`if q <= 0.0: continue`로 항 자체가 안 켜진다. "terminal이 폐색만 본다"가 아니라
**"ramp 큐가 있을 때만 켜진다"**가 정확한 서술.

## 단위 버그 (미발화, 그러나 실재)
`far = n² · tc_h / (2·g)` 차원분석 → **g는 veh(구간당 대수)**이지 veh/h가 아니다.
- 기존 `g_fw = 300` veh/구간 (= 6,000 veh/h 상당)
- FD 유도 실제값 = `segment_flow_veh_h(ρ_crit, V(ρ_crit), lanes)·T_c_h` = **196.1 veh/구간**
- 내가 넣은 값 = `segment_flow_veh_h(...)` = **3,922 veh/h** → **20배 과대**
죽은 분기라 발화 안 했으나, `FAR_FF=1`을 켜는 순간 far가 13배 축소된다. **사본에서 수정.**

## ③의 지위
**결과는 유효하다**(평균 +4.78%, 최악 −4.34%, 8승2패 — 재현 검증 진행 중).
코드도 맞다. **틀린 것은 내 설명뿐.**

## 원고 서술 (교체 필수)
- ✗ 폐기: "terminal의 배수율 상수 `g_fw`가 차선폐색을 못 봐서 고쳤다"
- ✓ 채택: **"terminal의 ramp 합류-후 통과시간이 자유류 속도를 가정해, 과포화·사고 시
  하류 지체를 못 봤다. METANET FD의 V(ρ)로 대체(새 상수 0)."**
- 작동 범위: **ramp 큐가 존재하는 셀에서만** 발화(q=0이면 항 자체가 스킵). skew 무영향.

## 남은 숙제
- `leader_mfd_far_freeflow_offset`이 **필드 없이 env로만 켜지는 죽은 분기**로 방치돼 있다.
  본선 far는 `else` 분기(`n_main²·tc_h/(2·g_fw)`, g_fw=300 상수)가 계속 쓰인다 —
  **본선은 여전히 폐색·과포화를 못 본다.** 이건 아직 안 고쳐진 진짜 결함.
- OBSERVED-Gu(사본 `observed-gu` 브랜치)도 같은 단위 함정 — `g_u = sink`(veh/구간)이지
  `sink/tc_h`(veh/h)가 아니다. 수정 후 진행.
