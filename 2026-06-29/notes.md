# 2026-06-29 — TASK #3 N_P dual decomposition: λ subgradient → bisection

## What changed
`src/controllers/wu_faithful_follower.py` only.

Replaced the fragile gain-normalized subgradient λ update with a **bisection on λ**.

- Removed the per-Jacobi-sweep subgradient step (`λ ← max(0, λ + dual_step_c/G·(Σnin−N_P))`).
  Root cause of the old bug: `_measure_dual_gain` measured gain ≈ 0 because its probe
  `lambda_hi` sat far below the response threshold, so the update was gated off
  (`dual_gain > 1e-12` false) and λ stayed pinned at 0 → N_P never tracked.
- Added `_bisect_lambda_for_np(...)`: runs **after** the Jacobi coupling loop converges,
  at the converged coupling/snapshot. Exploits that `Σnin(λ)` is monotone non-increasing &
  piecewise-constant:
  1. `Σnin(0)` — if `N_P_star ≥ Σnin(0)` → slack → λ*=0 (no needless suppression).
  2. grow `λ_max` geometrically (1,10,…) until the target is bracketed OR `Σnin` stops
     decreasing (floor). If `N_P_star ≤ Σnin(λ_max)` → infeasible → λ*=λ_max (track to floor).
  3. else bisect `[0, λ_max]` ~18 iters; commit the endpoint whose realized `Σnin` is
     nearest the target (piecewise-constant ⇒ converge on the λ bracket, not an exact Σnin hit).
- During Jacobi consensus, λ is **frozen** at the warm-start value (snapshot/coupling settle
  first). After bisection, a **final urban sweep at λ\*** commits the greens and records the
  realized `Σnin`. λ\* persisted as warm-start (`self._lambda_P`).
- `_measure_dual_gain` left **dormant** (unused, not deleted). `dual_step_c` attr now unused
  (harmless, left in place).
- PFO path (`leader=None` ⇒ `dual_active=False`) is entirely skipped — untouched.

## Validation (decisive)

### 1. N_P tracking — warmed sweet_128 congested state, single-step λ sweep
`2026-06-29/_validate_np_tracking.py`. Σnin(λ) at converged coupling: floor ~1055, Σnin(0)=1550.

| N_P_star | realized Σnin | λ*     | note                       |
|---------:|--------------:|-------:|----------------------------|
| 1600.0   | 1550.5        | 0.0000 | baseline (slack region)    |
| 1385.0   | 1235.5        | 0.0191 | follows target down        |
| 1300.0   | 1235.5        | 0.0191 | follows target down        |
| 1200.0   | 1203.0        | 0.0245 | follows target down        |
| 1108.0   | 1105.1        | 0.0720 | follows target down        |
| 1050.0   | 1054.7        | 10.000 | clamped @ floor (~1055)    |
|  900.0   | 1054.7        | 10.000 | clamped @ floor (~1055)    |

Σnin now FOLLOWS the target down and CLAMPS at the floor. Before the fix every row was flat
at the slack value (λ stuck at 0). This is the original "followers don't track the leader
target" problem, now solved.

### 2. PFO no-regression (closed-loop full T=3600)
- sweet_128 = **+56.63%** (1339.914) — exact baseline match.
- sweet_170 = +39.61% (3625.024)
- sweet_190 = +32.92% (4807.076)
PFO evals/step mean 547.5, no bisection cost (dual block skipped).

### 3. Cost
Dual-active step (one congested state): ~4.0 s, evals ≈ 2260 (≈15 bisection sweeps ×5 agents
+ final commit sweep + Jacobi). Slack steps are cheap (~790 evals). Solve stays local.

## Weak spots for reviewer
- Floor/levels here (~1055, 1235, …) come from the **converged-coupling** snapshot and differ
  from the original raw-warmed-state λ-sweep diagnosis (1108/1385). Same mechanism, different
  snapshot — not a discrepancy, but worth noting the numbers are snapshot-dependent.
- Piecewise-constant Σnin ⇒ targets in a gap (e.g. 1385) land on the nearest achievable level
  (1235), not the exact target. Inherent to discrete greens; bisection converges on λ, not Σnin.
- N_P tracking validated only at a single warmed state (single-step), not in closed loop with a
  real leader driving N_P_star over the horizon. Closed-loop leader+follower TTT impact unmeasured
  here (out of scope; this task was the tracking mechanism).
- `dual_step_c` / `_measure_dual_gain` left as dead-but-dormant code (not removed to keep the
  diff surgical; flag if you want them gone).

## TODO
- Wire a real leader and measure closed-loop TTT with N_P tracking active.
- Decide whether to delete the dormant `_measure_dual_gain` / `dual_step_c`.
