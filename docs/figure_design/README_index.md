# Figure Design Guide Index

This folder reorganizes the single long mixed-network figure guide into
spec-style chapters. The goal is to keep stable plotting requirements separate
from volatile experiment definitions.

## How To Use

Start with these three files:

1. `00_global_style.md`
2. `01_controller_catalog.md`
3. `02_scenario_catalog.md`

Then choose the analysis chapter that matches the figure to generate.

Most future edits should touch only:

- `01_controller_catalog.md` when controller definitions, labels, or authority
  change.
- `02_scenario_catalog.md` when scenarios, demand levels, incident windows, or
  scenario tags change.

The remaining chapters should be scenario-count independent. They should refer
to the active scenario registry and scenario tags instead of hard-coding five or
six named scenarios.

## File Map

| File | Purpose | Expected edit frequency |
|---|---|---|
| `00_global_style.md` | Publication style, colors, labels, units, output folders | Low |
| `01_controller_catalog.md` | Controller labels, authority, interpretation | High |
| `02_scenario_catalog.md` | Active scenario registry and flexible tags | High |
| `03_data_schema.md` | Common plotting data frames and source files | Medium |
| `04_main_text_figure_set.md` | Recommended main-text figure package | Medium |
| `10_macro_performance.md` | TTT, delay, throughput, terminal-state figures | Low |
| `20_congestion_transfer.md` | On-ramp, off-ramp, boundary spillback figures | Low |
| `30_leader_feasibility.md` | Stackelberg leader target and feasibility figures | Medium |
| `40_game_coupling.md` | Nash, coupling, predicted-vs-realized diagnostics | Medium |
| `50_micro_control_behavior.md` | RM, VSL, green, offset mechanism figures | Low |
| `60_computation_cost.md` | Runtime, candidate budget, scalability figures | Medium |
| `70_appendix_figures.md` | Appendix figure inventory | Low |
| `90_codex_plotting_prompt.md` | Reusable prompt for figure generation | Medium |

## Maintenance Rule

Do not duplicate the active scenario list throughout the figure guide. If a
chapter needs scenario-specific logic, use scenario tags such as `baseline`,
`medium`, `peak`, `incident`, `surge`, `spatial-skew`, `spillback-risk`, or
`capacity-drop-risk`.

Do not duplicate controller authority throughout the figure guide. Use the
controller catalog as the source of truth.

## Source Note

This folder is a refactor of the external draft:

`C:\Users\alsrj\Downloads\mixed_network_figure_design_guide.md`

The figure ideas were preserved, but the controller definitions and scenario
handling were rewritten for this repository's current MPC/Stackelberg controller
comparison workflow.
