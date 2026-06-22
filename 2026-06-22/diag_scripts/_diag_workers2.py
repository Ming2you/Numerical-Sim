# grid workers 8/10/12 step-0 시간 — page-file 안전 범위 무손실 단축 확인(per-config try/except, 일회용).
import time, traceback
from src.models.state import ExperimentConfig, ControlAction
from src.models.demand import DemandProfile, load_scenarios, apply_scenario_network_overrides
from src.simulation.simulator import MixedTrafficSimulator
from src.controllers.stackelberg_mpc import StackelbergMPCController


def run(workers, chunk):
    SC = load_scenarios("src/config/scenarios.yaml")["peak_demand"]
    cfg = apply_scenario_network_overrides(
        ExperimentConfig.from_file("src/config/default.yaml", {"mpc": {
            "follower_solver_mode": "distributed", "stackelberg_enable_fallback": False,
            "stackelberg_allocation_mode": "direct", "max_nash_iter": 1,
            "grid_parallel_backend": "process", "grid_parallel_max_workers": int(workers),
            "grid_parallel_chunk_size": int(chunk)}}), SC)
    prof = DemandProfile(cfg, SC); sim = MixedTrafficSimulator(cfg); ctl = StackelbergMPCController(cfg)
    fc = prof.horizon(0.0, cfg.mpc.horizon_steps)
    t0 = time.perf_counter()
    c = ctl.decide_with_info(sim.state.copy(), fc, ControlAction.fixed(cfg)).control
    return time.perf_counter() - t0, c.N_P_star, float(c.diagnostics.get("leader_selected_objective"))


if __name__ == "__main__":
    print(f"{'workers':>7} {'chunk':>5} {'wall_s':>8} {'N_P':>6} {'obj':>9}", flush=True)
    for w, ch in [(8, 8), (10, 5), (12, 4)]:
        try:
            wall, np_, obj = run(w, ch)
            print(f"{w:>7} {ch:>5} {wall:>8.1f} {np_:>6.0f} {obj:>9.3f}", flush=True)
        except Exception as e:
            print(f"{w:>7} {ch:>5}  FAILED: {type(e).__name__}: {str(e)[:60]}", flush=True)
