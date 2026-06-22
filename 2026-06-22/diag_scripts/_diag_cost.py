# follower solve 1회 비용을 grid 백엔드(serial/thread/process)별로 측정 — thread가 GIL로 무의미한지 검증(일회용).
import time
from src.models.state import ExperimentConfig, ControlAction
from src.models.demand import DemandProfile, load_scenarios, apply_scenario_network_overrides
from src.simulation.simulator import MixedTrafficSimulator
from src.controllers.distributed_coordinator import DistributedCoordinator

SCEN = "peak_demand"
SC = load_scenarios("src/config/scenarios.yaml")[SCEN]

def build_congested(backend):
    cfg = apply_scenario_network_overrides(
        ExperimentConfig.from_file("src/config/default.yaml",
            {"mpc": {"follower_solver_mode": "distributed", "stackelberg_enable_fallback": False,
                     "grid_parallel_backend": backend}}), SC)
    prof = DemandProfile(cfg, SC)
    sim = MixedTrafficSimulator(cfg)
    nc = ControlAction.uncontrolled(cfg)
    for k in range(2):
        sim.step(nc, prof.at(sim.state.time_sec), k)
    forecast = prof.horizon(sim.state.time_sec, cfg.mpc.horizon_steps)
    return cfg, sim.state.copy(), forecast, nc

for backend in ["serial", "thread"]:
    cfg, state, forecast, nc = build_congested(backend)
    coord = DistributedCoordinator(cfg)
    # warm-up 1회(process pool spawn/pickle 비용 제외)
    t0 = time.perf_counter(); coord.solve(state.copy(), None, forecast, nc); warm = time.perf_counter()-t0
    # 측정 3회 평균
    ts = []
    for _ in range(3):
        t0 = time.perf_counter(); coord.solve(state.copy(), None, forecast, nc); ts.append(time.perf_counter()-t0)
    avg = sum(ts)/len(ts)
    print(f"backend={backend:7s}  warmup={warm:6.2f}s  solve_avg={avg:6.2f}s  (workers={cfg.mpc.grid_parallel_max_workers})", flush=True)
