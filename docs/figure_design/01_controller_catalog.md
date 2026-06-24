# Controller Catalog

This file is the source of truth for controller labels and authority in result
figures. Update this file when controller definitions change.

## Active Controller Set

| Controller ID | Paper label | Short label | Role in comparison |
|---|---|---|---|
| `NO-CONTROL` | No control | NC | Fixed-time signal, no ramp metering, no VSL |
| `WU-CD-F` | WU-CD-F | WU | Wu-authority-matched distributed controller |
| `PROPOSED-FOLLOWERS-ONLY` | Proposed followers only | PFO | Proposed distributed follower package without leader |
| `PROPOSED-STACKELBERG` | Proposed Stackelberg | P-Stack | Full proposed leader-follower controller |
| `PROPOSED-CENTRALIZED` | Proposed centralized | Cent. | Full-information centralized reference |

## Control Authority Matrix

| Controller | Leader target | Allocation | Green time | Offset | Ramp metering | VSL |
|---|---:|---:|---:|---:|---:|---:|
| `NO-CONTROL` | No | No | Fixed | Fixed | No | No |
| `WU-CD-F` | No | No | Yes | No | No | Yes |
| `PROPOSED-FOLLOWERS-ONLY` | No | No | Yes | Yes | Yes | Yes |
| `PROPOSED-STACKELBERG` | Yes | Config-dependent | Yes | Yes | Yes | Yes |
| `PROPOSED-CENTRALIZED` | No separate leader | Joint centralized | Yes | Yes | Yes | Yes |

Notes:

- `WU-CD-F` should be interpreted as the repository's Wu-authority-matched
  distributed benchmark, not as an exact reproduction of every detail in the Wu
  paper.
- `PROPOSED-FOLLOWERS-ONLY` is the proposed distributed follower package. It uses
  local TTS-compatible objective evaluation and Nash-like coordination, but has
  no macroscopic leader.
- `PROPOSED-STACKELBERG` adds leader decisions for macroscopic targets such as
  `N_P_star` and `N_UF_star`. Its allocation mode can be `direct`,
  `simplified`, or `pso`; plots must report the mode used in a caption or run
  metadata table.
- `PROPOSED-CENTRALIZED` is a reference under the same physical plant and
  authority. It is not a theoretical global optimum unless the solver and budget
  are explicitly proven sufficient.

## Figure Interpretation Rules

Use these comparisons in the paper:

| Comparison | Question |
|---|---|
| `WU-CD-F` vs `PFO` | What is gained by adding proposed follower authority: RM, offset, and local TTS-compatible search? |
| `PFO` vs `P-Stack` | What is gained by adding the leader target layer? |
| `P-Stack` vs `Centralized` | What performance-computation trade-off remains relative to centralized control? |
| `No control` vs all active controllers | Does control improve the plant under identical demand and accounting? |

Avoid claiming that `P-Stack` is always better than `PFO`. If `P-Stack` selects
the PFO fallback or matches PFO, treat that as a diagnostic result about leader
candidate quality, objective fidelity, or computation budget.

## Required Caption Metadata

Every figure comparing controllers should state:

- scenario set or scenario tags included;
- simulation horizon;
- controller set;
- whether `PROPOSED-STACKELBERG` fallback guard was enabled;
- Stackelberg allocation mode if `P-Stack` is shown;
- whether relaxed/quantized controls were enabled.
