# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 12. Coding Style and Robustness

Follow these implementation rules:

- Use typed dataclasses or Pydantic models for states, controls, and config objects.
- Keep units explicit in variable names or config comments.
- Prevent negative density, speed, flow, and queue values by projection and logging.
- Avoid hidden global variables.
- Use deterministic random seeds.
- Save all raw time series.
- Never claim that the controller passed unless the metric calculation says so.
- If optimization is infeasible, return the nearest feasible control and log the infeasibility.
- If a dependency such as CasADi, scipy, or cvxpy is unavailable, implement a fallback grid search or heuristic solver.

### 12.1 Language policy

- Reports, implementation notes, review notes, and agent-facing Markdown documents must be written in Korean by default.
- New code comments and docstrings must be written in Korean by default.
- Keep code identifiers, public APIs, config keys, file paths, metric names, command names, units, and mathematical symbols in their existing English or symbolic form.
- Preserve original spelling when quoting command output, exception messages, CSV/JSON keys, or external references.

### 12.2 Required comment coverage

Add Korean comments for every non-trivial implementation block so that a reader can track the model without reconstructing the whole code path manually.

Required comments:

- Model equations: density update, speed update, queue conservation, storage update, receiving-space allocation, and delay-buffer scheduling.
- Unit conversions: every conversion between seconds/hours, vehicles/flow-rate, per-step counts, and per-hour rates.
- Coupling boundaries: on-ramp synchronization, ramp metering projection, off-ramp storage blocking, and freeway-to-urban arrival injection.
- Optimization logic: leader candidate generation, follower projection, beam search, convergence checks, infeasibility projection, and objective terms.
- Heuristics and approximations: any bounded search, fallback solver, compact topology, aggregation, clipping, or calibrated constant.
- Diagnostics: any metric or flag that is later used to interpret controller validity.

Comment style:

- Prefer a short Korean comment before the relevant block.
- Explain why the block exists, what equation/constraint it implements, and which units are used.
- Do not add empty line-by-line comments for self-evident assignments or simple dictionary plumbing.
- If a formula comes from the split spec, cite the section in the comment, for example `Spec 3.1.2 density update`.
- If the implementation intentionally approximates the spec, the comment must say so explicitly and name the caveat.

---
