# Main Text Figure Set

This chapter defines a compact paper-ready figure package. It should not need
editing when the active scenario count changes.

## Recommended Main Figures

| Figure | Chapter | Purpose |
|---|---|---|
| Fig. 0 | `02_scenario_catalog.md` | Scenario topology and directional demand snapshot |
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
| Improvements are not just freeway-protection artifacts | Urban TTT and freeway TTT both decrease, while completed vehicles increase and terminal vehicles decrease |
| PFO provides useful distributed local response | PFO vs WU and no-control macro and micro figures |
| P-Stack adds a meaningful leader layer only when it selects non-fallback targets | PFO vs P-Stack target/fallback/candidate diagnostics |
| Centralized reference is less real-time | Computation cost and runtime-per-step figures |

## Current Effect-Oriented Presentation Package

The current slide-ready package generated under
`reports/figures/effect_oriented_2026_06_23/` uses the following sequence:

1. `Scenario_topology_directional_demand`: show the demand pattern before
   showing controller outcomes.
2. `Fig. 1A Total TTT`: headline cross-scenario Total TTT reduction.
3. `Fig. 1B Urban-Freeway TTT Burden Decomposition`: defend against the claim
   that freeway gains are obtained by dumping burden into the urban side.
4. `Network_effect_summary`: show absolute completed vehicles and absolute
   terminal vehicles, with no-control included.
5. `EffectChain_RM_queue_TTT_*`: show RM/ramp queue to cumulative TTT and
   terminal outcome.
6. `EffectChain_signal_service_queue_*`: show green/offset changes to urban
   departures and movement queue response.
7. `EffectChain_VSL_RM_speed_density_incident_or_capacity_drop`: show
   directional VSL/RM, upstream/downstream ramp queues, freeway speed/density,
   and freeway TTT in the incident case.
8. FD/MFD operating-point figures: use as caveated supporting diagnostics only.
9. `Computation_time_per_step`: show that all controllers remain below the
   180 s control interval in the current 3600 s runs, while P-Stack is the
   computationally expensive method.

Do not present effect-chain figures as "the actuator was activated." Present
them as a causal diagnostic chain: control input, interface flow or queue
response, network state response, and final TTT/throughput/terminal consequence.

## FD/MFD Caveat

The current numerical simulator does not produce clean canonical FD/MFD loops in
all scenarios. Use FD/MFD plots to say that P-Stack appears to suppress
high-density or high-accumulation states, not to claim a validated empirical
fundamental diagram. Strong FD/MFD claims should be deferred to a microscopic
tool such as VISSIM or to a separately validated plant model.

## Scenario Handling

Use all active scenarios for cross-scenario summaries. Use scenario tags to select
representative mechanism figures:

- `incident` for VSL and bottleneck response.
- `surge` for recovery behavior.
- `peak` or `spillback-risk` for ramp and off-ramp spillback.
- `medium` for controllable non-extreme behavior.
