"""
Network topology based only on Zhai et al. (2025), Figure 3.

The case-study network contains:
 - four signalized urban intersections: A, C, D, F
 - two crossing-only intersections: B, E
 - D and F have external boundary legs, represented here as O3 and O4
 - two expressway directions with four on-ramps R1-R4 and four off-ramps

Figure 3 provides topology but not numeric turning proportions. The fixed turn
fractions below are therefore equal-share placeholders required by the current
queue model. Zhai et al. use DUE rather than fixed turn proportions.
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class FreewayLink:
    name: str
    direction: str
    n_segments: int = 3
    seg_length_km: float = 0.5
    n_lanes: int = 2
    origin: str = None
    on_ramp_seg: int = None
    off_ramp_seg: int = None
    on_ramp_node: str = None
    off_ramp_node: str = None
    off_ramp_ratio: float = 0.0
    on_ramp_segs: Dict[str, int] = field(default_factory=dict)
    off_ramp_segs: Dict[str, int] = field(default_factory=dict)


@dataclass
class UrbanLink:
    name: str
    frm: str
    to: str
    length_km: float = 0.5
    n_lanes: int = 2
    v_avg: float = 50.0
    L_veh: float = 6.0

    @property
    def storage_veh(self) -> float:
        return (self.length_km * 1000.0 / self.L_veh) * self.n_lanes


def _equal(*turns):
    share = 1.0 / len(turns)
    return {turn: share for turn in turns}


# Signalized intersections in Figure 3. Numeric ratios are placeholders.
# RAMP_ENTRY_SHARE is an implementation assumption: Zhai Fig. 3 defines ramp
# topology but not DUE turning proportions in this code-ready form. The share is
# split over the ramps at each interchange by Ramp.on_split.
RAMP_ENTRY_SHARE = 0.2


def _with_ramps(base_turns, ramp_splits):
    non_ramp_share = 1.0 - RAMP_ENTRY_SHARE
    turns = {name: share * non_ramp_share for name, share in base_turns.items()}
    for ramp_name, split in ramp_splits.items():
        turns[f"to_{ramp_name}"] = RAMP_ENTRY_SHARE * split
    return turns


TURNING = {
    ("A", "O1"): {"to_NA": 0.3, "to_B": 0.5, "to_D": 0.2},
    ("A", "NA"): {"to_O1": 0.3, "to_D": 0.4, "to_B": 0.3},
    ("A", "B"): {"to_NA": 0.3, "to_O1": 0.3, "to_D": 0.4},
    ("A", "D"): {"to_O1": 0.2, "to_NA": 0.7, "to_B": 0.1},
    ("C", "B"): {"to_NC": 0.3, "to_O2": 0.5, "to_F": 0.2},
    ("C", "NC"): {"to_B": 0.3, "to_F": 0.5, "to_O2": 0.2},
    ("C", "O2"): {"to_NC": 0.2, "to_B": 0.6, "to_F": 0.2},
    ("C", "F"): {"to_B": 0.1, "to_NC": 0.8, "to_O2": 0.1},
    ("D", "A"): _with_ramps(_equal("to_E", "to_O3"), {"R2": 0.4, "R3": 0.6}),
    ("D", "O3"): _with_ramps(_equal("to_A", "to_E"), {"R2": 0.4, "R3": 0.6}),
    ("D", "E"): _with_ramps(_equal("to_A", "to_O3"), {"R2": 0.4, "R3": 0.6}),
    ("F", "C"): _with_ramps(_equal("to_E", "to_O4"), {"R1": 0.5, "R4": 0.5}),
    ("F", "O4"): _with_ramps(_equal("to_C", "to_E"), {"R1": 0.5, "R4": 0.5}),
    ("F", "E"): _with_ramps(_equal("to_C", "to_O4"), {"R1": 0.5, "R4": 0.5}),
}

TURN_MAP = {
    ("A", "O1", "to_NA"): "NA",
    ("A", "O1", "to_B"): "B",
    ("A", "O1", "to_D"): "D",
    ("A", "NA", "to_B"): "B",
    ("A", "NA", "to_D"): "D",
    ("A", "NA", "to_O1"): "O1",
    ("A", "B", "to_NA"): "NA",
    ("A", "B", "to_O1"): "O1",
    ("A", "B", "to_D"): "D",
    ("A", "D", "to_O1"): "O1",
    ("A", "D", "to_B"): "B",
    ("A", "D", "to_NA"): "NA",
    ("C", "B", "to_NC"): "NC",
    ("C", "B", "to_O2"): "O2",
    ("C", "B", "to_F"): "F",
    ("C", "NC", "to_B"): "B",
    ("C", "NC", "to_F"): "F",
    ("C", "NC", "to_O2"): "O2",
    ("C", "O2", "to_NC"): "NC",
    ("C", "O2", "to_B"): "B",
    ("C", "O2", "to_F"): "F",
    ("C", "F", "to_O2"): "O2",
    ("C", "F", "to_B"): "B",
    ("C", "F", "to_NC"): "NC",    
    ("D", "A", "to_E"): "E",
    ("D", "A", "to_O3"): "O3",
    ("D", "A", "to_R2"): "R2",
    ("D", "A", "to_R3"): "R3",
    ("D", "O3", "to_A"): "A",
    ("D", "O3", "to_E"): "E",
    ("D", "O3", "to_R2"): "R2",
    ("D", "O3", "to_R3"): "R3",
    ("D", "E", "to_A"): "A",
    ("D", "E", "to_O3"): "O3",
    ("D", "E", "to_R2"): "R2",
    ("D", "E", "to_R3"): "R3",
    ("F", "C", "to_E"): "E",
    ("F", "C", "to_O4"): "O4",
    ("F", "C", "to_R1"): "R1",
    ("F", "C", "to_R4"): "R4",
    ("F", "O4", "to_C"): "C",
    ("F", "O4", "to_E"): "E",
    ("F", "O4", "to_R1"): "R1",
    ("F", "O4", "to_R4"): "R4",
    ("F", "E", "to_C"): "C",
    ("F", "E", "to_O4"): "O4",
    ("F", "E", "to_R1"): "R1",
    ("F", "E", "to_R4"): "R4",
}


def turn_to_leg(inter: str, approach: str, turn: str) -> str:
    leg = TURN_MAP[(inter, approach, turn)]
    if leg.startswith("R"):
        raise ValueError(
            f"{inter}/{approach}/{turn} is a ramp turn to {leg}, not an urban leg."
        )
    return leg


def turn_destination(inter: str, approach: str, turn: str):
    """Return ("urban", leg) or ("ramp", ramp_name) for a turn."""
    leg = TURN_MAP[(inter, approach, turn)]
    if leg.startswith("R"):
        return "ramp", leg
    return "urban", leg


@dataclass
class Ramp:
    name: str
    urban_node: str
    freeway: str
    on_split: float
    off_ratio: float
    length_km: float = 0.7
    n_lanes: int = 1
    Q_cap: float = 2000.0


RAMPS = [
    Ramp("R2", "D", "FW_W", on_split=0.4, off_ratio=0.1),
    Ramp("R1", "F", "FW_W", on_split=0.5, off_ratio=0.2),
    Ramp("R3", "D", "FW_E", on_split=0.6, off_ratio=0.1),
    Ramp("R4", "F", "FW_E", on_split=0.5, off_ratio=0.1),
]

@dataclass
class Network:
    freeways: Dict[str, FreewayLink] = field(default_factory=dict)
    urban_links: Dict[str, UrbanLink] = field(default_factory=dict)
    ramps: List[Ramp] = field(default_factory=list)
    signal_nodes: List[str] = field(default_factory=lambda: ["A", "C", "D", "F"])
    crossing_nodes: List[str] = field(default_factory=lambda: ["B", "E"])
    urban_origins: List[str] = field(default_factory=lambda: ["O1", "O2", "O3", "O4", "NA", "NB", "NC"])
    freeway_origins: List[str] = field(default_factory=lambda: ["D1", "D2"])


def build_network() -> Network:
    fw_w = FreewayLink(
        "FW_W", "WB", n_segments=3, origin="D1",
        on_ramp_seg=0, on_ramp_node="F",
        off_ramp_seg=2, off_ramp_node="D", off_ramp_ratio=0.1,
        on_ramp_segs={"R1": 0, "R2": 2},
        off_ramp_segs={"R1": 0, "R2": 2},
    )
    fw_e = FreewayLink(
        "FW_E", "EB", n_segments=3, origin="D2",
        on_ramp_seg=0, on_ramp_node="D",
        off_ramp_seg=2, off_ramp_node="F", off_ramp_ratio=0.1,
        on_ramp_segs={"R3": 0, "R4": 2},
        off_ramp_segs={"R3": 0, "R4": 2},
    )

    pairs = [
        ("O1", "A"), ("A", "O1"), ("A", "B"), ("B", "A"),
        ("B", "C"), ("C", "B"), ("C", "O2"), ("O2", "C"),
        ("NA", "A"), ("A", "NA"), ("NB", "B"), ("B", "NB"),
        ("NC", "C"), ("C", "NC"),
        ("A", "D"), ("D", "A"), ("B", "E"), ("E", "B"),
        ("C", "F"), ("F", "C"), ("D", "E"), ("E", "D"),
        ("E", "F"), ("F", "E"),
        ("O3", "D"), ("D", "O3"), ("O4", "F"), ("F", "O4"),
    ]
    ulinks = {f"{frm}->{to}": UrbanLink(f"{frm}->{to}", frm, to) for frm, to in pairs}

    return Network(
        freeways={"FW_W": fw_w, "FW_E": fw_e},
        urban_links=ulinks,
        ramps=list(RAMPS),
    )


if __name__ == "__main__":
    net = build_network()
    print("Signalized:", net.signal_nodes)
    print("Crossing-only:", net.crossing_nodes)
    print("Freeways:", [(k, v.direction) for k, v in net.freeways.items()])
    print("Urban links:", len(net.urban_links))
    print("Ramps:", [(r.name, r.urban_node, r.freeway) for r in net.ramps])


SIGNAL_PHASE = {
    "A": {"NA": 1, "D": 1, "O1": 2, "B": 2},
    "C": {"NC": 1, "F": 1, "B": 2, "O2": 2},
    "D": {"A": 1, "O3": 2, "E": 2},
    "F": {"C": 1, "O4": 2, "E": 2},
}
CORRIDORS = {"AD": ("A", "D"), "CF": ("C", "F")}
