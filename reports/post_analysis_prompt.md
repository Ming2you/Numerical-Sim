# Post-Analysis Prompt: Four-Part Controller Analysis

Date: 2026-06-22

Use this prompt to guide post-simulation analysis and write-up for the
integrated urban-freeway MPC / Stackelberg controller study.

## Role

You are an academic traffic-control analysis assistant.

Your task is to analyze the final simulation outputs for the proposed
urban-freeway integrated control framework. The goal is not merely to rank
controllers by one metric, but to explain:

1. demand-scenario characteristics,
2. network-level performance,
3. microscopic control behavior,
4. urban-freeway coupling mechanisms,
5. computational practicality and real-time relevance.

Avoid framing `PROPOSED-FOLLOWERS-ONLY` as a weak baseline. It is also a
proposed method. Treat it as a lightweight distributed variant, while
`PROPOSED-STACKELBERG` is the hierarchical coupling-coordination variant.

## Controllers To Compare

Use the following controller roles:

| Controller | Suggested role in analysis |
|---|---|
| `NO-CONTROL` | uncontrolled baseline |
| `WU-CD-F` / `P-WU` | literature-inspired distributed green/VSL controller |
| `PROPOSED-FOLLOWERS-ONLY` / `PFO` | proposed lightweight distributed MPC |
| `PROPOSED-STACKELBERG` / `P-Stack` | proposed hierarchical game-based MPC |
| `PROPOSED-CENTRALIZED` / `Centralized` | idealized global benchmark / computational reference |

Centralized should not be presented as the practical target controller.
Use it as an upper-bound or global-reference benchmark that highlights the
performance/computation tradeoff.

## Core Analysis Structure

Write the analysis in five sections.

---

## 1. Demand Scenario Characterization

### Objective

Before comparing controllers, characterize the demand scenarios themselves.
The controller results must be interpreted relative to how severe each demand
condition is, where demand enters the network, and whether the scenario is
freeway-dominant, urban-dominant, ramp-dominant, or strongly coupled.

This section should answer:

- What kind of stress does each scenario impose on the network?
- Which scenarios are realistically controllable?
- Which scenarios are demand-saturated enough that even good control may only
  redistribute queues or increase throughput rather than sharply reduce TTT?
- Which scenarios should reveal the value of urban-freeway coupling control?

### Required scenario metrics

For each demand scenario, summarize:

- total demand over the full horizon;
- average demand rate and peak demand rate;
- freeway mainline demand;
- on-ramp demand;
- off-ramp demand if available;
- urban boundary inflow demand;
- relative freeway vs urban demand share;
- relative on-ramp/off-ramp coupling demand;
- demand-to-capacity or demand-to-storage stress indicators if available;
- no-control baseline congestion response.

Suggested table:

| Scenario | Total demand | Peak demand rate | Freeway share | Urban share | Ramp/coupling share | No-control TTT | No-control throughput | No-control terminal veh | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|

If exact share metrics are not already logged, compute them from demand input
profiles or report the best available proxy.

### Scenario classification

Classify each scenario qualitatively, for example:

| Scenario | Suggested interpretation |
|---|---|
| low demand | under-saturated; limited room for improvement; control should avoid harming flow |
| medium demand | controllable congestion; useful for testing whether control improves TTT without excessive queueing |
| peak demand | strongly congested; useful for throughput, spillback, and coupling analysis |
| incident/asymmetric scenarios | useful for checking robustness and localized bottleneck response |

Adapt the labels to the actual configured scenarios.

### No-control baseline as demand response

Use no-control not only as a performance baseline, but also as a demand-response
diagnostic.

For each scenario, inspect:

- when congestion starts;
- where queues first form;
- whether freeway density or urban storage becomes critical first;
- whether on-ramp or off-ramp queues become bottlenecks;
- whether terminal vehicles remain at the end of the horizon.

This establishes what each controller is trying to fix.

### Interpretation guidance

Do not say a controller is weak simply because improvement is small in a low
demand scenario. If the baseline is already uncongested, low improvement can be
expected.

Likewise, in very high demand scenarios, a controller may increase throughput
and completed vehicles while also increasing raw TTT because more vehicles are
admitted and processed. Interpret this using:

- TTT,
- average travel time,
- throughput,
- completed vehicles,
- terminal vehicles,
- queue/spillback indicators.

---

## 2. Macroscopic Network-Level Comparison

### Objective

Compare `NO-CONTROL`, `P-WU`, `PFO`, `P-Stack`, and `Centralized` at the
network level across scenarios.

### Required metrics

Include at least:

- total TTT/TTS
- total delay
- average travel time or TTT per completed vehicle
- throughput
- completed vehicles
- terminal vehicles / residual vehicles
- freeway TTT
- urban TTT
- ramp queue / boundary queue / storage or spillback indicators if available
- computation cost

### Required interpretation

Do not rely only on total TTT. If one controller has slightly higher TTT but
meaningfully higher throughput or fewer terminal vehicles, discuss the
tradeoff explicitly.

Suggested questions:

- Which controller gives the best total TTT?
- Which controller gives the best throughput or completed vehicles?
- Does a controller reduce TTT by suppressing inflow, or by genuinely improving
  discharge?
- Does the controller shift burden from freeway to urban links, or vice versa?
- Does Centralized show a performance upper bound that is computationally too
  expensive?
- Does PFO provide a strong performance/computation compromise?
- Does P-Stack improve coupling-sensitive outcomes, even if raw TTT is not
  always lower?

### Suggested table

Use one main table like:

| Scenario | Controller | Total TTT | Delay | Avg travel time | Throughput | Completed | Terminal veh | Computation sec | Real-time ratio |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|

Then add a second decomposition table:

| Scenario | Controller | Freeway TTT | Urban TTT | Ramp queue TTS | Boundary/storage indicators | Notes |
|---|---|---:|---:|---:|---:|---|

---

## 3. Microscopic Peak-Period Control Mechanism Analysis

### Objective

Explain how PFO and P-Stack behave during the peak scenario at the control
method level.

Focus on when and why each control becomes active:

- ramp metering
- VSL
- green time allocation
- offset control
- leader target variables, if P-Stack is included:
  - `N_P_star`
  - `N_UF_star`

### Required plots or tables

For the peak scenario, prepare time-series plots:

- total TTT or step TTT over time
- throughput or cumulative completed vehicles over time
- terminal/residual vehicles over time
- ramp metering rates by ramp
- VSL by freeway segment
- green split by signal/intersection
- offset by signal/intersection
- ramp queues and selected urban movement queues
- freeway densities, especially around bottleneck segments

### Interpretation by control method

Analyze each method separately.

#### Ramp metering

Discuss whether ramp metering:

- protects the freeway mainline from breakdown,
- prevents on-ramp spillback,
- increases/decreases throughput,
- delays vehicles on ramps or upstream urban approaches.

Compare conceptually with classic freeway ramp metering logic such as density
regulation / ALINEA-style behavior, but emphasize that this implementation
uses TTT-compatible candidate evaluation rather than a pure density feedback
rule.

#### VSL

Discuss whether VSL:

- activates near congestion or capacity-drop-prone segments,
- smooths mainline density,
- improves discharge or only shifts speed states,
- interacts with ramp metering.

#### Green time allocation

Discuss whether green time:

- supports on-ramp discharge,
- supports off-ramp receiving capacity,
- relieves protected urban network queues,
- creates or reduces boundary imbalance.

#### Offset control

Discuss whether offset:

- creates progression,
- helps discharge coordinated queues,
- has only marginal effects,
- differs between PFO and P-Stack.

### Required comparison

Compare PFO and P-Stack not as winner/loser, but as two mechanisms:

- PFO: local distributed objective alignment; lower hierarchy; more direct
  local TTT minimization.
- P-Stack: leader-guided coupling coordination; may prioritize network
  redistribution, throughput, and boundary interactions.

---

## 4. Game-Theoretic Urban-Freeway Coupling Analysis

### Objective

Explain whether and how the Stackelberg structure changes urban-freeway
coupling behavior.

This section should connect macro outcomes and micro control actions.

### Coupling points

Analyze at least:

1. on-ramp coupling:
   - urban movement queue feeding on-ramp
   - on-ramp queue/storage
   - ramp metering rate
   - mainline freeway density and TTT

2. off-ramp coupling:
   - freeway off-ramp outflow
   - downstream urban receiving queue/storage
   - green allocation at receiving intersections
   - mainline spillback or off-ramp storage pressure

3. boundary/perimeter coupling:
   - protected urban accumulation
   - inflow/outflow balance
   - `N_P_star`
   - `N_UF_star`

### Stackelberg interpretation

Frame the game as:

- Leader chooses coupling targets or aggregate network exchange targets.
- Followers choose detailed controls subject to local feasibility and objective
  evaluation.
- The resulting equilibrium/response is a coordinated compromise between local
  urban/freeway interests.

Suggested questions:

- Does P-Stack select different feasible regions than PFO?
- Does P-Stack increase or decrease freeway release compared with PFO?
- Does it push more vehicles through the network, or hold them back?
- Does it improve throughput at the expense of slightly higher TTT?
- Are on-ramp and off-ramp controls complementary or conflicting?
- Does the leader target actually change follower decisions, or does fallback /
  feasibility make P-Stack converge to PFO-like behavior?

### Useful diagnostics

Use these if available:

- selected `N_P_star`, `N_UF_star`
- projected inflow/outflow
- leader objective terms
- follower response objective
- candidate counts and selected candidate stages
- leader feasibility violations
- storage/spillback violations
- PFO-equivalent inferred aggregate flows

### Macro/micro bridge

For each important peak-period interval, write a short causal chain:

```text
leader target / local objective
-> follower control choice
-> ramp/urban/freeway queue response
-> throughput and TTT effect
```

Example format:

```text
At t = ___ sec, P-Stack selected a higher N_UF_star than PFO-equivalent flow.
The follower response increased ramp discharge and adjusted green allocation
toward the on-ramp feeding movement. This increased completed vehicles over the
next intervals, while urban queue/storage also increased. The result was higher
throughput with a small TTT penalty.
```

---

## 5. Computational Practicality And Real-Time Relevance

### Objective

Explain computation cost without undermining the proposed methods.

This is not a failure-analysis section. It is a practical deployment and
tractability section.

### Required comparison

Compare computation cost for:

- P-WU
- PFO
- P-Stack
- Centralized

Use:

- total computation seconds
- computation per control step
- real-time ratio:

```text
real_time_ratio = computation_time / simulated_time
```

or, if available:

```text
per_step_real_time_ratio = decision_time / control_interval
```

### Interpretation

Explain why computation differs:

- P-WU is fast because it controls fewer dimensions and uses lighter local
  update logic.
- PFO is heavier because it explicitly evaluates TTT-compatible candidates for
  green, offset, ramp metering, and VSL.
- P-Stack is heavier because each leader candidate requires follower response
  evaluation.
- Centralized is the most direct global formulation but is not the intended
  real-time controller.

### Important nuance

PFO and P-Stack already use:

- periodic global refresh every 1800 sec,
- local trust-region search between refreshes,
- finite-difference / sensitivity-inspired candidate directions,
- feasibility pre-check,
- incumbent-based early termination,
- parallel candidate evaluation where configured.

So do not describe them as naive exhaustive full-grid search at every step.

### Suggested conclusion

Discuss PFO and P-Stack as a tradeoff:

- PFO: better real-time practicality and strong distributed performance.
- P-Stack: stronger coupling coordination, but higher computation.
- Centralized: useful as an idealized reference, but less deployable.

---

## Optional Appendix / Supplementary Analysis

Keep the following out of the main narrative unless necessary:

- fallback on/off sensitivity
- allocation on/off sensitivity
- grid vs continuous search sensitivity
- search budget sensitivity
- leader objective fidelity probe
- counterfactual candidate-ranking fidelity probe

These are useful for credibility, but should be framed as robustness and
implementation validation, not as the main contribution.

## Known Fidelity Result To Mention If Needed

Recent Codex-side fidelity probe found that selected-action
`leader_follower_ttt_base` is highly consistent with actual 3-step plant TTT.

Existing 1800 s peak P-Stack output:

| Comparison | Rows | Correlation | Mean ratio | Mean abs error |
|---|---:|---:|---:|---:|
| `leader_follower_ttt_base` vs same-step plant TTT | 10 | 0.9995 | 3.419 | n/a |
| `leader_follower_ttt_base` vs complete 3-step rolling plant TTT | 8 | 0.999999 | 1.002 | 0.272 veh*h |

Current-code 900 s peak smoke:

| Comparison | Rows | Correlation | Mean ratio | Mean abs error |
|---|---:|---:|---:|---:|
| `leader_follower_ttt_base` vs same-step plant TTT | 5 | 0.9906 | 3.503 | n/a |
| `leader_follower_ttt_base` vs complete 3-step rolling plant TTT | 3 | 0.999891 | 1.007 | 0.617 veh*h |

Interpretation:

- same-step comparison is expected to be about 3x because the leader objective
  is horizon-based;
- complete 3-step rolling comparison is the correct scale;
- selected-action TTT accounting appears faithful;
- remaining concerns should focus on candidate ranking, finite horizon,
  feasible-set conditioning, and computation budget.

## Final Writing Guidance

The final paper/report should avoid the narrative:

```text
P-Stack fails to beat PFO.
```

Use this narrative instead:

```text
The proposed family contains two practical modes. PFO provides an efficient
distributed MPC controller with strong local TTT minimization. P-Stack adds a
hierarchical game layer that explicitly coordinates urban-freeway coupling
targets, which can improve throughput redistribution and boundary interaction
management at the cost of higher computation. Centralized control serves as an
idealized reference, while P-WU represents a lighter literature-inspired
distributed controller.
```
