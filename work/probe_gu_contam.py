# drain 참값의 off-ramp 오염 정량 — 잔여 TTS가 n_u에 귀속되는지 검정
import sys, copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.demand import DemandProfile, DemandStep, apply_scenario_network_overrides, load_scenarios
from src.models.state import ExperimentConfig
from src.simulation.baseline import baseline_control
from src.simulation.simulator import MixedTrafficSimulator

overrides = {"mpc": {"relaxed_quantized_controls": True, "grid_parallel_backend": "serial"},
             "simulation": {"T_total": 60 * 180.0}}
cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), overrides)
scenarios = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))
SC = sys.argv[1] if len(sys.argv) > 1 else "sweet_170_w"
cfg = apply_scenario_network_overrides(cfg, scenarios[SC])
profile = DemandProfile(cfg, scenarios[SC])
net, tc_h = cfg.network, float(cfg.simulation.T_c_h)

sim = MixedTrafficSimulator(cfg)
STEP = 3
for step in range(STEP + 1):
    fc = profile.horizon(sim.state.time_sec, 1)
    sim.step(baseline_control("no_control", cfg, sim.state, fc[0]), fc[0], step)
    proto = fc[0]

n_u0 = (float(sim.state.protected_accumulation_veh(net))
        + float(sim.state.boundary_in_queue_vehicles(net)))
sink0 = float(getattr(sim.state, "last_urban_sink_veh", 0.0))
fw0 = float(sim.state.total_freeway_vehicles(net))
print(f"start: n_u={n_u0:.1f} sink={sink0:.2f} freeway_veh={fw0:.1f}")

zs = DemandStep(freeway_mainline={k: 0.0 for k in proto.freeway_mainline},
                urban_boundary={k: 0.0 for k in proto.urban_boundary},
                ramp_arrival={k: 0.0 for k in proto.ramp_arrival},
                incident_capacity_factor=proto.incident_capacity_factor, freeway_lane_loss={})

tot_ttt = 0.0
tot_sink = 0.0
offramp_in = 0.0
print(f"{'k':>3s} {'urban_ttt':>10s} {'n_u':>8s} {'sink':>8s} {'offramp->urban':>15s}")
for k in range(40):
    ctrl = baseline_control("no_control", cfg, sim.state, zs)
    res = sim.step(ctrl, zs, k)
    d = res.diagnostics
    ttt = float(res.urban_ttt)
    tot_ttt += ttt
    s = float(getattr(sim.state, "last_urban_sink_veh", 0.0))
    tot_sink += s
    off = 0.0
    for key in d:
        if "offramp" in key.lower() and ("urban" in key.lower() or "storage" in key.lower()):
            if "veh" in key.lower() and "ttt" not in key.lower():
                off += float(d[key])
    offramp_in += off
    n = (float(sim.state.protected_accumulation_veh(net))
         + float(sim.state.boundary_in_queue_vehicles(net)))
    if k < 8:
        print(f"{k:3d} {ttt:10.3f} {n:8.1f} {s:8.2f} {off:15.3f}")
    if n < 1.0:
        break
print(f"\nTRUE drain TTS = {tot_ttt:.2f} veh*h over {k+1} steps")
print(f"누적 sink(실제 이탈 대수) = {tot_sink:.1f} veh  vs  시작 n_u = {n_u0:.1f} veh")
print(f"누적 offramp->urban 유입 = {offramp_in:.1f} veh (오염분)")
print(f"오염 비율 = {offramp_in / max(n_u0,1e-9) * 100:.1f}% of n_u")
print(f"\n실측 평균 체류시간 = TTS/n_u = {tot_ttt/n_u0:.4f} h = {tot_ttt/n_u0*60:.2f} min")
CAP = len(net.boundary_out_links) * float(net.boundary_out_capacity_veh_h) * tc_h
print(f"far(cap={CAP:.0f}) 함의 평균 체류 = {n_u0*tc_h/(2*CAP)*60:.2f} min")
print(f"far(640)  함의 평균 체류 = {n_u0*tc_h/(2*640.0)*60:.2f} min")
print(f"far(obs={sink0:.0f}) 함의 평균 체류 = {n_u0*tc_h/(2*max(sink0,1))*60:.2f} min")
