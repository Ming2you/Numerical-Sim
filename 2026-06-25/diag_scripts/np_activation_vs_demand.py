# 수요를 올리며 P-Stack의 N_P intent가 0을 벗어나는지 + urban 누적이 N_P_crit을 넘는지 확인.
# "demand too low(N_P 쓸 일 없음)" vs "구조적으로 N_P 미사용"을 가른다.
import argparse

from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator

ap = argparse.ArgumentParser()
ap.add_argument("--scenarios", default="sweet_128,sweet_155,sweet_190,sweet_220")
ap.add_argument("--steps", type=int, default=10)
args = ap.parse_args()

base = ExperimentConfig.from_file(
    "src/config/default.yaml",
    {"simulation": {"T_total": 180.0 * args.steps}, "mpc": {
        "relaxed_quantized_controls": True,
        "grid_parallel_backend": "serial",
        "stackelberg_leader_parallel_backend": "serial",
    }},
)
n_p_crit = base.leader.N_P_crit_veh
scenarios = load_scenarios("src/config/scenarios.yaml")
print(f"N_P_crit = {n_p_crit:.1f} veh\n")
print(f"{'scenario':12s} {'maxUrbanNP':>11s} {'NP/crit':>8s} {'maxIntentNP':>12s} {'NPactiveFrac':>12s} {'fallbackFrac':>12s} {'finalTTT':>9s}")
for name in [s.strip() for s in args.scenarios.split(",") if s.strip()]:
    sc = scenarios[name]
    cfg = apply_scenario_network_overrides(base.with_updates({}), sc)
    cfg.mpc.follower_solver_mode = "distributed"
    demand = DemandProfile(cfg, sc)
    sim = MixedTrafficSimulator(cfg)
    ctrl = StackelbergMPCController(cfg)
    prev = None
    max_urban_np = 0.0
    max_intent_np = 0.0
    np_active = 0
    fallback = 0
    for step in range(args.steps):
        cd = demand.at(sim.state.time_sec)
        fc = demand.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
        urban_np = sim.state.protected_accumulation_veh(cfg.network)
        max_urban_np = max(max_urban_np, urban_np)
        c = ctrl.decide(sim.state.copy(), fc, prev, cfg)
        d = c.diagnostics
        intent_np = abs(float(d.get("leader_intent_N_P_star", d.get("leader_selected_N_P_star", 0.0))))
        max_intent_np = max(max_intent_np, intent_np)
        if intent_np > 1e-6:
            np_active += 1
        if float(d.get("leader_selected_stage_fallback_pfo", 0.0)) > 0.5:
            fallback += 1
        sim.step(c, cd, step)
        prev = c
    print(f"{name:12s} {max_urban_np:11.1f} {max_urban_np / n_p_crit:8.2f} {max_intent_np:12.1f} "
          f"{np_active}/{args.steps:<10} {fallback}/{args.steps:<10} {sim.total_ttt:9.2f}")
