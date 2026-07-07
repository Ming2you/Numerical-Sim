# two-branch VSL-FD 예비 결과 (sweet_190 7200s) — ⚠ calibration caveat

VSL-FD(two_branch, Codex a511be0) + rho_crit(VSL) 전파(1a7c17e) plant 위 예비 실행. 같은 머신.

## 결과 (new-FD regime)

| run | total | 비고 |
|---|---:|---|
| PFO new-FD (WuFaithful follower only) | **10013** | floor, freeway TTT 598 |
| legacy new-FD (Stackelberg+DistributedCoordinator) | **9530** | ceiling, urban 8933 / fw 598 |
| ALLPRICE h=3 (9분) | 9689 | gap 회수 +67%, solve 87s |
| ALLPRICE h=5 (15분) | 9841 | +36%, 124s |
| ALLPRICE h=8 (24분) | 9714 | +62%, 176s |
| gap(legacy−PFO) | **483** | |

## ⚠ 왜 예비(신뢰 제한)인가 — nominal capacity 뻥튀기

- two_branch(삼각형) FD의 capacity = v_free·rho_crit = 100·33.5 = **3350 veh/h/lane**.
- 근데 rho_crit=33.5는 **원래 exponential FD용**(거기선 capacity 1961, rho_crit보다 낮은 밀도서 peak).
  삼각형은 rho_crit에서 peak → **1961→3350 (×1.7) 뻥튀기.** **삼각형용 rho_crit 재calibration 미실시**
  (Codex caveat 1). 현실 freeway ~2000~2400/lane이라 3350은 비현실적.
- 결과: **freeway 거의 free-flow(TTT 598 vs 구 FD 1527)** → 포화 완화 → 협조(leader) 가치 붕괴
  (구 FD 격차 ~2200 → new FD 483). **PFO가 좋아 보이는 건 실력이 아니라 문제가 쉬워진 것.**
- **깊이 sweep 비단조(h3>h8>h5)**: 격차 작아 변별력 없음(노이즈 수준). terminal cost 가치는 심한
  포화에서만 나오는데 이 regime은 그게 약함.

## 참고 — Hegyi/METANET

Hegyi et al.(2005) VSL은 **exponential METANET + 속도상한**(V=min(V_e(ρ),(1+α)VSL))으로 **하류 병목
inflow를 동적 제한**(속도로 하는 metering) — capacity 현실값 유지, rho_crit 이동 안 함. two_branch
(rho_crit 이동, capacity 3350)는 Codex의 departure. 삼각형용 rho_crit 재calibration(≈19.6) 또는
Hegyi 방식 복원이 선결.

## 결론

**이 결과는 완만-포화 regime 한정이라 일반화 금지.** 진짜 판정은 (a) 삼각형 rho_crit 재calibration으로
capacity 현실복원 후, 또는 (b) 원래 exponential plant(격차 real·large)에서. 예비 보존용.
