# 가격 ablation + corr — 수정 전 baseline 스냅샷 (2026-07-23)

**주의**: VSL 미활성 문제로 컨트롤러 수정 중 → 수정 후 marginal price on/off 재실행 예정.
아래는 **수정 전 b13 flagship** 기준 스냅샷.

## 최종 표 (TABLE 4 + corr + |Δ|)

| Scenario | Proposed (veh·h) | Pricing removed (veh·h) | ΔTTT | Contribution (%) | Metering price↔lever corr (n) | Metering \|Δ\|/step (veh/h) |
|---|---:|---:|---:|---:|---:|---:|
| Low | 2990 | 2974 | −16 | −0.5 | −0.27 (n=53) | 135 |
| Medium | 3810 | 4146 | +337 | +8.8 | −0.16 (n=24) | 29 |
| Medium-skew | 3990 | 4156 | +166 | +4.2 | −0.34 (n=32) | 58 |
| Medium-incident | 5546 | 5547 | +1 | +0.0 | −0.44 (n=40) | 470 |
| High | 5735 | 6303 | +568 | +9.9 | −0.31 (n=42) | 269* |

\*190은 cf 반사실(PRICE_CF) 솔버 상태누수로 오염된 궤적 — corr·|Δ| 참고만. Contribution은 base_190(clean) 사용.

## corr 해석 (중요)

- **corr은 metering에만 의미** 있음. green/offset/VSL은 peak에 거의/전혀 안 움직여 표본이 없음.
  - green: n=0~18, |Δ|=6s(양자 1칸). Low는 peak 내내 n=0.
  - offset: peak 전구간 0 (회복기에만 작동).
  - VSL: 100↔115 bang-bang(주로 바닥 100), 단 **PRICE_CF hook이 VSL/offset 반사실을 안 찍음** → 인과 corr 계산 불가.
- metering corr −0.16~−0.44는 "제대로 계산됐으나 약함" — 이유는 **작은 n + 반사실이 4채널 전부 off**(metering만 격리 안 됨). 컬럼 오염 버그 아님(검증됨).

## green이 약한 이유 (sweep으로 확정)

- green을 ±40s 넓게 쓸어 TTT_global(green) 곡선 확인 → **볼록 U자, 바닥 넓고 평평, ref가 바닥에 위치**.
- green 완전최적화해도 이득 0.1~0.4%(surrogate). 넓은 probe로도 숨은 이득 없음 = **물리적 low leverage**.
- scale-adjusted marginal: metering 1.54 > green 0.63 > VSL 0.21 > offset 0.03.

## 다음에 할 것 (컨트롤러 수정 후)

1. VSL 활성화되는 새 컨트롤러로 marginal price on/off 재실행 (5셀).
2. PRICE_CF hook에 **VSL·offset 반사실 로깅 추가** → 4채널 corr 표 완성.
3. cf_190 솔버 상태누수 수정(반사실 솔브 전 clone/snapshot) → 190 per-step clean.
