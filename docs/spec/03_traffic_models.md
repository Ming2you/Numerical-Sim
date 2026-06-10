# Codex Implementation Spec: MPC-based Stackelberg Game Controller for Integrated Urban-Freeway Traffic Control

## 3. Traffic Models

### 3.0 Common notation and unit convention

Use separate time steps for the freeway, urban, and controller layers.

```text
T_f_sec: freeway simulation time step [s]
T_u_sec: urban simulation time step [s]
T_c_sec: controller/MPC sampling interval [s]
R_fu = T_f_sec / T_u_sec
```

Mandatory implementation rules:

```text
T_f_sec % T_u_sec == 0
T_c_sec % T_f_sec == 0
R_fu is an integer
```

Internally, use consistent units. If density is in `veh/km/lane`, speed is in `km/h`, and flow is in `veh/h`, then convert simulation time steps before using them in conservation equations:

```text
T_f_h = T_f_sec / 3600
T_u_h = T_u_sec / 3600
T_c_h = T_c_sec / 3600
```

All vehicle-count variables such as `x`, `w`, `m_arr`, `m_dep`, and `S` are in vehicles. All flow-rate variables such as `q`, `d`, and `Q_cap` are in vehicles per hour unless explicitly configured otherwise.

Do not mix "vehicles per time step" and "vehicles per hour" in the same equation. Convert explicitly at every model boundary.

---

### 3.1 Freeway model: METANET-style dynamics

Implement a METANET-style freeway model with the following core state variables:

- `rho[m, i]`: density of segment `i` on freeway link `m` `[veh/km/lane]`
- `v[m, i]`: space-mean speed of segment `i` on freeway link `m` `[km/h]`
- `q[m, i]`: outflow of segment `i` on freeway link `m` `[veh/h]`
- `w[o]`: queue length at freeway origin or on-ramp `o` `[veh]`

Use one-based segment notation in the mathematical specification:

```text
i = 1, ..., N_seg[m]
q[m, 0] is the upstream boundary inflow to link m
rho[m, N_seg[m] + 1] is the virtual downstream density used in the speed equation
v[m, 0] is the virtual upstream entering speed used in the speed equation
```

In code, zero-based arrays are allowed, but the boundary variables must be handled explicitly.

#### 3.1.1 Segment flow

```text
q[m,i](k) = rho[m,i](k) * v[m,i](k) * lanes[m]
```

Apply non-negativity projection after numerical updates:

```text
rho[m,i] = max(rho[m,i], 0)
v[m,i]   = max(v[m,i], v_min)
q[m,i]   = max(q[m,i], 0)
```

#### 3.1.2 Density update

For each segment:

```text
rho[m,i](k+1) = rho[m,i](k)
                + T_f_h / (L[m] * lanes[m])
                  * (q[m,i-1](k) - q[m,i](k))
```

where:

```text
L[m]: segment length of link m [km]
lanes[m]: number of lanes on link m
```

This is a conservation equation. Do not add or remove vehicles inside a link except through explicit boundary, ramp, or node flows.

#### 3.1.2a Off-ramp spill-back capacity drop

When an off-ramp storage link is occupied, represent spill-back as an effective lane-number reduction on the upstream freeway link's last segment. Let:

```text
N[m,i](k)          = rho[m,i](k) * L[m] * lambda_prev[m,i](k)  # vehicles
n_off[m,d](k)      = C[m,d] - available_storage[m,d](k)
lambda_m           = nominal lane number
delta_lambda       = configured lane reduction, possibly fractional
gamma[m,d], b_cd   = spill-back shape parameters
```

Use a generalized Wu-style effective lane number:

```text
lambda_eff[m,last](k)
    = lambda_m
      - delta_lambda
        * (1 - exp( -(1 / b_cd) * (n_off[m,d](k) / (gamma[m,d] * C[m,d])) ** b_cd ))
```

with exact boundary behaviour:

```text
n_off = 0      -> lambda_eff = lambda_m
n_off = C      -> lambda_eff = lambda_m - delta_lambda
```

For links without active off-ramp spill-back, `lambda_eff = lambda_m`.

Because `rho` is a per-lane density, changing `lambda_eff` must preserve vehicles. Do not update density by only changing the denominator in the original conservation equation. Instead use segment vehicle count as the conserved quantity:

```text
N_current(k)       = rho_stored(k) * L * lambda_prev(k)
rho_for_flow(k)    = N_current(k) / (L * lambda_eff(k))
q(k)               = rho_for_flow(k) * v(k) * lambda_eff(k)
N_next(k+1)        = N_current(k) + T_f_h * (q_in(k) - q_out(k))
rho_next(k+1)      = N_next(k+1) / (L * lambda_eff(k))
```

The speed equation must also be evaluated with the lane-corrected density:

```text
V_no_vsl(k)      = V_no_vsl(rho_for_flow(k))
V_eff(k)         = V_eff(rho_for_flow(k), vsl(k))
anticipation     uses rho_for_flow[m,i+1](k) - rho_for_flow[m,i](k)
```

This is the intended mechanism:

```text
lambda_eff decreases
-> rho_for_flow increases for the same N
-> desired speed and anticipation terms reduce speed
-> q decreases through speed, not through an ad-hoc capacity cap
```

Freeway TTT must be counted from vehicles:

```text
TTT_freeway += sum_i N_next[m,i](k+1) * T_f_h
```

When lane count changes, `N_next` is the conserved state. Do not upper-project
`N_next` only because `lambda_eff` decreased; otherwise vehicles disappear at the
capacity-drop boundary. If the derived `rho_next` exceeds `rho_max`, keep the
vehicles and report the density exceedance as congestion diagnostics.

#### 3.1.3 Desired speed without VSL

```text
V_no_vsl[m,i](k) = v_free[m]
                  * exp(
                      -(1 / a[m])
                      * (rho[m,i](k) / rho_crit[m]) ** a[m]
                    )
```

where:

```text
v_free[m]: free-flow speed of link m [km/h]
rho_crit[m]: critical density of link m [veh/km/lane]
a[m]: METANET shape parameter
```

#### 3.1.4 VSL effect

VSL must not be implemented as a direct increase in capacity or critical density. In the Van den Berg/Hegyi-style METANET implementation, VSL modifies the effective desired speed.

```text
if VSL is active on segment (m,i):
    V_eff[m,i](k) = min(
        V_no_vsl[m,i](k),
        (1 + alpha_vsl[m,i]) * vsl[m,i](k)
    )
else:
    V_eff[m,i](k) = V_no_vsl[m,i](k)
```

where:

```text
vsl[m,i](k): posted speed limit [km/h]
alpha_vsl[m,i]: compliance parameter
```

Typical interpretation:

```text
alpha_vsl < 0: strict enforcement, drivers drive below the displayed limit on average
alpha_vsl = 0: exact compliance
alpha_vsl > 0: weak enforcement, drivers exceed the displayed limit on average
```

Default VSL action set:

```text
vsl[m,i](k) in {50, 60, 70, 80, 90, 100}  # km/h
```

A link-level VSL is allowed as an implementation simplification:

```text
vsl[m,i](k) = vsl_link[m](k) for all controlled segments i in link m
```

If a link-level VSL is used, document this explicitly in the experiment report.

#### 3.1.5 Speed update

Implement the METANET speed update as the sum of the relaxation, convection, and anticipation terms:

```text
v[m,i](k+1) = v[m,i](k)
              + T_f_h / tau[m] * (V_eff[m,i](k) - v[m,i](k))
              + T_f_h / L[m] * v[m,i](k) * (v[m,i-1](k) - v[m,i](k))
              - nu[m] * T_f_h / (tau[m] * L[m])
                * (rho[m,i+1](k) - rho[m,i](k))
                / (rho[m,i](k) + kappa[m])
              + optional_merging_term[m,i](k)
              + optional_weaving_or_lane_drop_term[m,i](k)
```

where:

```text
tau[m], nu[m], kappa[m]: METANET parameters
v[m,i-1]: upstream speed or virtual entering speed
rho[m,i+1]: downstream density or virtual downstream density
```

Only include `optional_merging_term` or `optional_weaving_or_lane_drop_term` when their formulas and parameters are explicitly configured. Do not invent uncalibrated speed-drop terms by default.

#### 3.1.6 Node coupling between freeway links

For a node `p`, let:

```text
I_p: set of freeway links entering node p
O_p: set of freeway links leaving node p
last(mu): last segment index of entering link mu
beta[p,m]: turning rate from node p to leaving link m
```

Total entering flow:

```text
Q_tot[p](k) = sum_{mu in I_p} q[mu,last(mu)](k)
```

Flow into leaving link `m`:

```text
q[m,0](k) = beta[p,m](k) * Q_tot[p](k),  for each m in O_p
```

If node `p` has multiple leaving links, use a virtual downstream density for the last segment of each entering link. A practical implementation is:

```text
rho_virtual_downstream[mu](k)
    = sum_{m in O_p} weight[p,m](k) * rho[m,1](k)
```

where the default weight is based on turning rates or receiving flows. Log the chosen weighting rule.

If node `p` has multiple entering links, use a flow-weighted virtual entering speed for each leaving link:

```text
v[m,0](k)
    = sum_{mu in I_p} v[mu,last(mu)](k) * q[mu,last(mu)](k)
      / max(sum_{mu in I_p} q[mu,last(mu)](k), eps)
```

---

### 3.2 Ramp queue and ramp metering

For each freeway origin or on-ramp `o` connected to downstream freeway link `m`, implement the queue conservation equation:

```text
w[o](k+1) = w[o](k) + T_f_h * (d[o](k) - q_ramp[o](k))
```

where:

```text
d[o](k): demand arriving at ramp/origin o [veh/h]
q_ramp[o](k): actual flow from ramp/origin o to freeway [veh/h]
w[o](k): ramp/origin queue [veh]
```

The no-metering ramp outflow must be constrained by available vehicles, ramp capacity, and downstream freeway receiving condition:

```text
available_vehicle_flow[o](k) = d[o](k) + w[o](k) / T_f_h

receiving_factor[m](k)
    = clip(
        (rho_max[m] - rho[m,1](k)) / max(rho_max[m] - rho_crit[m], eps),
        0,
        1
      )

q_ramp_no_meter[o](k)
    = min(
        available_vehicle_flow[o](k),
        q_ramp_max[o],
        Q_cap_downstream[m] * receiving_factor[m](k)
      )
```

Ramp metering limits this outflow:

```text
q_ramp[o](k) = min(q_ramp_no_meter[o](k), b[o](k) * q_ramp_max[o])
```

where:

```text
0 <= b[o](k) <= 1
```

Mandatory constraints:

```text
0 <= q_ramp[o](k) <= q_ramp_max[o]
q_ramp[o](k) <= d[o](k) + w[o](k) / T_f_h
q_ramp[o](k) <= Q_cap_downstream[m] * receiving_factor[m](k)
0 <= w[o](k) <= w_max[o]
```

The Stackelberg leader target must be handled with explicit units. Configure one of the following:

```yaml
leader:
  N_UF_star_unit: "veh_per_hour"       # recommended
  # or
  N_UF_star_unit: "veh_per_control_interval"
```

If `N_UF_star_unit = veh_per_control_interval`, convert internally:

```text
N_UF_star_flow(k) = N_UF_star(k) / T_c_h
```

The freeway follower should satisfy:

```text
abs(sum_o q_ramp[o](k) - N_UF_star_flow(k)) <= eps_F
```

If infeasible, project to the nearest feasible ramp-flow vector and log:

```text
metering_target_infeasible = true
metering_tracking_residual = abs(sum_o q_ramp[o] - N_UF_star_flow)
```

---

### 3.3 Urban model: horizontal queue and turning-direction-dependent queues

Implement a queue-based urban model with horizontal queues and movement-level queues.

Core state variables:

```text
x[o,s,d](k): queue length of vehicles that came from origin/upstream node o,
             are waiting at intersection s, and intend to go to downstream destination d [veh]

m_arr[o,s,d](k): vehicles arriving at the tail of queue x[o,s,d] during urban step k [veh]

m_dep_int[o,s,d](k): intended departure from queue x[o,s,d] during urban step k before storage allocation [veh]

m_dep[o,s,d](k): actual departure from queue x[o,s,d] after signal and storage constraints [veh]

S[u,v](k): available storage/free space on directed urban link l_{u,v} [veh]

beta[o,s,d](k): turning ratio from upstream origin o through intersection s to destination d

g[o,s,d](k): binary green indicator, or effective green fraction if configured
```

Use `S[u,v]`, not only `S[s,d]`, because receiving space belongs to a directed link. For example, the available space of the link from intersection `s` to destination/downstream node `d` is `S[s,d]`, while the available space of an off-ramp link from ramp `r` to intersection `s` is `S[r,s]`.

#### 3.3.1 Intended movement departure

If `g` is implemented as a binary green/red signal:

```text
if g[o,s,d](k) == 0:
    m_dep_int[o,s,d](k) = 0
else:
    m_dep_int[o,s,d](k)
        = min(
            x[o,s,d](k) + m_arr[o,s,d](k),
            T_u_h * Q_cap[o,s,d]
          )
```

If `g` is implemented as an effective green fraction in `[0, 1]`:

```text
m_dep_int[o,s,d](k)
    = min(
        x[o,s,d](k) + m_arr[o,s,d](k),
        T_u_h * g[o,s,d](k) * Q_cap[o,s,d]
      )
```

Do not use both binary `g` and green fraction `g` in the same model without naming them separately.

#### 3.3.2 Receiving-space allocation and blocking

For each receiving link `l_{s,d}`, collect all upstream movements trying to enter it:

```text
M(s,d) = {(o,s,d) for all upstream origins o}
D_int_total[s,d](k) = sum_{(o,s,d) in M(s,d)} m_dep_int[o,s,d](k)
```

If receiving space is sufficient:

```text
if D_int_total[s,d](k) <= S[s,d](k):
    m_dep[o,s,d](k) = m_dep_int[o,s,d](k) for all (o,s,d)
```

If receiving space is insufficient:

```text
sum_{(o,s,d) in M(s,d)} m_dep[o,s,d](k) <= S[s,d](k)
0 <= m_dep[o,s,d](k) <= m_dep_int[o,s,d](k)
```

Use a configurable allocation rule:

```yaml
urban_model:
  receiving_space_rule: "proportional"  # proportional, equal_split, or main_priority
```

Recommended default:

```text
proportional allocation:
    m_dep[o,s,d](k)
        = S[s,d](k) * m_dep_int[o,s,d](k) / max(D_int_total[s,d](k), eps)
```

For `equal_split`, split available storage equally among active competing movements and redistribute unused residual capacity. For `main_priority`, allocate to configured priority movements first, then distribute the remaining storage according to the secondary rule.

#### 3.3.3 Queue update

```text
x[o,s,d](k+1) = x[o,s,d](k) + m_arr[o,s,d](k) - m_dep[o,s,d](k)
```

Apply:

```text
x[o,s,d](k+1) = clip(x[o,s,d](k+1), 0, x_max[o,s,d])
```

If clipping occurs, log the residual as overflow or numerical projection. Do not silently delete vehicles.

#### 3.3.4 Link free-space update

For each directed urban link `l_{u,v}`:

```text
S[u,v](k+1)
    = S[u,v](k)
      - inbound_to_link[u,v](k)
      + outbound_from_link[u,v](k)
```

where:

```text
inbound_to_link[u,v](k): vehicles entering link l_{u,v} during urban step k [veh]
outbound_from_link[u,v](k): vehicles leaving link l_{u,v} during urban step k [veh]
```

Apply storage bounds:

```text
S[u,v](k+1) = clip(S[u,v](k+1), 0, L_storage[u,v])
```

where `L_storage[u,v]` is the maximum number of vehicles that can be stored on link `l_{u,v}`.

#### 3.3.5 Link travel delay and arrival buffer

Vehicles that enter an urban link do not immediately reach the downstream queue. They first travel from the upstream end of the link to the tail of the downstream queue. Implement a delay buffer.

For link `l_{u,v}`:

```text
travel_distance_to_queue_tail_km[u,v](k)
    = S[u,v](k) * average_vehicle_length_km

travel_time_h[u,v](k)
    = travel_distance_to_queue_tail_km[u,v](k)
      / max(v_avg[u,v](k), eps)

delta_steps[u,v](k)
    = ceil(travel_time_h[u,v](k) / T_u_h)
```

When vehicles enter link `l_{u,v}` at urban step `k`, schedule them to arrive at the downstream queue tail at step `k + delta_steps[u,v](k)`:

```text
arrival_buffer[u,v][k + delta_steps[u,v](k)] += inbound_to_link[u,v](k)
```

Then split the vehicles reaching the queue tail by turning ratios:

```text
m_arr[o,s,d](k) = beta[o,s,d](k) * arrived_to_queue_tail[o,s](k)
```

Make sure that turning ratios satisfy:

```text
sum_d beta[o,s,d](k) = 1
0 <= beta[o,s,d](k) <= 1
```

---

### 3.4 Interface between urban and freeway models

The urban and freeway models are coupled through on-ramps and off-ramps. The implementation must avoid double-counting queues and must explicitly convert between freeway flow rates `[veh/h]` and urban vehicle counts `[veh/step]`.

Let:

```text
R_fu = T_f_sec / T_u_sec
k_u0 = k_f * R_fu
```

For every freeway step `k_f`, execute the coupled update using the following order.

#### 3.4.1 On-ramp interaction

Consider an on-ramp `r` connecting urban intersection/link `s` to freeway node `p`.

Use one physical queue. If the on-ramp is represented in the urban model as `x[s,r,p]`, synchronize it with the freeway queue variable `w[r]` at the freeway step boundary:

```text
w[r](k_f) = x[s,r,p](k_u0)
```

Step A. Compute the freeway-side on-ramp outflow over freeway interval `[k_f, k_f+1)`:

```text
q_rp_no_meter(k_f) = freeway_receiving_and_queue_limited_outflow(r,p,k_f)
q_rp(k_f) = min(q_rp_no_meter(k_f), b[r](k_f) * q_ramp_max[r])
```

If the freeway follower tracks `N_UF_star`, apply the target projection to the vector of `q_rp` values before simulating the interval.

Step B. Convert this freeway flow rate to an urban-step vehicle count and spread it evenly over the urban substeps:

```text
m_release_rp(k_u0 + j) = q_rp(k_f) * T_u_h,  for j = 0, ..., R_fu - 1
```

Step C. During the urban substeps, subtract `m_release_rp` from the on-ramp queue subject to available queued vehicles:

```text
m_dep[s,r,p](k_u0 + j)
    = min(x[s,r,p](k_u0 + j) + m_arr[s,r,p](k_u0 + j), m_release_rp(k_u0 + j))
```

Step D. After completing the urban substeps, synchronize the freeway queue:

```text
w[r](k_f + 1) = x[s,r,p](k_u0 + R_fu)
```

This synchronization replaces a separate freeway-only queue update for the same physical on-ramp. Do not update both `w[r]` and `x[s,r,p]` independently for the same vehicles.

#### 3.4.2 Off-ramp interaction

Consider an off-ramp `r` from the last segment of freeway link `m` to urban intersection `s`. The off-ramp storage is represented by directed urban link `l_{r,s}` with available storage `S[r,s]`.

Step A. Over the urban substeps, determine how many vehicles can leave the off-ramp link toward intersection `s`:

```text
offramp_out_to_urban(r,s,k_f)
    = sum_{j=0}^{R_fu-1} sum_d m_dep[r,s,d](k_u0 + j)
```

Step B. Compute the maximum freeway-to-off-ramp flow that can enter the off-ramp during the freeway interval:

```text
q_max_r1(k_f)
    = (S[r,s](k_u0 + R_fu) + offramp_out_to_urban(r,s,k_f)) / T_f_h
```

This equation states that freeway outflow into the off-ramp is limited by the storage that remains available at the end of the period plus the vehicles that leave the off-ramp during the period.

Step C. Limit the mainline/off-ramp outflow using this boundary condition:

```text
q_m_last_effective(k_f)
    = min(q_m_last_normal(k_f), q_max_r1(k_f))
```

where `q_m_last_normal` is the outflow that would leave the last freeway segment if the off-ramp were not blocked.

Step D. If the off-ramp boundary is binding, recalculate the speed of the last freeway segment consistently with the reduced outflow:

```text
if q_m_last_normal(k_f) <= q_max_r1(k_f):
    v_m_last_effective(k_f) = v_m_last_normal(k_f)
else:
    v_m_last_effective(k_f)
        = q_m_last_effective(k_f)
          / max(rho[m,last](k_f) * lanes[m], eps)
```

Step E. Spread the effective freeway outflow into the off-ramp urban link over urban substeps:

```text
m_enter_offramp(k_u0 + j) = q_m_last_effective(k_f) * T_u_h,
for j = 0, ..., R_fu - 1
```

Insert these vehicles into the arrival buffer of link `l_{r,s}` using the urban delay rule in Section 3.3.5.

#### 3.4.3 Required coupled simulation order

For each freeway time step:

```text
1. Synchronize on-ramp urban queues and freeway ramp queues.
2. Compute on-ramp freeway outflows, including ramp metering and N_UF_star projection.
3. Simulate urban substeps for on-ramp departures, signal departures, storage updates, and off-ramp downstream departures.
4. Compute off-ramp maximum entering flow q_max_r1 from available storage and off-ramp discharge.
5. Update the freeway METANET state using the off-ramp boundary condition.
6. Distribute effective freeway-to-off-ramp flows into the urban arrival buffers.
7. Project numerical states to feasible ranges and log every projection or infeasibility.
```

This order is mandatory because off-ramp storage can restrict freeway outflow, while on-ramp metering can create queues that spill back into the urban network.

---
