# far weight sweep 분석 — MFD_FAR_W ∈ {0,0.25,0.5,0.75,1.0} × {incident,high} (2026-07-24)
# TTT vs weight + freeway/urban 분해 + 과-metering 완화. PFO 기준선 대비.
import os
import pandas as pd, numpy as np
BASE = "C:/Users/alsrj/Desktop/Numerical-Sim-offiter"
PS = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"; FF = "WU-FAITHFUL-FOLLOWER"
def load(rel):
    p = os.path.join(BASE, rel); return pd.read_csv(p) if os.path.exists(p) else None
def num(d, k): return pd.to_numeric(d[k], errors="coerce").to_numpy() if (d is not None and k in d.columns) else None
def win(d, k, warm=5, hi=14400):
    if d is None: return None
    c = num(d, k); st = num(d, "step"); t = num(d, "time_sec")
    bi = next((i for i, s in enumerate(st) if s == warm-1), None); end = len(d)-1
    for i in range(len(t)):
        if t[i] > hi: end = i-1; break
    return c[end] - (c[bi] if bi is not None else 0)
def pk(d, k, lo=900, hi=5220):
    v = num(d, k); t = num(d, "time_sec")
    return float(np.nanmean(v[(t>=lo)&(t<hi)])) if v is not None else None
RAMPS = ["R_D_E","R_D_W","R_F_E","R_F_W"]
def mtot(d):
    s = np.zeros(len(d))
    for r in RAMPS:
        v = num(d, f"ramp_metering_release_actual_{r}_veh")
        if v is not None: s += np.nan_to_num(v)
    d["_mt"] = s

# weight -> 폴더 (w=0=far-off, w=1=기존 pstack4_)
def folder(w, cell):
    if w == 0.0:   return f"outputs/_diag/pstack4faroff_{cell}/{PS}/run_log.csv"
    if w == 1.0:   return f"outputs/_diag/pstack4_{cell}/{PS}/run_log.csv"
    tag = {0.25:"025", 0.5:"05", 0.75:"075"}[w]
    return f"outputs/_diag/pstack4fw{tag}_{cell}/{PS}/run_log.csv"
WEIGHTS = [0.0, 0.25, 0.5, 0.75, 1.0]

for cell, nm in [("170inc","Incident"), ("190","High")]:
    pfo = load(f"outputs/_diag/pfosplit_{cell}/{FF}/run_log.csv")
    pfo_tot = win(pfo, "cumulative_total_ttt")
    print("=" * 78)
    print(f"{nm} — far weight sweep (PFO 기준선 총TTT = {pfo_tot:.0f})")
    print(f"{'MFD_FAR_W':>10}{'총TTT':>9}{'vsPFO':>8}{'fwyTTT':>9}{'urbTTT':>9}{'방류':>8}{'rampQ':>8}")
    best_w, best_t = None, 1e18
    for w in WEIGHTS:
        d = load(folder(w, cell))
        if d is None: print(f"{w:>10.2f}{'미완':>9}"); continue
        mtot(d)
        tot = win(d, "cumulative_total_ttt"); fwy = win(d, "cumulative_freeway_ttt"); urb = win(d, "cumulative_urban_ttt")
        mt = pk(d, "_mt"); rq = pk(d, "total_ramp_queue_end_veh")
        vs = f"{tot-pfo_tot:+.0f}" if pfo_tot else "-"
        if tot < best_t: best_t, best_w = tot, w
        print(f"{w:>10.2f}{tot:>9.0f}{vs:>8}{fwy:>9.0f}{urb:>9.0f}{mt:>8.0f}{rq:>8.0f}")
    print(f"  → 최적 w={best_w} (총TTT {best_t:.0f}), PFO({pfo_tot:.0f}) {'이김' if best_t<pfo_tot else '못이김'}")
print("=" * 78)
print("w↓일수록 far 약화 → 과-metering 완화(방류↑ rampQ↓ urbTTT↓ 기대). sweet spot=총TTT 최소.")
