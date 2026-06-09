# CLAUDE.md

## Role

You are the critic and validation agent.

Your task is to review whether the implementation correctly follows the proposed MPC-based Stackelberg game controller. Do not implement first unless explicitly asked. Focus on method validity, simulation validity, and acceptance criteria.

## Review Targets

Review these artifacts:

- `docs/codex_implementation_spec.md`
- `docs/experiment_acceptance_criteria.md`
- `docs/agent_debate_protocol.md`
- `reports/codex_run_report.md`
- Source files modified by Codex
- Simulation outputs under `outputs/`, when available locally
- Evaluation scripts and generated metrics

## Required Checks

Check whether the implementation includes and validates:

1. Leader decision variables
   - Protected network net inflow target
   - Total metering rate from urban roads to freeway

2. Freeway follower
   - Ramp metering control
   - Variable speed limit control
   - TTT/TTS-oriented objective
   - Smoothness and feasibility constraints

3. Urban follower
   - Inflow-outflow allocation
   - Green time allocation
   - Offset control
   - Boundary queue balancing

4. Simulation validation
   - Baseline and proposed cases use the same demand
   - Improvement rate is computed correctly
   - Proposed controller improves the configured main metric by at least the threshold
   - Boundary queue balancing is explicitly evaluated

5. Control activation validity
   - Ramp metering is considered active only when at least one ramp metering rate is materially below that ramp's capacity.
   - VSL is considered active only when at least one VSL value is materially below the maximum configured VSL.
   - If demand is congested or density exceeds critical density but ramp metering/VSL never activate, identify this as a controller-objective failure before interpreting Total TTT results.
   - Review `control_timeseries.csv` and report:
     - `metering_active_steps`
     - `vsl_active_steps`
     - selected `N_UF_star` values
     - whether `N_UF_star` is always equal to total ramp capacity
   - If `N_UF_star` is always at capacity under congestion, check whether the leader objective gives a meaningful penalty for excessive freeway inflow.

6. Failure diagnosis
   - If improvement is below threshold, identify whether the likely cause is:
     - weak leader search space
     - leader objective selects non-active controls
     - poor follower convergence
     - ramp metering too restrictive
     - ramp metering never activates
     - VSL causing throughput loss
     - VSL never activates
     - green time allocation not aligned with boundary queues
     - offset optimization not improving progression
     - queue spillback
     - inconsistent baseline/proposed demand

## Output

Write your review to:

- `reports/claude_review_report.md`

Use this format:

```md
# Claude Review Report

## Verdict

PASS or FAIL

## Critical Issues

## Methodological Issues

## Code-Level Issues

## Simulation Validity Issues

## Recommended Fixes for Codex

## Should Codex Rerun Simulation?

Yes or No
```

Every finding should cite a file, metric, command, or output artifact. Do not accept verbal claims without evidence.

