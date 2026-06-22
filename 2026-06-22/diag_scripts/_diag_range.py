# 달성 가능한 net-inflow 범위(green 경계)를 측정해 leader N_P_star 탐색범위 과대 여부 확인(일회용).
from src.models.state import ExperimentConfig, ControlAction
from src.models.demand import DemandProfile, load_scenarios, apply_scenario_network_overrides
from src.simulation.simulator import MixedTrafficSimulator
from src.controllers.distributed_coordinator import DistributedCoordinator

SCEN = "peak_demand"
SC = load_scenarios("src/config/scenarios.yaml")[SCEN]
cfg = apply_scenario_network_overrides(
    ExperimentConfig.from_file("src/config/default.yaml",
        {"mpc": {"follower_solver_mode": "distributed"}}), SC)
prof = DemandProfile(cfg, SC)
sim = MixedTrafficSimulator(cfg)
nc = ControlAction.uncontrolled(cfg)
for k in range(2):
    sim.step(nc, prof.at(sim.state.time_sec), k)
state = sim.state.copy()
forecast = prof.horizon(state.time_sec, cfg.mpc.horizon_steps)
coord = DistributedCoordinator(cfg)
net = cfg.network

def projected_net_inflow(p1_val):
    c = ControlAction.fixed(cfg)
    for s in net.signals:
        c.green_times[f"{s}_p1"] = float(p1_val)
        c.green_times[f"{s}_p2"] = float(net.effective_green_total - p1_val)
    # leader는 0짜리 더미; 진단 함수는 projected_net_inflow를 계산
    from src.controllers.leader import LeaderAction
    d = coord._leader_direct_feasible_set_diagnostics(state.copy(), c, forecast, LeaderAction(0.0, net.total_ramp_capacity))
    return d.get("distributed_grid_leader_projected_net_inflow_veh", float("nan"))

lo = projected_net_inflow(net.green_min)
hi = projected_net_inflow(net.green_max)
print(f"green_min={net.green_min}  green_max={net.green_max}  eff_green_total={net.effective_green_total}", flush=True)
print(f"projected_net_inflow @ all green_min = {lo:.1f} veh", flush=True)
print(f"projected_net_inflow @ all green_max = {hi:.1f} veh", flush=True)
print(f"=> 달성가능 net-inflow 범위 ~ [{min(lo,hi):.0f}, {max(lo,hi):.0f}] veh", flush=True)
print(f"   leader N_P_star 탐색범위(config) = {cfg.leader.N_P_star_range} veh", flush=True)
