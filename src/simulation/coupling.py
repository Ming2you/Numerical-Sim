from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from src.models.demand import DemandStep
from src.models.metanet import compute_ramp_release_flows, freeway_substep
from src.models.state import ControlAction, ExperimentConfig, TrafficState
from src.models.urban_queue_model import (
    aggregate_urban_diagnostics,
    off_ramp_capacity_by_freeway_link,
    schedule_offramp_arrivals,
    sync_onramp_queues_from_freeway,
    sync_onramp_queues_to_freeway,
    urban_substep,
)


@dataclass
class CoupledStepResult:
    freeway_ttt: float
    urban_ttt: float
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def _aggregate_freeway_diagnostics(rows: list[Dict[str, float]]) -> Dict[str, float]:
    """`freeway_substep` diagnostics를 control interval 기준으로 묶는다."""
    if not rows:
        return {}
    avg_keys = {
        "total_metering_flow",
        "total_metering_error",
        "mean_ramp_receiving_factor",
        "mean_segment_flow",
        "offramp_flow_total",
        "offramp_blocked_flow_total",
    }
    out: Dict[str, float] = {}
    keys = set().union(*(row.keys() for row in rows))
    for key in keys:
        values = [float(row.get(key, 0.0)) for row in rows]
        if (
            key in avg_keys
            or key.startswith("offramp_flow_")
            or key.startswith("offramp_blocked_flow_")
            or key.startswith("lambda_eff_")
            or key.startswith("capacity_drop_lane_loss_")
            or key.startswith("offramp_occupancy_ratio_")
        ):
            out[key] = float(sum(values) / max(len(values), 1))
        elif key in {"metering_target_infeasible", "offramp_storage_binding", "capacity_drop_active"}:
            out[key] = float(max(values))
        else:
            out[key] = float(sum(values))
    return out


def _actual_ramp_release_flows(
    rows: list[Dict[str, float]],
    cfg: ExperimentConfig,
) -> Dict[str, float]:
    """이번 T_f 안에서 w_r에서 실제로 빠진 metering 차량만 freeway 유입으로 사용한다."""
    interval_h = cfg.simulation.T_f_h
    return {
        ramp: float(sum(
            row.get(f"ramp_metering_release_actual_{ramp}_veh", 0.0)
            for row in rows
        ) / max(interval_h, 1.0e-9))
        for ramp in cfg.network.ramps
    }


def _with_actual_ramp_diagnostics(
    requested_diag: Dict[str, float],
    actual_release: Dict[str, float],
) -> Dict[str, float]:
    diag = dict(requested_diag)
    actual_total = float(sum(actual_release.values()))
    diag["total_metering_flow"] = actual_total
    diag["total_no_meter_flow"] = float(max(
        requested_diag.get("total_no_meter_flow", 0.0),
        actual_total,
    ))
    return diag


def run_coupled_interval(
    state: TrafficState,
    control: ControlAction,
    demand: DemandStep,
    cfg: ExperimentConfig,
) -> CoupledStepResult:
    """Spec 3.4.3의 `T_c -> T_f -> T_u` nested order로 한 control interval을 전진한다."""
    sim = cfg.simulation
    sync_onramp_queues_from_freeway(state, cfg)

    freeway_ttt = 0.0
    urban_ttt = 0.0
    freeway_rows: list[Dict[str, float]] = []
    urban_rows: list[Dict[str, float]] = []
    accepted_offramp = 0.0
    rejected_offramp = 0.0
    start_urban_step = int(round(state.time_sec / max(sim.T_u_sec, 1.0e-9)))

    for freeway_substep_index in range(sim.K_cf):
        # 2저수지 구조에서는 현재 ramp 저수지 w_r만 이번 T_f의 metering release 후보가 된다.
        sync_onramp_queues_to_freeway(state, cfg)
        ramp_release, ramp_diag = compute_ramp_release_flows(
            state,
            control,
            demand,
            cfg,
            include_current_arrivals=False,
        )

        # freeway 한 스텝 사이에 들어있는 urban substep들을 먼저 진행해 off-ramp storage 여유를 갱신한다.
        urban_rows_in_freeway_step: list[Dict[str, float]] = []
        for urban_offset in range(sim.K_fu):
            step_idx = start_urban_step + freeway_substep_index * sim.K_fu + urban_offset
            ur_ttt, ur_diag = urban_substep(
                state,
                control,
                demand,
                cfg,
                urban_step_index=step_idx,
                ramp_release_veh_h=ramp_release,
            )
            urban_ttt += ur_ttt
            urban_rows.append(ur_diag)
            urban_rows_in_freeway_step.append(ur_diag)
        sync_onramp_queues_to_freeway(state, cfg)

        actual_ramp_release = _actual_ramp_release_flows(urban_rows_in_freeway_step, cfg)
        actual_ramp_diag = _with_actual_ramp_diagnostics(ramp_diag, actual_ramp_release)

        offramp_capacity = off_ramp_capacity_by_freeway_link(
            state,
            cfg,
            interval_h=sim.T_f_h,
        )
        fw_ttt, fw_diag = freeway_substep(
            state,
            control,
            demand,
            cfg,
            offramp_capacity_veh_h=offramp_capacity,
            ramp_release_veh_h=actual_ramp_release,
            ramp_release_diagnostics=actual_ramp_diag,
            update_ramp_queues=False,
            include_ramp_queue_ttt=False,
        )
        freeway_ttt += fw_ttt
        freeway_rows.append(fw_diag)

        # freeway에서 빠져나온 off-ramp 차량은 다음 urban substep 이후 storage/buffer로 들어간다.
        next_urban_step = start_urban_step + (freeway_substep_index + 1) * sim.K_fu
        for off_ramp in cfg.network.off_ramps:
            link = cfg.network.off_ramp_from_freeway[off_ramp]
            link_ratio_total = sum(
                ratio
                for candidate, ratio in cfg.network.off_ramp_split_ratio.items()
                if cfg.network.off_ramp_from_freeway.get(candidate) == link
            )
            share = cfg.network.off_ramp_split_ratio.get(off_ramp, 0.0) / max(link_ratio_total, 1.0e-9)
            flow = fw_diag.get(f"offramp_flow_{link}", 0.0) * share
            vehicles = flow * sim.T_f_h
            accepted, rejected = schedule_offramp_arrivals(state, cfg, off_ramp, vehicles, next_urban_step)
            accepted_offramp += accepted
            rejected_offramp += rejected

    diagnostics: Dict[str, Any] = {
        "coupling_nested_order_active": 1.0,
        "coupling_freeway_substeps": float(cfg.simulation.K_cf),
        "coupling_urban_substeps": float(cfg.simulation.K_cu),
        "coupling_onramp_sync_active": 1.0,
        "coupling_onramp_two_reservoir_active": 1.0,
        "coupling_offramp_storage_active": 1.0,
        "coupling_aggregate_urban_model": 0.0,
        "coupling_movement_urban_model": 1.0,
        "coupling_offramp_arrivals_accepted_veh": float(accepted_offramp),
        "coupling_offramp_arrivals_rejected_veh": float(rejected_offramp),
    }
    fw_diag = _aggregate_freeway_diagnostics(freeway_rows)
    ur_diag = aggregate_urban_diagnostics(urban_rows, cfg, control, interval_h=sim.T_c_h)
    diagnostics.update(fw_diag)
    diagnostics.update(ur_diag)
    return CoupledStepResult(
        freeway_ttt=float(freeway_ttt),
        urban_ttt=float(urban_ttt),
        diagnostics=diagnostics,
    )
