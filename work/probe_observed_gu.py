# OBSERVED-Gu 전제 검증: (1) 관측 유출이 state에 실려 rollout까지 가는가
# (2) skew면 실제로 낮은가 — 낮지 않으면 이 아이디어는 성립 안 한다.
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ExperimentConfig
from src.simulation.baseline import baseline_control
from src.simulation.simulator import MixedTrafficSimulator


def run(scenario_name, steps=40):
    overrides = {"mpc": {"relaxed_quantized_controls": True, "grid_parallel_backend": "serial"},
                 "simulation": {"T_total": float(steps * 180)}}
    cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), overrides)
    scenarios = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))
    scenario = scenarios[scenario_name]
    cfg = apply_scenario_network_overrides(cfg, scenario)
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    out = []
    for step in range(steps):
        forecast = profile.horizon(sim.state.time_sec, 1)
        ctrl = baseline_control("no_control", cfg, sim.state, forecast[0])
        sim.step(ctrl, forecast[0], step)
        n_u = sim.state.protected_accumulation_veh(cfg.network)
        sink = getattr(sim.state, "last_urban_sink_veh", None)
        out.append((step, n_u, sink))
    return cfg, out


print("=== NC 40스텝: n_u와 관측 유출(last_urban_sink_veh) ===")
print(f"{'시나리오':18s} {'스텝':>4s} {'n_u':>9s} {'sink/구간':>10s} {'G_obs[veh/h]':>13s}")
print('-' * 62)
rows = {}
for sc in ('sweet_170_w', 'sweet_170_skew_w'):
    cfg, out = run(sc)
    tc_h = float(cfg.simulation.T_c_h)
    rows[sc] = (cfg, out)
    for step in (0, 19, 30, 39):
        s, n_u, sink = out[step]
        if sink is None:
            print(f"{sc:18s} {s:4d}  ★필드 미도달(None) — 배관 실패")
            break
        print(f"{sc:18s} {s:4d} {n_u:9.1f} {sink:10.2f} {sink / tc_h:13.1f}")
    print()

# 핵심 판정: 같은 부하에서 skew가 유출이 낮은가
if all(v[1][-1][2] is not None for v in rows.values()):
    a = rows['sweet_170_w'][1]
    b = rows['sweet_170_skew_w'][1]
    tc_h = float(rows['sweet_170_w'][0].simulation.T_c_h)
    late_a = sum(x[2] for x in a[20:]) / len(a[20:]) / tc_h
    late_b = sum(x[2] for x in b[20:]) / len(b[20:]) / tc_h
    print("=== ★전제 검증: 같은 총수요에서 skew가 유출을 떨어뜨리는가 ===")
    print(f"  170_w      후반 평균 G_obs = {late_a:8.1f} veh/h")
    print(f"  170_skew_w 후반 평균 G_obs = {late_b:8.1f} veh/h")
    print(f"  차이 = {late_b - late_a:+8.1f} ({(late_b / late_a - 1) * 100:+.2f}%)")
    print()
    print("  판정: " + ("★skew가 유출 낮음 — 관측 g_u가 이질성을 잡는다(전제 성립)"
                       if late_b < late_a * 0.995 else
                       "✗ skew가 유출을 안 떨어뜨림 — 관측 g_u로도 skew를 못 본다(전제 실패)"))
