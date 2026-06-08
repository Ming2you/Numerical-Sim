"""
Urban traffic model (extended Kashani), Van den Berg et al. (2007) Sec. 2.2.

Essential features preserved:
  - horizontal, turning-direction-dependent queues x_{o,s,d}
  - green/red gating of departures (Eq. 6) at saturation flow Q_sat
  - blocking via downstream free space S (no entry into a full link)
  - proportional division of limited downstream space over competing inflows

SIMPLIFICATIONS vs. paper (documented for Min):
  [S1] Eq. (7) travel-time delay + accumulative arrival update replaced by a
       per-link FIFO pipeline of fixed length d = round(L / v_avg / Tu). One pop
       (arrivals at tail) and one push (inflow at head) per link per step.
  [S2] The 2-origin proportional split is generalized to N inflows by equal
       free-space division with one redistribution pass of unused shares.
These affect absolute TTS values, not the structural dynamics.
"""
import numpy as np
from collections import deque, defaultdict


class UrbanNetwork:
    def __init__(self, net, params):
        self.net = net
        self.p = params
        self.up = params.urban
        self.Tu_h = params.time.Tu_h
        self.Tu = params.time.Tu

        self.storage = {nm: lk.storage_veh for nm, lk in net.urban_links.items()}
        self.S = dict(self.storage)                       # free space (veh)
        self.x = defaultdict(float)                       # subqueues

        # per-link FIFO pipeline [S1]; constant length, one pop + one push / step
        self.delay_steps, self.pipe = {}, {}
        for nm, lk in net.urban_links.items():
            d = max(1, int(round(lk.length_km * 1000.0 / (lk.v_avg / 3.6) / self.Tu)))
            self.delay_steps[nm] = d
            self.pipe[nm] = deque([0.0] * d)

        self.green = defaultdict(lambda: 1.0)

        # time-resolved signal state (added). False => original proportional green.
        self.time_resolved = False
        self.t_step = 0
        self.cycle_steps = max(1, int(round(params.mpc.cycle_time / self.Tu)))
        self.signal = {}

        self.blocked = set()              # blocked signalized intersections
        self.blocked_crossing = set()     # blocked crossing/access nodes (e.g. D)
        self.demand = defaultdict(float)                  # origin node -> veh/h
        self.offramp_arrivals = defaultdict(float)
        self.crossing_q = defaultdict(float)

    # ---- enumeration ----------------------------------------------------------
    def approaches(self, inter):
        from network import TURNING
        return [a for (i, a) in TURNING if i == inter]

    def turns(self, inter, approach):
        from network import TURNING
        return list(TURNING[(inter, approach)].keys())

    def _origin_target(self, o):
        return {
            "O1": "A", "O2": "C", "O3": "D", "O4": "F",
            "NA": "A", "NB": "B", "NC": "C",
            # Legacy aliases kept so old quick tests fail softly.
            "oW": "A", "oN1": "A", "oE": "C", "oN2": "C",
        }.get(o, "A")

    def _ramp_feeder_to_node(self, node):
        if node == "D":
            return "A->D"
        if node == "F":
            return "C->F"
        # Legacy Van den Berg-style nodes.
        return f"{'A' if node == 'D' else 'C'}->{node}"

    def _offramp_return_link(self, node):
        if node == "D":
            return "D->A"
        if node == "F":
            return "F->C"
        return f"{node}->{'A' if node == 'D' else 'C'}"

    # ---- time-resolved signal control ----------------------------------------
    def set_signal(self, inter, g, offset_steps=0):
        self.signal[inter] = {"g": float(min(max(g, 0.0), 1.0)),
                              "offset_steps": int(offset_steps) % self.cycle_steps}

    def _phase_gate(self, inter, appr):
        if inter in self.blocked:
            return 0.0
        if not self.time_resolved:
            from network import TURNING
            for turn in TURNING[(inter, appr)]:
                return self.green[(inter, appr, turn)]
            return 0.0
        from network import SIGNAL_PHASE
        sig = self.signal.get(inter)
        if sig is None:
            return 0.0
        phase = SIGNAL_PHASE[inter].get(appr, 2)
        cyc = self.cycle_steps
        s = (self.t_step - sig["offset_steps"]) % cyc
        in_phase1 = s < sig["g"] * cyc
        return 1.0 if ((phase == 1 and in_phase1) or (phase == 2 and not in_phase1)) else 0.0

    # ---- one urban step -------------------------------------------------------
    def step(self, ramp_offramp_flow=None):
        from network import TURNING, turn_destination

        # (1) POP arrivals at the tail of every link (exactly one pop per link)
        # feeder links into a blocked crossing node are frozen: their vehicles
        # cannot discharge, so the link fills and spills back upstream.
        frozen = set()
        for node in self.blocked_crossing:
            if node == "B":
                frozen.update({"A->B", "C->B", "B->E"})
            elif node == "E":
                frozen.update({"D->E", "F->E", "B->E"})
            else:
                frozen.update(
                    name for name, link in self.net.urban_links.items()
                    if link.to == node and link.frm != node
                )
        arrivals = {}
        for nm in self.pipe:
            if nm in frozen:
                arrivals[nm] = 0.0            # nothing discharges
                self.S[nm] = 0.0              # link full -> blocks upstream
            else:
                arrivals[nm] = self.pipe[nm].popleft()
                self.S[nm] = min(self.storage[nm], self.S[nm] + arrivals[nm])

        # off-ramp arrivals feed D/E (added to the feeder-link arrivals)
        if ramp_offramp_flow:
            for node, veh in ramp_offramp_flow.items():
                self.offramp_arrivals[node] += veh

        # (2) intended departures from signalized intersections (Eq. 6)
        intended = {}
        for inter in self.net.signal_nodes:
            for appr in self.approaches(inter):
                arr = arrivals.get(f"{appr}->{inter}", 0.0)
                fr = TURNING[(inter, appr)]
                gate = self._phase_gate(inter, appr)
                for turn, ratio in fr.items():
                    key = (inter, appr, turn)
                    if gate <= 0.0:
                        intended[key] = 0.0
                    else:
                        sat = self.up.Q_sat * self.Tu_h * gate
                        intended[key] = min(self.x[key] + ratio * arr, sat)

        # (3) downstream free-space blocking with proportional division [S2]
        by_link = defaultdict(list)
        by_ramp = defaultdict(list)
        for inter in self.net.signal_nodes:
            for appr in self.approaches(inter):
                for turn in self.turns(inter, appr):
                    key = (inter, appr, turn)
                    dest_type, dest = turn_destination(inter, appr, turn)
                    if dest_type == "ramp":
                        by_ramp[dest].append((key, intended.get(key, 0.0)))
                    else:
                        out_link = f"{inter}->{dest}"
                        tgt = out_link if out_link in self.S else "__sink__"
                        by_link[tgt].append((key, intended.get(key, 0.0)))

        effective = {}
        for out_link, items in by_link.items():
            if out_link == "__sink__":
                for key, val in items:
                    effective[key] = val
                continue
            space, total = self.S[out_link], sum(v for _, v in items)
            if total <= space or total <= 0:
                for key, val in items:
                    effective[key] = val
            else:
                share = space / len(items)
                used, leftover, under = {}, 0.0, []
                for key, val in items:
                    if val <= share:
                        used[key] = val; leftover += share - val
                    else:
                        under.append((key, val))
                if under:
                    add = leftover / len(under)
                    for key, val in under:
                        used[key] = min(val, share + add)
                for key, val in items:
                    effective[key] = used.get(key, 0.0)

        onramp = defaultdict(float)
        for ramp_name, items in by_ramp.items():
            for key, val in items:
                effective[key] = val
                onramp[ramp_name] += val

        # (4) update subqueues: arrivals in, effective departures out
        for inter in self.net.signal_nodes:
            for appr in self.approaches(inter):
                arr = arrivals.get(f"{appr}->{inter}", 0.0)
                fr = TURNING[(inter, appr)]
                for turn, ratio in fr.items():
                    key = (inter, appr, turn)
                    self.x[key] = max(0.0,
                                      self.x[key] + ratio * arr - effective.get(key, 0.0))

        # (5) compute per-link inflow (one push per link)
        inflow = defaultdict(float)
        # 5a: origin demand enters origin links
        for o, dem in self.demand.items():
            inflow[f"{o}->{self._origin_target(o)}"] += dem * self.Tu_h
        # 5b: intersection departures enter downstream links
        for out_link, items in by_link.items():
            if out_link == "__sink__":
                continue
            inflow[out_link] += sum(effective.get(k, 0.0) for k, _ in items)
        # 5b-2: crossing-only intersections B and E transfer straight-through.
        # These nodes are not signalized in Zhai Fig. 3.
        crossing_pairs = {
            "A->B": "B->C",
            "C->B": "B->A",
            "NB->B": "B->E",
            "B->E": "E->B",
            "E->B": "B->NB",
            "D->E": "E->F",
            "F->E": "E->D",
        }
        for in_link, out_link in crossing_pairs.items():
            if in_link in arrivals and out_link in self.pipe:
                qkey = (in_link, out_link)
                self.crossing_q[qkey] += arrivals[in_link]
                if out_link in frozen:
                    continue
                accepted = min(self.crossing_q[qkey], self.S[out_link])
                inflow[out_link] += accepted
                self.crossing_q[qkey] = max(0.0, self.crossing_q[qkey] - accepted)
        # 5c: off-ramp arrivals enter the off-ramp feeder links (E->C / D->A back-haul)
        for node, veh in list(self.offramp_arrivals.items()):
            link = self._offramp_return_link(node)
            if link in inflow or link in self.pipe:
                inflow[link] += veh
            self.offramp_arrivals[node] = 0.0

        # (6) PUSH inflow into every link pipeline (exactly one push per link)
        for nm in self.pipe:
            if nm in frozen:
                continue                      # blocked: pipeline frozen
            q_in = inflow.get(nm, 0.0)
            q_in = min(q_in, self.S[nm])      # cannot exceed free space
            self.S[nm] = max(0.0, self.S[nm] - q_in)
            self.pipe[nm].append(q_in)

        self.t_step += 1
        return dict(onramp)

    # ---- metrics --------------------------------------------------------------
    def total_queue(self):
        return float(sum(self.x.values()))

    def vehicles_on_links(self):
        return float(sum(self.storage[nm] - self.S[nm] for nm in self.S))

    def link_occupancy(self, link_name):
        """Vehicles currently stored on an urban link pipeline."""
        if link_name not in self.S:
            raise KeyError(f"Unknown urban link: {link_name}")
        return float(self.storage[link_name] - self.S[link_name])

    def queue_metric(self, link_name):
        """Queue-length proxy used for link-level management constraints."""
        return self.link_occupancy(link_name) + self.link_queue(link_name)

    def link_queue(self, out_link):
        from network import turn_destination
        tot = 0.0
        for (inter, appr, turn), q in self.x.items():
            dest_type, dest = turn_destination(inter, appr, turn)
            if dest_type == "urban" and f"{inter}->{dest}" == out_link:
                tot += q
        return tot
