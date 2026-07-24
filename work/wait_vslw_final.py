# (A) VSL_SMOOTH_W={0, 0.005} × 5셀 완료 대기 후 분해 리포트(2026-07-23)
# 순수 VSL효과 = vslw000(VSL0,green0.1) − base(0.1); 순수 green효과 = all-off(0,0) − vslw000
import csv, glob, time
from pathlib import Path

CT = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
CELLS = ["155", "170", "170skew", "170inc", "190"]
ARMS = [("000", 0.0), ("0005", 0.005)]
BASE = {"155": 2989.8, "170": 3809.6, "170skew": 3990.2, "170inc": 5546.3, "190": 5734.8}
ALLOFF = {"155": 2949, "170": 4110, "170skew": 3995, "170inc": 5818, "190": 6154}  # VSL0+green0

def g1(pat):
    x = glob.glob(pat); return x[0] if x else None
def rl(c, wt): return g1(f"outputs/_diag/vslw{wt}_{c}/{CT}/run_log.csv")
def ct(c, wt): return g1(f"outputs/_diag/vslw{wt}_{c}/{CT}/control_timeseries.csv")
def done(c, wt):
    p = rl(c, wt)
    if not p: return False
    try:
        with open(p, encoding='utf-8', errors='ignore') as f: return sum(1 for _ in f) >= 81
    except: return False

t0 = time.time()
while time.time() - t0 < 3*3600:
    if all(done(c, wt) for c in CELLS for wt, _ in ARMS): break
    time.sleep(60)

def windowed(p, WARM=5):
    try:
        rows = list(csv.DictReader(open(p, newline='', encoding='utf-8', errors='ignore')))
        cum = [float(r['cumulative_total_ttt']) for r in rows]
        st = [int(float(r['step'])) for r in rows]
        bi = next((i for i, s in enumerate(st) if s == WARM-1), None)
        return cum[-1] - (cum[bi] if bi is not None else 0.0)
    except: return None
def vinfo(p):
    try: rows = list(csv.DictReader(open(p, newline='', encoding='utf-8', errors='ignore')))
    except: return None, None
    segc = [c for c in rows[0] if c.startswith('vsl_FW') and 'seg' in c]
    used = set(); cd = None
    for r in rows:
        t = float(r['time_sec']); vs = []
        for c in segc:
            try: v = round(float(r[c])); vs.append(v); used.add(v)
            except: pass
        if abs(t - 9000) < 90 and vs: cd = vs[0]
    return sorted(used), cd

D = {}
for c in CELLS:
    for wt, wv in ARMS:
        D[(c, wt)] = (windowed(rl(c, wt)), vinfo(ct(c, wt))[1])

out = []
out.append(f"=== (A) VSL-only 마찰 분해 리포트 (완료 {(time.time()-t0)/60:.0f}분 대기 후) ===")
out.append("vslw000=VSL0+green0.1 / all-off=VSL0+green0 / base=VSL0.1+green0.1. 190skew 제외.\n")

out.append("## 1) windowed TTT (괄호=base대비Δ) + cooldown VSL")
out.append(f"{'cell':9}{'base(0.1)':>11}{'w0.005':>14}{'w0(VSLonly)':>16}{'all-off':>14}")
for c in CELLS:
    b = BASE[c]
    t5, cd5 = D[(c, "0005")]
    t0v, cd0 = D[(c, "000")]
    ao = ALLOFF[c]
    row = f"{c:9}{b:8.0f}   "
    row += (f"{t5:.0f}({t5-b:+.0f})".rjust(14) if t5 else f"{'..':>14}")
    row += (f"{t0v:.0f}({t0v-b:+.0f})".rjust(16) if t0v else f"{'..':>16}")
    row += f"{ao:.0f}({ao-b:+.0f})".rjust(14)
    out.append(row)
    out.append(f"{'  └VSL@9000':16}{'':>4}{('115' if cd5==115 else str(cd5)):>10}(0.005){('115' if cd0==115 else str(cd0)):>10}(w0){'115':>10}(off)")

out.append("\n## 2) 분해 (핵심)")
out.append(f"{'cell':9}{'순수VSL효과':>16}{'순수green효과':>16}{'합(all-off−base)':>18}")
out.append("  (VSL: w0−base / green: alloff−w0 / 합=alloff−base)")
for c in CELLS:
    b = BASE[c]; t0v = D[(c, "000")][0]; ao = ALLOFF[c]
    if t0v:
        vsl_eff = t0v - b; grn_eff = ao - t0v; tot = ao - b
        out.append(f"{c:9}{vsl_eff:+16.0f}{grn_eff:+16.0f}{tot:+18.0f}")
    else:
        out.append(f"{c:9}{'(w0 미완)':>16}")

out.append("\n## 3) 해석 가이드")
out.append("  - w0(VSLonly)가 115 회복 + TTTΔ≈0 이면: VSL 마찰은 순수 cosmetic(TTT무관), 낮출 이유 없음 확정.")
out.append("  - 순수green효과가 크면(170/190 +): NO_FRICTION 손해의 진범=green 마찰 제거 확정.")
out.append("  - w0.005도 회복 못하면: 회복엔 정확히 0 필요(0.005도 막음).")

txt = "\n".join(out)
print(txt)
Path("outputs/_diag/VSLW_FINAL_REPORT.txt").write_text(txt, encoding='utf-8')
print("\n[written: outputs/_diag/VSLW_FINAL_REPORT.txt]")
