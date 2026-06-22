# step-0(global) leader 결정을 global max_evals별로 격리 실행 — N_P≈최적 유지하는 최소 예산 탐색(일회용).
# main-guard 필수: grid_parallel_backend=process가 Windows spawn에서 정상 동작하도록.
import time
from src.models.state import ExperimentConfig, ControlAction
from src.models.demand import DemandProfile, load_scenarios, apply_scenario_network_overrides
from src.simulation.simulator import MixedTrafficSimulator
from src.controllers.stackelberg_mpc import StackelbergMPCController


def run_one(max_evals: int):
    SCEN = "peak_demand"
    SC = load_scenarios("src/config/scenarios.yaml")[SCEN]
    cfg = apply_scenario_network_overrides(
        ExperimentConfig.from_file("src/config/default.yaml", {"mpc": {
            "follower_solver_mode": "distributed", "stackelberg_enable_fallback": False,
            "stackelberg_allocation_mode": "direct", "max_nash_iter": 1,
            "leader_continuous_max_evals": int(max_evals),
            "grid_parallel_backend": "process", "grid_parallel_max_workers": 6,
        }}), SC)
    prof = DemandProfile(cfg, SC)
    sim = MixedTrafficSimulator(cfg)
    ctl = StackelbergMPCController(cfg)
    prev = ControlAction.fixed(cfg)
    forecast = prof.horizon(0.0, cfg.mpc.horizon_steps)
    t0 = time.perf_counter()
    res = ctl.decide_with_info(sim.state.copy(), forecast, prev)
    wall = time.perf_counter() - t0
    c = res.control
    obj = float(c.diagnostics.get("leader_selected_objective", c.diagnostics.get("leader_objective", 0.0)))
    full = float(c.diagnostics.get("leader_candidate_full_evaluated_count", 0.0))
    return c.N_P_star, c.N_UF_star, obj, full, wall


if __name__ == "__main__":
    print(f"{'maxE':>5} {'N_P':>7} {'N_UF':>7} {'leader_obj':>11} {'full':>5} {'wall_s':>7}", flush=True)
    for me in [6, 10, 16, 25]:
        np_, nuf, obj, full, wall = run_one(me)
        print(f"{me:>5} {np_:>7.0f} {nuf:>7.0f} {obj:>11.3f} {full:>5.0f} {wall:>7.1f}", flush=True)
