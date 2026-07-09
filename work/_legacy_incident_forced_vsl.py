# legacy + incident 폐쇄창(2400~4800s) 동안 FW_E 상류 VSL 강제 — 미개척 VSL 가치 측정(baseline 8879)
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.controllers.distributed_coordinator import DistributedCoordinator
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator

MODE = sys.argv[1] if len(sys.argv) > 1 else "seg012_v70"
SC = "sweet_155_incident"
T = 7200.0
WINDOW = (2400.0, 4800.0)
if MODE == "seg012_v70":
    SEGS, VSL = [0, 1, 2], 70.0   # 병목(seg3) 직전까지 전부
elif MODE == "seg01_v60":
    SEGS, VSL = [0, 1], 60.0      # merge(seg2) 이전만
else:
    raise SystemExit(f"unknown mode {MODE}")

cfg = ExperimentConfig.from_file(
    str(ROOT / "src/config/default.yaml"),
    {
        "simulation": {"T_total": T},
        # 정식 러너와 동일 — process pool은 이 머신 standalone서 BrokenProcessPool.
        "mpc": {
            "grid_parallel_backend": "serial",
            "stackelberg_leader_parallel_backend": "serial",
        },
    },
)
scenario = load_scenarios(str(ROOT / "src/config/scenarios.yaml"))[SC]
cfg = apply_scenario_network_overrides(cfg, scenario)
profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)
controller = StackelbergMPCController(cfg)
controller.nash_solver = DistributedCoordinator(cfg)
steps = max(1, int(round(T / cfg.simulation.control_interval)))
print(f"MODE={MODE}: FW_E segs {SEGS} VSL={VSL} during {WINDOW}", flush=True)
t0 = time.perf_counter()
for step in range(steps):
    t = step * cfg.simulation.control_interval
    forecast = profile.horizon(t, cfg.mpc.horizon_steps)
    control = controller.decide(sim.state.copy(), forecast)
    if WINDOW[0] <= t < WINDOW[1]:
        control.vsl = dict(control.vsl)
        for i in SEGS:
            control.vsl[f"FW_E__seg{i}"] = VSL
        control.vsl["FW_E"] = min(float(control.vsl.get("FW_E", VSL)), VSL)
    sim.step(control, forecast[0], step)
    if step % 5 == 0 or step == steps - 1:
        print(f"[{MODE}] step {step+1}/{steps} cum={sim.total_ttt:.0f} u={sim.urban_ttt:.0f} f={sim.freeway_ttt:.0f}", flush=True)
print(f"==== LEGACY+forcedVSL {MODE}: total={sim.total_ttt:.0f} urban={sim.urban_ttt:.0f} freeway={sim.freeway_ttt:.0f} compute={time.perf_counter()-t0:.0f}s", flush=True)
print("baseline: legacy incident(무강제)=8879. 낮으면 미개척 VSL 가치 실재.", flush=True)
