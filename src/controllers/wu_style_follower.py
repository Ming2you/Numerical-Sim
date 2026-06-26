# proposed Stackelberg leader(N_P,N_UF)를 Wu식 국소분해 follower로 푸는 새 coordinator(O(n) 목표).
"""WuStyleStackelbergFollower — proposed leader 인터페이스(solve→NashResult)를 입힌 Wu식 follower.

DistributedCoordinator(full-coupled 전역 그리드, O(n²))를 대체한다. WuDistributedController의
consensus 루프·국소 agent solve·coupling을 재사용하되, proposed leader의 LeaderAction(N_P,N_UF)를
받고, 후보 선택을 **realized TTT**로 한다(WU-MATCHED 0% 버그 교훈: 누적·proxy 금지).

마일스톤:
- M1(현재): N_P conditioning(urban perimeter) + Wu consensus(green/VSL) + TTT 선택 + NashResult.
  N_UF(metering)·allocation은 M2.
- M2: freeway agent에 ramp metering 추가 + N_UF conditioning → proposed 23.88% 회복을 Wu 속도로.
"""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np

from src.controllers.leader import LeaderAction
from src.controllers.nash_solver import NashResult
from src.controllers.wu_distributed import WuDistributedController, WuLeaderAction
from src.models.demand import DemandStep
from src.models.state import ControlAction, ExperimentConfig, TrafficState


class WuStyleStackelbergFollower(WuDistributedController):
    """proposed leader가 nash_solver로 쓰는 Wu식 분해 follower.

    인터페이스는 DistributedCoordinator.solve와 동일: solve(state, leader, demand, previous).
    leader는 proposed LeaderAction(N_P_star, N_UF_star) 또는 None(PFO).
    """

    def __init__(self, cfg: ExperimentConfig):
        super().__init__(cfg, leader_enabled=True)

    def _map_leader(self, leader: Optional[LeaderAction]) -> Optional[WuLeaderAction]:
        """proposed LeaderAction(N_P,N_UF) → Wu conditioning.

        M1: N_P만 urban perimeter conditioning에 쓴다(n_p_star=N_P_star). 자유류 freeway 과-gating을
        막기 위해 n_f_star는 느슨하게(현 freeway 차량수의 큰 배수) 둬 비binding으로 만든다.
        N_UF(metering)는 M2에서 freeway agent에 추가한다.
        """
        # M1.5 진단: proposed N_P(net-inflow)와 Wu n_p_star(누적 cap) 의미 불일치로 과-gating(0%)
        # 발생 → 우선 conditioning OFF(순수 Wu follower)로 follower 정상성/속도 확인. M2에서
        # proposed 의미(net-inflow target·metering target)에 맞는 conditioning을 새로 구현한다.
        return None

    def solve(
        self,
        state: TrafficState,
        leader: Optional[LeaderAction],
        demand: DemandStep | Iterable[DemandStep],
        previous_control: Optional[ControlAction] = None,
        leader_incumbent_obj: float = np.inf,
    ) -> NashResult:
        forecast = [demand] if isinstance(demand, DemandStep) else list(demand)
        if not forecast:
            raise ValueError("WuStyleStackelbergFollower requires at least one demand step.")
        previous = previous_control or self.previous_control or _fixed(self.cfg)
        wu_leader = self._map_leader(leader)

        control, iters, converged, residual, evals = self._solve_followers(
            state, forecast[0], previous, wu_leader,
        )

        # realized rollout TTT(proposed leader guard가 distributed_response_rollout_ttt로 읽음).
        from src.simulation.coupling import run_coupled_interval

        sim = state.copy()
        urban_ttt = 0.0
        freeway_ttt = 0.0
        for step_demand in forecast[: self.cfg.mpc.horizon_steps]:
            result = run_coupled_interval(sim, control, step_demand, self.cfg)
            urban_ttt += float(result.urban_ttt)
            freeway_ttt += float(result.freeway_ttt)
            sim.time_sec += self.cfg.simulation.control_interval
        total_ttt = urban_ttt + freeway_ttt

        # proposed leader가 commit·guard·closure에서 읽는 핵심 키.
        control.N_P_star = float(leader.N_P_star) if leader is not None else 0.0
        control.N_UF_star = float(leader.N_UF_star) if leader is not None else 0.0
        control.diagnostics.update({
            "distributed_response_rollout_ttt": float(total_ttt),
            "distributed_response_rollout_urban_ttt": float(urban_ttt),
            "distributed_response_rollout_freeway_ttt": float(freeway_ttt),
            "wu_style_follower_active": 1.0,
            "wu_style_coupling_residual": float(residual),
            "wu_style_consensus_iterations": float(iters),
            "wu_style_solver_evaluations": float(evals),
        })
        self.previous_control = control
        return NashResult(
            control=control,
            objective_value=float(total_ttt),
            iterations=int(iters),
            converged=bool(converged),
            residual_objective=0.0,
            residual_control=float(residual),
            diagnostics=dict(control.diagnostics),
        )


def _fixed(cfg: ExperimentConfig) -> ControlAction:
    return ControlAction.fixed(cfg)
