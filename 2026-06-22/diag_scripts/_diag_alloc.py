# allocation 모드(direct vs pso) P-STACK total TTT 비교 — allocation 모듈이 이득인지 스크리닝(일회용).
# main-guard 필수: grid_parallel_backend=process가 Windows spawn에서 정상 동작하도록.
import time
from src.models.state import ExperimentConfig, ControlAction
from src.models.demand import DemandProfile, load_scenarios, apply_scenario_network_overrides
from src.simulation.simulator import MixedTrafficSimulator
from src.controllers.stackelberg_mpc import StackelbergMPCController

SCEN = "peak_demand"
T = 900.0


def run_mode(mode: str):
    SC = load_scenarios("src/config/scenarios.yaml")[SCEN]
    cfg = apply_scenario_network_overrides(
        ExperimentConfig.from_file("src/config/default.yaml", {"mpc": {
            "follower_solver_mode": "distributed", "stackelberg_enable_fallback": False,
            "stackelberg_allocation_mode": mode, "max_nash_iter": 1,
            "grid_parallel_backend": "process", "grid_parallel_max_workers": 6,
        }}), SC)
    prof = DemandProfile(cfg, SC)
    sim = MixedTrafficSimulator(cfg)
    ctl = StackelbergMPCController(cfg)
    prev = ControlAction.fixed(cfg)
    n = int(T / cfg.simulation.control_interval)
    t0 = time.perf_counter()
    cum = 0.0
    nps = []
    for k in range(n):
        t = sim.state.time_sec
        forecast = prof.horizon(t, cfg.mpc.horizon_steps)
        res = ctl.decide_with_info(sim.state.copy(), forecast, prev)
        c = res.control
        log = sim.step(c, prof.at(t), k)
        cum += float(log.freeway_ttt + log.urban_ttt)
        prev = c
        nps.append(round(c.N_P_star))
    return cum, time.perf_counter() - t0, nps


if __name__ == "__main__":
    print(f"{'mode':>9} {'cum_TTT(900s)':>13} {'wall_s':>8}  N_P_trace", flush=True)
    for mode in ["direct", "pso"]:
        cum, wall, nps = run_mode(mode)
        print(f"{mode:>9} {cum:>13.3f} {wall:>8.1f}  {nps}", flush=True)
