# [THROWAWAY 검증 전용] B의 decisive H1 재현 — per-signal 후보를 global coupled-plant TTT로 채점
"""Investigator A 감독용 일회성 변형. 기존 파일 미변경, WuFaithfulFollower 서브클래스만.

B의 주장: follower의 per-signal urban green 후보를 LOCAL self-TTS(rollout_local_tts) 대신
GLOBAL coupled-plant TTT(run_coupled_interval)로 horizon=3, full 5-iter Jacobi, closed-loop
T=3600으로 채점하면 +29% 개선. 이를 독립 재현한다.

per-signal coordinate: 한 signal의 p1 후보만 바꾸고 나머지 signal/vsl은 현재 snapshot 고정,
그 전체 control을 global plant(run_coupled_interval)로 horizon=3 굴려 total TTT argmin.
"""
from __future__ import annotations

from typing import Dict, List, Mapping

import numpy as np

from src.controllers.nash_solver import NashResult
from src.controllers.relaxed_quantization import (
    queue_pressure_green_target,
    repair_green_pair,
)
from src.controllers.wu_faithful_follower import WuFaithfulFollower, q0_sum
from src.models.state import ControlAction
from src.simulation.coupling import run_coupled_interval


class GlobalTTTFollower(WuFaithfulFollower):
    """후보 채점만 global coupled-plant TTT(horizon=3)로 교체한 throwaway 변형."""

    def __init__(self, cfg):
        super().__init__(cfg)
        self._forecast: List = []

    # forecast 전체를 solve에서 받아 저장(부모는 first_demand만 _solve_followers에 넘김).
    def solve(self, state, leader, demand, previous_control=None, leader_incumbent_obj=np.inf):
        from src.models.demand import DemandStep
        forecast = [demand] if isinstance(demand, DemandStep) else list(demand)
        self._forecast = forecast
        return super().solve(state, leader, demand, previous_control, leader_incumbent_obj)

    def _candidate_p1_list(self, signal, state, coupling, previous) -> List[float]:
        net = self.cfg.network
        model = self._local_models[signal]
        total = net.effective_green_total
        sim = self.cfg.simulation
        horizon = max(1, self.cfg.mpc.horizon_steps)
        substeps = horizon * max(1, sim.K_cu)
        dt_h = sim.T_u_h
        q0 = {m: max(0.0, state.urban_movement_queue.get(m, 0.0)) for m in model.movements}
        arr_phase = {pid: float(coupling.get(f"arr_{signal}_{pid}", 0.0)) for pid in ("p1", "p2")}
        prev_p1 = float(previous.green_times.get(f"{signal}_p1", total / 2.0))
        p1_pressure = q0_sum(q0, model, "p1") + arr_phase["p1"] * dt_h * substeps
        p2_pressure = q0_sum(q0, model, "p2") + arr_phase["p2"] * dt_h * substeps
        pressure_center = queue_pressure_green_target(p1_pressure, p2_pressure, self.cfg)
        raw_candidates = [total / 2.0, prev_p1, pressure_center]
        if self.cfg.mpc.relaxed_quantized_controls:
            raw_candidates.extend([
                pressure_center - 1.0, pressure_center + 1.0,
                pressure_center - 2.0, pressure_center + 2.0,
                pressure_center - 5.0, pressure_center + 5.0,
            ])
        raw_candidates.extend(float(v) for v in np.linspace(net.green_min, net.green_max, 13))
        candidates: List[float] = []
        for raw in raw_candidates:
            p1_value = repair_green_pair(float(raw), self.cfg).p1
            if not any(abs(p1_value - e) <= 1.0e-9 for e in candidates):
                candidates.append(float(p1_value))
        out = []
        for p1 in candidates:
            p2 = total - p1
            if p2 < net.green_min - 1e-9 or p2 > net.green_max + 1e-9:
                continue
            out.append(float(p1))
        return out

    def _global_ttt_for_p1(self, signal, state, snapshot, p1) -> float:
        """이 signal의 p1만 바꾼 snapshot control을 global plant로 horizon 굴려 total TTT."""
        net = self.cfg.network
        control = ControlAction(
            ramp_metering=dict(snapshot.ramp_metering),
            vsl=dict(snapshot.vsl),
            green_times=dict(snapshot.green_times),
            offsets=dict(snapshot.offsets),
            inflow_outflow_allocation={},
        )
        control.green_times[f"{signal}_p1"] = float(p1)
        control.green_times[f"{signal}_p2"] = net.effective_green_total - float(p1)
        horizon = max(1, min(len(self._forecast), self.cfg.mpc.horizon_steps))
        s = state.copy()
        total = 0.0
        for demand in self._forecast[:horizon]:
            res = run_coupled_interval(s, control, demand, self.cfg)
            total += float(res.urban_ttt + res.freeway_ttt)
            s.time_sec += self.cfg.simulation.control_interval
        return total

    def _solve_urban_agent_local(self, signal, state, coupling, arr_movement, s_eff_frozen, previous):
        # 부모 시그니처와 동일하나, 채점만 global plant로. previous == iteration snapshot.
        candidates = self._candidate_p1_list(signal, state, coupling, previous)
        net = self.cfg.network
        smooth_w = self.cfg.urban_follower.green_smoothness_weight
        prev_p1 = float(previous.green_times.get(f"{signal}_p1", net.effective_green_total / 2.0))
        best_p1, best_obj = prev_p1, float("inf")
        evals = 0
        for p1 in candidates:
            cost = self._global_ttt_for_p1(signal, state, previous, p1)
            cost += smooth_w * abs(p1 - prev_p1)
            evals += 1
            if cost < best_obj:
                best_obj, best_p1 = cost, float(p1)
        return best_p1, best_obj, evals
