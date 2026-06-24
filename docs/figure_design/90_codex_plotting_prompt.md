# Codex Plotting Prompt

Use this prompt when asking Codex to generate figures from experiment outputs.

```text
You are generating publication-quality figures for a transportation engineering
paper about integrated urban-freeway control.

Read these figure-design files first:
- docs/figure_design/00_global_style.md
- docs/figure_design/01_controller_catalog.md
- docs/figure_design/02_scenario_catalog.md
- docs/figure_design/03_data_schema.md

Controller definitions:
- Use controller labels and colors from docs/figure_design/01_controller_catalog.md.
- Do not invent controller authority.
- If PROPOSED-STACKELBERG is shown, report fallback setting, allocation mode, and
  leader search budget when available.

Scenario handling:
- Read active scenarios from the experiment outputs and scenario catalog.
- Do not assume exactly five or six scenarios.
- Use scenario tags to decide which event windows and annotations are relevant.
- Skip tag-specific figures when no active scenario has that tag, and report the
  skip in the log.

Figure requirements:
1. Use Times New Roman and the global style settings.
2. Save every final figure as PNG and PDF under reports/figures/.
3. Use one metric per y-axis unless the figure is explicitly a diagnostic overlay.
4. Add units to every axis label.
5. Keep controller colors consistent across figures.
6. Add threshold lines only when the threshold exists in config or diagnostics.
7. Shade incident, surge, spillback, and binding windows only when available.
8. Include source output directory and simulation horizon in the figure metadata
   or companion log.
9. Do not claim controller acceptance from figures alone.

Primary figure package:
- Macro performance: total/urban/freeway TTT, delay, ATT, throughput, terminal
  vehicles.
- Congestion transfer: on-ramp, off-ramp, boundary queue exposure and spillback.
- Leader feasibility: N_P_star, N_UF_star, actual response, candidate objectives,
  fallback selection.
- Game coupling: Nash convergence, coupling sensitivity, predicted objective vs
  realized plant TTT.
- Micro behavior: RM, VSL, green time, offset.
- Computation cost: runtime per step, candidate evaluations, budget sensitivity.
```
