# SLSQP vs structured-grid: 동일 state에서 예측모델상 목적값(best_obj) 직접 비교 프로브.
# 목적: SLSQP가 grid보다 나쁜 실측 TTT의 원인이 "로컬 갇힘"인지 확증한다.
# 두 솔버는 같은 _predict_with_ttt·_objective를 공유(centralized_mpc.py:602,707) →
# 같은 state에서 slsqp best_obj > grid best_obj이면 예측모델 무죄·로컬 갇힘 확정.
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run_claude_style_five_controller import build_cfg  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.controllers.centralized_mpc import CentralizedMPC  # noqa: E402
from src.simulation.baseline import baseline_control  # noqa: E402
from src.simulation.simulator import MixedTrafficSimulator  # noqa: E402
from src.models.demand import DemandProfile  # noqa: E402

SCEN = os.environ.get("PROBE_SCEN", "sweet_155_w")
WARM = 20
PROBE_STEPS = [20, 30, 40]

cfg, scenario = build_cfg(SCEN, 10800.0)
profile = DemandProfile(cfg, scenario)
sim = MixedTrafficSimulator(cfg)

print(f"=== SLSQP vs grid best_obj probe: {SCEN} ===", flush=True)
print(f"solver_mode(default.yaml)={cfg.mpc.centralized_solver_mode}", flush=True)

results = []
prev = None
for step in range(max(PROBE_STEPS) + 1):
    t = step * cfg.simulation.control_interval
    forecast = profile.horizon(t, cfg.mpc.horizon_steps + max(0, cfg.mpc.leader_value_depth))
    if step in PROBE_STEPS:
        state = sim.state.copy()
        # grid
        cfg.mpc.centralized_solver_mode = "structured_grid"
        g = CentralizedMPC(cfg, mode="proposed")
        t0 = time.perf_counter()
        gi = g.decide_with_info(state.copy(), forecast, prev)
        gt = time.perf_counter() - t0
        # slsqp
        cfg.mpc.centralized_solver_mode = "slsqp"
        s = CentralizedMPC(cfg, mode="proposed")
        t0 = time.perf_counter()
        si = s.decide_with_info(state.copy(), forecast, prev)
        st = time.perf_counter() - t0
        gap = si.objective - gi.objective
        verdict = "GRID_BETTER(로컬갇힘)" if gap > 1e-6 else ("SLSQP_BETTER" if gap < -1e-6 else "TIE")
        slsqp_ok = si.control.diagnostics.get("centralized_slsqp_success", -1.0)
        slsqp_fb = si.control.diagnostics.get("centralized_slsqp_fallback_structured_grid", -1.0)
        print(f"step {step}: grid_obj={gi.objective:.4f}({gt:.0f}s)  "
              f"slsqp_obj={si.objective:.4f}({st:.0f}s)  gap(sl-grid)={gap:+.4f}  "
              f"slsqp_success={slsqp_ok} fb={slsqp_fb}  => {verdict}", flush=True)
        results.append((step, gi.objective, si.objective, gap, verdict))
    # closed-loop 전진은 no-control로(두 솔버 비교는 state 무관 — 동일 진입상태만 필요)
    control = baseline_control("no_control", cfg, sim.state, forecast[0])
    sim.step(control, forecast[0], step)
    prev = control.copy()

print("\n=== 요약 ===", flush=True)
grid_wins = sum(1 for r in results if r[4].startswith("GRID_BETTER"))
print(f"GRID_BETTER {grid_wins}/{len(results)} 스텝 — grid_obj가 낮으면 SLSQP가 예측모델상 열등해 수렴(로컬 갇힘)", flush=True)
