from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PatchCollection
from matplotlib.colors import Normalize
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = (
    WORKSPACE_ROOT
    / "outputs"
    / "final_5x5_10800"
    / "sweet_170_incident_w"
    / "P-STACK-WU-FAITHFUL-APJOINT-FINAL"
)
DEFAULT_OUT_DIR = WORKSPACE_ROOT / "outputs" / "paper_topology_heatmap_preview_20260718"

WINDOW_START_SEC = 3600.0
WINDOW_END_SEC = 10800.0
FREEWAY_LINKS = ("FW_E", "FW_W")
N_SEGMENTS = 8
RAMP_TO_NODE = {
    "R_D_E": "D",
    "R_D_W": "D",
    "R_F_E": "F",
    "R_F_W": "F",
}
RAMP_TO_LINK = {
    "R_D_E": "FW_E",
    "R_F_E": "FW_E",
    "R_D_W": "FW_W",
    "R_F_W": "FW_W",
}
NODE_POS = {
    "A": (1.0, 4.2),
    "B": (4.0, 4.2),
    "C": (7.0, 4.2),
    "D": (1.0, 2.55),
    "E": (4.0, 2.55),
    "F": (7.0, 2.55),
}
URBAN_EDGES = (
    ("A", "B"),
    ("B", "C"),
    ("A", "D"),
    ("B", "E"),
    ("C", "F"),
    ("D", "E"),
    ("E", "F"),
)
FREEWAY_Y = {"FW_E": 1.05, "FW_W": 0.45}
FREEWAY_X0 = 0.35
FREEWAY_X1 = 7.65
SEG_H = 0.36


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def windowed(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "time_sec" not in df.columns:
        return df.iloc[0:0].copy()
    time = numeric(df["time_sec"])
    return df.loc[(time >= WINDOW_START_SEC) & (time <= WINDOW_END_SEC)].copy()


def nearest_row(df: pd.DataFrame, time_sec: float) -> pd.Series:
    if df.empty or "time_sec" not in df.columns:
        return pd.Series(dtype=float)
    idx = (numeric(df["time_sec"]) - float(time_sec)).abs().idxmin()
    return df.loc[idx]


def seg_x(link: str, seg: int) -> tuple[float, float]:
    width = (FREEWAY_X1 - FREEWAY_X0) / N_SEGMENTS
    if link == "FW_E":
        left = FREEWAY_X0 + seg * width
    else:
        # Westbound traffic travels right-to-left; put seg0 at the east/upstream end.
        left = FREEWAY_X0 + (N_SEGMENTS - 1 - seg) * width
    return left, width


def link_center_x(link: str, seg: int) -> float:
    left, width = seg_x(link, seg)
    return left + width / 2.0


def draw_base_topology(ax: plt.Axes) -> None:
    ax.set_xlim(0.0, 8.2)
    ax.set_ylim(-0.2, 5.0)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    for a, b in URBAN_EDGES:
        x1, y1 = NODE_POS[a]
        x2, y2 = NODE_POS[b]
        ax.plot([x1, x2], [y1, y2], color="#b7c0cb", linewidth=2.2, zorder=0)

    for node, (x, y) in NODE_POS.items():
        ax.add_patch(Circle((x, y), 0.145, facecolor="#ffffff", edgecolor="#495260", linewidth=1.5, zorder=3))
        ax.text(x, y + 0.31, node, ha="center", va="center", fontsize=10.5, fontweight="bold", color="#303946")

    for link, y in FREEWAY_Y.items():
        ax.plot([FREEWAY_X0, FREEWAY_X1], [y, y], color="#3f4650", linewidth=1.1, alpha=0.25, zorder=0)
        if link == "FW_E":
            ax.annotate("", xy=(FREEWAY_X1 + 0.15, y), xytext=(FREEWAY_X1 - 0.45, y), arrowprops={"arrowstyle": "->", "lw": 1.5, "color": "#303946"})
            ax.text(FREEWAY_X0 - 0.15, y, "FW_E", ha="right", va="center", fontsize=10.5, fontweight="bold", color="#303946")
        else:
            ax.annotate("", xy=(FREEWAY_X0 - 0.15, y), xytext=(FREEWAY_X0 + 0.45, y), arrowprops={"arrowstyle": "->", "lw": 1.5, "color": "#303946"})
            ax.text(FREEWAY_X1 + 0.15, y, "FW_W", ha="left", va="center", fontsize=10.5, fontweight="bold", color="#303946")

    for ramp, node in RAMP_TO_NODE.items():
        x, y_node = NODE_POS[node]
        y_fw = FREEWAY_Y[RAMP_TO_LINK[ramp]]
        x_fw = x + (0.12 if ramp.endswith("_E") else -0.12)
        arrow = FancyArrowPatch(
            (x, y_node - 0.15),
            (x_fw, y_fw + SEG_H / 2.0 + 0.03),
            arrowstyle="-|>",
            mutation_scale=9,
            linewidth=1.25,
            color="#8c96a3",
            alpha=0.55,
            zorder=2,
        )
        ax.add_patch(arrow)
        ax.text(x_fw, (y_node + y_fw) / 2.0 - 0.05, ramp.replace("R_", ""), ha="center", va="center", fontsize=7.3, color="#657080")


def add_incident_marker(ax: plt.Axes) -> None:
    left, width = seg_x("FW_E", 6)
    y = FREEWAY_Y["FW_E"] - SEG_H / 2.0
    ax.add_patch(Rectangle((left, y), width, SEG_H, fill=False, edgecolor="#d23b3b", linewidth=2.8, zorder=5))
    ax.text(left + width / 2.0, y + SEG_H + 0.18, "closure\nseg6", ha="center", va="bottom", fontsize=7.8, color="#b72d2d", fontweight="bold")


def save(fig: plt.Figure, out_dir: Path, name: str) -> None:
    ensure_dir(out_dir)
    fig.savefig(out_dir / f"{name}.png", dpi=220, bbox_inches="tight")
    fig.savefig(out_dir / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def freeway_segment_values(control: pd.DataFrame, reducer: Callable[[pd.Series], float]) -> dict[tuple[str, int], float]:
    values: dict[tuple[str, int], float] = {}
    for link in FREEWAY_LINKS:
        for seg in range(N_SEGMENTS):
            col = f"vsl_{link}_seg{seg}"
            if col in control.columns:
                values[(link, seg)] = float(reducer(numeric(control[col]).dropna()))
    return values


def draw_vsl_map(values: dict[tuple[str, int], float], out_dir: Path, name: str, title: str, subtitle: str) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.3))
    draw_base_topology(ax)
    patches: list[Rectangle] = []
    colors: list[float] = []
    for link in FREEWAY_LINKS:
        for seg in range(N_SEGMENTS):
            left, width = seg_x(link, seg)
            y = FREEWAY_Y[link] - SEG_H / 2.0
            patches.append(Rectangle((left, y), width * 0.96, SEG_H))
            colors.append(values.get((link, seg), np.nan))
            ax.text(left + width / 2.0, y - 0.13, str(seg), ha="center", va="top", fontsize=7.0, color="#596270")
    collection = PatchCollection(patches, cmap="RdYlGn", norm=Normalize(vmin=50.0, vmax=100.0), edgecolor="#ffffff", linewidth=1.15, zorder=4)
    collection.set_array(np.asarray(colors, dtype=float))
    ax.add_collection(collection)
    add_incident_marker(ax)
    cbar = fig.colorbar(collection, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("VSL command (km/h)")
    ax.text(0.0, 4.88, title, ha="left", va="top", fontsize=16.5, fontweight="bold")
    ax.text(0.0, 4.55, subtitle, ha="left", va="top", fontsize=10.5, color="#5d6672")
    ax.text(8.18, -0.11, "topology heatmap preview", ha="right", va="bottom", fontsize=9.5, color="#8a94a3", fontweight="bold")
    save(fig, out_dir, name)


def ramp_values(control: pd.DataFrame, prefix: str, reducer: Callable[[pd.Series], float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ramp in RAMP_TO_NODE:
        col = f"{prefix}_{ramp}"
        if col in control.columns:
            out[ramp] = float(reducer(numeric(control[col]).dropna()))
    return out


def draw_ramp_map(
    values: dict[str, float],
    out_dir: Path,
    name: str,
    title: str,
    subtitle: str,
    cbar_label: str,
    vmin: float | None = None,
    vmax: float | None = None,
    cmap: str = "viridis",
) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.3))
    draw_base_topology(ax)
    v = np.asarray(list(values.values()), dtype=float)
    if vmin is None:
        vmin = float(np.nanmin(v)) if v.size else 0.0
    if vmax is None:
        vmax = float(np.nanmax(v)) if v.size else 1.0
    if abs(vmax - vmin) < 1.0e-9:
        vmax = vmin + 1.0
    norm = Normalize(vmin=vmin, vmax=vmax)
    cmap_obj = plt.get_cmap(cmap)
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap_obj)

    for ramp, node in RAMP_TO_NODE.items():
        x, y_node = NODE_POS[node]
        y_fw = FREEWAY_Y[RAMP_TO_LINK[ramp]]
        offset = 0.2 if ramp.endswith("_E") else -0.2
        val = values.get(ramp, np.nan)
        color = cmap_obj(norm(val)) if np.isfinite(val) else "#b7c0cb"
        arrow = FancyArrowPatch(
            (x + offset, y_node - 0.22),
            (x + offset, y_fw + SEG_H / 2.0 + 0.03),
            arrowstyle="-|>",
            mutation_scale=16,
            linewidth=4.2,
            color=color,
            alpha=0.95,
            zorder=6,
        )
        ax.add_patch(arrow)
        label = f"{ramp}\n{val:.2g}" if np.isfinite(val) else ramp
        ax.text(x + offset + (0.3 if offset > 0 else -0.3), (y_node + y_fw) / 2.0, label, ha="center", va="center", fontsize=8.0, color="#303946")

    add_incident_marker(ax)
    cbar = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label(cbar_label)
    ax.text(0.0, 4.88, title, ha="left", va="top", fontsize=16.5, fontweight="bold")
    ax.text(0.0, 4.55, subtitle, ha="left", va="top", fontsize=10.5, color="#5d6672")
    ax.text(8.18, -0.11, "topology heatmap preview", ha="right", va="bottom", fontsize=9.5, color="#8a94a3", fontweight="bold")
    save(fig, out_dir, name)


def draw_signal_price_map(control: pd.DataFrame, out_dir: Path) -> None:
    win = windowed(control)
    fig, ax = plt.subplots(figsize=(9.5, 5.3))
    draw_base_topology(ax)
    nodes = ("A", "B", "C", "D", "F")
    values = {}
    for node in nodes:
        col = f"diag_wu_b2_price_{node}"
        if col in win.columns:
            values[node] = float(np.nanmean(np.abs(numeric(win[col]))))
    vals = np.asarray(list(values.values()), dtype=float)
    vmax = float(np.nanmax(vals)) if vals.size else 1.0
    if vmax < 1.0e-9:
        vmax = 1.0
    norm = Normalize(vmin=0.0, vmax=vmax)
    cmap = plt.get_cmap("magma")
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    for node in nodes:
        x, y = NODE_POS[node]
        val = values.get(node, np.nan)
        color = cmap(norm(val)) if np.isfinite(val) else "#ffffff"
        ax.add_patch(Circle((x, y), 0.24, facecolor=color, edgecolor="#ffffff", linewidth=1.8, zorder=6))
        ax.text(x, y, node, ha="center", va="center", fontsize=10.5, fontweight="bold", color="#ffffff" if np.isfinite(val) and norm(val) > 0.45 else "#303946", zorder=7)
        if np.isfinite(val):
            ax.text(x, y - 0.39, f"{val:.2f}", ha="center", va="top", fontsize=8.0, color="#303946")
    add_incident_marker(ax)
    cbar = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("|green price|, window mean")
    ax.text(0.0, 4.88, "Signal Price Topology", ha="left", va="top", fontsize=16.5, fontweight="bold")
    ax.text(0.0, 4.55, "Incident 170 / P-Stack; mean |green price| in the analysis window.", ha="left", va="top", fontsize=10.5, color="#5d6672")
    ax.text(8.18, -0.11, "topology heatmap preview", ha="right", va="bottom", fontsize=9.5, color="#8a94a3", fontweight="bold")
    save(fig, out_dir, "topology_incident170_pstack_signal_green_price_mean_abs")


def make_figures(run_dir: Path, out_dir: Path) -> None:
    control = read_csv(run_dir / "control_timeseries.csv")
    if control.empty:
        raise FileNotFoundError(f"Missing or empty control_timeseries.csv under {run_dir}")
    win = windowed(control)

    mean_values = freeway_segment_values(win, lambda s: float(np.nanmean(s)))
    min_values = freeway_segment_values(win, lambda s: float(np.nanmin(s)))
    draw_vsl_map(
        mean_values,
        out_dir,
        "topology_incident170_pstack_vsl_window_mean",
        "VSL Topology Map",
        "Incident 170 / P-Stack; mean VSL in the analysis window.",
    )
    draw_vsl_map(
        min_values,
        out_dir,
        "topology_incident170_pstack_vsl_window_min",
        "VSL Activation Map",
        "Incident 170 / P-Stack; most restrictive VSL in the analysis window.",
    )
    for t in (3600.0, 5400.0, 7200.0, 9000.0):
        row = nearest_row(control, t)
        values = {}
        for link in FREEWAY_LINKS:
            for seg in range(N_SEGMENTS):
                col = f"vsl_{link}_seg{seg}"
                if col in row.index:
                    values[(link, seg)] = float(row[col])
        draw_vsl_map(
            values,
            out_dir,
            f"topology_incident170_pstack_vsl_snapshot_t{int(t)}",
            f"VSL Snapshot t={int(t)} s",
            "Incident 170 / P-Stack; FW_E seg6 closure marker.",
        )

    metering = ramp_values(win, "ramp_metering", lambda s: float(np.nanmean(s)))
    if metering:
        draw_ramp_map(
            metering,
            out_dir,
            "topology_incident170_pstack_ramp_metering_mean",
            "Ramp Metering Topology",
            "Incident 170 / P-Stack; mean metering command in the analysis window.",
            "metering flow (veh/h)",
            vmin=0.0,
            vmax=max(1500.0, max(metering.values())),
            cmap="YlGnBu",
        )

    meter_price = ramp_values(win, "diag_wu_b3_meter_price", lambda s: float(np.nanmean(np.abs(s))))
    if meter_price:
        draw_ramp_map(
            meter_price,
            out_dir,
            "topology_incident170_pstack_meter_price_mean_abs",
            "Metering Price Topology",
            "Incident 170 / P-Stack; mean |metering price| in the analysis window.",
            "|metering price|, window mean",
            vmin=0.0,
            vmax=max(meter_price.values()),
            cmap="magma",
        )

    draw_signal_price_map(control, out_dir)

    readme = out_dir / "README.md"
    readme.write_text(
        "# Topology Heatmap Preview\n\n"
        "Network-topology alternatives to matrix heatmaps. These are design previews, not final paper numbers.\n\n"
        "- Freeway VSL maps color the two 8-segment freeway links directly on the network.\n"
        "- FW_E is drawn left-to-right; FW_W is drawn right-to-left so segment order follows travel direction.\n"
        "- The incident marker is FW_E seg6, matching `sweet_170_incident_w`.\n"
        "- Ramp maps use arrow colors for metering command or metering-price magnitude.\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    make_figures(args.run_dir, args.out_dir)
    print(f"Wrote topology heatmap previews to {args.out_dir}")


if __name__ == "__main__":
    main()
