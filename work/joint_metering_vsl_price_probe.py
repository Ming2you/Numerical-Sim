# [probe] metering×VSL cross-term 가격이 신호를 갖는가 (Task 3) — sub-critical에서만
"""notes §6.1 가설: metering(유입)·VSL(속도)은 freeway bottleneck의 결합 쌍이라 per-lever
1차 편미분이 약해도 cross-term ∂²TTT/∂meter∂vsl가 신호를 가질 수 있다.

⚠️ metering 절벽 caveat(§12): capacity drop 위(ρ>ρ_crit)에선 미분 자체가 무의미(3국면
붕괴). 그래서 **sub-critical(ρ<ρ_crit) 상태에서만** probe한다 — 매끄러운 영역에서
cross-term이 사나 본다. 여기서도 0이면 RM/VSL joint도 무효 → metering=constraint(F1RHO) 확정.

green×offset probe(joint_green_offset_price_probe.py)와 동형: (Δmeter, ΔVSL) 2D 격자의
전역 horizon TTT를 재고, joint 최선이 metering-only 슬라이스를 이기는지·이득이 노이즈
(7200s FP 발산 ~700/40스텝 ≈ 17.5 veh·h/step) 초과인지 본다.

CLI: python -B work/joint_metering_vsl_price_probe.py --scenario sweet_190
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.demand import DemandProfile
from src.simulation.coupling import run_coupled_interval
from src.models.state import segment_vsl
from work.step_a_oracle_probe import build_cfg, load_legacy_controls, replay_to_step

TRACE = "outputs/_b2tr_sweet190_7200/P-STACK-WU-FAITHFUL-B2TR/control_timeseries.csv"


def horizon_ttt(cfg, profile, controls, state_k, k, ramp, link, seg, dmeter, dvsl):
    """ego ramp만 metering+=dmeter, ego segment만 VSL+=dvsl, 나머지 trace 고정, horizon TTT."""
    dt = cfg.simulation.control_interval
    horizon = max(1, cfg.mpc.horizon_steps)
    cap = float(cfg.network.ramp_capacity_veh_h[ramp])
    ff = cfg.freeway_follower
    vlo, vhi = min(ff.vsl_set), max(ff.vsl_set)
    s = state_k.copy()
    ttt = 0.0
    for j in range(horizon):
        demand = profile.at(s.time_sec)
        ctrl = controls[k + j].copy()
        ctrl.ramp_metering = dict(controls[k + j].ramp_metering)
        ctrl.vsl = dict(controls[k + j].vsl)
        m = float(ctrl.ramp_metering.get(ramp, cap)) + dmeter
        ctrl.ramp_metering[ramp] = max(0.0, min(cap, m))
        base_v = float(segment_vsl(controls[k + j], link, seg, cfg))
        v = max(vlo, min(vhi, base_v + dvsl))
        ctrl.vsl[f"{link}__seg{seg}"] = v
        ctrl.vsl[link] = min(float(ctrl.vsl.get(link, vhi)), v)
        r = run_coupled_interval(s, ctrl, demand, cfg)
        ttt += float(r.freeway_ttt) + float(r.urban_ttt)
        s.time_sec += dt
    return float(ttt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="sweet_190")
    ap.add_argument("--trace", default=TRACE)
    ap.add_argument("--steps", default="")  # 비면 자동으로 sub-critical step 탐색
    args = ap.parse_args()

    cfg, scenario = build_cfg(args.scenario)
    profile = DemandProfile(cfg, scenario)
    controls = load_legacy_controls(cfg, str(ROOT / args.trace))
    net = cfg.network
    rho_crit = float(net.rho_crit)
    horizon = max(1, cfg.mpc.horizon_steps)

    # sub-critical step 자동 탐색: 각 step 시작 상태의 본선 최대 밀도 < ρ_crit.
    if args.steps.strip():
        steps = [int(x) for x in args.steps.split(",") if x.strip()]
    else:
        steps = []
        for k in range(2, 40):
            if any((k + j) not in controls for j in range(horizon)):
                continue
            s = replay_to_step(cfg, profile, controls, k)
            max_rho = max((max(s.freeway_density.get(l, [0])) for l in net.freeway_links),
                          default=0.0)
            if max_rho < rho_crit:
                steps.append(k)
            if len(steps) >= 3:
                break
    print(f"=== metering×VSL cross-term probe {args.scenario}  ρ_crit={rho_crit} ===")
    print(f"sub-critical steps: {steps}", flush=True)

    dmeter_grid = [-300.0, -150.0, 0.0, 150.0, 300.0]
    dvsl_grid = [-20.0, -10.0, 0.0, 10.0, 20.0]

    gains = []
    for k in steps:
        state_k = replay_to_step(cfg, profile, controls, k)
        max_rho = max((max(state_k.freeway_density.get(l, [0])) for l in net.freeway_links),
                      default=0.0)
        print(f"\n--- step {k} (t={state_k.time_sec:.0f}s, max_rho={max_rho:.1f}) ---", flush=True)
        # 각 link의 소유 ramp 하나 + 그 link의 병목 segment(최대 밀도)로 probe.
        for link in net.freeway_links:
            owned = [r for r in net.ramps if net.ramp_to_freeway.get(r) == link]
            if not owned:
                continue
            ramp = owned[0]
            rhos = state_k.freeway_density.get(link, [0.0])
            seg = max(range(len(rhos)), key=lambda i: rhos[i]) if rhos else 0
            base = horizon_ttt(cfg, profile, controls, state_k, k, ramp, link, seg, 0.0, 0.0)
            best = (base, 0.0, 0.0)
            meter_only_best = (base, 0.0)
            for dm in dmeter_grid:
                for dv in dvsl_grid:
                    t = horizon_ttt(cfg, profile, controls, state_k, k, ramp, link, seg, dm, dv)
                    if t < best[0]:
                        best = (t, dm, dv)
                    if dv == 0.0 and t < meter_only_best[0]:
                        meter_only_best = (t, dm)
            gain = meter_only_best[0] - best[0]
            needs_vsl = abs(best[2]) > 1e-9
            gains.append(gain)
            print(f"  {link}/{ramp} seg{seg}: base={base:8.2f}  meter_only={meter_only_best[0]:8.2f}"
                  f"(Δm={meter_only_best[1]:+.0f})  joint={best[0]:8.2f}"
                  f"(Δm={best[1]:+.0f},Δvsl={best[2]:+.0f})  joint_gain={gain:6.3f}  "
                  f"needs_vsl={needs_vsl}", flush=True)
    if gains:
        import statistics
        print(f"\n=== SUMMARY: joint_gain over {len(gains)} link-steps: max={max(gains):.3f} "
              f"mean={statistics.mean(gains):.3f}  (7200s noise floor ~17.5/step) ===", flush=True)


if __name__ == "__main__":
    main()
