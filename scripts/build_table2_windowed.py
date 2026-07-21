# 5컨트롤러×5시나리오 windowed(A) TTT 표를 outputs에서 집계해 paper_data/CSV로 저장(2026-07-21)
"""Table 2 데이터 생성 — 창 [900s,14400s](warmup 제외, buffer 포함) total TTT.

물리: Wang 캘리브레이션(v115/ρc31.5/τ20.2/ν22.5/κ10/δ0.9), w60u T=14400.
컨트롤러: No control / Dist.(Wu) / Aug.Dist.(PFO) / Centralized(dense) / Proposed(P-Stack b13).
NC 기준선은 _wang/nc_*_wang(= _wang3/ncbit_170과 비트동일로 물리 일치 확증).

outputs/는 gitignore라 이 스크립트는 로컬 재현용이고, 결과 CSV(paper_data/)만 커밋한다.
"""
import csv, glob, json, os

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "paper_data")
os.makedirs(OUT, exist_ok=True)
WARM = 5
DT_H = 180.0 / 3600.0

CELLS = [("Low", "155"), ("Medium", "170"), ("Medium-Skew", "skew15"),
         ("Medium-Incident", "incident"), ("High", "190")]
CTRLS = [
    ("No control",  os.path.join(ROOT, "_wang",  "nc_{c}_wang")),
    ("Dist.",       os.path.join(ROOT, "_wang3", "wu_{c}")),
    ("Aug. Dist.",  os.path.join(ROOT, "_wang3", "pfo_{c}")),
    ("Centralized", os.path.join(ROOT, "_wang3", "pcent_{c}")),
    ("Proposed",    os.path.join(ROOT, "_wang3", "b13_{c}")),
]

def _f(x):
    try: return float(x)
    except: return 0.0

def windowed(rundir):
    logs = glob.glob(os.path.join(rundir, "*", "run_log.csv"))
    if not logs:
        return None
    rows = sorted(csv.DictReader(open(logs[0], encoding="utf-8")), key=lambda r: float(r["step"]))
    if len(rows) <= WARM:
        return None
    u = _f(rows[-1]["cumulative_urban_ttt"]) - _f(rows[WARM-1]["cumulative_urban_ttt"])
    fw = _f(rows[-1]["cumulative_freeway_ttt"]) - _f(rows[WARM-1]["cumulative_freeway_ttt"])
    comp = sum(_f(r.get("boundary_out_sink_veh")) + _f(r.get("mainline_exit_flow_total")) * DT_H
               for r in rows[WARM:])
    term = float("nan")
    sj = os.path.join(rundir, "summary.json")
    if os.path.exists(sj):
        d = json.load(open(sj)); d = d[0] if isinstance(d, list) else d
        term = d.get("terminal_total_vehicles", float("nan"))
    tot = u + fw
    return dict(urban=u, freeway=fw, total=tot, throughput=comp, terminal=term,
                att=(tot / comp * 60.0 if comp else float("nan")))

rows_out = []
for label, cell in CELLS:
    nc = windowed(CTRLS[0][1].format(c=cell))
    for cname, tmpl in CTRLS:
        r = windowed(tmpl.format(c=cell))
        if r is None:
            print("MISSING", cname, cell); continue
        imp = (nc["total"] - r["total"]) / nc["total"] * 100.0 if nc else float("nan")
        rows_out.append({
            "class": label, "cell": cell, "controller": cname,
            "urban_ttt": round(r["urban"], 1), "freeway_ttt": round(r["freeway"], 1),
            "total_ttt": round(r["total"], 1), "throughput": round(r["throughput"], 0),
            "terminal": round(r["terminal"], 0), "att_min": round(r["att"], 2),
            "improvement_pct": round(imp, 1),
        })

csv_path = os.path.join(OUT, "table2_5ctrl_5scen_windowed.csv")
with open(csv_path, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
    w.writeheader(); w.writerows(rows_out)
print("wrote", csv_path, "rows:", len(rows_out))
