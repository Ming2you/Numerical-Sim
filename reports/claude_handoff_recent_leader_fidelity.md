# Claude Handoff: Recent Leader / P-Stack Fidelity Work

Date: 2026-06-21

This note summarizes the recent Codex-side work so Claude can resume without
reconstructing the chat history.

## Repository / Branch State

- Active repo used by Codex: `C:\Users\alsrj\Desktop\Numerical-Sim`
- Latest pushed commit before this handoff: `65323d9 Add continuous leader search safeguards`
- Current uncommitted tracked change:
  - `reports/codex_run_report.md`
- Current untracked local diagnostic file:
  - `_diag_fidelity.py`

## Recent Implementation Context

The recent work focused on why `PROPOSED-STACKELBERG` can perform worse than
`PROPOSED-FOLLOWERS-ONLY` even though the leader is intended to minimize global
TTT/TTS.

Before the fidelity probe, the code had already been updated with continuous
leader search safeguards:

- `leader_search_mode: continuous | grid`
- continuous leader search enabled by default
- hard feasibility pre-checks
- cheap proxy prefiltering and top-K full evaluation
- incumbent-based early termination in candidate evaluation
- thread-based leader outer-loop parallel evaluation
- sensitivity/proxy-inspired local directions
- fallback/cache support for expensive follower response evaluation

The latest pushed commit containing those changes is:

```text
65323d9 Add continuous leader search safeguards
```

## Boundary Queue Hypothesis Status

The user's boundary-queue hypothesis was set aside for now.

The more important question became:

> Does `leader_follower_ttt_base` / `follower_ttt_base` match actual plant TTT/TTS?

In other words, before changing cost terms or constraints again, we checked
whether the leader's selected-action objective is faithful to what the simulator
actually realizes.

## Fidelity Probe Performed

Two checks were performed.

### 1. Existing 1800 s Peak P-Stack Output

Input output folder:

```text
outputs/continuous_leader_peak_1800_pfo_pstack_evals5_20260621/runs/peak_demand/PROPOSED-STACKELBERG
```

Files used:

- `decision_diagnostics.csv`
- `progress_summary.csv`

Comparison:

- `leader_follower_ttt_base`
- actual plant `step_total_ttt`
- actual plant 3-step rolling TTT

Key result:

| Comparison | Rows | Correlation | Mean ratio | Mean abs error |
|---|---:|---:|---:|---:|
| `leader_follower_ttt_base` vs same-step plant TTT | 10 | 0.9995 | 3.419 | n/a |
| `leader_follower_ttt_base` vs complete 3-step rolling plant TTT | 8 | 0.999999 | 1.002 | 0.272 veh*h |

Interpretation:

- Same-step TTT is not the correct scale because `leader_follower_ttt_base` is
  an MPC-horizon value.
- When compared against a complete 3-step rolling plant TTT, it is almost 1:1.

### 2. Current-Code 900 s Peak Smoke Probe

A temporary runner was created outside the repo:

```text
C:\tmp\fidelity_probe_current.py
```

Command:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" C:\tmp\fidelity_probe_current.py `
  --scenario peak_demand `
  --seconds 900 `
  --max-evals 1 `
  --prefilter-samples 5 `
  --prefilter-top-k 1 `
  --output-dir outputs\fidelity_probe_current_peak_900_evals1_20260621
```

Output:

```text
outputs/fidelity_probe_current_peak_900_evals1_20260621
```

Files:

- `steps.csv`
- `summary.txt`

Key result:

| Comparison | Rows | Correlation | Mean ratio | Mean abs error |
|---|---:|---:|---:|---:|
| `leader_follower_ttt_base` vs same-step plant TTT | 5 | 0.9906 | 3.503 | n/a |
| `leader_follower_ttt_base` vs complete 3-step rolling plant TTT | 3 | 0.999891 | 1.007 | 0.617 veh*h |

Step-level current-code smoke values:

| Step | `pred_base` | Actual step TTT | `N_P_star` | `N_UF_star` |
|---:|---:|---:|---:|---:|
| 0 | 80.536556 | 19.990947 | 0.0 | 6000.0 |
| 1 | 95.434135 | 27.710584 | 0.0 | 6000.0 |
| 2 | 106.981793 | 31.846385 | 0.0 | 6000.0 |
| 3 | 118.174699 | 35.512102 | 0.0 | 6000.0 |
| 4 | 131.333893 | 39.126707 | 0.0 | 6000.0 |

Complete 3-step rolling comparison from current-code smoke:

| Start step | `pred_base` | Actual 3-step rolling TTT |
|---:|---:|---:|
| 0 | 80.536556 | 79.547916 |
| 1 | 95.434135 | 95.069071 |
| 2 | 106.981793 | 106.485194 |

## Diagnosis So Far

Selected-action fidelity appears good.

That means the current evidence does **not** support:

- "P-Stack is bad because `follower_ttt_base` omits a large chunk of realized
  plant TTT."
- "Boundary queue accounting alone explains the selected P-Stack behavior."

The leader's selected `leader_follower_ttt_base` is basically an MPC-horizon
TTT/TTS value. It should not be compared directly to one-step TTT without
accounting for the 3-step horizon.

## Remaining Likely Causes

The remaining issue is probably not selected-action accounting fidelity.

More likely causes:

1. Candidate-level ranking mismatch:
   - The selected candidate's predicted TTT matches its realized rollout, but
     we have not yet verified whether the leader ranks alternative candidates
     the same way as actual counterfactual rollouts from the same state.

2. Finite-horizon effect:
   - A candidate can improve the short MPC horizon while worsening longer-term
     throughput/storage/balance.

3. Leader feasible-set / target issue:
   - The leader may not be exploring the same effective control region as PFO,
     especially after translating `(N_P_star, N_UF_star)` into follower feasible
     sets.

4. Penalty/throughput tradeoff:
   - The current leader objective includes TTT-compatible terms plus MFD/storage
     style penalties.
   - A candidate may increase throughput and terminal clearance while slightly
     increasing raw TTT.

5. Continuous-search budget:
   - Current default is still expensive:
     - `leader_continuous_max_evals = 25`
     - `leader_continuous_prefilter_samples = 31`
     - `leader_continuous_prefilter_top_k = 7`
   - Even the reduced current-code smoke with `max_evals=1` took about 182 s
     for 900 s simulated time.

## Important Runtime Observation

The fidelity probe also showed that current P-Stack evaluation remains costly.

Current-code 900 s smoke with only one leader full evaluation per step:

```text
runtime_sec = 182.361
steps = 5
```

Per-step decision times:

| Step | Decision sec |
|---:|---:|
| 0 | 53.508 |
| 1 | 33.704 |
| 2 | 33.199 |
| 3 | 33.534 |
| 4 | 28.155 |

This suggests follower response / distributed grid evaluation remains the main
cost driver, not just the number of leader candidates.

## Report Updated

Codex appended these results to:

```text
reports/codex_run_report.md
```

Section title:

```text
2026-06-21 - Leader follower-TTT fidelity probe
```

## Recommended Next Diagnostic

Do **not** immediately add another boundary queue penalty or MFD penalty.

The next useful probe is counterfactual candidate-level fidelity:

1. Pick one fixed initial state from `peak_demand`.
2. Generate several leader candidates `(N_P_star, N_UF_star)`.
3. For each candidate:
   - compute leader objective / `leader_follower_ttt_base`
   - apply the resulting follower response to a copied simulator
   - run an actual 3-step rollout from the same state
   - record actual plant rolling TTT
4. Compare candidate ranking:
   - objective rank
   - actual rollout rank

If candidate rankings disagree, the bug is in candidate evaluation / response
translation / counterfactual rollout fidelity.

If candidate rankings agree, then P-Stack's worse long-run performance is more
likely a finite-horizon or objective-design issue rather than an implementation
bug in selected-action TTT accounting.

