# t0 — Demand & incident specification for the six paper cells

All values extracted from code (code-of-record: `Numerical-Sim-offiter`, branch `cross-gate`).
No invented numbers. Companion figure: `analysis/figures/f0_demand_profile.{pdf,png}`.

## 1. Scenario cells (src/config/scenarios.yaml)

| Cell | Class scale (urban = freeway = ramp) | Spatial skew (W:E) | Incident | Source lines |
|---|---|---|---|---|
| sweet_155_w | 1.55 | — | — | scenarios.yaml:455-466 |
| sweet_170_w | 1.70 | — | — | scenarios.yaml:493-504 |
| sweet_170_skew15_w | 1.70 | `urban_west_east_ratio: 1.5` | — | scenarios.yaml:518-530 |
| sweet_170_incident_w | 1.70 | — | FW_E seg 6, 1 of 2 lanes, 4500-6300 s | scenarios.yaml:434-454 |
| sweet_190_w | 1.90 | — | — | scenarios.yaml:531-542 |
| sweet_200_w | 2.00 | — | — | scenarios.yaml:357-368 |

All six cells share identical pulse parameters: `pulse_base_scale: 0.5`,
`pulse_start_sec: 3600`, `pulse_rampup_sec: 300`, `pulse_plateau_sec: 3600`,
`pulse_rampdown_sec: 300`. `incident_capacity_factor: 1.0` in every cell (global
capacity multiplier, inactive).

## 2. Demand time profile (src/models/demand.py)

Trapezoidal pulse, `DemandProfile._pulse_fraction` (demand.py:192-210), applied as
`effective_scale(t) = base + (class_scale − base) · pulse(t)` with the built-in sine
peak wave disabled in pulse mode (`peak = 1.0`, demand.py:257-264; sine definition
demand.py:249).

Timeline over T_total = 10800 s = 60 control steps × 180 s = 180 min
(run convention `--T-total 10800`, ANALYSIS_PLAN_FINAL.md §0.3):

| Phase | Time (s) | Time (min) | Steps (0-based) | Scale |
|---|---|---|---|---|
| Base plateau | 0 – 3600 | 0 – 60 | 0 – 19 | 0.5 |
| Ramp-up (linear) | 3600 – 3900 | 60 – 65 | 20 – 21 | 0.5 → class |
| Peak plateau | 3900 – 7500 | 65 – 125 | 21 – 41 | class scale |
| Ramp-down (linear) | 7500 – 7800 | 125 – 130 | 41 – 43 | class → 0.5 |
| Base tail | 7800 – 10800 | 130 – 180 | 43 – 59 | 0.5 |

NC warmup = steps 0–19 (0–60 min); scoring window wTTT = steps 20–59
(pubstyle.py:34-38; ANALYSIS_PLAN_FINAL.md §0.3). The pulse starts exactly at
warmup end (both 3600 s).

## 3. Entry points and nominal rates (scale = 1.0)

Base rates (demand.py:265-267): freeway 1650, ramp 560, urban 500 veh/h, each
multiplied by the per-entry gradients below.

| Entry group | Entries and nominal rates [veh/h] | Gradient | Source |
|---|---|---|---|
| Freeway mainline origins (2) | FW_W 1650, FW_E 1732.5 | ×(1+0.05·idx) | demand.py:269-272 |
| Urban boundary gates (7) | in_A_top 500, in_A_left 550, in_B_top 600, in_C_top 650, in_C_right 700, in_D_left 750, in_F_right 800 | ×(1+0.10·idx) | demand.py:274-277 |
| On-ramp arrivals (4) | R_D_W 560, R_F_W 588, R_D_E 616, R_F_E 644 | ×(1+0.05·idx) | demand.py:307-310 |

Total nominal inflow at scale 1.0 = 3382.5 (mainline) + 4550 (urban) + 2408 (ramps)
= **10340.5 veh/h**. Per-cell peak inflow = 10340.5 × class scale
(1.55 → 16028, 1.70 → 17579, 1.90 → 19647, 2.00 → 20681 veh/h); base periods run at
0.5 × 10340.5 = 5170 veh/h. Boundary-out side rates `urban_base·(0.82+0.08·idx)`
(410–650 veh/h) are exit-side quantities, not entries (demand.py:305-306).

### Spatial skew (sweet_170_skew15_w only)

`urban_west_east_ratio = 1.5` redistributes only the four side gates — west
(in_A_left, in_D_left) vs east (in_C_right, in_F_right) — to a 1.5:1 west:east
split while preserving the side total and the north gates (demand.py:286-303).
At scale 1.0: west total 1300 → 1680 (×1.292; in_A_left 710.8, in_D_left 969.2),
east total 1500 → 1120 (×0.747; in_C_right 522.7, in_F_right 597.3). Total urban
inflow is unchanged (skew is separated from demand volume).

## 4. Incident specification (P1-A5) — sweet_170_incident_w

What is blocked, mechanism, timing — with code quotes.

**Scenario definition** (src/config/scenarios.yaml:439-446):

```json
"freeway_lane_closures": [
  {
    "link": "FW_E",
    "segment": 6,
    "lane_loss": 1.0,
    "start_sec": 4500.0,
    "end_sec": 6300.0
  }
]
```

- **What**: freeway link FW_E, segment index 6 (0-based; 7th of 8 segments — the
  tail segment downstream of the last on-ramp merge at seg 5, upstream of exit
  seg 7).
- **Mechanism**: lane closure, not a direct capacity factor. `lane_loss: 1.0` of
  `freeway_lanes: 2` → effective lanes 2 → 1 at that segment (50% local capacity
  reduction). Applied via the effective-lane profile, taking the minimum with any
  off-ramp capacity-drop reduction (src/models/metanet.py:244-245):

  ```python
  incident_lanes = max(1.0e-9, float(net.freeway_lanes) - max(0.0, float(loss)))
  profile[link][segment_idx] = min(profile[link][segment_idx], incident_lanes)
  ```

- **Activation window**: half-open `start_sec <= t < end_sec`
  (src/models/demand.py:237: `... or not start <= time_sec < end: continue`),
  i.e. t ∈ [4500, 6300) s = [75, 105) min = steps 25–34, duration 1800 s = 30 min,
  entirely inside the peak plateau (65–125 min).
- The closure enters `DemandStep.freeway_lane_loss`, so plant and MPC forecast see
  the same incident state (demand.py:228-243).

## 5. Fixed network-side constants relevant to demand (src/config/default.yaml)

Freeway per link: 8 seg × 0.5 km, 2 lanes, q_cap 4000 veh/h, v_free 100 km/h,
ρ_crit 33.5, ρ_max 95.02 (default.yaml:22-30). On-ramp capacity 1500 veh/h each,
ramp queue ≤ 180 veh (default.yaml:41-45, 54). Off-ramp split ratio 0.2 per
off-ramp, storage 60 veh (default.yaml:127-130, 151-155). Boundary-out exit
capacity 1600 veh/h per gate (default.yaml:95). Signal cycle 120 s, lost time 8 s,
green 20–92 s (default.yaml:71-74).
