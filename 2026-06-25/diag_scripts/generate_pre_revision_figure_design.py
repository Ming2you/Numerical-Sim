from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
STAGE1 = ROOT / "post_analysis" / "stage1"
OUT = ROOT / "reports" / "figures" / "pre_revision_claude_2026_06_25"


CONTROLLER_LABELS = {
    "WU-CD-F": "WU-CD-F",
    "WU-MATCHED-STACKELBERG": "WU-matched",
    "WU-CC-F": "WU-CC-F",
    "PROPOSED-FOLLOWERS-ONLY": "PFO",
    "PROPOSED-STACKELBERG": "P-Stack",
    "PROPOSED-CENTRALIZED": "Centralized",
}

CONTROLLER_COLORS = {
    "WU-CD-F": "#1F77B4",
    "WU-MATCHED-STACKELBERG": "#17BECF",
    "WU-CC-F": "#7F7F7F",
    "PROPOSED-FOLLOWERS-ONLY": "#2CA02C",
    "PROPOSED-STACKELBERG": "#D62728",
    "PROPOSED-CENTRALIZED": "#9467BD",
}

SCENARIOS = {
    "medium_demand": {
        "label": "Median",
        "folder": "medium_demand_s42",
        "seed": 42,
        "tags": ["median", "baseline"],
    },
    "peak_demand": {
        "label": "Peak",
        "folder": "peak_demand_s42",
        "seed": 42,
        "tags": ["peak", "spillback-risk"],
    },
    "incident_or_capacity_drop": {
        "label": "Incident",
        "folder": "incident_or_capacity_drop_s42",
        "seed": 42,
        "tags": ["incident", "capacity-drop-risk"],
    },
}

REUSED_SKEW_FIGURES = [
    ROOT / "reports" / "figures" / "fig03_skew_demand.png",
    ROOT / "reports" / "figures" / "fig15_skew_balance.png",
]


@dataclass
class RunFiles:
    scenario: str
    controller: str
    run_dir: Path
    run_log: Path
    control: Path
    decision: Path
    state: Path


def configure_style() -> None:
    mpl.rcParams["font.family"] = "Times New Roman"
    mpl.rcParams["mathtext.fontset"] = "stix"
    mpl.rcParams["axes.unicode_minus"] = False
    mpl.rcParams["font.size"] = 10
    mpl.rcParams["axes.labelsize"] = 10
    mpl.rcParams["axes.titlesize"] = 10
    mpl.rcParams["xtick.labelsize"] = 9
    mpl.rcParams["ytick.labelsize"] = 9
    mpl.rcParams["legend.fontsize"] = 8
    mpl.rcParams["figure.dpi"] = 160
    mpl.rcParams["savefig.dpi"] = 300
    mpl.rcParams["savefig.bbox"] = "tight"


def ensure_dirs() -> dict[str, Path]:
    dirs = {
        "root": OUT,
        "macro": OUT / "01_macro_performance",
        "transfer": OUT / "02_congestion_transfer",
        "leader": OUT / "03_leader_feasibility",
        "game": OUT / "04_game_coupling",
        "micro": OUT / "05_micro_controls",
        "compute": OUT / "06_computation_cost",
        "reused": OUT / "reused_skew_peak",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def savefig(fig: plt.Figure, path_no_ext: Path, manifest: list[dict]) -> None:
    png = path_no_ext.with_suffix(".png")
    pdf = path_no_ext.with_suffix(".pdf")
    fig.savefig(png)
    fig.savefig(pdf)
    plt.close(fig)
    manifest.append({"status": "generated", "png": str(png.relative_to(ROOT)), "pdf": str(pdf.relative_to(ROOT))})


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def scenario_dir(scenario: str) -> Path:
    return STAGE1 / SCENARIOS[scenario]["folder"]


def available_run_files() -> list[RunFiles]:
    files: list[RunFiles] = []
    for scen in SCENARIOS:
        runs_root = scenario_dir(scen) / "runs" / scen
        if not runs_root.exists():
            continue
        for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
            files.append(
                RunFiles(
                    scenario=scen,
                    controller=run_dir.name,
                    run_dir=run_dir,
                    run_log=run_dir / "run_log.csv",
                    control=run_dir / "control_timeseries.csv",
                    decision=run_dir / "decision_diagnostics.csv",
                    state=run_dir / "state_timeseries.csv",
                )
            )
    return files


def load_summary() -> pd.DataFrame:
    df = read_csv(STAGE1 / "matrix_all_controllers.csv")
    df = df[df["scenario"].isin(SCENARIOS)].copy()
    df = df[df["seed"].eq(42)].copy()
    order = list(CONTROLLER_LABELS)
    df["controller_label"] = df["controller_id"].map(CONTROLLER_LABELS).fillna(df["controller_id"])
    df["scenario_label"] = df["scenario"].map(lambda s: SCENARIOS[s]["label"])
    df["controller_order"] = df["controller_id"].map({c: i for i, c in enumerate(order)}).fillna(99)
    df["scenario_order"] = df["scenario"].map({s: i for i, s in enumerate(SCENARIOS)}).fillna(99)
    return df.sort_values(["scenario_order", "controller_order"])


def grouped_bar(
    df: pd.DataFrame,
    metrics: list[tuple[str, str]],
    title: str,
    path_no_ext: Path,
    manifest: list[dict],
) -> None:
    n = len(metrics)
    fig, axes = plt.subplots(1, n, figsize=(4.4 * n, 3.4), squeeze=False)
    scenarios = list(df["scenario"].drop_duplicates())
    controllers = [c for c in CONTROLLER_LABELS if c in set(df["controller_id"])]
    x = np.arange(len(scenarios))
    width = min(0.12, 0.75 / max(1, len(controllers)))
    offsets = (np.arange(len(controllers)) - (len(controllers) - 1) / 2) * width
    for ax, (metric, ylabel) in zip(axes[0], metrics):
        for i, ctrl in enumerate(controllers):
            sub = df[df["controller_id"].eq(ctrl)].set_index("scenario")
            values = [float(sub.loc[s, metric]) if s in sub.index and metric in sub else np.nan for s in scenarios]
            ax.bar(
                x + offsets[i],
                values,
                width=width,
                label=CONTROLLER_LABELS.get(ctrl, ctrl),
                color=CONTROLLER_COLORS.get(ctrl),
            )
        ax.set_xticks(x)
        ax.set_xticklabels([SCENARIOS[s]["label"] for s in scenarios], rotation=20, ha="right")
        ax.set_ylabel(ylabel)
        ax.set_title(metric.replace("_", " ").title())
        ax.grid(axis="y", alpha=0.25)
    axes[0, 0].legend(loc="best", frameon=False, ncol=2)
    fig.suptitle(title)
    fig.tight_layout()
    savefig(fig, path_no_ext, manifest)


def macro_figures(df: pd.DataFrame, dirs: dict[str, Path], manifest: list[dict]) -> None:
    grouped_bar(
        df,
        [("total_ttt", "Total TTT (veh-h)"), ("urban_ttt", "Urban TTT (veh-h)"), ("freeway_ttt", "Freeway TTT (veh-h)")],
        "Macro TTT Decomposition (pre-revision Claude runs)",
        dirs["macro"] / "fig01_macro_ttt_decomposition",
        manifest,
    )
    grouped_bar(
        df,
        [
            ("total_delay", "Total delay (veh-h)"),
            ("average_delay_per_completed_vehicle_h", "Avg delay / completed veh (h/veh)"),
            ("network_throughput_veh_h", "Throughput (veh/h)"),
        ],
        "Delay and Throughput",
        dirs["macro"] / "fig02_delay_att_throughput",
        manifest,
    )
    grouped_bar(
        df,
        [
            ("terminal_total_vehicles", "Terminal vehicles (veh)"),
            ("completed_vehicles", "Completed vehicles (veh)"),
            ("solver_evaluations", "Solver evaluations"),
        ],
        "Terminal Burden and Solver Evaluations",
        dirs["macro"] / "fig03_terminal_and_evaluations",
        manifest,
    )

    fig, ax = plt.subplots(figsize=(6.2, 4.8))
    for ctrl, sub in df.groupby("controller_id"):
        ax.scatter(
            sub["urban_ttt"],
            sub["freeway_ttt"],
            label=CONTROLLER_LABELS.get(ctrl, ctrl),
            color=CONTROLLER_COLORS.get(ctrl),
            s=50,
        )
        for _, r in sub.iterrows():
            ax.annotate(r["scenario_label"], (r["urban_ttt"], r["freeway_ttt"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("Urban TTT (veh-h)")
    ax.set_ylabel("Freeway TTT (veh-h)")
    ax.set_title("Urban-Freeway Burden Shift")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=7, ncol=2)
    savefig(fig, dirs["macro"] / "fig04_urban_freeway_burden_scatter", manifest)


def runlog_timeseries(run_files: list[RunFiles], dirs: dict[str, Path], manifest: list[dict]) -> None:
    for scen in SCENARIOS:
        fig, axes = plt.subplots(3, 1, figsize=(9, 7.5), sharex=True)
        plotted = False
        for rf in [r for r in run_files if r.scenario == scen]:
            log = read_csv(rf.run_log)
            if log.empty or "time_sec" not in log:
                continue
            t = log["time_sec"] / 60.0
            total_step = log.get("total_ttt", log.get("urban_ttt", 0) + log.get("freeway_ttt", 0))
            cumulative = pd.Series(total_step).cumsum()
            axes[0].plot(t, total_step, label=CONTROLLER_LABELS.get(rf.controller, rf.controller), color=CONTROLLER_COLORS.get(rf.controller))
            axes[1].plot(t, cumulative, label=CONTROLLER_LABELS.get(rf.controller, rf.controller), color=CONTROLLER_COLORS.get(rf.controller))
            if "urban_ttt" in log and "freeway_ttt" in log:
                axes[2].plot(t, log["urban_ttt"], color=CONTROLLER_COLORS.get(rf.controller), linestyle="-", alpha=0.9)
                axes[2].plot(t, log["freeway_ttt"], color=CONTROLLER_COLORS.get(rf.controller), linestyle="--", alpha=0.9)
            plotted = True
        if not plotted:
            plt.close(fig)
            manifest.append({"status": "skipped", "figure": f"time_series_{scen}", "reason": "missing run_log.csv"})
            continue
        axes[0].set_ylabel("Interval TTT")
        axes[1].set_ylabel("Cumulative TTT")
        axes[2].set_ylabel("Urban solid / Freeway dashed")
        axes[2].set_xlabel("Time (min)")
        for ax in axes:
            ax.grid(alpha=0.25)
        axes[0].legend(frameon=False, fontsize=7, ncol=3)
        fig.suptitle(f"{SCENARIOS[scen]['label']} TTT Time-Series")
        fig.tight_layout()
        savefig(fig, dirs["macro"] / f"fig05_{scen}_ttt_timeseries", manifest)


def queue_figures(run_files: list[RunFiles], dirs: dict[str, Path], manifest: list[dict]) -> None:
    queue_cols = [
        ("ramp_queue_veh", "Ramp queue (veh)"),
        ("onramp_approach_queue_veh", "On-ramp approach queue (veh)"),
        ("offramp_storage_occupancy_veh", "Off-ramp storage (veh)"),
        ("urban_total_vehicles_veh", "Urban vehicles (veh)"),
    ]
    summary_rows = []
    for rf in run_files:
        log = read_csv(rf.run_log)
        if log.empty:
            continue
        dt_h = infer_dt_hours(log)
        row = {
            "scenario": rf.scenario,
            "scenario_label": SCENARIOS[rf.scenario]["label"],
            "controller": rf.controller,
            "controller_label": CONTROLLER_LABELS.get(rf.controller, rf.controller),
        }
        if "B_in" in log and "B_out" in log:
            row["boundary_B_mean"] = float((log["B_in"] + log["B_out"]).mean())
        for col, _ in queue_cols:
            if col in log:
                row[col + "_exposure"] = float(log[col].sum() * dt_h)
        summary_rows.append(row)
    qdf = pd.DataFrame(summary_rows)
    metrics = [(c, c.replace("_", " ")) for c in qdf.columns if c.endswith("_exposure")]
    if "boundary_B_mean" in qdf.columns:
        metrics = [("boundary_B_mean", "Mean B_in + B_out")] + metrics[:2]
    if metrics:
        grouped_bar(qdf.rename(columns={"controller": "controller_id"}), metrics[:3], "Queue and Boundary Exposure", dirs["transfer"] / "fig01_queue_exposure_summary", manifest)
    else:
        manifest.append({"status": "skipped", "figure": "queue_exposure_summary", "reason": "no queue exposure columns"})

    for scen in SCENARIOS:
        fig, axes = plt.subplots(4, 1, figsize=(9, 8.5), sharex=True)
        plotted_any = False
        for rf in [r for r in run_files if r.scenario == scen and r.controller in ("WU-CD-F", "PROPOSED-FOLLOWERS-ONLY", "PROPOSED-STACKELBERG", "PROPOSED-CENTRALIZED")]:
            log = read_csv(rf.run_log)
            if log.empty or "time_sec" not in log:
                continue
            t = log["time_sec"] / 60.0
            line_label = CONTROLLER_LABELS.get(rf.controller, rf.controller)
            color = CONTROLLER_COLORS.get(rf.controller)
            for ax, (col, ylabel) in zip(axes, queue_cols):
                if col in log:
                    ax.plot(t, log[col], label=line_label, color=color)
                    ax.set_ylabel(ylabel)
                    plotted_any = True
        if not plotted_any:
            plt.close(fig)
            manifest.append({"status": "skipped", "figure": f"queue_timeseries_{scen}", "reason": "missing queue columns"})
            continue
        axes[-1].set_xlabel("Time (min)")
        for ax in axes:
            ax.grid(alpha=0.25)
        axes[0].legend(frameon=False, fontsize=7, ncol=2)
        fig.suptitle(f"{SCENARIOS[scen]['label']} Congestion Transfer Time-Series")
        fig.tight_layout()
        savefig(fig, dirs["transfer"] / f"fig02_{scen}_queue_timeseries", manifest)


def infer_dt_hours(df: pd.DataFrame) -> float:
    if "time_sec" in df and len(df) > 1:
        diffs = df["time_sec"].diff().dropna()
        if not diffs.empty:
            return float(diffs.median()) / 3600.0
    return 180.0 / 3600.0


def leader_figures(run_files: list[RunFiles], dirs: dict[str, Path], manifest: list[dict]) -> None:
    for scen in SCENARIOS:
        rf = next((r for r in run_files if r.scenario == scen and r.controller == "PROPOSED-STACKELBERG"), None)
        if rf is None:
            manifest.append({"status": "skipped", "figure": f"leader_{scen}", "reason": "missing P-Stack run"})
            continue
        ctrl = read_csv(rf.control)
        log = read_csv(rf.run_log)
        diag = read_csv(rf.decision)
        if ctrl.empty:
            manifest.append({"status": "skipped", "figure": f"leader_{scen}", "reason": "missing control_timeseries.csv"})
            continue
        t = (ctrl["time_sec"] if "time_sec" in ctrl else ctrl["step"] * 180.0) / 60.0
        fig, axes = plt.subplots(4, 1, figsize=(9, 8.5), sharex=True)
        if "N_P_star" in ctrl:
            axes[0].plot(t, ctrl["N_P_star"], label="$N_P^*$", color="#D62728")
        if not log.empty and "net_inflow" in log:
            axes[0].plot(log["time_sec"] / 60.0, log["net_inflow"], label="actual net inflow", color="#555555", linestyle="--")
        axes[0].set_ylabel("Net inflow target/actual")
        if "N_UF_star" in ctrl:
            axes[1].plot(t, ctrl["N_UF_star"], label="$N_{UF}^*$", color="#D62728")
        for col, label, style in [
            ("total_metering_flow", "actual metering flow", "--"),
            ("nuf_target_flow", "logged NUF target flow", ":"),
        ]:
            if not log.empty and col in log:
                axes[1].plot(log["time_sec"] / 60.0, log[col], label=label, color="#555555", linestyle=style)
        axes[1].set_ylabel("Metering target/actual")
        if not diag.empty and "leader_objective" in diag:
            axes[2].plot(t[: len(diag)], diag["leader_objective"], color="#D62728", label="leader objective")
        if not diag.empty and "leader_candidate_count" in diag:
            axes[3].plot(t[: len(diag)], diag["leader_candidate_count"], color="#D62728", label="leader candidates")
        if not diag.empty and "nash_iterations" in diag:
            axes[3].plot(t[: len(diag)], diag["nash_iterations"], color="#2CA02C", label="Nash iterations")
        axes[2].set_ylabel("Leader objective")
        axes[3].set_ylabel("Count")
        axes[3].set_xlabel("Time (min)")
        for ax in axes:
            ax.grid(alpha=0.25)
            ax.legend(frameon=False, fontsize=7)
        fig.suptitle(f"{SCENARIOS[scen]['label']} P-Stack Leader Targets")
        fig.tight_layout()
        savefig(fig, dirs["leader"] / f"fig01_{scen}_leader_targets", manifest)


def micro_control_figures(run_files: list[RunFiles], dirs: dict[str, Path], manifest: list[dict]) -> None:
    for scen in SCENARIOS:
        fig, axes = plt.subplots(4, 1, figsize=(9, 8.8), sharex=True)
        plotted = [False, False, False, False]
        selected = {"WU-CD-F", "PROPOSED-FOLLOWERS-ONLY", "PROPOSED-STACKELBERG", "PROPOSED-CENTRALIZED"}
        for rf in [r for r in run_files if r.scenario == scen and r.controller in selected]:
            ctrl = read_csv(rf.control)
            if ctrl.empty:
                continue
            t = (ctrl["time_sec"] if "time_sec" in ctrl else ctrl["step"] * 180.0) / 60.0
            label = CONTROLLER_LABELS.get(rf.controller, rf.controller)
            color = CONTROLLER_COLORS.get(rf.controller)
            ramp_cols = [c for c in ctrl.columns if c.startswith("ramp_metering_")]
            vsl_cols = [c for c in ctrl.columns if c.startswith("vsl_")]
            green_cols = [c for c in ctrl.columns if c.startswith("green_")]
            offset_cols = [c for c in ctrl.columns if c.startswith("offset_")]
            if ramp_cols:
                axes[0].plot(t, ctrl[ramp_cols].mean(axis=1), label=label, color=color)
                plotted[0] = True
            if vsl_cols:
                axes[1].plot(t, ctrl[vsl_cols].mean(axis=1), label=label, color=color)
                plotted[1] = True
            if green_cols:
                axes[2].plot(t, ctrl[green_cols].mean(axis=1), label=label, color=color)
                plotted[2] = True
            if offset_cols:
                axes[3].plot(t, ctrl[offset_cols].abs().mean(axis=1), label=label, color=color)
                plotted[3] = True
        if not any(plotted):
            plt.close(fig)
            manifest.append({"status": "skipped", "figure": f"micro_controls_{scen}", "reason": "missing control columns"})
            continue
        for ax, ylabel in zip(
            axes,
            ["Mean ramp metering (veh/h)", "Mean VSL (km/h)", "Mean green time (s)", "Mean |offset| (s)"],
        ):
            ax.set_ylabel(ylabel)
            ax.grid(alpha=0.25)
        axes[-1].set_xlabel("Time (min)")
        axes[0].legend(frameon=False, fontsize=7, ncol=2)
        fig.suptitle(f"{SCENARIOS[scen]['label']} Micro-Control Behavior")
        fig.tight_layout()
        savefig(fig, dirs["micro"] / f"fig01_{scen}_micro_controls", manifest)


def game_figures(run_files: list[RunFiles], dirs: dict[str, Path], manifest: list[dict]) -> None:
    rows = []
    for rf in run_files:
        diag = read_csv(rf.decision)
        if diag.empty:
            continue
        for col in ["nash_iterations", "nash_residual_objective", "nash_residual_control", "distributed_iterations"]:
            if col in diag:
                for v in diag[col].dropna():
                    rows.append(
                        {
                            "scenario": rf.scenario,
                            "scenario_label": SCENARIOS[rf.scenario]["label"],
                            "controller_id": rf.controller,
                            "controller_label": CONTROLLER_LABELS.get(rf.controller, rf.controller),
                            "metric": col,
                            "value": float(v),
                        }
                    )
    gdf = pd.DataFrame(rows)
    if gdf.empty:
        manifest.append({"status": "skipped", "figure": "game_coupling", "reason": "missing Nash diagnostics"})
        return
    metrics = [m for m in ["nash_iterations", "distributed_iterations", "nash_residual_objective"] if m in set(gdf["metric"])]
    fig, axes = plt.subplots(1, len(metrics), figsize=(4.4 * len(metrics), 3.5), squeeze=False)
    for ax, metric in zip(axes[0], metrics):
        sub = gdf[gdf["metric"].eq(metric)]
        labels = []
        values = []
        colors = []
        for ctrl in [c for c in CONTROLLER_LABELS if c in set(sub["controller_id"])]:
            vals = sub[sub["controller_id"].eq(ctrl)]["value"].astype(float)
            if vals.empty:
                continue
            labels.append(CONTROLLER_LABELS.get(ctrl, ctrl))
            values.append(vals.to_numpy())
            colors.append(CONTROLLER_COLORS.get(ctrl, "#333333"))
        bp = ax.boxplot(values, labels=labels, patch_artist=True, showfliers=False)
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.65)
        ax.set_title(metric.replace("_", " ").title())
        ax.tick_params(axis="x", rotation=30)
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Follower/Game Diagnostics")
    fig.tight_layout()
    savefig(fig, dirs["game"] / "fig01_nash_and_game_diagnostics", manifest)


def compute_figures(df: pd.DataFrame, dirs: dict[str, Path], manifest: list[dict]) -> None:
    grouped_bar(
        df,
        [("computation_time_sec", "Compute time (s)"), ("solver_evaluations", "Solver evaluations"), ("solver_converged_rate", "Convergence rate")],
        "Computation Cost",
        dirs["compute"] / "fig01_computation_cost_summary",
        manifest,
    )
    fig, ax = plt.subplots(figsize=(6.2, 4.5))
    for ctrl, sub in df.groupby("controller_id"):
        ax.scatter(
            sub["computation_time_sec"],
            sub["total_ttt"],
            label=CONTROLLER_LABELS.get(ctrl, ctrl),
            color=CONTROLLER_COLORS.get(ctrl),
            s=55,
        )
        for _, r in sub.iterrows():
            ax.annotate(r["scenario_label"], (r["computation_time_sec"], r["total_ttt"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("Computation time (s)")
    ax.set_ylabel("Total TTT (veh-h)")
    ax.set_title("Performance-Compute Trade-off")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=7, ncol=2)
    savefig(fig, dirs["compute"] / "fig02_performance_compute_tradeoff", manifest)


def reuse_skew_figures(dirs: dict[str, Path], manifest: list[dict]) -> None:
    for src in REUSED_SKEW_FIGURES:
        if not src.exists():
            manifest.append({"status": "skipped", "figure": src.name, "reason": "source skew figure missing"})
            continue
        dst = dirs["reused"] / src.name
        shutil.copy2(src, dst)
        manifest.append(
            {
                "status": "reused",
                "source": str(src.relative_to(ROOT)),
                "target": str(dst.relative_to(ROOT)),
                "reason": "peak_skew raw run CSV not found; copied existing post-analysis figure",
            }
        )


def write_manifest(manifest: list[dict], df: pd.DataFrame, run_files: list[RunFiles]) -> None:
    summary = {
        "source_roots": [
            "post_analysis/stage1/medium_demand_s42",
            "post_analysis/stage1/peak_demand_s42",
            "post_analysis/stage1/incident_or_capacity_drop_s42",
            "reports/figures/fig03_skew_demand.png",
            "reports/figures/fig15_skew_balance.png",
        ],
        "scenarios_generated_from_csv": list(SCENARIOS),
        "scenario_aliases": {
            "median": "medium_demand",
            "peak": "peak_demand",
            "incident": "incident_or_capacity_drop",
            "peak_skew": "reused existing skew figures only; raw run CSV not found",
        },
        "controllers": sorted(df["controller_id"].unique().tolist()),
        "run_file_count": len(run_files),
        "figures": manifest,
    }
    (OUT / "manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    configure_style()
    dirs = ensure_dirs()
    manifest: list[dict] = []
    summary = load_summary()
    run_files = available_run_files()
    macro_figures(summary, dirs, manifest)
    runlog_timeseries(run_files, dirs, manifest)
    queue_figures(run_files, dirs, manifest)
    leader_figures(run_files, dirs, manifest)
    game_figures(run_files, dirs, manifest)
    micro_control_figures(run_files, dirs, manifest)
    compute_figures(summary, dirs, manifest)
    reuse_skew_figures(dirs, manifest)
    write_manifest(manifest, summary, run_files)
    print(f"generated_manifest={OUT / 'manifest.json'}")
    print(f"generated_count={sum(1 for x in manifest if x['status'] == 'generated')}")
    print(f"reused_count={sum(1 for x in manifest if x['status'] == 'reused')}")
    print(f"skipped_count={sum(1 for x in manifest if x['status'] == 'skipped')}")


if __name__ == "__main__":
    main()
