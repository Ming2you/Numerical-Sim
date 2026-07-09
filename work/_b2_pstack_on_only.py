# [Step B2 검증] P-Stack sweet_190 3600s green_price ON만 완주 (OFF는 이미 완료)
import sys, time as _time, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.models.state import ExperimentConfig
from src.models.demand import apply_scenario_network_overrides, load_scenarios
from src.experiments import six_controller_comparison as scc

overrides = {"simulation": {"T_total": 3600.0},
             "mpc": {"relaxed_quantized_controls": True, "grid_parallel_backend": "thread"}}
base_cfg = ExperimentConfig.from_file(str(ROOT/"src/config/default.yaml"), overrides)
scenario = load_scenarios(str(ROOT/"src/config/scenarios.yaml"))["sweet_190"]
cfg = apply_scenario_network_overrides(base_cfg.with_updates({}), scenario)

_orig_init = scc._ControllerAdapter.__init__
def _patched_init(self, cfg_, controller_id):
    _orig_init(self, cfg_, controller_id)
    if controller_id == "PROPOSED-STACKELBERG":
        self._impl.green_price_enabled = True
scc._ControllerAdapter.__init__ = _patched_init

t0 = _time.perf_counter()
result = scc.run_controller(cfg, scenario, "PROPOSED-STACKELBERG",
                            ROOT/"outputs/_b2_closedloop/sweet_190/pstack_on")
wall = _time.perf_counter()-t0
print(f"\nON DONE total_ttt={result['total_ttt']:.4f} wall={wall:.1f}s steps={len(result['run_rows'])}")
