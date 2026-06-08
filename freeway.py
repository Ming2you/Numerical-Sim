"""
METANET freeway model (destination-independent), Van den Berg et al. (2007) Sec. 2.1.

Implements:
  - segment outflow  q = rho * v * n
  - density conservation
  - speed update Eq. (1): relaxation + convection + anticipation
  - desired speed Eq. (2)
  - mainstream origin queue Eq. (3)-(4)
  - off-ramp diverge with blocking extension Eq. (5)
  - on-ramp merge with metering

Boundary handling for a single 3-segment link with one external origin:
  upstream of segment 0 we use the origin flow / virtual entering speed;
  downstream of the last segment we use a free-flow downstream density
  (no congestion imposed unless a scenario sets it).
"""
import numpy as np


class FreewayState:
    """State of one freeway link."""
    def __init__(self, link, p):
        self.link = link
        self.n = link.n_segments
        self.L = link.seg_length_km
        self.lanes = link.n_lanes
        self.p = p.metanet
        # state vectors
        self.rho = np.full(self.n, 20.0)   # veh/km/lane (light traffic init)
        self.v = np.full(self.n, p.metanet.v_free)
        self.w_origin = 0.0                # origin queue (veh)
        # boundary conditions (set per step)
        self.rho_downstream = 20.0         # virtual downstream density (seg n)
        self.v_upstream = p.metanet.v_free # virtual entering speed (seg -1)
        # control / external
        self.metering_rate = 1.0           # b(k) in [0,1] for on-ramp
        self.speed_limit = None            # optional km/h direction-level VSL
        self.demand_origin = 0.0           # veh/h mainstream demand

    def outflow(self):
        """q_{m,i} = rho v n  (veh/h)."""
        return self.rho * self.v * self.lanes


def step_freeway(fs: FreewayState, Tf_h, on_ramp_flow=0.0, off_ratio=0.0,
                 off_max_flow=np.inf, on_ramp_flows=None, off_events=None):
    """
    Advance one freeway link by one freeway time step Tf (hours).

    on_ramp_flow  : legacy veh/h merging at on_ramp_seg
    off_ratio     : legacy fraction diverging at off_ramp_seg
    off_max_flow  : legacy max flow the off-ramp can accept (blocking), veh/h
    on_ramp_flows : optional dict ramp_name -> veh/h, using link.on_ramp_segs
    off_events    : optional list of dicts with name, seg, ratio, max_flow

    Returns dict with diagnostics including realized off-ramp outflow.
    """
    p = fs.p
    n = fs.n
    L = fs.L
    lanes = fs.lanes
    rho = fs.rho
    v = fs.v

    q = rho * v * lanes  # segment outflows (veh/h)

    # --- origin queue & inflow to segment 0, Eq. (3)-(4) ---
    rho0 = rho[0]
    q_cap = p.Q_cap
    cong_factor = (p.rho_max - rho0) / (p.rho_max - p.rho_crit)
    cong_factor = np.clip(cong_factor, 0.0, 1.0)
    avail = fs.demand_origin + fs.w_origin / Tf_h
    q_in = min(avail, q_cap, q_cap * cong_factor)
    q_in = max(q_in, 0.0)
    # metering applies to mainstream origin only if configured (not used by default)
    fs.w_origin = max(0.0, fs.w_origin + Tf_h * (fs.demand_origin - q_in))

    # upstream inflow profile per segment boundary
    q_up = np.empty(n)        # flow entering segment i
    q_up[0] = q_in
    for i in range(1, n):
        q_up[i] = q[i - 1]

    # --- on-ramp merge (added to the segment's inflow) ---
    if on_ramp_flows is None:
        on_ramp_flows = {}
        if fs.link.on_ramp_seg is not None and on_ramp_flow > 0:
            on_ramp_flows["__legacy__"] = on_ramp_flow
            fs.link.on_ramp_segs.setdefault("__legacy__", fs.link.on_ramp_seg)
    for ramp_name, flow in on_ramp_flows.items():
        seg = fs.link.on_ramp_segs.get(ramp_name, fs.link.on_ramp_seg)
        if seg is not None and flow > 0:
            q_up[seg] += flow

    # --- off-ramp diverge with blocking (Eq. 5) ---
    off_realized = 0.0
    off_realized_by_ramp = {}
    off_want_by_seg = np.zeros(n)
    off_realized_by_seg = np.zeros(n)
    q_down = np.empty(n)      # flow leaving segment i (downstream)
    for i in range(n):
        q_down[i] = q[i]
    if off_events is None:
        off_events = []
        if fs.link.off_ramp_seg is not None and off_ratio > 0:
            off_events.append({
                "name": "__legacy__",
                "seg": fs.link.off_ramp_seg,
                "ratio": off_ratio,
                "max_flow": off_max_flow,
            })
    for ev in off_events:
        seg = ev["seg"]
        q_want = ev["ratio"] * q[seg]
        realized = min(q_want, ev["max_flow"])
        realized = max(realized, 0.0)
        off_want_by_seg[seg] += q_want
        off_realized_by_seg[seg] += realized
        off_realized_by_ramp[ev["name"]] = realized
        off_realized += realized
    for seg in range(n):
        if off_realized_by_seg[seg] > 0:
            # flow continuing downstream past the off-ramp segment is reduced
            q_down[seg] = q[seg] - off_realized_by_seg[seg]

    # --- density conservation ---
    rho_new = np.empty(n)
    for i in range(n):
        inflow = q_up[i]
        outflow = q_down[i] if off_realized_by_seg[i] > 0 else q[i]
        # for an off-ramp segment, total leaving = mainline-continuing + off
        if off_realized_by_seg[i] > 0:
            outflow = q_down[i] + off_realized_by_seg[i]
        rho_new[i] = rho[i] + (Tf_h / (L * lanes)) * (inflow - outflow)
        rho_new[i] = max(rho_new[i], 0.0)

    # --- speed update Eq. (1) ---
    V = p.V(rho)  # desired speed at current density
    if fs.speed_limit is not None:
        V = np.minimum(V, fs.speed_limit)
    v_new = np.empty(n)
    for i in range(n):
        v_up = fs.v_upstream if i == 0 else v[i - 1]
        rho_dn = fs.rho_downstream if i == n - 1 else rho[i + 1]
        relax = (Tf_h / p.tau) * (V[i] - v[i])
        conv = (Tf_h / L) * v[i] * (v_up - v[i])
        antic = (p.nu * Tf_h / (p.tau * L)) * (rho_dn - rho[i]) / (rho[i] + p.kappa)
        v_new[i] = v[i] + relax + conv - antic
        v_new[i] = max(v_new[i], 1.0)  # floor to keep numerics sane

    # --- off-ramp blocking speed correction on last/diverge segment ---
    for seg in range(n):
        if off_want_by_seg[seg] > off_realized_by_seg[seg] and off_want_by_seg[seg] > 0:
            v_new[seg] = v_new[seg] * (off_realized_by_seg[seg] / off_want_by_seg[seg])
            v_new[seg] = max(v_new[seg], 1.0)

    fs.rho = rho_new
    fs.v = v_new

    return {
        "q_in": q_in,
        "off_realized": off_realized,
        "off_realized_by_ramp": off_realized_by_ramp,
        "w_origin": fs.w_origin,
        "rho": rho_new.copy(),
        "v": v_new.copy(),
        "q_out_last": rho_new[-1] * v_new[-1] * lanes,
    }


def freeway_vehicles(fs: FreewayState):
    """Number of vehicles on the link (for TTS), veh."""
    return float(np.sum(fs.rho) * fs.L * fs.lanes) + fs.w_origin
