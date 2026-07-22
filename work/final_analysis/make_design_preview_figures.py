from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = WORKSPACE_ROOT / "outputs" / "final_5x5_10800"
EXTRACT_ROOT = WORKSPACE_ROOT / "outputs" / "final_analysis_extract_5x5_10800"
OUT_DIR = WORKSPACE_ROOT / "outputs" / "paper_figure_design_preview_20260718"
RHO_CRIT = 33.5

CONTROLLER_LABELS = {
    "NO-CONTROL": "NC",
    "WU-CD-F": "WU-CD-F",
    "WU-FAITHFUL-FOLLOWER": "PFO-link",
    "P-STACK-WU-FAITHFUL-APJOINT-FINAL": "P-Stack",
    "P-CENT-SLSQP": "P-Cent-SLSQP",
}

RAW_BY_LABEL = {v: k for k, v in CONTROLLER_LABELS.items()}
RAW_BY_LABEL["NC"] = "NO-CONTROL"

CONTROLLER_ORDER = ["NC", "WU-CD-F", "PFO-link", "P-Stack", "P-Cent-SLSQP"]
COLORS = {
    "NC": "#5c6570",
    "WU-CD-F": "#b87914",
    "PFO-link": "#148f87",
    "P-Stack": "#2f65b0",
    "P-Cent-SLSQP": "#8b4ab8",
}
SCENARIO_LABELS = {
    "sweet_155_w": "Low 155",
    "sweet_170_w": "Mid 170",
    "sweet_190_w": "High 190",
    "sweet_200_w": "Stress 200",
    "sweet_170_skew15_w": "Skew 170",
    "sweet_170_incident_w": "Incident 170",
}
SCENARIO_ORDER = [
    "sweet_155_w",
    "sweet_170_w",
    "sweet_190_w",
    "sweet_200_w",
    "sweet_170_skew15_w",
    "sweet_170_incident_w",
]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def numeric(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def run_dir(scenario: str, controller_label: str) -> Path:
    raw = RAW_BY_LABEL.get(controller_label, controller_label)
    return SOURCE_ROOT / scenario / raw


def setup_ax(ax: plt.Axes, title: str, ylabel: str = "", xlabel: str = "") -> None:
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    ax.grid(axis="y", color="#d7dde5", linewidth=0.8, alpha=0.9)
    ax.grid(axis="x", color="#e8edf3", linewidth=0.55, alpha=0.35)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#b9c1cc")
    ax.tick_params(colors="#2e3440", labelsize=9)
    ax.text(
        0.995,
        1.015,
        "DRAFT DESIGN PREVIEW",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=7,
        color="#8a93a3",
        fontweight="bold",
    )


def save(fig: plt.Figure, stem: str, rows: list[dict[str, str]], note: str) -> None:
    ensure_dir(OUT_DIR)
    fig.tight_layout()
    png = OUT_DIR / f"{stem}.png"
    pdf = OUT_DIR / f"{stem}.pdf"
    fig.savefig(png, dpi=220)
    fig.savefig(pdf)
    plt.close(fig)
    rows.append({"figure_id": stem, "png": str(png), "pdf": str(pdf), "note": note})


def add_legend(ax: plt.Axes, ncol: int = 1) -> None:
    handles, labels = ax.get_legend_handles_labels()
    if not handles:
        return
    ax.legend(
        frameon=False,
        fontsize=8,
        ncol=ncol,
        loc="best",
        handlelength=2.4,
        borderaxespad=0.8,
    )


def scenario_sort_key(value: str) -> int:
    try:
        return SCENARIO_ORDER.index(value)
    except ValueError:
        return len(SCENARIO_ORDER)


def grouped_bar(df: pd.DataFrame, metric: str, stem: str, title: str, ylabel: str, rows: list[dict[str, str]]) -> None:
    if df.empty or metric not in df.columns:
        return
    tmp = df[["scenario", "controller_label", metric]].copy()
    tmp = tmp[tmp["controller_label"].isin(CONTROLLER_ORDER)]
    tmp[metric] = pd.to_numeric(tmp[metric], errors="coerce")
    tmp = tmp.dropna(subset=[metric])
    if tmp.empty:
        return
    tmp["scenario"] = pd.Categorical(
        tmp["scenario"],
        categories=sorted(tmp["scenario"].unique(), key=scenario_sort_key),
        ordered=True,
    )
    tmp["controller_label"] = pd.Categorical(tmp["controller_label"], categories=CONTROLLER_ORDER, ordered=True)
    pivot = tmp.pivot_table(index="scenario", columns="controller_label", values=metric, aggfunc="first", observed=False)
    pivot = pivot.dropna(axis=1, how="all")
    labels = [SCENARIO_LABELS.get(str(i), str(i)) for i in pivot.index]
    x = np.arange(len(pivot.index))
    width = min(0.16, 0.72 / max(1, len(pivot.columns)))
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    for idx, controller in enumerate(pivot.columns):
        offset = (idx - (len(pivot.columns) - 1) / 2.0) * width
        ax.bar(
            x + offset,
            pivot[controller].values,
            width=width,
            label=str(controller),
            color=COLORS.get(str(controller), "#777777"),
            edgecolor="white",
            linewidth=0.7,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=0)
    setup_ax(ax, title, ylabel)
    add_legend(ax, ncol=min(5, len(pivot.columns)))
    save(fig, stem, rows, "macro grouped bar; current data preview, not final 190 matrix")


def load_macro() -> pd.DataFrame:
    df = read_csv(EXTRACT_ROOT / "final_5x5_windowed_macro.csv")
    if df.empty:
        return df
    for col in ["total_ttt", "improvement_vs_nc_pct", "completed_vehicles", "terminal_vehicles", "att_min_per_completed", "realtime_ratio", "compute_s_per_step"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def macro_figures(rows: list[dict[str, str]]) -> None:
    macro = load_macro()
    grouped_bar(macro, "total_ttt", "preview_macro_wttt", "Windowed Total Travel Time", "veh*h", rows)
    grouped_bar(macro, "improvement_vs_nc_pct", "preview_macro_improvement_vs_nc", "Improvement Relative To NC", "%", rows)
    grouped_bar(macro, "completed_vehicles", "preview_macro_completed_vehicles", "Completed Vehicles", "vehicles", rows)
    grouped_bar(macro, "terminal_vehicles", "preview_macro_terminal_vehicles", "Terminal Vehicles At T", "vehicles", rows)
    grouped_bar(macro, "att_min_per_completed", "preview_macro_att_completed", "Average Travel Time For Completed Trips", "min/veh", rows)
    grouped_bar(macro, "realtime_ratio", "preview_macro_realtime_ratio", "Real-Time Compute Ratio", "compute / 180s", rows)
    if not macro.empty and {"compute_s_per_step", "total_ttt", "controller_label", "scenario"}.issubset(macro.columns):
        tmp = macro.dropna(subset=["compute_s_per_step", "total_ttt"]).copy()
        fig, ax = plt.subplots(figsize=(7.2, 5.2))
        for controller in CONTROLLER_ORDER:
            group = tmp[tmp["controller_label"].eq(controller)]
            if group.empty:
                continue
            ax.scatter(
                group["compute_s_per_step"],
                group["total_ttt"],
                label=controller,
                s=58,
                color=COLORS.get(controller, "#777777"),
                edgecolor="white",
                linewidth=0.7,
            )
        setup_ax(ax, "Compute-Performance Frontier", "window TTT (veh*h)", "mean compute per step (s)")
        add_legend(ax)
        save(fig, "preview_macro_compute_frontier", rows, "macro scatter; current data preview")


def line_plot(
    df: pd.DataFrame,
    cols: Iterable[str],
    stem: str,
    title: str,
    ylabel: str,
    rows: list[dict[str, str]],
    label_cleanup: bool = True,
    hline: float | None = None,
    hline_label: str = "",
) -> None:
    cols = [c for c in cols if c in df.columns and pd.to_numeric(df[c], errors="coerce").notna().any()]
    if df.empty or not cols:
        return
    time_col = "time_sec" if "time_sec" in df.columns else "step"
    x = numeric(df, time_col)
    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    palette = ["#2f65b0", "#148f87", "#b87914", "#8b4ab8", "#d45f5f", "#4d6f77", "#7b8f2a", "#6f5f90"]
    for idx, col in enumerate(cols):
        y = numeric(df, col)
        label = col
        if label_cleanup:
            label = re.sub(r"^(ramp_metering_|ramp_queue_|diag_wu_b2_price_|diag_wu_b3_meter_price_|diag_wu_f3_offset_price_)", "", label)
            label = label.replace("green_", "").replace("_p1", "")
            label = label.replace("offset_", "")
            label = re.sub(r"^rho_(FW_[EW])_mean$", r"\1", label)
        ax.plot(x, y, label=label, linewidth=1.9, color=palette[idx % len(palette)])
    if hline is not None:
        ax.axhline(hline, color="#343a40", linewidth=1.1, linestyle=(0, (4, 3)), label=hline_label or f"{hline:g}")
    setup_ax(ax, title, ylabel, "time (s)")
    add_legend(ax, ncol=2 if len(cols) > 4 else 1)
    save(fig, stem, rows, "single-metric trajectory preview")


def compare_cumulative_ttt(scenario: str, rows: list[dict[str, str]]) -> None:
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    for controller in CONTROLLER_ORDER[:-1]:
        path = run_dir(scenario, controller) / "run_log.csv"
        df = read_csv(path)
        if df.empty or "cumulative_total_ttt" not in df.columns:
            continue
        ax.plot(
            numeric(df, "time_sec"),
            numeric(df, "cumulative_total_ttt"),
            label=controller,
            color=COLORS.get(controller, "#777777"),
            linewidth=2.0,
        )
    setup_ax(ax, f"{SCENARIO_LABELS.get(scenario, scenario)}: Cumulative TTT", "veh*h", "time (s)")
    add_legend(ax, ncol=4)
    save(fig, f"preview_{scenario}_cumulative_ttt_compare", rows, "controller comparison trajectory preview")


def vsl_heatmap(scenario: str, controller: str, rows: list[dict[str, str]]) -> None:
    df = read_csv(run_dir(scenario, controller) / "control_timeseries.csv")
    cols = [c for c in df.columns if re.match(r"vsl_.*_seg\d+$", c)] if not df.empty else []
    if df.empty or not cols:
        return
    matrix = df[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float).T
    time = numeric(df, "time_sec").to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    im = ax.imshow(matrix, aspect="auto", origin="lower", extent=[np.nanmin(time), np.nanmax(time), -0.5, len(cols) - 0.5], cmap="viridis")
    ax.set_yticks(range(len(cols)))
    ax.set_yticklabels([c.replace("vsl_", "") for c in cols], fontsize=7)
    setup_ax(ax, f"{SCENARIO_LABELS.get(scenario, scenario)} / {controller}: VSL Commands", "segment", "time (s)")
    fig.colorbar(im, ax=ax, label="km/h")
    save(fig, f"preview_{scenario}_{controller}_vsl_heatmap", rows, "single heatmap preview")


def mechanism_figures(rows: list[dict[str, str]]) -> None:
    compare_cumulative_ttt("sweet_170_w", rows)
    compare_cumulative_ttt("sweet_170_incident_w", rows)
    stack_scenario = "sweet_170_w"
    incident_scenario = "sweet_170_incident_w"
    stack_control = read_csv(run_dir(stack_scenario, "P-Stack") / "control_timeseries.csv")
    stack_state = read_csv(run_dir(stack_scenario, "P-Stack") / "state_timeseries.csv")
    incident_control = read_csv(run_dir(incident_scenario, "P-Stack") / "control_timeseries.csv")
    incident_state = read_csv(run_dir(incident_scenario, "P-Stack") / "state_timeseries.csv")
    incident_log = read_csv(run_dir(incident_scenario, "P-Stack") / "run_log.csv")

    line_plot(stack_control, ["N_UF_star"], "preview_sweet_170_w_pstack_nuf_target", "Mid 170 / P-Stack: Urban-To-Freeway Target", "veh/h", rows)
    line_plot(stack_control, ["N_P_star"], "preview_sweet_170_w_pstack_np_target", "Mid 170 / P-Stack: Protected Accumulation Target", "veh", rows)
    line_plot(stack_control, [c for c in stack_control.columns if c.startswith("ramp_metering_")], "preview_sweet_170_w_pstack_ramp_metering", "Mid 170 / P-Stack: Ramp Metering", "veh/h", rows)
    line_plot(stack_state, [c for c in stack_state.columns if c.startswith("ramp_queue_")], "preview_sweet_170_w_pstack_ramp_queue", "Mid 170 / P-Stack: Ramp Queues", "vehicles", rows)
    line_plot(stack_control, [c for c in stack_control.columns if c.startswith("green_") and c.endswith("_p1")], "preview_sweet_170_w_pstack_green", "Mid 170 / P-Stack: Green Phase 1", "s", rows)
    line_plot(stack_control, [c for c in stack_control.columns if c.startswith("offset_")], "preview_sweet_170_w_pstack_offsets", "Mid 170 / P-Stack: Offset Commands", "s", rows)

    if not incident_state.empty:
        rho_cols = [c for c in incident_state.columns if re.match(r"rho_FW_.*_mean$", c)]
        ratio = incident_state[["time_sec"] + rho_cols].copy() if rho_cols and "time_sec" in incident_state.columns else pd.DataFrame()
        for col in rho_cols:
            ratio[col] = pd.to_numeric(ratio[col], errors="coerce") / RHO_CRIT
        line_plot(
            ratio,
            rho_cols,
            "preview_sweet_170_incident_w_pstack_density_ratio",
            "Incident 170 / P-Stack: Freeway Density Ratio",
            "rho / rho_crit",
            rows,
            hline=1.0,
            hline_label="critical density",
        )
    line_plot(incident_log, ["capacity_drop_active", "incident_lane_closure_active"], "preview_sweet_170_incident_w_pstack_incident_flags", "Incident 170 / P-Stack: Incident And Capacity Drop", "indicator", rows)
    vsl_heatmap(incident_scenario, "P-Stack", rows)
    line_plot(incident_control, [c for c in incident_control.columns if re.match(r"vsl_.*_seg\d+$", c)][:8], "preview_sweet_170_incident_w_pstack_vsl_lines", "Incident 170 / P-Stack: VSL Line Sample", "km/h", rows)


def price_figures(rows: list[dict[str, str]]) -> None:
    scenario = "sweet_170_w"
    control = read_csv(run_dir(scenario, "P-Stack") / "control_timeseries.csv")
    if control.empty:
        return
    excluded = ("enabled", "delta", "trust", "ref", "refresh", "count")
    green = [c for c in control.columns if c.startswith("diag_wu_b2_price_") and not any(x in c for x in excluded)]
    meter = [c for c in control.columns if c.startswith("diag_wu_b3_meter_price_") and not any(x in c for x in excluded)]
    offset = [c for c in control.columns if c.startswith("diag_wu_f3_offset_price_") and not any(x in c for x in excluded)]
    line_plot(control, green, "preview_sweet_170_w_pstack_price_green", "Mid 170 / P-Stack: Green Prices", "marginal cost", rows)
    line_plot(control, meter, "preview_sweet_170_w_pstack_price_metering", "Mid 170 / P-Stack: Metering Prices", "marginal cost", rows)
    line_plot(control, offset, "preview_sweet_170_w_pstack_price_offset", "Mid 170 / P-Stack: Offset Prices", "marginal cost", rows)

    audit = read_csv(EXTRACT_ROOT / "final_price_channel_audit.csv")
    if not audit.empty and {"channel", "status", "max_abs_price"}.issubset(audit.columns):
        tmp = audit.groupby(["channel", "status"], as_index=False)["max_abs_price"].max()
        status_labels = {
            "normal": "normal",
            "domain_constrained": "domain constrained",
            "enabled_no_scalar_price_values_exported": "enabled; no scalar price export",
            "truly_flat_or_inactive": "flat/inactive",
            "not_observed": "not observed",
        }
        labels = [f"{r.channel} - {status_labels.get(str(r.status), str(r.status))}" for r in tmp.itertuples()]
        values = pd.to_numeric(tmp["max_abs_price"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        y = np.arange(len(labels))
        fig, ax = plt.subplots(figsize=(8.4, 4.8))
        ax.barh(y, values, color="#2f65b0", edgecolor="white")
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        setup_ax(ax, "Price Channel Audit Preview", "", "max |price|")
        save(fig, "preview_price_channel_audit", rows, "price audit design preview")


def write_index(rows: list[dict[str, str]]) -> None:
    ensure_dir(OUT_DIR)
    with (OUT_DIR / "preview_plot_index.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["figure_id", "png", "pdf", "note"])
        writer.writeheader()
        writer.writerows(rows)
    with (OUT_DIR / "README.md").open("w", encoding="utf-8") as handle:
        handle.write("# Paper Figure Design Preview\n\n")
        handle.write("These figures are design previews from currently available runs. Do not cite them as the final 190-based matrix.\n\n")
        handle.write("- Every figure is saved as both PNG and PDF.\n")
        handle.write("- No multi-panel subplot figures are generated.\n")
        handle.write("- `sweet_200_w` appears only where current preview data exists; final paper high-demand should use `sweet_190_w`.\n")


def main() -> None:
    rows: list[dict[str, str]] = []
    macro_figures(rows)
    mechanism_figures(rows)
    price_figures(rows)
    write_index(rows)
    print(f"Wrote {len(rows)} preview figures to {OUT_DIR}")


if __name__ == "__main__":
    main()
