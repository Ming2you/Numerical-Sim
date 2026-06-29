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
10. For slide figures, remove or shorten titles when they collide with legends;
    put the interpretation in slide text instead.
11. When a network-effect summary includes no-control, plot absolute completed
    vehicles and absolute terminal vehicles rather than gains only.
12. If demand is shown on a topology map, place ramp-bound demand near the
    boundary/intersection approach, not directly on the ramp link.

Primary figure package:
- Scenario demand map: directional urban boundary, freeway entry, and ramp-bound
  demand.
- Macro performance: total/urban/freeway TTT, ATT or TTT/completed proxy,
  completed vehicles, terminal vehicles.
- Congestion transfer: on-ramp, off-ramp, boundary queue exposure and spillback.
- Leader feasibility: N_P_star, N_UF_star, actual response, candidate objectives,
  fallback selection.
- Game coupling: Nash convergence, coupling sensitivity, predicted objective vs
  realized plant TTT.
- Micro behavior: RM/VSL/green/offset effect chains that connect control inputs
  to queues, freeway density/speed, departures, TTT saved, completed vehicles, or
  terminal vehicles.
- Operating-point diagnostics: FD/MFD plots, but treat them as preliminary when
  the numerical simulator does not form clean empirical loops.
- Computation cost: runtime per step with the control-interval reference line,
  candidate evaluations, budget sensitivity.

Current effect-oriented output directory to inspect when available:

reports/figures/effect_oriented_2026_06_23/

Important current figures:

- 00_scenario_demand/Scenario_topology_directional_demand
- 01_time_aligned_effects/EffectChain_RM_queue_TTT_*
- 01_time_aligned_effects/EffectChain_signal_service_queue_*
- 01_time_aligned_effects/EffectChain_VSL_RM_speed_density_incident_or_capacity_drop
- 02_operating_point_shift/FD_operating_point_shift_*
- 02_operating_point_shift/Urban_MFD_operating_point_shift_*
- 04_network_effect_summary/Network_effect_summary
- 05_computation_time/Computation_time_per_step

Interpretation discipline:

- Do not write "control was activated" as the main claim. Explain what state or
  outcome changed after activation.
- To argue that TTT improvement is not transferred to one subsystem, cite both
  urban/freeway TTT decomposition and completed/terminal outcome bars.
- To argue that RM is beneficial, show metering/release, ramp queue, freeway
  density/speed, and cumulative TTT or terminal response on the same time axis.
- To argue that signal or offset matters, show green/offset change together with
  urban departures and movement queue response.
- To discuss FD/MFD, state the numerical-simulation caveat and avoid strong
  empirical FD/MFD claims unless the plant has been separately validated.
```
