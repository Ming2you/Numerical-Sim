# [Step B2 검증] P-Stack sweet_190 3600s: green_price_enabled True vs False (TTT·step시간)
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
scenarios = load_scenarios(str(ROOT/"src/config/scenarios.yaml"))
scenario = scenarios["sweet_190"]
cfg = apply_scenario_network_overrides(base_cfg.with_updates({}), scenario)

# green_price_enabled를 강제하는 어댑터 서브클래스 훅: run_controller 내부가 _ControllerAdapter를
# 만들므로, 모듈 클래스의 __init__을 감싸 flag를 세팅한다(모듈 미변경 — 런타임 몽키패치).
_orig_init = scc._ControllerAdapter.__init__
FLAG = {"value": True}
def _patched_init(self, cfg_, controller_id):
    _orig_init(self, cfg_, controller_id)
    if controller_id == "PROPOSED-STACKELBERG":
        self._impl.green_price_enabled = FLAG["value"]
scc._ControllerAdapter.__init__ = _patched_init

def run(flag: bool, tag: str):
    FLAG["value"] = flag
    out = ROOT/f"outputs/_b2_closedloop/sweet_190/pstack_{tag}"
    t0 = _time.perf_counter()
    result = scc.run_controller(cfg, scenario, "PROPOSED-STACKELBERG", out)
    wall = _time.perf_counter() - t0
    steps = len(result["run_rows"])
    return result["total_ttt"], wall, steps

ttt_off, wall_off, n_off = run(False, "off")
ttt_on, wall_on, n_on = run(True, "on")

print("\n=== P-STACK CLOSED-LOOP (sweet_190 3600s) ===")
print(f"green_price OFF: total_ttt={ttt_off:.4f}  wall={wall_off:.1f}s  steps={n_off}  ({wall_off/max(n_off,1):.2f}s/step)")
print(f"green_price ON : total_ttt={ttt_on:.4f}  wall={wall_on:.1f}s  steps={n_on}  ({wall_on/max(n_on,1):.2f}s/step)")
delta = ttt_on - ttt_off
pct = 100.0*delta/ttt_off if ttt_off else 0.0
print(f"ON - OFF = {delta:+.4f} TTT ({pct:+.3f}%)  [negative=improvement]")
print(f"step-time overhead: {(wall_on-wall_off)/max(n_on,1):+.2f}s/step")
json.dump({"ttt_off":ttt_off,"ttt_on":ttt_on,"wall_off":wall_off,"wall_on":wall_on,
           "steps":n_on,"delta":delta,"pct":pct},
          open(ROOT/"outputs/_b2_closedloop/summary.json","w"), indent=2)
