from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DESKTOP_ROOT = Path(r"C:\Users\alsrj\Desktop\Numerical-Sim")
SRC = ROOT / "reports" / "figures"
OUT = ROOT / "reports" / "figures" / "post_analysis_2026_06_23_figure_design"


FIGURES = [
    ("00_scenario_demand", "fig01_demand_profiles.png", "Demand profiles across 6/23 scenarios"),
    ("00_scenario_demand", "fig02_demand_composition.png", "Demand composition by source"),
    ("00_scenario_demand", "fig03_skew_demand.png", "Spatial demand skew, total preserved"),
    ("01_macro_performance", "fig04_improvement.png", "TTT improvement vs no-control"),
    ("01_macro_performance", "fig05_pstack_pfo_gap.png", "P-Stack minus PFO improvement gap"),
    ("01_macro_performance", "fig06_throughput_terminal.png", "Completed and terminal vehicles"),
    ("01_macro_performance", "fig07_freeway_urban.png", "Freeway and urban TTT decomposition"),
    ("03_leader_feasibility", "fig08_leader_targets.png", "P-Stack leader target trajectories"),
    ("03_leader_feasibility", "fig09_step_ttt.png", "Step TTT divergence over time"),
    ("05_micro_controls", "fig10_green_queue_align.png", "Green split and queue split alignment"),
    ("05_micro_controls", "fig11_ramp_green.png", "Ramp-feeding green differentiation"),
    ("04_game_coupling", "fig12_coupling_micro.png", "Ramp-level micro coupling"),
    ("04_game_coupling", "fig13_coupling_macro.png", "Network-level macro coupling"),
    ("04_game_coupling", "fig14_accumulation.png", "Half-cap movement excess"),
    ("04_game_coupling", "fig15_skew_balance.png", "Boundary balance under spatial skew"),
    ("05_micro_controls", "fig16_vsl.png", "Incident VSL activation"),
    ("06_computation_cost", "fig17_computation.png", "Computation cost and real-time ratio"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source_report": str((ROOT / "reports" / "post_analysis_results_2026-06-23.md").relative_to(ROOT)),
        "source_script": str((ROOT / "2026-06-23" / "diag_scripts" / "make_paper_figures_v2.py").relative_to(ROOT)),
        "raw_inputs_expected_by_source_script": [
            "outputs/analysis_matrix_3600",
            "outputs/analysis_matrix_3600_extra",
        ],
        "raw_inputs_present_in_current_workspace": {
            "outputs/analysis_matrix_3600": (ROOT / "outputs" / "analysis_matrix_3600").exists(),
            "outputs/analysis_matrix_3600_extra": (ROOT / "outputs" / "analysis_matrix_3600_extra").exists(),
        },
        "raw_inputs_present_in_desktop_clone": {
            "workspace": str(DESKTOP_ROOT),
            "outputs/analysis_matrix_3600": (DESKTOP_ROOT / "outputs" / "analysis_matrix_3600").exists(),
            "outputs/analysis_matrix_3600_extra": (
                DESKTOP_ROOT / "outputs" / "analysis_matrix_3600_extra"
            ).exists(),
        },
        "scenario_coverage_from_report": [
            "medium",
            "peak",
            "heavy1.40",
            "heavy1.50",
            "oversaturated",
            "incident",
            "skew-peak",
            "skew-heavy",
        ],
        "requested_focus_scenarios": ["median/medium", "peak", "peak_skew/skew-peak", "incident"],
        "figures": [],
    }

    for group, filename, description in FIGURES:
        source = SRC / filename
        group_dir = OUT / group
        group_dir.mkdir(parents=True, exist_ok=True)
        target = group_dir / filename
        if source.exists():
            shutil.copy2(source, target)
            status = "copied"
        else:
            status = "missing"
        manifest["figures"].append(
            {
                "status": status,
                "group": group,
                "filename": filename,
                "description": description,
                "source": str(source.relative_to(ROOT)),
                "target": str(target.relative_to(ROOT)),
            }
        )

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"packaged_dir={OUT}")
    print(f"copied_count={sum(1 for item in manifest['figures'] if item['status'] == 'copied')}")
    print(f"missing_count={sum(1 for item in manifest['figures'] if item['status'] == 'missing')}")


if __name__ == "__main__":
    main()
