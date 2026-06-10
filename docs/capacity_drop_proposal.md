# Capacity Drop 제안 — Wu et al.(2022) Eq.(22) off-ramp spill-back

대상: Codex. 목적: 현재 METANET에 capacity drop이 없어 VSL이 켜질 유인이 없는 문제를,
Wu et al.(2022) 식(22)의 off-ramp spill-back 차로수 감소로 해결한다. **canonical
`docs/spec/03_traffic_models.md`는 Codex가 코드 구현과 함께 한 커밋에서 통합할 것**(여기는
제안/초안). round-6 진단에서 freeway TTT 188→268로 악화·`density_exceedance_duration=23`인데
`vsl_active_steps=0`이었던 게 이 항이 없어서다.

## 왜 필요한가 (한 줄)
relaxation METANET은 단일값 FD라 혼잡 병목도 자유류 용량으로 방류 → VSL이 막을 capacity drop이
없음 → VSL 무의미. 식(22)로 off-ramp가 막히면 **마지막 세그먼트 차로수=용량을 떨어뜨려**
mainline through까지 choke → spill-back 발생 → urban이 off-ramp 비우는 동안 VSL/metering이
상류 inflow를 제한해 TTT 악화를 막는 통합 제어가 성립.

## 03_traffic_models.md에 추가할 절 (3.1.6 다음, 영문 spec 스타일)

```markdown
#### 3.1.7 Off-ramp spill-back capacity drop (lane-number reduction)

Sections 3.1.1–3.1.6 use a constant lane number `lanes[m]`, so the freeway has no
capacity drop and VSL / mainstream metering yields no throughput benefit. To
reproduce the spill-back of a congested off-ramp into the freeway mainline, make
the lane number of the off-ramp's upstream segment a decreasing function of the
off-ramp occupancy, following Wu et al. (2022), Eq. (22).

For an off-ramp `(m,d)` that leaves the last segment `(m, N_m)` of freeway link
`m` toward urban intersection `d`, define:

```text
n[m,d](k)        : number of vehicles on the off-ramp link (m,d)   [veh]
C[m,d]           : storage capacity of the off-ramp link (m,d)     [veh]
lambda_m         : original (free-flow) lane number of (m, N_m)
gamma[m,d], b_cd : shape parameters (calibration)
```

Effective lane number of the last segment:

```text
lambda_eff[m,N_m](k)
    = (lambda_m - 1)
      + exp( -(1 / b_cd) * ( n[m,d](k) / (gamma[m,d] * C[m,d]) ) ** b_cd )    # Wu Eq.(22)
```

Behaviour:

```text
n[m,d] = 0        ->  exp(0) = 1      ->  lambda_eff = lambda_m        (full capacity)
n[m,d] large      ->  exp(.) -> 0     ->  lambda_eff -> lambda_m - 1   (one lane lost)
```

The reduction is smooth and recovers as `n[m,d]` decreases. No separate hysteresis
term is added; the temporal lag is provided by the off-ramp queue dynamics
(`n[m,d]` is cleared by the downstream intersection over several urban steps). For
`lambda_m = 2`, the last-segment capacity is roughly halved at full spill-back.

Use `lambda_eff[m,N_m](k)` in place of the constant `lanes[m]` for segment
`(m, N_m)` in the segment flow (3.1.1) and the density update (3.1.2):

```text
q[m,N_m](k)        = rho[m,N_m](k) * v[m,N_m](k) * lambda_eff[m,N_m](k)
rho[m,N_m](k+1)    = rho[m,N_m](k)
                     + T_f_h / (L[m] * lambda_eff[m,N_m](k))
                       * (q[m,N_m-1](k) - q[m,N_m](k))
```

Because the reduced lane number lowers the capacity of the WHOLE segment (not only
the off-ramp split flow), the mainline through-flow is choked during spill-back.
This is what (a) propagates congestion upstream and (b) gives VSL and ramp metering
a reason to restrict upstream inflow so the reduced-capacity segment does not break
down while the urban controller clears the off-ramp queue `n[m,d]`.

This supersedes the simplified boundary cap of 3.4.2 for the spill-back effect: the
previous form limits only the off-ramp split outflow by available storage, whereas
Eq.(22) reduces the through-capacity of the segment itself.

`lambda_eff[m,N_m](k)` MUST be applied identically in the simulator plant and in
the controller's freeway prediction model; otherwise the follower cannot value VSL
or metering against the capacity drop.

Configuration (explicit):

```yaml
freeway_offramp_capacity_drop:
  enabled: true
  lane_reduction: 1     # lanes lost at full spill-back (lambda_m -> lambda_m - 1)
  gamma: 0.5            # gamma[m,d], occupancy scale (fraction of C at onset)
  b: 2.0               # b_cd, transition sharpness
```

`n[m,d]` and `C[m,d]` reuse the off-ramp storage link of 3.4.2
(`off_ramp_storage_link` / `urban_link_storage_veh`):
`n[m,d] = C[m,d] - available_storage[m,d]`.
```

## 구현 지시 (코드)
- `src/models/metanet.py` `freeway_substep`: 마지막 세그먼트 outflow/density에 상수 `lanes`
  대신 `lambda_eff` 적용. 기존 `offramp_capacity_veh_h`(유출 cap)는 식(22)로 대체.
- `src/models/state.py`/config: `n[m,d] = urban_link_storage_veh[storage_link] - urban_link_storage[storage_link]`.
- **`src/controllers/freeway_follower.py` `_lightweight_transition`에도 동일 `lambda_eff` 반영**
  (예측-plant 일치). 안 하면 follower가 VSL 가치를 못 봄.
- 단위 테스트: `lambda_eff(n=0)=lambda_m`, `n→큰값→lambda_m-1`, full spill-back 시 마지막 세그먼트
  용량 ~50% 감소(lambda_m=2).

## 파라미터
- `gamma=0.5, b=2`는 Wu가 고정값 안 줘서 시작값(calibration 대상). `lane_reduction=1`은 원문대로.
- hysteresis 없음(원문 충실 — 회복 지연은 off-ramp 큐가 비워지는 시간이 대신).

## 검증 (구현 후)
풀 진단 run(peak_demand)에서 **`vsl_active_steps>0`** (VSL 실제 활성) + freeway TTT 악화 감소.
off-ramp spill-back 시 mainline density가 상류로 번지고, VSL이 그걸 완화하는지 시계열 확인.
