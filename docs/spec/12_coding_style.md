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

---
