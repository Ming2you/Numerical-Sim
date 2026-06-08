"""
MPC controller for the mixed network.

Control vector per control step, following Zhai et al. (2025) Figure 3:
  g_A, g_C, g_D, g_F : green fraction for phase-1 at signalized intersections
  b1..b4             : ramp metering rates for R1..R4
  v_FW_W, v_FW_E     : direction-level freeway variable speed limits (km/h)
=> 10 variables per step, held over a control horizon Nc, then constant.

Prediction: the mixed model itself (simulator) rolled forward Np control steps
under a candidate control sequence; cost = TTS (urban + alpha*freeway).
Optimizer: SLSQP (scipy) with optional multi-start (paper uses multi-start SQP).
Receding horizon: apply first control step, re-measure, re-optimize.

Phase->approach mapping (2-phase plan, [A] per spec Sec. 7):
  Phase 1 (N-S): approaches from N and S get green.
  Phase 2 (E-W): approaches from E and W get green.
"""
import copy
import numpy as np

# approach -> phase, per intersection
_PHASE = {
    "A": {"NA": 1, "D": 1, "O1": 2, "B": 2},
    "C": {"NC": 1, "F": 1, "B": 2, "O2": 2},
    "D": {"A": 1, "O3": 2, "E": 2},
    "F": {"C": 1, "O4": 2, "E": 2},
}


def apply_control(sim, u):
    """Apply u = [g_A, g_C, g_D, g_F, b1..b4, optional v_FW_W, v_FW_E]."""
    u = np.asarray(u, dtype=float)
    if len(u) < 8:
        raise ValueError("control vector must contain at least 8 values")
    g_A, g_C, g_D, g_F, b1, b2, b3, b4 = u[:8]
    for inter, g1 in (("A", g_A), ("C", g_C), ("D", g_D), ("F", g_F)):
        for appr, ph in _PHASE[inter].items():
            frac = g1 if ph == 1 else (1.0 - g1)
            for turn in sim.urban.turns(inter, appr):
                sim.urban.green[(inter, appr, turn)] = frac
    sim.set_metering("R1", b1)
    sim.set_metering("R2", b2)
    sim.set_metering("R3", b3)
    sim.set_metering("R4", b4)
    if len(u) >= 10:
        for fw_name, limit in (("FW_W", u[8]), ("FW_E", u[9])):
            if fw_name in sim.fw:
                sim.fw[fw_name].speed_limit = float(limit)
    else:
        for fs in sim.fw.values():
            fs.speed_limit = None


def _rollout(sim0, u_seq, params, Np, max_queue_link=None):
    """Roll out a cloned simulator and return (sim, max_queue)."""
    sim = copy.deepcopy(sim0)
    sim.tts_freeway = 0.0
    sim.tts_urban = 0.0
    K_cf = params.time.K_cf
    Nc = u_seq.shape[0]
    max_q = 0.0
    for kc in range(Np):
        u = u_seq[min(kc, Nc - 1)]
        apply_control(sim, u)
        for _ in range(K_cf):
            sim.step_freeway_period()
            if max_queue_link is not None:
                max_q = max(max_q, sim.urban.queue_metric(max_queue_link))
    return sim, max_q


def rollout_cost(sim0, u_seq, params, Np):
    """Clone sim0, apply control sequence over Np control steps, return TTS cost.

    u_seq : array shape (Nc, nvar); held constant after Nc.
    """
    sim, _ = _rollout(sim0, u_seq, params, Np)
    return sim.tts_total()


def rollout_queue_margin(sim0, u_seq, params, Np, max_queue_link, max_queue_val):
    """Positive when all predicted queues stay within the management limit."""
    _, max_q = _rollout(sim0, u_seq, params, Np, max_queue_link)
    return max_queue_val - max_q


class MPCController:
    def __init__(self, params, Np_opt=None):
        self.p = params
        self.mpc = params.mpc
        self.Np = Np_opt or params.mpc.Np
        self.Nc = params.mpc.Nc
        self.nvar = 10
        # bounds: green fractions, metering rates, and direction-level VSLs
        gb = (self.mpc.g_min, self.mpc.g_max)
        bb = (self.mpc.b_min, self.mpc.b_max)
        vb = (self.mpc.vsl_min, self.mpc.vsl_max)
        self.bounds = []
        for _ in range(self.Nc):
            self.bounds += [gb, gb, gb, gb, bb, bb, bb, bb, vb, vb]
        self.last_u = None

    def optimize(self, sim, max_queue_link=None, max_queue_val=None):
        """Return optimal first-step control vector (length 10)."""
        from scipy.optimize import minimize

        Nc, nv = self.Nc, self.nvar

        def obj(flat):
            u_seq = flat.reshape(Nc, nv)
            return rollout_cost(sim, u_seq, self.p, self.Np)

        constraints = []
        if max_queue_link is not None:
            def queue_constraint(flat):
                u_seq = flat.reshape(Nc, nv)
                return rollout_queue_margin(
                    sim, u_seq, self.p, self.Np, max_queue_link, max_queue_val
                )
            constraints.append({"type": "ineq", "fun": queue_constraint})

        # initial guesses (multi-start)
        starts = []
        if self.last_u is not None:
            starts.append(np.tile(self.last_u, Nc))
        nominal = [
            0.5, 0.5, 0.5, 0.5,
            1.0, 1.0, 1.0, 1.0,
            self.mpc.vsl_max, self.mpc.vsl_max,
        ]
        starts.append(np.tile(nominal, Nc))
        if self.mpc.n_starts > len(starts):
            rng = np.random.default_rng(0)
            while len(starts) < self.mpc.n_starts:
                s = np.array([rng.uniform(*b) for b in self.bounds[:nv]])
                s = np.tile(s, Nc)
                starts.append(s)

        best_f, best_x = np.inf, None
        for x0 in starts[:self.mpc.n_starts]:
            res = minimize(obj, x0, method="SLSQP", bounds=self.bounds,
                           constraints=constraints,
                           options={"maxiter": self.mpc.maxiter, "ftol": 1e-3})
            if res.fun < best_f:
                best_f, best_x = res.fun, res.x
        u0 = best_x[:nv]
        self.last_u = u0.copy()
        return u0, best_f
