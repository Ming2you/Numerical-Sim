# 사후 오라클: 전체 제어 시퀀스를 진짜 plant TTT로 좌표하강 최적화 — open-loop 달성가능 상한 측정
"""proxy 없는 진짜 천장(2026-07-10 심야).

- 채점 = MixedTrafficSimulator 실측 total_ttt (proxy 부재 → optimizer's curse 원천 차단).
- 시드 = 플래그십 폐루프 런의 실현 제어 시퀀스(control_timeseries.csv) → 개선만 수락하므로
  "≥ 시드" 보장이 **진짜 목적함수 기준으로** 성립(POLISH의 proxy-보장 실패 교훈 반영).
- prefix 스냅샷: 스텝 t 섭동은 t 이후만 재시뮬(deepcopy 스냅샷 복원).
- 결과 지위: 완전 정보(전 수요 기지·모델=plant) open-loop 오라클 — 인과 컨트롤러와의
  공정 비교가 아니라 plant의 물리적 달성가능값 측정(논문: oracle upper bound).
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import time
from pathlib import Path
from typing import Dict, List

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator


def load_seed(csv_path: Path, cfg: ExperimentConfig) -> List[ControlAction]:
    net = cfg.network
    seq: List[ControlAction] = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            c = ControlAction.uncontrolled(cfg)
            c.green_times = {}
            for s in net.signals:
                c.green_times[f"{s}_p1"] = float(row[f"green_{s}_p1"])
                c.green_times[f"{s}_p2"] = float(row[f"green_{s}_p2"])
            c.offsets = {s: float(row.get(f"offset_{s}", 0.0)) for s in net.signals}
            c.ramp_metering = {r: float(row[f"ramp_metering_{r}"]) for r in net.ramps}
            vsl: Dict[str, float] = {}
            for link in net.freeway_links:
                if f"vsl_{link}" in row:
                    vsl[link] = float(row[f"vsl_{link}"])
                for i in range(net.freeway_segments_per_link):
                    key = f"vsl_{link}_seg{i}"
                    if key in row:
                        vsl[f"{link}__seg{i}"] = float(row[key])
            c.vsl = vsl
            c.inflow_outflow_allocation = {}
            seq.append(c)
    return seq


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="sweet_190")
    ap.add_argument("--seed-csv", required=True)
    ap.add_argument("--T-total", type=float, default=7200.0)
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--output", default="outputs/_13p/oracle")
    args = ap.parse_args()

    cfg = ExperimentConfig.from_file(
        "src/config/default.yaml", {"simulation": {"T_total": args.T_total}},
    )
    sc = load_scenarios("src/config/scenarios.yaml")[args.scenario]
    cfg = apply_scenario_network_overrides(cfg, sc)
    profile = DemandProfile(cfg, sc)
    net = cfg.network
    ci = cfg.simulation.control_interval
    steps = max(1, int(round(cfg.simulation.T_total / ci)))
    demands = [profile.horizon(i * ci, 1)[0] for i in range(steps)]

    seq = load_seed(Path(args.seed_csv), cfg)
    assert len(seq) >= steps, f"seed steps {len(seq)} < {steps}"
    seq = seq[:steps]

    def simulate_from(t0: int, snap, seq_: List[ControlAction]) -> tuple[float, list]:
        """t0부터 끝까지 전진 — 반환 (final total_ttt, t0 이후 각 스텝 종료 스냅샷)."""
        sim = copy.deepcopy(snap)
        snaps_after = []
        for i in range(t0, steps):
            sim.step(seq_[i], demands[i], i)
            snaps_after.append(copy.deepcopy(sim))
        return float(sim.total_ttt), snaps_after

    # ---- 시드 재현 검증 + 스냅샷 구축 ----
    base_sim = MixedTrafficSimulator(cfg)
    t0 = time.perf_counter()
    seed_ttt, snaps = simulate_from(0, base_sim, seq)
    sim_cost = time.perf_counter() - t0
    print(f"[oracle] seed replay TTT={seed_ttt:.1f} (full-sim {sim_cost:.2f}s)", flush=True)
    snapshots = [base_sim] + snaps[:-1]  # snapshots[t] = 스텝 t 시작 시점 상태

    vsl_sorted = sorted(float(v) for v in cfg.freeway_follower.vsl_set)
    g_lo, g_hi = float(net.green_min), float(net.green_max)
    g_total = float(net.effective_green_total)
    gq = 5.0
    mq = 250.0

    def lever_moves(c: ControlAction) -> List[tuple]:
        moves = []
        for s in net.signals:
            moves.append(("g", s))
        for r in net.ramps:
            moves.append(("m", r))
        for link in net.freeway_links:
            for i in range(net.freeway_segments_per_link):
                moves.append(("v", f"{link}__seg{i}"))
        return moves

    best_ttt = seed_ttt
    accepted = 0
    evals = 0
    t_start = time.perf_counter()
    for p in range(args.passes):
        pass_accepted = 0
        for t in range(steps):
            for kind, key in lever_moves(seq[t]):
                cands: List[float] = []
                if kind == "g":
                    cur = seq[t].green_times[f"{key}_p1"]
                    for d in (gq, -gq):
                        nv = cur + d
                        if g_lo <= nv <= g_hi and g_lo <= g_total - nv <= g_hi:
                            cands.append(nv)
                elif kind == "m":
                    cur = seq[t].ramp_metering[key]
                    cap = float(net.ramp_capacity_veh_h[key])
                    for d in (mq, -mq):
                        nv = min(max(cur + d, 0.0), cap)
                        if abs(nv - cur) > 1e-9:
                            cands.append(nv)
                else:
                    cur = seq[t].vsl.get(key, vsl_sorted[-1])
                    idx = min(range(len(vsl_sorted)), key=lambda k: abs(vsl_sorted[k] - cur))
                    for di in (1, -1):
                        j = idx + di
                        if 0 <= j < len(vsl_sorted):
                            cands.append(vsl_sorted[j])
                for nv in cands:
                    trial = copy.deepcopy(seq[t])
                    if kind == "g":
                        trial.green_times[f"{key}_p1"] = nv
                        trial.green_times[f"{key}_p2"] = g_total - nv
                    elif kind == "m":
                        trial.ramp_metering[key] = nv
                    else:
                        trial.vsl[key] = nv
                        link = key.split("__")[0]
                        segs = [trial.vsl.get(f"{link}__seg{i}", vsl_sorted[-1])
                                for i in range(net.freeway_segments_per_link)]
                        trial.vsl[link] = min(segs)
                    old = seq[t]
                    seq[t] = trial
                    ttt, new_snaps = simulate_from(t, snapshots[t], seq)
                    evals += 1
                    if ttt < best_ttt - 1e-6:
                        best_ttt = ttt
                        accepted += 1
                        pass_accepted += 1
                        for k, sn in enumerate(new_snaps[:-1]):
                            if t + 1 + k < steps:
                                snapshots[t + 1 + k] = sn
                        break  # 이 lever는 수락 — 다음 lever로
                    seq[t] = old
        el = time.perf_counter() - t_start
        print(f"[oracle] pass {p+1}/{args.passes}: TTT={best_ttt:.1f} "
              f"(accepted {pass_accepted}, cum evals {evals}, {el:.0f}s)", flush=True)
        if pass_accepted == 0:
            break

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "oracle_summary.json", "w", encoding="utf-8") as f:
        json.dump({
            "scenario": args.scenario, "seed_ttt": seed_ttt, "oracle_ttt": best_ttt,
            "improvement": seed_ttt - best_ttt, "accepted_moves": accepted,
            "evals": evals, "elapsed_sec": time.perf_counter() - t_start,
        }, f, indent=2)
    rows = []
    for t, c in enumerate(seq):
        row: Dict[str, float] = {"step": t}
        for s in net.signals:
            row[f"green_{s}_p1"] = c.green_times[f"{s}_p1"]
        for r in net.ramps:
            row[f"ramp_metering_{r}"] = c.ramp_metering[r]
        for link in net.freeway_links:
            for i in range(net.freeway_segments_per_link):
                row[f"vsl_{link}_seg{i}"] = c.vsl.get(f"{link}__seg{i}", vsl_sorted[-1])
        rows.append(row)
    with open(out / "oracle_controls.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"[oracle] FINAL: seed {seed_ttt:.1f} -> oracle {best_ttt:.1f} "
          f"(improvement {seed_ttt - best_ttt:.1f})", flush=True)


if __name__ == "__main__":
    main()
