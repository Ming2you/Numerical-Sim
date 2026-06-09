# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 1. Background and Control Concept

The target method is an MPC-based Stackelberg game controller for a mixed urban-freeway network.

The upper-level **leader** decides coordination variables:

- `N_P_star`: target net inflow to the protected urban network
- `N_UF_star`: target total metering rate from urban roads to the freeway

Given the leader decision, the lower-level **followers** solve decentralized control problems:

- Freeway follower:
  - ramp metering rate for each ramp
  - VSL for each freeway link or segment
- Urban follower:
  - inflow-outflow allocation
  - movement-level green time allocation
  - signal offset adjustment

The follower layer should approximate a Nash-equilibrium-like response under the selected leader decision. The leader evaluates the follower response using system-level performance, including TTT/TTS and target-exceedance penalties, then selects the best leader decision.

The implementation should treat the controller as a closed-loop MPC controller. At each control interval:

1. Read current traffic state.
2. Predict traffic evolution over the prediction horizon.
3. Enumerate or optimize leader candidates.
4. For each leader candidate, solve follower responses.
5. Choose the leader candidate that minimizes the leader objective.
6. Apply only the first-step control actions to the simulator.
7. Advance the simulation.
8. Log state, control, objective, and diagnostic metrics.

---
