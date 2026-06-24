# Main Text Figure Set

This chapter defines a compact paper-ready figure package. It should not need
editing when the active scenario count changes.

## Recommended Main Figures

| Figure | Chapter | Purpose |
|---|---|---|
| Fig. 1 | `10_macro_performance.md` | Cross-scenario performance: total, urban, freeway TTT plus delay or ATT |
| Fig. 2 | `20_congestion_transfer.md` | On-ramp, off-ramp, and boundary congestion transfer |
| Fig. 3 | `30_leader_feasibility.md` | Leader target, actual follower response, feasibility, fallback selection |
| Fig. 4 | `40_game_coupling.md` | Nash/coupling diagnostics and predicted-vs-realized fidelity |
| Fig. 5 | `50_micro_control_behavior.md` | Mechanism panel for RM, VSL, green time, and offset |
| Fig. 6 | `60_computation_cost.md` | Runtime and candidate-evaluation cost |

## Minimal Page-Limited Set

If the paper can only include four result figures, use:

1. Cross-scenario macro performance.
2. Representative congestion-transfer mechanism.
3. PFO vs P-Stack leader feasibility and fallback diagnostics.
4. Computation-cost trade-off against WU and centralized reference.

## Main Claims Mapped To Figures

| Claim | Required figure evidence |
|---|---|
| Active controllers improve network performance | Total TTT, delay, throughput, terminal vehicles |
| Improvements are not just freeway-protection artifacts | Urban TTT, boundary queues, ramp/off-ramp queue exposure |
| PFO provides useful distributed local response | PFO vs WU and no-control macro and micro figures |
| P-Stack adds a meaningful leader layer only when it selects non-fallback targets | PFO vs P-Stack target/fallback/candidate diagnostics |
| Centralized reference is less real-time | Computation cost and runtime-per-step figures |

## Scenario Handling

Use all active scenarios for cross-scenario summaries. Use scenario tags to select
representative mechanism figures:

- `incident` for VSL and bottleneck response.
- `surge` for recovery behavior.
- `peak` or `spillback-risk` for ramp and off-ramp spillback.
- `medium` for controllable non-extreme behavior.
