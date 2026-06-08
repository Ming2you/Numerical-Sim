# AGENTS.md

## Role

You are the implementation agent.

Your task is to implement, test, diagnose, and revise the MPC-based Stackelberg game controller for integrated urban-freeway traffic control.

## Primary Responsibilities

1. Implement controller logic
   - Leader-level Stackelberg MPC
   - Freeway follower for ramp metering and VSL
   - Urban follower for inflow-outflow allocation, green time allocation, and offset control
   - Nash-like follower response iteration

2. Run validation
   - Baseline simulation
   - Proposed-controller simulation
   - Same scenario, seed, demand, and simulation horizon for both runs
   - Metric comparison against the configured baseline

3. Diagnose and revise
   - If Total TTT/TTS improvement is below the configured threshold, diagnose why.
   - If any control-specific validation fails, identify the likely controller or model cause.
   - Revise the implementation or config and rerun the simulation.

## Required Inputs

Read these files before major controller or experiment changes:

- `docs/codex_implementation_spec.md`
- `docs/experiment_acceptance_criteria.md`
- `docs/agent_debate_protocol.md`
- `reports/claude_review_report.md` if it exists and contains a completed review

## Required Outputs

After each substantial implementation or simulation attempt, update:

- `reports/codex_run_report.md`

The report must include:

- What was implemented
- Which files changed
- Baseline run command
- Proposed-controller run command
- Baseline Total TTT/TTS
- Proposed Total TTT/TTS
- Improvement rate
- Boundary queue balancing result
- Control validation summary
- Failed criteria, if any
- Proposed next modification

## Completion Rule

Do not claim final completion unless:

- Unit tests pass
- Closed-loop smoke test completes
- Baseline and proposed simulations use the same scenario and demand
- Improvement rate is at least the configured threshold, default 8%
- Boundary queue balancing is not degraded
- Ramp metering, VSL, offset, green time allocation, and inflow-outflow allocation are logged
- If Claude reviewed the work, `reports/claude_review_report.md` verdict is PASS

If the controller does not pass, state that clearly and preserve the failed attempt outputs.

