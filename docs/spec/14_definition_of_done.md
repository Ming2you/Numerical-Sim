# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 14. Definition of Done

The implementation is complete only when all of the following are true:

- The proposed controller can run closed-loop simulation end to end.
- Baseline and proposed simulations use the same scenario, seed, horizon, and demand.
- Ramp metering, VSL, green time, offset, and inflow-outflow allocation are all logged as time series.
- The evaluation computes total TTT/TTS and improvement rate.
- The 8% improvement criterion is checked automatically.
- Boundary queue balancing is evaluated separately from total TTT/TTS.
- If the first run fails, the diagnosis and auto-tuning loop reruns the simulation.
- Every attempt is saved and visible in the final report.
- Unit tests and the closed-loop smoke test pass.
- The final report clearly states `PASS` or `FAIL`.

---
