from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


WINDOW_START_SEC = 3600.0
WINDOW_END_SEC = 10800.0
WARMUP_NC_STEPS = 20
DEFAULT_CONTROL_INTERVAL_SEC = 180.0
RHO_CRIT = 33.5

TARGET_SCENARIOS = [
    "sweet_155_w",
    "sweet_170_w",
    "sweet_190_w",
    "sweet_170_skew15_w",
    "sweet_170_incident_w",
]

FINAL_CONTROLLERS = [
    "NC",
    "WU-CD-F",
    "PFO-link",
    "P-Stack",
    "P-Cent-SLSQP",
]

CONTROLLER_LABELS = {
    "NO-CONTROL": "NC",
    "NC": "NC",
    "WU-CD-F": "WU-CD-F",
    "PROPOSED-FOLLOWERS-ONLY": "PFO-link",
    "WU-FAITHFUL-FOLLOWER": "PFO-link",
    "WU-FAITHFUL-FOLLOWER-NOP1": "PFO-link",
    "PFO": "PFO-link",
    "P-STACK-WU-FAITHFUL-G1DF": "P-Stack",
    "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT": "P-Stack",
    "P-STACK-WU-FAITHFUL-APJOINT-FINAL": "P-Stack",
    "P-STACK-FINAL": "P-Stack",
    "PSTACK-G1DF": "P-Stack",
    "APJOINT": "P-Stack",
    "P-Stack": "P-Stack",
    "PROPOSED-STACKELBERG": "P-Stack-old",
    "P-CENT-SLSQP": "P-Cent-SLSQP",
    "P-CENT": "P-Cent-SLSQP",
    "P-Cent": "P-Cent-SLSQP",
    "PROPOSED-CENTRALIZED": "P-Cent-SLSQP",
    "P-CENT-GRID": "P-Cent-grid",
    "Centralized-grid": "P-Cent-grid",
    "Centralized": "P-Cent-legacy",
    "LEGACY": "P-Cent-legacy",
}


FIGURE_MANIFEST_ROWS = [
    ("macro_wttt", "bar", "scenario", "window_total_ttt", "controller", "5 scenarios x 5 controllers wTTT; final source should be T=10800 window [3600,10800]."),
    ("macro_improvement_vs_nc", "bar", "scenario", "improvement_vs_nc_pct", "controller", "Improvement against NC with NC warmup 20 steps."),
    ("macro_completed_vehicles", "bar", "scenario", "completed_vehicles", "controller", "Check that gains are not produced by suppressing completions."),
    ("macro_terminal_vehicles", "bar", "scenario", "terminal_vehicles", "controller", "Residual queue/congestion burden at T."),
    ("macro_att_completed", "bar", "scenario", "att_completed", "controller", "Average travel time over completed trips."),
    ("macro_mean_compute", "bar", "scenario", "mean_step_compute_sec", "controller", "Per-step compute; compare to ci=180s."),
    ("macro_max_compute", "bar", "scenario", "max_step_compute_sec", "controller", "Worst per-step compute; operational risk."),
    ("macro_realtime_ratio", "bar", "scenario", "mean_realtime_ratio", "controller", "Mean compute divided by 180 s control interval."),
    ("pcent_gap_ttt_pct", "bar", "scenario", "pstack_minus_pcent_slsqp_ttt_pct", "none", "P-Stack proximity or advantage relative to SLSQP centralized NLP."),
    ("pcent_compute_ratio", "bar", "scenario", "pstack_to_pcent_slsqp_compute_ratio", "none", "Compute multiplier of P-Stack vs SLSQP centralized NLP."),
    ("mechanism_total_ttt_timeseries", "line", "time_sec", "cumulative_total_ttt", "controller", "How TTT accumulation diverges."),
    ("mechanism_urban_freeway_ttt", "line", "time_sec", "cumulative_urban_ttt/cumulative_freeway_ttt", "component", "Separate urban transfer from freeway protection."),
    ("mechanism_nuf_target", "line", "time_sec", "N_UF_star", "none", "u-to-f quantity target used by leader."),
    ("mechanism_np_target", "line", "time_sec", "N_P_star", "none", "Protected urban accumulation target."),
    ("mechanism_ramp_metering", "line", "time_sec", "ramp_metering_*", "ramp", "Ramp release differentiation."),
    ("mechanism_ramp_queue", "line", "time_sec", "ramp_queue_*", "ramp", "Queue consequence of metering."),
    ("mechanism_green", "line", "time_sec", "green_*_p1", "signal", "Signal service allocation response."),
    ("mechanism_offset", "line", "time_sec", "offset_*", "signal", "Offset/progression response."),
    ("mechanism_vsl", "line_or_heatmap", "time_sec", "vsl_*", "link/segment", "VSL response; isolate incident/capacity-drop regimes."),
    ("mechanism_density", "line", "time_sec", "rho_FW_*_mean", "freeway_link", "Critical density protection."),
    ("mechanism_capacity_drop", "line", "time_sec", "capacity_drop_active", "none", "Whether control delays or reduces capacity-drop exposure."),
    ("price_green", "line", "time_sec", "diag_wu_b2_price_*", "signal", "Green split marginal externality."),
    ("price_offset", "line", "time_sec", "diag_wu_f3_offset_price_*", "signal", "Offset/progression marginal externality."),
    ("price_metering", "line", "time_sec", "diag_wu_b3_meter_price_*", "ramp", "Breakdown-threshold marginal cost; delta must hit cliff."),
    ("price_vsl", "line", "time_sec", "diag_wu_b3_vsl_price_*", "segment", "VSL marginal channel; may be partly hidden by active-set filters."),
    ("criticality_loo", "bar_or_heatmap", "agent_id", "criticality_total_ttt", "scenario", "Leave-one-out criticality."),
    ("criticality_phi", "directed_graph", "agent_pair_or_channel", "Phi", "direction", "Directional coupling flux."),
]

LITERATURE_ROWS = [
    ("Hegyi et al. 2005", "MPC coordination of ramp metering and variable speed limits", "control trajectories; density/flow states; RM+VSL benefit under bottlenecks", "mechanism_vsl, mechanism_ramp_metering, mechanism_density"),
    ("Papamichail & Papageorgiou 2008", "Traffic-responsive linked ramp metering / HERO", "no-control vs local vs coordinated metering; ramp occupancy and metering rates", "mechanism_ramp_metering, mechanism_ramp_queue"),
    ("Papamichail et al. 2010", "hierarchical coordinated ramp metering", "hierarchical layers; TTS comparisons; ramp storage utilization", "macro_wttt, macro_compute, criticality_loo"),
    ("Carlson et al. 2010", "optimal motorway control with VSL and ramp metering", "fundamental diagram and bottleneck activation; VSL/RM profiles", "mechanism_vsl, mechanism_density"),
    ("Geroliminis & Daganzo 2008", "urban MFD evidence", "accumulation-production/speed-density scatter; critical accumulation", "criticality_np_accumulation, mechanism_np_target"),
    ("Keyvan-Ekbatani et al. 2013", "urban gating using reduced NFD", "critical range and gating time series", "mechanism_np_target, price_metering"),
    ("Wu et al. 2022", "distributed integrated urban-freeway control", "distributed vs SLSQP centralized comparisons; green/VSL cooperative mixed network", "macro_wttt, pcent_gap_ttt_pct"),
    ("Farabi et al. 2024", "integrated corridor signal and ramp metering control", "direction-wise delay, accumulation, ramp flow, runtime", "macro_urban_freeway_ttt, mechanism_ramp_metering, macro_compute"),
    ("Hillier & Rothery 1967", "traffic-signal synchronization and offset", "delay as a function of offset and progression/platoon diffusion", "mechanism_offset, price_offset"),
    ("Weitzman 1974; Roberts & Spence 1976", "prices vs quantities and hybrid instruments", "instrument-choice interpretation under uncertainty", "price_green, price_metering, quantity corridor targets"),
]


def safe_float(value: Any) -> float:
    if value is None:
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    rows = list(rows)
    ensure_dir(path.parent)
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def summarize_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = read_json(path)
    if isinstance(data, list) and data:
        return dict(data[0])
    if isinstance(data, dict):
        return dict(data)
    return {}


def label_controller(raw: str) -> str:
    return CONTROLLER_LABELS.get(raw, raw)


def display_path(path: Path, repo_root: Path) -> str:
    for root in (repo_root, repo_root.parent):
        try:
            return str(path.relative_to(root))
        except ValueError:
            continue
    return str(path)


def guess_scenario(run_dir: Path) -> str:
    parts = [p.name for p in run_dir.parents] + [run_dir.name]
    known = set(TARGET_SCENARIOS) | {
        "low_demand",
        "medium_demand",
        "peak_demand",
        "oversaturated_demand",
        "incident_or_capacity_drop",
        "medium_incident_east",
        "medium_urban_west_skew",
    }
    for part in [run_dir.name] + parts:
        if part in known:
            return part
        if re.match(r"sweet_\d+(?:_skew\d+|_incident)?_w$", part):
            return part
        if re.match(r"sweet_\d+(_incident|_skew)?$", part):
            return part
        if re.match(r"sweet\d+", part):
            digits = re.findall(r"\d+", part)
            if digits:
                scenario = f"sweet_{digits[0]}"
                if "incident" in part.lower():
                    scenario += "_incident"
                if "skew" in part.lower():
                    scenario += "_skew"
                return scenario
        if part.endswith("_s42") or part.endswith("_s7") or part.endswith("_s123"):
            return re.sub(r"_s\d+$", "", part)
    return ""


def scan_roots(repo_root: Path) -> list[Path]:
    roots = [repo_root]
    for candidate in (repo_root / "outputs", repo_root.parent / "outputs"):
        if candidate.exists() and candidate not in roots:
            roots.append(candidate)
    return roots


def find_run_dirs(repo_root: Path) -> list[Path]:
    run_dirs = set()
    for file_name in ["run_log.csv", "control_timeseries.csv", "state_timeseries.csv", "summary.json"]:
        for root in scan_roots(repo_root):
            for path in root.rglob(file_name):
                if any(part in {".git", "__pycache__"} for part in path.parts):
                    continue
                run_dirs.add(path.parent)
    return sorted(run_dirs)


def count_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def inventory_runs(run_dirs: list[Path], repo_root: Path) -> list[dict[str, Any]]:
    rows = []
    for run_dir in run_dirs:
        summary = summarize_json(run_dir / "summary.json")
        controller_raw = str(summary.get("controller_id") or run_dir.name)
        scenario = guess_scenario(run_dir)
        run_log = run_dir / "run_log.csv"
        state = run_dir / "state_timeseries.csv"
        control = run_dir / "control_timeseries.csv"
        decision = run_dir / "decision_diagnostics.csv"
        progress = run_dir / "progress_summary.csv"
        horizon = ""
        if run_log.exists():
            try:
                sample = pd.read_csv(run_log, usecols=lambda c: c in {"time_sec", "step"})
                if "time_sec" in sample.columns and len(sample):
                    horizon = float(pd.to_numeric(sample["time_sec"], errors="coerce").max())
                elif "step" in sample.columns and len(sample):
                    horizon = (float(pd.to_numeric(sample["step"], errors="coerce").max()) + 1.0) * DEFAULT_CONTROL_INTERVAL_SEC
            except Exception:
                horizon = ""
        rows.append({
            "run_dir": display_path(run_dir, repo_root),
            "scenario_guess": scenario,
            "controller_raw": controller_raw,
            "controller_label": label_controller(controller_raw),
            "horizon_sec_guess": horizon,
            "has_summary_json": int((run_dir / "summary.json").exists()),
            "has_run_log": int(run_log.exists()),
            "has_state_timeseries": int(state.exists()),
            "has_control_timeseries": int(control.exists()),
            "has_decision_diagnostics": int(decision.exists()),
            "has_progress_summary": int(progress.exists()),
            "run_log_rows": count_rows(run_log),
            "state_rows": count_rows(state),
            "control_rows": count_rows(control),
            "decision_rows": count_rows(decision),
        })
    return rows


def infer_control_interval_sec(df: pd.DataFrame) -> float:
    if "time_sec" not in df.columns or len(df) < 2:
        return DEFAULT_CONTROL_INTERVAL_SEC
    times = pd.to_numeric(df["time_sec"], errors="coerce").dropna().sort_values()
    diffs = times.diff().dropna()
    diffs = diffs[diffs > 0.0]
    if diffs.empty:
        return DEFAULT_CONTROL_INTERVAL_SEC
    return float(diffs.median())


def compute_windowed_metrics(run_dirs: list[Path], repo_root: Path) -> list[dict[str, Any]]:
    rows = []
    for run_dir in run_dirs:
        run_log = run_dir / "run_log.csv"
        if not run_log.exists():
            continue
        summary = summarize_json(run_dir / "summary.json")
        controller_raw = str(summary.get("controller_id") or run_dir.name)
        controller = label_controller(controller_raw)
        scenario = guess_scenario(run_dir)
        try:
            df = pd.read_csv(run_log)
        except Exception:
            continue
        if df.empty:
            continue
        if "time_sec" not in df.columns:
            if "step" in df.columns:
                df["time_sec"] = (pd.to_numeric(df["step"], errors="coerce") + 1.0) * DEFAULT_CONTROL_INTERVAL_SEC
            else:
                continue
        interval_sec = infer_control_interval_sec(df)
        interval_h = interval_sec / 3600.0
        nc_warmup_sec = WARMUP_NC_STEPS * interval_sec if controller == "NC" else WINDOW_START_SEC
        start_sec = max(WINDOW_START_SEC, nc_warmup_sec)
        observed_end_sec = float(pd.to_numeric(df["time_sec"], errors="coerce").max())
        effective_end_sec = min(WINDOW_END_SEC, observed_end_sec)
        mask = (pd.to_numeric(df["time_sec"], errors="coerce") >= start_sec) & (
            pd.to_numeric(df["time_sec"], errors="coerce") <= effective_end_sec
        )
        win = df.loc[mask].copy()
        completed = math.nan
        if "boundary_out_sink_veh" in win.columns or "mainline_exit_flow_total" in win.columns:
            completed = safe_float(win.get("boundary_out_sink_veh", pd.Series(dtype=float)).sum())
            completed += safe_float(win.get("mainline_exit_flow_total", pd.Series(dtype=float)).sum()) * interval_h
        full_completed = math.nan
        if "boundary_out_sink_veh" in df.columns or "mainline_exit_flow_total" in df.columns:
            full_completed = safe_float(df.get("boundary_out_sink_veh", pd.Series(dtype=float)).sum())
            full_completed += safe_float(df.get("mainline_exit_flow_total", pd.Series(dtype=float)).sum()) * interval_h
        terminal_vehicles = math.nan
        state_path = run_dir / "state_timeseries.csv"
        if state_path.exists():
            try:
                state_df = pd.read_csv(state_path)
                if not state_df.empty:
                    last = state_df.iloc[-1]
                    if "terminal_total_vehicles" in state_df.columns:
                        terminal_vehicles = safe_float(last.get("terminal_total_vehicles"))
                    elif "total_vehicles" in state_df.columns:
                        terminal_vehicles = safe_float(last.get("total_vehicles"))
                    else:
                        terminal_vehicles = safe_float(last.get("urban_vehicles")) + safe_float(last.get("freeway_vehicles"))
            except Exception:
                terminal_vehicles = math.nan
        window_att = math.nan
        if completed and np.isfinite(completed) and completed > 0:
            window_att = safe_float(win.get("step_total_ttt", pd.Series(dtype=float)).sum()) / completed * 60.0
        row = {
            "run_dir": display_path(run_dir, repo_root),
            "scenario_guess": scenario,
            "scenario": scenario,
            "controller_raw": controller_raw,
            "controller_label": controller,
            "window_start_sec": start_sec,
            "window_end_requested_sec": WINDOW_END_SEC,
            "window_end_observed_sec": effective_end_sec,
            "window_complete_3600_10800": int(observed_end_sec >= WINDOW_END_SEC),
            "window_rows": len(win),
            "window_total_ttt": safe_float(win.get("step_total_ttt", pd.Series(dtype=float)).sum()),
            "window_urban_ttt": safe_float(win.get("step_urban_ttt", pd.Series(dtype=float)).sum()),
            "window_freeway_ttt": safe_float(win.get("step_freeway_ttt", pd.Series(dtype=float)).sum()),
            "window_completed_vehicles_est": completed,
            "window_att_min_per_completed_est": window_att,
            "mean_step_compute_sec": safe_float(win.get("computation_time_sec", pd.Series(dtype=float)).mean()),
            "max_step_compute_sec": safe_float(win.get("computation_time_sec", pd.Series(dtype=float)).max()),
            "mean_realtime_ratio": safe_float(win.get("computation_time_sec", pd.Series(dtype=float)).mean()) / max(interval_sec, 1e-9),
            "full_total_ttt_summary": summary.get("total_ttt", ""),
            "full_completed_vehicles": full_completed,
            "full_completed_vehicles_summary": summary.get("completed_vehicles", ""),
            "full_terminal_vehicles": terminal_vehicles,
            "full_terminal_vehicles_summary": summary.get("terminal_total_vehicles", summary.get("terminal_vehicles", "")),
            "full_att_min_per_completed_summary": summary.get("att_min_per_completed", ""),
        }
        rows.append(row)
    return rows


def final_windowed_macro(windowed: list[dict[str, Any]], out_dir: Path) -> pd.DataFrame:
    df = pd.DataFrame(windowed)
    if df.empty:
        return pd.DataFrame()
    df = df[
        df["scenario"].isin(TARGET_SCENARIOS)
        & df["controller_label"].isin(FINAL_CONTROLLERS)
        & df["window_rows"].astype(float).gt(0)
    ].copy()
    if df.empty:
        return pd.DataFrame()
    df["source"] = np.where(
        df["window_complete_3600_10800"].astype(int).eq(1),
        "final 5x5 windowed complete",
        "final 5x5 windowed partial",
    )
    df["total_ttt"] = pd.to_numeric(df["window_total_ttt"], errors="coerce")
    df["completed_vehicles"] = pd.to_numeric(df["full_completed_vehicles"], errors="coerce")
    df["window_completed_vehicles"] = pd.to_numeric(df["window_completed_vehicles_est"], errors="coerce")
    df["terminal_vehicles"] = pd.to_numeric(df["full_terminal_vehicles"], errors="coerce")
    df["att_min_per_completed"] = pd.to_numeric(df["window_att_min_per_completed_est"], errors="coerce")
    df["compute_s_per_step"] = pd.to_numeric(df["mean_step_compute_sec"], errors="coerce")
    df["max_compute_s_per_step"] = pd.to_numeric(df["max_step_compute_sec"], errors="coerce")
    df["realtime_ratio"] = pd.to_numeric(df["mean_realtime_ratio"], errors="coerce")
    nc = df[df["controller_label"].eq("NC")].set_index("scenario")["total_ttt"]
    df["improvement_vs_nc_pct"] = df.apply(
        lambda row: 100.0 * (nc.get(row["scenario"], np.nan) - row["total_ttt"]) / nc.get(row["scenario"], np.nan)
        if np.isfinite(nc.get(row["scenario"], np.nan)) and nc.get(row["scenario"], np.nan) != 0
        else np.nan,
        axis=1,
    )
    df.to_csv(out_dir / "final_5x5_windowed_macro.csv", index=False)
    return df


def window_slice(df: pd.DataFrame, controller: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    if "time_sec" not in out.columns:
        if "step" in out.columns:
            out["time_sec"] = (pd.to_numeric(out["step"], errors="coerce") + 1.0) * DEFAULT_CONTROL_INTERVAL_SEC
        else:
            return out.iloc[0:0].copy()
    interval_sec = infer_control_interval_sec(out)
    start_sec = max(WINDOW_START_SEC, WARMUP_NC_STEPS * interval_sec) if controller == "NC" else WINDOW_START_SEC
    time = pd.to_numeric(out["time_sec"], errors="coerce")
    return out.loc[(time >= start_sec) & (time <= WINDOW_END_SEC)].copy()


def numeric_matrix(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    if not cols:
        return pd.DataFrame(index=df.index)
    return df[cols].apply(pd.to_numeric, errors="coerce")


def stack_nonnull(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    try:
        return df.stack(future_stack=True).dropna()
    except TypeError:
        return df.stack(dropna=True)


def count_positive(df: pd.DataFrame, col: str, threshold: float = 0.5) -> float:
    if col not in df.columns or df.empty:
        return math.nan
    values = pd.to_numeric(df[col], errors="coerce")
    return float(values.gt(threshold).sum())


def sum_numeric_col(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns or df.empty:
        return math.nan
    return safe_float(pd.to_numeric(df[col], errors="coerce").sum())


def mean_numeric_col(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns or df.empty:
        return math.nan
    return safe_float(pd.to_numeric(df[col], errors="coerce").mean())


def max_numeric_col(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns or df.empty:
        return math.nan
    return safe_float(pd.to_numeric(df[col], errors="coerce").max())


def compute_mechanism_event_counts(run_dirs: list[Path], repo_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_dir in final_trajectory_dirs(run_dirs):
        summary = summarize_json(run_dir / "summary.json")
        controller_raw = str(summary.get("controller_id") or run_dir.name)
        controller = label_controller(controller_raw)
        scenario = guess_scenario(run_dir)
        try:
            run_log = pd.read_csv(run_dir / "run_log.csv")
        except Exception:
            run_log = pd.DataFrame()
        try:
            state = pd.read_csv(run_dir / "state_timeseries.csv")
        except Exception:
            state = pd.DataFrame()
        try:
            control = pd.read_csv(run_dir / "control_timeseries.csv")
        except Exception:
            control = pd.DataFrame()

        win_log = window_slice(run_log, controller)
        win_state = window_slice(state, controller)
        win_control = window_slice(control, controller)
        rho_cols = [c for c in win_state.columns if re.match(r"rho_FW_.*_mean$", c)]
        rho = numeric_matrix(win_state, rho_cols)
        rho_stack = stack_nonnull(rho)
        queue_cols = select_cols(win_state, "ramp_queue_")
        ramp_queue = numeric_matrix(win_state, queue_cols)
        queue_total = ramp_queue.sum(axis=1, skipna=True) if not ramp_queue.empty else pd.Series(dtype=float)
        meter_cols = select_cols(win_control, "ramp_metering_")
        metering = numeric_matrix(win_control, meter_cols)
        metering_active_steps = math.nan
        metering_reduction_mean = math.nan
        if not metering.empty:
            max_by_col = metering.max(axis=0, skipna=True)
            reduction = max_by_col - metering
            metering_active_steps = float(reduction.gt(1e-6).any(axis=1).sum())
            metering_reduction_mean = safe_float(stack_nonnull(reduction).mean())

        row = {
            "scenario": scenario,
            "controller_raw": controller_raw,
            "controller_label": controller,
            "run_dir": display_path(run_dir, repo_root),
            "window_rows": len(win_log),
            "capacity_drop_step_count": count_positive(win_log, "capacity_drop_active"),
            "incident_step_count": count_positive(win_log, "incident_lane_closure_active"),
            "density_exceedance_step_count": float(rho.gt(RHO_CRIT).any(axis=1).sum()) if not rho.empty else math.nan,
            "density_exceedance_cell_count": float(rho.gt(RHO_CRIT).sum().sum()) if not rho.empty else math.nan,
            "density_exceedance_count_logged_sum": sum_numeric_col(win_log, "density_exceedance_count"),
            "max_density_ratio": safe_float(rho_stack.max() / RHO_CRIT) if not rho_stack.empty else math.nan,
            "mean_density_ratio": safe_float(rho_stack.mean() / RHO_CRIT) if not rho_stack.empty else math.nan,
            "mean_flow_FW_W": mean_numeric_col(win_state, "flow_FW_W_mean"),
            "mean_flow_FW_E": mean_numeric_col(win_state, "flow_FW_E_mean"),
            "mean_speed_FW_W": mean_numeric_col(win_state, "speed_FW_W_mean"),
            "mean_speed_FW_E": mean_numeric_col(win_state, "speed_FW_E_mean"),
            "peak_total_ramp_queue_state": safe_float(queue_total.max()) if not queue_total.empty else math.nan,
            "mean_total_ramp_queue_state": safe_float(queue_total.mean()) if not queue_total.empty else math.nan,
            "peak_total_ramp_queue_logged": max_numeric_col(win_log, "total_ramp_queue_end_veh"),
            "ramp_queue_overflow_count_sum": sum_numeric_col(win_log, "ramp_queue_overflow_count"),
            "queue_overflow_count_sum": sum_numeric_col(win_log, "queue_overflow_count"),
            "offramp_blocked_flow_total_sum": sum_numeric_col(win_log, "offramp_blocked_flow_total"),
            "metering_active_step_count": metering_active_steps,
            "metering_reduction_mean_vs_run_max": metering_reduction_mean,
            "mean_total_metering_flow": mean_numeric_col(win_log, "total_metering_flow"),
            "mean_total_no_meter_flow": mean_numeric_col(win_log, "total_no_meter_flow"),
            "mean_metering_shortfall_flow": mean_numeric_col(win_log, "metering_shortfall_flow"),
            "metering_target_infeasible_step_count": count_positive(win_log, "metering_target_infeasible"),
            "mean_net_inflow_tracking_error": mean_numeric_col(win_log, "net_inflow_tracking_error"),
        }
        rows.append(row)
    return rows


PRICE_CHANNELS = [
    {
        "channel": "green",
        "price_prefix": "diag_wu_b2_price_",
        "enabled_col": "diag_wu_b2_price_enabled",
        "refresh_col": "diag_wu_b2_price_refresh_count",
        "action_regex": r"green_.*_p1$",
        "physical_meaning": "signal service allocation marginal externality",
    },
    {
        "channel": "offset",
        "price_prefix": "diag_wu_f3_offset_price_",
        "enabled_col": "diag_wu_f3_offset_price_enabled",
        "refresh_col": "",
        "action_prefix": "offset_",
        "physical_meaning": "progression and arrival-alignment marginal externality",
    },
    {
        "channel": "metering",
        "price_prefix": "diag_wu_b3_meter_price_",
        "enabled_col": "diag_wu_b3_meter_price_enabled",
        "refresh_col": "",
        "action_prefix": "ramp_metering_",
        "physical_meaning": "breakdown-threshold marginal cost near ramp release cliffs",
    },
    {
        "channel": "vsl",
        "price_prefix": "diag_wu_b3_vsl_price_",
        "enabled_col": "diag_wu_b3_vsl_price_enabled",
        "refresh_col": "",
        "action_regex": r"vsl_.*_seg\d+$",
        "physical_meaning": "freeway speed/density marginal channel under active-set filtering",
    },
]


def channel_price_cols(df: pd.DataFrame, prefix: str) -> list[str]:
    excluded = ("enabled", "delta", "trust", "ref", "refresh", "count")
    return [
        c
        for c in df.columns
        if c.startswith(prefix)
        and not any(token in c for token in excluded)
        and pd.to_numeric(df[c], errors="coerce").notna().any()
    ]


def channel_action_cols(df: pd.DataFrame, channel: dict[str, str]) -> list[str]:
    if "action_prefix" in channel:
        return select_cols(df, str(channel["action_prefix"]))
    regex = channel.get("action_regex", "")
    if regex:
        return [c for c in df.columns if re.match(regex, c) and pd.to_numeric(df[c], errors="coerce").notna().any()]
    return []


def compute_price_channel_audit(run_dirs: list[Path], repo_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_dir in final_trajectory_dirs(run_dirs):
        summary = summarize_json(run_dir / "summary.json")
        controller_raw = str(summary.get("controller_id") or run_dir.name)
        controller = label_controller(controller_raw)
        if controller != "P-Stack":
            continue
        scenario = guess_scenario(run_dir)
        try:
            control = pd.read_csv(run_dir / "control_timeseries.csv")
        except Exception:
            continue
        win = window_slice(control, controller)
        for channel in PRICE_CHANNELS:
            price_cols = channel_price_cols(win, str(channel["price_prefix"]))
            prices = numeric_matrix(win, price_cols)
            price_stack = stack_nonnull(prices)
            action_cols = channel_action_cols(win, channel)
            actions = numeric_matrix(win, action_cols)
            action_stack = stack_nonnull(actions)
            enabled_col = str(channel["enabled_col"])
            enabled_fraction = mean_numeric_col(win, enabled_col) if enabled_col in win.columns else math.nan
            refresh_col = str(channel.get("refresh_col") or "")
            refresh_max = max_numeric_col(win, refresh_col) if refresh_col and refresh_col in win.columns else math.nan
            max_abs_price = safe_float(price_stack.abs().max()) if not price_stack.empty else math.nan
            mean_abs_price = safe_float(price_stack.abs().mean()) if not price_stack.empty else math.nan
            nonzero_price_steps = (
                float(prices.abs().gt(1e-9).any(axis=1).sum()) if not prices.empty else 0.0
            )
            action_span = safe_float(action_stack.max() - action_stack.min()) if not action_stack.empty else math.nan
            action_mean_step_std = safe_float(actions.std(axis=1, skipna=True).mean()) if not actions.empty else math.nan
            enabled = np.isfinite(enabled_fraction) and enabled_fraction > 0.5
            if not price_cols and enabled:
                status = "enabled_no_scalar_price_values_exported"
            elif np.isfinite(max_abs_price) and max_abs_price <= 1e-9 and np.isfinite(action_span) and action_span <= 1e-9:
                status = "truly_flat_or_inactive"
            elif np.isfinite(max_abs_price) and max_abs_price > 1e-9 and np.isfinite(action_span) and action_span <= 1e-9:
                status = "domain_constrained"
            elif np.isfinite(max_abs_price) and max_abs_price > 1e-9:
                status = "normal"
            else:
                status = "not_observed"
            rows.append(
                {
                    "scenario": scenario,
                    "controller_raw": controller_raw,
                    "controller_label": controller,
                    "channel": channel["channel"],
                    "enabled_fraction": enabled_fraction,
                    "price_column_count": len(price_cols),
                    "price_columns": ";".join(price_cols),
                    "max_abs_price": max_abs_price,
                    "mean_abs_price": mean_abs_price,
                    "nonzero_price_step_count": nonzero_price_steps,
                    "action_column_count": len(action_cols),
                    "action_columns": ";".join(action_cols),
                    "action_span": action_span,
                    "action_mean_step_std": action_mean_step_std,
                    "refresh_count_max": refresh_max,
                    "status": status,
                    "physical_meaning": channel["physical_meaning"],
                    "cross_price_policy": "green-offset and VSL-metering cross-price terms excluded in final frame",
                    "run_dir": display_path(run_dir, repo_root),
                }
            )
    return rows


def load_existing_macro(repo_root: Path, out_dir: Path) -> pd.DataFrame:
    frames = []
    final4 = repo_root / "2026-07-10" / "results" / "final4_7scenario_metrics.csv"
    if final4.exists():
        df = pd.read_csv(final4)
        df["source"] = "2026-07-10 final4 aggregate"
        df["controller_label"] = df["controller"].map(label_controller).fillna(df["controller"])
        frames.append(df)
    stage1 = repo_root / "2026-07-09" / "results" / "stage1_matrix" / "stage1_summary.csv"
    if stage1.exists():
        df = pd.read_csv(stage1)
        df["source"] = "2026-07-09 stage1 aggregate"
        df["controller_label"] = df["controller"].map(label_controller).fillna(df["controller"])
        if "terminal_vehicles" not in df.columns and "terminal_total_vehicles" in df.columns:
            df["terminal_vehicles"] = df["terminal_total_vehicles"]
        if "compute_s_per_step" not in df.columns and "compute_per_step_sec" in df.columns:
            df["compute_s_per_step"] = df["compute_per_step_sec"]
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    macro = pd.concat(frames, ignore_index=True, sort=False)
    macro.to_csv(out_dir / "existing_macro_sources.csv", index=False)
    return macro


def save_figure(fig: plt.Figure, out_base: Path, plot_rows: list[dict[str, Any]], title: str, source: str) -> None:
    ensure_dir(out_base.parent)
    fig.tight_layout()
    png = out_base.with_suffix(".png")
    pdf = out_base.with_suffix(".pdf")
    fig.savefig(png, dpi=180)
    fig.savefig(pdf)
    plt.close(fig)
    plot_rows.append({
        "figure_id": out_base.name,
        "png": str(png),
        "pdf": str(pdf),
        "title": title,
        "source": source,
    })


def numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def plot_grouped_bar(
    df: pd.DataFrame,
    metric: str,
    out_base: Path,
    plot_rows: list[dict[str, Any]],
    ylabel: str,
    title: str,
    source_label: str,
) -> None:
    if metric not in df.columns or "scenario" not in df.columns or "controller_label" not in df.columns:
        return
    tmp = df[["scenario", "controller_label", metric]].copy()
    tmp[metric] = pd.to_numeric(tmp[metric], errors="coerce")
    tmp = tmp.dropna(subset=[metric])
    if tmp.empty:
        return
    pivot = tmp.pivot_table(index="scenario", columns="controller_label", values=metric, aggfunc="first")
    pivot = pivot.sort_index()
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    pivot.plot(kind="bar", ax=ax, width=0.82)
    ax.set_xlabel("scenario")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(title="controller", fontsize=8)
    save_figure(fig, out_base, plot_rows, title, source_label)


def plot_compute_frontier(df: pd.DataFrame, out_base: Path, plot_rows: list[dict[str, Any]], source_label: str) -> None:
    needed = {"compute_s_per_step", "total_ttt", "controller_label", "scenario"}
    if not needed.issubset(df.columns):
        return
    tmp = df[list(needed)].copy()
    tmp["compute_s_per_step"] = pd.to_numeric(tmp["compute_s_per_step"], errors="coerce")
    tmp["total_ttt"] = pd.to_numeric(tmp["total_ttt"], errors="coerce")
    tmp = tmp.dropna(subset=["compute_s_per_step", "total_ttt"])
    if tmp.empty:
        return
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    for label, group in tmp.groupby("controller_label"):
        ax.scatter(group["compute_s_per_step"], group["total_ttt"], label=label, s=42)
    ax.set_xlabel("mean compute per step (s)")
    ax.set_ylabel("total TTT")
    ax.set_title("Compute-performance frontier")
    ax.grid(alpha=0.25)
    ax.legend(title="controller", fontsize=8)
    save_figure(fig, out_base, plot_rows, "Compute-performance frontier", source_label)


def plot_pcent_gaps(df: pd.DataFrame, plots_dir: Path, plot_rows: list[dict[str, Any]], suffix: str, source_label: str) -> None:
    if "scenario" not in df.columns or "controller_label" not in df.columns or "total_ttt" not in df.columns:
        return
    tmp = df.copy()
    tmp["total_ttt"] = pd.to_numeric(tmp["total_ttt"], errors="coerce")
    p = tmp.pivot_table(index="scenario", columns="controller_label", values="total_ttt", aggfunc="first")
    pcent_label = "P-Cent-SLSQP" if "P-Cent-SLSQP" in p.columns else "P-Cent"
    if "P-Stack" in p.columns and pcent_label in p.columns:
        gap = 100.0 * (p["P-Stack"] - p[pcent_label]) / p[pcent_label].replace(0, np.nan)
        fig, ax = plt.subplots(figsize=(8.0, 4.6))
        gap.sort_index().plot(kind="bar", ax=ax, color="#3b6ea8")
        ax.axhline(0.0, color="black", linewidth=0.8)
        ax.set_xlabel("scenario")
        ax.set_ylabel(f"P-Stack minus {pcent_label} TTT (%)")
        ax.set_title(f"P-Stack vs {pcent_label} TTT gap")
        ax.grid(axis="y", alpha=0.25)
        save_figure(fig, plots_dir / f"pcent_gap_ttt_pct_{suffix}", plot_rows, f"P-Stack vs {pcent_label} TTT gap", source_label)
    if "compute_s_per_step" in tmp.columns:
        tmp["compute_s_per_step"] = pd.to_numeric(tmp["compute_s_per_step"], errors="coerce")
        c = tmp.pivot_table(index="scenario", columns="controller_label", values="compute_s_per_step", aggfunc="first")
        pcent_label = "P-Cent-SLSQP" if "P-Cent-SLSQP" in c.columns else "P-Cent"
        if "P-Stack" in c.columns and pcent_label in c.columns:
            ratio = c["P-Stack"] / c[pcent_label].replace(0, np.nan)
            fig, ax = plt.subplots(figsize=(8.0, 4.6))
            ratio.sort_index().plot(kind="bar", ax=ax, color="#6a8f3a")
            ax.axhline(1.0, color="black", linewidth=0.8)
            ax.set_xlabel("scenario")
            ax.set_ylabel("compute ratio")
            ax.set_title(f"P-Stack compute / {pcent_label} compute")
            ax.grid(axis="y", alpha=0.25)
            save_figure(fig, plots_dir / f"pcent_compute_ratio_{suffix}", plot_rows, f"P-Stack compute / {pcent_label} compute", source_label)


def select_cols(df: pd.DataFrame, prefix: str, exclude: tuple[str, ...] = ()) -> list[str]:
    cols = [c for c in df.columns if c.startswith(prefix) and not any(token in c for token in exclude)]
    return [c for c in cols if pd.to_numeric(df[c], errors="coerce").notna().any()]


def plot_lines(df: pd.DataFrame, time_col: str, cols: list[str], out_base: Path, plot_rows: list[dict[str, Any]], ylabel: str, title: str, source: str) -> None:
    if not cols or time_col not in df.columns:
        return
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    x = pd.to_numeric(df[time_col], errors="coerce")
    for col in cols:
        y = pd.to_numeric(df[col], errors="coerce")
        if y.notna().any():
            ax.plot(x, y, label=col)
    if not ax.lines:
        plt.close(fig)
        return
    ax.set_xlabel("time (s)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(alpha=0.25)
    if len(cols) <= 14:
        ax.legend(fontsize=7, ncol=2)
    save_figure(fig, out_base, plot_rows, title, source)


def plot_vsl_heatmap(df: pd.DataFrame, time_col: str, cols: list[str], out_base: Path, plot_rows: list[dict[str, Any]], source: str) -> None:
    if not cols or time_col not in df.columns:
        return
    matrix = df[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float).T
    if np.isnan(matrix).all():
        return
    fig, ax = plt.subplots(figsize=(9.2, max(3.8, 0.24 * len(cols))))
    x = pd.to_numeric(df[time_col], errors="coerce").to_numpy(dtype=float)
    extent = [np.nanmin(x), np.nanmax(x), -0.5, len(cols) - 0.5]
    im = ax.imshow(matrix, aspect="auto", origin="lower", extent=extent, cmap="viridis")
    ax.set_yticks(range(len(cols)))
    ax.set_yticklabels(cols, fontsize=7)
    ax.set_xlabel("time (s)")
    ax.set_title("VSL command heatmap")
    fig.colorbar(im, ax=ax, label="km/h")
    save_figure(fig, out_base, plot_rows, "VSL command heatmap", source)


def trajectory_dirs(repo_root: Path) -> list[Path]:
    root = repo_root / "2026-07-06" / "results" / "trajectories"
    if not root.exists():
        return []
    return sorted([p for p in root.iterdir() if p.is_dir() and (p / "control_timeseries.csv").exists()])


def final_trajectory_dirs(run_dirs: list[Path]) -> list[Path]:
    out: list[Path] = []
    for run_dir in run_dirs:
        scenario = guess_scenario(run_dir)
        controller = label_controller(run_dir.name)
        if (
            scenario in TARGET_SCENARIOS
            and controller in FINAL_CONTROLLERS
            and (run_dir / "control_timeseries.csv").exists()
            and (run_dir / "run_log.csv").exists()
        ):
            out.append(run_dir)
    return sorted(out)


def plot_trajectory_dir(run_dir: Path, repo_root: Path, plots_dir: Path, plot_rows: list[dict[str, Any]]) -> None:
    source = display_path(run_dir, repo_root)
    scenario = guess_scenario(run_dir)
    controller = label_controller(run_dir.name)
    slug_source = f"{scenario}_{controller}" if scenario else run_dir.name
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", slug_source)
    control_path = run_dir / "control_timeseries.csv"
    state_path = run_dir / "state_timeseries.csv"
    run_log_path = run_dir / "run_log.csv"
    control = pd.read_csv(control_path) if control_path.exists() else pd.DataFrame()
    state = pd.read_csv(state_path) if state_path.exists() else pd.DataFrame()
    run_log = pd.read_csv(run_log_path) if run_log_path.exists() else pd.DataFrame()
    out = plots_dir / "trajectories"

    if not control.empty:
        time_col = "time_sec" if "time_sec" in control.columns else "step"
        plot_lines(control, time_col, ["N_UF_star"], out / f"{slug}_nuf_target", plot_rows, "veh/h", f"{slug}: N_UF target", source)
        plot_lines(control, time_col, ["N_P_star"], out / f"{slug}_np_target", plot_rows, "veh", f"{slug}: N_P target", source)
        plot_lines(control, time_col, select_cols(control, "ramp_metering_"), out / f"{slug}_ramp_metering", plot_rows, "veh/h", f"{slug}: ramp metering", source)
        plot_lines(control, time_col, [c for c in control.columns if c.startswith("green_") and c.endswith("_p1")], out / f"{slug}_green_p1", plot_rows, "s", f"{slug}: phase-1 green", source)
        plot_lines(control, time_col, select_cols(control, "offset_"), out / f"{slug}_offsets", plot_rows, "s", f"{slug}: offsets", source)
        plot_lines(control, time_col, [c for c in control.columns if re.match(r"vsl_.*_seg\d+$", c)], out / f"{slug}_vsl_segments", plot_rows, "km/h", f"{slug}: VSL by segment", source)
        plot_vsl_heatmap(control, time_col, [c for c in control.columns if re.match(r"vsl_.*_seg\d+$", c)], out / f"{slug}_vsl_heatmap", plot_rows, source)
        price_exclude = ("enabled", "delta", "ref", "refresh", "trust", "count")
        plot_lines(control, time_col, select_cols(control, "diag_wu_b2_price_", price_exclude), out / f"{slug}_price_green", plot_rows, "marginal cost", f"{slug}: green marginal prices", source)
        plot_lines(control, time_col, select_cols(control, "diag_wu_b3_meter_price_", price_exclude), out / f"{slug}_price_metering", plot_rows, "marginal cost", f"{slug}: metering marginal prices", source)
        plot_lines(control, time_col, select_cols(control, "diag_wu_b3_vsl_price_", price_exclude), out / f"{slug}_price_vsl", plot_rows, "marginal cost", f"{slug}: VSL marginal prices", source)
        plot_lines(control, time_col, select_cols(control, "diag_wu_f3_offset_price_", price_exclude), out / f"{slug}_price_offset", plot_rows, "marginal cost", f"{slug}: offset marginal prices", source)

    if not state.empty:
        time_col = "time_sec" if "time_sec" in state.columns else "step"
        plot_lines(state, time_col, [c for c in state.columns if re.match(r"rho_FW_.*_mean$", c)], out / f"{slug}_freeway_density", plot_rows, "veh/km/lane", f"{slug}: freeway density", source)
        plot_lines(state, time_col, [c for c in state.columns if re.match(r"speed_FW_.*_mean$", c)], out / f"{slug}_freeway_speed", plot_rows, "km/h", f"{slug}: freeway speed", source)
        plot_lines(state, time_col, [c for c in state.columns if re.match(r"flow_FW_.*_mean$", c)], out / f"{slug}_freeway_flow", plot_rows, "veh/h", f"{slug}: freeway flow", source)
        plot_lines(state, time_col, select_cols(state, "ramp_queue_"), out / f"{slug}_ramp_queue", plot_rows, "veh", f"{slug}: ramp queues", source)
        plot_lines(state, time_col, ["urban_protected_accumulation_veh"], out / f"{slug}_urban_protected_accumulation", plot_rows, "veh", f"{slug}: protected urban accumulation", source)
        rho_cols = [c for c in state.columns if re.match(r"rho_FW_.*_mean$", c)]
        if rho_cols:
            ratio = state[[time_col] + rho_cols].copy()
            for col in rho_cols:
                ratio[col] = pd.to_numeric(ratio[col], errors="coerce") / RHO_CRIT
            plot_lines(ratio, time_col, rho_cols, out / f"{slug}_freeway_density_ratio", plot_rows, "rho/rho_crit", f"{slug}: freeway density ratio", source)
        if not control.empty and "diag_N_P_crit" in control.columns and "urban_protected_accumulation_veh" in state.columns:
            merged = state[[time_col, "urban_protected_accumulation_veh"]].copy()
            crit = pd.to_numeric(control["diag_N_P_crit"], errors="coerce").replace(0, np.nan)
            merged["urban_accumulation_over_npcrit"] = pd.to_numeric(merged["urban_protected_accumulation_veh"], errors="coerce") / crit.to_numpy()[: len(merged)]
            plot_lines(merged, time_col, ["urban_accumulation_over_npcrit"], out / f"{slug}_npcrit_ratio", plot_rows, "N_P/N_P_crit", f"{slug}: protected accumulation ratio", source)

    if not run_log.empty:
        time_col = "time_sec" if "time_sec" in run_log.columns else "step"
        plot_lines(run_log, time_col, [c for c in ["cumulative_total_ttt", "cumulative_urban_ttt", "cumulative_freeway_ttt"] if c in run_log.columns], out / f"{slug}_cumulative_ttt", plot_rows, "veh*h", f"{slug}: cumulative TTT", source)
        plot_lines(run_log, time_col, [c for c in ["capacity_drop_active", "incident_lane_closure_active"] if c in run_log.columns], out / f"{slug}_capacity_drop_incident", plot_rows, "indicator", f"{slug}: capacity drop / incident state", source)
        plot_lines(run_log, time_col, [c for c in ["total_metering_flow", "total_no_meter_flow", "net_inflow", "net_inflow_target"] if c in run_log.columns], out / f"{slug}_release_flow", plot_rows, "veh/h", f"{slug}: release and target flows", source)


def make_plots(repo_root: Path, out_dir: Path, macro: pd.DataFrame, run_dirs: list[Path] | None = None) -> list[dict[str, Any]]:
    plots_dir = out_dir / "plots"
    plot_rows: list[dict[str, Any]] = []
    if not macro.empty:
        is_final = macro["source"].astype(str).str.contains("final 5x5").any() if "source" in macro.columns else False
        plot_df = macro.copy() if is_final else macro[macro["source"].eq("2026-07-10 final4 aggregate")].copy()
        if plot_df.empty:
            plot_df = macro.copy()
        suffix = "5x5" if is_final else "existing"
        title_prefix = "Final 5x5" if is_final else "Existing aggregate"
        source_label = "final 5x5 windowed runs" if is_final else "existing aggregate CSV"
        plot_grouped_bar(plot_df, "total_ttt", plots_dir / f"macro_wttt_{suffix}", plot_rows, "window TTT (veh*h)", f"{title_prefix} windowed TTT", source_label)
        plot_grouped_bar(plot_df, "improvement_vs_nc_pct", plots_dir / f"macro_improvement_vs_nc_{suffix}", plot_rows, "%", f"{title_prefix} improvement vs NC", source_label)
        plot_grouped_bar(plot_df, "completed_vehicles", plots_dir / f"macro_completed_vehicles_{suffix}", plot_rows, "vehicles", f"{title_prefix} completed vehicles", source_label)
        plot_grouped_bar(plot_df, "terminal_vehicles", plots_dir / f"macro_terminal_vehicles_{suffix}", plot_rows, "vehicles", f"{title_prefix} terminal vehicles", source_label)
        plot_grouped_bar(plot_df, "att_min_per_completed", plots_dir / f"macro_att_completed_{suffix}", plot_rows, "min/veh", f"{title_prefix} ATT", source_label)
        plot_grouped_bar(plot_df, "compute_s_per_step", plots_dir / f"macro_compute_mean_{suffix}", plot_rows, "s/step", f"{title_prefix} mean compute", source_label)
        plot_grouped_bar(plot_df, "max_compute_s_per_step", plots_dir / f"macro_compute_max_{suffix}", plot_rows, "s/step", f"{title_prefix} max compute", source_label)
        plot_grouped_bar(plot_df, "realtime_ratio", plots_dir / f"macro_realtime_ratio_{suffix}", plot_rows, "compute / 180s", f"{title_prefix} realtime ratio", source_label)
        plot_compute_frontier(plot_df, plots_dir / f"macro_compute_frontier_{suffix}", plot_rows, source_label)
        plot_pcent_gaps(plot_df, plots_dir, plot_rows, suffix, source_label)

    for run_dir in trajectory_dirs(repo_root):
        plot_trajectory_dir(run_dir, repo_root, plots_dir, plot_rows)
    if run_dirs is not None:
        for run_dir in final_trajectory_dirs(run_dirs):
            plot_trajectory_dir(run_dir, repo_root, plots_dir, plot_rows)
    return plot_rows


def write_static_tables(out_dir: Path) -> None:
    write_csv(
        out_dir / "final_figure_manifest.csv",
        [
            {
                "figure_id": row[0],
                "plot_type": row[1],
                "x": row[2],
                "y": row[3],
                "group": row[4],
                "claim": row[5],
                "subplot_policy": "one file per figure; no subplot panels",
            }
            for row in FIGURE_MANIFEST_ROWS
        ],
    )
    write_csv(
        out_dir / "literature_figure_mapping.csv",
        [
            {
                "source": row[0],
                "topic": row[1],
                "figure_convention": row[2],
                "our_mapping": row[3],
            }
            for row in LITERATURE_ROWS
        ],
    )
    write_csv(
        out_dir / "final_scenario_controller_manifest.csv",
        [
            {
                "scenario": scenario,
                "controller": controller,
                "T_total_sec": 10800,
                "window_start_sec": WINDOW_START_SEC,
                "window_end_sec": WINDOW_END_SEC,
                "warmup_nc_steps": WARMUP_NC_STEPS,
            }
            for scenario in TARGET_SCENARIOS
            for controller in FINAL_CONTROLLERS
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="../outputs/final_analysis_extract")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out_dir = Path(args.output).resolve()
    ensure_dir(out_dir)

    run_dirs = find_run_dirs(repo_root)
    inventory = inventory_runs(run_dirs, repo_root)
    write_csv(out_dir / "existing_data_inventory.csv", inventory)

    windowed = compute_windowed_metrics(run_dirs, repo_root)
    write_csv(out_dir / "windowed_metrics_existing.csv", windowed)
    write_csv(out_dir / "windowed_metrics_existing_nonempty.csv", [row for row in windowed if int(row.get("window_rows", 0)) > 0])
    write_csv(out_dir / "windowed_metrics_existing_complete.csv", [row for row in windowed if int(row.get("window_complete_3600_10800", 0)) == 1])
    write_csv(out_dir / "final_mechanism_event_counts.csv", compute_mechanism_event_counts(run_dirs, repo_root))
    write_csv(out_dir / "final_price_channel_audit.csv", compute_price_channel_audit(run_dirs, repo_root))

    final_macro = final_windowed_macro(windowed, out_dir)
    existing_macro = load_existing_macro(repo_root, out_dir)
    macro = final_macro if not final_macro.empty else existing_macro
    write_static_tables(out_dir)

    plot_rows = make_plots(repo_root, out_dir, macro, run_dirs)
    write_csv(out_dir / "generated_plot_index.csv", plot_rows)

    print(f"Wrote analysis extraction to {out_dir}")
    print(f"Run dirs inventoried: {len(inventory)}")
    print(f"Windowed metric rows: {len(windowed)}")
    print(f"Plots generated: {len(plot_rows)}")


if __name__ == "__main__":
    main()
