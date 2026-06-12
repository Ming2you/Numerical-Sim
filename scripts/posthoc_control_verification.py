# 시나리오 런 출력에서 control별 효과·allocation before/after를 사후검증하는 분석 스크립트(수정 없음, 측정 전용)
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_actuator_diagnostics import svg_chart  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.models.state import ExperimentConfig  # noqa: E402
from src.models.urban_queue_model import boundary_group_key, movement_specs, movement_storage_capacity, safe_balance_index  # noqa: E402


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _f(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key))
    except (TypeError, ValueError):
        return default


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _corr(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    vy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if vx * vy <= 1e-12:
        return 0.0
    return cov / (vx * vy)


def gate_densities(cfg, state_row: dict) -> dict[str, float]:
    """state snapshot에서 게이트 요소별 집계 밀도(Σq/Σcap)."""
    specs = movement_specs(cfg)
    queues: dict[str, float] = {}
    caps: dict[str, float] = {}
    for movement, spec in specs.items():
        if str(spec.get("kind", "")) != "boundary_in":
            continue
        key = boundary_group_key(spec)
        queues[key] = queues.get(key, 0.0) + _f(state_row, f"movement_queue_{movement}")
        caps[key] = caps.get(key, 0.0) + max(movement_storage_capacity(cfg, movement, spec), 1e-9)
    return {k: queues[k] / caps[k] for k in sorted(queues)}


def analyze(run_dir: Path, label: str, out_dir: Path, cfg) -> dict:
    summary = json.load(open(run_dir / "metrics_summary.json", encoding="utf-8"))
    metrics = summary["metrics"]
    validation = summary["control_validation"]
    prop = {name: _read(run_dir / "proposed" / f"{name}.csv") for name in ("run_log", "state_timeseries", "control_timeseries")}
    base = {name: _read(run_dir / "baseline" / f"{name}.csv") for name in ("run_log", "state_timeseries")}
    rl, st, ctl = prop["run_log"], prop["state_timeseries"], prop["control_timeseries"]
    rlb, stb = base["run_log"], base["state_timeseries"]
    t = [_f(s, "time_sec") for s in st]
    rho_crit = cfg.network.rho_crit

    # --- (1) allocation before/after: 실현 B_in/B_out 시계열 (proposed vs baseline) ---
    svg_chart(
        out_dir / f"{label}_alloc_B_before_after.svg",
        f"[{label}] gate balance B_in — allocation 작동(proposed) vs 없음(baseline)",
        t,
        [
            {"label": "B_in proposed", "values": [_f(r, "B_in") for r in rl], "color": "#2563eb"},
            {"label": "B_in baseline", "values": [_f(r, "B_in") for r in rlb], "color": "#9ca3af"},
            {"label": "gate load proposed [veh]", "values": [_f(r, "boundary_in_load_veh") for r in rl], "color": "#d97706", "axis": "y2"},
        ],
        "B_in",
        "gate load [veh]",
        hlines=[(cfg.evaluation.eps_balance, "eps_balance 0.03", "y")],
    )

    # --- (2) allocation 계획 vs 실현: net inflow target vs 실현 dN_P/dt (feedback 창) ---
    t_c_h = cfg.simulation.T_c_h
    window = max(1, int(round(cfg.leader.N_P_feedback_horizon_h / t_c_h)))
    accs = [_f(r, "urban_accumulation_mean_veh", _f(r, "urban_accumulation_veh")) for r in rl]
    targets = [_f(r, "net_inflow_target") for r in rl]
    realized = [float("nan")] * len(rl)
    for i in range(window, len(rl)):
        realized[i] = (accs[i] - accs[i - window]) / (window * t_c_h)
    valid = [(ti, re, tg) for ti, re, tg in zip(t, realized, targets) if not math.isnan(re)]
    svg_chart(
        out_dir / f"{label}_alloc_plan_vs_realized.svg",
        f"[{label}] allocation net-inflow 계획(target) vs 실현(dN_P/dt, {window}-interval 창)",
        [v[0] for v in valid],
        [
            {"label": "realized dN_P/dt [veh/h]", "values": [v[1] for v in valid], "color": "#2563eb"},
            {"label": "target [veh/h]", "values": [v[2] for v in valid], "color": "#dc2626"},
        ],
        "veh/h",
    )

    # --- (3) perimeter: N_P vs N_P_star (+ baseline N_P) ---
    svg_chart(
        out_dir / f"{label}_np_tracking.svg",
        f"[{label}] N_P 추적 — proposed vs target vs baseline",
        t,
        [
            {"label": "N_P proposed (interval mean)", "values": accs, "color": "#2563eb"},
            {"label": "N_P_star", "values": [_f(r, "urban_accumulation_target_veh") for r in rl], "color": "#dc2626", "step": True},
            {"label": "N_P baseline", "values": [_f(r, "urban_accumulation_mean_veh", _f(r, "urban_accumulation_veh")) for r in rlb], "color": "#9ca3af"},
        ],
        "N_P [veh]",
        hlines=[(cfg.leader.N_P_crit_veh, f"N_P_crit {cfg.leader.N_P_crit_veh:.0f}", "y")],
    )

    # --- 게이트별 시간평균 밀도 (공평성 before/after) ---
    def time_mean_gate_density(states: list[dict]) -> dict[str, float]:
        acc: dict[str, float] = {}
        for s in states:
            for k, v in gate_densities(cfg, s).items():
                acc[k] = acc.get(k, 0.0) + v
        return {k: v / len(states) for k, v in acc.items()}

    gd_prop = time_mean_gate_density(st)
    gd_base = time_mean_gate_density(stb)

    # --- VSL 반응성 ---
    act_r, ina_r = [], []
    for c, s in zip(ctl, st):
        for link in cfg.network.freeway_links:
            v = _f(c, f"vsl_{link}", 100.0)
            r = _f(s, f"rho_{link}_mean") / rho_crit
            (act_r if v < 99.5 else ina_r).append(r)
    vsl_active = sum(1 for c in ctl if any(_f(c, f"vsl_{link}", 100.0) < 99.5 for link in cfg.network.freeway_links))

    # --- green 반응성: p1 비율 vs 직전 상태의 p1 큐 점유율 상관 ---
    specs = movement_specs(cfg)
    p1_movements = {sig: [m for m, sp in specs.items() if sp.get("phase") == f"{sig}_p1"] for sig in cfg.network.signals}
    p2_movements = {sig: [m for m, sp in specs.items() if sp.get("phase") == f"{sig}_p2"] for sig in cfg.network.signals}
    green_corr = {}
    for sig in cfg.network.signals:
        xs, ys = [], []
        for i in range(1, len(ctl)):
            prev_state = st[i - 1]
            q1 = sum(_f(prev_state, f"movement_queue_{m}") for m in p1_movements[sig])
            q2 = sum(_f(prev_state, f"movement_queue_{m}") for m in p2_movements[sig])
            if q1 + q2 <= 1e-9:
                continue
            xs.append(q1 / (q1 + q2))
            g1 = _f(ctl[i], f"green_{sig}_p1")
            g2 = _f(ctl[i], f"green_{sig}_p2")
            ys.append(g1 / max(g1 + g2, 1e-9))
        green_corr[sig] = _corr(xs, ys)

    # --- offset 가동성 ---
    def std(vals: list[float]) -> float:
        m = _mean(vals)
        return math.sqrt(_mean([(v - m) ** 2 for v in vals]))

    offset_std = {sig: std([_f(c, f"offset_{sig}") for c in ctl]) for sig in cfg.network.signals}
    d_off = _mean([(_f(c, "offset_D") - _f(c, "offset_A")) % cfg.network.cycle_length for c in ctl])

    # --- 수치 요약 ---
    out = {
        "label": label,
        "passed": bool(summary.get("passed")),
        "improvement_pct": round(float(summary.get("improvement_pct", 0.0)), 2),
        "gates": {k: bool(v.get("pass")) for k, v in validation.items()},
        "ttt": {
            "baseline": round(metrics.get("baseline_total_ttt", 0.0), 1),
            "proposed": round(metrics.get("proposed_total_ttt", 0.0), 1),
            "freeway_b": round(metrics.get("baseline_freeway_ttt", 0.0), 1),
            "freeway_p": round(metrics.get("proposed_freeway_ttt", 0.0), 1),
            "urban_b": round(metrics.get("baseline_urban_ttt", 0.0), 1),
            "urban_p": round(metrics.get("proposed_urban_ttt", 0.0), 1),
        },
        "allocation": {
            "B_in_baseline": round(metrics.get("baseline_B_in", 0.0), 4),
            "B_in_proposed": round(metrics.get("proposed_B_in", 0.0), 4),
            "B_out_baseline": round(metrics.get("baseline_B_out", 0.0), 4),
            "B_out_proposed": round(metrics.get("proposed_B_out", 0.0), 4),
            "net_inflow_tracking_veh_h": round(metrics.get("proposed_urban_net_inflow_tracking_error_veh_h", 0.0), 1),
            "np_abs_error_veh": round(metrics.get("proposed_urban_accumulation_abs_error_veh", 0.0), 1),
            "gate_density_mean_baseline": {k: round(v, 4) for k, v in gd_base.items()},
            "gate_density_mean_proposed": {k: round(v, 4) for k, v in gd_prop.items()},
            "gate_density_spread_baseline": round(safe_balance_index(list(gd_base.values())), 4),
            "gate_density_spread_proposed": round(safe_balance_index(list(gd_prop.values())), 4),
        },
        "metering": {
            "mean_error": round(metrics.get("proposed_mean_metering_error", 0.0), 1),
            "wr_mean": round(_mean([sum(_f(s, f"ramp_queue_{r}") for r in cfg.network.ramps) for s in st]), 1),
            "wr_max": round(max(sum(_f(s, f"ramp_queue_{r}") for r in cfg.network.ramps) for s in st), 1),
        },
        "vsl": {
            "active_intervals": vsl_active,
            "density_ratio_active": round(_mean(act_r), 3) if act_r else None,
            "density_ratio_inactive": round(_mean(ina_r), 3) if ina_r else None,
            "exceedance_p": metrics.get("proposed_density_exceedance_duration"),
            "exceedance_b": metrics.get("baseline_density_exceedance_duration"),
        },
        "green_queue_corr": {k: round(v, 3) for k, v in green_corr.items()},
        "offset": {"std": {k: round(v, 1) for k, v in offset_std.items()}, "mean_D_minus_A": round(d_off, 1)},
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="src/config/default.yaml")
    args = parser.parse_args()
    cfg = ExperimentConfig.from_file(args.config)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = analyze(Path(args.run_dir), args.label, out_dir, cfg)
    (out_dir / f"{args.label}_posthoc.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
