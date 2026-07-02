import csv
import math
import statistics as stats
from pathlib import Path


ROOT = Path("outputs")
SCENARIOS = {
    "sweet190": ROOT / "claude_style_sweet190_3600_20260629",
    "sweet220": ROOT / "claude_style_sweet220_3600_20260629",
}
PFO = "WU-FAITHFUL-FOLLOWER"
PSTACK = "P-STACK-WU-FAITHFUL"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def val(row: dict[str, str], key: str, default: float = 0.0) -> float:
    raw = row.get(key, "")
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def sum_cols(row: dict[str, str], cols: list[str]) -> float:
    return sum(val(row, c) for c in cols)


def mean(rows: list[dict[str, str]], fn) -> float:
    return stats.mean(fn(row) for row in rows)


def print_summary() -> None:
    print("=== SUMMARY DELTAS P-Stack minus PFO ===")
    for scenario, directory in SCENARIOS.items():
        rows = read_csv(directory / "summary.csv")
        by_controller = {row["controller_id"]: row for row in rows}
        pfo = by_controller[PFO]
        pstack = by_controller[PSTACK]
        for metric in [
            "total_ttt",
            "urban_ttt",
            "freeway_ttt",
            "completed_vehicles",
            "terminal_total_vehicles",
            "mean_step_compute_sec",
        ]:
            diff = val(pstack, metric) - val(pfo, metric)
            print(
                scenario,
                metric,
                round(diff, 3),
                "(PFO",
                round(val(pfo, metric), 3),
                "P-Stack",
                round(val(pstack, metric), 3),
                ")",
            )
        pp = val(pstack, "ttt_improvement_vs_no_control_pct") - val(
            pfo, "ttt_improvement_vs_no_control_pct"
        )
        print(scenario, "improvement pp vs no-control delta", round(pp, 3))
        print()


def analyze_scenario(scenario: str, directory: Path) -> None:
    print(f"=== {scenario} step/control/state diagnostics ===")
    pfo_run = read_csv(directory / PFO / "run_log.csv")
    pstack_run = read_csv(directory / PSTACK / "run_log.csv")
    pfo_ctl = read_csv(directory / PFO / "control_timeseries.csv")
    pstack_ctl = read_csv(directory / PSTACK / "control_timeseries.csv")
    pfo_state = read_csv(directory / PFO / "state_timeseries.csv")
    pstack_state = read_csv(directory / PSTACK / "state_timeseries.csv")

    ramp_cols = [
        "ramp_metering_R_D_E",
        "ramp_metering_R_D_W",
        "ramp_metering_R_F_E",
        "ramp_metering_R_F_W",
    ]
    vsl_cols = [
        c for c in pstack_ctl[0] if c.startswith("vsl_FW") and "seg" not in c
    ]
    green_cols = [c for c in pstack_ctl[0] if c.startswith("green_")]
    offset_cols = [c for c in pstack_ctl[0] if c.startswith("offset_")]
    rampq_cols = [
        "ramp_queue_R_D_E",
        "ramp_queue_R_D_W",
        "ramp_queue_R_F_E",
        "ramp_queue_R_F_W",
    ]

    deltas = []
    for i in range(min(len(pfo_run), len(pstack_run))):
        deltas.append(
            {
                "total": val(pstack_run[i], "step_total_ttt")
                - val(pfo_run[i], "step_total_ttt"),
                "urban": val(pstack_run[i], "step_urban_ttt")
                - val(pfo_run[i], "step_urban_ttt"),
                "freeway": val(pstack_run[i], "step_freeway_ttt")
                - val(pfo_run[i], "step_freeway_ttt"),
            }
        )

    for key in ["total", "urban", "freeway"]:
        values = [x[key] for x in deltas]
        print(
            "step_delta",
            key,
            "sum",
            round(sum(values), 3),
            "mean",
            round(stats.mean(values), 3),
            "min",
            round(min(values), 3),
            "max",
            round(max(values), 3),
        )

    for start, end in [(0, 15), (15, 30), (30, 45), (45, 60)]:
        values = deltas[start:end]
        print(
            "window",
            start,
            "-",
            end,
            "min: total",
            round(sum(x["total"] for x in values), 2),
            "urban",
            round(sum(x["urban"] for x in values), 2),
            "freeway",
            round(sum(x["freeway"] for x in values), 2),
        )

    print(
        "mean RM command sum PFO/P-Stack",
        round(mean(pfo_ctl, lambda r: sum_cols(r, ramp_cols)), 1),
        round(mean(pstack_ctl, lambda r: sum_cols(r, ramp_cols)), 1),
    )
    print(
        "mean ramp queue sum PFO/P-Stack",
        round(mean(pfo_state, lambda r: sum_cols(r, rampq_cols)), 1),
        round(mean(pstack_state, lambda r: sum_cols(r, rampq_cols)), 1),
    )
    print(
        "mean FW density E/W PFO/P-Stack",
        round(mean(pfo_state, lambda r: val(r, "rho_FW_E_mean")), 2),
        round(mean(pfo_state, lambda r: val(r, "rho_FW_W_mean")), 2),
        "/",
        round(mean(pstack_state, lambda r: val(r, "rho_FW_E_mean")), 2),
        round(mean(pstack_state, lambda r: val(r, "rho_FW_W_mean")), 2),
    )
    print(
        "mean FW speed E/W PFO/P-Stack",
        round(mean(pfo_state, lambda r: val(r, "speed_FW_E_mean")), 2),
        round(mean(pfo_state, lambda r: val(r, "speed_FW_W_mean")), 2),
        "/",
        round(mean(pstack_state, lambda r: val(r, "speed_FW_E_mean")), 2),
        round(mean(pstack_state, lambda r: val(r, "speed_FW_W_mean")), 2),
    )
    print(
        "mean VSL E/W PFO/P-Stack",
        [round(mean(pfo_ctl, lambda r, c=c: val(r, c)), 1) for c in vsl_cols],
        "/",
        [round(mean(pstack_ctl, lambda r, c=c: val(r, c)), 1) for c in vsl_cols],
    )
    print(
        "mean green total PFO/P-Stack",
        round(mean(pfo_ctl, lambda r: sum_cols(r, green_cols)), 1),
        round(mean(pstack_ctl, lambda r: sum_cols(r, green_cols)), 1),
    )
    print(
        "mean abs offset total PFO/P-Stack",
        round(mean(pfo_ctl, lambda r: sum(abs(val(r, c)) for c in offset_cols)), 1),
        round(
            mean(pstack_ctl, lambda r: sum(abs(val(r, c)) for c in offset_cols)), 1
        ),
    )

    for key in [
        "leader_selected_N_P_star",
        "leader_selected_N_UF_star",
        "leader_mfd_storage_penalty",
        "leader_density_penalty",
        "leader_target_penalty",
        "leader_boundary_in_queue_penalty",
        "leader_follower_ttt_base",
        "leader_total_objective",
    ]:
        values = [val(r, key, math.nan) for r in pstack_run if r.get(key, "") != ""]
        if values:
            print(
                key,
                "mean",
                round(stats.mean(values), 3),
                "min",
                round(min(values), 3),
                "max",
                round(max(values), 3),
            )

    for key in [
        "leader_fallback_guard_selected",
        "leader_fallback_guard_selected_pfo",
        "leader_fallback_guard_selected_no_control",
        "leader_fallback_guard_rejected_leader",
        "leader_selected_stage_fallback_pfo",
        "leader_selected_stage_refined",
        "leader_selected_stage_coarse",
    ]:
        values = [val(r, key) for r in pstack_run]
        print(
            key,
            "count",
            int(sum(1 for v in values if abs(v) > 1e-9)),
            "sum",
            round(sum(values), 3),
        )
    print()


def main() -> None:
    print_summary()
    for scenario, directory in SCENARIOS.items():
        analyze_scenario(scenario, directory)


if __name__ == "__main__":
    main()
