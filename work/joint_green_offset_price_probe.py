# [probe] per-signal (green, offset) JOINT 가격이 신호를 갖는가 — F3(offset 단독=0)의 다음 질문
"""사용자 가설(2026-07-06): offset 단독 편미분은 0이나 green과 결합하면(∂²TTT/∂g∂off)
가치가 생긴다 — "언제(offset) × 얼마나(green)". 구현 전 결정적 probe:

혼잡 운영점에서 ego 비-ramp 신호의 (Δp1, Δoffset) 2D 격자에 대한 **전역 horizon TTT**를
평가해, 최소가 (a) green 축 위(Δoff*=0 — offset 무가치, F3 재확인)냐 (b) 축 밖(둘 다
움직여야 — joint 가격에 신호)냐를 가른다. green-only 슬라이스 최선과 joint 최선을 비교해
"joint가 green 단독을 이기는 이득"을 정량화한다.

경계 구분: per-signal (g,off) joint가 신호를 가지면 = **가격 프레임의 새 채널(우리 레인)**.
여전히 ~0이면 = 순수 cross-signal corridor(=Codex의 후보-패턴 레인).

replay: B2TR committed control_timeseries를 trace로 써서 혼잡 step까지 전진(오라클 불요).
CLI: python -B work/joint_green_offset_price_probe.py --steps 18,24,30
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
from work.step_a_oracle_probe import build_cfg, load_legacy_controls, replay_to_step

TRACE = "outputs/_b2tr_sweet190_7200/P-STACK-WU-FAITHFUL-B2TR/control_timeseries.csv"


def horizon_ttt(cfg, profile, controls, state_k, k, signal, dp1, doff):
    """ego 신호만 p1+=dp1, offset+=doff, 나머지 trace 고정, horizon 전역 TTT."""
    dt = cfg.simulation.control_interval
    horizon = max(1, cfg.mpc.horizon_steps)
    total = cfg.network.effective_green_total
    cycle = cfg.network.cycle_length
    s = state_k.copy()
    ttt = 0.0
    for j in range(horizon):
        demand = profile.at(s.time_sec)
        ctrl = controls[k + j].copy()
        ctrl.green_times = dict(controls[k + j].green_times)
        ctrl.offsets = dict(controls[k + j].offsets)
        p1 = float(ctrl.green_times.get(f"{signal}_p1", total / 2.0)) + dp1
        p1 = max(cfg.network.green_min, min(cfg.network.green_max, p1))
        ctrl.green_times[f"{signal}_p1"] = p1
        ctrl.green_times[f"{signal}_p2"] = total - p1
        ctrl.offsets[signal] = (float(ctrl.offsets.get(signal, 0.0)) + doff) % cycle
        r = run_coupled_interval(s, ctrl, demand, cfg)
        ttt += float(r.freeway_ttt) + float(r.urban_ttt)
        s.time_sec += dt
    return float(ttt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="sweet_190")
    ap.add_argument("--steps", default="18,24,30")
    args = ap.parse_args()
    steps = [int(x) for x in args.steps.split(",") if x.strip()]

    cfg, scenario = build_cfg(args.scenario)
    profile = DemandProfile(cfg, scenario)
    controls = load_legacy_controls(cfg, str(ROOT / TRACE))
    net = cfg.network
    cycle = net.cycle_length
    non_ramp = [s for s in net.signals
                if not any(net.ramp_to_freeway.get(r) and r for r in [])  # placeholder
                ]
    # 비-ramp 판정: on_ramp_to_movement에 안 걸리는 신호 = offset 대상.
    ramp_signals = set()
    for movements in net.on_ramp_to_movement.values():
        for m in movements:
            # movement 이름의 앞글자가 신호 — 스펙에서 D/F가 ramp 신호.
            pass
    non_ramp = [s for s in net.signals if s in ("A", "B", "C")]

    dp1_grid = [-6.0, -3.0, 0.0, 3.0, 6.0]
    doff_grid = [-cycle / 4, -cycle / 8, 0.0, cycle / 8, cycle / 4]

    print(f"=== (green,offset) joint price probe  {args.scenario}  "
          f"cycle={cycle:.0f}s ===", flush=True)
    agg_joint_beats = []
    for k in steps:
        if any((k + j) not in controls for j in range(max(1, cfg.mpc.horizon_steps))):
            print(f"skip step {k}: trace missing", flush=True)
            continue
        state_k = replay_to_step(cfg, profile, controls, k)
        print(f"\n--- step {k} (t={state_k.time_sec:.0f}s) ---", flush=True)
        for sig in non_ramp:
            best = (float("inf"), 0.0, 0.0)
            green_only_best = (float("inf"), 0.0)
            base = None
            for dp1 in dp1_grid:
                for doff in doff_grid:
                    t = horizon_ttt(cfg, profile, controls, state_k, k, sig, dp1, doff)
                    if dp1 == 0.0 and doff == 0.0:
                        base = t
                    if t < best[0]:
                        best = (t, dp1, doff)
                    if doff == 0.0 and t < green_only_best[0]:
                        green_only_best = (t, dp1)
            joint_gain = green_only_best[0] - best[0]  # joint가 green-only보다 더 준 TTT
            needs_off = abs(best[2]) > 1e-9
            agg_joint_beats.append(joint_gain)
            print(f"  {sig}: base={base:8.2f}  green_only_best={green_only_best[0]:8.2f}"
                  f"(Δp1={green_only_best[1]:+.0f})  joint_best={best[0]:8.2f}"
                  f"(Δp1={best[1]:+.0f},Δoff={best[2]:+.0f})  "
                  f"joint_gain={joint_gain:6.2f}  needs_offset={needs_off}", flush=True)
    if agg_joint_beats:
        import statistics
        print(f"\n=== SUMMARY: joint_gain over {len(agg_joint_beats)} signal-steps: "
              f"max={max(agg_joint_beats):.2f} mean={statistics.mean(agg_joint_beats):.2f} "
              f"n(gain>1)={sum(1 for g in agg_joint_beats if g > 1.0)} ===", flush=True)


if __name__ == "__main__":
    main()
