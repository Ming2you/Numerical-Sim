# VSL_SMOOTH_W=0 6셀 완료 대기 후 자동 집계(2026-07-23)
import csv, glob, time
from pathlib import Path

CT = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
# (cell, smooth0 dir, base dir, base windowed TTT)
runs = [
    ("155", "outputs/_diag/nofric_155", "outputs/hinge_matrix/base_155", 2989.8),
    ("170", "outputs/_diag/nofric_170", "outputs/hinge_matrix/base_170", 3809.6),
    ("170skew", "outputs/_diag/nofric_170skew", "outputs/hinge_matrix/base_170skew", 3990.2),
    ("170inc", "outputs/_diag/nofric_170inc", "outputs/hinge_matrix/base_170inc", 5546.3),
    ("190", "outputs/_diag/nofric_190", "outputs/hinge_matrix/base_190", 5734.8),
    ("190skew", "outputs/_diag/nofric_190skew", "outputs/hinge_matrix/base_190skew", 6378.9),
]

def rlpath(d):
    g = glob.glob(f"{d}/{CT}/run_log.csv")
    return g[0] if g else None
def ctpath(d):
    g = glob.glob(f"{d}/{CT}/control_timeseries.csv")
    return g[0] if g else None
def complete(d):
    p = rlpath(d)
    if not p: return False
    try:
        with open(p, encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f) >= 81
    except Exception:
        return False

t0 = time.time()
while time.time() - t0 < 3*3600:
    if all(complete(d) for _, d, _, _ in runs):
        break
    time.sleep(60)

def windowed(p, WARM=5):
    try:
        rows = list(csv.DictReader(open(p, newline='', encoding='utf-8', errors='ignore')))
        cum = [float(r['cumulative_total_ttt']) for r in rows]
        st = [int(float(r['step'])) for r in rows]
        bi = next((i for i, s in enumerate(st) if s == WARM-1), None)
        return cum[-1] - (cum[bi] if bi is not None else 0.0)
    except Exception:
        return None
def vsl_info(ctp):
    """cooldown(t=150분) VSL, 전 구간 사용된 VSL 값 집합, peak 변화횟수(chatter)."""
    try:
        rows = list(csv.DictReader(open(ctp, newline='', encoding='utf-8', errors='ignore')))
    except Exception:
        return None
    segcols = [c for c in rows[0] if c.startswith('vsl_FW') and 'seg' in c]
    used = set(); cd150 = None; prev = None; peak_changes = 0
    for r in rows:
        t = float(r['time_sec'])
        vs = []
        for c in segcols:
            try: v = round(float(r[c])); vs.append(v); used.add(v)
            except Exception: pass
        if abs(t - 9000) < 90 and vs:
            cd150 = vs[0]
        # peak[900,5220] chatter: seg0 값 변화 횟수
        if 900 <= t < 5220 and vs:
            if prev is not None and vs[0] != prev: peak_changes += 1
            prev = vs[0]
    return sorted(used), cd150, peak_changes

out = []
out.append(f"=== VSL_SMOOTH_W=0 결과 (완료 {(time.time()-t0)/60:.0f}분 대기 후) ===\n")
out.append(f"{'cell':9}{'base':>8}{'smooth0':>10}{'Δ':>8}{'cd150 VSL':>11}{'used VSL vals':>22}{'peak변화':>9}")
for cell, d, _, base in runs:
    w = windowed(rlpath(d)); vi = vsl_info(ctpath(d))
    dd = (w - base) if w else None
    if vi:
        used, cd, pc = vi
        out.append(f"{cell:9}{base:8.0f}{(w or 0):10.0f}{(dd or 0):+8.1f}{(cd if cd is not None else -1):>11}{str(used):>22}{pc:>9}")
    else:
        out.append(f"{cell:9}{base:8.0f}{(w or 0):10.0f}{(dd or 0):+8.1f}   (ctrl_ts 없음)")
out.append("\n(Δ 음수=마찰제거로 개선. cd150=cooldown VSL(115면 회복). used=실제 쓰인 VSL 값들. peak변화=chatter 대리)")
txt = "\n".join(out)
print(txt)
Path("outputs/_diag/VSLSMOOTH_REPORT.txt").write_text(txt, encoding='utf-8')
print("\n[written: outputs/_diag/VSLSMOOTH_REPORT.txt]")
