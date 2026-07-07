# [probe] full corridor-joint offset이 격차를 닫나 — 우리 궤적서 5신호 offset 공동 최적화
"""사용자 우선 진단(2026-07-07): "격차=offset"은 아직 유추(Codex 오라클 주입 Step3=무효,
궤적-특이). legacy 이식 대신 **우리 궤적 위에서 전 신호 offset을 공동 최적화**해 horizon TTT가
얼마나 주는지 잰다 = "leader-joint offset의 상한 가치". FP-면역(단일 상태).

방법: 혼잡 step 재생성 → 전 신호 offset을 (a) per-signal best-response 1라운드 (b) 좌표하강
3라운드(green-wave 결합은 라운드로 창발) 로 최적화, offset=0 대비 horizon TTT 감소 측정.
green은 trace 고정(follower가 이미 정한 값). 비교: joint 감소 × 40스텝 vs 격차(~1150-1850,
같은 env) vs FP 노이즈 하한(~700). 크면 offset이 격차 몸통(leader-joint 구현 정당),
작으면 격차≠offset(다른 곳).

CLI: python -B work/corridor_joint_offset_probe.py --scenario sweet_190 --steps 24,30,36
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


def horizon_ttt(cfg, profile, controls, state_k, k, offsets):
    """전 신호 offset을 offsets dict로 덮고 나머지(green 등) trace 고정, horizon 전역 TTT."""
    dt = cfg.simulation.control_interval
    horizon = max(1, cfg.mpc.horizon_steps)
    cycle = cfg.network.cycle_length
    s = state_k.copy()
    ttt = 0.0
    for j in range(horizon):
        demand = profile.at(s.time_sec)
        ctrl = controls[k + j].copy()
        ctrl.offsets = dict(controls[k + j].offsets)
        for sig, off in offsets.items():
            ctrl.offsets[sig] = float(off) % cycle
        r = run_coupled_interval(s, ctrl, demand, cfg)
        ttt += float(r.freeway_ttt) + float(r.urban_ttt)
        s.time_sec += dt
    return float(ttt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="sweet_190")
    ap.add_argument("--steps", default="24,30,36")
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()
    steps = [int(x) for x in args.steps.split(",") if x.strip()]

    cfg, scenario = build_cfg(args.scenario)
    profile = DemandProfile(cfg, scenario)
    controls = load_legacy_controls(cfg, str(ROOT / TRACE))
    net = cfg.network
    cycle = net.cycle_length
    horizon = max(1, cfg.mpc.horizon_steps)
    signals = list(net.signals)
    # offset 후보 격자(legacy std 28-45 커버): 0..cycle 8등분.
    grid = [round(f * cycle / 8.0, 3) for f in range(8)]

    print(f"=== corridor-joint offset probe {args.scenario} cycle={cycle:.0f} "
          f"signals={signals} grid={len(grid)}pts rounds={args.rounds} ===", flush=True)

    per_step = []
    for k in steps:
        if any((k + j) not in controls for j in range(horizon)):
            print(f"skip step {k}: trace missing"); continue
        state_k = replay_to_step(cfg, profile, controls, k)
        base = horizon_ttt(cfg, profile, controls, state_k, k, {s: 0.0 for s in signals})

        # (a) per-signal best-response 1라운드(다른 신호 offset=0 고정).
        single = {}
        for sig in signals:
            best = (base, 0.0)
            for off in grid:
                offs = {s: 0.0 for s in signals}; offs[sig] = off
                t = horizon_ttt(cfg, profile, controls, state_k, k, offs)
                if t < best[0]:
                    best = (t, off)
            single[sig] = best[1]
        single_ttt = horizon_ttt(cfg, profile, controls, state_k, k, single)

        # (b) 좌표하강 3라운드(green-wave 결합 창발).
        joint = {s: 0.0 for s in signals}
        for _ in range(args.rounds):
            for sig in signals:
                best = (horizon_ttt(cfg, profile, controls, state_k, k, joint), joint[sig])
                for off in grid:
                    trial = dict(joint); trial[sig] = off
                    t = horizon_ttt(cfg, profile, controls, state_k, k, trial)
                    if t < best[0] - 1e-9:
                        best = (t, off)
                joint[sig] = best[1]
        joint_ttt = horizon_ttt(cfg, profile, controls, state_k, k, joint)

        single_gain = base - single_ttt
        joint_gain = base - joint_ttt
        coupling_gain = single_ttt - joint_ttt  # 좌표하강이 per-signal 위에 더 준 것
        per_step.append((joint_gain, single_gain))
        print(f"\n--- step {k} (t={state_k.time_sec:.0f}s) base_horizon_TTT={base:.2f} ---", flush=True)
        print(f"  per-signal best:   TTT={single_ttt:8.2f}  gain={single_gain:6.2f}  "
              f"offsets={ {s: round(single[s],0) for s in signals} }", flush=True)
        print(f"  joint(좌표하강):    TTT={joint_ttt:8.2f}  gain={joint_gain:6.2f}  "
              f"coupling+={coupling_gain:5.2f}  offsets={ {s: round(joint[s],0) for s in signals} }",
              flush=True)

    if per_step:
        import statistics
        jm = statistics.mean(g for g, _ in per_step)
        print(f"\n=== SUMMARY (joint offset value/horizon): "
              f"mean={jm:.2f}  max={max(g for g,_ in per_step):.2f} veh-h ===", flush=True)
        print(f"  40스텝 상한 추정 ~= {jm*40:.0f} veh-h  vs 격차(g1df~legacy ~1150-1850) "
              f"vs FP 노이즈(~700)", flush=True)


if __name__ == "__main__":
    main()
