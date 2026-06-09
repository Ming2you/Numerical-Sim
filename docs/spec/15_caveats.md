# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 15. Important Caveats

The current mathematical specification contains some parts that may require implementation choices, especially:

- exact units of `N_P_star` and `N_UF_star`
- whether the leader objective should use accumulation terms or follower TTT directly
- the exact network topology and demand input format
- whether the urban queue model should operate at 1 s, 5 s, or another short interval
- how to map VSL to desired speed in the METANET model
- whether boundary queue balancing should use only perimeter movements or all inflow/outflow movements

Implement these as explicit config options. Do not silently assume them without documenting the assumption in `report.md`.
