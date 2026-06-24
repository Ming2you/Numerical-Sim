from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


SCENARIO_PRESETS = {
    "configured": [
        ("low_demand", "Low", "outputs/no_control_low_fd_rhocap95_1800"),
        ("medium_demand", "Medium", "outputs/no_control_medium_fd_rhocap95_1800"),
        ("peak_demand", "Peak", "outputs/no_control_peak_fd_rhocap95_1800"),
    ],
    "proposed": [
        ("low_demand", "Low", "outputs/canonical_low_fd_rhocap95_1800"),
        (
            "medium_demand",
            "Medium",
            "outputs/canonical_medium_fd_rhocap95_1800",
        ),
        ("peak_demand", "Peak", "outputs/canonical_peak_fd_rhocap95_1800"),
    ],
}

TOKENS = {
    "surface": "#FCFCFD",
    "panel": "#FFFFFF",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "axis": "#D7DBE7",
}

LINK_STYLES = {
    "FW_W": {
        "label": "FW_W",
        "color": "#5477C4",
        "light": "#CEDFFE",
        "linestyle": "-",
        "marker": "o",
    },
    "FW_E": {
        "label": "FW_E",
        "color": "#CC6F47",
        "light": "#FFBDA1",
        "linestyle": "--",
        "marker": "s",
    },
}


def _theme() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": TOKENS["surface"],
            "savefig.facecolor": TOKENS["surface"],
            "axes.facecolor": TOKENS["panel"],
            "axes.edgecolor": TOKENS["axis"],
            "axes.labelcolor": TOKENS["ink"],
            "axes.grid": True,
            "grid.color": TOKENS["grid"],
            "grid.linewidth": 0.8,
            "font.family": "sans-serif",
            "font.sans-serif": ["Aptos", "Segoe UI", "DejaVu Sans", "Arial"],
        }
    )


def _header(fig: plt.Figure, title: str, subtitle: str) -> None:
    fig.text(
        0.065,
        0.985,
        textwrap.fill(title, width=95),
        ha="left",
        va="top",
        fontsize=16,
        fontweight="semibold",
        color=TOKENS["ink"],
    )
    fig.text(
        0.065,
        0.953,
        textwrap.fill(subtitle, width=150),
        ha="left",
        va="top",
        fontsize=10,
        color=TOKENS["muted"],
    )


def _load(
    repo_root: Path,
    scenarios: list[tuple[str, str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw_parts = []
    aggregate_parts = []
    scenario_summary = []
    for scenario, label, relative_dir in scenarios:
        out_dir = repo_root / relative_dir
        raw = pd.read_csv(out_dir / "segment_fd_timeseries.csv")
        aggregate = pd.read_csv(out_dir / "segment_fd_aggregate.csv")
        metadata = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
        raw["scenario_label"] = label
        aggregate["scenario_label"] = label
        raw_parts.append(raw)
        aggregate_parts.append(aggregate)
        scenario_summary.append(
            {
                "scenario": scenario,
                "scenario_label": label,
                "total_sec": float(metadata["total_sec"]),
                "rho_max": float(metadata["rho_max"]),
                "final_total_ttt_veh_h": float(metadata["final_total_ttt"]),
            }
        )
    return (
        pd.concat(raw_parts, ignore_index=True),
        pd.concat(aggregate_parts, ignore_index=True),
        pd.DataFrame(scenario_summary),
    )


def _segment_summary(raw: pd.DataFrame, rho_crit: float) -> pd.DataFrame:
    summary = (
        raw.assign(congested=raw["rho_veh_km_lane"] > rho_crit)
        .groupby(["scenario", "scenario_label", "link", "segment"], as_index=False)
        .agg(
            max_rho_veh_km_lane=("rho_veh_km_lane", "max"),
            mean_rho_veh_km_lane=("rho_veh_km_lane", "mean"),
            max_flow_veh_h=("flow_veh_h", "max"),
            min_speed_km_h=("speed_km_h", "min"),
            congested_share=("congested", "mean"),
        )
    )
    return summary


def _plot(
    raw: pd.DataFrame,
    aggregate: pd.DataFrame,
    scenario_labels: list[str],
    chart_title: str,
    rho_crit: float,
    output_png: Path,
    output_svg: Path,
) -> None:
    _theme()
    segments = sorted(int(value) for value in raw["segment"].unique())
    fig, axes = plt.subplots(
        len(scenario_labels),
        len(segments),
        figsize=(16, 11.5),
        sharex=True,
        sharey=True,
    )

    x_max = max(float(raw["rho_veh_km_lane"].max()) * 1.05, rho_crit * 1.25)
    y_max = float(raw["flow_veh_h"].max()) * 1.08

    for row_index, scenario_label in enumerate(scenario_labels):
        for col_index, segment in enumerate(segments):
            ax = axes[row_index, col_index]
            panel_raw = raw[
                (raw["scenario_label"] == scenario_label)
                & (raw["segment"] == segment)
            ]
            panel_aggregate = aggregate[
                (aggregate["scenario_label"] == scenario_label)
                & (aggregate["segment"] == segment)
            ]

            for link, style in LINK_STYLES.items():
                link_raw = panel_raw[panel_raw["link"] == link]
                link_aggregate = panel_aggregate[
                    panel_aggregate["link"] == link
                ].sort_values("time_sec")
                sampled_raw = link_raw.iloc[::2]
                ax.scatter(
                    sampled_raw["rho_veh_km_lane"],
                    sampled_raw["flow_veh_h"],
                    color=style["light"],
                    edgecolors="none",
                    alpha=0.24,
                    s=13,
                )
                ax.plot(
                    link_aggregate["rho_veh_km_lane"],
                    link_aggregate["flow_veh_h"],
                    color=style["color"],
                    linestyle=style["linestyle"],
                    marker=style["marker"],
                    markersize=4.5,
                    linewidth=1.25,
                    label=style["label"] if row_index == 0 and col_index == 0 else None,
                )

            ax.axvline(
                rho_crit,
                color="#464C55",
                linewidth=1.0,
                linestyle=":",
                zorder=0,
            )
            ax.set_xlim(0.0, x_max)
            ax.set_ylim(0.0, y_max)
            ax.set_title(
                f"Segment {segment}" if row_index == 0 else "",
                fontsize=10,
                color=TOKENS["ink"],
                pad=8,
            )
            ax.set_xlabel(
                "Density (veh/km/lane)" if row_index == len(scenario_labels) - 1 else "",
                fontsize=9,
            )
            ax.set_ylabel(
                f"{scenario_label}\nFlow (veh/h)" if col_index == 0 else "",
                fontsize=9,
            )
            ax.tick_params(labelsize=8, colors=TOKENS["muted"], length=0)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)

    handles = [
        plt.Line2D(
            [0],
            [0],
            color=style["color"],
            linestyle=style["linestyle"],
            marker=style["marker"],
            linewidth=1.25,
            markersize=5,
            label=style["label"],
        )
        for style in LINK_STYLES.values()
    ]
    handles.append(
        plt.Line2D(
            [0],
            [0],
            color="#464C55",
            linestyle=":",
            linewidth=1.0,
            label=f"rho_crit = {rho_crit:.1f}",
        )
    )
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.065, 0.925),
        frameon=False,
        ncol=3,
        fontsize=9,
    )
    _header(
        fig,
        chart_title,
        "No-control, 1,800 s, coupled METANET storage-cap plant; gray points are 10 s states and colored paths are 180 s means. All panels use common axes.",
    )
    fig.subplots_adjust(
        left=0.065,
        right=0.985,
        bottom=0.07,
        top=0.875,
        hspace=0.24,
        wspace=0.14,
    )
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=180, bbox_inches="tight")
    fig.savefig(output_svg, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--preset",
        choices=sorted(SCENARIO_PRESETS),
        default="configured",
    )
    parser.add_argument("--rho-crit", type=float, default=33.5)
    parser.add_argument(
        "--output-png",
        default="reports/figures/fig_no_control_three_scenario_fd_rhocap95_1800.png",
    )
    parser.add_argument(
        "--output-svg",
        default="reports/figures/fig_no_control_three_scenario_fd_rhocap95_1800.svg",
    )
    parser.add_argument(
        "--summary-csv",
        default="outputs/no_control_three_scenario_fd_rhocap95_1800/segment_summary.csv",
    )
    parser.add_argument(
        "--scenario-summary-csv",
        default="outputs/no_control_three_scenario_fd_rhocap95_1800/scenario_summary.csv",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    scenarios = SCENARIO_PRESETS[args.preset]
    raw, aggregate, scenario_summary = _load(repo_root, scenarios)
    segment_summary = _segment_summary(raw, args.rho_crit)
    summary_path = repo_root / args.summary_csv
    scenario_summary_path = repo_root / args.scenario_summary_csv
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    segment_summary.to_csv(summary_path, index=False)
    scenario_summary.to_csv(scenario_summary_path, index=False)
    _plot(
        raw,
        aggregate,
        [label for _, label, _ in scenarios],
        (
            "The recalibrated scenarios separate near-critical, loading, and peak regimes"
            if args.preset == "proposed"
            else "The current demand labels do not create evenly separated freeway regimes"
        ),
        args.rho_crit,
        repo_root / args.output_png,
        repo_root / args.output_svg,
    )
    print(
        json.dumps(
            {
                "output_png": str(repo_root / args.output_png),
                "output_svg": str(repo_root / args.output_svg),
                "summary_csv": str(summary_path),
                "scenario_summary_csv": str(scenario_summary_path),
                "scenario_summary": scenario_summary.to_dict(orient="records"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
