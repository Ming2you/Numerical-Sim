"""Run demand-fluctuation extra scenarios and summarize VSL activation."""
from __future__ import annotations

import argparse
import csv
import json
import site
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEPS = ROOT / ".codex_pydeps"
if LOCAL_DEPS.exists():
    site.addsitedir(str(LOCAL_DEPS))

from network import build_network
from params import Params
from run import run_open_loop
from scenarios import EXTRA_SCENARIO_NAMES, SCENARIOS
from stackelberg import StackelbergController, StackelbergParams, run_stackelberg


def _control_stats(u_log, p):
    if u_log is None or len(u_log) == 0:
        return {}
    out = {}
    names = [
        "g_A", "g_C", "g_D", "g_F",
        "b1", "b2", "b3", "b4",
        "v_FW_W", "v_FW_E",
    ]
    for idx, name in enumerate(names[:u_log.shape[1]]):
        vals = u_log[:, idx]
        out[f"{name}_min"] = float(np.min(vals))
        out[f"{name}_mean"] = float(np.mean(vals))
        out[f"{name}_max"] = float(np.max(vals))
    vsl_cols = u_log[:, 8:10] if u_log.shape[1] >= 10 else np.empty((len(u_log), 0))
    if vsl_cols.size:
        active = np.any(vsl_cols < (p.mpc.vsl_max - 1e-6), axis=1)
        out["vsl_active_steps"] = int(np.sum(active))
        out["vsl_active_fraction"] = float(np.mean(active))
        out["vsl_min_overall"] = float(np.min(vsl_cols))
    return out


def _follower_game_stats(info_log):
    if not info_log:
        return {}
    iterations = []
    converged = 0
    selected_candidates = []
    for item in info_log:
        st = item["stackelberg_iteration"]
        iterations.append(st["follower_game_iterations"])
        converged += 1 if st["follower_game_converged"] else 0
        selected_candidates.append(st["selected_candidate"])
    return {
        "follower_game_steps": len(info_log),
        "follower_game_converged_steps": converged,
        "follower_game_iter_min": int(min(iterations)),
        "follower_game_iter_max": int(max(iterations)),
        "selected_candidate_min": int(min(selected_candidates)),
        "selected_candidate_max": int(max(selected_candidates)),
    }


def _row(scenario, sim_ol, sim_st, u_log, info_log, p):
    row = {
        "scenario": scenario,
        "open_loop_freeway_tts_veh_h": sim_ol.tts_freeway,
        "open_loop_urban_tts_veh_h": sim_ol.tts_urban,
        "open_loop_total_tts_veh_h": sim_ol.tts_total(),
        "stackelberg_freeway_tts_veh_h": sim_st.tts_freeway,
        "stackelberg_urban_tts_veh_h": sim_st.tts_urban,
        "stackelberg_total_tts_veh_h": sim_st.tts_total(),
        "stackelberg_improvement_vs_open_loop_percent": (
            100.0 * (sim_ol.tts_total() - sim_st.tts_total()) / sim_ol.tts_total()
            if sim_ol.tts_total()
            else 0.0
        ),
    }
    row.update(_control_stats(u_log, p))
    row.update(_follower_game_stats(info_log))
    return row


def _write_outputs(out_dir, rows, metadata, control_logs, info_logs):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    summary_path = out / "extra_scenario_summary.csv"
    fields = sorted({key for row in rows for key in row})
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    json_path = out / "extra_scenario_analysis.json"
    json_path.write_text(json.dumps({
        "metadata": metadata,
        "summary": rows,
        "info_logs": info_logs,
    }, indent=2), encoding="utf-8")

    for scenario, u_log in control_logs.items():
        path = out / f"{scenario}_stackelberg_controls.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "control_step", "time_sec",
                    "g_A", "g_C", "g_D", "g_F",
                    "b1", "b2", "b3", "b4",
                    "v_FW_W", "v_FW_E",
                ],
            )
            writer.writeheader()
            for kc, u in enumerate(u_log):
                writer.writerow({
                    "control_step": kc,
                    "time_sec": metadata["controller_step_seconds"] * kc,
                    "g_A": u[0],
                    "g_C": u[1],
                    "g_D": u[2],
                    "g_F": u[3],
                    "b1": u[4],
                    "b2": u[5],
                    "b3": u[6],
                    "b4": u[7],
                    "v_FW_W": u[8],
                    "v_FW_E": u[9],
                })
    return summary_path, json_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="results/extra_scenarios")
    parser.add_argument("--freeway-preview-steps", type=int, default=1)
    parser.add_argument("--leader-preview-steps", type=int, default=1)
    parser.add_argument("--apply-rho-crit-to-plant", action="store_true")
    args = parser.parse_args()

    p = Params()
    sp = StackelbergParams(
        freeway_preview_control_steps=args.freeway_preview_steps,
        leader_preview_control_steps=args.leader_preview_steps,
        apply_rho_crit_to_plant=args.apply_rho_crit_to_plant,
    )
    net = build_network()

    rows = []
    control_logs = {}
    info_logs = {}
    for name in EXTRA_SCENARIO_NAMES:
        sim_ol, dfn_ol, _constraint = SCENARIOS[name](net, p)
        sim_ol = run_open_loop(sim_ol, p, dfn_ol)

        sim_st, dfn_st, constraint = SCENARIOS[name](net, p)
        ctrl = StackelbergController(p, sp)
        sim_st, u_log, info_log = run_stackelberg(sim_st, p, dfn_st, ctrl, constraint)

        rows.append(_row(name, sim_ol, sim_st, u_log, info_log, p))
        control_logs[name] = u_log
        info_logs[name] = info_log
        print(
            f"{name:34s} | OL={sim_ol.tts_total():8.1f} "
            f"Stackelberg={sim_st.tts_total():8.1f} "
            f"VSL active={rows[-1].get('vsl_active_steps', 0)}/{len(u_log)} "
            f"minVSL={rows[-1].get('vsl_min_overall', p.mpc.vsl_max):.1f}"
        )

    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "controller": "stackelberg_follower_game",
        "sim_time_seconds": p.time.sim_time,
        "controller_step_seconds": p.time.Tc,
        "scenarios": EXTRA_SCENARIO_NAMES,
        "params": asdict(sp),
    }
    summary_path, json_path = _write_outputs(
        args.output_dir,
        rows,
        metadata,
        control_logs,
        info_logs,
    )
    print(f"Saved: {summary_path}")
    print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()
