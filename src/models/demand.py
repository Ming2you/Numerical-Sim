from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional

from .state import ExperimentConfig, load_jsonish


@dataclass
class DemandStep:
    freeway_mainline: Dict[str, float]
    urban_boundary: Dict[str, float]
    ramp_arrival: Dict[str, float]
    incident_capacity_factor: float = 1.0


@dataclass
class ScenarioConfig:
    name: str
    urban_scale: float = 1.0
    freeway_scale: float = 1.0
    ramp_scale: float = 1.0
    incident_capacity_factor: float = 1.0
    required: bool = False
    # off-ramp split ratio를 이 시나리오에서만 덮어쓴다(None이면 NetworkConfig 0.06 유지).
    # capacity-drop 유발 무대를 만들기 위한 시나리오 한정 주입 — plant 보존식은 불변.
    off_ramp_split_ratio_override: Optional[Dict[str, float]] = None
    metadata: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, name: str, raw: Mapping[str, object]) -> "ScenarioConfig":
        known = {
            "urban_scale": float(raw.get("urban_scale", 1.0)),
            "freeway_scale": float(raw.get("freeway_scale", 1.0)),
            "ramp_scale": float(raw.get("ramp_scale", 1.0)),
            "incident_capacity_factor": float(raw.get("incident_capacity_factor", 1.0)),
            "required": bool(raw.get("required", False)),
        }
        raw_override = raw.get("off_ramp_split_ratio_override")
        if isinstance(raw_override, Mapping):
            known["off_ramp_split_ratio_override"] = {
                str(k): float(v) for k, v in raw_override.items()
            }
        return cls(name=name, **known)


def load_scenarios(path: str | Path) -> Dict[str, ScenarioConfig]:
    raw = load_jsonish(path)
    scenarios = raw.get("scenarios", raw)
    return {
        name: ScenarioConfig.from_mapping(name, value)
        for name, value in scenarios.items()
    }


def apply_scenario_network_overrides(
    cfg: ExperimentConfig, scenario: ScenarioConfig
) -> ExperimentConfig:
    """시나리오의 network 단위 override(off-ramp split)를 cfg에 반영한 새 cfg를 반환한다.

    off_ramp_split_ratio는 plant·모든 controller가 단일하게 cfg.network에서 읽으므로,
    여기서 한 번만 덮어쓰면 모든 사용처에 일관 적용된다. override가 None이면 cfg를 그대로
    반환(기존 0.06 동작 유지). 차량보존식·β합류 로직은 건드리지 않고 split 값만 주입한다."""
    override = scenario.off_ramp_split_ratio_override
    if not override:
        return cfg
    merged = dict(cfg.network.off_ramp_split_ratio)
    merged.update({str(k): float(v) for k, v in override.items()})
    return cfg.with_updates({"network": {"off_ramp_split_ratio": merged}})


class DemandProfile:
    """Deterministic demand generator with a mild peak wave."""

    def __init__(self, cfg: ExperimentConfig, scenario: ScenarioConfig):
        self.cfg = cfg
        self.scenario = scenario

    def at(self, time_sec: float) -> DemandStep:
        sim = self.cfg.simulation
        net = self.cfg.network
        x = time_sec / max(sim.T_total, 1.0)
        peak = 1.0 + 0.22 * math.sin(math.pi * min(max(x, 0.0), 1.0))

        freeway_base = 1650.0 * self.scenario.freeway_scale * peak
        ramp_base = 560.0 * self.scenario.ramp_scale * peak
        urban_base = 500.0 * self.scenario.urban_scale * peak

        freeway = {
            link: freeway_base * (1.0 + 0.05 * idx)
            for idx, link in enumerate(net.freeway_links)
        }
        urban = {}
        for idx, link in enumerate(net.boundary_in_links):
            urban[link] = urban_base * (1.0 + 0.10 * idx)
        for idx, link in enumerate(net.boundary_out_links):
            urban[link] = urban_base * (0.82 + 0.08 * idx)
        ramp = {
            ramp_name: ramp_base * (1.0 + 0.05 * idx)
            for idx, ramp_name in enumerate(net.ramps)
        }
        return DemandStep(
            freeway_mainline=freeway,
            urban_boundary=urban,
            ramp_arrival=ramp,
            incident_capacity_factor=self.scenario.incident_capacity_factor,
        )

    def horizon(self, start_time_sec: float, steps: int) -> list[DemandStep]:
        dt = self.cfg.simulation.control_interval
        return [self.at(start_time_sec + i * dt) for i in range(max(1, steps))]
