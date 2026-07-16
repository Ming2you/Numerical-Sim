# far(urban)의 g 선택을 '실측 잔여 TTS'(zero-demand drain)로 채점 — obs vs 상수 vs 용량
import sys, copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.demand import DemandProfile, DemandStep, apply_scenario_network_overrides, load_scenarios
from src.models.state import ExperimentConfig
from src.simulation.baseline import baseline_control
from src.simulation.simulator import MixedTrafficSimulator


def zero_step(proto: DemandStep) -> DemandStep:
    return DemandStep(
        freeway_mainline={k: 0.0 for k in proto.freeway_mainline},
        urban_boundary={k: 0.0 for k in proto.urban_boundary},
        ramp_arrival={k: 0.0 for k in proto.ramp_arrival},
        incident_capacity_factor=proto.incident_capacity_factor,
        freeway_lane_loss={},
    )


def far_urban(n_u, tc_h, g):
    return (n_u * n_u) * tc_h / (2.0 * max(g, 1.0))


def build(scenario_name, steps):
    overrides = {"mpc": {"relaxed_quantized_controls": True, "grid_parallel_backend": "serial"},
                 "simulation": {"T_total": float(steps * 180)}}
    cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), overrides)
    scenarios = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))
    scenario = scenarios[scenario_name]
    cfg = apply_scenario_network_overrides(cfg, scenario)
    return cfg, DemandProfile(cfg, scenario)


def drain_truth(cfg, sim_snapshot, proto, max_steps=400):
    """zero-demand로 완전 배수하며 실제 urban TTT 누적 = 참 잔여 TTS."""
    sim = copy.deepcopy(sim_snapshot)
    zs = zero_step(proto)
    total = 0.0
    for k in range(max_steps):
        ctrl = baseline_control("no_control", cfg, sim.state, zs)
        res = sim.step(ctrl, zs, k)
        total += float(res.urban_ttt) if hasattr(res, "urban_ttt") else float(
            res.diagnostics.get("urban_ttt", 0.0))
        n = (float(sim.state.protected_accumulation_veh(cfg.network))
             + float(sim.state.boundary_in_queue_vehicles(cfg.network)))
        if n < 1.0:
            return total, k + 1, n
    n = (float(sim.state.protected_accumulation_veh(cfg.network))
         + float(sim.state.boundary_in_queue_vehicles(cfg.network)))
    return total, max_steps, n


SC = sys.argv[1] if len(sys.argv) > 1 else "sweet_170_w"
PROBE_STEPS = [int(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else ["3", "9", "19"])]
RUN_TO = max(PROBE_STEPS) + 1

cfg, profile = build(SC, 60)
tc_h = float(cfg.simulation.T_c_h)
net = cfg.network
CAP = len(net.boundary_out_links) * float(net.boundary_out_capacity_veh_h) * tc_h

print(f"scenario={SC}  tc_h={tc_h}  exit cap/interval = {len(net.boundary_out_links)}"
      f" x {net.boundary_out_capacity_veh_h} x {tc_h} = {CAP:.1f} veh")
print()

sim = MixedTrafficSimulator(cfg)
snaps = {}
for step in range(RUN_TO):
    fc = profile.horizon(sim.state.time_sec, 1)
    ctrl = baseline_control("no_control", cfg, sim.state, fc[0])
    sim.step(ctrl, fc[0], step)
    if step in PROBE_STEPS:
        n_u = (float(sim.state.protected_accumulation_veh(net))
               + float(sim.state.boundary_in_queue_vehicles(net)))
        snaps[step] = (copy.deepcopy(sim), n_u,
                       float(getattr(sim.state, "last_urban_sink_veh", 0.0)), fc[0])

hdr = (f"{'step':>4s} {'n_u':>8s} {'sink':>8s} | {'TRUE drain TTS':>14s} {'steps':>5s} |"
       f" {'far(obs)':>9s} {'far(640)':>9s} {'far(cap560)':>11s} |"
       f" {'obs/TRUE':>8s} {'640/TRUE':>8s} {'cap/TRUE':>8s}")
print(hdr)
print("-" * len(hdr))
for step in PROBE_STEPS:
    sim_s, n_u, sink, proto = snaps[step]
    truth, nsteps, leftover = drain_truth(cfg, sim_s, proto)
    g_obs = sink if sink > 0 else 640.0
    f_obs = far_urban(n_u, tc_h, g_obs)
    f_640 = far_urban(n_u, tc_h, 640.0)
    f_cap = far_urban(n_u, tc_h, CAP)
    print(f"{step:4d} {n_u:8.1f} {sink:8.2f} | {truth:14.2f} {nsteps:5d} |"
          f" {f_obs:9.2f} {f_640:9.2f} {f_cap:11.2f} |"
          f" {f_obs/truth:8.2f} {f_640/truth:8.2f} {f_cap/truth:8.2f}")
    if leftover >= 1.0:
        print(f"     (경고: 미배수 잔량 {leftover:.1f} veh — 참값 하한)")
