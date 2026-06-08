"""
Coupled mixed-network simulator for the Zhai Figure 3 mixed network.

Time nesting: Tu=1 s (urban) < Tf=10 s (freeway) < Tc=120 s (controller).
Per freeway step (Fig. 5 order):
  1. simulate urban network for the K_fu urban steps in this period
     -> accumulate effective ramp-bound turn departures
  2. compute max off-ramp flow each freeway can discharge into urban
     (limited by available urban storage at the off-ramp feeder link)
  3. simulate freeway one step with on-ramp inflow + off-ramp blocking limit
  4. distribute realized off-ramp outflow back into urban arrivals
On-ramp queues buffer signal-served urban->freeway flow and are released subject
to metering.
"""
import numpy as np
from collections import defaultdict

from freeway import FreewayState, step_freeway, freeway_vehicles
from urban import UrbanNetwork


class MixedSimulator:
    def __init__(self, net, params):
        self.net = net
        self.p = params
        self.t = params.time

        self.fw = {nm: FreewayState(lk, params) for nm, lk in net.freeways.items()}
        self.urban = UrbanNetwork(net, params)

        # on-ramp queues (veh waiting to enter freeway), per ramp
        self.onramp_q = defaultdict(float)
        # ramp metering rate b in [0,1], per ramp (1 = no metering)
        self.metering = defaultdict(lambda: 1.0)

        # which ramp serves which freeway/segment
        self.ramp_by_name = {r.name: r for r in net.ramps}

        # logs
        self.tts_freeway = 0.0
        self.tts_urban = 0.0
        self.history = defaultdict(list)

    # ---- control interface ----------------------------------------------------
    def set_green(self, inter, splits):
        """splits: dict (approach,turn)->fraction in [0,1]."""
        for (appr, turn), frac in splits.items():
            self.urban.green[(inter, appr, turn)] = frac

    def set_metering(self, ramp_name, b):
        self.metering[ramp_name] = float(np.clip(b, 0.0, 1.0))

    # ---- one freeway step (contains K_fu urban steps) -------------------------
    def step_freeway_period(self):
        Tf_h, Tu_h = self.t.Tf_h, self.t.Tu_h
        K_fu = self.t.K_fu

        # 1. urban steps -> accumulate effective on-ramp departures
        onramp_acc = defaultdict(float)
        # off-ramp arrivals computed at end of previous freeway step are injected
        # progressively; here we inject the pending arrivals split over urban steps
        pending_off = getattr(self, "_pending_offramp", defaultdict(float))
        per_step_off = {n: v / K_fu for n, v in pending_off.items()}

        for _ in range(K_fu):
            onramp = self.urban.step(ramp_offramp_flow=per_step_off)
            for nm, veh in onramp.items():
                onramp_acc[nm] += veh
        self._pending_offramp = defaultdict(float)

        # queue the urban veh on each on-ramp
        for nm, veh in onramp_acc.items():
            self.onramp_q[nm] += veh

        # 2-3-4. per freeway, gather its ramps, compute inflow & off limits, step
        new_off = defaultdict(float)
        off_space_remaining = {}
        for node in {r.urban_node for r in self.net.ramps}:
            feeder = "D->A" if node == "D" else ("F->C" if node == "F" else f"{node}->{'A' if node == 'D' else 'C'}")
            off_space_remaining[node] = self.urban.S.get(feeder, np.inf)
        for fwname, fs in self.fw.items():
            # on-ramp inflow (veh/h) for this freeway, kept per ramp so each
            # interchange merges at its Fig. 8 segment.
            on_flows = {}
            served_ramps = [r for r in self.net.ramps if r.freeway == fwname]
            for r in served_ramps:
                # release rate limited by metering and on-ramp capacity
                b = self.metering[r.name]
                cap_flow = b * r.Q_cap                       # veh/h
                avail_flow = self.onramp_q[r.name] / Tf_h     # veh/h equiv of queue
                release = min(cap_flow, avail_flow)
                release = max(release, 0.0)
                self.onramp_q[r.name] = max(
                    0.0, self.onramp_q[r.name] - release * Tf_h)
                on_flows[r.name] = release

            # off-ramps: max flow urban can accept (storage at feeder link),
            # kept per ramp so blockage feeds back at the right interchange.
            off_events = []
            for r in served_ramps:
                if r.name not in fs.link.off_ramp_segs:
                    continue
                node = r.urban_node
                space = off_space_remaining.get(node, np.inf)
                off_max = space / Tf_h if np.isfinite(space) else np.inf
                off_events.append({
                    "name": r.name,
                    "seg": fs.link.off_ramp_segs[r.name],
                    "ratio": r.off_ratio,
                    "max_flow": off_max,
                })

            out = step_freeway(fs, Tf_h,
                               on_ramp_flows=on_flows,
                               off_events=off_events)

            for ramp_name, flow in out["off_realized_by_ramp"].items():
                node = self.ramp_by_name[ramp_name].urban_node
                veh = flow * Tf_h
                new_off[node] += veh  # veh this period
                if np.isfinite(off_space_remaining.get(node, np.inf)):
                    off_space_remaining[node] = max(0.0, off_space_remaining[node] - veh)

        self._pending_offramp = new_off

        # 5. accumulate TTS (veh * hours) over this freeway period
        veh_fw = sum(freeway_vehicles(fs) for fs in self.fw.values())
        veh_ur = self.urban.vehicles_on_links() + self.urban.total_queue() \
            + sum(self.onramp_q.values())
        self.tts_freeway += veh_fw * Tf_h
        self.tts_urban += veh_ur * Tf_h

        self.history["veh_fw"].append(veh_fw)
        self.history["veh_ur"].append(veh_ur)
        self.history["onramp_q"].append(dict(self.onramp_q))
        self.history["AB_queue"].append(self.urban.queue_metric("A->B"))

    def tts_total(self):
        return self.tts_freeway + self.p.mpc.alpha * self.tts_urban
