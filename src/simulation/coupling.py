from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from src.models.demand import DemandStep
from src.models.metanet import freeway_step
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    off_ramp_capacity_by_freeway_link,
    schedule_offramp_arrivals,
    sync_onramp_queues_from_freeway,
    sync_onramp_queues_to_freeway,
    urban_step,
)


@dataclass
class CoupledStepResult:
    freeway_ttt: float
    urban_ttt: float
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def run_coupled_interval(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
) -> CoupledStepResult:
    """Run one controller interval through the urban/freeway coupling point."""
    sync_onramp_queues_from_freeway(state, cfg)
    ur_ttt, ur_diag = urban_step(state, control, demand, cfg)
    sync_onramp_queues_to_freeway(state, cfg)

    offramp_capacity = off_ramp_capacity_by_freeway_link(state, cfg)
    fw_ttt, fw_diag = freeway_step(
        state,
        control,
        demand,
        cfg,
        offramp_capacity_veh_h=offramp_capacity,
    )

    next_urban_step = int(round(state.time_sec / max(cfg.simulation.T_u_sec, 1.0e-9))) + cfg.simulation.K_cu
    accepted_offramp = 0.0
    rejected_offramp = 0.0
    for off_ramp in cfg.network.off_ramps:
        link = cfg.network.off_ramp_from_freeway[off_ramp]
        link_ratio_total = sum(
            ratio
            for candidate, ratio in cfg.network.off_ramp_split_ratio.items()
            if cfg.network.off_ramp_from_freeway.get(candidate) == link
        )
        share = cfg.network.off_ramp_split_ratio.get(off_ramp, 0.0) / max(link_ratio_total, 1.0e-9)
        flow = fw_diag.get(f"offramp_flow_{link}", 0.0) * share
        vehicles = flow * cfg.simulation.T_c_h
        accepted, rejected = schedule_offramp_arrivals(state, cfg, off_ramp, vehicles, next_urban_step)
        accepted_offramp += accepted
        rejected_offramp += rejected
    sync_onramp_queues_from_freeway(state, cfg)

    diagnostics: Dict[str, Any] = {
        "coupling_freeway_substeps": float(cfg.simulation.K_cf),
        "coupling_urban_substeps": float(cfg.simulation.K_cu),
        "coupling_onramp_sync_active": 1.0,
        "coupling_offramp_storage_active": 1.0,
        "coupling_aggregate_urban_model": 0.0,
        "coupling_movement_urban_model": 1.0,
        "coupling_offramp_arrivals_accepted_veh": float(accepted_offramp),
        "coupling_offramp_arrivals_rejected_veh": float(rejected_offramp),
    }
    diagnostics.update(fw_diag)
    diagnostics.update(ur_diag)
    return CoupledStepResult(
        freeway_ttt=float(fw_ttt),
        urban_ttt=float(ur_ttt),
        diagnostics=diagnostics,
    )
