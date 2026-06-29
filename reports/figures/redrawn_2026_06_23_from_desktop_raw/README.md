# Redrawn 2026-06-23 Figures From Desktop Raw Outputs

Generated on 2026-06-25 by:

```powershell
& "C:\Users\alsrj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -B "C:\Users\alsrj\Documents\Numerical Simulation\2026-06-25\diag_scripts\redraw_2026_06_23_figures_from_desktop_raw.py"
```

Inputs:

- `C:\Users\alsrj\Desktop\Numerical-Sim\outputs\analysis_matrix_3600`
- `C:\Users\alsrj\Desktop\Numerical-Sim\outputs\analysis_matrix_3600_extra`

Output:

- 17 regenerated PNG files, `fig01_...` through `fig17_...`.

Verification against the tracked 6/23 figures in `reports/figures`:

- `fig04` through `fig17` are byte-identical to the tracked 6/23 figures.
- `fig01` through `fig03` differ because the current repository no longer contains
  the exact 6/23 scenario definitions for `heavy_demand_140`, `heavy_demand_150`,
  `skew_peak`, and `skew_heavy`; the redraw script injects local legacy scenario
  definitions to make the demand-profile figures reproducible enough for
  inspection.

Therefore, use `fig04` through `fig17` here as fully verified redraws from raw CSV.
For the exact original demand-profile figures, use the tracked 6/23 originals:

- `reports/figures/fig01_demand_profiles.png`
- `reports/figures/fig02_demand_composition.png`
- `reports/figures/fig03_skew_demand.png`
