# [THROWAWAY] B의 cheap surrogate 가설 검증 — off-ramp storage 점유로 D/F p1 split bias (plant 호출 없음)
"""LOCAL self-TTS(rollout_local_tts) 채점은 그대로 두되, off-ramp을 가진 신호(D,F)에 한해
state에서 직접 읽은 freeway off-ramp storage 점유를 p1 green에 cheap하게 bias한다.

근거(검증된 물리): off-ramp movement는 전부 p1에 있고 _drain_offramp_storage가 p1 green
fraction에 비례해 storage를 방출 → freeway off-ramp storage 점유↓ → capacity-drop 완화.
local rollout은 이 freeway-TTT 효과를 못 본다(자기 urban 큐만). 그래서 cheap penalty로 보충:
  cost(p1) += W_OFF * occupancy_total * (green_total - p1) / green_total
즉 storage가 차 있을수록 p1을 키우도록(p2 깎도록) 보너스. plant 미호출 → 저렴.
W_OFF를 sweep해 어떤 cheap 가중치든 의미 있는 개선을 회복하는지 본다.
"""
from __future__ import annotations

from typing import List, Mapping

import numpy as np

from src.controllers.local_signal_plant import rollout_local_tts
from src.controllers.relaxed_quantization import (
    queue_pressure_green_target,
    repair_green_pair,
)
from src.controllers.wu_faithful_follower import WuFaithfulFollower, q0_sum


class OffRampBiasFollower(WuFaithfulFollower):
    def __init__(self, cfg, w_off: float):
        super().__init__(cfg)
        self.w_off = float(w_off)
        net = cfg.network
        # 신호 -> 소속 off_ramp storage_link 목록.
        self._signal_storage = {}
        for s in net.signals:
            links = []
            for o in net.off_ramps:
                if any(m.startswith(f"{s}_off") for m in net.off_ramp_to_movement.get(o, [])):
                    sl = net.off_ramp_storage_link.get(o, "")
                    if sl:
                        links.append((o, sl))
            self._signal_storage[s] = links
        self._cur_state = None

    def _solve_followers(self, state, demand, previous):
        self._cur_state = state  # occupancy 읽기용.
        return super()._solve_followers(state, demand, previous)

    def _offramp_occupancy(self, signal) -> float:
        st = self._cur_state
        net = self.cfg.network
        total = 0.0
        for off_ramp, sl in self._signal_storage.get(signal, []):
            cap = float(net.urban_link_storage_veh.get(sl, 0.0))
            avail = float(st.urban_link_storage.get(sl, cap))
            total += max(0.0, cap - avail)
        return total

    def _solve_urban_agent_local(self, signal, state, coupling, arr_movement, s_eff_frozen, previous):
        # 부모 _solve_urban_agent_local 복제 + off-ramp bias term 추가.
        net = self.cfg.network
        sim = self.cfg.simulation
        model = self._local_models[signal]
        total = net.effective_green_total
        horizon = max(1, self.cfg.mpc.horizon_steps)
        substeps = horizon * max(1, sim.K_cu)
        dt_h = sim.T_u_h
        smooth_w = self.cfg.urban_follower.green_smoothness_weight

        q0 = {m: max(0.0, state.urban_movement_queue.get(m, 0.0)) for m in model.movements}
        arr_phase = {pid: float(coupling.get(f"arr_{signal}_{pid}", 0.0)) for pid in ("p1", "p2")}
        arr_mv = {}
        for pid in ("p1", "p2"):
            pm = [m for m in model.movements if model.phase_of[m] == pid]
            raw_sum = sum(max(0.0, float(arr_movement.get(m, 0.0))) for m in pm)
            tgt = arr_phase[pid]
            for m in pm:
                arr_mv[m] = (max(0.0, float(arr_movement.get(m, 0.0))) * tgt / raw_sum) if raw_sum > 1e-12 else 0.0
        s_eff0 = {model.receiving_of[m]: float(s_eff_frozen.get(model.receiving_of[m], 0.0))
                  for m in model.movements if model.receiving_of[m]}

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
            if not any(abs(p1_value - e) <= 1e-9 for e in candidates):
                candidates.append(float(p1_value))

        occ = self._offramp_occupancy(signal) if self.w_off > 0.0 else 0.0

        best_p1, best_obj = prev_p1, float("inf")
        evals = 0
        for p1 in candidates:
            p2 = total - p1
            if p2 < net.green_min - 1e-9 or p2 > net.green_max + 1e-9:
                continue
            cost = rollout_local_tts(model, q0, arr_mv, s_eff0, p1, p2, substeps, dt_h)
            cost += smooth_w * abs(p1 - prev_p1)
            # cheap off-ramp bias: storage 점유가 클수록 p1 키우면 비용↓ (plant 미호출).
            cost += self.w_off * occ * (total - p1) / total
            evals += 1
            if cost < best_obj:
                best_obj, best_p1 = cost, float(p1)
        return best_p1, best_obj, evals
