from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


ROOT = Path(__file__).resolve().parents[2]
DESKTOP_ROOT = Path(r"C:\Users\alsrj\Desktop\Numerical-Sim")
D1 = DESKTOP_ROOT / "outputs" / "analysis_matrix_3600"
D2 = DESKTOP_ROOT / "outputs" / "analysis_matrix_3600_extra"
OUT = ROOT / "reports" / "figures" / "figure_design_2026_06_23_redraw"

SCENARIOS = [
    {"id": "medium_demand", "label": "Median", "root": D1, "tags": ["medium", "baseline"]},
    {"id": "peak_demand", "label": "Peak", "root": D1, "tags": ["peak", "spillback-risk"]},
    {"id": "skew_peak", "label": "Peak skew", "root": D2, "tags": ["peak", "spatial-skew"]},
    {
        "id": "incident_or_capacity_drop",
        "label": "Incident",
        "root": D1,
        "tags": ["incident", "capacity-drop-risk"],
    },
]

CONTROLLERS = [
    "NO-CONTROL",
    "WU-CD-F",
    "PROPOSED-FOLLOWERS-ONLY",
    "PROPOSED-STACKELBERG",
]

CTRL_LABEL = {
    "NO-CONTROL": "No control",
    "WU-CD-F": "WU-CD-F",
    "PROPOSED-FOLLOWERS-ONLY": "PFO",
    "PROPOSED-STACKELBERG": "P-Stack",
}

CTRL_SHORT = {
    "NO-CONTROL": "NC",
    "WU-CD-F": "WU",
    "PROPOSED-FOLLOWERS-ONLY": "PFO",
    "PROPOSED-STACKELBERG": "P-Stack",
}

CTRL_COLOR = {
    "NO-CONTROL": "#4D4D4D",
    "WU-CD-F": "#1F77B4",
    "PROPOSED-FOLLOWERS-ONLY": "#2CA02C",
    "PROPOSED-STACKELBERG": "#D62728",
}

SCENARIO_LABEL = {s["id"]: s["label"] for s in SCENARIOS}
SCENARIO_ROOT = {s["id"]: s["root"] for s in SCENARIOS}
SCENARIO_MARKER = {
    "medium_demand": "o",
    "peak_demand": "s",
    "skew_peak": "^",
    "incident_or_capacity_drop": "D",
}


def setup_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "Times New Roman",
            "mathtext.fontset": "stix",
            "axes.unicode_minus": False,
            "font.size": 10,
            "axes.labelsize": 10,
            "axes.titlesize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "figure.dpi": 300,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "axes.axisbelow": True,
        }
    )


def ensure_dirs() -> dict[str, Path]:
    dirs = {
        "macro": OUT / "01_macro_performance",
        "transfer": OUT / "02_congestion_transfer",
        "leader": OUT / "03_leader_feasibility",
        "coupling": OUT / "04_game_coupling",
        "micro": OUT / "05_micro_controls",
        "micro_rm": OUT / "05_micro_controls" / "ramp_metering",
        "micro_vsl": OUT / "05_micro_controls" / "vsl",
        "micro_green": OUT / "05_micro_controls" / "green_time",
        "micro_offset": OUT / "05_micro_controls" / "offset",
        "compute": OUT / "06_computation_cost",
        "tables": OUT / "tables",
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    for col in df.columns:
        if col not in ("scenario", "controller_id", "authority_group", "authority_violations"):
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().any():
                df[col] = converted
    return df


def run_dir(scenario: str, controller: str) -> Path:
    return SCENARIO_ROOT[scenario] / "runs" / scenario / controller


def load_summary() -> pd.DataFrame:
    frames = []
    for root in sorted({D1, D2}):
        f = root / "analysis" / "summary_with_no_control.csv"
        if f.exists():
            frames.append(read_csv(f))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df[df["scenario"].isin(SCENARIO_LABEL) & df["controller_id"].isin(CONTROLLERS)].copy()
    df["scenario_label"] = df["scenario"].map(SCENARIO_LABEL)
    df["controller_label"] = df["controller_id"].map(CTRL_LABEL)
    df["controller_short"] = df["controller_id"].map(CTRL_SHORT)
    df["att_h_per_completed"] = df["total_ttt"] / df["completed_vehicles"].replace(0, np.nan)
    df["att_sec_per_completed"] = 3600.0 * df["att_h_per_completed"]
    return df


def load_file(name: str) -> pd.DataFrame:
    frames = []
    for s in SCENARIO_LABEL:
        for c in CONTROLLERS:
            p = run_dir(s, c) / name
            df = read_csv(p)
            if df.empty:
                continue
            df["scenario"] = s
            df["scenario_label"] = SCENARIO_LABEL[s]
            df["controller_id"] = c
            df["controller_label"] = CTRL_LABEL[c]
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def save(fig: plt.Figure, rel: Path, manifest: list[dict[str, str]]) -> None:
    png = rel.with_suffix(".png")
    pdf = rel.with_suffix(".pdf")
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png)
    fig.savefig(pdf)
    plt.close(fig)
    manifest.append(
        {
            "status": "generated",
            "png": str(png.relative_to(ROOT)),
            "pdf": str(pdf.relative_to(ROOT)),
        }
    )


def add_top_legend(fig: plt.Figure, axes, ncol: int = 4, y: float = 1.06) -> None:
    ax0 = np.ravel(axes)[0]
    handles, labels = ax0.get_legend_handles_labels()
    if handles:
        fig.legend(
            handles,
            labels,
            ncol=ncol,
            loc="upper center",
            bbox_to_anchor=(0.5, y),
            frameon=True,
        )


def first_existing(df: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def sum_columns(df: pd.DataFrame, prefixes: tuple[str, ...], contains: str | None = None) -> pd.Series:
    cols = [
        c
        for c in df.columns
        if c.startswith(prefixes) and (contains is None or contains in c)
    ]
    if not cols:
        return pd.Series(np.zeros(len(df)), index=df.index)
    return df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)


def grouped_bars(
    df: pd.DataFrame,
    metric: str,
    ylabel: str,
    title: str,
    path: Path,
    manifest: list[dict[str, str]],
    annotate_improvement: bool = False,
) -> None:
    scenarios = [s["id"] for s in SCENARIOS if s["id"] in set(df["scenario"])]
    x = np.arange(len(scenarios))
    width = 0.78 / max(len(CONTROLLERS), 1)
    fig, ax = plt.subplots(figsize=(8.6, 3.8))
    for i, ctrl in enumerate(CONTROLLERS):
        vals = []
        for s in scenarios:
            row = df[(df["scenario"] == s) & (df["controller_id"] == ctrl)]
            vals.append(float(row[metric].iloc[0]) if not row.empty and metric in row else np.nan)
        offset = (i - (len(CONTROLLERS) - 1) / 2) * width
        bars = ax.bar(
            x + offset,
            vals,
            width,
            label=CTRL_LABEL[ctrl],
            color=CTRL_COLOR[ctrl],
            edgecolor="white",
            linewidth=0.5,
        )
        if annotate_improvement and ctrl != "NO-CONTROL":
            for j, bar in enumerate(bars):
                s = scenarios[j]
                row = df[(df["scenario"] == s) & (df["controller_id"] == ctrl)]
                if row.empty or "total_ttt_improvement_vs_no_control_pct" not in row:
                    continue
                pct = row["total_ttt_improvement_vs_no_control_pct"].iloc[0]
                if pd.notna(pct):
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height(),
                        f"{pct:.0f}%",
                        ha="center",
                        va="bottom",
                        fontsize=7,
                        rotation=90,
                    )
    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABEL[s] for s in scenarios], rotation=20, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.18), frameon=True)
    save(fig, path, manifest)


def macro_figures(summary: pd.DataFrame, progress: pd.DataFrame, dirs: dict[str, Path], manifest: list[dict[str, str]]) -> None:
    grouped_bars(
        summary,
        "total_ttt",
        "Total TTT (veh-h)",
        "Fig. 1A. Total TTT Across Focus Scenarios",
        dirs["macro"] / "Fig1A_total_ttt_cross_scenario",
        manifest,
        annotate_improvement=True,
    )

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.8), sharex=True)
    for ax, metric, title in zip(
        axes,
        ["urban_ttt", "freeway_ttt"],
        ["Urban TTT", "Freeway TTT"],
    ):
        scenarios = [s["id"] for s in SCENARIOS]
        x = np.arange(len(scenarios))
        width = 0.78 / len(CONTROLLERS)
        for i, ctrl in enumerate(CONTROLLERS):
            vals = [
                summary.loc[
                    (summary["scenario"] == s) & (summary["controller_id"] == ctrl),
                    metric,
                ].squeeze()
                if not summary.loc[
                    (summary["scenario"] == s) & (summary["controller_id"] == ctrl)
                ].empty
                else np.nan
                for s in scenarios
            ]
            ax.bar(
                x + (i - 1.5) * width,
                vals,
                width,
                label=CTRL_LABEL[ctrl],
                color=CTRL_COLOR[ctrl],
                edgecolor="white",
                linewidth=0.5,
            )
        ax.set_title(title)
        ax.set_ylabel("TTT (veh-h)")
        ax.set_xticks(x)
        ax.set_xticklabels([SCENARIO_LABEL[s] for s in scenarios], rotation=20, ha="right")
    add_top_legend(fig, axes, ncol=4, y=1.06)
    fig.subplots_adjust(top=0.82)
    fig.suptitle("Fig. 1B. Urban-Freeway TTT Burden Decomposition")
    save(fig, dirs["macro"] / "Fig1B_urban_freeway_ttt_decomposition", manifest)

    fig, axes = plt.subplots(1, 3, figsize=(12.2, 3.8))
    panels = [
        ("total_delay", "Total delay (veh-h)", "Total delay"),
        ("att_sec_per_completed", "TTT/completed (s/veh)", "Average travel-time proxy"),
        ("completed_vehicles", "Completed vehicles", "Throughput"),
    ]
    for ax, (metric, ylabel, title) in zip(axes, panels):
        scenarios = [s["id"] for s in SCENARIOS]
        x = np.arange(len(scenarios))
        width = 0.78 / len(CONTROLLERS)
        for i, ctrl in enumerate(CONTROLLERS):
            vals = [
                summary.loc[
                    (summary["scenario"] == s) & (summary["controller_id"] == ctrl),
                    metric,
                ].squeeze()
                if not summary.loc[
                    (summary["scenario"] == s) & (summary["controller_id"] == ctrl)
                ].empty
                else np.nan
                for s in scenarios
            ]
            ax.bar(x + (i - 1.5) * width, vals, width, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks(x)
        ax.set_xticklabels([SCENARIO_LABEL[s] for s in scenarios], rotation=25, ha="right")
    add_top_legend(fig, axes, ncol=4, y=1.06)
    fig.subplots_adjust(top=0.82)
    fig.suptitle("Fig. 1C. Delay, Travel-Time Proxy, and Throughput")
    save(fig, dirs["macro"] / "Fig1C_delay_att_throughput", manifest)

    fig, axes = plt.subplots(1, 3, figsize=(12.2, 3.8))
    panels = [
        ("terminal_total_vehicles", "Terminal total veh."),
        ("terminal_urban_vehicles", "Terminal urban veh."),
        ("terminal_onramp_vehicles", "Terminal on-ramp veh."),
    ]
    for ax, (metric, ylabel) in zip(axes, panels):
        scenarios = [s["id"] for s in SCENARIOS]
        x = np.arange(len(scenarios))
        width = 0.78 / len(CONTROLLERS)
        for i, ctrl in enumerate(CONTROLLERS):
            vals = [
                summary.loc[
                    (summary["scenario"] == s) & (summary["controller_id"] == ctrl),
                    metric,
                ].squeeze()
                if not summary.loc[
                    (summary["scenario"] == s) & (summary["controller_id"] == ctrl)
                ].empty
                else np.nan
                for s in scenarios
            ]
            ax.bar(x + (i - 1.5) * width, vals, width, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        ax.set_ylabel(ylabel)
        ax.set_xticks(x)
        ax.set_xticklabels([SCENARIO_LABEL[s] for s in scenarios], rotation=25, ha="right")
    add_top_legend(fig, axes, ncol=4, y=1.06)
    fig.subplots_adjust(top=0.84)
    fig.suptitle("Fig. 1D. Terminal-State Burden")
    save(fig, dirs["macro"] / "Fig1D_terminal_state_burden", manifest)

    for scenario in [s["id"] for s in SCENARIOS]:
        sub = progress[progress["scenario"] == scenario]
        if sub.empty or "step_total_ttt" not in sub:
            continue
        fig, axes = plt.subplots(3, 1, figsize=(8.4, 7.2), sharex=True)
        for ctrl in CONTROLLERS:
            cdf = sub[sub["controller_id"] == ctrl].sort_values("time_sec")
            if cdf.empty:
                continue
            t = cdf["time_sec"] / 60.0
            axes[0].plot(t, cdf["step_total_ttt"], label=CTRL_LABEL[ctrl], color=CTRL_COLOR[ctrl])
            axes[1].plot(t, cdf["cumulative_total_ttt"], label=CTRL_LABEL[ctrl], color=CTRL_COLOR[ctrl])
            axes[2].plot(t, cdf["terminal_total_vehicles"], label=CTRL_LABEL[ctrl], color=CTRL_COLOR[ctrl])
        axes[0].set_ylabel("Step TTT (veh-h)")
        axes[1].set_ylabel("Cumulative TTT (veh-h)")
        axes[2].set_ylabel("Terminal vehicles")
        axes[2].set_xlabel("Time (min)")
        add_top_legend(fig, axes, ncol=4, y=1.04)
        fig.subplots_adjust(top=0.90)
        fig.suptitle(f"Fig. 2. Scenario Time-Series Package: {SCENARIO_LABEL[scenario]}")
        save(fig, dirs["macro"] / f"Fig2_timeseries_{scenario}", manifest)


def exposure_table(runlog: pd.DataFrame) -> pd.DataFrame:
    if runlog.empty:
        return pd.DataFrame()
    rows = []
    dt_h = 180.0 / 3600.0
    for (scenario, ctrl), df in runlog.groupby(["scenario", "controller_id"]):
        boundary_col = first_existing(
            df,
            [
                "leader_boundary_in_queue_veh",
                "boundary_in_load_veh",
                "urban_accumulation_veh",
            ],
        )
        rows.append(
            {
                "scenario": scenario,
                "scenario_label": SCENARIO_LABEL[scenario],
                "controller_id": ctrl,
                "controller_label": CTRL_LABEL[ctrl],
                "ramp_queue_exposure": df.get("ramp_queue_veh", pd.Series(0, index=df.index)).sum() * dt_h,
                "onramp_approach_exposure": df.get("onramp_approach_queue_veh", pd.Series(0, index=df.index)).sum()
                * dt_h,
                "offramp_storage_exposure": df.get("offramp_storage_occupancy_veh", pd.Series(0, index=df.index)).sum()
                * dt_h,
                "boundary_queue_exposure": df.get(boundary_col, pd.Series(0, index=df.index)).sum() * dt_h
                if boundary_col
                else 0.0,
                "ramp_spillback_steps": df.get("ramp_queue_overflow_count", pd.Series(0, index=df.index)).gt(0).sum(),
                "offramp_binding_steps": df.get("offramp_storage_binding", pd.Series(0, index=df.index)).gt(0).sum(),
                "boundary_overflow_steps": df.get("queue_overflow_count", pd.Series(0, index=df.index)).gt(0).sum(),
            }
        )
    return pd.DataFrame(rows)


def congestion_figures(runlog: pd.DataFrame, dirs: dict[str, Path], manifest: list[dict[str, str]]) -> pd.DataFrame:
    exp = exposure_table(runlog)
    if exp.empty:
        return exp
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.8))
    panels = [
        ("ramp_spillback_steps", "Ramp overflow steps"),
        ("offramp_binding_steps", "Off-ramp binding steps"),
        ("boundary_overflow_steps", "Boundary overflow steps"),
    ]
    for ax, (metric, ylabel) in zip(axes, panels):
        scenarios = [s["id"] for s in SCENARIOS]
        x = np.arange(len(scenarios))
        width = 0.78 / len(CONTROLLERS)
        for i, ctrl in enumerate(CONTROLLERS):
            vals = [
                exp.loc[(exp["scenario"] == s) & (exp["controller_id"] == ctrl), metric].squeeze()
                if not exp.loc[(exp["scenario"] == s) & (exp["controller_id"] == ctrl)].empty
                else np.nan
                for s in scenarios
            ]
            ax.bar(x + (i - 1.5) * width, vals, width, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        ax.set_ylabel(ylabel)
        ax.set_xticks(x)
        ax.set_xticklabels([SCENARIO_LABEL[s] for s in scenarios], rotation=25, ha="right")
    add_top_legend(fig, axes, ncol=4, y=1.06)
    fig.subplots_adjust(top=0.84)
    fig.suptitle("Fig. 2A. Spillback and Binding Summary")
    save(fig, dirs["transfer"] / "Fig2A_spillback_summary", manifest)

    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.8))
    panels = [
        ("ramp_queue_exposure", "Ramp queue exposure (veh-h)"),
        ("offramp_storage_exposure", "Off-ramp storage exposure (veh-h)"),
        ("boundary_queue_exposure", "Boundary load/queue exposure (veh-h)"),
    ]
    for ax, (metric, ylabel) in zip(axes, panels):
        scenarios = [s["id"] for s in SCENARIOS]
        x = np.arange(len(scenarios))
        width = 0.78 / len(CONTROLLERS)
        for i, ctrl in enumerate(CONTROLLERS):
            vals = [
                exp.loc[(exp["scenario"] == s) & (exp["controller_id"] == ctrl), metric].squeeze()
                if not exp.loc[(exp["scenario"] == s) & (exp["controller_id"] == ctrl)].empty
                else np.nan
                for s in scenarios
            ]
            ax.bar(x + (i - 1.5) * width, vals, width, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        ax.set_ylabel(ylabel)
        ax.set_xticks(x)
        ax.set_xticklabels([SCENARIO_LABEL[s] for s in scenarios], rotation=25, ha="right")
    add_top_legend(fig, axes, ncol=4, y=1.06)
    fig.subplots_adjust(top=0.84)
    fig.suptitle("Fig. 2B. Queue Exposure Summary")
    save(fig, dirs["transfer"] / "Fig2B_queue_exposure_summary", manifest)

    if "offramp_departures_veh" in runlog and "offramp_flow_total" in runlog:
        ratio_rows = []
        dt_h = 180.0 / 3600.0
        for (scenario, ctrl), df in runlog.groupby(["scenario", "controller_id"]):
            desired = df["offramp_flow_total"].sum() * dt_h
            accepted = df["offramp_departures_veh"].sum()
            ratio_rows.append(
                {
                    "scenario": scenario,
                    "controller_id": ctrl,
                    "accepted_ratio": accepted / desired if desired > 1e-9 else np.nan,
                }
            )
        ar = pd.DataFrame(ratio_rows)
        grouped_bars(
            ar,
            "accepted_ratio",
            "Accepted / desired off-ramp flow",
            "Fig. 2C. Off-Ramp Acceptance Ratio",
            dirs["transfer"] / "Fig2C_offramp_acceptance_ratio",
            manifest,
        )

    for scenario in ["peak_demand", "incident_or_capacity_drop"]:
        sub = runlog[runlog["scenario"] == scenario]
        if sub.empty:
            continue
        fig, axes = plt.subplots(4, 1, figsize=(8.6, 7.8), sharex=True)
        for ctrl in ["NO-CONTROL", "WU-CD-F", "PROPOSED-FOLLOWERS-ONLY", "PROPOSED-STACKELBERG"]:
            cdf = sub[sub["controller_id"] == ctrl].sort_values("time_sec")
            if cdf.empty:
                continue
            t = cdf["time_sec"] / 60.0
            axes[0].plot(t, cdf.get("ramp_queue_veh", 0), label=CTRL_LABEL[ctrl], color=CTRL_COLOR[ctrl])
            axes[1].plot(t, cdf.get("total_metering_flow", 0), label=CTRL_LABEL[ctrl], color=CTRL_COLOR[ctrl])
            axes[2].plot(t, cdf.get("onramp_approach_queue_veh", 0), label=CTRL_LABEL[ctrl], color=CTRL_COLOR[ctrl])
            axes[3].plot(t, cdf.get("ramp_metering_releases_veh", 0), label=CTRL_LABEL[ctrl], color=CTRL_COLOR[ctrl])
        axes[0].set_ylabel("Ramp queue (veh)")
        axes[1].set_ylabel("Metering flow (veh/h)")
        axes[2].set_ylabel("Urban on-ramp queue (veh)")
        axes[3].set_ylabel("Ramp releases (veh)")
        axes[3].set_xlabel("Time (min)")
        add_top_legend(fig, axes, ncol=4, y=1.04)
        fig.subplots_adjust(top=0.90)
        fig.suptitle(f"Fig. 2D. On-Ramp Mechanism: {SCENARIO_LABEL[scenario]}")
        save(fig, dirs["transfer"] / f"Fig2D_onramp_mechanism_{scenario}", manifest)

    return exp


def leader_figures(progress: pd.DataFrame, runlog: pd.DataFrame, diag: pd.DataFrame, dirs: dict[str, Path], manifest: list[dict[str, str]]) -> None:
    pstack = progress[progress["controller_id"] == "PROPOSED-STACKELBERG"]
    rstack = runlog[runlog["controller_id"] == "PROPOSED-STACKELBERG"]
    if pstack.empty:
        return
    for scenario in [s["id"] for s in SCENARIOS]:
        ps = pstack[pstack["scenario"] == scenario].sort_values("time_sec")
        rs = rstack[rstack["scenario"] == scenario].sort_values("time_sec")
        if ps.empty:
            continue
        fig, axes = plt.subplots(4, 1, figsize=(8.6, 8.2), sharex=True)
        t = ps["time_sec"] / 60.0
        axes[0].plot(t, ps["N_P_star"], color="#D62728", label=r"$N_P^\ast$")
        if not rs.empty and "net_inflow" in rs:
            axes[0].plot(rs["time_sec"] / 60.0, rs["net_inflow"], color="0.35", linestyle="--", label="actual net inflow")
        axes[0].set_ylabel("Net inflow target/actual")
        axes[0].legend(frameon=True)

        axes[1].plot(t, ps["N_UF_star"], color="#D62728", label=r"$N_{UF}^\ast$")
        if not rs.empty and "total_metering_flow" in rs:
            axes[1].plot(rs["time_sec"] / 60.0, rs["total_metering_flow"], color="0.35", linestyle="--", label="actual metering flow")
        axes[1].set_ylabel("Metering target/actual")
        axes[1].legend(frameon=True)

        y_obj = "leader_selected_objective" if "leader_selected_objective" in ps else "leader_objective"
        if y_obj in ps:
            axes[2].plot(t, ps[y_obj], color="#D62728")
        axes[2].set_ylabel("Leader objective")

        fallback = ps.get("leader_fallback_guard_selected", pd.Series(0, index=ps.index))
        axes[3].step(t, fallback, where="post", color="#D62728")
        axes[3].set_ylabel("Fallback selected")
        axes[3].set_xlabel("Time (min)")
        axes[3].set_ylim(-0.05, 1.05)
        fig.suptitle(f"Fig. 3A. Leader Targets and Realized Response: {SCENARIO_LABEL[scenario]}")
        save(fig, dirs["leader"] / f"Fig3A_leader_targets_response_{scenario}", manifest)

    rows = []
    for scenario in [s["id"] for s in SCENARIOS]:
        ps = pstack[pstack["scenario"] == scenario]
        rs = rstack[rstack["scenario"] == scenario]
        if ps.empty:
            continue
        merged = pd.merge(
            ps[["step", "N_P_star", "N_UF_star", "leader_fallback_guard_selected"]],
            rs[["step", "net_inflow", "total_metering_flow"]] if {"step", "net_inflow", "total_metering_flow"} <= set(rs.columns) else pd.DataFrame(),
            on="step",
            how="left",
        )
        rows.append(
            {
                "scenario": scenario,
                "controller_id": "PROPOSED-STACKELBERG",
                "net_inflow_tracking_error": (merged["N_P_star"] - merged.get("net_inflow", np.nan)).abs().mean(),
                "metering_tracking_error": (merged["N_UF_star"] - merged.get("total_metering_flow", np.nan)).abs().mean(),
                "fallback_rate": merged["leader_fallback_guard_selected"].mean(),
            }
        )
    lsum = pd.DataFrame(rows)
    if not lsum.empty:
        fig, axes = plt.subplots(1, 3, figsize=(11.6, 3.6))
        for ax, metric, ylabel in zip(
            axes,
            ["net_inflow_tracking_error", "metering_tracking_error", "fallback_rate"],
            ["Mean abs. net inflow error", "Mean abs. metering error", "Fallback rate"],
        ):
            ax.bar(
                [SCENARIO_LABEL[s] for s in lsum["scenario"]],
                lsum[metric],
                color="#D62728",
                edgecolor="white",
            )
            ax.set_ylabel(ylabel)
            ax.tick_params(axis="x", rotation=25)
        fig.suptitle("Fig. 3C-D. P-Stack Fallback and Tracking Error")
        save(fig, dirs["leader"] / "Fig3CD_fallback_tracking_error", manifest)

    dstack = diag[diag["controller_id"] == "PROPOSED-STACKELBERG"]
    cols_needed = {"leader_candidate_best_N_P_star", "leader_candidate_best_N_UF_star", "leader_candidate_best_objective"}
    if cols_needed <= set(dstack.columns):
        fig, axes = plt.subplots(1, len(SCENARIOS), figsize=(3.4 * len(SCENARIOS), 3.5), sharex=False, sharey=False)
        if len(SCENARIOS) == 1:
            axes = [axes]
        for ax, s in zip(axes, [x["id"] for x in SCENARIOS]):
            sdf = dstack[dstack["scenario"] == s]
            if sdf.empty:
                ax.set_axis_off()
                continue
            sc = ax.scatter(
                sdf["leader_candidate_best_N_P_star"],
                sdf["leader_candidate_best_N_UF_star"],
                c=sdf["leader_candidate_best_objective"],
                cmap="viridis_r",
                s=28,
            )
            ax.set_title(SCENARIO_LABEL[s])
            ax.set_xlabel(r"Best $N_P^\ast$")
            ax.set_ylabel(r"Best $N_{UF}^\ast$")
        fig.colorbar(sc, ax=axes, shrink=0.8, label="best objective")
        fig.suptitle("Fig. 3B. Logged Best Leader Candidate Locations")
        save(fig, dirs["leader"] / "Fig3B_logged_best_candidate_locations", manifest)
    else:
        manifest.append({"status": "skipped", "figure": "Fig3B", "reason": "leader candidate columns unavailable"})


def coupling_figures(progress: pd.DataFrame, runlog: pd.DataFrame, diag: pd.DataFrame, dirs: dict[str, Path], manifest: list[dict[str, str]]) -> None:
    if "nash_iterations" in runlog:
        fig, axes = plt.subplots(1, 3, figsize=(11.8, 3.6))
        metrics = [
            ("nash_iterations", "Nash iterations"),
            ("nash_residual_objective", "Objective residual"),
            ("nash_residual_control", "Control residual"),
        ]
        for ax, (metric, ylabel) in zip(axes, metrics):
            if metric not in runlog:
                ax.set_axis_off()
                continue
            data = [
                runlog.loc[runlog["controller_id"] == c, metric].dropna().values
                for c in CONTROLLERS
                if c != "NO-CONTROL"
            ]
            labels = [CTRL_SHORT[c] for c in CONTROLLERS if c != "NO-CONTROL"]
            ax.boxplot(data, showfliers=False)
            ax.set_xticklabels(labels)
            ax.set_ylabel(ylabel)
        fig.suptitle("Fig. 4A. Follower Nash/Response Diagnostics")
        save(fig, dirs["coupling"] / "Fig4A_nash_response_diagnostics", manifest)

    records = []
    for (scenario, ctrl), df in runlog.groupby(["scenario", "controller_id"]):
        if ctrl == "NO-CONTROL":
            continue
        candidates = {
            "RM": "total_metering_flow",
            "Green service": "inbound_service_veh",
            "Offset proxy": "urban_total_departures_veh",
            "VSL proxy": "mean_segment_flow",
        }
        responses = {
            "Ramp queue": "ramp_queue_veh",
            "Urban queue": "onramp_approach_queue_veh",
            "Freeway TTT": "freeway_ttt",
            "Urban TTT": "urban_ttt",
            "Off-ramp storage": "offramp_storage_occupancy_veh",
        }
        for action, acol in candidates.items():
            if acol not in df:
                continue
            for resp, rcol in responses.items():
                if rcol not in df:
                    continue
                a = pd.to_numeric(df[acol], errors="coerce")
                b = pd.to_numeric(df[rcol], errors="coerce")
                if a.std(skipna=True) <= 1e-9 or b.std(skipna=True) <= 1e-9:
                    val = 0.0
                else:
                    val = float(a.corr(b))
                records.append({"controller_id": ctrl, "action": action, "response": resp, "corr": val})
    cmat = pd.DataFrame(records)
    if not cmat.empty:
        pivot = cmat.groupby(["action", "response"])["corr"].mean().unstack().fillna(0.0)
        fig, ax = plt.subplots(figsize=(7.2, 4.0))
        im = ax.imshow(pivot.values, cmap="coolwarm", vmin=-1.0, vmax=1.0)
        ax.set_xticks(np.arange(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns, rotation=30, ha="right")
        ax.set_yticks(np.arange(len(pivot.index)))
        ax.set_yticklabels(pivot.index)
        for i in range(pivot.shape[0]):
            for j in range(pivot.shape[1]):
                ax.text(j, i, f"{pivot.values[i, j]:.2f}", ha="center", va="center", fontsize=8)
        fig.colorbar(im, ax=ax, label="mean correlation")
        ax.set_title("Fig. 4B. Normalized Coupling Response Matrix")
        save(fig, dirs["coupling"] / "Fig4B_coupling_response_matrix", manifest)

    rows = []
    pstack = progress[progress["controller_id"] == "PROPOSED-STACKELBERG"]
    for scenario, df in pstack.groupby("scenario"):
        sdf = df.sort_values("step")
        if "leader_selected_objective" not in sdf:
            continue
        realized = sdf["step_total_ttt"].shift(-1)
        pred = sdf["leader_selected_objective"]
        for p, r in zip(pred, realized):
            if pd.notna(p) and pd.notna(r):
                rows.append({"scenario": scenario, "predicted": p, "realized_next_step_ttt": r})
    pr = pd.DataFrame(rows)
    if not pr.empty:
        fig, ax = plt.subplots(figsize=(5.8, 4.2))
        for scenario, sdf in pr.groupby("scenario"):
            ax.scatter(sdf["predicted"], sdf["realized_next_step_ttt"], label=SCENARIO_LABEL[scenario], s=28)
        ax.set_xlabel("Selected leader objective")
        ax.set_ylabel("Next-step realized TTT (veh-h)")
        ax.set_title("Fig. 4D. Selected Objective vs Realized Plant TTT")
        ax.legend(frameon=True)
        save(fig, dirs["coupling"] / "Fig4D_predicted_vs_realized_selected", manifest)
    else:
        manifest.append({"status": "skipped", "figure": "Fig4D", "reason": "predicted selected objective unavailable"})

    audit = pd.DataFrame(
        [
            {"State group": "Freeway segment vehicles", "Freeway follower": 1, "Urban follower": 0, "Leader": 1, "Plant TTT": 1},
            {"State group": "Ramp queue", "Freeway follower": 1, "Urban follower": 0, "Leader": 1, "Plant TTT": 1},
            {"State group": "On-ramp approach queue", "Freeway follower": 1, "Urban follower": 1, "Leader": 1, "Plant TTT": 1},
            {"State group": "Urban movement queue", "Freeway follower": 0, "Urban follower": 1, "Leader": 1, "Plant TTT": 1},
            {"State group": "Off-ramp storage", "Freeway follower": 1, "Urban follower": 1, "Leader": 1, "Plant TTT": 1},
            {"State group": "Boundary queue/load", "Freeway follower": 0, "Urban follower": 1, "Leader": 1, "Plant TTT": 1},
        ]
    )
    fig, ax = plt.subplots(figsize=(7.8, 3.8))
    mat = audit.drop(columns=["State group"]).values
    ax.imshow(mat, cmap="Greens", vmin=0, vmax=1)
    ax.set_xticks(np.arange(mat.shape[1]))
    ax.set_xticklabels(audit.columns[1:], rotation=25, ha="right", fontsize=8)
    ax.set_yticks(np.arange(mat.shape[0]))
    ax.set_yticklabels(audit["State group"], fontsize=8)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, "yes" if mat[i, j] else "no", ha="center", va="center", fontsize=8)
    ax.tick_params(axis="both", pad=2)
    ax.set_title("Fig. 4E. Objective Coverage Audit")
    save(fig, dirs["coupling"] / "Fig4E_objective_coverage_audit", manifest)


def micro_figures(runlog: pd.DataFrame, controls: pd.DataFrame, dirs: dict[str, Path], manifest: list[dict[str, str]]) -> None:
    rows = []
    for (scenario, ctrl), rdf in runlog.groupby(["scenario", "controller_id"]):
        cdf = controls[(controls["scenario"] == scenario) & (controls["controller_id"] == ctrl)]
        met_cols = [c for c in cdf.columns if c.startswith("ramp_metering_")]
        vsl_cols = [c for c in cdf.columns if c.startswith("vsl_")]
        green_cols = [c for c in cdf.columns if c.startswith("green_")]
        offset_cols = [c for c in cdf.columns if c.startswith("offset_")]
        met = cdf[met_cols].apply(pd.to_numeric, errors="coerce") if met_cols else pd.DataFrame()
        vsl = cdf[vsl_cols].apply(pd.to_numeric, errors="coerce") if vsl_cols else pd.DataFrame()
        green = cdf[green_cols].apply(pd.to_numeric, errors="coerce") if green_cols else pd.DataFrame()
        offset = cdf[offset_cols].apply(pd.to_numeric, errors="coerce") if offset_cols else pd.DataFrame()
        rows.append(
            {
                "scenario": scenario,
                "controller_id": ctrl,
                "mean_metering_rate": met.mean(axis=1).mean() if not met.empty else np.nan,
                "metering_active_frac": (met < 1499.0).any(axis=1).mean() if not met.empty else 0.0,
                "mean_vsl_reduction": (100.0 - vsl).clip(lower=0).mean(axis=1).mean() if not vsl.empty else 0.0,
                "vsl_active_frac": (vsl < 99.0).any(axis=1).mean() if not vsl.empty else 0.0,
                "mean_green_adjustment": (green - 56.0).abs().mean(axis=1).mean() if not green.empty else 0.0,
                "green_active_frac": ((green - 56.0).abs() > 1.0).any(axis=1).mean() if not green.empty else 0.0,
                "mean_offset_change": offset.diff().abs().mean(axis=1).mean() if not offset.empty else 0.0,
                "offset_active_frac": (offset.diff().abs() > 1.0).any(axis=1).mean() if not offset.empty else 0.0,
                "ramp_queue_exposure": rdf.get("ramp_queue_veh", pd.Series(0, index=rdf.index)).sum() * 180.0 / 3600.0,
                "ramp_releases": rdf.get("ramp_metering_releases_veh", pd.Series(0, index=rdf.index)).sum(),
            }
        )
    micro = pd.DataFrame(rows)

    panels = [
        ("mean_metering_rate", "Mean metering rate (veh/h)", "ramp_metering", "Fig5A_RM_mean_metering_rate"),
        ("metering_active_frac", "RM activation fraction", "ramp_metering", "Fig5A_RM_activation_fraction"),
        ("mean_vsl_reduction", "Mean VSL reduction (km/h)", "vsl", "Fig5B_VSL_reduction"),
        ("vsl_active_frac", "VSL activation fraction", "vsl", "Fig5B_VSL_activation"),
        ("mean_green_adjustment", "Mean green adjustment (s)", "green_time", "Fig5C_green_adjustment"),
        ("green_active_frac", "Green activation fraction", "green_time", "Fig5C_green_activation"),
        ("mean_offset_change", "Mean offset change (s)", "offset", "Fig5D_offset_change"),
        ("offset_active_frac", "Offset activation fraction", "offset", "Fig5D_offset_activation"),
    ]
    panel_dirs = {
        "ramp_metering": dirs["micro_rm"],
        "vsl": dirs["micro_vsl"],
        "green_time": dirs["micro_green"],
        "offset": dirs["micro_offset"],
    }
    for metric, ylabel, subdir, fname in panels:
        grouped_bars(
            micro,
            metric,
            ylabel,
            fname.replace("_", " "),
            panel_dirs[subdir] / fname,
            manifest,
        )

    for scenario in ["peak_demand", "incident_or_capacity_drop", "skew_peak"]:
        csub = controls[controls["scenario"] == scenario]
        rsub = runlog[runlog["scenario"] == scenario]
        if csub.empty:
            continue
        fig, axes = plt.subplots(4, 1, figsize=(8.6, 8.0), sharex=True)
        for ctrl in CONTROLLERS:
            cdf = csub[csub["controller_id"] == ctrl].sort_values("time_sec")
            rdf = rsub[rsub["controller_id"] == ctrl].sort_values("time_sec")
            if cdf.empty:
                continue
            t = cdf["time_sec"] / 60.0
            met_cols = [c for c in cdf.columns if c.startswith("ramp_metering_")]
            vsl_cols = [c for c in cdf.columns if c.startswith("vsl_")]
            green_cols = [c for c in cdf.columns if c.startswith("green_")]
            offset_cols = [c for c in cdf.columns if c.startswith("offset_")]
            if met_cols:
                axes[0].plot(t, cdf[met_cols].mean(axis=1), color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
            if vsl_cols:
                axes[1].plot(t, cdf[vsl_cols].mean(axis=1), color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
            if green_cols:
                axes[2].plot(t, (cdf[green_cols] - 56.0).abs().mean(axis=1), color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
            if offset_cols:
                axes[3].plot(t, cdf[offset_cols].diff().abs().mean(axis=1), color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        axes[0].set_ylabel("Mean RM (veh/h)")
        axes[1].set_ylabel("Mean VSL (km/h)")
        axes[2].set_ylabel("|green-fixed| (s)")
        axes[3].set_ylabel("|offset change| (s)")
        axes[3].set_xlabel("Time (min)")
        add_top_legend(fig, axes, ncol=4, y=1.04)
        fig.subplots_adjust(top=0.90)
        fig.suptitle(f"Fig. 5. Mechanism Panel: {SCENARIO_LABEL[scenario]}")
        save(fig, dirs["micro"] / f"Fig5_mechanism_panel_{scenario}", manifest)


def computation_figures(summary: pd.DataFrame, progress: pd.DataFrame, diag: pd.DataFrame, dirs: dict[str, Path], manifest: list[dict[str, str]]) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    data = [
        progress.loc[progress["controller_id"] == c, "controller_compute_time_sec"].dropna().values
        for c in CONTROLLERS
        if c != "NO-CONTROL"
    ]
    labels = [CTRL_SHORT[c] for c in CONTROLLERS if c != "NO-CONTROL"]
    ax.boxplot(data, showfliers=False)
    ax.set_xticklabels(labels)
    ax.axhline(180.0, color="0.25", linestyle="--", linewidth=1.0, label="180 s control interval")
    ax.set_ylabel("Runtime per control step (s)")
    ax.set_title("Fig. 6A. Runtime Per Control Step")
    ax.legend(frameon=True)
    save(fig, dirs["compute"] / "Fig6A_runtime_per_control_step", manifest)

    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.6))
    metrics = [
        ("solver_evaluations", "Solver evaluations"),
        ("leader_candidate_count", "Leader candidates"),
        ("distributed_grid_total_candidates", "Follower grid candidates"),
    ]
    for ax, (metric, ylabel) in zip(axes, metrics):
        source = diag if metric in diag else progress
        if metric not in source:
            ax.set_axis_off()
            continue
        vals = [
            source.loc[source["controller_id"] == c, metric].dropna().mean()
            for c in CONTROLLERS
            if c != "NO-CONTROL"
        ]
        ax.bar(labels, vals, color=[CTRL_COLOR[c] for c in CONTROLLERS if c != "NO-CONTROL"])
        ax.set_ylabel(ylabel)
    fig.suptitle("Fig. 6B. Candidate Evaluation Budget")
    save(fig, dirs["compute"] / "Fig6B_candidate_evaluation_budget", manifest)

    fig, ax = plt.subplots(figsize=(6.8, 4.8))
    for ctrl in CONTROLLERS:
        if ctrl == "NO-CONTROL":
            continue
        for scenario, sdf in summary[summary["controller_id"] == ctrl].groupby("scenario"):
            if sdf.empty:
                continue
            ax.scatter(
                sdf["wall_time_sec"] / 20.0,
                sdf["total_ttt_improvement_vs_no_control_pct"],
                color=CTRL_COLOR[ctrl],
                marker=SCENARIO_MARKER.get(scenario, "o"),
                edgecolor="white",
                linewidth=0.6,
                s=58,
            )
    ax.axvline(180.0, color="0.25", linestyle="--", linewidth=1.0)
    ax.set_xlabel("Mean wall time per step (s)")
    ax.set_ylabel("TTT improvement vs no-control (%)")
    ax.set_title("Fig. 6C. Performance-Compute Trade-Off")
    controller_handles = [
        Line2D([0], [0], marker="o", linestyle="", markersize=7, color=CTRL_COLOR[c], label=CTRL_LABEL[c])
        for c in CONTROLLERS
        if c != "NO-CONTROL"
    ]
    scenario_handles = [
        Line2D(
            [0],
            [0],
            marker=SCENARIO_MARKER.get(s["id"], "o"),
            linestyle="",
            markersize=7,
            markerfacecolor="white",
            markeredgecolor="0.25",
            label=s["label"],
        )
        for s in SCENARIOS
    ]
    first_legend = ax.legend(handles=controller_handles, frameon=True, loc="lower right", title="Controller")
    ax.add_artist(first_legend)
    ax.legend(handles=scenario_handles, frameon=True, loc="upper left", title="Scenario")
    save(fig, dirs["compute"] / "Fig6C_performance_compute_tradeoff", manifest)


def write_manifest(manifest: list[dict[str, str]], skipped_extra: list[dict[str, str]]) -> None:
    payload = {
        "purpose": "New figure set generated from docs/figure_design guidance, not a copy of the old 6/23 figures.",
        "source_raw": [
            str((D1).resolve()),
            str((D2).resolve()),
        ],
        "focus_scenarios": [{k: v for k, v in s.items() if k != "root"} for s in SCENARIOS],
        "controllers": CONTROLLERS,
        "generated_count": sum(1 for item in manifest if item.get("status") == "generated"),
        "skipped": [item for item in manifest if item.get("status") == "skipped"] + skipped_extra,
        "figures": manifest,
    }
    (OUT / "manifest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    setup_style()
    dirs = ensure_dirs()
    manifest: list[dict[str, str]] = []
    skipped_extra: list[dict[str, str]] = []

    summary = load_summary()
    progress = load_file("progress_summary.csv")
    runlog = load_file("run_log.csv")
    controls = load_file("control_timeseries.csv")
    diag = load_file("decision_diagnostics.csv")

    if summary.empty:
        raise RuntimeError("No summary data loaded from 6/23 Desktop raw outputs.")

    summary.to_csv(dirs["tables"] / "df_summary_focus.csv", index=False)
    progress.to_csv(dirs["tables"] / "df_progress_focus.csv", index=False)

    macro_figures(summary, progress, dirs, manifest)
    exp = congestion_figures(runlog, dirs, manifest)
    if not exp.empty:
        exp.to_csv(dirs["tables"] / "df_queue_exposure_focus.csv", index=False)
    leader_figures(progress, runlog, diag, dirs, manifest)
    coupling_figures(progress, runlog, diag, dirs, manifest)
    micro_figures(runlog, controls, dirs, manifest)
    computation_figures(summary, progress, diag, dirs, manifest)

    if not any("Fig3B" in item.get("png", "") for item in manifest):
        skipped_extra.append(
            {
                "figure": "candidate full objective surface",
                "reason": "decision_progress.csv with rejected candidate-level objective values was not present in 6/23 raw outputs.",
            }
        )
    write_manifest(manifest, skipped_extra)
    print(f"output_dir={OUT}")
    print(f"generated_count={sum(1 for item in manifest if item.get('status') == 'generated')}")
    print(f"manifest={OUT / 'manifest.json'}")


if __name__ == "__main__":
    main()
