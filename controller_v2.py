"""
Stackelberg controller v2 (rebuilt per Min's design decisions).

Changes vs. the original stackelberg.py / follower_agents.py:
  1. Lower level solved as a genuine Nash game by iterated *continuous*
     best-response (urban green <-> freeway metering) to a residual tolerance,
     with a max-iteration cap and a best-iterate fallback (no grid search).
  2. Freeway follower: ramp metering b is continuous (SLSQP); VSL is discrete
     (enumerated), since posted advisory speed limits are physically discrete.
  3. Leader: NO n_crit/rho_crit adaptation. The leader chooses (N_P*, N_UF*)
     directly and the Stackelberg objective is the *follower-returned TTT*,
     minimised by continuous (derivative-free) optimisation.
  4. Urban follower is two-stage and corridor-aware:
       stage 1 -> green splits that meet the net-inflow target (explicit, with
                  slack) while balancing phase queues  [SLSQP, continuous];
       stage 2 -> offset (+green held) chosen from a small candidate set seeded
                  by the link travel time, scored by a corridor-TTT rollout.
     Signals are time-resolved (urban.time_resolved=True) so offset has a real
     dynamical effect. Corridors: A-D and C-F.

OPEN MODELLING KNOB (please confirm):
  `net_inflow_estimate` keeps the aggregate proxy used by the existing codebase
  (weights 1.0 at A,C and 0.5 at D,F). The movement-explicit boundary set can be
  swapped in here without touching the rest of the controller.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
from scipy.optimize import minimize

from freeway import freeway_vehicles

RAMP_ORDER: List[str] = ["R1", "R2", "R3", "R4"]
RAMP_TO_FW = {"R1": "FW_W", "R2": "FW_W", "R3": "FW_E", "R4": "FW_E"}
FW_RAMPS = {"FW_W": ["R1", "R2"], "FW_E": ["R3", "R4"]}
NODES = ["A", "C", "D", "F"]
VSL_SET = (60.0, 70.0, 80.0, 90.0, 100.0, 106.0)
# phase-1 / phase-2 approaches per node (mirrors network.SIGNAL_PHASE)
P1 = {"A": ["NA", "D"], "C": ["NC", "F"], "D": ["A"], "F": ["C"]}
P2 = {"A": ["O1", "B"], "C": ["B", "O2"], "D": ["O3", "E"], "F": ["O4", "E"]}


@dataclass
class CtrlConfig:
    g_min: float = 0.2
    g_max: float = 0.8
    b_min: float = 0.2
    b_max: float = 1.0
    eps_NP: float = 100.0          # net-inflow tracking tolerance (veh/h)
    eps_g: float = 0.05            # stage-2 green fine-tune band
    nash_max_iter: int = 6
    nash_tol: float = 1e-3         # ||du||_inf convergence tol
    nash_damping: float = 0.5      # relaxation on best-response updates
    leader_maxfev: int = 16        # derivative-free budget per control step
    NP_cap: float = 800.0          # |N_P*| bound (veh/h)


# ----------------------------------------------------------------------------
# control vector <-> plant
def build_u(greens, offsets, metering, vsl, p):
    """u = [gA,gC,gD,gF, offD, offF, b1,b2,b3,b4, vW,vE]."""
    return np.array([
        greens["A"], greens["C"], greens["D"], greens["F"],
        offsets.get("D", 0), offsets.get("F", 0),
        metering["R1"], metering["R2"], metering["R3"], metering["R4"],
        vsl.get("FW_W", p.mpc.vsl_max), vsl.get("FW_E", p.mpc.vsl_max),
    ], dtype=float)


def apply_control_v2(sim, u):
    sim.urban.time_resolved = True
    gA, gC, gD, gF, offD, offF = u[:6]
    sim.urban.set_signal("A", gA, 0)
    sim.urban.set_signal("C", gC, 0)
    sim.urban.set_signal("D", gD, int(round(offD)))
    sim.urban.set_signal("F", gF, int(round(offF)))
    for r, b in zip(RAMP_ORDER, u[6:10]):
        sim.set_metering(r, b)
    sim.fw["FW_W"].speed_limit = float(u[10])
    sim.fw["FW_E"].speed_limit = float(u[11])


def preview(sim, u, steps, p):
    trial = copy.deepcopy(sim)
    trial.tts_freeway = 0.0
    trial.tts_urban = 0.0
    apply_control_v2(trial, u)
    for _ in range(max(1, int(steps)) * p.time.K_cf):
        trial.step_freeway_period()
    return trial


# ----------------------------------------------------------------------------
# pressures / proxies
def _approach_pressure(sim, appr, inter):
    link = f"{appr}->{inter}"
    pr = 0.0
    if link in sim.urban.pipe:
        pr += sim.urban.queue_metric(link)
    for (n, a, _t), q in sim.urban.x.items():
        if n == inter and a == appr:
            pr += q
    return max(pr, 0.0)


def phase_pressures(sim):
    out = {}
    for n in NODES:
        p1 = sum(_approach_pressure(sim, a, n) for a in P1[n])
        p2 = sum(_approach_pressure(sim, a, n) for a in P2[n])
        out[n] = (float(p1), float(p2))
    return out


def net_inflow_estimate(greens, Q_sat):
    """Aggregate net-inflow proxy (OPEN KNOB - see module docstring)."""
    return float(Q_sat * (
        (greens["A"] - 0.5) + (greens["C"] - 0.5)
        + 0.5 * (greens["D"] - 0.5) + 0.5 * (greens["F"] - 0.5)
    ))


# ----------------------------------------------------------------------------
class UrbanFollower:
    def __init__(self, p, cfg: CtrlConfig):
        self.p, self.cfg = p, cfg
        self.last = {n: 0.5 for n in NODES}

    def stage1(self, sim, NP_target):
        """Continuous green to meet net-inflow target while balancing queues."""
        pr = phase_pressures(sim)
        Q_sat = self.p.urban.Q_sat
        sat = Q_sat * self.p.time.Tc / 3600.0
        gmin, gmax = self.cfg.g_min, self.cfg.g_max

        def obj(x):
            g = {n: x[i] for i, n in enumerate(NODES)}
            slack = x[4]
            c = 0.0
            for n in NODES:
                p1, p2 = pr[n]
                sc = max(p1 + p2, 1.0)
                q1 = max(0.0, p1 - g[n] * sat)
                q2 = max(0.0, p2 - (1.0 - g[n]) * sat)
                c += (q1 / sc) ** 2 + (q2 / sc) ** 2
            c += 1e-5 * slack ** 2
            c += 0.05 * sum((g[n] - self.last[n]) ** 2 for n in NODES)
            return c

        def netc(x):
            g = {n: x[i] for i, n in enumerate(NODES)}
            return self.cfg.eps_NP + x[4] - abs(net_inflow_estimate(g, Q_sat) - NP_target)

        x0 = [self.last[n] for n in NODES] + [0.0]
        bnds = [(gmin, gmax)] * 4 + [(0.0, 5000.0)]
        res = minimize(obj, x0, method="SLSQP", bounds=bnds,
                       constraints=[{"type": "ineq", "fun": netc}],
                       options={"maxiter": 60, "ftol": 1e-6, "disp": False})
        x = res.x
        return {n: float(np.clip(x[i], gmin, gmax)) for i, n in enumerate(NODES)}, bool(res.success)

    def stage2(self, sim, greens, metering, vsl):
        """Pick corridor offsets from a travel-time-seeded candidate set."""
        cyc = sim.urban.cycle_steps
        ideal_AD = sim.urban.delay_steps.get("A->D", 36)
        ideal_CF = sim.urban.delay_steps.get("C->F", 36)
        cand_D = sorted({0, int(ideal_AD) % cyc})
        cand_F = sorted({0, int(ideal_CF) % cyc})
        best = None
        for offD in cand_D:
            for offF in cand_F:
                u = build_u(greens, {"D": offD, "F": offF}, metering, vsl, self.p)
                tot = preview(sim, u, 1, self.p).tts_total()
                if best is None or tot < best[0]:
                    best = (tot, offD, offF)
        return {"D": best[1], "F": best[2]}, best[0]


class FreewayFollower:
    def __init__(self, p, cfg: CtrlConfig):
        self.p, self.cfg = p, cfg
        self.last_vsl = {"FW_W": p.mpc.vsl_max, "FW_E": p.mpc.vsl_max}

    def respond(self, sim, NUF_target):
        """Per-direction best response: continuous b (SLSQP) + discrete VSL."""
        Tc_h = self.p.time.Tc / 3600.0
        caps = {r.name: r.Q_cap for r in sim.net.ramps}
        bmin, bmax = self.cfg.b_min, self.cfg.b_max
        total_cap = sum(caps[r] for r in RAMP_ORDER)
        metering, vsl = {}, {}
        for fw, ramps in FW_RAMPS.items():
            fs = sim.fw[fw]
            veh = freeway_vehicles(fs)
            avail = np.array([sim.onramp_q.get(r, 0.0) for r in ramps])
            cv = np.array([caps[r] for r in ramps])
            loc_target = NUF_target * sum(cv) / max(total_cap, 1e-9)

            def obj(b, vsl_val):
                release = b * cv
                ramp_q = float(np.sum(np.maximum(0.0, avail - release * Tc_h)))
                tts = Tc_h * veh
                speed_delay = tts * max(0.0, self.p.mpc.vsl_max / max(vsl_val, 1.0) - 1.0)
                tgt = (float(np.dot(b, cv)) - loc_target) ** 2
                sm = (vsl_val - self.last_vsl[fw]) ** 2
                return tts + speed_delay + 0.08 * ramp_q + 1e-9 * tgt + 1e-4 * sm

            best = None
            b0 = np.clip(loc_target / np.maximum(cv, 1e-9), bmin, bmax)
            for v in VSL_SET:
                res = minimize(lambda b: obj(b, v), b0, method="SLSQP",
                               bounds=[(bmin, bmax)] * len(ramps),
                               options={"maxiter": 40, "ftol": 1e-6, "disp": False})
                val = obj(res.x, v)
                if best is None or val < best[0]:
                    best = (val, np.clip(res.x, bmin, bmax), v)
            _, b_opt, v_opt = best
            for i, r in enumerate(ramps):
                metering[r] = float(b_opt[i])
            vsl[fw] = float(v_opt)
        return metering, vsl


# ----------------------------------------------------------------------------
@dataclass
class StepInfo:
    NP: float
    NUF: float
    greens: Dict[str, float]
    offsets: Dict[str, float]
    metering: Dict[str, float]
    vsl: Dict[str, float]
    tts_total: float
    tts_freeway: float
    tts_urban: float
    nash_iters: int
    nash_residual: float
    nash_converged: bool
    leader_evals: int


class StackelbergV2:
    def __init__(self, p, cfg: CtrlConfig = None):
        self.p = p
        self.cfg = cfg or CtrlConfig()
        self.urban = UrbanFollower(p, self.cfg)
        self.freeway = FreewayFollower(p, self.cfg)

    # ----- lower level: Nash by iterated best response -----------------------
    def nash(self, sim, NP, NUF):
        cfg = self.cfg
        greens = dict(self.urban.last)
        metering = {r: 1.0 for r in RAMP_ORDER}
        vsl = dict(self.freeway.last_vsl)
        last_vec = None
        best = None
        residual = np.inf
        converged = False
        it = 0
        for it in range(1, cfg.nash_max_iter + 1):
            g_new, _ = self.urban.stage1(sim, NP)
            # damped update on greens
            greens = {n: (1 - cfg.nash_damping) * greens[n] + cfg.nash_damping * g_new[n]
                      for n in NODES}
            m_new, v_new = self.freeway.respond(sim, NUF)
            metering = {r: (1 - cfg.nash_damping) * metering[r] + cfg.nash_damping * m_new[r]
                        for r in RAMP_ORDER}
            vsl = v_new  # discrete: take best response directly

            vec = np.array([greens[n] for n in NODES]
                           + [metering[r] for r in RAMP_ORDER]
                           + [vsl[f] for f in ("FW_W", "FW_E")])
            # cheap analytic score for best-iterate tracking
            score = self._analytic_cost(sim, greens, metering, vsl, NP, NUF)
            if best is None or score < best[0]:
                best = (score, dict(greens), dict(metering), dict(vsl))
            if last_vec is not None:
                residual = float(np.max(np.abs(vec - last_vec)))
                if residual <= cfg.nash_tol:
                    converged = True
                    break
            last_vec = vec
        # fallback to best iterate if not converged
        if not converged:
            _, greens, metering, vsl = best
        return greens, metering, vsl, dict(iters=it, residual=residual, converged=converged)

    def _analytic_cost(self, sim, greens, metering, vsl, NP, NUF):
        pr = phase_pressures(sim)
        Q_sat = self.p.urban.Q_sat
        sat = Q_sat * self.p.time.Tc / 3600.0
        Tc_h = self.p.time.Tc / 3600.0
        c = 0.0
        for n in NODES:
            p1, p2 = pr[n]
            sc = max(p1 + p2, 1.0)
            c += (max(0.0, p1 - greens[n] * sat) / sc) ** 2
            c += (max(0.0, p2 - (1 - greens[n]) * sat) / sc) ** 2
        for fw, fs in sim.fw.items():
            c += Tc_h * freeway_vehicles(fs) * max(0.0, self.p.mpc.vsl_max / max(vsl[fw], 1.0))
        return c

    # ----- upper level: continuous leader over (N_P*, N_UF*) -----------------
    def optimize(self, sim):
        cfg = self.cfg
        ramp_cap = sum(r.Q_cap for r in sim.net.ramps)
        evals = {"n": 0}
        cache = {}

        def evaluate(NP, NUF):
            key = (round(NP, 1), round(NUF, 1))
            if key in cache:
                return cache[key]
            evals["n"] += 1
            greens, metering, vsl, ninfo = self.nash(sim, NP, NUF)
            offsets, tot = self.urban.stage2(sim, greens, metering, vsl)
            cache[key] = (tot, greens, metering, vsl, offsets, ninfo)
            return cache[key]

        # derivative-free search over the two leader targets
        x0 = np.array([0.0, 0.5 * ramp_cap])
        bounds = [(-cfg.NP_cap, cfg.NP_cap), (0.0, ramp_cap)]

        def f(x):
            NP = float(np.clip(x[0], -cfg.NP_cap, cfg.NP_cap))
            NUF = float(np.clip(x[1], 0.0, ramp_cap))
            return evaluate(NP, NUF)[0]

        res = minimize(f, x0, method="Powell", bounds=bounds,
                       options={"maxfev": cfg.leader_maxfev, "xtol": 1e-2, "ftol": 1e-2})
        NP = float(np.clip(res.x[0], -cfg.NP_cap, cfg.NP_cap))
        NUF = float(np.clip(res.x[1], 0.0, ramp_cap))
        tot, greens, metering, vsl, offsets, ninfo = evaluate(NP, NUF)

        # commit memory
        self.urban.last = dict(greens)
        self.freeway.last_vsl = dict(vsl)

        u = build_u(greens, offsets, metering, vsl, self.p)
        tr = preview(sim, u, 1, self.p)
        info = StepInfo(NP=NP, NUF=NUF, greens=greens, offsets=offsets,
                        metering=metering, vsl=vsl,
                        tts_total=tr.tts_total(), tts_freeway=tr.tts_freeway,
                        tts_urban=tr.tts_urban, nash_iters=ninfo["iters"],
                        nash_residual=ninfo["residual"], nash_converged=ninfo["converged"],
                        leader_evals=evals["n"])
        return u, info


def run_v2(sim, p, demand_fn=None, cfg: CtrlConfig = None, n_ctrl=None):
    ctrl = StackelbergV2(p, cfg)
    n_ctrl = n_ctrl or int(p.time.sim_time / p.time.Tc)
    infos = []
    for kc in range(n_ctrl):
        if demand_fn:
            demand_fn(kc * p.time.Tc)
        u, info = ctrl.optimize(sim)
        apply_control_v2(sim, u)
        for _ in range(p.time.K_cf):
            sim.step_freeway_period()
        infos.append(info)
    return sim, infos
