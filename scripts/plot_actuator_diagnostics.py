# 액추에이터(VSL/ramp metering/offset·green) 동작 진단 시계열을 run 출력에서 SVG로 뽑는 스크립트
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

PALETTE = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#be185d"]
W, H = 1000, 360
ML, MR, MT, MB = 70, 70, 46, 46


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _f(row: dict, key: str, default: float = 0.0) -> float:
    value = row.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _scale(values: list[float], lo: float, hi: float, out_lo: float, out_hi: float) -> list[float]:
    span = max(hi - lo, 1.0e-9)
    return [out_lo + (v - lo) / span * (out_hi - out_lo) for v in values]


def svg_chart(
    out_path: Path,
    title: str,
    x: list[float],
    curves: list[dict],
    y_label: str,
    y2_label: str = "",
    hlines: list[tuple[float, str, str]] | None = None,
    y_min: float | None = None,
    y_max: float | None = None,
) -> None:
    """curves: [{label, values, color, axis('y'|'y2'), step(bool)}]. hlines: (y값, 라벨, 축)."""
    left = [c for c in curves if c.get("axis", "y") == "y"]
    right = [c for c in curves if c.get("axis") == "y2"]

    def bounds(cs, extra=()):  # noqa: ANN001
        vals = [v for c in cs for v in c["values"]] + list(extra)
        if not vals:
            return 0.0, 1.0
        lo, hi = min(vals), max(vals)
        pad = max((hi - lo) * 0.08, 1.0e-6)
        return lo - pad, hi + pad

    h_extra_y = [h[0] for h in (hlines or []) if h[2] == "y"]
    h_extra_y2 = [h[0] for h in (hlines or []) if h[2] == "y2"]
    lo1, hi1 = bounds(left, h_extra_y)
    if y_min is not None:
        lo1 = y_min
    if y_max is not None:
        hi1 = y_max
    lo2, hi2 = bounds(right, h_extra_y2)
    x_lo, x_hi = (min(x), max(x)) if x else (0.0, 1.0)

    px = _scale(x, x_lo, x_hi, ML, W - MR)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="Arial">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<text x="{ML}" y="24" font-size="15" font-weight="bold">{title}</text>',
        f'<text x="14" y="{(MT + H - MB) / 2:.0f}" font-size="11" transform="rotate(-90 14 {(MT + H - MB) / 2:.0f})">{y_label}</text>',
    ]
    if right and y2_label:
        parts.append(
            f'<text x="{W - 14}" y="{(MT + H - MB) / 2:.0f}" font-size="11" transform="rotate(90 {W - 14} {(MT + H - MB) / 2:.0f})">{y2_label}</text>'
        )
    # 격자 + 축 라벨
    for i in range(5):
        gy = MT + i * (H - MB - MT) / 4
        v1 = hi1 - i * (hi1 - lo1) / 4
        parts.append(f'<line x1="{ML}" y1="{gy:.1f}" x2="{W - MR}" y2="{gy:.1f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{ML - 6}" y="{gy + 4:.1f}" font-size="10" text-anchor="end">{v1:,.0f}</text>')
        if right:
            v2 = hi2 - i * (hi2 - lo2) / 4
            parts.append(f'<text x="{W - MR + 6}" y="{gy + 4:.1f}" font-size="10">{v2:,.1f}</text>')
    for i in range(6):
        gx = ML + i * (W - MR - ML) / 5
        tv = x_lo + i * (x_hi - x_lo) / 5
        parts.append(f'<text x="{gx:.1f}" y="{H - MB + 16}" font-size="10" text-anchor="middle">{tv:,.0f}s</text>')

    for hy, hlabel, haxis in hlines or []:
        lo, hi = (lo1, hi1) if haxis == "y" else (lo2, hi2)
        gy = _scale([hy], lo, hi, H - MB, MT)[0]
        parts.append(
            f'<line x1="{ML}" y1="{gy:.1f}" x2="{W - MR}" y2="{gy:.1f}" stroke="#9ca3af" stroke-dasharray="6 4"/>'
        )
        parts.append(f'<text x="{W - MR - 4}" y="{gy - 4:.1f}" font-size="10" text-anchor="end" fill="#6b7280">{hlabel}</text>')

    legend_x = ML
    for idx, curve in enumerate(curves):
        lo, hi = (lo1, hi1) if curve.get("axis", "y") == "y" else (lo2, hi2)
        py = _scale(curve["values"], lo, hi, H - MB, MT)
        if curve.get("step"):
            pts = []
            for i in range(len(px)):
                if i > 0:
                    pts.append(f"{px[i]:.1f},{py[i - 1]:.1f}")
                pts.append(f"{px[i]:.1f},{py[i]:.1f}")
            points = " ".join(pts)
        else:
            points = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(px, py))
        color = curve.get("color", PALETTE[idx % len(PALETTE)])
        dash = ' stroke-dasharray="4 3"' if curve.get("axis") == "y2" else ""
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.8"{dash} points="{points}"/>')
        parts.append(f'<rect x="{legend_x}" y="{H - 14}" width="14" height="4" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 18}" y="{H - 8}" font-size="11">{curve["label"]}</text>')
        legend_x += 18 + 7 * len(curve["label"]) + 16
    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="attempt_0/proposed 가 들어있는 attempt 디렉토리")
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rho-crit", type=float, default=33.5)
    parser.add_argument("--ramp-capacity-total", type=float, default=6000.0)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    ctl = _read(run_dir / "proposed" / "control_timeseries.csv")
    st = _read(run_dir / "proposed" / "state_timeseries.csv")
    rl = _read(run_dir / "proposed" / "run_log.csv")
    stb = _read(run_dir / "baseline" / "state_timeseries.csv")
    t = [_f(r, "time_sec") for r in st]

    # --- VSL: 링크별 VSL 명령 vs 본선 평균 밀도비(ρ/ρ_crit) + 초과 interval ---
    for link in ("FW_W", "FW_E"):
        svg_chart(
            out / f"{args.label}_vsl_{link}.svg",
            f"[{args.label}] VSL vs density — {link} (proposed)",
            t,
            [
                {"label": f"VSL {link} [km/h]", "values": [_f(c, f"vsl_{link}", 100.0) for c in ctl], "color": "#2563eb", "step": True},
                {"label": "rho/rho_crit (proposed)", "values": [_f(s, f"rho_{link}_mean") / args.rho_crit for s in st], "color": "#dc2626", "axis": "y2"},
                {"label": "rho/rho_crit (baseline)", "values": [_f(s, f"rho_{link}_mean") / args.rho_crit for s in stb], "color": "#9ca3af", "axis": "y2"},
            ],
            "VSL [km/h]",
            "density ratio",
            hlines=[(1.0, "ratio=1.0 (rho_crit)", "y2"), (0.95, "VSL activation 0.95", "y2")],
        )

    # --- Ramp metering: 총 metering 명령 vs N_UF_star vs w_r/x_on 큐 ---
    meter_total = [sum(_f(c, f"ramp_metering_{r}") for r in ("R_D_W", "R_F_W", "R_D_E", "R_F_E")) for c in ctl]
    nuf = [_f(c, "N_UF_star") for c in ctl]
    wr = [sum(_f(s, f"ramp_queue_{r}") for r in ("R_D_W", "R_F_W", "R_D_E", "R_F_E")) for s in st]
    xon = [_f(r, "onramp_approach_queue_veh") for r in rl]
    svg_chart(
        out / f"{args.label}_metering.svg",
        f"[{args.label}] ramp metering vs targets/queues (proposed)",
        t,
        [
            {"label": "sum metering cmd [veh/h]", "values": meter_total, "color": "#2563eb", "step": True},
            {"label": "N_UF_star [veh/h]", "values": nuf, "color": "#059669", "step": True},
            {"label": "w_r total [veh]", "values": wr, "color": "#dc2626", "axis": "y2"},
            {"label": "x_on total [veh]", "values": xon, "color": "#d97706", "axis": "y2"},
        ],
        "flow [veh/h]",
        "queue [veh]",
        hlines=[(args.ramp_capacity_total, "ramp capacity 6000", "y")],
    )

    # --- Offset: 신호별 offset + 인접쌍 Δoffset vs 이상 진행시간 ---
    signals = ["A", "B", "C", "D", "F"]
    svg_chart(
        out / f"{args.label}_offsets.svg",
        f"[{args.label}] signal offsets (proposed) — plant에 미반영(장식 변수)",
        t,
        [
            {"label": f"offset {s} [s]", "values": [_f(c, f"offset_{s}") for c in ctl], "step": True}
            for s in signals
        ],
        "offset [s]",
        y_min=0.0,
        y_max=120.0,
    )
    cycle = 120.0
    d_ab = [(_f(c, "offset_B") - _f(c, "offset_A")) % cycle for c in ctl]
    d_bc = [(_f(c, "offset_C") - _f(c, "offset_B")) % cycle for c in ctl]
    svg_chart(
        out / f"{args.label}_offset_progression.svg",
        f"[{args.label}] corridor delta-offset vs ideal urban progression",
        t,
        [
            {"label": "offset(B)-offset(A) [s]", "values": d_ab, "color": "#2563eb", "step": True},
            {"label": "offset(C)-offset(B) [s]", "values": d_bc, "color": "#dc2626", "step": True},
        ],
        "delta offset [s]",
        hlines=[(95.0, "ideal urban 1.32km@50km/h = 95s", "y")],
        y_min=0.0,
        y_max=120.0,
    )

    # --- Green split: 신호별 p1 비율(NS축) — 신호제어가 실제로 반응하는 부분 ---
    svg_chart(
        out / f"{args.label}_green_p1_fraction.svg",
        f"[{args.label}] green p1(NS) fraction by signal (proposed)",
        t,
        [
            {
                "label": f"{s} p1/(p1+p2)",
                "values": [
                    _f(c, f"green_{s}_p1") / max(_f(c, f"green_{s}_p1") + _f(c, f"green_{s}_p2"), 1.0e-9)
                    for c in ctl
                ],
                "step": True,
            }
            for s in signals
        ],
        "p1 fraction",
        y_min=0.0,
        y_max=1.0,
        hlines=[(0.5, "50/50", "y")],
    )

    # --- 수치 요약 stdout ---
    vsl_active = sum(
        1 for c in ctl if any(_f(c, f"vsl_{link}", 100.0) < 99.5 for link in ("FW_W", "FW_E"))
    )
    meter_binding = sum(1 for v in meter_total if v < args.ramp_capacity_total - 4.0)
    ratio_peak = max(max(_f(s, f"rho_{link}_mean") / args.rho_crit for s in st) for link in ("FW_W", "FW_E"))
    print(
        f"{args.label}: intervals={len(ctl)} vsl_active={vsl_active} meter_binding={meter_binding} "
        f"rho_ratio_peak={ratio_peak:.3f} d_ab(mean)={sum(d_ab)/len(d_ab):.1f}s d_bc(mean)={sum(d_bc)/len(d_bc):.1f}s"
    )


if __name__ == "__main__":
    main()
