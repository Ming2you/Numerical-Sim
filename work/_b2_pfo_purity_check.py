# [Step B2 검증] PFO sweet_128 3600s가 B2 도입 후에도 저장된 참조 런과 비트 동일한지 확인
import sys, hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.models.state import ExperimentConfig
from src.models.demand import apply_scenario_network_overrides, load_scenarios
from src.experiments.six_controller_comparison import run_controller

overrides = {"simulation": {"T_total": 3600.0},
             "mpc": {"relaxed_quantized_controls": True, "grid_parallel_backend": "thread"}}
base_cfg = ExperimentConfig.from_file(str(ROOT/"src/config/default.yaml"), overrides)
scenarios = load_scenarios(str(ROOT/"src/config/scenarios.yaml"))
scenario = scenarios["sweet_128"]
cfg = apply_scenario_network_overrides(base_cfg.with_updates({}), scenario)

out = ROOT/"outputs/_b2_pfo_purity/runs/sweet_128/PROPOSED-FOLLOWERS-ONLY"
result = run_controller(cfg, scenario, "PROPOSED-FOLLOWERS-ONLY", out)

new_ttt = result["total_ttt"]
new_hash = hashlib.sha256((out/"state_timeseries.csv").read_bytes()).hexdigest()

ref_dir = ROOT/"outputs/pfo_sweet128_3600/runs/sweet_128/PROPOSED-FOLLOWERS-ONLY"
ref_ttt = 2191.1599035661484
ref_hash = "950363cf788c65359c40db2e0f87f77917f3f4ed0003ca4f4f7789c25b7f0597"

print("\n=== PFO PURITY (sweet_128 3600s) ===")
print(f"new total_ttt = {new_ttt!r}")
print(f"ref total_ttt = {ref_ttt!r}")
print(f"ttt bit-identical: {new_ttt == ref_ttt}")
print(f"new state sha256 = {new_hash}")
print(f"ref state sha256 = {ref_hash}")
print(f"state sha256 identical: {new_hash == ref_hash}")
