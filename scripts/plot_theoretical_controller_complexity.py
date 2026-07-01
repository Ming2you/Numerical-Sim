from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


OUT_DIR = Path("reports/figures/theoretical_complexity")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def complexity(n: int) -> dict[str, float]:
    """Representative normalized work for the current Wu-faithful comparison.

    n is the number of distributed follower players. Constants are illustrative
    and only preserve the architecture ordering. The asymptotic point is that
    PFO/P-Stack keep fixed local/leader budgets, while centralized SLSQP solves
    one full-network NLP whose variable dimension grows with n.
    """

    h = 3.0
    i = 3.0
    c_wu = 8.0
    c_faithful = 24.0
    l_stack = 8.0
    sqp_iter = 12.0
    variables_per_player = 4.0
    d = variables_per_player * n

    return {
        "NO-CONTROL": 1.0,
        "WU-CD-F": i * n * c_wu * h,
        "CLASSICAL-HIERARCHICAL": 6.0 * n * h,
        "WU-FAITHFUL-FOLLOWER / PFO": i * n * c_faithful * h,
        "P-STACK-WU-FAITHFUL": l_stack * i * n * c_faithful * h,
        # Numerical-gradient SLSQP: each iteration needs O(d) objective calls,
        # each rollout objective is O(nH), and the internal QP update is
        # represented by an O(d^3) dense term.
        "CENTRALIZED-SQP": sqp_iter * (d * n * h + 0.05 * d ** 3),
    }


def exact_joint_reference(n: int) -> float:
    """Optional exact discrete joint-search reference, not the implemented SQP."""

    return n * (3.0 ** n)


def main() -> None:
    n_values = list(range(1, 31))
    rows: list[dict[str, float]] = []
    for n in n_values:
        for controller, value in complexity(n).items():
            rows.append({
                "n": float(n),
                "controller": controller,
                "normalized_work": float(value),
            })
        rows.append({
            "n": float(n),
            "controller": "EXACT-JOINT-GRID reference",
            "normalized_work": float(exact_joint_reference(n)),
        })

    with (OUT_DIR / "controller_complexity_scaling.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["n", "controller", "normalized_work"])
        writer.writeheader()
        writer.writerows(rows)

    colors = {
        "NO-CONTROL": "#555555",
        "WU-CD-F": "#1f77b4",
        "CLASSICAL-HIERARCHICAL": "#ff7f0e",
        "WU-FAITHFUL-FOLLOWER / PFO": "#2ca02c",
        "P-STACK-WU-FAITHFUL": "#d62728",
        "CENTRALIZED-SQP": "#9467bd",
        "EXACT-JOINT-GRID reference": "#999999",
    }
    linestyles = {
        "NO-CONTROL": "-",
        "WU-CD-F": "-",
        "CLASSICAL-HIERARCHICAL": "-",
        "WU-FAITHFUL-FOLLOWER / PFO": "-",
        "P-STACK-WU-FAITHFUL": "-.",
        "CENTRALIZED-SQP": "--",
        "EXACT-JOINT-GRID reference": ":",
    }

    plot_order = [
        "NO-CONTROL",
        "WU-CD-F",
        "CLASSICAL-HIERARCHICAL",
        "WU-FAITHFUL-FOLLOWER / PFO",
        "P-STACK-WU-FAITHFUL",
        "CENTRALIZED-SQP",
    ]
    zoom_order = [
        "NO-CONTROL",
        "WU-CD-F",
        "CLASSICAL-HIERARCHICAL",
        "WU-FAITHFUL-FOLLOWER / PFO",
        "P-STACK-WU-FAITHFUL",
    ]

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(13.8, 5.6),
        gridspec_kw={"width_ratios": [1.35, 1.0]},
    )
    ax = axes[0]
    for controller in plot_order:
        values = [
            row["normalized_work"]
            for row in rows
            if row["controller"] == controller
        ]
        ax.plot(
            n_values,
            values,
            label=controller,
            color=colors[controller],
            linestyle=linestyles[controller],
            linewidth=2.4,
        )
    ax.set_xlabel("Number of distributed follower players, n")
    ax.set_ylabel("Normalized online work units")
    ax.set_title("Implemented Controllers (linear scale)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8.5, frameon=True)

    ax_zoom = axes[1]
    for controller in zoom_order:
        values = [
            row["normalized_work"]
            for row in rows
            if row["controller"] == controller
        ]
        ax_zoom.plot(
            n_values,
            values,
            label=controller,
            color=colors[controller],
            linestyle=linestyles[controller],
            linewidth=2.4,
        )
    ax_zoom.set_xlabel("Number of distributed follower players, n")
    ax_zoom.set_ylabel("Normalized online work units")
    ax_zoom.set_title("Distributed-family zoom (linear scale)")
    ax_zoom.grid(True, alpha=0.25)
    ax_zoom.legend(loc="upper left", fontsize=8.0, frameon=True)

    fig.suptitle("Theoretical Online Complexity: Wu-Faithful Controller Set")
    fig.tight_layout()
    for ext in ["png", "pdf"]:
        fig.savefig(OUT_DIR / f"controller_complexity_scaling.{ext}", dpi=220, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
