# refined_candidates의 반경 준수 여부를 단위 수준에서 분해 계측 — 프로덕션 미변경(읽기 전용).
import sys, io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'work'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
import numpy as np
from src.models.demand import DemandProfile
from src.simulation.simulator import MixedTrafficSimulator
from src.simulation.baseline import baseline_control
from src.controllers.leader import Leader, LeaderAction

runner = importlib.import_module('run_claude_style_five_controller')

SC = 'sweet_170_incident_w'
cfg, scenario = runner.build_cfg(SC, 30 * 180.0)
R_NUF = float(cfg.mpc.leader_local_nuf_radius_veh_h)
R_NP = float(cfg.mpc.leader_local_np_radius_veh)
BUDGET = int(cfg.mpc.leader_refinement_candidate_count)
print("cfg: nuf_radius=%s  np_radius=%s  budget=%s  search_mode=%s"
      % (R_NUF, R_NP, BUDGET, cfg.mpc.leader_search_mode))

profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
prev = None
for step in range(21):
    forecast = profile.horizon(sim.state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    ctrl = baseline_control('no_control', cfg, sim.state, forecast[0])
    sim.step(ctrl, forecast[0], step)
    prev = ctrl

state = sim.state
forecast = profile.horizon(state.time_sec, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
demand = forecast[0]
leader = Leader(cfg)
bounds = leader._candidate_bounds(state, prev, demand, forecast)
print("bounds: nuf=[%.0f, %.0f]  np=[%.0f, %.0f]  heuristic_nuf=%.0f  stress=%.3f"
      % (bounds.nuf_lower, bounds.nuf_upper, bounds.np_lower, bounds.np_upper,
         bounds.heuristic_nuf, bounds.stress_index))

for center_nuf in (6000.0, 4231.0):
    center = LeaderAction(float(np.clip(50.0, bounds.np_lower, bounds.np_upper)), center_nuf)
    out = leader.refined_candidates(state, center, prev, demand, forecast, count=BUDGET)
    vals = [a.N_UF_star for a in out]
    nps = [a.N_P_star for a in out]
    lo_ok, hi_ok = center_nuf - R_NUF, center_nuf + R_NUF
    outside = sorted({v for v in vals if v < lo_ok - 1e-6 or v > hi_ok + 1e-6})
    print("\n=== center N_UF=%.0f  (반경대로면 [%.0f, %.0f]) ===" % (center_nuf, max(bounds.nuf_lower, lo_ok), min(bounds.nuf_upper, hi_ok)))
    print("  최종 selected: n=%d  N_UF범위=[%.0f, %.0f]  N_P범위=[%.0f, %.0f]"
          % (len(out), min(vals), max(vals), min(nps), max(nps)))
    print("  반경 밖 N_UF 값(최종 selected 내): %s" % ([round(v) for v in outside] or "없음"))

    # --- 기여 분해 ---
    n_np = max(3, int(round(np.sqrt(BUDGET))))
    n_nuf = max(3, int(np.ceil(BUDGET / n_np)))
    nuf_radius = max(R_NUF, (bounds.nuf_upper - bounds.nuf_lower) / max(2.0 * (n_nuf - 1), 1.0))
    nuf_low = max(bounds.nuf_lower, center_nuf - nuf_radius)
    nuf_high = min(bounds.nuf_upper, center_nuf + nuf_radius)
    comp = {
        "radius_grid(linspace)": set(float(v) for v in np.linspace(nuf_low, nuf_high, n_nuf)),
        "center": {float(np.clip(center_nuf, bounds.nuf_lower, bounds.nuf_upper))},
        "bounds.heuristic_nuf": {float(np.clip(bounds.heuristic_nuf, bounds.nuf_lower, bounds.nuf_upper))},
        "_nuf_anchor_values": set(leader._nuf_anchor_values(bounds, prev)),
        "_previous_nuf_target": {float(np.clip(leader._previous_nuf_target(prev), bounds.nuf_lower, bounds.nuf_upper))},
    }
    print("  [기여 분해] nuf_radius(유효)=%.0f, 격자=[%.0f,%.0f], n_nuf=%d" % (nuf_radius, nuf_low, nuf_high, n_nuf))
    for name, s in comp.items():
        out_of = sorted({v for v in s if v < lo_ok - 1e-6 or v > hi_ok + 1e-6})
        print("    %-24s 값=%-42s 반경밖=%s" % (name, [round(v) for v in sorted(s)], [round(v) for v in out_of] or "-"))

    # --- N_P 쪽 ---
    np_radius = max(R_NP, (bounds.np_upper - bounds.np_lower) / max(2.0 * (n_np - 1), 1.0))
    np_lo_ok, np_hi_ok = center.N_P_star - R_NP, center.N_P_star + R_NP
    np_outside = sorted({v for v in nps if v < np_lo_ok - 1e-6 or v > np_hi_ok + 1e-6})
    print("  [N_P] center=%.0f 반경=%.0f(유효 %.0f) → 최종 반경밖 N_P: %s"
          % (center.N_P_star, R_NP, np_radius, [round(v) for v in np_outside] or "없음"))
