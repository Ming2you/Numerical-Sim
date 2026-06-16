# Split Codex Implementation Spec

This folder splits the implementation specification by top-level section so an LLM/coding agent can work with a smaller, focused context.

`../codex_implementation_spec.md` is the master index. The files in this folder are the detailed source of truth.

## File map

- `00_purpose.md`
- `01_control_concept.md`
- `02_implementation_scope.md`
- `03_traffic_models.md`
- `04_controller.md`
- `05_simulation_pipeline.md`
- `06_metrics.md`
- `07_auto_diagnosis.md`
- `08_cli.md`
- `09_configuration_requirements.md`
- `10_tests.md`
- `11_reporting.md`
- `12_coding_style.md`
- `13_implementation_order.md`
- `14_definition_of_done.md`
- `15_caveats.md`
- `16_six_controller_comparison.md`
- `17_relaxed_quantized_fast_mode.md`

## Recommended use

1. Give `00_purpose.md`, `01_control_concept.md`, and the target section file to the coding agent.
2. For traffic-model implementation, give `03_traffic_models.md` plus the relevant controller file only.
3. For tests, give `10_tests.md` plus the module-specific section being tested.
4. Keep `15_caveats.md` attached to every coding task.
5. For benchmark implementation and post-analysis, also provide
   `16_six_controller_comparison.md` and `../literature_grounded_post_analysis_plan.md`.
6. For computation-cost reduction of the four-controller benchmark, also provide
   `17_relaxed_quantized_fast_mode.md`.

Do not give the entire full spec to the coding agent unless the task requires cross-section integration.
