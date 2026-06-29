from __future__ import annotations

import json
import warnings
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Rectangle
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


ROOT = Path(__file__).resolve().parents[2]
DESKTOP_ROOT = Path(r"C:\Users\alsrj\Desktop\Numerical-Sim")
D1 = DESKTOP_ROOT / "outputs" / "analysis_matrix_3600"
D2 = DESKTOP_ROOT / "outputs" / "analysis_matrix_3600_extra"
OUT = ROOT / "reports" / "figures" / "effect_oriented_2026_06_23"

DT_SEC = 180.0
DT_H = DT_SEC / 3600.0

SCENARIOS = [
    {"id": "medium_demand", "label": "Median", "root": D1},
    {"id": "peak_demand", "label": "Peak", "root": D1},
    {"id": "skew_peak", "label": "Peak skew", "root": D2},
    {"id": "incident_or_capacity_drop", "label": "Incident", "root": D1},
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

CTRL_COLOR = {
    "NO-CONTROL": "#4D4D4D",
    "WU-CD-F": "#1F77B4",
    "PROPOSED-FOLLOWERS-ONLY": "#2CA02C",
    "PROPOSED-STACKELBERG": "#D62728",
}

SCENARIO_LABEL = {s["id"]: s["label"] for s in SCENARIOS}
SCENARIO_ROOT = {s["id"]: s["root"] for s in SCENARIOS}

# Frozen demand definitions used by the 2026-06-23, 3600 s analysis runs.
DEMAND_SCENARIOS = {
    "medium_demand": {"urban_scale": 1.0, "freeway_scale": 1.0, "ramp_scale": 1.0},
    "peak_demand": {"urban_scale": 1.25, "freeway_scale": 1.20, "ramp_scale": 1.25},
    "skew_peak": {
        "urban_scale": 1.25,
        "freeway_scale": 1.20,
        "ramp_scale": 1.25,
        "urban_weights": {
            "in_C_top": 2.5,
            "in_C_right": 2.5,
            "in_F_right": 2.5,
        },
    },
    "incident_or_capacity_drop": {
        "urban_scale": 1.20,
        "freeway_scale": 1.15,
        "ramp_scale": 1.25,
        "incident_capacity_factor": 0.72,
    },
}

BOUNDARY_IN_LINKS = [
    "in_A_top",
    "in_A_left",
    "in_B_top",
    "in_C_top",
    "in_C_right",
    "in_D_left",
    "in_F_right",
]


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


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    for col in df.columns:
        if col not in ("scenario", "controller_id", "event", "stage"):
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().any():
                df[col] = converted
    return df


def run_dir(scenario: str, controller: str) -> Path:
    return SCENARIO_ROOT[scenario] / "runs" / scenario / controller


def load_file(name: str) -> pd.DataFrame:
    frames = []
    for s in SCENARIO_LABEL:
        for c in CONTROLLERS:
            df = read_csv(run_dir(s, c) / name)
            if df.empty:
                continue
            df["scenario"] = s
            df["scenario_label"] = SCENARIO_LABEL[s]
            df["controller_id"] = c
            df["controller_label"] = CTRL_LABEL[c]
            if "time_sec" not in df and "step" in df:
                df["time_sec"] = pd.to_numeric(df["step"], errors="coerce") * DT_SEC
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


def add_top_legend(fig: plt.Figure, axes, ncol: int = 4, y: float = 1.03) -> None:
    ax0 = np.ravel(axes)[0]
    handles, labels = ax0.get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, ncol=ncol, loc="upper center", bbox_to_anchor=(0.5, y), frameon=True)


def mean_cols(df: pd.DataFrame, prefix: str) -> pd.Series:
    cols = [c for c in df.columns if c.startswith(prefix)]
    if not cols:
        return pd.Series(np.nan, index=df.index)
    return df[cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)


def sum_cols(df: pd.DataFrame, prefix: str) -> pd.Series:
    cols = [c for c in df.columns if c.startswith(prefix)]
    if not cols:
        return pd.Series(0.0, index=df.index)
    return df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)


def demand_snapshot(
    scenario: str,
    time_sec: float = 1800.0,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    spec = DEMAND_SCENARIOS[scenario]
    peak = 1.0 + 0.22 * np.sin(np.pi * np.clip(time_sec / 3600.0, 0.0, 1.0))
    urban_base = 500.0 * spec["urban_scale"] * peak
    urban = {
        link: urban_base * (1.0 + 0.10 * idx)
        for idx, link in enumerate(BOUNDARY_IN_LINKS)
    }
    weights = spec.get("urban_weights", {})
    if weights:
        weighted = {link: value * float(weights.get(link, 1.0)) for link, value in urban.items()}
        renorm = sum(urban.values()) / max(sum(weighted.values()), 1.0e-9)
        urban = {link: value * renorm for link, value in weighted.items()}

    freeway_base = 1650.0 * spec["freeway_scale"] * peak
    freeway = {"FW_W": freeway_base, "FW_E": freeway_base * 1.05}
    ramp_base = 560.0 * spec["ramp_scale"] * peak
    ramps = {
        ramp: ramp_base * (1.0 + 0.05 * idx)
        for idx, ramp in enumerate(["R_D_W", "R_F_W", "R_D_E", "R_F_E"])
    }
    return urban, freeway, ramps


def _draw_arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color: str,
    width: float = 1.4,
    mutation_scale: float = 11.0,
    linestyle: str = "-",
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=mutation_scale,
            linewidth=width,
            linestyle=linestyle,
            color=color,
            shrinkA=0,
            shrinkB=0,
        )
    )


def _draw_topology_demand_panel(ax: plt.Axes, scenario: str) -> None:
    urban, freeway, ramps = demand_snapshot(scenario)
    nodes = {
        "A": (0.0, 2.0),
        "B": (2.0, 2.0),
        "C": (4.0, 2.0),
        "D": (0.0, 0.0),
        "E": (2.0, 0.0),
        "F": (4.0, 0.0),
    }
    edges = [
        ("A", "B"),
        ("B", "C"),
        ("A", "D"),
        ("B", "E"),
        ("C", "F"),
        ("D", "E"),
        ("E", "F"),
    ]
    for left, right in edges:
        x1, y1 = nodes[left]
        x2, y2 = nodes[right]
        ax.plot(
            [x1, x2],
            [y1, y2],
            color="#AEB4BE",
            linewidth=4.0,
            solid_capstyle="round",
            zorder=1,
        )

    for node, (x, y) in nodes.items():
        face = "#F2F3F5" if node == "E" else "#FFFFFF"
        ax.add_patch(
            Rectangle(
                (x - 0.22, y - 0.22),
                0.44,
                0.44,
                facecolor=face,
                edgecolor="#30343B",
                linewidth=1.2,
                zorder=3,
            )
        )
        ax.text(x, y, node, ha="center", va="center", fontsize=9, fontweight="bold", zorder=4)

    freeway_color = "#5477C4"
    boundary_color = "#CC6F47"
    _draw_arrow(ax, (-1.25, -1.65), (5.15, -1.65), color="#8A929E", width=3.0, mutation_scale=13)
    _draw_arrow(ax, (5.15, -2.25), (-1.25, -2.25), color="#8A929E", width=3.0, mutation_scale=13)
    ax.text(2.0, -1.48, "FW_E", ha="center", va="bottom", color="#4C5360", fontsize=8)
    ax.text(2.0, -2.42, "FW_W", ha="center", va="top", color="#4C5360", fontsize=8)
    ax.text(
        -1.23,
        -1.42,
        f"{freeway['FW_E']:,.0f}",
        ha="left",
        va="bottom",
        color=freeway_color,
        fontsize=8,
        fontweight="bold",
    )
    ax.text(
        5.13,
        -2.02,
        f"{freeway['FW_W']:,.0f}",
        ha="right",
        va="bottom",
        color=freeway_color,
        fontsize=8,
        fontweight="bold",
    )

    # Show the physical interfaces without treating the on-ramps as exogenous origins.
    for node_x in (0.0, 4.0):
        ax.plot([node_x, node_x - 0.25], [-0.22, -1.65], color="#B8BDC6", linewidth=1.1, linestyle="--")
        ax.plot([node_x, node_x + 0.25], [-0.22, -2.25], color="#B8BDC6", linewidth=1.1, linestyle="--")
    ramp_label_style = {
        "ha": "center",
        "va": "top",
        "fontsize": 7.2,
        "color": "#736422",
        "bbox": {
            "boxstyle": "round,pad=0.24",
            "facecolor": "#FFF4C2",
            "edgecolor": "#B8A037",
            "linewidth": 0.8,
        },
    }
    ax.text(
        0.0,
        -0.43,
        f"Ramp-bound at D\nW {ramps['R_D_W']:,.0f} | E {ramps['R_D_E']:,.0f}",
        **ramp_label_style,
    )
    ax.text(
        4.0,
        -0.43,
        f"Ramp-bound at F\nW {ramps['R_F_W']:,.0f} | E {ramps['R_F_E']:,.0f}",
        **ramp_label_style,
    )

    boundary_arrows = {
        "in_A_top": ((0.0, 3.05), (0.0, 2.28), (0.0, 3.12), "center", "bottom"),
        "in_A_left": ((-1.15, 2.0), (-0.28, 2.0), (-1.18, 2.16), "left", "bottom"),
        "in_B_top": ((2.0, 3.05), (2.0, 2.28), (2.0, 3.12), "center", "bottom"),
        "in_C_top": ((4.0, 3.05), (4.0, 2.28), (4.0, 3.12), "center", "bottom"),
        "in_C_right": ((5.15, 2.0), (4.28, 2.0), (5.18, 2.16), "right", "bottom"),
        "in_D_left": ((-1.15, 0.0), (-0.28, 0.0), (-1.18, 0.16), "left", "bottom"),
        "in_F_right": ((5.15, 0.0), (4.28, 0.0), (5.18, 0.16), "right", "bottom"),
    }
    for link, (start, end, label_xy, ha, va) in boundary_arrows.items():
        _draw_arrow(ax, start, end, color=boundary_color)
        ax.text(
            *label_xy,
            f"{urban[link]:,.0f}",
            ha=ha,
            va=va,
            color="#804126",
            fontsize=8,
            fontweight="bold",
        )

    label = SCENARIO_LABEL[scenario]
    if scenario == "incident_or_capacity_drop":
        label += " (capacity factor 0.72)"
    ax.set_title(label, fontsize=11, fontweight="bold", pad=8)
    ax.set_xlim(-1.55, 5.55)
    ax.set_ylim(-2.7, 3.45)
    ax.set_aspect("equal")
    ax.axis("off")


def plot_topology_demand_maps(manifest: list[dict[str, str]]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 8.7))
    for ax, scenario in zip(
        axes.ravel(),
        ["medium_demand", "peak_demand", "skew_peak", "incident_or_capacity_drop"],
    ):
        _draw_topology_demand_panel(ax, scenario)
    fig.suptitle("Scenario Directional Demand on the Mixed-Network Topology", fontsize=15, y=0.985)
    fig.text(
        0.5,
        0.952,
        "Peak-rate snapshot at t = 1800 s; labels show boundary, ramp-bound, and upstream-freeway demand (veh/h). Ramp-bound demand is placed at D/F rather than on the ramp links.",
        ha="center",
        va="top",
        fontsize=9,
        color="#5C6370",
    )
    fig.text(
        0.5,
        0.018,
        "Orange: urban boundary entry  |  Gold boxes: ramp-bound demand near D/F  |  Blue: upstream freeway entry.",
        ha="center",
        va="bottom",
        fontsize=8.5,
        color="#5C6370",
    )
    fig.subplots_adjust(top=0.90, bottom=0.06, hspace=0.13, wspace=0.08)
    save(fig, OUT / "00_scenario_demand" / "Scenario_topology_directional_demand", manifest)


def scenario_controller(df: pd.DataFrame, scenario: str, controller: str) -> pd.DataFrame:
    sub = df[(df["scenario"] == scenario) & (df["controller_id"] == controller)].copy()
    return sub.sort_values("time_sec" if "time_sec" in sub else "step")


def no_control_series(progress: pd.DataFrame, scenario: str, col: str) -> pd.Series:
    nc = scenario_controller(progress, scenario, "NO-CONTROL")
    if nc.empty or col not in nc:
        return pd.Series(dtype=float)
    return nc.set_index("step")[col]


def plot_effect_chain(
    scenario: str,
    runlog: pd.DataFrame,
    progress: pd.DataFrame,
    controls: pd.DataFrame,
    states: pd.DataFrame,
    manifest: list[dict[str, str]],
) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(8.6, 8.0), sharex=True)
    nc_cum = no_control_series(progress, scenario, "cumulative_total_ttt")
    nc_terminal = no_control_series(progress, scenario, "terminal_total_vehicles")

    for ctrl in CONTROLLERS:
        r = scenario_controller(runlog, scenario, ctrl)
        p = scenario_controller(progress, scenario, ctrl)
        c = scenario_controller(controls, scenario, ctrl)
        if r.empty or p.empty:
            continue
        t = r["time_sec"] / 60.0
        axes[0].plot(t, r.get("total_metering_flow", pd.Series(np.nan, index=r.index)), color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        axes[1].plot(t, r.get("ramp_queue_veh", pd.Series(np.nan, index=r.index)), color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        if "step" in p:
            pp = p.set_index("step")
            saving = nc_cum.reindex(pp.index) - pp["cumulative_total_ttt"]
            terminal_avoided = nc_terminal.reindex(pp.index) - pp["terminal_total_vehicles"]
            axes[2].plot(pp["time_sec"] / 60.0, saving, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
            axes[3].plot(pp["time_sec"] / 60.0, terminal_avoided, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        if ctrl != "NO-CONTROL" and not c.empty:
            vsl = mean_cols(c, "vsl_")
            if vsl.notna().any() and scenario == "incident_or_capacity_drop":
                # Show VSL activation as light vertical markers only in the incident case.
                active_t = c.loc[vsl < 99.0, "time_sec"] / 60.0
                for x in active_t:
                    axes[2].axvline(x, color=CTRL_COLOR[ctrl], alpha=0.08, linewidth=1.0)

    axes[0].set_ylabel("Ramp release /\nmetering flow\n(veh/h)")
    axes[1].set_ylabel("Ramp queue\n(veh)")
    axes[2].set_ylabel("Cumulative TTT\nsaved (veh-h)")
    axes[3].set_ylabel("Terminal vehicles\navoided")
    axes[3].set_xlabel("Time (min)")
    add_top_legend(fig, axes, ncol=4, y=1.02)
    fig.subplots_adjust(top=0.90)
    fig.suptitle(f"Effect Chain: RM/Queue to Network Outcome ({SCENARIO_LABEL[scenario]})")
    save(fig, OUT / "01_time_aligned_effects" / f"EffectChain_RM_queue_TTT_{scenario}", manifest)


def plot_vsl_speed_effect(
    scenario: str,
    controls: pd.DataFrame,
    states: pd.DataFrame,
    progress: pd.DataFrame,
    manifest: list[dict[str, str]],
) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(8.6, 8.0), sharex=True)
    nc_cum = no_control_series(progress, scenario, "cumulative_freeway_ttt")

    for ctrl in CONTROLLERS:
        c = scenario_controller(controls, scenario, ctrl)
        s = scenario_controller(states, scenario, ctrl)
        p = scenario_controller(progress, scenario, ctrl)
        if s.empty:
            continue
        t = s["time_sec"] / 60.0
        vsl = mean_cols(c, "vsl_") if not c.empty else pd.Series(np.nan, index=s.index)
        speed = mean_cols(s, "speed_")
        rho = mean_cols(s, "rho_")
        axes[0].plot(c["time_sec"] / 60.0 if not c.empty else t, vsl, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        axes[1].plot(t, speed, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        axes[2].plot(t, rho, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        if not p.empty:
            pp = p.set_index("step")
            saving = nc_cum.reindex(pp.index) - pp["cumulative_freeway_ttt"]
            axes[3].plot(pp["time_sec"] / 60.0, saving, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])

    axes[0].set_ylabel("Mean VSL\n(km/h)")
    axes[1].set_ylabel("Mean freeway\nspeed")
    axes[2].set_ylabel("Mean freeway\nrho")
    axes[3].set_ylabel("Freeway TTT\nsaved (veh-h)")
    axes[3].set_xlabel("Time (min)")
    add_top_legend(fig, axes, ncol=4, y=1.02)
    fig.subplots_adjust(top=0.90)
    fig.suptitle(f"Effect Chain: VSL to Speed/Density/Freeway TTT ({SCENARIO_LABEL[scenario]})")
    save(fig, OUT / "01_time_aligned_effects" / f"EffectChain_VSL_speed_density_{scenario}", manifest)


def plot_vsl_rm_speed_effect(
    scenario: str,
    runlog: pd.DataFrame,
    controls: pd.DataFrame,
    states: pd.DataFrame,
    progress: pd.DataFrame,
    manifest: list[dict[str, str]],
) -> None:
    fig = plt.figure(figsize=(9.6, 10.2))
    grid = fig.add_gridspec(6, 2, height_ratios=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    ax_vsl = fig.add_subplot(grid[0, :])
    ax_rm_up = fig.add_subplot(grid[1, 0], sharex=ax_vsl)
    ax_rm_down = fig.add_subplot(grid[1, 1], sharex=ax_vsl)
    ax_queue_up = fig.add_subplot(grid[2, 0], sharex=ax_vsl)
    ax_queue_down = fig.add_subplot(grid[2, 1], sharex=ax_vsl)
    ax_speed = fig.add_subplot(grid[3, :], sharex=ax_vsl)
    ax_rho = fig.add_subplot(grid[4, :], sharex=ax_vsl)
    ax_ttt = fig.add_subplot(grid[5, :], sharex=ax_vsl)
    axes = [
        ax_vsl,
        ax_rm_up,
        ax_rm_down,
        ax_queue_up,
        ax_queue_down,
        ax_speed,
        ax_rho,
        ax_ttt,
    ]
    nc_cum = no_control_series(progress, scenario, "cumulative_freeway_ttt")

    for ctrl in CONTROLLERS:
        c = scenario_controller(controls, scenario, ctrl)
        s = scenario_controller(states, scenario, ctrl)
        p = scenario_controller(progress, scenario, ctrl)
        if s.empty:
            continue

        t_state = s["time_sec"] / 60.0
        if c.empty:
            t_control = t_state
            vsl = pd.Series(100.0, index=s.index)
            rm_up = pd.Series(np.nan, index=s.index)
            rm_down = pd.Series(np.nan, index=s.index)
        else:
            t_control = c["time_sec"] / 60.0
            vsl = c.get("vsl_FW_E", mean_cols(c, "vsl_FW_E"))
            if not vsl.notna().any():
                vsl = pd.Series(100.0, index=c.index)
            rm_up = c.get("ramp_metering_R_D_E", pd.Series(np.nan, index=c.index))
            rm_down = c.get("ramp_metering_R_F_E", pd.Series(np.nan, index=c.index))

        ax_vsl.plot(t_control, vsl, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        ax_rm_up.plot(t_control, rm_up, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        ax_rm_down.plot(t_control, rm_down, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        ax_queue_up.plot(
            t_state,
            s.get("ramp_queue_R_D_E", pd.Series(np.nan, index=s.index)),
            color=CTRL_COLOR[ctrl],
            label=CTRL_LABEL[ctrl],
        )
        ax_queue_down.plot(
            t_state,
            s.get("ramp_queue_R_F_E", pd.Series(np.nan, index=s.index)),
            color=CTRL_COLOR[ctrl],
            label=CTRL_LABEL[ctrl],
        )
        ax_speed.plot(
            t_state,
            s.get("speed_FW_E_mean", mean_cols(s, "speed_FW_E")),
            color=CTRL_COLOR[ctrl],
            label=CTRL_LABEL[ctrl],
        )
        ax_rho.plot(
            t_state,
            s.get("rho_FW_E_mean", mean_cols(s, "rho_FW_E")),
            color=CTRL_COLOR[ctrl],
            label=CTRL_LABEL[ctrl],
        )

        if not p.empty and "step" in p:
            pp = p.set_index("step")
            saving = nc_cum.reindex(pp.index) - pp["cumulative_freeway_ttt"]
            ax_ttt.plot(pp["time_sec"] / 60.0, saving, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])

    ax_vsl.set_ylabel("Eastbound VSL\n(km/h)")
    ax_rm_up.set_title("Upstream ramp: D -> FW_E")
    ax_rm_down.set_title("Downstream ramp: F -> FW_E")
    ax_rm_up.set_ylabel("RM command\n(veh/h)")
    ax_rm_down.set_ylabel("RM command\n(veh/h)")
    ax_queue_up.set_ylabel("Ramp queue\n(veh)")
    ax_queue_down.set_ylabel("Ramp queue\n(veh)")
    ax_speed.set_ylabel("FW_E mean\nspeed (km/h)")
    ax_rho.set_ylabel("FW_E mean\nrho")
    ax_ttt.set_ylabel("Freeway TTT\nsaved (veh-h)")
    ax_ttt.set_xlabel("Time (min)")
    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)
    add_top_legend(fig, axes, ncol=4, y=1.012)
    fig.subplots_adjust(top=0.91, hspace=0.28, wspace=0.24)
    fig.suptitle(f"Effect Chain: Directional VSL + RM to Freeway State/TTT ({SCENARIO_LABEL[scenario]})")
    save(fig, OUT / "01_time_aligned_effects" / f"EffectChain_VSL_RM_speed_density_{scenario}", manifest)


def plot_fd_shift(scenario: str, states: pd.DataFrame, manifest: list[dict[str, str]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2), sharey=True)
    directions = [("FW_E", "Eastbound"), ("FW_W", "Westbound")]
    for ax, (key, title) in zip(axes, directions):
        for ctrl in CONTROLLERS:
            s = scenario_controller(states, scenario, ctrl)
            if s.empty:
                continue
            rho_col = f"rho_{key}_mean"
            flow_col = f"flow_{key}_mean"
            if rho_col not in s or flow_col not in s:
                continue
            ax.plot(
                s[rho_col],
                s[flow_col],
                marker="o",
                markersize=3.0,
                linewidth=1.0,
                color=CTRL_COLOR[ctrl],
                label=CTRL_LABEL[ctrl],
                alpha=0.85,
            )
            ax.scatter(s[rho_col].iloc[-1], s[flow_col].iloc[-1], color=CTRL_COLOR[ctrl], marker="x", s=45)
        ax.set_title(title)
        ax.set_xlabel("Mean density rho")
    axes[0].set_ylabel("Mean flow")
    add_top_legend(fig, axes, ncol=4, y=1.05)
    fig.subplots_adjust(top=0.82)
    fig.suptitle(f"Freeway FD Operating-Point Shift ({SCENARIO_LABEL[scenario]})")
    save(fig, OUT / "02_operating_point_shift" / f"FD_operating_point_shift_{scenario}", manifest)


def plot_urban_mfd_shift(scenario: str, runlog: pd.DataFrame, manifest: list[dict[str, str]]) -> None:
    fig, ax = plt.subplots(figsize=(6.8, 4.8))
    for ctrl in CONTROLLERS:
        r = scenario_controller(runlog, scenario, ctrl)
        if r.empty or "urban_accumulation_veh" not in r or "urban_total_departures_veh" not in r:
            continue
        ax.plot(
            r["urban_accumulation_veh"],
            r["urban_total_departures_veh"] / DT_H,
            marker="o",
            markersize=3.5,
            linewidth=1.0,
            color=CTRL_COLOR[ctrl],
            label=CTRL_LABEL[ctrl],
            alpha=0.85,
        )
        ax.scatter(
            r["urban_accumulation_veh"].iloc[-1],
            (r["urban_total_departures_veh"] / DT_H).iloc[-1],
            color=CTRL_COLOR[ctrl],
            marker="x",
            s=45,
        )
    ax.set_xlabel("Urban accumulation (veh)")
    ax.set_ylabel("Urban production proxy (veh/h)")
    ax.set_title(f"Urban MFD Operating-Point Shift ({SCENARIO_LABEL[scenario]})")
    ax.legend(ncol=2, frameon=True)
    save(fig, OUT / "02_operating_point_shift" / f"Urban_MFD_operating_point_shift_{scenario}", manifest)


def plot_signal_queue_service_effect(
    scenario: str,
    runlog: pd.DataFrame,
    controls: pd.DataFrame,
    states: pd.DataFrame,
    manifest: list[dict[str, str]],
) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(8.6, 8.0), sharex=True)
    for ctrl in CONTROLLERS:
        r = scenario_controller(runlog, scenario, ctrl)
        c = scenario_controller(controls, scenario, ctrl)
        s = scenario_controller(states, scenario, ctrl)
        if r.empty:
            continue
        t = r["time_sec"] / 60.0
        if not c.empty:
            green_cols = [col for col in c.columns if col.startswith("green_")]
            green = (
                c[green_cols].apply(pd.to_numeric, errors="coerce").sub(56.0).abs().mean(axis=1)
                if green_cols
                else pd.Series(np.nan, index=c.index)
            )
            offset_cols = [col for col in c.columns if col.startswith("offset_")]
            offset_change = (
                c[offset_cols].apply(pd.to_numeric, errors="coerce").diff().abs().mean(axis=1)
                if offset_cols
                else pd.Series(np.nan, index=c.index)
            )
            ct = c["time_sec"] / 60.0
        else:
            green = pd.Series(np.nan, index=r.index)
            offset_change = pd.Series(np.nan, index=r.index)
            ct = t
        movement_queue = (
            sum_cols(s, "movement_queue_")
            if not s.empty and any(col.startswith("movement_queue_") for col in s.columns)
            else r.get("movement_queue_projection_veh", pd.Series(np.nan, index=r.index))
        )
        mt = s["time_sec"] / 60.0 if not s.empty and "time_sec" in s else t
        axes[0].plot(ct, green, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        axes[1].plot(c["time_sec"] / 60.0 if not c.empty else t, offset_change, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        axes[2].plot(t, r.get("urban_total_departures_veh", pd.Series(np.nan, index=r.index)) / DT_H, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        axes[3].plot(mt, movement_queue, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
    axes[0].set_ylabel("Mean |green\n- fixed| (s)")
    axes[1].set_ylabel("Mean offset\nchange (s)")
    axes[2].set_ylabel("Urban departures\n(veh/h)")
    axes[3].set_ylabel("Movement queue\nproxy (veh)")
    axes[3].set_xlabel("Time (min)")
    add_top_legend(fig, axes, ncol=4, y=1.02)
    fig.subplots_adjust(top=0.90)
    fig.suptitle(f"Effect Chain: Signal/Offset to Urban Service ({SCENARIO_LABEL[scenario]})")
    save(fig, OUT / "01_time_aligned_effects" / f"EffectChain_signal_service_queue_{scenario}", manifest)


def plot_candidate_surface(scenario: str, manifest: list[dict[str, str]]) -> None:
    p = run_dir(scenario, "PROPOSED-STACKELBERG") / "decision_progress.csv"
    df = read_csv(p)
    if df.empty:
        manifest.append({"status": "skipped", "figure": "LeaderCandidateObjective", "scenario": scenario, "reason": "decision_progress.csv missing"})
        return
    df = df[pd.to_numeric(df.get("objective", np.nan), errors="coerce").notna()].copy()
    if df.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.2))
    sc = axes[0].scatter(df["N_P_star"], df["N_UF_star"], c=df["objective"], cmap="viridis_r", s=30)
    axes[0].set_xlabel(r"$N_P^*$")
    axes[0].set_ylabel(r"$N_{UF}^*$")
    axes[0].set_title("Candidate objective")
    fig.colorbar(sc, ax=axes[0], label="Objective")
    for step, sdf in df.groupby("step"):
        best = sdf.loc[sdf["objective"].idxmin()]
        axes[1].scatter(step, best["objective"], color="#D62728", s=25)
    axes[1].set_xlabel("Control step")
    axes[1].set_ylabel("Best logged candidate objective")
    axes[1].set_title("Best objective over time")
    fig.suptitle(f"Leader Candidate Objective Surface ({SCENARIO_LABEL[scenario]})")
    save(fig, OUT / "03_leader_candidate_effect" / f"Leader_candidate_objective_surface_{scenario}", manifest)


def plot_effect_summary(summary: pd.DataFrame, manifest: list[dict[str, str]]) -> None:
    if summary.empty:
        return
    scenarios = [s["id"] for s in SCENARIOS]
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.8))
    metrics = [
        ("completed_vehicles", "Completed vehicles (veh; higher is better)", 1.0),
        ("terminal_total_vehicles", "Terminal vehicles (veh; lower is better)", 1.0),
    ]
    ctrls = CONTROLLERS
    width = 0.80 / len(ctrls)
    x = np.arange(len(scenarios))
    for ax, (metric, ylabel, sign) in zip(axes, metrics):
        for i, ctrl in enumerate(ctrls):
            vals = []
            for s in scenarios:
                row = summary[(summary["scenario"] == s) & (summary["controller_id"] == ctrl)]
                vals.append(sign * float(row[metric].iloc[0]) if not row.empty and metric in row else np.nan)
            offset = (i - (len(ctrls) - 1) / 2) * width
            ax.bar(x + offset, vals, width, color=CTRL_COLOR[ctrl], label=CTRL_LABEL[ctrl])
        ax.set_xticks(x)
        ax.set_xticklabels([SCENARIO_LABEL[s] for s in scenarios], rotation=25, ha="right")
        ax.set_ylabel(ylabel)
    add_top_legend(fig, axes, ncol=4, y=0.99)
    fig.subplots_adjust(top=0.84)
    save(fig, OUT / "04_network_effect_summary" / "Network_effect_summary", manifest)


def plot_computation_time_per_step(
    summary: pd.DataFrame,
    manifest: list[dict[str, str]],
) -> None:
    if summary.empty:
        return
    scenarios = [s["id"] for s in SCENARIOS]
    ctrls = ["WU-CD-F", "PROPOSED-FOLLOWERS-ONLY", "PROPOSED-STACKELBERG"]
    n_steps = 3600.0 / DT_SEC
    reference_sec = DT_SEC
    x = np.arange(len(scenarios))
    width = 0.78 / len(ctrls)

    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    for i, ctrl in enumerate(ctrls):
        values = []
        for scenario in scenarios:
            row = summary[
                (summary["scenario"] == scenario)
                & (summary["controller_id"] == ctrl)
            ]
            value = (
                float(row["computation_time_sec"].iloc[0]) / n_steps
                if not row.empty and "computation_time_sec" in row
                else np.nan
            )
            values.append(value)
        offset = (i - (len(ctrls) - 1) / 2) * width
        bars = ax.bar(
            x + offset,
            values,
            width,
            color=CTRL_COLOR[ctrl],
            edgecolor=CTRL_COLOR[ctrl],
            label=CTRL_LABEL[ctrl],
        )
        for bar, value in zip(bars, values):
            if not np.isfinite(value):
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 2.0,
                f"{value:.1f}",
                ha="center",
                va="bottom",
                fontsize=8.5,
            )

    ax.axhline(reference_sec, color="#4D4D4D", linestyle="--", linewidth=1.4)
    ax.text(
        len(scenarios) - 0.55,
        reference_sec + 3.0,
        "Control interval = 180 s",
        ha="right",
        va="bottom",
        fontsize=9,
        color="#4D4D4D",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABEL[s] for s in scenarios], rotation=22, ha="right")
    ax.set_ylabel("Mean computation time per step (s)")
    ax.set_ylim(0.0, 205.0)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.11), ncol=3, frameon=True)
    fig.subplots_adjust(top=0.84, bottom=0.18)
    save(
        fig,
        OUT / "05_computation_time" / "Computation_time_per_step",
        manifest,
    )


def load_summary() -> pd.DataFrame:
    frames = []
    for root in sorted({D1, D2}):
        f = root / "analysis" / "summary_with_no_control.csv"
        if f.exists():
            frames.append(read_csv(f))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return df[df["scenario"].isin(SCENARIO_LABEL) & df["controller_id"].isin(CONTROLLERS)].copy()


def write_manifest(manifest: list[dict[str, str]]) -> None:
    payload = {
        "purpose": "Effect-oriented figures inspired by control literature: control input, state response, operating-point shift, and network outcome are plotted together.",
        "source_raw": [str(D1.resolve()), str(D2.resolve())],
        "controllers": CONTROLLERS,
        "scenarios": [
            {"id": s["id"], "label": s["label"], "root": str(s["root"].resolve())}
            for s in SCENARIOS
        ],
        "generated_count": sum(1 for item in manifest if item.get("status") == "generated"),
        "figures": manifest,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    setup_style()
    manifest: list[dict[str, str]] = []
    summary = load_summary()
    runlog = load_file("run_log.csv")
    progress = load_file("progress_summary.csv")
    controls = load_file("control_timeseries.csv")
    states = load_file("state_timeseries.csv")

    plot_topology_demand_maps(manifest)
    for scenario in ["peak_demand", "incident_or_capacity_drop", "skew_peak"]:
        plot_effect_chain(scenario, runlog, progress, controls, states, manifest)
    plot_vsl_speed_effect("incident_or_capacity_drop", controls, states, progress, manifest)
    plot_vsl_rm_speed_effect("incident_or_capacity_drop", runlog, controls, states, progress, manifest)
    for scenario in ["peak_demand", "skew_peak", "incident_or_capacity_drop"]:
        plot_fd_shift(scenario, states, manifest)
        plot_urban_mfd_shift(scenario, runlog, manifest)
    for scenario in ["peak_demand", "skew_peak", "incident_or_capacity_drop"]:
        plot_signal_queue_service_effect(scenario, runlog, controls, states, manifest)
    for scenario in ["peak_demand", "skew_peak", "incident_or_capacity_drop"]:
        plot_candidate_surface(scenario, manifest)
    plot_effect_summary(summary, manifest)
    plot_computation_time_per_step(summary, manifest)
    write_manifest(manifest)
    print(f"output_dir={OUT}")
    print(f"generated_count={sum(1 for item in manifest if item.get('status') == 'generated')}")
    print(f"manifest={OUT / 'manifest.json'}")


if __name__ == "__main__":
    main()
