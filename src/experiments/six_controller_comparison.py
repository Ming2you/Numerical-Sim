# Stage 1 6-controller 비교 runner (spec 16, plan §2) — 동일 plant/demand/horizon/TTT 회계
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.analysis.authority import (
    LEADER_ENABLED,
    PRIMARY_CONTROLLERS,
    check_control_authority,
)
from src.analysis.free_flow_reference import FreeFlowReference, compute_free_flow_reference
from src.controllers.centralized_mpc import CentralizedMPC
from src.controllers.distributed_coordinator import DistributedCoordinator
from src.controllers.stackelberg_mpc import StackelbergMPCController
from src.controllers.wu_distributed import WuDistributedController
from src.models.demand import (
    DemandProfile,
    ScenarioConfig,
    apply_scenario_network_overrides,
    load_scenarios,
)
from src.models.state import ControlAction, ExperimentConfig
from src.simulation.simulator import MixedTrafficSimulator, control_row, state_row


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({k for row in rows for k in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class _ControllerAdapter:
    """6개 controller를 동일 decide 인터페이스로 감싸고 계산량 진단을 표준화한다."""

    def __init__(self, cfg: ExperimentConfig, controller_id: str):
        self.cfg = cfg
        self.controller_id = controller_id
        self.previous: Optional[ControlAction] = None
        if controller_id == "WU-CD-F":
            self._impl = WuDistributedController(cfg, leader_enabled=False)
        elif controller_id == "WU-MATCHED-STACKELBERG":
            self._impl = WuDistributedController(cfg, leader_enabled=True)
        elif controller_id == "WU-CC-F":
            self._impl = CentralizedMPC(cfg, mode="wu")
        elif controller_id == "PROPOSED-FOLLOWERS-ONLY":
            self._impl = DistributedCoordinator(cfg)
        elif controller_id == "PROPOSED-STACKELBERG":
            # spec 16.8: proposed Stackelberg의 follower는 distributed player 구조다.
            cfg.mpc.follower_solver_mode = "distributed"
            self._impl = StackelbergMPCController(cfg)
        elif controller_id == "PROPOSED-CENTRALIZED":
            self._impl = CentralizedMPC(cfg, mode="proposed")
        else:
            raise ValueError(f"Unknown controller id: {controller_id}")

    def decide(self, state, forecast) -> tuple[ControlAction, Dict[str, float]]:
        start = time.perf_counter()
        diag: Dict[str, float] = {}
        if self.controller_id in {"WU-CD-F", "WU-MATCHED-STACKELBERG"}:
            info = self._impl.decide_with_info(state, forecast, self.previous)
            control = info.control
            diag = {
                "solver_evaluations": float(info.solver_evaluations),
                "solver_converged": float(info.converged),
                "coordination_iterations": float(info.iterations),
                "coupling_residual": float(info.coupling_residual),
                "leader_candidate_count": float(info.leader_candidates),
                "leader_objective": float(info.leader_objective),
            }
        elif self.controller_id in {"WU-CC-F", "PROPOSED-CENTRALIZED"}:
            info = self._impl.decide_with_info(state, forecast, self.previous)
            control = info.control
            diag = {
                "solver_evaluations": float(info.solver_evaluations),
                "solver_converged": float(info.converged),
                "leader_candidate_count": 0.0,
            }
        elif self.controller_id == "PROPOSED-FOLLOWERS-ONLY":
            # leaderless distributed: leader=None — 숨은 전역 목표 없음(spec 16.7).
            nash = self._impl.solve(state.copy(), None, forecast, self.previous)
            control = nash.control
            n_agents = len(self._impl.urban_agents) + len(self._impl.freeway_agents)
            diag = {
                "solver_evaluations": float(nash.iterations * n_agents),
                "solver_converged": float(nash.converged),
                "coordination_iterations": float(nash.iterations),
                "coupling_residual": float(nash.residual_control),
                "leader_candidate_count": 0.0,
            }
        else:  # PROPOSED-STACKELBERG
            result = self._impl.decide_with_info(state, forecast, self.previous)
            control = result.control
            n_agents = (
                len(self._impl.nash_solver.urban_agents) + len(self._impl.nash_solver.freeway_agents)
                if hasattr(self._impl.nash_solver, "urban_agents") else 1
            )
            candidates = float(result.metadata.get("leader_candidate_count", 0.0))
            iters = float(result.control.diagnostics.get("nash_iterations", 0.0))
            rollout_evals = (
                self.cfg.mpc.horizon_steps
                if float(result.metadata.get("leader_rollout_prediction_used", 0.0)) > 0.5
                else 0
            )
            diag = {
                "solver_evaluations": candidates * (iters * n_agents + rollout_evals),
                "solver_converged": float(result.control.diagnostics.get("nash_converged", 0.0)),
                "coordination_iterations": iters,
                "leader_candidate_count": candidates,
                "leader_objective": float(result.leader_objective),
            }
            for key, value in result.metadata.items():
                if key.startswith("leader_") and isinstance(value, (int, float, bool)):
                    diag[key] = float(value)
        diag.update({
            "relaxed_quantized_controls": float(self.cfg.mpc.relaxed_quantized_controls),
            "relaxed_rounding_mode_floor": float(self.cfg.mpc.relaxed_rounding_mode == "floor"),
            "relaxed_rounding_mode_nearest": float(self.cfg.mpc.relaxed_rounding_mode == "nearest"),
            "green_quantization_residual_sec": float(control.diagnostics.get("green_quantization_residual_sec", 0.0)),
            "vsl_quantization_residual_km_h": float(control.diagnostics.get("vsl_quantization_residual_km_h", 0.0)),
            "green_repair_count": float(control.diagnostics.get("green_repair_count", 0.0)),
            "vsl_repair_count": float(control.diagnostics.get("vsl_repair_count", 0.0)),
        })
        diag["computation_time_sec"] = time.perf_counter() - start
        self.previous = control.copy()
        return control, diag


def run_controller(
    cfg: ExperimentConfig,
    scenario: ScenarioConfig,
    controller_id: str,
    output_dir: Path,
) -> Dict[str, Any]:
    """단일 controller closed-loop 실행 — 모든 controller가 같은 plant/step 루프를 쓴다."""
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = DemandProfile(cfg, scenario)
    sim = MixedTrafficSimulator(cfg)
    adapter = _ControllerAdapter(cfg, controller_id)
    steps = max(1, int(round(cfg.simulation.T_total / cfg.simulation.control_interval)))
    run_rows: List[Dict[str, Any]] = []
    control_rows: List[Dict[str, Any]] = []
    state_rows: List[Dict[str, Any]] = []
    decision_rows: List[Dict[str, Any]] = []
    for step in range(steps):
        t = step * cfg.simulation.control_interval
        forecast = profile.horizon(t, cfg.mpc.horizon_steps)
        control, diag = adapter.decide(sim.state.copy(), forecast)
        log = sim.step(control, forecast[0], step)
        run_rows.append({"step": step, "time_sec": sim.state.time_sec, **{
            k: v for k, v in log.diagnostics.items() if isinstance(v, (int, float, bool))
        }, "freeway_ttt": log.freeway_ttt, "urban_ttt": log.urban_ttt})
        control_rows.append(control_row(control, cfg, step, sim.state.time_sec))
        state_rows.append(state_row(sim.state, cfg, step))
        decision_rows.append({"step": step, **diag})
    _write_csv(output_dir / "run_log.csv", run_rows)
    _write_csv(output_dir / "control_timeseries.csv", control_rows)
    _write_csv(output_dir / "state_timeseries.csv", state_rows)
    _write_csv(output_dir / "decision_diagnostics.csv", decision_rows)
    return {
        "run_rows": run_rows,
        "control_rows": control_rows,
        "state_rows": state_rows,
        "decision_rows": decision_rows,
        "final_state": sim.state,
        "total_ttt": sim.total_ttt,
        "urban_ttt": sim.urban_ttt,
        "freeway_ttt": sim.freeway_ttt,
    }


def summarize_controller(
    cfg: ExperimentConfig,
    controller_id: str,
    result: Dict[str, Any],
    reference: FreeFlowReference,
) -> Dict[str, Any]:
    """spec 16.12 Common diagnostics — TTT/delay/throughput/terminal/계산량 한 묶음."""
    net = cfg.network
    rows = result["run_rows"]
    horizon_h = cfg.simulation.T_total / 3600.0
    t_c_h = cfg.simulation.T_c_h
    completed_urban = sum(float(r.get("boundary_out_sink_veh", 0.0)) for r in rows)
    completed_freeway = sum(float(r.get("mainline_exit_flow_total", 0.0)) * t_c_h for r in rows)
    completed = completed_urban + completed_freeway
    final = result["final_state"]
    onramp_terminal = sum(final.ramp_queue.values()) + sum(
        max(0.0, final.urban_movement_queue.get(m, 0.0))
        for movements in net.on_ramp_to_movement.values()
        for m in movements
    )
    total_delay = result["total_ttt"] - reference.total_ttt
    urban_delay = result["urban_ttt"] - reference.urban_ttt
    freeway_delay = result["freeway_ttt"] - reference.freeway_ttt
    decisions = result["decision_rows"]
    auth = check_control_authority(controller_id, result["control_rows"], cfg)
    return {
        "controller_id": controller_id,
        "authority_group": auth["authority_group"],
        "leader_enabled": controller_id in LEADER_ENABLED,
        "centralized": auth["centralized"],
        "authority_ok": auth["ok"],
        "authority_violations": ";".join(auth["violations"]),
        "total_ttt": round(result["total_ttt"], 3),
        "urban_ttt": round(result["urban_ttt"], 3),
        "freeway_ttt": round(result["freeway_ttt"], 3),
        "free_flow_reference_total_ttt": round(reference.total_ttt, 3),
        "free_flow_reference_urban_ttt": round(reference.urban_ttt, 3),
        "free_flow_reference_freeway_ttt": round(reference.freeway_ttt, 3),
        "total_delay": round(total_delay, 3),
        "urban_delay": round(urban_delay, 3),
        "freeway_delay": round(freeway_delay, 3),
        "completed_vehicles": round(completed, 1),
        "network_throughput_veh_h": round(completed / max(horizon_h, 1e-9), 1),
        "average_delay_per_completed_vehicle_h": round(total_delay / max(completed, 1.0), 6),
        "terminal_total_vehicles": round(
            final.total_urban_vehicles(net) + final.total_freeway_vehicles(net), 1
        ),
        "terminal_urban_vehicles": round(final.total_urban_vehicles(net), 1),
        "terminal_onramp_vehicles": round(onramp_terminal, 1),
        "terminal_freeway_vehicles": round(final.total_freeway_vehicles(net) - sum(final.ramp_queue.values()), 1),
        "computation_time_sec": round(sum(float(d.get("computation_time_sec", 0.0)) for d in decisions), 2),
        "solver_evaluations": round(sum(float(d.get("solver_evaluations", 0.0)) for d in decisions), 0),
        "solver_converged_rate": round(
            sum(float(d.get("solver_converged", 0.0)) for d in decisions) / max(len(decisions), 1), 3
        ),
    }


# 주 비교쌍(spec 16.10, 2026-06-13 개정). ProposedLeaderValue는 Leader+allocation
# coordination layer의 "결합" 효과다 — Leader 단독 효과로 해석하지 않는다.
PAIRED_COMPARISONS = [
    ("ProposedLeaderValue", "PROPOSED-FOLLOWERS-ONLY", "PROPOSED-STACKELBERG"),
    ("ProposedCentralizationGap", "PROPOSED-STACKELBERG", "PROPOSED-CENTRALIZED"),
    ("FollowerPackageDifference", "WU-CD-F", "PROPOSED-FOLLOWERS-ONLY"),
    ("FullPackageValue", "WU-CD-F", "PROPOSED-STACKELBERG"),
]
# 보조 참고군 쌍 — 해당 controller를 명시 실행한 경우에만 부록으로 계산된다.
APPENDIX_COMPARISONS = [
    ("WuLeaderValue", "WU-CD-F", "WU-MATCHED-STACKELBERG"),
    ("WuCentralizationGap", "WU-CD-F", "WU-CC-F"),
    ("LeaderPackageDifference", "WU-MATCHED-STACKELBERG", "PROPOSED-STACKELBERG"),
]


def paired_rows(summaries: Dict[str, Dict[str, Any]], delay_eps: float) -> List[Dict[str, Any]]:
    """spec 16.10 쌍 — TTT/delay/throughput/terminal 차이를 한 행으로(16.11 규칙 적용).

    주 비교쌍 + (실행된 경우) 부록 쌍. 양쪽 controller가 모두 실행된 쌍만 계산한다."""
    rows = []
    for name, base_id, other_id in PAIRED_COMPARISONS + APPENDIX_COMPARISONS:
        if base_id not in summaries or other_id not in summaries:
            continue
        b, c = summaries[base_id], summaries[other_id]
        delay_abs = b["total_delay"] - c["total_delay"]
        if b["total_delay"] <= delay_eps:
            delay_pct: Any = "NA"  # low-delay 규칙(16.11): 절대 차이를 주 지표로.
        else:
            delay_pct = round(100.0 * delay_abs / b["total_delay"], 2)
        rows.append({
            "comparison": name,
            "baseline_controller": base_id,
            "other_controller": other_id,
            "ttt_difference": round(b["total_ttt"] - c["total_ttt"], 3),
            "delay_improvement_abs": round(delay_abs, 3),
            "delay_improvement_pct": delay_pct,
            "throughput_difference": round(
                c["network_throughput_veh_h"] - b["network_throughput_veh_h"], 1
            ),
            "terminal_total_difference": round(
                c["terminal_total_vehicles"] - b["terminal_total_vehicles"], 1
            ),
            "computation_time_ratio": round(
                c["computation_time_sec"] / max(b["computation_time_sec"], 1e-9), 2
            ),
            "negative_delay_flag": bool(b["total_delay"] < 0.0 or c["total_delay"] < 0.0),
        })
    return rows


FIDELITY_MATRIX_MD = """# Stage 1 fidelity matrix (plan §2.4)

| controller | plant | authority | objective | horizon | solver | coupling iteration | 차이의 영향 |
|---|---|---|---|---|---|---|---|
| WU-CD-F | 공유 plant(METANET+movement queue, storage-cap spillback, **per-segment VSL**) | green p1+**segment 벡터 VSL** (offset 0, metering=용량, allocation 無) | agent local 순수 TTS(Σ L·λ_eff·ρ+ramp 큐)+Δu (인위적 결합 항 無 — VSL 활성화는 storage-aware probe의 λ-recovery 순수 TTS 예측에서만) | freeway는 Np=10(freeway_prediction_horizon_steps), 그 외 공통 T_c×horizon | 원문 MILP/SQP 대신 결정적 후보탐색(경량 국소 큐/밀도 모델, freeway는 Np×K_cf substep storage-aware probe로 capacity-drop·λ 회복 내생화 + segment 벡터 VSL 탐색: 병목 seg는 {max,prev}, 상류는 max_vsl_step 내) | Jacobi: y 고정→agent solve가 outgoing y를 후보 제어로 갱신→under-relaxation(α=0.5) 전파, S_max=5 | local 모델이 거칠어 분산해의 질이 원문 대비 보수적일 수 있음. VSL은 free-flow 가지에서만 metering 성립(과포화 시 이득→0, 정직 한계) |
| WU-MATCHED-STACKELBERG | 동일 | 동일 | local + w·pos(n_pred−ω·target) conditioning | 동일 | follower=위와 동일, leader=후보 열거+coupled 예측 | 동일 | leader 후보 9개 고정 그리드 — conditioning이 binding하지 않으면 WU-CD-F와 동일해질 수 있음 |
| WU-CC-F | 동일 | 동일(green+VSL) | J_WU_global(TTS+Δu) | 동일 | seeded random search(budget 보고) | 없음 | 보장된 전역최적 아님 — 동일 budget 수치 참조 |
| PROPOSED-FOLLOWERS-ONLY | 동일 | green 자유탐색([green_min,green_max] 후보)+offset+metering+VSL (allocation 無) | agent local 잔여 큐+Δgreen (전역 target 無) | 동일 | 신호별 green 후보탐색 + leaderless metering 국소 후보선택 | coupling iteration | allocation 비제어 — movement service는 plant 포화유율 fallback(Wu와 동일) |
| PROPOSED-STACKELBERG | 동일 | 동일 full | leader J_L(16.8)+follower 휴리스틱 | 동일 | leader 후보×distributed Nash | coupling iteration | 기존 검증된 controller |
| PROPOSED-CENTRALIZED | 동일 | 동일 full | J_PROPOSED_SYSTEM(TTS+초과+Δu) | 동일 | seeded random search | 없음 | allocation을 게이트 service level로 매개변수화(차원 축소 근사) |

공통: Wu off-ramp spillback(식22 차로수 감소)은 본 plant의 storage-cap 방식으로 대응(효과 등가,
wu2022_reference §8). VSL 변화 제약은 양방향 max_vsl_step(Wu는 감소만 제한) — 기존 plant 정의 유지.

per-segment VSL은 권한 확대가 아니라 같은 VSL 권한의 공간 입자도 세분화다(link 1값 uniform→
segment 벡터). uniform VSL은 병목 segment까지 같이 늦춰 mainstream metering이 불가능했고 강한
capacity-drop에서도 ΔTTS가 정확히 0이었다(Option C 이후 상류 segment VSL↓ ΔTTS 음수). capacity_drop
시나리오(점유 ~22%, λ_eff≈1.98)는 실증 무대가 아니라 "이 망은 심한 capacity-drop을 잘 안 만든다"의
정직 근거이며, VSL 작동 실증은 test_c의 강제 98% 상태(λ_eff≈1.70)로 한다(wu2022_reference §8).
"""


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="src/config/default.yaml")
    parser.add_argument("--scenarios-config", default="src/config/scenarios.yaml")
    parser.add_argument("--scenario", default="peak_demand")
    parser.add_argument("--T-total", type=float, default=None)
    parser.add_argument("--output", default="post_analysis/stage1")
    parser.add_argument("--controllers", default=",".join(PRIMARY_CONTROLLERS))
    parser.add_argument("--delay-eps", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--relaxed-quantized-controls",
        action="store_true",
        help="Enable spec 17 relaxed continuous targets with quantized feasible controls.",
    )
    parser.add_argument("--relaxed-rounding-mode", choices=["floor", "nearest"], default=None)
    parser.add_argument("--relaxed-green-quantum-sec", type=float, default=None)
    parser.add_argument("--relaxed-vsl-quantum-km-h", type=float, default=None)
    args = parser.parse_args(argv)

    overrides: Dict[str, Any] = {}
    if args.T_total is not None:
        overrides["simulation"] = {"T_total": args.T_total}
    if args.seed is not None:
        overrides.setdefault("simulation", {})["random_seed"] = args.seed
    if args.relaxed_quantized_controls:
        overrides.setdefault("mpc", {})["relaxed_quantized_controls"] = True
    if args.relaxed_rounding_mode is not None:
        overrides.setdefault("mpc", {})["relaxed_rounding_mode"] = args.relaxed_rounding_mode
    if args.relaxed_green_quantum_sec is not None:
        overrides.setdefault("mpc", {})["relaxed_green_quantum_sec"] = args.relaxed_green_quantum_sec
    if args.relaxed_vsl_quantum_km_h is not None:
        overrides.setdefault("mpc", {})["relaxed_vsl_quantum_km_h"] = args.relaxed_vsl_quantum_km_h
    base_cfg = ExperimentConfig.from_file(args.config, overrides)
    scenarios = load_scenarios(args.scenarios_config)
    if args.scenario == "all":
        scenario_names = list(scenarios)
    else:
        scenario_names = [name.strip() for name in args.scenario.split(",") if name.strip()]
    unknown = [name for name in scenario_names if name not in scenarios]
    if unknown:
        raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}. Available: {', '.join(sorted(scenarios))}")
    # 시나리오 한정 off-ramp split override를 cfg.network에 단일 주입(plant+모든 controller 공유).
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    requested = [c.strip() for c in args.controllers.split(",") if c.strip()]
    if len(scenario_names) != 1:
        raise SystemExit(
            "This runner executes one scenario per invocation; run it once per scenario for all-scenario screening."
        )
    scenario_name = scenario_names[0]
    scenario = scenarios[scenario_name]
    # Scenario overrides are injected after config overrides so all controllers share the same plant.
    cfg = apply_scenario_network_overrides(base_cfg.with_updates({}), scenario)

    # free-flow reference는 시나리오/seed당 1회 — 여섯 controller 공통(spec 16.11).
    reference = compute_free_flow_reference(cfg, scenario)
    _write_csv(out / "free_flow_reference.csv", [{
        "scenario": scenario_name,
        "seed": cfg.simulation.random_seed,
        "total_ttt": reference.total_ttt,
        "urban_ttt": reference.urban_ttt,
        "freeway_ttt": reference.freeway_ttt,
    }])

    summaries: Dict[str, Dict[str, Any]] = {}
    for controller_id in requested:
        result = run_controller(cfg, scenario, controller_id, out / "runs" / scenario_name / controller_id)
        summaries[controller_id] = summarize_controller(cfg, controller_id, result, reference)
        print(f"{controller_id}: ttt={summaries[controller_id]['total_ttt']:.1f} "
              f"delay={summaries[controller_id]['total_delay']:.1f} "
              f"authority_ok={summaries[controller_id]['authority_ok']}")
    _write_csv(out / "six_controller_summary.csv", list(summaries.values()))
    (out / "fidelity_matrix.md").write_text(FIDELITY_MATRIX_MD, encoding="utf-8")
    _write_csv(out / "optimization_diagnostics.csv", [
        {
            "controller_id": cid,
            "computation_time_sec": s["computation_time_sec"],
            "solver_evaluations": s["solver_evaluations"],
            "solver_converged_rate": s["solver_converged_rate"],
        }
        for cid, s in summaries.items()
    ])
    pair_rows = paired_rows(summaries, args.delay_eps)
    if pair_rows:
        _write_csv(out / "paired_comparisons.csv", pair_rows)
    (out / "summary.json").write_text(
        json.dumps({"scenario": scenario_name, "summaries": summaries}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"STAGE1 scenario={scenario_name} controllers={len(summaries)} output={out}")


if __name__ == "__main__":
    main()
