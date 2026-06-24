# sweet_* 부하 스윕 결과에서 PFO/P-Stack 개선율·leader 활성·방향별 freeway jam을 한 표로 뽑는 추출기.
"""sweet_sweep 결과(summary.json + 각 run의 state_timeseries/progress_summary)에서
- PFO/P-Stack TTT 개선율(vs no-control)
- LeaderValue = PFO_ttt - PStack_ttt (양수 = P-Stack 우위)
- leader 활성도(max N_P*, max N_UF*, 활성 step 비율)
- 방향별(FW_E/FW_W) terminal 밀도·속도로 jam 판정
을 추출한다. 정밀 재실행/1차 스윕 양쪽에 재사용.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

RHO_CRIT = 33.5
RHO_MAX = 95.01964207118104
V_MIN = 5.0
# jam 판정: terminal 방향 평균밀도가 rho_max의 75% 초과 또는 평균속도가 20km/h 미만이면 해당 방향 'jammed'.
JAM_RHO = 0.75 * RHO_MAX
JAM_SPEED = 20.0


def _last_row(csv_path: Path) -> Optional[Dict[str, str]]:
    if not csv_path.exists():
        return None
    last = None
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            last = row
    return last


def _dir_state(run_dir: Path) -> Dict[str, float]:
    row = _last_row(run_dir / "state_timeseries.csv")
    if row is None:
        return {}
    keys = ["rho_FW_E_mean", "rho_FW_W_mean", "speed_FW_E_mean", "speed_FW_W_mean"]
    return {k: float(row.get(k, "nan")) for k in keys}


def _leader_activation(run_dir: Path) -> Dict[str, float]:
    path = run_dir / "progress_summary.csv"
    if not path.exists():
        return {"max_N_P_star": 0.0, "max_N_UF_star": 0.0, "active_frac": 0.0, "steps": 0}
    n_p, n_uf, active, total = 0.0, 0.0, 0, 0
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            total += 1
            np_star = float(row.get("leader_selected_N_P_star", 0.0) or 0.0)
            nuf_star = float(row.get("leader_selected_N_UF_star", 0.0) or 0.0)
            n_p = max(n_p, np_star)
            n_uf = max(n_uf, nuf_star)
            if np_star != 0.0 or nuf_star != 0.0:
                active += 1
    return {
        "max_N_P_star": round(n_p, 1),
        "max_N_UF_star": round(n_uf, 1),
        "active_frac": round(active / max(total, 1), 3),
        "steps": total,
    }


def _jam_label(ds: Dict[str, float]) -> str:
    if not ds:
        return "?"
    e_jam = ds["rho_FW_E_mean"] > JAM_RHO or ds["speed_FW_E_mean"] < JAM_SPEED
    w_jam = ds["rho_FW_W_mean"] > JAM_RHO or ds["speed_FW_W_mean"] < JAM_SPEED
    if e_jam and w_jam:
        return "BOTH-jam"
    if e_jam or w_jam:
        return "one-jam"
    e_cong = ds["rho_FW_E_mean"] > RHO_CRIT
    w_cong = ds["rho_FW_W_mean"] > RHO_CRIT
    if e_cong or w_cong:
        return "moderate"
    return "free"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep-dir", required=True)
    ap.add_argument("--csv-out", default=None)
    args = ap.parse_args()

    sweep = Path(args.sweep_dir)
    summary = json.loads((sweep / "summary.json").read_text(encoding="utf-8"))
    results = summary["results"]

    rows: List[Dict[str, Any]] = []
    for sc, by_ctrl in results.items():
        nc = by_ctrl.get("NO-CONTROL", {})
        pfo = by_ctrl.get("PROPOSED-FOLLOWERS-ONLY", {})
        ps = by_ctrl.get("PROPOSED-STACKELBERG", {})
        ps_dir = _dir_state(sweep / "runs" / sc / "PROPOSED-STACKELBERG")
        act = _leader_activation(sweep / "runs" / sc / "PROPOSED-STACKELBERG")
        lv = round(float(pfo.get("total_ttt", 0)) - float(ps.get("total_ttt", 0)), 3)
        lv_pct = round(100.0 * lv / max(float(pfo.get("total_ttt", 1)), 1e-9), 3)
        rows.append({
            "scenario": sc,
            "nc_ttt": nc.get("total_ttt"),
            "pfo_ttt": pfo.get("total_ttt"),
            "ps_ttt": ps.get("total_ttt"),
            "pfo_impr_pct": pfo.get("total_ttt_improvement_vs_no_control_pct"),
            "ps_impr_pct": ps.get("total_ttt_improvement_vs_no_control_pct"),
            "leader_value": lv,
            "leader_value_pct": lv_pct,
            "leader_active_frac": act["active_frac"],
            "max_N_P_star": act["max_N_P_star"],
            "max_N_UF_star": act["max_N_UF_star"],
            "term_fw_veh": ps.get("terminal_freeway_vehicles"),
            "rho_FW_E": round(ps_dir.get("rho_FW_E_mean", float("nan")), 1) if ps_dir else None,
            "rho_FW_W": round(ps_dir.get("rho_FW_W_mean", float("nan")), 1) if ps_dir else None,
            "spd_FW_E": round(ps_dir.get("speed_FW_E_mean", float("nan")), 1) if ps_dir else None,
            "spd_FW_W": round(ps_dir.get("speed_FW_W_mean", float("nan")), 1) if ps_dir else None,
            "jam": _jam_label(ps_dir),
        })

    rows.sort(key=lambda r: r["scenario"])
    hdr = ["scenario", "pfo_impr_pct", "ps_impr_pct", "leader_value", "leader_value_pct",
           "leader_active_frac", "max_N_P_star", "max_N_UF_star",
           "rho_FW_E", "rho_FW_W", "spd_FW_E", "spd_FW_W", "jam"]
    print(" | ".join(f"{h:>14s}" if i else f"{h:<10s}" for i, h in enumerate(hdr)))
    for r in rows:
        print(" | ".join(
            (f"{r[h]:<10s}" if i == 0 else f"{str(r[h]):>14s}") for i, h in enumerate(hdr)
        ))

    if args.csv_out:
        out = Path(args.csv_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
