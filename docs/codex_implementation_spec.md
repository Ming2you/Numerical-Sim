# Codex Implementation Spec

This file is the master index only.

Do not implement from this file alone. Before modifying any source code, read the relevant files under `./spec/`.

The detailed specification files in `./spec/` are the source of truth. If this file and any file under `./spec/` conflict, the file under `./spec/` takes precedence.

## Required reading by task

- For `models/metanet.py`, `models/urban_queue_model.py`, and `simulation/simulator.py`, read:
  - `./spec/03_traffic_models.md`
  - `./spec/12_coding_style.md`
  - `./spec/15_caveats.md`

- For `controllers/*.py`, read:
  - `./spec/04_controller.md`
  - `./spec/03_traffic_models.md`
  - `./spec/12_coding_style.md`
  - `./spec/15_caveats.md`

- For `evaluation/*.py`, read:
  - `./spec/06_metrics.md`
  - `./spec/11_reporting.md`
  - `./spec/12_coding_style.md`

- For `experiments/*.py`, read:
  - `./spec/05_simulation_pipeline.md`
  - `./spec/07_auto_diagnosis.md`
  - `./spec/08_cli.md`
  - `./spec/13_implementation_order.md`

- For `tests/*.py`, read:
  - `./spec/10_tests.md`
  - the corresponding implementation spec for the module being tested.

## Implementation rule

When working on a file, first state which spec files were used. Do not implement unrelated modules. Do not simplify mathematical equations unless the relevant spec explicitly allows it.