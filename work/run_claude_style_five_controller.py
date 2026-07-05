from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.free_flow_reference import compute_free_flow_reference
from src.controllers.classical_hierarchical import ClassicalHierarchicalController
from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.stackelberg_wu_metered import StackelbergWuMeteredController
from src.controllers.wu_faithful_follower import WuFaithfulFollower
from src.models.demand import DemandProfile, apply_scenario_network_overrides, load_scenarios
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.baseline import baseline_control
from src.simulation.simulator import MixedTrafficSimulator, control_row, state_row


CONTROLLERS = [
    "NO-CONTROL",
    "WU-CD-F",
    "WU-FAITHFUL-FOLLOWER",
    "P-STACK-WU-FAITHFUL",
    "CLASSICAL-HIERARCHICAL",
]

# 3점 사다리(2026-07-03 §4d) 변형 ID — 기본 5종의 거동은 불변:
#   WU-FAITHFUL-FOLLOWER-NOP1 : rung1 = PFO 순수 own-TTS(P1 blocked-inflow 가격 OFF).
#   WU-FAITHFUL-FOLLOWER      : rung2 = PFO + tax(P1 ON, leader 없음) — 기존 기본값.
#   P-STACK-WU-FAITHFUL       : rung3 = leader + marginal price(B2 ON) — B2가 기본.
#   P-STACK-WU-FAITHFUL-NOB2  : rung3의 가격 채널 귀속용 A/B(B2 OFF, 구 P-Stack).
LADDER_VARIANTS = [
    "WU-FAITHFUL-FOLLOWER-NOP1",
    "P-STACK-WU-FAITHFUL-NOB2",
]

# P1.5 재검토(조건부 활성화) 변형:
#   WU-FAITHFUL-FOLLOWER-P15SAT  : 게이트는 닫아두고 포화도 x만 진단 기록(계측 전용).
#   WU-FAITHFUL-FOLLOWER-P15AUTO : 포화도 band 안의 ramp 신호만 phase-resolved 활성.
P15_VARIANTS = [
    "WU-FAITHFUL-FOLLOWER-P15SAT",
    "WU-FAITHFUL-FOLLOWER-P15AUTO",
]


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_cfg(scenario_name: str, t_total: float) -> tuple[ExperimentConfig, Any]:
    overrides = {
        "mpc": {
            "relaxed_quantized_controls": True,
            "grid_parallel_backend": "serial",
            "leader_search_mode": "grid",
            "stackelberg_leader_parallel_backend": "serial",
        },
        "simulation": {"T_total": float(t_total)},
    }
    cfg = ExperimentConfig.from_file(str(ROOT / "src" / "config" / "default.yaml"), overrides)
    scenarios = load_scenarios(str(ROOT / "src" / "config" / "scenarios.yaml"))
    scenario = scenarios[scenario_name]
    cfg = apply_scenario_network_overrides(cfg, scenario)
    return cfg, scenario


def make_controller(controller_id: str, cfg: ExperimentConfig):
    if controller_id == "NO-CONTROL":
        return None
    if controller_id == "WU-CD-F":
        return DistributedCoordinator(cfg, ablation="WU_GREEN_VSL_ONLY_TTT")
    if controller_id == "WU-FAITHFUL-FOLLOWER":
        return WuFaithfulFollower(cfg)
    if controller_id == "WU-FAITHFUL-FOLLOWER-NOP1":
        follower = WuFaithfulFollower(cfg)
        follower.count_blocked_ramp_inflow = False
        return follower
    if controller_id == "WU-FAITHFUL-FOLLOWER-P15SAT":
        follower = WuFaithfulFollower(cfg)
        follower.ramp_aware_phase_auto = True
        follower.ramp_aware_phase_auto_band = (9.0e9, 9.0e9)  # 계측 전용(게이트 불발)
        return follower
    if controller_id == "WU-FAITHFUL-FOLLOWER-P15AUTO":
        follower = WuFaithfulFollower(cfg)
        follower.ramp_aware_phase_auto = True
        return follower
    if controller_id == "P-STACK-WU-FAITHFUL":
        return StackelbergWuMeteredController(cfg)
    # 2026-07-05 §8부터 P-STACK-WU-FAITHFUL 기본 = green 가격 + trust(=B2TR).
    # -B2 = 무제한 가격(trust 없음, sweet_155 폭주 재현/역사적 비교용).
    if controller_id == "P-STACK-WU-FAITHFUL-B2":
        controller = StackelbergWuMeteredController(cfg)
        controller.signal_price_enabled = True
        controller.signal_price_trust_sec = None
        return controller
    # B3: green + metering 가격, trust 없음(과소방류 나선 재현/역사적 비교용).
    if controller_id == "P-STACK-WU-FAITHFUL-B3":
        controller = StackelbergWuMeteredController(cfg)
        controller.signal_price_enabled = True
        controller.signal_price_trust_sec = None
        controller.metering_price_enabled = True
        controller.metering_price_trust_frac = None
        return controller
    # B3TR: 기본(green+trust) + metering 가격+trust(격자 맞춤 δ) — 나선의 월권 처방 검증.
    if controller_id == "P-STACK-WU-FAITHFUL-B3TR":
        controller = StackelbergWuMeteredController(cfg)
        controller.metering_price_enabled = True
        return controller
    # B2TR: green 가격 + trust region(가격 유효 범위 = 유한차분 이웃 ±6s) —
    # B2.1 폭주(선형 가격의 이웃 밖 월권, 2026-07-05 §6·§7 진단)의 원인 직결 처방.
    if controller_id == "P-STACK-WU-FAITHFUL-B2TR":
        controller = StackelbergWuMeteredController(cfg)
        controller.signal_price_enabled = True
        controller.signal_price_trust_sec = controller.signal_price_delta_sec
        return controller
    # B2BAR: green 가격 + barrier(선형 fw+spillback) 보정, metering 가격 없음 —
    # sweet_155 B2 폭발(+10.3%)의 barrier 처방 검증(spillback이 조여질 때만 자동 발화).
    if controller_id == "P-STACK-WU-FAITHFUL-B2BAR":
        controller = StackelbergWuMeteredController(cfg)
        controller.signal_price_enabled = True
        controller.barrier_price_enabled = True
        return controller
    # B2BAR50: 사용자 제안의 urban critical capacity(0.5·cap 초과분) 기준 —
    # 발화가 이르고(반차부터) 양방향(2026-07-05 probe: green축 C −0.21, A/B/F +0.03~0.04).
    if controller_id == "P-STACK-WU-FAITHFUL-B2BAR50":
        controller = StackelbergWuMeteredController(cfg)
        controller.signal_price_enabled = True
        controller.barrier_price_enabled = True
        controller.barrier_spillback_frac = 0.5
        return controller
    # B4: B3 + rho_crit barrier 가격(절벽 예고 항), trust 없음(역사적 재현용 — 무력 판정).
    if controller_id == "P-STACK-WU-FAITHFUL-B4":
        controller = StackelbergWuMeteredController(cfg)
        controller.signal_price_enabled = True
        controller.signal_price_trust_sec = None
        controller.metering_price_enabled = True
        controller.metering_price_trust_frac = None
        controller.barrier_price_enabled = True
        return controller
    if controller_id == "P-STACK-WU-FAITHFUL-NOB2":
        # 기본이 OFF가 되면서 P-STACK-WU-FAITHFUL과 동일 — 과거 런 재현용 별칭으로 유지.
        controller = StackelbergWuMeteredController(cfg)
        controller.signal_price_enabled = False
        return controller
    # N_UF 등식→cap A/B(2026-07-03): budget을 상한으로만 쓰는 cap 모드 변형.
    if controller_id == "P-STACK-WU-FAITHFUL-NUFCAP":
        cfg.mpc.wu_faithful_nuf_coordination_mode = "cap"
        return StackelbergWuMeteredController(cfg)
    # standalone(=PFO incumbent/fallback 없이 leader 후보만) — 등식 budget 악화 사례의 A/B.
    if controller_id == "P-STACK-WU-FAITHFUL-STANDALONE":
        cfg.mpc.stackelberg_enable_fallback = False
        cfg.mpc.stackelberg_enable_pfo_incumbent = False
        return StackelbergWuMeteredController(cfg)
    if controller_id == "P-STACK-WU-FAITHFUL-STANDALONE-NUFCAP":
        cfg.mpc.stackelberg_enable_fallback = False
        cfg.mpc.stackelberg_enable_pfo_incumbent = False
        cfg.mpc.wu_faithful_nuf_coordination_mode = "cap"
        return StackelbergWuMeteredController(cfg)
    if controller_id == "CLASSICAL-HIERARCHICAL":
        return ClassicalHierarchicalController(cfg)
    raise ValueError(f"Unknown controller: {controller_id}")


def decide(controller_id: str, controller, sim: MixedTrafficSimulator, forecast, previous, cfg, step: int):
    if controller_id == "NO-CONTROL":
        return baseline_control("no_control", cfg, sim.state, forecast[0])
    if controller_id in {
        "WU-CD-F",
        "WU-FAITHFUL-FOLLOWER",
        "WU-FAITHFUL-FOLLOWER-NOP1",
        "WU-FAITHFUL-FOLLOWER-P15SAT",
        "WU-FAITHFUL-FOLLOWER-P15AUTO",
    }:
        return controller.solve(sim.state.copy(), None, forecast, previous).control
    if controller_id.startswith("P-STACK-WU-FAITHFUL"):
        return controller.decide(sim.state.copy(), forecast, previous, cfg)
    if controller_id == "CLASSICAL-HIERARCHICAL":
        return controller.decide(sim.state.copy(), forecast, previous)
    raise ValueError(f"Unknown controller: {controller_id}")


def summarize(controller_id: str, cfg: ExperimentConfig, sim: MixedTrafficSimulator, decision_rows, run_rows, reference) -> Dict[str, Any]:
    net = cfg.network
    horizon_h = cfg.simulation.T_total / 3600.0
    t_c_h = cfg.simulation.T_c_h
    completed_urban = sum(float(r.get("boundary_out_sink_veh", 0.0)) for r in run_rows)
    completed_freeway = sum(float(r.get("mainline_exit_flow_total", 0.0)) * t_c_h for r in run_rows)
    completed = completed_urban + completed_freeway
    final = sim.state
    onramp_terminal = sum(final.ramp_queue.values()) + sum(
        max(0.0, final.urban_movement_queue.get(m, 0.0))
        for movements in net.on_ramp_to_movement.values()
        for m in movements
    )
    compute_times = [float(row.get("computation_time_sec", 0.0)) for row in decision_rows]
    total_delay = sim.total_ttt - reference.total_ttt
    return {
        "controller_id": controller_id,
        "total_ttt": round(sim.total_ttt, 3),
        "urban_ttt": round(sim.urban_ttt, 3),
        "freeway_ttt": round(sim.freeway_ttt, 3),
        "free_flow_reference_total_ttt": round(reference.total_ttt, 3),
        "total_delay": round(total_delay, 3),
        "urban_delay": round(sim.urban_ttt - reference.urban_ttt, 3),
        "freeway_delay": round(sim.freeway_ttt - reference.freeway_ttt, 3),
        "completed_vehicles": round(completed, 1),
        "completed_urban_vehicles": round(completed_urban, 1),
        "completed_freeway_vehicles": round(completed_freeway, 1),
        "network_throughput_veh_h": round(completed / max(horizon_h, 1e-9), 1),
        "terminal_total_vehicles": round(final.total_urban_vehicles(net) + final.total_freeway_vehicles(net), 1),
        "terminal_urban_vehicles": round(final.total_urban_vehicles(net), 1),
        "terminal_onramp_vehicles": round(onramp_terminal, 1),
        "terminal_freeway_vehicles": round(final.total_freeway_vehicles(net) - sum(final.ramp_queue.values()), 1),
        "computation_time_sec": round(sum(compute_times), 3),
        "mean_step_compute_sec": round(float(np.mean(compute_times)) if compute_times else 0.0, 3),
        "max_step_compute_sec": round(float(np.max(compute_times)) if compute_times else 0.0, 3),
    }


def run_one(controller_id: str, scenario_name: str, t_total: float, output_root: Path, reference) -> Dict[str, Any]:
    cfg, scenario = build_cfg(scenario_name, t_total)
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    controller = make_controller(controller_id, cfg)
    previous: Optional[ControlAction] = None
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    run_rows: List[Dict[str, Any]] = []
    control_rows: List[Dict[str, Any]] = []
    state_rows: List[Dict[str, Any]] = []
    decision_rows: List[Dict[str, Any]] = []
    out_dir = output_root / controller_id

    print(f"=== {controller_id} ===", flush=True)
    for step in range(steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        t0 = time.perf_counter()
        control = decide(controller_id, controller, sim, forecast, previous, cfg, step)
        compute_time = time.perf_counter() - t0
        log = sim.step(control, forecast[0], step)
        previous = control.copy()
        decision = {
            "step": step,
            "computation_time_sec": compute_time,
            "N_P_star": control.N_P_star,
            "N_UF_star": control.N_UF_star,
            "solver_evaluations": float(control.diagnostics.get("wu_faithful_local_evals", 0.0)),
            "wu_faithful_active": float(control.diagnostics.get("wu_faithful_follower_active", 0.0)),
            "leader_candidate_count": float(control.diagnostics.get("leader_candidate_count", 0.0)),
            "leader_full_evaluated_count": float(control.diagnostics.get("leader_candidate_full_evaluated_count", 0.0)),
            "leader_serial_override": float(control.diagnostics.get("leader_candidate_wu_metered_serial_override", 0.0)),
        }
        # 가격(wu_b2_/wu_b3_/wu_b4_)·P1.5 포화도(wu_p15_*) 진단은 control_row에 안 실리므로 여기서 수집.
        decision.update({
            k: float(v) for k, v in control.diagnostics.items()
            if k.startswith(("wu_b2_", "wu_b3_", "wu_b4_", "wu_p15_"))
            and isinstance(v, (int, float, bool))
        })
        decision_rows.append(decision)
        control_rows.append(control_row(control, cfg, step, sim.state.time_sec))
        state_rows.append(state_row(sim.state, cfg, step))
        row = {
            "step": step,
            "time_sec": sim.state.time_sec,
            "step_total_ttt": log.freeway_ttt + log.urban_ttt,
            "step_urban_ttt": log.urban_ttt,
            "step_freeway_ttt": log.freeway_ttt,
            "cumulative_total_ttt": sim.total_ttt,
            "cumulative_urban_ttt": sim.urban_ttt,
            "cumulative_freeway_ttt": sim.freeway_ttt,
            "computation_time_sec": compute_time,
        }
        row.update({k: v for k, v in log.diagnostics.items() if isinstance(v, (int, float, bool))})
        run_rows.append(row)
        print(
            f"{controller_id} step {step + 1}/{steps} "
            f"cum_ttt={sim.total_ttt:.3f} step_ttt={row['step_total_ttt']:.3f} "
            f"solve={compute_time * 1000.0:.0f}ms",
            flush=True,
        )

    if hasattr(controller, "close"):
        controller.close()

    write_csv(out_dir / "run_log.csv", run_rows)
    write_csv(out_dir / "control_timeseries.csv", control_rows)
    write_csv(out_dir / "state_timeseries.csv", state_rows)
    write_csv(out_dir / "decision_diagnostics.csv", decision_rows)
    summary = summarize(controller_id, cfg, sim, decision_rows, run_rows, reference)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="sweet_190")
    parser.add_argument("--T-total", type=float, default=3600.0)
    parser.add_argument("--output", default="outputs/claude_style_sweet190_3600_20260629")
    parser.add_argument("--controllers", default=",".join(CONTROLLERS))
    args = parser.parse_args()

    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    cfg, scenario = build_cfg(args.scenario, args.T_total)
    reference = compute_free_flow_reference(cfg, scenario)
    selected = [item.strip() for item in args.controllers.split(",") if item.strip()]
    summaries: List[Dict[str, Any]] = []
    for controller_id in selected:
        summaries.append(run_one(controller_id, args.scenario, args.T_total, output_root, reference))

    no_control = next((row for row in summaries if row["controller_id"] == "NO-CONTROL"), None)
    for row in summaries:
        if no_control and row["controller_id"] != "NO-CONTROL":
            row["ttt_improvement_vs_no_control_pct"] = round(
                100.0 * (no_control["total_ttt"] - row["total_ttt"]) / max(no_control["total_ttt"], 1.0e-9),
                3,
            )
            row["delay_improvement_vs_no_control_pct"] = round(
                100.0 * (no_control["total_delay"] - row["total_delay"]) / max(no_control["total_delay"], 1.0e-9),
                3,
            )
        else:
            row["ttt_improvement_vs_no_control_pct"] = 0.0
            row["delay_improvement_vs_no_control_pct"] = 0.0

    write_csv(output_root / "summary.csv", summaries)
    (output_root / "summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print("\n========== SUMMARY ==========", flush=True)
    for row in summaries:
        print(
            f"{row['controller_id']}: total_ttt={row['total_ttt']:.3f} "
            f"delay={row['total_delay']:.3f} "
            f"impr={row['ttt_improvement_vs_no_control_pct']:+.2f}% "
            f"completed={row['completed_vehicles']:.1f} "
            f"terminal={row['terminal_total_vehicles']:.1f} "
            f"mean_solve={row['mean_step_compute_sec']:.3f}s",
            flush=True,
        )


if __name__ == "__main__":
    main()
