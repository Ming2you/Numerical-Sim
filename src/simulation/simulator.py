from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.models.demand import DemandStep
from src.models.metanet import freeway_step
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import urban_step


@dataclass
class StepLog:
    step: int
    time_sec: float
    freeway_ttt: float
    urban_ttt: float
    diagnostics: Dict[str, Any] = field(default_factory=dict)


class MixedTrafficSimulator:
    def __init__(self, cfg: ExperimentConfig, initial_state: TrafficState | None = None):
        self.cfg = cfg
        self.state = initial_state.copy() if initial_state else TrafficState.initial(cfg)
        self.freeway_ttt = 0.0
        self.urban_ttt = 0.0
        self.logs: List[StepLog] = []

    def copy(self) -> "MixedTrafficSimulator":
        return copy.deepcopy(self)

    def step(self, control: ControlAction, demand: DemandStep, step_idx: int) -> StepLog:
        fw_ttt, fw_diag = freeway_step(self.state, control, demand, self.cfg)
        ur_ttt, ur_diag = urban_step(self.state, control, demand, self.cfg)
        self.state.time_sec += self.cfg.simulation.control_interval
        self.freeway_ttt += fw_ttt
        self.urban_ttt += ur_ttt
        diag = {**fw_diag, **ur_diag, **control.diagnostics}
        log = StepLog(
            step=step_idx,
            time_sec=self.state.time_sec,
            freeway_ttt=fw_ttt,
            urban_ttt=ur_ttt,
            diagnostics=diag,
        )
        self.logs.append(log)
        return log

    @property
    def total_ttt(self) -> float:
        return float(self.freeway_ttt + self.urban_ttt)


def state_row(state: TrafficState, cfg: ExperimentConfig, step: int) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "step": step,
        "time_sec": state.time_sec,
        "freeway_vehicles": state.total_freeway_vehicles(cfg.network),
        "urban_vehicles": state.total_urban_vehicles(),
    }
    for link, values in state.freeway_density.items():
        row[f"rho_{link}_mean"] = sum(values) / len(values)
    for link, values in state.freeway_speed.items():
        row[f"speed_{link}_mean"] = sum(values) / len(values)
    for ramp, value in state.ramp_queue.items():
        row[f"ramp_queue_{ramp}"] = value
    for link, value in state.boundary_queue.items():
        row[f"boundary_queue_{link}"] = value
    return row


def control_row(control: ControlAction, cfg: ExperimentConfig, step: int, time_sec: float) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "step": step,
        "time_sec": time_sec,
        "N_P_star": control.N_P_star,
        "N_UF_star": control.N_UF_star,
    }
    for ramp in cfg.network.ramps:
        row[f"ramp_metering_{ramp}"] = control.ramp_metering.get(ramp, 0.0)
    for link in cfg.network.freeway_links:
        row[f"vsl_{link}"] = control.vsl.get(link, max(cfg.freeway_follower.vsl_set))
    for signal in cfg.network.signals:
        row[f"green_{signal}_p1"] = control.green_times.get(f"{signal}_p1", 0.0)
        row[f"green_{signal}_p2"] = control.green_times.get(f"{signal}_p2", 0.0)
        row[f"offset_{signal}"] = control.offsets.get(signal, 0.0)
    for link in cfg.network.movement_links:
        row[f"allocation_{link}"] = control.inflow_outflow_allocation.get(link, 0.0)
    row.update({f"diag_{k}": v for k, v in control.diagnostics.items() if isinstance(v, (int, float, bool))})
    return row
