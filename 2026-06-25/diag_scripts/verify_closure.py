# Layer1 출력폐쇄 검증: sweet_128 9스텝에서 intent vs realized(N_P*/N_UF*)와 closure 적용여부를 출력.
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator

cfg = ExperimentConfig.from_file(
    "src/config/default.yaml",
    {"simulation": {"T_total": 1620.0}, "mpc": {
        "relaxed_quantized_controls": True,
        "grid_parallel_backend": "serial",
        "stackelberg_leader_parallel_backend": "serial",
    }},
)
sc = load_scenarios("src/config/scenarios.yaml")["sweet_128"]
cfg = apply_scenario_network_overrides(cfg, sc)
cfg.mpc.follower_solver_mode = "distributed"  # production PROPOSED-STACKELBERG 어댑터와 동일
demand = DemandProfile(cfg, sc)
sim = MixedTrafficSimulator(cfg)
ctrl = StackelbergMPCController(cfg)
prev = None
print(f"{'step':>4} {'intentNP':>9} {'realNP':>9} {'ctrlNP':>9} | {'intentNUF':>9} {'realNUF':>9} {'ctrlNUF':>9} {'closed':>6}")
for step in range(9):
    cd = demand.at(sim.state.time_sec)
    fc = demand.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
    c = ctrl.decide(sim.state.copy(), fc, prev, cfg)
    d = c.diagnostics
    print(f"{step:>4} {d.get('leader_intent_N_P_star',0):9.1f} {d.get('leader_realized_N_P_star',0):9.1f} {c.N_P_star:9.1f} | "
          f"{d.get('leader_intent_N_UF_star',0):9.1f} {d.get('leader_realized_N_UF_star',0):9.1f} {c.N_UF_star:9.1f} {d.get('leader_output_closure_applied',0):6.0f}")
    sim.step(c, cd, step)
    prev = c
print("total_ttt=%.4f" % sim.total_ttt)
