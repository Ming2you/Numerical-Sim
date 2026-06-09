# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 0. Purpose

Implement an end-to-end simulation and control framework for the proposed MPC-based Stackelberg game controller.

The implementation must include not only the controller logic, but also a closed-loop simulation validation pipeline that checks whether the proposed controls work as intended:

- ramp metering
- variable speed limit (VSL)
- signal offset control
- movement-level green time allocation
- inflow-outflow allocation for boundary queue balancing

The system must compare the proposed controller against a baseline simulation. The proposed controller passes only when the target performance improvement is at least **8%** on the main system-level metric, unless a different metric is explicitly configured.

If the controller does not pass, the code must diagnose likely causes, adjust controller/configuration parameters, rerun the simulation, and produce a final report showing all attempts.

---
