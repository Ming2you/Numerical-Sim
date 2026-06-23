# Stackelberg-RL Controller Specification

## Purpose

This spec defines a reinforcement-learning extension of the current
leader-follower urban-freeway Stackelberg controller.

The goal is not to replace the existing MPC controller immediately. The goal is
to define a research-grade implementation path for a hierarchical multi-agent
RL controller that preserves the Stackelberg structure:

1. a leader learns aggregate coupling targets;
2. distributed followers learn target-conditioned local control policies;
3. the simulator realizes the joint control;
4. the leader learns from the global effect of follower responses.

The design is motivated by the Stackelberg-Nash Markov game formulation in:

```text
Zhong et al. (2023), "Can Reinforcement Learning Find Stackelberg-Nash
Equilibria in General-Sum Markov Games with Myopically Rational Followers?"
JMLR 24(2023).
```

The paper's theoretical setting assumes a leader, multiple myopically rational
followers, and Stackelberg-Nash equilibrium learning. This traffic-control
implementation should be presented as a practical approximation, not a direct
claim of the paper's theoretical guarantees.

## Non-Goals

- Do not remove or rewrite the existing MPC controllers.
- Do not implement a monolithic RL controller as the only proposed method.
- Do not collapse the Stackelberg hierarchy into a single shared global reward
  without explicitly treating it as a baseline or ablation.
- Do not claim exact Stackelberg-Nash convergence unless a separate theoretical
  proof is provided.
- Do not train unsafe policies without feasibility masks, action clipping, or a
  safe fallback controller.

## Core Formulation

### Markov Game Mapping

| Markov game term | Traffic-control mapping |
|---|---|
| State `s_t` | freeway density/speed, ramp queues, urban movement queues, storage, boundary state, demand forecast, time index |
| Leader action `a_L` | aggregate coupling targets such as `N_P_star`, `N_UF_star` |
| Follower actions `a_F_i` | follower-specific local controls only: freeway followers control RM/VSL, urban followers control signal green/offset |
| Leader reward `r_L` | negative global TTT/TTS-compatible cost plus throughput, terminal, storage, and spillback terms |
| Follower reward `r_F_i` | negative pure local TTT/TTS-compatible cost for the follower's assigned subnetwork |
| Transition | `MixedTrafficSimulator.step()` |
| Follower best response | approximated by distributed target-conditioned follower RL policies |

### Decision Order

At each control step:

```text
global/local state s_t is observed
leader policy selects aggregate target a_L
followers observe local state plus a_L
followers select local controls a_F_i
joint control is applied to the simulator
new state s_{t+1}, leader reward, and follower rewards are logged
```

This order is mandatory. It is what distinguishes Stackelberg-form RL from a
monolithic joint RL policy.

## Agents

### Follower Authority Boundaries

Follower RL agents must preserve the same ownership boundaries as the current
distributed MPC followers.

There are two main follower types, but they are instantiated as multiple
decentralized agents:

1. freeway follower;
2. urban follower.

Do not implement only one freeway follower and one urban follower. The required
agent instances are:

| Agent family | Required instances | Control status |
|---|---|---|
| Freeway segment followers | one RL agent per freeway segment/link | controlled |
| Urban intersection followers | one RL agent per controlled urban intersection/signal | controlled |
| Intersection E | no RL control actor | no-control / passive state only |

Each follower instance can only observe and control the links, ramps, movements,
and signals assigned to its own local subnetwork.

Authority rules:

| Follower type | Observes | Controls | Must not control |
|---|---|---|---|
| Freeway segment follower | assigned freeway segment/link, directly attached or feeding ramp queues, connected on-ramp/off-ramp coupling summaries, previous local RM/VSL, relevant leader target | VSL for the assigned segment/link and RM only for ramps assigned to that segment/link | urban signal green splits or offsets; RM/VSL for other freeway segments |
| Urban intersection follower | assigned intersection/signal movements, connected urban links/storage, local boundary/ramp coupling queues, previous local green/offset, relevant leader target | green split and offset for the assigned intersection/signal | freeway VSL or ramp metering; signal controls for other intersections |
| Intersection E passive node | E queues/storage/flows as plant state and metrics | no RL action | any direct control action |

If a shared neural network is used across multiple urban followers, this is
parameter sharing only. Execution must remain decentralized: each urban follower
receives only its own local observation and outputs only its own signal controls.

Likewise, freeway segment followers may share neural-network parameters, but
execution must remain decentralized: each segment follower receives only its
own local segment/ramp observation and outputs only its assigned VSL/RM controls.

Global network state may be used by the leader and by centralized-training
critics, but it must not be silently added to decentralized follower actors at
execution time.

Intersection E is passive/no-control in the RL design. However, E must not
become a hidden sink. E queues, storage, inflow/outflow, and vehicles must remain
included in plant metrics, leader global reward, and neighboring agents'
coupling summaries whenever they are physically connected.

### Follower Observation Locality

Follower actor observations must be strictly local.

For each follower instance, the observation builder must first construct an
ownership set:

```text
owned_links(agent)
owned_ramps(agent)
owned_movements(agent)
owned_signals(agent)
connected_coupling_links(agent)
```

The follower actor may only receive features derived from those sets plus the
current leader target and its own previous action.

#### Freeway segment follower locality

A freeway segment follower may observe only:

- its assigned freeway segment/link state;
- immediately adjacent freeway segment summaries if explicitly needed for VSL
  continuity or downstream congestion awareness;
- ramps physically attached to or assigned to that segment/link;
- on-ramp urban feeding queues connected to those assigned ramps;
- off-ramp receiving-pressure summaries connected to that segment/link;
- previous local VSL and local RM action;
- leader target values relevant to freeway/urban coupling.

It must not observe arbitrary urban intersections, remote freeway segments, or
global queue totals unless those are passed only to a centralized-training
critic and not to the decentralized actor.

#### Urban intersection follower locality

An urban intersection follower may observe only:

- movements controlled by the assigned intersection/signal;
- urban links entering or leaving the assigned intersection/signal;
- boundary links physically connected to the assigned intersection/signal;
- on-ramp or off-ramp links physically connected to the assigned
  intersection/signal;
- passive E-node queues/storage only if E is directly connected to that
  intersection/signal;
- previous local green and offset action;
- leader target values relevant to protected-network or coupling control.

It must not observe remote intersection queues, full freeway density vectors, or
global demand totals unless those are passed only to a centralized-training
critic and not to the decentralized actor.

#### Allowed exceptions

The following information may be shared with all follower actors:

- normalized leader target values such as `N_P_star` and `N_UF_star`;
- time-of-day or control-step phase features;
- static topology identifiers or masks needed by a shared neural-network policy.

These shared features must be explicitly documented and logged. They must not
include hidden global traffic state.

### Leader RL Agent

The leader represents the hierarchical coupling coordinator.

#### Observation

The leader observation should include normalized global features:

- protected urban accumulation;
- total freeway accumulation or density summary;
- ramp queue summary;
- on-ramp and off-ramp coupling queues;
- boundary inflow/outflow queue summary;
- storage/spillback indicators;
- recent throughput and completed vehicles;
- previous leader target;
- previous aggregate follower response;
- short demand forecast;
- time-of-day or control-step index features.

The leader observation may include compact follower summaries but should not
include full per-agent hidden training state.

#### Action

Initial action space:

```text
a_L = (N_P_star, N_UF_star)
```

Recommended scaling:

- train policies in normalized `[-1, 1]` action space;
- map to configured physical ranges in `leader.N_P_star_range` and
  `leader.N_UF_star_range`;
- clip and log all physical actions.

Possible future extensions:

- storage target;
- protected-network accumulation target;
- coupling priority weight;
- ramp release budget.

These extensions should not be added in the first implementation unless the
two-action version is already validated.

#### Reward

Use a clear cost/reward sign convention.

The leader cost is minimized conceptually, while the RL implementation maximizes
the negative of that cost.

Primary leader cost:

```text
C_L,t = global_step_ttt
        + density_excess_tts
        + urban_storage_halfcap_tts
        + optional_terminal_or_throughput_terms
        + optional_leader_smoothness_term
```

where:

```text
density_excess_tts
  = sum_{freeway segment s}
      segment_length_km_s
      * lanes_s
      * max(rho_s - rho_crit_s, 0)
      * control_interval_h

urban_storage_halfcap_tts
  = sum_{urban-side link or queue l}
      max(N_l - 0.5 * N_cap_l, 0)
      * control_interval_h
```

If a term is kept in vehicles instead of vehicle-hours, it must have an
explicit unit-conversion weight. The preferred first implementation is to keep
all terms in TTT/TTS-compatible vehicle-hours.

Primary leader RL reward:

```text
r_L,t = - C_L,t
```

Notes:

- The minimum required leader objective is:

```text
r_L,t =
  - global_step_ttt
  - sum_s L_s * lanes_s * max(rho_s - rho_crit_s, 0) * control_interval_h
  - sum_l max(N_l - 0.5 * N_cap_l, 0) * control_interval_h
```

- `rho_s` is freeway segment density.
- `rho_crit_s` is the corresponding critical density.
- `N_l` is urban-side link, queue, or storage occupancy included in the
  all-urban half-cap storage guard.
- `N_cap_l` is the storage capacity used for that link or queue. Boundary
  queues must use the configured accounting capacity, not clipping.
- Throughput and terminal terms may be added, but they must be reported
  separately so that improved throughput is not mistaken for hidden queueing.
- Follower rewards should not be blindly added to the leader reward.
- If follower welfare is included, use it only as a small regularizer:

```text
r_L_total = r_L + eta * sum_i r_F_i
```

where `eta` is explicitly logged and ablated. Large `eta` turns the problem
into cooperative MARL and weakens the Stackelberg interpretation.

### Follower RL Agents

Followers should correspond to the current distributed follower players, not a
single giant follower policy.

Initial follower set:

1. one freeway segment follower agent per freeway segment/link;
2. one urban intersection follower agent per controlled intersection/signal;
3. no control actor for intersection E.

Optional finer follower splits, such as per-ramp freeway agents, may be added
later. They must still obey the authority boundaries above and must not create
duplicate control authority over the same ramp, segment, or signal.

#### Freeway Segment Follower Agents

Observation:

- assigned freeway segment/link density;
- assigned freeway segment/link speed if available;
- directly attached or assigned ramp queues;
- directly attached or assigned ramp demands;
- connected on-ramp urban feeding queue summaries;
- connected off-ramp receiving-pressure summaries if available;
- previous local ramp metering rate if the segment has an assigned ramp;
- previous local VSL value;
- leader target `N_UF_star`;
- relevant part of `N_P_star` if it affects coupling.

Action:

- local VSL or VSL delta for the assigned freeway segment/link;
- local ramp metering rate or normalized ramp release factor only if a ramp is
  assigned to that segment/link.

The freeway follower must not output urban green splits or offsets.
It must also not output VSL or RM for other freeway segments.

Reward:

```text
r_F_freeway = - freeway_local_ttt
```

For the main Stackelberg-RL method, follower reward should be pure local
TTT/TTS-compatible cost. Spillback, storage, and smoothness should be enforced
through feasibility masks, action projection, diagnostics, or explicit ablation
variants rather than silently mixed into the main follower reward.

#### Urban Intersection Follower Agents

Observation:

- movement queues assigned to the signal/intersection player;
- link storage on urban links connected to that player;
- boundary inflow/outflow queues connected to that player;
- on-ramp or off-ramp coupling queues connected to that player;
- previous green split;
- previous offset;
- leader target `N_P_star`;
- relevant part of `N_UF_star` if the signal feeds a ramp.

Action:

- green split for assigned signal phases, preferably normalized and mapped to
  feasible green bounds;
- offset delta or offset phase choice for assigned signal only;
- optional local service-priority action if direct green output is too hard.

The urban follower must not output freeway VSL or ramp metering.
It must also not output green split or offset for other intersections.

Intersection E is excluded from this controlled urban follower set. If E appears
in the topology, it is represented as a passive plant node whose queues/storage
affect rewards and observations of connected controlled agents, but no E policy
is trained and no E action is emitted.

Reward:

```text
r_F_urban_i = - local_urban_ttt_i
```

For the main Stackelberg-RL method, urban follower reward should be pure local
TTT/TTS-compatible cost over the links, queues, and movements assigned to that
intersection follower. Additional storage, spillback, or smoothness reward
terms should be treated as ablations unless explicitly approved.

### Myopic Follower Interpretation

To stay close to the referenced paper, follower policies should approximate
myopic or short-horizon best responses to the leader target.

Acceptable implementations:

- follower discount `gamma_F = 0` for strictly one-step reward;
- short follower horizon with small `gamma_F`;
- recurrent or history features only if needed for partial observability.

The leader may use a longer discount or episodic return:

```text
gamma_L >= gamma_F
```

This two-timescale design is central to the Stackelberg interpretation.

### Future Cost Approximation: RL vs MPC

MPC explicitly looks ahead by rolling out a model over a finite horizon at each
control step. RL does not need to perform that online rollout during inference,
but it must still account for future cost through the learned value function.

Required interpretation:

```text
MPC:
  current state + forecast -> online H-step rollout -> action

RL:
  current state + forecast features -> policy/value function
  where the value function approximates expected future cumulative cost
```

Therefore, the leader must not be trained as a purely one-step myopic policy.
The leader should optimize a discounted or episodic return:

```text
J_L = E[sum_t gamma_L^t r_L,t]
```

with:

```text
gamma_L > gamma_F
```

and `gamma_L` should normally be near long-horizon control values such as
`0.95` to `0.995`, subject to empirical validation.

The leader observation should include demand forecast features, because RL does
not automatically know future demand unless it is provided through state,
history, or experience. At minimum, include short forecast summaries for the
same demand horizon used by the MPC experiments.

If a proposed RL variant uses `gamma_L = 0`, it is a myopic leader ablation, not
the main Stackelberg-RL controller.

### Follower Nash Response Requirement

For a fixed leader target `a_L`, the distributed follower policies must be
interpreted as players in the follower subgame induced by that leader target.
The intended follower solution concept is an approximate Nash equilibrium of
that induced subgame.

In words:

```text
given leader target a_L,
given other followers' policies pi_F_-i,
each follower i should have no profitable unilateral local deviation
within its own action authority.
```

Equivalently, the trained follower response should satisfy:

```text
J_i(pi_F_i, pi_F_-i | a_L)
  >= max_{pi'_F_i in local_policy_class_i}
     J_i(pi'_F_i, pi_F_-i | a_L) - epsilon_Nash
```

where `J_i` is follower `i`'s local TTS-compatible return or myopic reward.

This requirement is what separates Stackelberg-RL from ordinary hierarchical
control. The leader is not learning against arbitrary simultaneous follower
actions; it is learning against an approximate distributed follower Nash
response.

Exact Nash convergence is not required for the first implementation, but the
implementation must:

- train followers as local players with their own rewards;
- condition follower policies on the leader target;
- avoid replacing follower rewards with a single shared global reward in the
  main Stackelberg-RL method;
- estimate and log an approximate follower Nash residual / exploitability
  metric during evaluation.

Suggested approximate Nash residual:

```text
epsilon_Nash_hat
  = max_i [
      best_unilateral_local_return_i
      - realized_return_i
    ]_+
```

The unilateral local deviation set can be constructed from:

- small continuous perturbations of the follower RL action;
- the current MPC local candidate set for that follower;
- safe no-control / previous-control guard candidates;
- a short local rollout with other follower actions fixed.

If `epsilon_Nash_hat` is large, the result should be described as a
hierarchical MARL policy, not a Stackelberg-Nash approximation.

## Training Design

### Training Phases

Implement training in phases.

#### Phase 0: Dataset and Environment Wrapper

Create a Gymnasium-like environment wrapper around the current simulator.

Required outputs per step:

- normalized global observation;
- local follower observations;
- leader action;
- follower actions;
- raw physical control action;
- leader reward;
- follower rewards;
- next observations;
- done/truncation flags;
- safety and feasibility diagnostics.

Use existing scenario seeds and demand profiles.

#### Phase 1: Follower Pretraining

Train follower agents with scripted or sampled leader targets.

Purpose:

- learn stable local target-conditioned responses;
- avoid training the leader against random unstable followers;
- validate that distributed follower RL can reproduce or approximate MPC/PFO
  follower behavior.

Possible data sources:

- current PFO outputs;
- current P-Stack follower responses;
- safe random perturbations around no-control and previous-control candidates;
- centralized or MPC outputs as optional imitation targets.

Recommended objectives:

- RL reward optimization;
- optional behavior cloning warm start from MPC actions;
- optional supervised value/reward prediction for diagnostics.

#### Phase 2: Leader Training With Followers Frozen

Freeze follower policies or update them very slowly.

Train the leader to choose `N_P_star` and `N_UF_star` while followers respond
with learned target-conditioned policies.

This is the first true Stackelberg-RL experiment.

#### Phase 3: Two-Timescale Joint Fine-Tuning

Allow follower updates more frequently than leader updates.

Example:

```text
for each leader update:
    run M environment rollouts
    update follower policies every rollout or mini-batch
    update leader policy once after follower responses stabilize
```

The exact update ratio must be logged.

#### Phase 4: Safe Evaluation

Evaluate learned policies without exploration noise.

Always compare against:

- no-control;
- WU controller;
- PFO MPC;
- P-Stack MPC;
- centralized MPC if available;
- monolithic RL baseline.

### Algorithm Choices

The paper proposes optimistic/pessimistic LSVI-SNE variants. Directly applying
that algorithm to this simulator is difficult because the traffic state/action
spaces are continuous and high-dimensional.

Recommended practical approximations:

1. discrete pilot:
   - discretize leader targets and follower actions;
   - implement fitted Q or LSVI-style value learning;
   - useful for validating the game formulation.

2. deep actor-critic implementation:
   - leader: SAC, TD3, PPO, or fitted actor-critic;
   - followers: independent or centralized-training decentralized-execution
     actor-critic;
   - action masks and projection enforce feasibility.

3. offline-to-online training:
   - offline pretrain from existing controller logs;
   - simulator fine-tune with exploration;
   - final deterministic evaluation.

The first implementation should prioritize a stable research prototype over
exact theoretical replication.

### DDQN-Ready Discrete Action Guidance

Double Deep Q-Learning is appropriate only when each learned action space is
kept small enough to enumerate.

Recommended DDQN use:

- Stackelberg-RL leader:
  - discretize `N_P_star` and `N_UF_star` into a small factorized or flattened
    target set;
  - use DDQN as an initial leader policy learner.
- Stackelberg-RL freeway segment followers:
  - each segment agent chooses from a small local VSL/RM action set;
  - actions must affect only that segment and its assigned ramp, if any.
- Stackelberg-RL urban intersection followers:
  - each intersection agent chooses from a small local green/offset action set;
  - actions must affect only that intersection.
- Full Distributed RL:
  - use the same per-segment/per-intersection DDQN-ready local action spaces;
  - train local agents toward an approximate distributed Nash response.

DDQN is not recommended for a naive Full Centralized RL baseline that flattens
all RM, VSL, green, and offset combinations into one joint action. The joint
action count grows combinatorially and will quickly become intractable.

Acceptable Full Centralized RL options:

1. factorized centralized Q-heads:
   - one shared global encoder;
   - separate discrete heads for VSL, RM, green, and offset groups;
   - log that this is a factorized approximation rather than a true full joint
     Q-table;
2. autoregressive discrete policy:
   - choose control groups sequentially from the global state;
   - still treat this as centralized because the actor observes global state;
3. continuous actor-critic baseline:
   - use SAC/TD3/PPO-style continuous or bounded actions;
   - project outputs to physical feasible controls.

The first coding milestone should not implement full neural DDQN training.
It should implement DDQN-ready action-space definitions and mappings:

```text
discrete action index
-> local normalized action
-> projected physical ControlAction field
```

This keeps the environment and action interface compatible with DDQN while
allowing safe random-policy and scripted-policy smoke tests before training.

## Baselines

The RL study must include baselines that show why the hierarchy matters.

### Required Four-Way Comparison

The RL study should compare four model families:

| Method | Role |
|---|---|
| Full Centralized RL | monolithic global-state/global-action RL baseline |
| Full Distributed RL | decentralized local-agent RL baseline with follower Nash response |
| Stackelberg-RL | proposed leader-target plus distributed follower Nash-response model |
| Existing MPC PFO/P-Stack | deterministic reference controllers and online-computation benchmarks |

The first coding plan for RL should include explicit specs for Full Centralized
RL and Full Distributed RL, because they are not merely optional baselines; they
define what the proposed Stackelberg decomposition is being compared against.

### Full Centralized RL Baseline

One policy observes the global state and directly outputs all controls:

```text
RM + VSL + green + offset
```

Purpose:

- tests whether Stackelberg decomposition improves sample efficiency,
  stability, and interpretability relative to a single large policy.

#### Centralized observation

The centralized actor may observe the full global traffic state:

- all freeway segment densities/speeds;
- all ramp queues and ramp demands;
- all urban movement queues;
- all urban link storage values;
- all boundary inflow/outflow queues;
- E-node queues/storage/flows;
- previous full control action;
- full demand forecast summary;
- time-of-day or control-step features.

#### Centralized action

The centralized actor directly outputs all controlled variables:

- VSL for all controlled freeway segments;
- ramp metering for all controlled ramps;
- green splits for all controlled urban intersections except passive E;
- offsets for all controlled urban intersections except passive E.

Intersection E remains no-control/passive. The centralized actor must not emit
an E control action.

#### Centralized reward

Use global network reward:

```text
r_C = - global_step_ttt
      + throughput_weight * completed_or_throughput_reward
      - terminal_weight * terminal_vehicles
      - spillback_weight * spillback_violation
      - storage_weight * storage_excess
      - smoothness_weight * full_control_change
```

This baseline is expected to have the largest action dimension and the hardest
credit-assignment problem. It is not a Stackelberg model.

### Full Distributed RL Baseline

Segment and intersection agents learn local controls without a leader target.

This baseline must use the same decentralized agent ownership as
Stackelberg-RL:

- one freeway segment agent per freeway segment/link;
- one urban intersection agent per controlled intersection/signal;
- no control actor for passive intersection E.

There is no leader policy and no `N_P_star` or `N_UF_star` conditioning.

Purpose:

- isolates the value of `N_P_star` and `N_UF_star` coupling targets.

#### Distributed observation

Each agent observes only its local ownership set:

- freeway segment agents observe their assigned segment/link, assigned ramp
  state, connected ramp/urban coupling summaries, previous local VSL/RM;
- urban intersection agents observe their assigned intersection movements,
  connected urban links/storage, connected boundary/ramp queues, previous local
  green/offset;
- passive E is observed only by physically connected neighboring agents as a
  local coupling summary.

No distributed actor may observe full global state at execution time.
Centralized-training critics may use global state, but actors must remain local.

#### Distributed action

Each agent outputs only its owned local action:

- freeway segment agent: assigned VSL and assigned ramp metering if any;
- urban intersection agent: assigned green split and assigned offset;
- passive E: no action.

#### Distributed reward

Each agent receives its own local TTS-compatible reward:

```text
r_i = - local_tts_i
      - local_storage_weight * local_storage_excess_i
      - local_spillback_weight * local_spillback_i
      - smoothness_weight * local_control_change_i
```

Do not replace the main Full Distributed RL baseline with a shared global
reward. A shared-global-reward version may be added as a cooperative MARL
ablation, but it answers a different question.

#### Distributed Nash response requirement

Full Distributed RL is also a game among local agents. It should seek an
approximate Nash equilibrium among the local agents, but unlike Stackelberg-RL
there is no leader-induced target.

For evaluation, log the same approximate Nash residual:

```text
epsilon_Nash_hat_distributed
  = max_i [
      best_unilateral_local_return_i
      - realized_return_i
    ]_+
```

The unilateral local deviation set should use the same construction as
Stackelberg-RL, but without conditioning on `N_P_star` or `N_UF_star`.

This comparison tests whether leader coupling targets improve over a purely
decentralized Nash-response controller.

### Hierarchical Cooperative RL

Leader/follower architecture exists, but all agents share global reward.

Purpose:

- tests whether improvement is due to hierarchy alone or specifically due to
  Stackelberg-style asymmetric rewards.

### Stackelberg-RL

Leader uses global reward. Followers use local rewards and condition on leader
targets.

Purpose:

- main proposed RL extension.

## Evaluation Metrics

### Traffic Performance

Report:

- total TTT/TTS;
- total delay;
- average travel time;
- throughput;
- completed vehicles;
- terminal vehicles;
- freeway TTT;
- urban TTT;
- ramp queue TTS;
- boundary/storage/spillback indicators;
- action smoothness;
- constraint violations.

### Learning Performance

Report:

- episodes to reach a TTT or reward threshold;
- sample efficiency at fixed simulation budgets;
- training wall-clock time;
- reward curve stability;
- seed variance;
- catastrophic episode rate;
- scenario generalization.

Important:

Follower local reward convergence is not enough. Always pair it with global
network performance convergence.

### Online Computation

Report separately:

- training wall-clock time;
- inference time per control step;
- real-time ratio:

```text
real_time_ratio = decision_time / control_interval
```

Expected research claim:

- MPC has no training cost but high online decision cost;
- RL has high training cost but low inference cost;
- Stackelberg-RL should be compared on both dimensions.

## Logging Requirements

Every RL run must log:

- run seed;
- scenario;
- episode index;
- step index;
- raw simulator state summary;
- normalized observations;
- leader action in normalized and physical units;
- follower actions in normalized and physical units;
- final applied `ControlAction`;
- rewards by agent;
- global traffic metrics;
- local traffic metrics;
- safety masks and action projections;
- policy version/checkpoint id;
- training losses and value estimates when available.

The log format should support post-hoc reconstruction of:

```text
leader target -> follower response -> plant outcome
```

## Safety and Feasibility

All RL actions must pass through the same physical bounds used by the MPC
controllers.

Required safeguards:

- ramp metering bounds;
- VSL bounds and quantization if required;
- green min/max constraints;
- cycle/effective green consistency;
- offset wrapping;
- storage/spillback action masks where possible;
- fallback to no-control or MPC previous-control guard if action projection
  fails.

Safety diagnostics must distinguish:

- raw policy output;
- clipped/projected feasible action;
- fallback action.

## Expected Implementation Modules

Proposed module layout:

```text
src/rl/
  __init__.py
  env.py
  observations.py
  rewards.py
  action_space.py
  agents.py
  replay.py
  train_followers.py
  train_leader.py
  train_stackelberg.py
  evaluate.py
```

Possible experiment entry points:

```text
src/experiments/rl_stackelberg_comparison.py
src/experiments/rl_training_diagnostics.py
```

Do not add these modules until the implementation task explicitly begins.

## First Implementation Milestone

The first coding milestone should be minimal:

1. create environment wrapper;
2. compute observations and rewards;
3. support random/safe policy rollout;
4. log leader/follower observations, actions, rewards, and plant metrics;
5. verify no-control and random-safe rollouts finish without simulator errors.

No neural-network training should start before this milestone passes.

## Second Implementation Milestone

Follower-only RL pilot:

1. freeze leader target to fixed or sampled values;
2. train freeway and urban follower agents;
3. compare learned follower response against PFO/MPC follower behavior;
4. report local rewards and global metrics.

## Third Implementation Milestone

Leader-RL pilot:

1. freeze trained follower policies;
2. train leader policy over `N_P_star` and `N_UF_star`;
3. evaluate against current P-Stack continuous/grid leader;
4. compare online inference time.

## Fourth Implementation Milestone

Two-timescale Stackelberg-RL:

1. update followers more frequently than leader;
2. log update ratios;
3. compare against monolithic RL and independent distributed RL;
4. report convergence speed, sample efficiency, traffic performance, and
   inference cost.

## Acceptance Criteria

An RL implementation should not be considered successful unless:

- rollouts are reproducible by seed;
- all actions satisfy physical constraints after projection;
- no-control and safe random policies complete all target scenarios;
- learned policies are evaluated without exploration noise;
- inference time is clearly lower than MPC P-Stack decision time;
- traffic performance is better than no-control in congested scenarios;
- comparison includes monolithic RL and distributed-follower baselines;
- logs are sufficient to reconstruct leader target, follower response, and
  plant outcome.

## Open Questions

These must be resolved experimentally:

1. Is `gamma_F = 0` too myopic for stable signal/ramp control?
2. Should followers use one policy per signal or a shared parameterized policy?
3. Should freeway RM and VSL be one follower or separate followers?
4. How much follower reward, if any, should regularize leader reward?
5. Does Stackelberg-RL converge faster than monolithic RL?
6. Does Stackelberg-RL generalize better across demand scenarios?
7. Does learned leader policy reproduce useful `N_P_star` and `N_UF_star`
   patterns observed in MPC P-Stack?
