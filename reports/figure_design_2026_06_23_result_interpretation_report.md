# Figure-Design 2026-06-23 Redraw: Assumptions and Interpretation

작성일: 2026-06-25

## Scope

이 리포트는 2026-06-23 Desktop raw output을 `docs/figure_design/*.md` 기준으로 새로 그린 figure set의 해석 기록이다. 새 simulation은 수행하지 않았고, 기존 3600 s 결과를 재가공했다.

- Figure root: `reports/figures/figure_design_2026_06_23_redraw/`
- Source raw 1: `C:\Users\alsrj\Desktop\Numerical-Sim\outputs\analysis_matrix_3600`
- Source raw 2: `C:\Users\alsrj\Desktop\Numerical-Sim\outputs\analysis_matrix_3600_extra`
- Generated output: 37 PNG + 37 PDF figure files
- QA contact sheets: `reports/figures/figure_design_2026_06_23_redraw/_qa_contact_sheets/`

## Plotting Assumptions

1. Scenario mapping

| Raw scenario id | Figure label | Interpretation |
|---|---:|---|
| `medium_demand` | Median | controllable moderate demand case |
| `peak_demand` | Peak | high-demand spillback-risk case |
| `skew_peak` | Peak skew | high-demand spatially skewed case |
| `incident_or_capacity_drop` | Incident | capacity-drop / incident-risk case |

현재 canonical scenario set은 이후에 수정되었으므로, 이 figure set은 최신 six-scenario definition의 final evidence가 아니라 6/23 raw result의 사후분석이다.

2. Controller set

| Controller | Figure label | Authority interpretation |
|---|---:|---|
| `NO-CONTROL` | No control | fixed-time / no RM / no VSL |
| `WU-CD-F` | WU-CD-F | Wu-authority-matched distributed benchmark: signal + VSL authority |
| `PROPOSED-FOLLOWERS-ONLY` | PFO | proposed distributed followers without leader |
| `PROPOSED-STACKELBERG` | P-Stack | proposed leader-follower hierarchy |

`PROPOSED-CENTRALIZED`는 이 raw output set에 없어서 이 report에서는 비교하지 않는다.

3. Metric assumptions

- Macro values are read from `analysis/summary_with_no_control.csv`.
- `Average travel-time proxy` is computed as `total_ttt / completed_vehicles * 3600`. This is not a true trajectory-level average travel time.
- Time-series figures use `progress_summary.csv`.
- Control-mechanism figures use `control_timeseries.csv` and `run_log.csv`.
- VSL activation is counted when posted VSL is below 99 km/h.
- RM activation is counted when any logged metering rate is below 1499 veh/h.
- Green activation is counted when any green time differs from the 56 s nominal reference by more than 1 s.
- Offset activation is counted when step-to-step offset change exceeds 1 s.

4. Diagnostic caveats

- Full rejected-candidate leader objective surfaces are unavailable because `decision_progress.csv` is not present in the 6/23 raw outputs.
- Fig. 4D therefore compares selected leader objective against next-step realized plant TTT only for selected actions. It is a fidelity sanity check, not proof that rejected candidates were ranked correctly.
- Boundary queue/load exposure is based on available logged proxy columns. In this raw set, the P-Stack run exposes leader-side boundary/load proxy columns more clearly than the other controllers. Treat Fig. 2B boundary panel as a diagnostic coverage warning, not as a harmonized cross-controller boundary-accounting result.
- P-Stack fallback/allocation/search metadata is only partially available in the raw tables. Fig. 3C shows fallback selection near zero in this run, but allocation mode cannot be inferred from the generated tables alone.

## Layout QA Result

The generated figures were visually inspected through individual PNG previews and contact sheets. The following readability corrections were applied:

- Moved dense legends in macro and congestion-transfer multi-panel figures from inside axes to figure-level top legends.
- Replaced per-point text labels in Fig. 6C with color-by-controller and marker-by-scenario legends to remove label overlap.
- Enlarged and re-spaced Fig. 4E objective-coverage audit so row and column labels remain readable.
- Corrected Fig. 2C off-ramp acceptance ratio by converting desired off-ramp flow from veh/h to vehicles before taking the accepted/desired ratio.
- Regenerated the figure set and QA contact sheets after the fixes.

Remaining dense plots are readable, but several panels intentionally remain compact because they are diagnostic summaries rather than standalone presentation slides.

## Macro Interpretation

### Total TTT improvement

| Scenario | WU-CD-F | PFO | P-Stack |
|---|---:|---:|---:|
| Median | 7.8% | 8.7% | 8.7% |
| Peak | 33.8% | 39.7% | 53.4% |
| Peak skew | 34.4% | 38.1% | 49.7% |
| Incident | 37.2% | 39.9% | 47.2% |

The main pattern is clear: P-Stack is not meaningfully different from PFO in the Median case, but it adds a large leader-layer gain in the congested Peak, Peak skew, and Incident cases. This supports the interpretation that the leader layer is most valuable when the network has strong urban-freeway coupling or storage pressure.

### Throughput and terminal burden

P-Stack improves TTT while also processing more vehicles in the congested cases:

| Scenario | No-control completed | P-Stack completed | No-control terminal | P-Stack terminal |
|---|---:|---:|---:|---:|
| Median | 11229.9 | 11632.3 | 830.3 | 430.9 |
| Peak | 9025.6 | 12886.6 | 5789.6 | 1929.8 |
| Peak skew | 8867.9 | 12403.1 | 5947.3 | 2415.6 |
| Incident | 9071.0 | 11911.1 | 5292.2 | 2457.2 |

This matters for interpretation: the P-Stack gains are not simply obtained by hiding vehicles outside the completed-vehicle accounting in these aggregate summaries. In Peak/Peak skew/Incident, P-Stack both reduces cumulative vehicle-hours and reduces the terminal-state burden relative to no control.

### Travel-time proxy

The `TTT/completed` proxy falls substantially under active control:

| Scenario | No control | PFO | P-Stack |
|---|---:|---:|---:|
| Median | 171.9 s/veh | 151.5 s/veh | 151.6 s/veh |
| Peak | 1006.4 s/veh | 473.2 s/veh | 328.7 s/veh |
| Peak skew | 1054.8 s/veh | 508.4 s/veh | 379.6 s/veh |
| Incident | 898.6 s/veh | 428.9 s/veh | 361.1 s/veh |

This reinforces the same conclusion: the larger P-Stack throughput is not accompanied by a worse aggregate TTT/completed proxy in these runs.

## Congestion-Transfer Interpretation

The decomposition figures show that the largest absolute gains in congested scenarios come from freeway TTT reduction, while urban TTT is also generally reduced relative to no control. This is consistent with the controller using ramp metering, signal service, and offset coordination to prevent freeway breakdown from dominating the total TTT.

However, the queue-exposure figures also show that P-Stack can carry nontrivial ramp queue exposure:

- Peak: P-Stack ramp queue exposure is higher than PFO and no control in the plotted proxy.
- Incident: P-Stack ramp queue exposure is below no control but above WU-CD-F/PFO.
- Off-ramp storage exposure is small in absolute magnitude; WU-CD-F tends to have larger off-ramp storage exposure in several scenarios.
- Boundary/load exposure is not directly comparable across controllers in this raw set because the logged proxy is not harmonized.

Interpretation: P-Stack is not merely suppressing all queues. It appears to trade some local queue/storage burden for much larger reductions in freeway/urban TTT and terminal vehicles. A final paper claim should use harmonized boundary-queue logging before presenting boundary exposure as a cross-controller fairness metric.

## Leader-Feasibility Interpretation

Fig. 3A and Fig. 3C suggest that the P-Stack leader is actively selecting targets rather than simply falling back to PFO/no-control in this 6/23 run.

Key observations:

- Fallback selection is essentially zero in the plotted P-Stack runs.
- `N_UF_star` and actual metering flow often move together after early transients, so the freeway/ramp target has visible behavioral effect.
- `N_P_star` and actual net inflow do not track as tightly; actual net inflow can stay negative while the selected target is positive.

The last point is important. It suggests one of three things may be happening: physical feasibility limits, target-definition mismatch, or net-inflow logging/sign-convention mismatch. Therefore, the leader target plot supports "leader influences follower behavior", but it does not yet support "the perimeter net-inflow target is accurately realized".

## Game-Coupling Interpretation

Fig. 4B shows correlations between action proxies and response proxies. These are useful as descriptive coupling evidence:

- Green service has negative correlation with freeway TTT, ramp queue, urban TTT, and urban queue, consistent with service allocation relieving both local and coupled congestion.
- RM also has negative correlation with freeway TTT and ramp queue in the logged response matrix, consistent with ramp-metering involvement in congestion mitigation.
- Offset proxy has weaker and mixed correlations, so offset should be interpreted as a secondary coordination mechanism rather than the sole source of gains.

These are not causal derivatives. They are response correlations under the selected closed-loop trajectories. For a stronger game-theoretic coupling claim, candidate-level perturbation data or controlled ablation runs are still needed.

Fig. 4D shows a monotone relationship between selected leader objective and next-step realized TTT. This is encouraging for objective fidelity, but because rejected candidates are absent, it cannot prove that the leader always selected the globally best candidate.

## Micro-Control Interpretation

The control-mechanism figures are consistent with controller authority:

- WU-CD-F changes signal green and VSL but has no ramp-metering or offset authority.
- PFO and P-Stack use ramp metering in Peak, Peak skew, and Incident.
- P-Stack uses more aggressive RM and offset changes in the congested cases than PFO, which is consistent with its larger freeway/terminal gains.
- VSL is most visible in the Incident case for WU-CD-F and PFO; P-Stack's improvements in this raw set appear to rely more strongly on RM / signal / leader-target coordination than on VSL activation.

This supports a control-method interpretation: PFO provides the distributed local control package, while P-Stack adds a macroscopic target layer that changes how aggressively the follower set manages freeway inflow and boundary service under high stress.

## Computation Interpretation

The 3600 s runs use 20 control steps at a 180 s control interval. Mean wall time per control step is approximately:

| Scenario | WU-CD-F | PFO | P-Stack |
|---|---:|---:|---:|
| Median | 4.9 s | 6.6 s | 64.1 s |
| Peak | 4.9 s | 8.2 s | 64.0 s |
| Peak skew | 5.4 s | 8.2 s | 67.1 s |
| Incident | 4.9 s | 8.1 s | 60.9 s |

All three active controllers stay below the 180 s control interval in this figure set, but P-Stack is still much more expensive than PFO and WU-CD-F. This supports a nuanced real-time claim:

- P-Stack is real-time feasible under this 3600 s raw experiment budget.
- P-Stack's computation cost remains the main practical trade-off.
- Centralized comparison is still needed to show whether P-Stack delivers a better performance-cost point than full centralized control.

## Figure-by-Figure Interpretation Notes

This section provides short interpretation notes for each generated figure. The notes are intended as caption or main-text drafting material, not as final causal proof.

### 01 Macro Performance

#### `Fig1A_total_ttt_cross_scenario`

This is the headline aggregate-performance figure. It shows that all active controllers reduce Total TTT relative to no control, but the leader layer becomes most valuable under stressed scenarios. In Median, PFO and P-Stack are almost identical, so the leader should not be overclaimed there. In Peak, Peak skew, and Incident, P-Stack provides a visibly larger improvement than both WU-CD-F and PFO.

Suggested interpretation: the Stackelberg layer is most useful when congestion creates strong urban-freeway coupling and storage pressure; under moderate demand, the distributed follower layer already captures most available benefit.

#### `Fig1B_urban_freeway_ttt_decomposition`

This figure decomposes the aggregate gain into urban and freeway components. The largest absolute reduction appears in freeway TTT, especially in Peak, Peak skew, and Incident. Urban TTT also decreases for PFO/P-Stack relative to no control in the congested scenarios, which weakens the concern that P-Stack only improves freeway performance by dumping all burden into the urban side.

Suggested interpretation: P-Stack primarily prevents freeway breakdown while still reducing, not increasing, the plotted urban TTT burden in the 6/23 raw summaries.

#### `Fig1C_delay_att_throughput`

This figure links three macro outcomes: total delay, TTT/completed proxy, and throughput. P-Stack reduces delay and the TTT/completed proxy while increasing completed vehicles in the stressed cases. This is important because higher throughput alone could otherwise make TTT look worse; here, P-Stack improves both throughput and the aggregate travel-time proxy.

Suggested interpretation: the P-Stack improvement is not simply a consequence of processing fewer vehicles. In Peak, Peak skew, and Incident, it processes more vehicles with lower cumulative vehicle-hours per completed vehicle.

#### `Fig1D_terminal_state_burden`

This figure checks whether controllers leave vehicles stranded at the end of the horizon. No control leaves a much larger terminal burden in stressed cases. P-Stack leaves the fewest or near-fewest terminal vehicles overall, especially in Peak and Peak skew.

Suggested interpretation: P-Stack's TTT improvement is accompanied by better horizon-end clearance. This helps defend against the concern that the controller merely shifts congestion beyond the evaluation window.

#### `Fig2_timeseries_medium_demand`

The Median time-series shows all active controllers tracking closely for most of the horizon. The no-control trajectory worsens late, while active controllers limit terminal growth. P-Stack does not visibly outperform PFO, matching Fig. 1A.

Suggested interpretation: Median is a sanity case for avoiding unnecessary intervention, not the strongest evidence for leader-layer value.

#### `Fig2_timeseries_peak_demand`

In Peak, trajectories separate strongly after congestion builds. No control accumulates TTT and terminal vehicles rapidly. WU-CD-F and PFO mitigate the growth, while P-Stack gives the lowest cumulative TTT and terminal burden.

Suggested interpretation: the leader-follower structure becomes valuable once ramp/freeway/urban interactions become binding enough that local follower control alone is insufficient.

#### `Fig2_timeseries_skew_peak`

The skewed peak case has a similar trend to Peak, but it stresses spatial imbalance. P-Stack again reduces cumulative TTT and terminal burden more than PFO and WU-CD-F.

Suggested interpretation: the leader layer helps when demand imbalance makes the coupling problem spatially uneven, not just when total demand is high.

#### `Fig2_timeseries_incident_or_capacity_drop`

The incident/capacity-drop case shows no-control deterioration over the horizon. Active controllers reduce the cumulative growth, and P-Stack remains the strongest among the plotted active controllers.

Suggested interpretation: under reduced freeway capacity, coordinated RM/signal/leader response can limit the downstream propagation of congestion.

### 02 Congestion Transfer

#### `Fig2A_spillback_summary`

This figure shows zero hard overflow/binding steps under the plotted diagnostics. It should be interpreted as a hard-constraint diagnostic rather than a performance figure.

Suggested interpretation: the compared runs do not trigger the logged hard spillback/binding flags, so performance differences in this raw set come from queue exposure and TTT dynamics rather than binary hard-spillback events.

#### `Fig2B_queue_exposure_summary`

This figure summarizes ramp, off-ramp, and boundary/load exposure. P-Stack can carry substantial ramp queue exposure, especially in Peak, while still reducing total TTT and terminal vehicles. Off-ramp storage exposure is small in absolute magnitude. The boundary/load panel should be treated cautiously because the available logged proxy is not harmonized across controllers.

Suggested interpretation: P-Stack does not eliminate all local queues; it trades some local storage burden for larger network-level TTT and throughput gains. Boundary/load conclusions require harmonized logging before becoming a final fairness claim.

#### `Fig2C_offramp_acceptance_ratio`

After unit correction, accepted/designed off-ramp flow is close to one across scenarios and controllers. This suggests that off-ramp demand is generally being served rather than heavily rejected.

Suggested interpretation: the main performance differences are unlikely to be caused by large off-ramp starvation in these runs.

#### `Fig2D_onramp_mechanism_incident_or_capacity_drop`

This mechanism panel shows how ramp queue, metering flow, urban on-ramp queue, and ramp releases evolve during the incident/capacity-drop case. P-Stack uses metering and releases differently from no control, maintaining controlled release while the no-control queue grows sharply.

Suggested interpretation: in the incident case, P-Stack is actively regulating freeway entry rather than passively matching no-control inflow. The remaining ramp queue is a trade-off against preventing larger freeway/terminal deterioration.

#### `Fig2D_onramp_mechanism_peak_demand`

In Peak, P-Stack applies stronger ramp-metering behavior than PFO and WU-CD-F. Ramp queue exposure can be high, but urban on-ramp queue and terminal outcomes are better than no control in the aggregate summaries.

Suggested interpretation: P-Stack's peak gain appears to come from stronger freeway-entry regulation combined with signal/offset response, not from VSL alone.

### 03 Leader Feasibility

#### `Fig3A_leader_targets_response_medium_demand`

The Median leader plot shows nonzero leader targets but weak separation from PFO-level performance. `N_UF_star` and actual metering flow move in the same broad range, while actual net inflow does not tightly track `N_P_star`.

Suggested interpretation: in Median, the leader is active but has limited marginal value because the network is not strongly constrained.

#### `Fig3A_leader_targets_response_peak_demand`

The Peak leader plot shows active adjustment of both `N_P_star` and `N_UF_star`. Actual metering flow broadly responds to `N_UF_star`, while net inflow tracking remains imperfect.

Suggested interpretation: the freeway/ramp target is behaviorally effective, but perimeter net-inflow target realization still needs diagnostic validation.

#### `Fig3A_leader_targets_response_skew_peak`

The skewed peak leader plot shows changing selected targets under spatially imbalanced demand. As in Peak, `N_UF_star` is more visibly reflected in actual metering flow than `N_P_star` is in actual net inflow.

Suggested interpretation: the leader appears to adjust to the skewed condition, but the target-response mismatch should be discussed as a feasibility or logging issue.

#### `Fig3A_leader_targets_response_incident_or_capacity_drop`

The incident leader plot shows target changes under reduced capacity. The selected objective increases over time as the system becomes more constrained, and the target-response mismatch is most visible.

Suggested interpretation: incident conditions expose the limits of target tracking. The result supports active leader behavior, but not perfect target realization.

#### `Fig3B_logged_best_candidate_locations`

This figure plots logged best leader candidate locations rather than a full objective surface. The selected candidates occupy a limited set of `N_P_star`/`N_UF_star` regions.

Suggested interpretation: the leader is not simply selecting a constant target, but this figure cannot prove global optimality because rejected candidate surfaces are unavailable.

#### `Fig3CD_fallback_tracking_error`

This figure combines target-tracking error and fallback selection. Fallback is essentially zero in this raw set, so P-Stack outcomes are not explained by fallback-to-PFO behavior. Tracking error remains nontrivial, especially for net inflow.

Suggested interpretation: P-Stack is actively selecting leader targets, but target tracking is an implementation/feasibility issue that should be reported honestly.

### 04 Game Coupling

#### `Fig4A_nash_response_diagnostics`

This figure shows follower response iteration diagnostics. WU-CD-F and PFO have a wider range of Nash-like iterations, while P-Stack is more tightly concentrated in the logged response.

Suggested interpretation: the follower response procedure is numerically stable in the logged runs, but iteration count alone should not be treated as proof of equilibrium quality.

#### `Fig4B_coupling_response_matrix`

This heatmap summarizes correlations between control-action proxies and response proxies. Green service, RM, and VSL proxy generally show negative correlations with TTT/queue responses, while offset has weaker mixed correlations.

Suggested interpretation: the plot supports the existence of urban-freeway coupling in the selected trajectories. It should be described as correlation evidence, not causal sensitivity.

#### `Fig4D_predicted_vs_realized_selected`

This plot compares selected leader objective and next-step realized plant TTT. The monotone trend suggests that the selected objective is directionally aligned with realized plant burden.

Suggested interpretation: selected-action objective fidelity is encouraging. However, because rejected candidates are not plotted, this does not prove that the leader ranked all alternatives correctly.

#### `Fig4E_objective_coverage_audit`

This audit records which state groups are included in freeway follower, urban follower, leader, and plant TTT accounting. It makes explicit that follower objectives are local while leader/plant coverage is broader.

Suggested interpretation: this figure should be used to explain the hierarchy: local followers do not individually see every state group, but the leader and plant TTT are intended to cover the global accounting.

### 05 Micro Control Behavior

#### `Fig5_mechanism_panel_incident_or_capacity_drop`

The incident mechanism panel shows P-Stack using aggressive RM and offset changes, while WU-CD-F/PFO show visible VSL activation in the incident case. P-Stack's gains appear to come more from RM/signal/leader-target coordination than VSL.

Suggested interpretation: the proposed hierarchy does not rely on a single actuator; it coordinates RM and signal-side actions when freeway capacity is degraded.

#### `Fig5_mechanism_panel_peak_demand`

The Peak mechanism panel shows P-Stack making sharp RM and offset adjustments. PFO is smoother, and WU-CD-F lacks RM/offset authority.

Suggested interpretation: the leader layer changes the aggressiveness and timing of local follower actions under peak congestion.

#### `Fig5_mechanism_panel_skew_peak`

The skewed peak mechanism panel shows sustained RM action and stronger offset activity for P-Stack. This is consistent with a response to spatially imbalanced demand.

Suggested interpretation: offset and RM become more important when the demand pattern is asymmetric, because the controller must coordinate both storage and progression.

#### `Fig5A_RM_mean_metering_rate`

This figure summarizes average RM strength. P-Stack generally has the lowest mean metering rate in stressed scenarios, meaning stronger metering.

Suggested interpretation: P-Stack's stressed-scenario gains are associated with more assertive freeway-entry regulation.

#### `Fig5A_RM_activation_fraction`

PFO and P-Stack activate RM frequently under Peak, Peak skew, and Incident. P-Stack also activates RM in Median more than PFO.

Suggested interpretation: RM is a primary differentiator between the proposed controllers and WU-CD-F, and P-Stack uses it more actively.

#### `Fig5B_VSL_reduction`

Mean VSL reduction is visible mainly in the Incident case for WU-CD-F and PFO. P-Stack does not show strong VSL reduction in this raw set.

Suggested interpretation: VSL is not the dominant source of P-Stack improvement in the 6/23 runs.

#### `Fig5B_VSL_activation`

VSL activation is concentrated in the Incident case. This matches the expectation that VSL is most relevant when a freeway capacity-drop or incident condition is present.

Suggested interpretation: VSL behavior is scenario-specific; it should not be presented as the universal mechanism behind all improvements.

#### `Fig5C_green_adjustment`

Green-time adjustment is active for WU-CD-F, PFO, and P-Stack. P-Stack shows larger adjustment in the most stressed scenarios, especially Peak skew and Incident.

Suggested interpretation: signal control contributes to the proposed controllers' ability to manage urban-freeway boundary conditions.

#### `Fig5C_green_activation`

Green activation is frequent across active controllers. This confirms that signal control is not a passive background setting in the comparison.

Suggested interpretation: differences between controllers are not only about whether green control is used, but about how it is coordinated with RM, offset, and leader targets.

#### `Fig5D_offset_change`

Offset changes are only available to PFO and P-Stack. P-Stack shows larger mean offset changes in stressed scenarios.

Suggested interpretation: offset is a secondary but meaningful coordination lever, especially when coupled with leader-guided RM and green-time decisions.

#### `Fig5D_offset_activation`

Offset activation is common for PFO/P-Stack and absent for WU-CD-F/no-control by authority design.

Suggested interpretation: this figure should be used to document authority differences, not to claim that offset alone explains the performance gap.

### 06 Computation Cost

#### `Fig6A_runtime_per_control_step`

P-Stack is much slower than WU-CD-F and PFO, but remains below the 180 s control interval in these 3600 s runs.

Suggested interpretation: P-Stack is feasible under the tested budget but has a significant computation-cost trade-off.

#### `Fig6B_candidate_evaluation_budget`

This figure shows why P-Stack is expensive: it carries leader candidate evaluation plus follower response work. PFO has substantial follower-grid cost but avoids the leader layer.

Suggested interpretation: the main remaining engineering issue is reducing Stackelberg evaluation cost without losing the stressed-scenario performance gains.

#### `Fig6C_performance_compute_tradeoff`

This figure places performance improvement against mean wall time per control step. P-Stack dominates in stressed scenarios in performance but is much more expensive. In Median, P-Stack costs much more while giving almost no gain beyond PFO.

Suggested interpretation: the strongest argument for P-Stack is not universal dominance, but a stress-dependent trade-off: higher computation cost buys large benefits under Peak, Peak skew, and Incident conditions.

## Main Takeaways

1. PFO validates the proposed distributed follower layer: it improves over WU-CD-F in most stressed scenarios and remains fast.
2. P-Stack adds clear value in Peak, Peak skew, and Incident: higher TTT improvement, higher completed vehicles, lower terminal burden, and lower TTT/completed proxy.
3. Median is not the scenario where the leader layer should be overclaimed; P-Stack and PFO are almost identical there.
4. The leader layer appears behaviorally active, but `N_P_star` tracking requires further validation because target and realized net inflow are not tightly aligned.
5. Boundary/load exposure must be re-evaluated with harmonized logging before it is used as a fairness or queue-hiding claim.
6. The current figures are appropriate for macro/micro/game-coupling discussion, but ablation and candidate-level fidelity runs are still needed before final causal claims.
