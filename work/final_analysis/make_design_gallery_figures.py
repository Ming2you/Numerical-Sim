from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOTS = [
    WORKSPACE_ROOT / "outputs" / "final_5x5_10800",
    WORKSPACE_ROOT / "outputs" / "final_sweet190_w_10800",
]
DEFAULT_OUT_DIR = WORKSPACE_ROOT / "outputs" / "paper_figure_design_gallery_20260718"

WINDOW_START_SEC = 3600.0
WINDOW_END_SEC = 10800.0
WARMUP_NC_STEPS = 20
DEFAULT_INTERVAL_SEC = 180.0
RHO_CRIT = 33.5

CONTROLLER_LABELS = {
    "NO-CONTROL": "NC",
    "WU-CD-F": "WU-CD-F",
    "WU-FAITHFUL-FOLLOWER": "PFO-link",
    "P-STACK-WU-FAITHFUL-APJOINT-FINAL": "P-Stack",
    "P-CENT-SLSQP": "P-Cent-SLSQP",
}
CONTROLLER_ORDER = ["NC", "WU-CD-F", "PFO-link", "P-Stack", "P-Cent-SLSQP"]
SCENARIO_ORDER = [
    "sweet_155_w",
    "sweet_170_w",
    "sweet_190_w",
    "sweet_200_w",
    "sweet_170_skew15_w",
    "sweet_170_incident_w",
]
SCENARIO_LABELS = {
    "sweet_155_w": "Low 155",
    "sweet_170_w": "Mid 170",
    "sweet_190_w": "High 190",
    "sweet_200_w": "Stress 200",
    "sweet_170_skew15_w": "Skew 170",
    "sweet_170_incident_w": "Incident 170",
}
COLORS = {
    "NC": "#5c6570",
    "WU-CD-F": "#b87914",
    "PFO-link": "#148f87",
    "P-Stack": "#2f65b0",
    "P-Cent-SLSQP": "#8b4ab8",
    "FW_E": "#2f65b0",
    "FW_W": "#148f87",
}
LINE_PALETTE = [
    "#2f65b0",
    "#148f87",
    "#b87914",
    "#8b4ab8",
    "#d45f5f",
    "#4d6f77",
    "#7b8f2a",
    "#6f5f90",
    "#a35f2a",
    "#2f8fb0",
]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def controller_label(raw: str) -> str:
    return CONTROLLER_LABELS.get(raw, raw)


def scenario_label(raw: str) -> str:
    return SCENARIO_LABELS.get(raw, raw)


def scenario_key(raw: str) -> int:
    try:
        return SCENARIO_ORDER.index(raw)
    except ValueError:
        return len(SCENARIO_ORDER)


def controller_key(raw: str) -> int:
    try:
        return CONTROLLER_ORDER.index(raw)
    except ValueError:
        return len(CONTROLLER_ORDER)


def infer_scenario(run_dir: Path) -> str:
    for part in run_dir.parts:
        if part in SCENARIO_ORDER or re.match(r"sweet_\d+(?:_skew\d+|_incident)?_w$", part):
            return part
    return run_dir.parent.name


def infer_interval(df: pd.DataFrame) -> float:
    if "time_sec" not in df.columns or len(df) < 2:
        return DEFAULT_INTERVAL_SEC
    time = to_num(df["time_sec"]).dropna().sort_values()
    diffs = time.diff().dropna()
    diffs = diffs[diffs > 0.0]
    return float(diffs.median()) if not diffs.empty else DEFAULT_INTERVAL_SEC


def ensure_time(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    if "time_sec" not in out.columns and "step" in out.columns:
        out["time_sec"] = (to_num(out["step"]) + 1.0) * DEFAULT_INTERVAL_SEC
    return out


def windowed(df: pd.DataFrame, label: str) -> pd.DataFrame:
    out = ensure_time(df)
    if out.empty or "time_sec" not in out.columns:
        return out.iloc[0:0].copy()
    interval = infer_interval(out)
    start = max(WINDOW_START_SEC, WARMUP_NC_STEPS * interval) if label == "NC" else WINDOW_START_SEC
    time = to_num(out["time_sec"])
    return out.loc[(time >= start) & (time <= WINDOW_END_SEC)].copy()


def find_run_dirs() -> list[Path]:
    out: list[Path] = []
    for root in SOURCE_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("run_log.csv"):
            run_dir = path.parent
            if run_dir not in out:
                out.append(run_dir)
    return sorted(out, key=lambda p: (scenario_key(infer_scenario(p)), controller_key(controller_label(p.name)), str(p)))


def status_tag(df: pd.DataFrame) -> str:
    if df.empty or "time_sec" not in ensure_time(df).columns:
        return "missing"
    end = float(to_num(ensure_time(df)["time_sec"]).max())
    return "complete" if end >= WINDOW_END_SEC else f"partial {end:.0f}s"


def setup_ax(ax: plt.Axes, title: str, ylabel: str = "", xlabel: str = "") -> None:
    ax.set_title(title, loc="left", fontsize=12.5, fontweight="bold", pad=11)
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
        "DRAFT FIGURE GALLERY",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=7,
        color="#8a93a3",
        fontweight="bold",
    )


def add_legend(ax: plt.Axes, ncol: int = 1) -> None:
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(frameon=False, fontsize=8, ncol=ncol, loc="best", handlelength=2.4)


def save(fig: plt.Figure, out_dir: Path, stem: str, index_rows: list[dict[str, str]], note: str) -> None:
    ensure_dir(out_dir)
    fig.tight_layout()
    png = out_dir / f"{stem}.png"
    pdf = out_dir / f"{stem}.pdf"
    fig.savefig(png, dpi=220)
    fig.savefig(pdf)
    plt.close(fig)
    index_rows.append({"figure_id": stem, "png": str(png), "pdf": str(pdf), "note": note})


def line_cols(df: pd.DataFrame, patterns: Iterable[str]) -> list[str]:
    cols: list[str] = []
    for pattern in patterns:
        for col in df.columns:
            if re.match(pattern, col) and col not in cols and to_num(df[col]).notna().any():
                cols.append(col)
    return cols


def clean_label(col: str) -> str:
    replacements = [
        (r"^rho_(FW_[EW])_mean$", r"\1"),
        (r"^speed_(FW_[EW])_mean$", r"\1"),
        (r"^flow_(FW_[EW])_mean$", r"\1"),
        (r"^ramp_metering_", ""),
        (r"^ramp_queue_", ""),
        (r"^green_", ""),
        (r"_p1$", ""),
        (r"^offset_", ""),
        (r"^diag_wu_b2_price_", ""),
        (r"^diag_wu_b3_meter_price_", ""),
        (r"^diag_wu_f3_offset_price_", ""),
        (r"^diag_wu_b3_vsl_price_", ""),
        (r"^vsl_", ""),
    ]
    out = col
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out)
    return out


def line_plot(
    df: pd.DataFrame,
    cols: list[str],
    out_dir: Path,
    stem: str,
    title: str,
    ylabel: str,
    index_rows: list[dict[str, str]],
    hline: float | None = None,
    hline_label: str = "",
    max_legend_cols: int = 2,
) -> None:
    df = ensure_time(df)
    cols = [c for c in cols if c in df.columns and to_num(df[c]).notna().any()]
    if df.empty or "time_sec" not in df.columns or not cols:
        return
    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    x = to_num(df["time_sec"])
    for idx, col in enumerate(cols):
        ax.plot(x, to_num(df[col]), label=clean_label(col), linewidth=1.85, color=LINE_PALETTE[idx % len(LINE_PALETTE)])
    if hline is not None:
        ax.axhline(hline, color="#343a40", linewidth=1.1, linestyle=(0, (4, 3)), label=hline_label or f"{hline:g}")
    setup_ax(ax, title, ylabel, "time (s)")
    add_legend(ax, ncol=max_legend_cols if len(cols) > 3 else 1)
    save(fig, out_dir, stem, index_rows, "line figure")


def heatmap_plot(
    df: pd.DataFrame,
    cols: list[str],
    out_dir: Path,
    stem: str,
    title: str,
    cbar_label: str,
    index_rows: list[dict[str, str]],
) -> None:
    df = ensure_time(df)
    cols = [c for c in cols if c in df.columns and to_num(df[c]).notna().any()]
    if df.empty or "time_sec" not in df.columns or not cols:
        return
    matrix = df[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float).T
    if np.isnan(matrix).all():
        return
    time = to_num(df["time_sec"]).to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(9.2, max(4.8, 0.23 * len(cols))))
    im = ax.imshow(
        matrix,
        aspect="auto",
        origin="lower",
        extent=[np.nanmin(time), np.nanmax(time), -0.5, len(cols) - 0.5],
        cmap="viridis",
    )
    ax.set_yticks(range(len(cols)))
    ax.set_yticklabels([clean_label(c) for c in cols], fontsize=7)
    setup_ax(ax, title, "segment", "time (s)")
    fig.colorbar(im, ax=ax, label=cbar_label)
    save(fig, out_dir, stem, index_rows, "heatmap figure")


def compute_macro(run_dirs: list[Path]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for run_dir in run_dirs:
        scenario = infer_scenario(run_dir)
        raw_controller = run_dir.name
        label = controller_label(raw_controller)
        run_log = read_csv(run_dir / "run_log.csv")
        if run_log.empty:
            continue
        run_log = ensure_time(run_log)
        win = windowed(run_log, label)
        interval_h = infer_interval(run_log) / 3600.0
        completed = math.nan
        if not win.empty:
            completed = 0.0
            if "boundary_out_sink_veh" in win.columns:
                completed += float(to_num(win["boundary_out_sink_veh"]).sum())
            if "mainline_exit_flow_total" in win.columns:
                completed += float(to_num(win["mainline_exit_flow_total"]).sum()) * interval_h
        state = read_csv(run_dir / "state_timeseries.csv")
        terminal = math.nan
        if not state.empty:
            last = state.iloc[-1]
            if "terminal_total_vehicles" in state.columns:
                terminal = float(last["terminal_total_vehicles"])
            elif "urban_vehicles" in state.columns and "freeway_vehicles" in state.columns:
                terminal = float(last["urban_vehicles"]) + float(last["freeway_vehicles"])
        total_ttt = float(to_num(win["step_total_ttt"]).sum()) if "step_total_ttt" in win.columns and not win.empty else math.nan
        rows.append(
            {
                "scenario": scenario,
                "controller_label": label,
                "raw_controller": raw_controller,
                "complete": int(float(to_num(run_log["time_sec"]).max()) >= WINDOW_END_SEC),
                "window_ttt": total_ttt,
                "window_completed": completed,
                "terminal_vehicles": terminal,
                "att_completed": total_ttt / completed * 60.0 if completed and completed > 0 and np.isfinite(total_ttt) else math.nan,
                "mean_compute_sec": float(to_num(win["computation_time_sec"]).mean()) if "computation_time_sec" in win.columns and not win.empty else math.nan,
                "max_compute_sec": float(to_num(win["computation_time_sec"]).max()) if "computation_time_sec" in win.columns and not win.empty else math.nan,
                "realtime_ratio": float(to_num(win["computation_time_sec"]).mean()) / max(infer_interval(run_log), 1e-9)
                if "computation_time_sec" in win.columns and not win.empty
                else math.nan,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    complete = df[df["complete"].eq(1)].copy()
    nc = complete[complete["controller_label"].eq("NC")].set_index("scenario")["window_ttt"]
    complete["improvement_vs_nc_pct"] = complete.apply(
        lambda row: 100.0 * (nc.get(row["scenario"], np.nan) - row["window_ttt"]) / nc.get(row["scenario"], np.nan)
        if np.isfinite(nc.get(row["scenario"], np.nan)) and nc.get(row["scenario"], np.nan) != 0
        else np.nan,
        axis=1,
    )
    return complete


def grouped_bar(df: pd.DataFrame, out_dir: Path, metric: str, stem: str, title: str, ylabel: str, index_rows: list[dict[str, str]]) -> None:
    if df.empty or metric not in df.columns:
        return
    tmp = df[["scenario", "controller_label", metric]].copy()
    tmp[metric] = pd.to_numeric(tmp[metric], errors="coerce")
    tmp = tmp.dropna(subset=[metric])
    if tmp.empty:
        return
    scenarios = sorted(tmp["scenario"].unique(), key=scenario_key)
    controllers = [c for c in CONTROLLER_ORDER if c in set(tmp["controller_label"])]
    pivot = tmp.pivot_table(index="scenario", columns="controller_label", values=metric, aggfunc="first")
    pivot = pivot.reindex(index=scenarios, columns=controllers)
    x = np.arange(len(pivot.index))
    width = min(0.15, 0.75 / max(1, len(pivot.columns)))
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    for idx, controller in enumerate(pivot.columns):
        offset = (idx - (len(pivot.columns) - 1) / 2.0) * width
        ax.bar(
            x + offset,
            pivot[controller].to_numpy(dtype=float),
            width=width,
            label=controller,
            color=COLORS.get(controller, "#777777"),
            edgecolor="white",
            linewidth=0.7,
        )
    ax.set_xticks(x)
    ax.set_xticklabels([scenario_label(str(s)) for s in pivot.index])
    setup_ax(ax, title, ylabel)
    add_legend(ax, ncol=min(5, len(pivot.columns)))
    save(fig, out_dir, stem, index_rows, "macro grouped bar")


def macro_figures(run_dirs: list[Path], out_dir: Path, index_rows: list[dict[str, str]]) -> None:
    df = compute_macro(run_dirs)
    ensure_dir(out_dir)
    if not df.empty:
        df.to_csv(out_dir / "gallery_macro_source.csv", index=False)
    grouped_bar(df, out_dir, "window_ttt", "gallery_macro_wttt", "Windowed Total Travel Time", "veh*h", index_rows)
    grouped_bar(df, out_dir, "improvement_vs_nc_pct", "gallery_macro_improvement_vs_nc", "Improvement Relative To NC", "%", index_rows)
    grouped_bar(df, out_dir, "window_completed", "gallery_macro_completed_vehicles", "Completed Vehicles In Window", "vehicles", index_rows)
    grouped_bar(df, out_dir, "terminal_vehicles", "gallery_macro_terminal_vehicles", "Terminal Vehicles At T", "vehicles", index_rows)
    grouped_bar(df, out_dir, "att_completed", "gallery_macro_att_completed", "Average Travel Time For Completed Trips", "min/veh", index_rows)
    grouped_bar(df, out_dir, "mean_compute_sec", "gallery_macro_compute_mean", "Mean Step Compute", "s/step", index_rows)
    grouped_bar(df, out_dir, "max_compute_sec", "gallery_macro_compute_max", "Max Step Compute", "s/step", index_rows)
    grouped_bar(df, out_dir, "realtime_ratio", "gallery_macro_realtime_ratio", "Real-Time Compute Ratio", "compute / 180s", index_rows)
    if not df.empty:
        tmp = df.dropna(subset=["mean_compute_sec", "window_ttt"]).copy()
        if not tmp.empty:
            fig, ax = plt.subplots(figsize=(7.4, 5.3))
            for controller in CONTROLLER_ORDER:
                g = tmp[tmp["controller_label"].eq(controller)]
                if g.empty:
                    continue
                ax.scatter(g["mean_compute_sec"], g["window_ttt"], label=controller, color=COLORS.get(controller, "#777777"), s=58, edgecolor="white", linewidth=0.7)
            setup_ax(ax, "Compute-Performance Frontier", "window TTT (veh*h)", "mean compute per step (s)")
            add_legend(ax)
            save(fig, out_dir, "gallery_macro_compute_frontier", index_rows, "macro scatter")


def scenario_compare_figures(run_dirs: list[Path], out_dir: Path, index_rows: list[dict[str, str]]) -> None:
    by_scenario: dict[str, list[Path]] = {}
    for run_dir in run_dirs:
        by_scenario.setdefault(infer_scenario(run_dir), []).append(run_dir)
    for scenario, dirs in sorted(by_scenario.items(), key=lambda item: scenario_key(item[0])):
        fig, ax = plt.subplots(figsize=(8.8, 4.8))
        drew = False
        for run_dir in sorted(dirs, key=lambda p: controller_key(controller_label(p.name))):
            label = controller_label(run_dir.name)
            run_log = ensure_time(read_csv(run_dir / "run_log.csv"))
            if run_log.empty or "cumulative_total_ttt" not in run_log.columns:
                continue
            ax.plot(to_num(run_log["time_sec"]), to_num(run_log["cumulative_total_ttt"]), label=label, color=COLORS.get(label, "#777777"), linewidth=2.0)
            drew = True
        if not drew:
            plt.close(fig)
            continue
        setup_ax(ax, f"{scenario_label(scenario)}: Cumulative TTT By Controller", "veh*h", "time (s)")
        add_legend(ax, ncol=min(5, len(dirs)))
        save(fig, out_dir, f"gallery_{slug(scenario)}_cumulative_ttt_by_controller", index_rows, "scenario controller comparison")


def per_run_figures(run_dirs: list[Path], out_dir: Path, index_rows: list[dict[str, str]]) -> None:
    for run_dir in run_dirs:
        scenario = infer_scenario(run_dir)
        label = controller_label(run_dir.name)
        run_log = ensure_time(read_csv(run_dir / "run_log.csv"))
        control = ensure_time(read_csv(run_dir / "control_timeseries.csv"))
        state = ensure_time(read_csv(run_dir / "state_timeseries.csv"))
        tag = status_tag(run_log)
        base = f"gallery_{slug(scenario)}_{slug(label)}"
        prefix = f"{scenario_label(scenario)} / {label}"
        if tag != "complete":
            prefix += f" ({tag})"

        line_plot(run_log, [c for c in ["cumulative_total_ttt"] if c in run_log.columns], out_dir, f"{base}_cumulative_total_ttt", f"{prefix}: Cumulative Total TTT", "veh*h", index_rows)
        line_plot(run_log, [c for c in ["cumulative_urban_ttt", "cumulative_freeway_ttt"] if c in run_log.columns], out_dir, f"{base}_cumulative_urban_freeway_ttt", f"{prefix}: Urban And Freeway TTT", "veh*h", index_rows)
        line_plot(run_log, [c for c in ["capacity_drop_active", "incident_lane_closure_active"] if c in run_log.columns], out_dir, f"{base}_incident_capacity_drop", f"{prefix}: Incident And Capacity-Drop Flags", "indicator", index_rows)
        line_plot(run_log, [c for c in ["total_metering_flow", "total_no_meter_flow", "net_inflow", "net_inflow_target"] if c in run_log.columns], out_dir, f"{base}_release_flow", f"{prefix}: Release And Target Flows", "veh/h", index_rows, max_legend_cols=2)

        if not state.empty:
            rho_cols = line_cols(state, [r"rho_FW_.*_mean$"])
            if rho_cols:
                ratio = state[["time_sec"] + rho_cols].copy() if "time_sec" in state.columns else pd.DataFrame()
                for col in rho_cols:
                    ratio[col] = to_num(ratio[col]) / RHO_CRIT
                line_plot(ratio, rho_cols, out_dir, f"{base}_density_ratio", f"{prefix}: Freeway Density Ratio", "rho / rho_crit", index_rows, hline=1.0, hline_label="critical density")
            line_plot(state, line_cols(state, [r"speed_FW_.*_mean$"]), out_dir, f"{base}_freeway_speed", f"{prefix}: Freeway Speed", "km/h", index_rows)
            line_plot(state, line_cols(state, [r"flow_FW_.*_mean$"]), out_dir, f"{base}_freeway_flow", f"{prefix}: Freeway Flow", "veh/h", index_rows)
            line_plot(state, line_cols(state, [r"ramp_queue_.*"]), out_dir, f"{base}_ramp_queue", f"{prefix}: Ramp Queues", "vehicles", index_rows, max_legend_cols=2)
            line_plot(state, [c for c in ["urban_protected_accumulation_veh"] if c in state.columns], out_dir, f"{base}_urban_protected_accumulation", f"{prefix}: Protected Urban Accumulation", "vehicles", index_rows)

        if not control.empty:
            line_plot(control, [c for c in ["N_UF_star"] if c in control.columns], out_dir, f"{base}_nuf_target", f"{prefix}: Urban-To-Freeway Target", "veh/h", index_rows)
            line_plot(control, [c for c in ["N_P_star"] if c in control.columns], out_dir, f"{base}_np_target", f"{prefix}: Protected Accumulation Target", "vehicles", index_rows)
            line_plot(control, line_cols(control, [r"ramp_metering_.*"]), out_dir, f"{base}_ramp_metering", f"{prefix}: Ramp Metering", "veh/h", index_rows, max_legend_cols=2)
            line_plot(control, line_cols(control, [r"green_.*_p1$"]), out_dir, f"{base}_green_p1", f"{prefix}: Green Phase 1", "s", index_rows, max_legend_cols=2)
            line_plot(control, line_cols(control, [r"offset_.*"]), out_dir, f"{base}_offsets", f"{prefix}: Offset Commands", "s", index_rows, max_legend_cols=2)
            vsl_cols = line_cols(control, [r"vsl_.*_seg\d+$"])
            heatmap_plot(control, vsl_cols, out_dir, f"{base}_vsl_heatmap", f"{prefix}: VSL Commands", "km/h", index_rows)
            line_plot(control, vsl_cols[:8], out_dir, f"{base}_vsl_line_sample", f"{prefix}: VSL Line Sample", "km/h", index_rows, max_legend_cols=2)

            excluded = ("enabled", "delta", "trust", "ref", "refresh", "count")
            price_groups = [
                ("price_green", "Green Prices", [c for c in control.columns if c.startswith("diag_wu_b2_price_") and not any(x in c for x in excluded)]),
                ("price_metering", "Metering Prices", [c for c in control.columns if c.startswith("diag_wu_b3_meter_price_") and not any(x in c for x in excluded)]),
                ("price_offset", "Offset Prices", [c for c in control.columns if c.startswith("diag_wu_f3_offset_price_") and not any(x in c for x in excluded)]),
                ("price_vsl", "VSL Prices", [c for c in control.columns if c.startswith("diag_wu_b3_vsl_price_") and not any(x in c for x in excluded)]),
            ]
            for suffix, title, cols in price_groups:
                line_plot(control, cols, out_dir, f"{base}_{suffix}", f"{prefix}: {title}", "marginal cost", index_rows, max_legend_cols=2)


def write_static_preview(out_dir: Path, index_rows: list[dict[str, str]]) -> None:
    ensure_dir(out_dir)
    with (out_dir / "gallery_plot_index.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["figure_id", "png", "pdf", "note"])
        writer.writeheader()
        writer.writerows(index_rows)
    with (out_dir / "README.md").open("w", encoding="utf-8") as handle:
        handle.write("# Paper Figure Design Gallery\n\n")
        handle.write("Design gallery generated from currently available runs. These figures are not the final paper numbers.\n\n")
        handle.write("- One metric per figure; no multi-panel subplot figures.\n")
        handle.write("- PNG and PDF are saved for every figure.\n")
        handle.write("- Partial runs are marked in figure titles.\n")
        handle.write("- `sweet_200_w` is a stress preview; final high-demand paper figures should use `sweet_190_w`.\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()
    out_dir = Path(args.output).resolve()
    ensure_dir(out_dir)
    run_dirs = find_run_dirs()
    index_rows: list[dict[str, str]] = []
    macro_figures(run_dirs, out_dir, index_rows)
    scenario_compare_figures(run_dirs, out_dir, index_rows)
    per_run_figures(run_dirs, out_dir, index_rows)
    write_static_preview(out_dir, index_rows)
    print(f"Wrote {len(index_rows)} gallery figures to {out_dir}")


if __name__ == "__main__":
    main()
