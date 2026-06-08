# controller_v2(Stackelberg v2)로 각 시나리오를 돌려 open-loop 대비 TTS와 제어 결과를 뽑는 드라이버
"""
Driver: run each scenario open-loop (baseline) and under the Stackelberg v2
controller (controller_v2.run_v2), report TTS and dump per-step controls.

Usage:
  python run_v2_scenarios.py
  python run_v2_scenarios.py --scenario s3_rush_hour
  python run_v2_scenarios.py --extra            # include extra scenarios
  python run_v2_scenarios.py --output-dir 2026-06-08/results
"""
import argparse
import csv
import json
import site
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEPS = ROOT / ".codex_pydeps"
if LOCAL_DEPS.exists():
    site.addsitedir(str(LOCAL_DEPS))

from params import Params
from network import build_network
from scenarios import (DEFAULT_SCENARIO_NAMES, EXTRA_SCENARIO_NAMES, SCENARIOS)
from controller_v2 import run_v2, apply_control_v2, build_u, CtrlConfig


def run_open_loop(sim, p, demand_fn=None):
    """Baseline: 0.5 green split, no metering, full VSL."""
    n_ctrl = int(p.time.sim_time / p.time.Tc)
    u = build_u({"A": 0.5, "C": 0.5, "D": 0.5, "F": 0.5},
                {"D": 0, "F": 0},
                {"R1": 1.0, "R2": 1.0, "R3": 1.0, "R4": 1.0},
                {"FW_W": p.mpc.vsl_max, "FW_E": p.mpc.vsl_max}, p)
    for kc in range(n_ctrl):
        if demand_fn:
            demand_fn(kc * p.time.Tc)
        apply_control_v2(sim, u)
        for _ in range(p.time.K_cf):
            sim.step_freeway_period()
    return sim


def summarize(name, sim_ol, sim_v2):
    f_ol, ur_ol, t_ol = sim_ol.tts_freeway, sim_ol.tts_urban, sim_ol.tts_total()
    f_v, ur_v, t_v = sim_v2.tts_freeway, sim_v2.tts_urban, sim_v2.tts_total()
    imp = 100.0 * (t_ol - t_v) / t_ol if t_ol else 0.0
    return (f"{name:28s} | OL: fw={f_ol:7.1f} ur={ur_ol:7.1f} tot={t_ol:8.1f}"
            f" | V2: fw={f_v:7.1f} ur={ur_v:7.1f} tot={t_v:8.1f}"
            f" | improve={imp:5.1f}%")


def result_row(name, sim_ol, sim_v2):
    f_ol, ur_ol, t_ol = sim_ol.tts_freeway, sim_ol.tts_urban, sim_ol.tts_total()
    f_v, ur_v, t_v = sim_v2.tts_freeway, sim_v2.tts_urban, sim_v2.tts_total()
    return {
        "scenario": name,
        "open_loop_freeway_tts_veh_h": f_ol,
        "open_loop_urban_tts_veh_h": ur_ol,
        "open_loop_total_tts_veh_h": t_ol,
        "v2_freeway_tts_veh_h": f_v,
        "v2_urban_tts_veh_h": ur_v,
        "v2_total_tts_veh_h": t_v,
        "v2_improvement_percent": 100.0 * (t_ol - t_v) / t_ol if t_ol else 0.0,
        "open_loop_max_queue_AB_veh": max(sim_ol.history["AB_queue"]),
        "v2_max_queue_AB_veh": max(sim_v2.history["AB_queue"]),
    }


def write_control_log(out_dir, scenario, infos, p):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{scenario}_v2_controls.csv"
    fields = ["scenario", "control_step", "time_sec",
              "NP", "NUF",
              "g_A", "g_C", "g_D", "g_F", "off_D", "off_F",
              "b_R1", "b_R2", "b_R3", "b_R4", "v_FW_W", "v_FW_E",
              "tts_total", "tts_freeway", "tts_urban",
              "nash_iters", "nash_residual", "nash_converged", "leader_evals"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for kc, info in enumerate(infos):
            w.writerow({
                "scenario": scenario,
                "control_step": kc,
                "time_sec": kc * p.time.Tc,
                "NP": info.NP, "NUF": info.NUF,
                "g_A": info.greens["A"], "g_C": info.greens["C"],
                "g_D": info.greens["D"], "g_F": info.greens["F"],
                "off_D": info.offsets.get("D", 0), "off_F": info.offsets.get("F", 0),
                "b_R1": info.metering["R1"], "b_R2": info.metering["R2"],
                "b_R3": info.metering["R3"], "b_R4": info.metering["R4"],
                "v_FW_W": info.vsl["FW_W"], "v_FW_E": info.vsl["FW_E"],
                "tts_total": info.tts_total, "tts_freeway": info.tts_freeway,
                "tts_urban": info.tts_urban,
                "nash_iters": info.nash_iters,
                "nash_residual": info.nash_residual,
                "nash_converged": info.nash_converged,
                "leader_evals": info.leader_evals,
            })
    return path


def write_results(out_dir, rows, metadata):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "v2_numerical_results.csv"
    json_path = out / "v2_numerical_results.json"
    fieldnames = sorted({k for row in rows for k in row})
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    json_path.write_text(json.dumps({"metadata": metadata, "results": rows},
                                    indent=2), encoding="utf-8")
    return csv_path, json_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=None)
    ap.add_argument("--extra", action="store_true",
                    help="include extra scenarios")
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--demand-scale", type=float, default=1.0)
    args = ap.parse_args()

    p = Params()
    net = build_network()
    cfg = CtrlConfig()

    if args.scenario:
        names = [args.scenario]
    else:
        names = list(DEFAULT_SCENARIO_NAMES)
        if args.extra:
            names += EXTRA_SCENARIO_NAMES

    def scale(sim, dfn):
        if args.demand_scale == 1.0:
            return dfn
        def do_scale():
            for k in list(sim.urban.demand.keys()):
                sim.urban.demand[k] *= args.demand_scale
            for fw in sim.fw.values():
                fw.demand_origin *= args.demand_scale
        do_scale()
        if dfn is None:
            return None
        def wrapped(t):
            dfn(t)
            do_scale()
        return wrapped

    print(f"Stackelberg v2: nash_max_iter={cfg.nash_max_iter} "
          f"leader_maxfev={cfg.leader_maxfev}\n")
    rows, lines, control_paths = [], [], []
    for name in names:
        builder = SCENARIOS[name]
        sim_ol, dfn_ol, _ = builder(net, p)
        sim_ol = run_open_loop(sim_ol, p, scale(sim_ol, dfn_ol))

        sim_v2, dfn_v2, _ = builder(net, p)
        sim_v2, infos = run_v2(sim_v2, p, demand_fn=scale(sim_v2, dfn_v2), cfg=cfg)

        rows.append(result_row(name, sim_ol, sim_v2))
        lines.append(summarize(name, sim_ol, sim_v2))
        print(lines[-1])
        if args.output_dir:
            control_paths.append(str(write_control_log(args.output_dir, name, infos, p)))

    print("\nTTS in veh*h. OL = open-loop baseline (0.5 green, no metering). "
          "V2 = Stackelberg v2 controller.")
    if args.output_dir:
        meta = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "controller": "Stackelberg v2 (controller_v2.run_v2)",
            "topology_source": "Zhai et al. (2025) Figure 3 topology",
            "sim_time_seconds": p.time.sim_time,
            "controller_step_seconds": p.time.Tc,
            "nash_max_iter": cfg.nash_max_iter,
            "leader_maxfev": cfg.leader_maxfev,
            "demand_scale": args.demand_scale,
            "scenarios": names,
            "control_logs": control_paths,
        }
        csv_path, json_path = write_results(args.output_dir, rows, meta)
        print(f"Saved: {csv_path}")
        print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()
