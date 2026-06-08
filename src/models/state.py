from __future__ import annotations

import copy
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


def _deep_update(base: Dict[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = _deep_update(dict(out[key]), value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_jsonish(path: str | Path) -> Dict[str, Any]:
    """Load JSON-compatible YAML without requiring PyYAML.

    The project config files are written as JSON, which is valid YAML. This
    helper keeps the runtime dependency-free while still accepting ordinary
    comments-free JSON/YAML scalars for small user edits.
    """
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} is not JSON-compatible YAML. Install PyYAML or keep the "
            "config in JSON/YAML subset syntax."
        ) from exc


@dataclass
class SimulationConfig:
    T_total: float = 7200.0
    T_f: float = 10.0
    T_u: float = 5.0
    control_interval: float = 180.0
    random_seed: int = 42

    @property
    def control_interval_h(self) -> float:
        return self.control_interval / 3600.0

    @property
    def n_control_steps(self) -> int:
        return max(1, int(math.ceil(self.T_total / self.control_interval)))


@dataclass
class NetworkConfig:
    freeway_links: List[str] = field(default_factory=lambda: ["FW_W", "FW_E"])
    freeway_segments_per_link: int = 3
    freeway_segment_length_km: float = 0.5
    freeway_lanes: int = 2
    v_free: float = 100.0
    rho_crit: float = 33.5
    rho_max: float = 180.0
    freeway_capacity_veh_h: float = 3600.0
    ramps: List[str] = field(default_factory=lambda: ["R1", "R2", "R3", "R4"])
    ramp_to_freeway: Dict[str, str] = field(default_factory=lambda: {
        "R1": "FW_W", "R2": "FW_W", "R3": "FW_E", "R4": "FW_E"
    })
    ramp_capacity_veh_h: Dict[str, float] = field(default_factory=lambda: {
        "R1": 1500.0, "R2": 1500.0, "R3": 1500.0, "R4": 1500.0
    })
    ramp_queue_max_veh: float = 180.0
    signals: List[str] = field(default_factory=lambda: ["A", "C", "D", "F"])
    cycle_length: float = 120.0
    lost_time: float = 8.0
    green_min: float = 20.0
    green_max: float = 92.0
    boundary_in_links: List[str] = field(default_factory=lambda: ["in_A", "in_C"])
    boundary_out_links: List[str] = field(default_factory=lambda: ["out_D", "out_F"])
    boundary_queue_max_veh: float = 240.0
    movement_capacity_veh_h: float = 1400.0

    @property
    def movement_links(self) -> List[str]:
        return list(self.boundary_in_links) + list(self.boundary_out_links)

    @property
    def total_ramp_capacity(self) -> float:
        return float(sum(self.ramp_capacity_veh_h[r] for r in self.ramps))

    @property
    def effective_green_total(self) -> float:
        return max(0.0, self.cycle_length - self.lost_time)


@dataclass
class MPCConfig:
    horizon_steps: int = 5
    leader_candidate_count: int = 15
    max_nash_iter: int = 10
    nash_obj_tol: float = 1.0e-3
    nash_control_tol: float = 1.0e-3
    nash_relaxation_alpha: float = 0.8


@dataclass
class LeaderConfig:
    objective_mode: str = "follower_ttt"
    w_P: float = 1.0
    w_F: float = 1.0
    w_L: float = 0.05
    N_P_star_range: List[float] = field(default_factory=lambda: [0.0, 500.0])
    N_UF_star_range: List[float] = field(default_factory=lambda: [0.0, 6000.0])
    non_convergence_penalty: float = 500.0


@dataclass
class FreewayFollowerConfig:
    eps_F: float = 100.0
    vsl_set: List[float] = field(default_factory=lambda: [50, 60, 70, 80, 90, 100])
    max_vsl_step: float = 20.0
    ramp_queue_penalty: float = 10.0
    density_penalty: float = 10.0
    metering_smoothness_weight: float = 0.1
    vsl_smoothness_weight: float = 0.1


@dataclass
class UrbanFollowerConfig:
    eps_U: float = 100.0
    eps_g: float = 5.0
    max_offset_step: float = 15.0
    boundary_balance_weight: float = 10.0
    offset_smoothness_weight: float = 0.1
    green_smoothness_weight: float = 0.1
    receiving_space_rule: str = "proportional"


@dataclass
class EvaluationConfig:
    main_metric: str = "total_ttt"
    main_metric_direction: str = "lower_is_better"
    min_improvement_pct: float = 8.0
    eps: float = 1.0e-9


@dataclass
class AutoTuningConfig:
    enabled: bool = True
    max_iterations: int = 5
    preserve_all_runs: bool = True


@dataclass
class ExperimentConfig:
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    mpc: MPCConfig = field(default_factory=MPCConfig)
    leader: LeaderConfig = field(default_factory=LeaderConfig)
    freeway_follower: FreewayFollowerConfig = field(default_factory=FreewayFollowerConfig)
    urban_follower: UrbanFollowerConfig = field(default_factory=UrbanFollowerConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    auto_tuning: AutoTuningConfig = field(default_factory=AutoTuningConfig)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ExperimentConfig":
        return cls(
            simulation=SimulationConfig(**raw.get("simulation", {})),
            network=NetworkConfig(**raw.get("network", {})),
            mpc=MPCConfig(**raw.get("mpc", {})),
            leader=LeaderConfig(**raw.get("leader", {})),
            freeway_follower=FreewayFollowerConfig(**raw.get("freeway_follower", {})),
            urban_follower=UrbanFollowerConfig(**raw.get("urban_follower", {})),
            evaluation=EvaluationConfig(**raw.get("evaluation", {})),
            auto_tuning=AutoTuningConfig(**raw.get("auto_tuning", {})),
        )

    @classmethod
    def from_file(cls, path: str | Path, overrides: Optional[Mapping[str, Any]] = None) -> "ExperimentConfig":
        raw = load_jsonish(path)
        if overrides:
            raw = _deep_update(raw, overrides)
        return cls.from_dict(raw)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def with_updates(self, updates: Mapping[str, Any]) -> "ExperimentConfig":
        return ExperimentConfig.from_dict(_deep_update(self.to_dict(), updates))


@dataclass
class TrafficState:
    freeway_density: Dict[str, List[float]]
    freeway_speed: Dict[str, List[float]]
    ramp_queue: Dict[str, float]
    urban_queue: Dict[str, float]
    boundary_queue: Dict[str, float]
    time_sec: float = 0.0

    @classmethod
    def initial(cls, cfg: ExperimentConfig) -> "TrafficState":
        net = cfg.network
        density = {
            link: [18.0 for _ in range(net.freeway_segments_per_link)]
            for link in net.freeway_links
        }
        speed = {
            link: [net.v_free for _ in range(net.freeway_segments_per_link)]
            for link in net.freeway_links
        }
        return cls(
            freeway_density=density,
            freeway_speed=speed,
            ramp_queue={r: 0.0 for r in net.ramps},
            urban_queue={m: 20.0 for m in net.movement_links},
            boundary_queue={m: 20.0 for m in net.movement_links},
        )

    def copy(self) -> "TrafficState":
        return copy.deepcopy(self)

    def total_freeway_vehicles(self, net: NetworkConfig) -> float:
        return float(sum(
            sum(rhos) * net.freeway_segment_length_km * net.freeway_lanes
            for rhos in self.freeway_density.values()
        ) + sum(self.ramp_queue.values()))

    def total_urban_vehicles(self) -> float:
        return float(sum(self.urban_queue.values()) + sum(self.boundary_queue.values()))

    def boundary_vector(self) -> List[float]:
        return [float(v) for v in self.boundary_queue.values()]


@dataclass
class ControlAction:
    N_P_star: float = 0.0
    N_UF_star: float = 0.0
    ramp_metering: Dict[str, float] = field(default_factory=dict)
    vsl: Dict[str, float] = field(default_factory=dict)
    green_times: Dict[str, float] = field(default_factory=dict)
    offsets: Dict[str, float] = field(default_factory=dict)
    inflow_outflow_allocation: Dict[str, float] = field(default_factory=dict)
    infeasibility: Dict[str, float] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def fixed(cls, cfg: ExperimentConfig) -> "ControlAction":
        net = cfg.network
        green = {}
        phase_green = net.effective_green_total / 2.0
        for signal in net.signals:
            green[f"{signal}_p1"] = phase_green
            green[f"{signal}_p2"] = phase_green
        return cls(
            ramp_metering={r: net.ramp_capacity_veh_h[r] for r in net.ramps},
            vsl={link: max(cfg.freeway_follower.vsl_set) for link in net.freeway_links},
            green_times=green,
            offsets={signal: 0.0 for signal in net.signals},
            inflow_outflow_allocation={m: net.movement_capacity_veh_h * 0.5 for m in net.movement_links},
        )

    def control_vector(self, cfg: ExperimentConfig) -> List[float]:
        net = cfg.network
        return (
            [self.ramp_metering.get(r, 0.0) for r in net.ramps]
            + [self.vsl.get(link, max(cfg.freeway_follower.vsl_set)) for link in net.freeway_links]
            + [self.green_times.get(f"{s}_p1", 0.0) for s in net.signals]
            + [self.offsets.get(s, 0.0) for s in net.signals]
            + [self.inflow_outflow_allocation.get(m, 0.0) for m in net.movement_links]
        )


@dataclass
class EvaluationResult:
    metrics: Dict[str, float]
    improvement_pct: float
    passed: bool
    control_validation: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosticResult:
    failure_modes: List[str]
    suggestions: List[str]
    dominant_failure_mode: str = "none"


def mean(values: Iterable[float], default: float = 0.0) -> float:
    values = list(values)
    return float(sum(values) / len(values)) if values else default
