from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, MutableMapping

import numpy as np

from src.models.state import MODEL_PHASES, ExperimentConfig


@dataclass(frozen=True)
class GreenRepairResult:
    """복구된 현시별 녹색. `primary` 는 `phases[MODEL_PHASES[0]]` 과 같다."""

    primary: float
    phases: Mapping[str, float]
    quantization_residual_sec: float
    repair_count: int


@dataclass(frozen=True)
class VSLRepairResult:
    value: float
    quantization_residual_km_h: float
    repair_count: int


GREEN_RESIDUAL_KEY = "green_quantization_residual_sec"
VSL_RESIDUAL_KEY = "vsl_quantization_residual_km_h"
GREEN_REPAIR_COUNT_KEY = "green_repair_count"
VSL_REPAIR_COUNT_KEY = "vsl_repair_count"


def accumulate_repair_diagnostics(
    diagnostics: MutableMapping[str, float],
    *,
    green: GreenRepairResult | None = None,
    vsl: VSLRepairResult | None = None,
) -> None:
    """Spec 17 diagnostics: residual은 최대값, repair count는 합계로 누적한다."""
    if green is not None:
        diagnostics[GREEN_RESIDUAL_KEY] = max(
            float(diagnostics.get(GREEN_RESIDUAL_KEY, 0.0)),
            float(green.quantization_residual_sec),
        )
        diagnostics[GREEN_REPAIR_COUNT_KEY] = (
            float(diagnostics.get(GREEN_REPAIR_COUNT_KEY, 0.0)) + float(green.repair_count)
        )
    if vsl is not None:
        diagnostics[VSL_RESIDUAL_KEY] = max(
            float(diagnostics.get(VSL_RESIDUAL_KEY, 0.0)),
            float(vsl.quantization_residual_km_h),
        )
        diagnostics[VSL_REPAIR_COUNT_KEY] = (
            float(diagnostics.get(VSL_REPAIR_COUNT_KEY, 0.0)) + float(vsl.repair_count)
        )


def merge_repair_diagnostics(
    diagnostics: MutableMapping[str, float],
    source: Mapping[str, float],
) -> None:
    """여러 agent diagnostics를 합칠 때 residual/count 의미를 보존한다."""
    for key in (GREEN_RESIDUAL_KEY, VSL_RESIDUAL_KEY):
        if key in source:
            diagnostics[key] = max(float(diagnostics.get(key, 0.0)), float(source.get(key, 0.0)))
    for key in (GREEN_REPAIR_COUNT_KEY, VSL_REPAIR_COUNT_KEY):
        if key in source:
            diagnostics[key] = float(diagnostics.get(key, 0.0)) + float(source.get(key, 0.0))


def _quantize(value: float, quantum: float, mode: str) -> float:
    quantum = max(float(quantum), 1.0e-9)
    ratio = float(value) / quantum
    if mode == "nearest":
        return float(round(ratio) * quantum)
    return float(math.floor(ratio + 1.0e-12) * quantum)


def _project_to_vsl_set(value: float, vsl_set: Iterable[float], mode: str) -> float:
    values = sorted(float(v) for v in vsl_set)
    if not values:
        raise ValueError("vsl_set must not be empty.")
    if mode == "floor":
        lower = [v for v in values if v <= value + 1.0e-9]
        return float(lower[-1] if lower else values[0])
    return float(min(values, key=lambda v: (abs(v - value), v)))


def repair_vsl_value(
    target: float,
    previous: float,
    cfg: ExperimentConfig,
) -> VSLRepairResult:
    """Spec 17.4 VSL: continuous target을 step 제약과 이산 vsl_set으로 투영한다."""
    fc = cfg.freeway_follower
    mpc = cfg.mpc
    vsl_set = sorted(float(v) for v in fc.vsl_set)
    minimum = min(vsl_set)
    maximum = max(vsl_set)
    repair_count = 0

    clipped = float(np.clip(target, minimum, maximum))
    repair_count += int(abs(clipped - target) > 1.0e-9)

    step_low = max(minimum, float(previous) - fc.max_vsl_step)
    step_high = min(maximum, float(previous) + fc.max_vsl_step)
    stepped = float(np.clip(clipped, step_low, step_high))
    repair_count += int(abs(stepped - clipped) > 1.0e-9)

    quantized = _quantize(stepped, mpc.relaxed_vsl_quantum_km_h, mpc.relaxed_rounding_mode)
    repair_count += int(abs(quantized - stepped) > 1.0e-9)
    projected = _project_to_vsl_set(quantized, vsl_set, mpc.relaxed_rounding_mode)
    feasible = [v for v in vsl_set if step_low - 1.0e-9 <= v <= step_high + 1.0e-9] or vsl_set
    repaired = float(min(feasible, key=lambda v: (abs(v - projected), v)))
    repair_count += int(abs(repaired - quantized) > 1.0e-9 or abs(repaired - projected) > 1.0e-9)
    return VSLRepairResult(
        value=repaired,
        quantization_residual_km_h=abs(float(target) - repaired),
        repair_count=repair_count,
    )


def repair_green_phases(
    primary_target: float,
    cfg: ExperimentConfig,
) -> GreenRepairResult:
    """Spec 17.4 green: 주 현시 target 을 상자·양자화·주기 등식에 맞게 복구한다.

    구 `repair_green_pair` 의 N 현시 일반화다. 주 현시를 양자화한 뒤 남는 예산을
    나머지 (N-1) 현시에 **양자 배수로** 나누고 자투리를 첫 나머지 현시가 흡수한다.
    그래서 Σ = effective_green_total 이 정확히 유지되면서 모든 현시가 양자 격자 위에 있다.
    N=2 면 나머지가 하나라 자투리도 없어 `total - p1` 과 같다.
    """
    net = cfg.network
    mpc = cfg.mpc
    total = float(net.effective_green_total)
    gmin = float(net.green_min)
    gmax = float(net.green_max)
    rest_ids = list(MODEL_PHASES[1:])
    others = max(len(rest_ids), 1)
    low = max(gmin, total - others * gmax)
    high = min(gmax, total - others * gmin)
    repair_count = 0

    if low > high:
        # 상자가 예산을 담지 못한다 — 균등분배로 물러난다(예산 보존이 상자보다 우선).
        share = total / float(net.num_phases)
        return GreenRepairResult(
            primary=share,
            phases={pid: share for pid in MODEL_PHASES},
            quantization_residual_sec=abs(float(primary_target) - share),
            repair_count=1,
        )

    clipped = float(np.clip(primary_target, low, high))
    repair_count += int(abs(clipped - primary_target) > 1.0e-9)
    quantum = max(float(mpc.relaxed_green_quantum_sec), 1.0e-9)
    quantized = _quantize(clipped, quantum, mpc.relaxed_rounding_mode)
    repair_count += int(abs(quantized - clipped) > 1.0e-9)
    primary = float(np.clip(quantized, low, high))
    repair_count += int(abs(primary - quantized) > 1.0e-9)

    rest_budget = total - primary
    if not rest_ids:
        return GreenRepairResult(
            primary=primary,
            phases={MODEL_PHASES[0]: primary},
            quantization_residual_sec=abs(float(primary_target) - primary),
            repair_count=repair_count,
        )
    base = math.floor(rest_budget / float(len(rest_ids)) / quantum + 1.0e-12) * quantum
    values = [base] * len(rest_ids)
    values[0] += rest_budget - base * float(len(rest_ids))
    if any(v < gmin - 1.0e-9 or v > gmax + 1.0e-9 for v in values):
        values = _project_rest_to_box(values, rest_budget, gmin, gmax)
        repair_count += 1
    phases = {MODEL_PHASES[0]: primary}
    phases.update({pid: float(v) for pid, v in zip(rest_ids, values)})
    return GreenRepairResult(
        primary=float(primary),
        phases=phases,
        quantization_residual_sec=abs(float(primary_target) - float(primary)),
        repair_count=repair_count,
    )


def _project_rest_to_box(values: list[float], total: float, low: float, high: float) -> list[float]:
    n = len(values)
    share = total / float(n)
    low = min(low, share)
    high = max(high, share)
    out = [float(np.clip(v, low, high)) for v in values]
    for _ in range(n + 1):
        residual = total - sum(out)
        if abs(residual) <= 1.0e-12:
            break
        free = [
            i for i in range(n)
            if (residual > 0.0 and out[i] < high - 1.0e-12) or (residual < 0.0 and out[i] > low + 1.0e-12)
        ]
        if not free:
            break
        step = residual / float(len(free))
        for i in free:
            out[i] = float(np.clip(out[i] + step, low, high))
    return out


def queue_pressure_green_target(
    primary_pressure: float,
    other_pressure: float,
    cfg: ExperimentConfig,
) -> float:
    """주 현시 압력 대 **나머지 현시 압력 합**을 주 현시 녹색 target 으로 변환한다."""
    total = float(cfg.network.effective_green_total)
    pressure_sum = max(0.0, float(primary_pressure)) + max(0.0, float(other_pressure))
    ratio = max(0.0, float(primary_pressure)) / max(pressure_sum, 1.0e-9) if pressure_sum > 0.0 else 0.5
    return float(total * ratio)
