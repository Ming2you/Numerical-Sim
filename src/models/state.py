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


def _is_integer_ratio(numerator: float, denominator: float, eps: float = 1.0e-9) -> bool:
    ratio = numerator / denominator
    return abs(ratio - round(ratio)) <= eps


def load_jsonish(path: str | Path) -> Dict[str, Any]:
    """Load project config from JSON-compatible YAML or a small YAML subset.

    The runtime intentionally has no PyYAML dependency. JSON remains the
    preferred fully structured format, and the fallback supports the simple
    mapping/list/scalar YAML used by the repository config files.
    """
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        parsed = _load_simple_yaml(text)
        if not isinstance(parsed, dict):
            raise ValueError(f"{path} must contain a mapping at the top level.")
        return parsed


def _load_simple_yaml(text: str) -> Any:
    def parse_scalar(value: str) -> Any:
        value = value.strip()
        if value == "":
            return ""
        if value in ("true", "True"):
            return True
        if value in ("false", "False"):
            return False
        if value in ("null", "None", "~"):
            return None
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        try:
            if any(c in value for c in (".", "e", "E")):
                return float(value)
            return int(value)
        except ValueError:
            return value

    rows: List[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        rows.append((indent, stripped))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(rows):
            return {}, index
        if rows[index][0] < indent:
            return {}, index
        is_list = rows[index][1].startswith("- ")
        if is_list:
            values: List[Any] = []
            while index < len(rows) and rows[index][0] == indent and rows[index][1].startswith("- "):
                item = rows[index][1][2:].strip()
                if item:
                    values.append(parse_scalar(item))
                    index += 1
                else:
                    nested_indent = rows[index + 1][0] if index + 1 < len(rows) else indent + 2
                    value, index = parse_block(index + 1, nested_indent)
                    values.append(value)
            return values, index

        values: Dict[str, Any] = {}
        while index < len(rows) and rows[index][0] == indent and not rows[index][1].startswith("- "):
            key, sep, rest = rows[index][1].partition(":")
            if not sep:
                raise ValueError(f"Unsupported YAML line: {rows[index][1]}")
            key = key.strip()
            rest = rest.strip()
            if rest:
                values[key] = parse_scalar(rest)
                index += 1
            else:
                nested_indent = rows[index + 1][0] if index + 1 < len(rows) else indent + 2
                value, index = parse_block(index + 1, nested_indent)
                values[key] = value
        return values, index

    parsed, end = parse_block(0, rows[0][0] if rows else 0)
    if end != len(rows):
        raise ValueError("Unsupported YAML indentation or mixed collection structure.")
    return parsed


@dataclass
class SimulationConfig:
    T_total: float = 7200.0
    T_f: float = 10.0
    T_u: float = 5.0
    control_interval: float = 180.0
    random_seed: int = 42
    unit_time: str = "seconds"
    unit_flow: str = "veh/h"
    unit_speed: str = "km/h"
    unit_density: str = "veh/km/lane"
    derived_time_ratios: Dict[str, float] = field(default_factory=dict)

    @property
    def T_f_sec(self) -> float:
        return self.T_f

    @property
    def T_u_sec(self) -> float:
        return self.T_u

    @property
    def T_c_sec(self) -> float:
        return self.control_interval

    @property
    def T_f_h(self) -> float:
        return self.T_f_sec / 3600.0

    @property
    def T_u_h(self) -> float:
        return self.T_u_sec / 3600.0

    @property
    def T_c_h(self) -> float:
        return self.T_c_sec / 3600.0

    @property
    def control_interval_h(self) -> float:
        return self.T_c_h

    @property
    def n_control_steps(self) -> int:
        return max(1, int(math.ceil(self.T_total / self.T_c_sec)))

    @property
    def K_fu(self) -> int:
        return int(round(self.T_f_sec / self.T_u_sec))

    @property
    def K_cf(self) -> int:
        return int(round(self.T_c_sec / self.T_f_sec))

    @property
    def K_cu(self) -> int:
        return int(round(self.T_c_sec / self.T_u_sec))

    def validate(self) -> None:
        if min(self.T_f_sec, self.T_u_sec, self.T_c_sec) <= 0.0:
            raise ValueError("T_f, T_u, and control_interval must be positive.")
        if not _is_integer_ratio(self.T_f_sec, self.T_u_sec):
            raise ValueError("T_f must be an integer multiple of T_u.")
        if not _is_integer_ratio(self.T_c_sec, self.T_f_sec):
            raise ValueError("control_interval must be an integer multiple of T_f.")


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
    urban_movements: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "in_A_to_out_D": {
            "origin": "in_A", "signal": "A", "destination": "out_D",
            "receiving_link": "A_out_D", "phase": "A_p1", "kind": "boundary_in",
        },
        "in_C_to_out_F": {
            "origin": "in_C", "signal": "C", "destination": "out_F",
            "receiving_link": "C_out_F", "phase": "C_p1", "kind": "boundary_in",
        },
        "R1_onramp": {
            "origin": "A", "signal": "R1", "destination": "FW_W",
            "receiving_link": "A_R1", "phase": "A_p2", "kind": "on_ramp", "ramp": "R1",
        },
        "R2_onramp": {
            "origin": "C", "signal": "R2", "destination": "FW_W",
            "receiving_link": "C_R2", "phase": "C_p2", "kind": "on_ramp", "ramp": "R2",
        },
        "R3_onramp": {
            "origin": "D", "signal": "R3", "destination": "FW_E",
            "receiving_link": "D_R3", "phase": "D_p2", "kind": "on_ramp", "ramp": "R3",
        },
        "R4_onramp": {
            "origin": "F", "signal": "R4", "destination": "FW_E",
            "receiving_link": "F_R4", "phase": "F_p2", "kind": "on_ramp", "ramp": "R4",
        },
        "OR_W_to_out_D": {
            "origin": "OR_W", "signal": "D", "destination": "out_D",
            "receiving_link": "D_out_D", "phase": "D_p1", "kind": "off_ramp", "off_ramp": "OR_W",
        },
        "OR_E_to_out_F": {
            "origin": "OR_E", "signal": "F", "destination": "out_F",
            "receiving_link": "F_out_F", "phase": "F_p1", "kind": "off_ramp", "off_ramp": "OR_E",
        },
    })
    urban_link_storage_veh: Dict[str, float] = field(default_factory=lambda: {
        "A_out_D": 220.0,
        "C_out_F": 220.0,
        "A_R1": 180.0,
        "C_R2": 180.0,
        "D_R3": 180.0,
        "F_R4": 180.0,
        "OR_W_D": 120.0,
        "OR_E_F": 120.0,
        "D_out_D": 220.0,
        "F_out_F": 220.0,
    })
    on_ramp_to_movement: Dict[str, str] = field(default_factory=lambda: {
        "R1": "R1_onramp",
        "R2": "R2_onramp",
        "R3": "R3_onramp",
        "R4": "R4_onramp",
    })
    off_ramps: List[str] = field(default_factory=lambda: ["OR_W", "OR_E"])
    off_ramp_from_freeway: Dict[str, str] = field(default_factory=lambda: {
        "OR_W": "FW_W",
        "OR_E": "FW_E",
    })
    off_ramp_storage_link: Dict[str, str] = field(default_factory=lambda: {
        "OR_W": "OR_W_D",
        "OR_E": "OR_E_F",
    })
    off_ramp_to_movement: Dict[str, str] = field(default_factory=lambda: {
        "OR_W": "OR_W_to_out_D",
        "OR_E": "OR_E_to_out_F",
    })
    off_ramp_split_ratio: Dict[str, float] = field(default_factory=lambda: {
        "OR_W": 0.12,
        "OR_E": 0.12,
    })
    v_min: float = 5.0
    alpha_vsl: float = 0.0
    metanet_tau_h: float = 0.005
    metanet_tau_sec: float = 18.0
    metanet_nu_km2_h: float = 65.0
    metanet_kappa_veh_km_lane: float = 40.0
    metanet_a_m: float = 1.867
    metanet_rho_eps: float = 0.001
    urban_Q_sat_veh_h: float = 1000.0
    urban_avg_vehicle_length_m: float = 6.0
    urban_avg_speed_km_h: float = 50.0
    green_min_fraction: float = 0.2
    green_max_fraction: float = 0.8

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
class CapacityDropConfig:
    enabled: bool = True
    lane_reduction: float = 0.35
    gamma: float = 0.5
    b: float = 2.0


@dataclass
class MPCConfig:
    horizon_steps: int = 3
    leader_candidate_count: int = 15
    follower_solver_mode: str = "two_block"
    max_nash_iter: int = 10
    nash_obj_tol: float = 1.0e-3
    nash_control_tol: float = 1.0e-3
    nash_relaxation_alpha: float = 0.8
    distributed_coupling_tol: float = 1.0e-3
    control_horizon_steps: int = 3
    urban_freeway_tts_weight_alpha: float = 1.0
    optimizer_maxiter: int = 40
    optimizer_n_starts: int = 2


@dataclass
class LeaderConfig:
    objective_mode: str = "state_accumulation"
    w_P: float = 1.0
    w_F: float = 1.0
    w_L: float = 0.05
    N_P_star_range: List[float] = field(default_factory=lambda: [0.0, 500.0])
    N_UF_star_range: List[float] = field(default_factory=lambda: [0.0, 6000.0])
    N_P_crit_veh: float = 172.2252769877888
    N_P_candidate_lower_factor: float = 0.90
    N_P_candidate_upper_factor: float = 1.05
    N_P_star_unit: str = "veh"
    N_UF_star_unit: str = "veh_per_hour"
    N_P_feedback_horizon_h: float = 0.5
    N_P_feedback_flow_limit_veh_h: float = 800.0
    N_UF_feasible_margin: float = 0.95
    non_convergence_penalty: float = 500.0
    metering_congestion_weight: float = 0.45
    metering_queue_weight: float = 4.0
    vsl_activation_density_ratio: float = 0.95
    metering_activation_density_ratio: float = 0.95


@dataclass
class FreewayFollowerConfig:
    eps_F: float = 100.0
    vsl_set: List[float] = field(default_factory=lambda: [50, 60, 70, 80, 90, 100])
    max_vsl_step: float = 20.0
    ramp_queue_penalty: float = 10.0
    density_penalty: float = 10.0
    metering_smoothness_weight: float = 0.1
    vsl_smoothness_weight: float = 0.1
    horizon_beam_width: int = 2
    horizon_ramp_candidate_limit: int = 3
    horizon_vsl_candidate_limit_per_link: int = 3
    ramp_metering_rate_min: float = 0.2
    ramp_metering_rate_max: float = 1.0
    vsl_min_km_h: float = 60.0
    vsl_max_km_h: float = 106.0


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
    freeway_offramp_capacity_drop: CapacityDropConfig = field(default_factory=CapacityDropConfig)
    mpc: MPCConfig = field(default_factory=MPCConfig)
    leader: LeaderConfig = field(default_factory=LeaderConfig)
    freeway_follower: FreewayFollowerConfig = field(default_factory=FreewayFollowerConfig)
    urban_follower: UrbanFollowerConfig = field(default_factory=UrbanFollowerConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    auto_tuning: AutoTuningConfig = field(default_factory=AutoTuningConfig)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ExperimentConfig":
        cfg = cls(
            simulation=SimulationConfig(**raw.get("simulation", {})),
            network=NetworkConfig(**raw.get("network", {})),
            freeway_offramp_capacity_drop=CapacityDropConfig(**raw.get("freeway_offramp_capacity_drop", {})),
            mpc=MPCConfig(**raw.get("mpc", {})),
            leader=LeaderConfig(**raw.get("leader", {})),
            freeway_follower=FreewayFollowerConfig(**raw.get("freeway_follower", {})),
            urban_follower=UrbanFollowerConfig(**raw.get("urban_follower", {})),
            evaluation=EvaluationConfig(**raw.get("evaluation", {})),
            auto_tuning=AutoTuningConfig(**raw.get("auto_tuning", {})),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        self.simulation.validate()
        if self.mpc.follower_solver_mode not in {"two_block", "distributed"}:
            raise ValueError("mpc.follower_solver_mode must be two_block or distributed.")
        if self.mpc.distributed_coupling_tol <= 0.0:
            raise ValueError("mpc.distributed_coupling_tol must be positive.")
        cap_drop = self.freeway_offramp_capacity_drop
        if cap_drop.lane_reduction < 0.0:
            raise ValueError("freeway_offramp_capacity_drop.lane_reduction must be non-negative.")
        if cap_drop.lane_reduction >= self.network.freeway_lanes:
            raise ValueError("freeway_offramp_capacity_drop.lane_reduction must be less than freeway_lanes.")
        if cap_drop.gamma <= 0.0:
            raise ValueError("freeway_offramp_capacity_drop.gamma must be positive.")
        if cap_drop.b <= 0.0:
            raise ValueError("freeway_offramp_capacity_drop.b must be positive.")
        if self.leader.objective_mode not in {"state_accumulation", "follower_ttt"}:
            raise ValueError("leader.objective_mode must be state_accumulation or follower_ttt.")
        if self.leader.N_P_star_unit != "veh":
            raise ValueError("leader.N_P_star_unit must be veh.")
        if self.leader.N_P_crit_veh <= 0.0:
            raise ValueError("leader.N_P_crit_veh must be positive.")
        if self.leader.N_P_candidate_lower_factor <= 0.0:
            raise ValueError("leader.N_P_candidate_lower_factor must be positive.")
        if self.leader.N_P_candidate_upper_factor < self.leader.N_P_candidate_lower_factor:
            raise ValueError("leader.N_P_candidate_upper_factor must be >= lower factor.")
        if self.leader.N_UF_star_unit not in {"veh_per_hour", "veh_per_control_interval"}:
            raise ValueError("leader.N_UF_star_unit must be veh_per_hour or veh_per_control_interval.")

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
    freeway_flow: Dict[str, List[float]]
    ramp_queue: Dict[str, float]
    urban_queue: Dict[str, float]
    boundary_queue: Dict[str, float]
    freeway_effective_lanes: Dict[str, List[float]] = field(default_factory=dict)
    urban_movement_queue: Dict[str, float] = field(default_factory=dict)
    urban_link_storage: Dict[str, float] = field(default_factory=dict)
    urban_arrival_buffer: Dict[str, Dict[int, float]] = field(default_factory=dict)
    urban_storage_release_buffer: Dict[str, Dict[int, float]] = field(default_factory=dict)
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
        flow = {
            link: [
                max(0.0, density[link][i]) * max(0.0, speed[link][i]) * max(0.0, net.freeway_lanes)
                for i in range(net.freeway_segments_per_link)
            ]
            for link in net.freeway_links
        }
        lanes = {
            link: [float(net.freeway_lanes) for _ in range(net.freeway_segments_per_link)]
            for link in net.freeway_links
        }
        return cls(
            freeway_density=density,
            freeway_speed=speed,
            freeway_flow=flow,
            ramp_queue={r: 0.0 for r in net.ramps},
            urban_queue={m: 20.0 for m in net.movement_links},
            boundary_queue={m: 20.0 for m in net.movement_links},
            freeway_effective_lanes=lanes,
            urban_movement_queue={
                movement: (0.0 if spec.get("kind") == "on_ramp" else 20.0)
                for movement, spec in net.urban_movements.items()
            },
            urban_link_storage=dict(net.urban_link_storage_veh),
            urban_arrival_buffer={movement: {} for movement in net.urban_movements},
            urban_storage_release_buffer={link: {} for link in net.urban_link_storage_veh},
        )

    def copy(self) -> "TrafficState":
        return copy.deepcopy(self)

    def ensure_freeway_lane_profile(self, net: NetworkConfig) -> None:
        for link in net.freeway_links:
            count = len(self.freeway_density.get(link, []))
            lanes = self.freeway_effective_lanes.get(link, [])
            if len(lanes) != count:
                self.freeway_effective_lanes[link] = [float(net.freeway_lanes) for _ in range(count)]

    def freeway_vehicle_count_by_link(self, net: NetworkConfig) -> Dict[str, List[float]]:
        self.ensure_freeway_lane_profile(net)
        out: Dict[str, List[float]] = {}
        for link in net.freeway_links:
            out[link] = [
                max(0.0, rho) * net.freeway_segment_length_km * max(lane, 1.0e-9)
                for rho, lane in zip(
                    self.freeway_density.get(link, []),
                    self.freeway_effective_lanes.get(link, []),
                )
            ]
        return out

    def refresh_freeway_flow(self, net: NetworkConfig) -> None:
        self.ensure_freeway_lane_profile(net)
        self.freeway_flow = {
            link: [
                max(0.0, rho) * max(0.0, speed) * max(0.0, lane)
                for rho, speed, lane in zip(
                    self.freeway_density.get(link, []),
                    self.freeway_speed.get(link, []),
                    self.freeway_effective_lanes.get(link, []),
                )
            ]
            for link in net.freeway_links
        }

    def total_freeway_vehicles(self, net: NetworkConfig) -> float:
        self.ensure_freeway_lane_profile(net)
        return float(sum(
            sum(
                max(0.0, rho) * net.freeway_segment_length_km * max(lane, 1.0e-9)
                for rho, lane in zip(
                    self.freeway_density.get(link, []),
                    self.freeway_effective_lanes.get(link, []),
                )
            )
            for link in net.freeway_links
        ) + sum(self.ramp_queue.values()))

    def total_urban_vehicles(self) -> float:
        if self.urban_movement_queue:
            return float(sum(self.urban_movement_queue.values()))
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
        allocation = {m: net.movement_capacity_veh_h * 0.5 for m in net.movement_links}
        allocation.update({
            movement: net.movement_capacity_veh_h * 0.5
            for movement in net.urban_movements
        })
        return cls(
            ramp_metering={r: net.ramp_capacity_veh_h[r] for r in net.ramps},
            vsl={link: max(cfg.freeway_follower.vsl_set) for link in net.freeway_links},
            green_times=green,
            offsets={signal: 0.0 for signal in net.signals},
            inflow_outflow_allocation=allocation,
        )

    def control_vector(self, cfg: ExperimentConfig) -> List[float]:
        net = cfg.network
        return (
            [self.ramp_metering.get(r, 0.0) for r in net.ramps]
            + [self.vsl.get(link, max(cfg.freeway_follower.vsl_set)) for link in net.freeway_links]
            + [self.green_times.get(f"{s}_p1", 0.0) for s in net.signals]
            + [self.offsets.get(s, 0.0) for s in net.signals]
            + [self.inflow_outflow_allocation.get(m, 0.0) for m in net.movement_links]
            + [self.inflow_outflow_allocation.get(m, 0.0) for m in net.urban_movements]
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
