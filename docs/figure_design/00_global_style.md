# Global Figure Style

## Matplotlib Defaults

Use a publication-oriented style for every figure.

```python
import matplotlib as mpl

mpl.rcParams["font.family"] = "Times New Roman"
mpl.rcParams["mathtext.fontset"] = "stix"
mpl.rcParams["axes.unicode_minus"] = False
mpl.rcParams["font.size"] = 10
mpl.rcParams["axes.labelsize"] = 10
mpl.rcParams["axes.titlesize"] = 10
mpl.rcParams["xtick.labelsize"] = 9
mpl.rcParams["ytick.labelsize"] = 9
mpl.rcParams["legend.fontsize"] = 9
mpl.rcParams["figure.dpi"] = 300
mpl.rcParams["savefig.dpi"] = 300
mpl.rcParams["savefig.bbox"] = "tight"
```

If `Times New Roman` is unavailable, report the font fallback warning in the run
log. Do not silently change fonts between figures.

## Controller Colors

Use the same colors across every chapter.

| Controller | Plot label | Color |
|---|---|---|
| `NO-CONTROL` | `No control` | `#4D4D4D` |
| `WU-CD-F` | `WU-CD-F` | `#1F77B4` |
| `PROPOSED-FOLLOWERS-ONLY` | `PFO` | `#2CA02C` |
| `PROPOSED-STACKELBERG` | `P-Stack` | `#D62728` |
| `PROPOSED-CENTRALIZED` | `Centralized` | `#9467BD` |

When a figure has too many scenario markers, use color for controller and marker
shape for scenario family or tag.

## Unit Conventions

| Quantity | Preferred unit |
|---|---|
| Total TTT or TTS | veh-h |
| Delay | veh-h and sec/veh when possible |
| Throughput | veh or veh/h, clearly labeled |
| Queue length | veh |
| Density | veh/km/lane |
| Flow or metering rate | veh/h |
| VSL | km/h |
| Green time and offset | s |
| Runtime | s/control step |

Do not mix cumulative and interval values on the same axis unless the second
series is placed in a separate panel.

## Output Folders

Recommended figure output root:

```text
reports/figures/
  00_style/
  01_macro_performance/
  02_congestion_transfer/
  03_leader_feasibility/
  04_game_coupling/
  05_micro_controls/
    ramp_metering/
    vsl/
    green_time/
    offset/
  06_computation_cost/
  appendix/
```

Save every final figure as both PNG and PDF.

```python
fig.savefig("reports/figures/01_macro_performance/Fig1_total_ttt.png")
fig.savefig("reports/figures/01_macro_performance/Fig1_total_ttt.pdf")
```

## Plot Hygiene

- Use one metric per y-axis unless the figure is explicitly a diagnostic overlay.
- Keep legends outside dense panels when possible.
- Add threshold lines only when the threshold is used in the model or acceptance
  interpretation.
- Shade incident, surge, and constraint-binding windows only when the scenario
  catalog or diagnostics expose those windows.
- Prefer grouped bars for aggregate cross-scenario summaries.
- Prefer aligned time-series panels for mechanism analysis.
- Prefer heatmaps or contour plots for space-time and candidate-response figures.
