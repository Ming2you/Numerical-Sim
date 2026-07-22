# Final Paper Analysis Scripts

This folder contains reproducible analysis and plotting utilities for the final
five-scenario traffic-management comparison. It intentionally contains code and
analysis protocol only; generated simulation data and figures are written under
the workspace-level `outputs/` directory and should not be committed.

## Frozen Experiment Frame

- Network: final 8-segment freeway topology.
- Main paper scenarios:
  - `sweet_155_w`
  - `sweet_170_w`
  - `sweet_190_w`
  - `sweet_170_skew15_w`
  - `sweet_170_incident_w`
- Stress/design-only scenario:
  - `sweet_200_w`
- Controllers:
  - `NO-CONTROL`
  - `WU-CD-F`
  - `WU-FAITHFUL-FOLLOWER`
  - `P-STACK-WU-FAITHFUL-APJOINT-FINAL`
  - `P-CENT-SLSQP`
- Scoring:
  - total horizon `T = 10800 s`
  - analysis window `[3600, 10800] s`
  - no-control warmup `WARMUP_NC_STEPS = 20`

## Scripts

- `run_final_5x5_matrix.py`
  - Runs the final scenario-controller matrix.
  - Supports `--scenarios`, `--controllers`, `--output`, `--max-workers`, and
    `--skip-existing`.
- `extract_and_plot_final_analysis.py`
  - Aggregates windowed macro metrics, mechanism/event summaries, price-channel
    audits, and paper-style single-plot figures.
- `make_design_preview_figures.py`
  - Produces a smaller design preview set from currently available runs.
- `make_design_gallery_figures.py`
  - Produces a broad one-metric-per-file figure gallery for manual figure
    selection.
- `make_topology_heatmap_preview.py`
  - Draws network-topology overlays for VSL, ramp metering, metering prices, and
    green-price node diagnostics. These are intended to replace matrix-style
    heatmaps in the main mechanism figures.

## Intended Figure Logic

1. Use macro bar/frontier plots to establish performance and compute feasibility.
2. Use cumulative TTT and flow/density time series to show when congestion is
   prevented rather than merely delayed.
3. Use topology overlays for spatial mechanisms:
   - VSL commands on the two 8-segment freeway links.
   - Ramp metering and metering prices on ramp arrows.
   - Green/offset prices on urban nodes or node-to-node links.
4. Keep matrix heatmaps as diagnostics or appendix material unless the topology
   overlay hides important timing detail.
5. Rebuild final paper figures after `sweet_190_w` and all `P-CENT-SLSQP` runs
   complete.

## Example Commands

```powershell
python .\work\final_analysis\run_final_5x5_matrix.py --output ..\outputs\final_5x5_10800 --max-workers 20 --skip-existing
python .\work\final_analysis\extract_and_plot_final_analysis.py --repo-root . --output ..\outputs\final_analysis_extract_5x5_10800
python .\work\final_analysis\make_design_gallery_figures.py
python .\work\final_analysis\make_topology_heatmap_preview.py
```
