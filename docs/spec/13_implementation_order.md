# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 13. Minimal Implementation Order

Implement in this order.

### Step 1. Core data structures

Create:

```text
TrafficState
ControlAction
NetworkConfig
ControllerConfig
EvaluationResult
DiagnosticResult
```

### Step 2. Baseline simulator

Run the network without proposed control and save TTT/TTS, queues, densities, speeds, and signal states.

### Step 3. Freeway model and freeway follower

Implement METANET update, ramp queue update, ramp metering, and VSL.

### Step 4. Urban queue model and urban follower

Implement horizontal queue dynamics, green time allocation, offset adjustment, and boundary queue balance metrics.

### Step 5. Stackelberg MPC loop

Connect leader, follower Nash solver, prediction, and first-step control application.

### Step 6. Evaluation and report generation

Implement metrics, diagnostics, and report export.

### Step 7. Auto-tuning and rerun logic

Implement the self-improvement loop with saved attempt histories.

### Step 8. Ablation experiments

Run component removal cases for diagnosis.

---
