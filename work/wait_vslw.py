# VSL 마찰 weight 스윕(0.02~0.05) 24런 완료 대기 후 자동 집계(2026-07-23)
# base(0.1)·all-off(0)는 기존 결과 하드코딩 → 6점 커브(0→0.02→0.03→0.04→0.05→0.1)
import csv, glob, time
from pathlib import Path

CT = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
CELLS = ["155", "170", "170skew", "170inc", "190", "190skew"]
WEIGHTS = [("002", 0.02), ("003", 0.03), ("004", 0.04), ("005", 0.05)]

# 기존 측정값(windowed TTT)
BASE = {"155": 2989.8, "170": 3809.6, "170skew": 3990.2, "170inc": 5546.3, "190": 5734.8, "190skew": 6378.9}
ALLOFF = {"155": 2949, "170": 4110, "170skew": 3995, "170inc": 5818, "190": 6154, "190skew": 6126}
# base(0.1)의 cooldown VSL은 100 고착(회복 실패)이 원 문제였음. all-off(0)은 115 회복.

def rlpath(cell, wt):
    g = glob.glob(f"outputs/_diag/vslw{wt}_{cell}/{CT}/run_log.csv")
    return g[0] if g else None
def ctpath(cell, wt):
    g = glob.glob(f"outputs/_diag/vslw{wt}_{cell}/{CT}/control_timeseries.csv")
    return g[0] if g else None
def complete(cell, wt):
    p = rlpath(cell, wt)
    if not p: return False
    try:
        with open(p, encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f) >= 81
    except Exception:
        return False

# ---- 폴링(최대 4시간) ----
t0 = time.time()
while time.time() - t0 < 4*3600:
    if all(complete(c, wt) for c in CELLS for wt, _ in WEIGHTS):
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
    """cooldown(t=9000s) VSL, 전 구간 사용된 VSL 값 집합, peak[900,5220] seg0 변화횟수(chatter)."""
    try:
        rows = list(csv.DictReader(open(ctp, newline='', encoding='utf-8', errors='ignore')))
    except Exception:
        return None
    segcols = [c for c in rows[0] if c.startswith('vsl_FW') and 'seg' in c]
    used = set(); cd = None; prev = None; chg = 0
    for r in rows:
        t = float(r['time_sec'])
        vs = []
        for c in segcols:
            try: v = round(float(r[c])); vs.append(v); used.add(v)
            except Exception: pass
        if abs(t - 9000) < 90 and vs:
            cd = vs[0]
        if 900 <= t < 5220 and vs:
            if prev is not None and vs[0] != prev: chg += 1
            prev = vs[0]
    return sorted(used), cd, chg

# ---- 집계 ----
# 각 (cell, weight) 결과 수집
data = {}  # (cell, wt) -> dict(ttt, cd, used, chg)
for c in CELLS:
    for wt, wv in WEIGHTS:
        ttt = windowed(rlpath(c, wt))
        vi = vsl_info(ctpath(c, wt))
        used, cd, chg = (vi if vi else (None, None, None))
        data[(c, wt)] = dict(ttt=ttt, cd=cd, used=used, chg=chg)

out = []
out.append(f"=== VSL 마찰 weight 스윕 결과 (완료 {(time.time()-t0)/60:.0f}분 대기 후) ===")
out.append("base=0.1(원본, cooldown VSL 100 고착), all-off=0(VSL 등 4종 전부 off, 115 회복)\n")

# 표1: windowed TTT (Δ vs base)
out.append("## 1) windowed TTT — 값(괄호=base대비Δ)")
hdr = f"{'cell':9}{'w0(off)':>13}{'w0.02':>13}{'w0.03':>13}{'w0.04':>13}{'w0.05':>13}{'w0.1(base)':>13}"
out.append(hdr)
for c in CELLS:
    b = BASE[c]
    row = f"{c:9}"
    # w0 (all-off)
    ao = ALLOFF[c]; row += f"{ao:5.0f}({ao-b:+.0f})".rjust(13)
    for wt, wv in WEIGHTS:
        v = data[(c, wt)]['ttt']
        row += (f"{v:5.0f}({v-b:+.0f})".rjust(13) if v else f"{'..':>13}")
    row += f"{b:9.0f}".rjust(13)
    out.append(row)

# 표2: cooldown VSL (115=회복). base=100(고착), all-off=115
out.append("\n## 2) cooldown VSL @t=9000s (115=회복 성공, 100=고착)")
out.append(f"{'cell':9}{'w0(off)':>10}{'w0.02':>8}{'w0.03':>8}{'w0.04':>8}{'w0.05':>8}{'w0.1':>8}")
for c in CELLS:
    row = f"{c:9}{'115':>10}"
    for wt, wv in WEIGHTS:
        cd = data[(c, wt)]['cd']
        row += f"{(cd if cd is not None else -1):>8}"
    row += f"{'100':>8}"
    out.append(row)

# 표3: peak chatter (seg0 변화 횟수). 낮을수록 안정
out.append("\n## 3) peak[900,5220] chatter (seg0 VSL 변화 횟수, 낮을수록 안정)")
out.append(f"{'cell':9}{'w0.02':>8}{'w0.03':>8}{'w0.04':>8}{'w0.05':>8}")
for c in CELLS:
    row = f"{c:9}"
    for wt, wv in WEIGHTS:
        chg = data[(c, wt)]['chg']
        row += f"{(chg if chg is not None else -1):>8}"
    out.append(row)

# ---- 권고 로직 ----
out.append("\n## 4) 권고")
# 각 weight: 회복(cd==115)한 셀 수, 평균 TTT Δ vs base
summary = []
for wt, wv in WEIGHTS:
    recov = sum(1 for c in CELLS if data[(c, wt)]['cd'] == 115)
    dts = [data[(c, wt)]['ttt'] - BASE[c] for c in CELLS if data[(c, wt)]['ttt']]
    meandt = sum(dts)/len(dts) if dts else None
    chgs = [data[(c, wt)]['chg'] for c in CELLS if data[(c, wt)]['chg'] is not None]
    meanchg = sum(chgs)/len(chgs) if chgs else None
    summary.append((wv, recov, meandt, meanchg))
    out.append(f"  w={wv}: 회복 {recov}/6셀, 평균TTTΔ {meandt:+.0f}, 평균chatter {meanchg:.1f}")
# 추천: 전 셀(6/6) 회복하는 것 중 가장 높은 weight(=damping 최대 보존), 그 중 TTT 손해 최소
full = [s for s in summary if s[1] == 6]
if full:
    best = min(full, key=lambda s: (s[2] if s[2] is not None else 1e9))  # TTT 손해 최소
    highest = max(full, key=lambda s: s[0])  # 가장 높은 회복 weight
    out.append(f"\n  → 6/6 회복 weight 중 최고값(damping 최대 보존): w={highest[0]} (TTTΔ {highest[2]:+.0f})")
    out.append(f"  → 6/6 회복 weight 중 TTT 손해 최소: w={best[0]} (TTTΔ {best[2]:+.0f})")
else:
    out.append("\n  → 6/6 회복하는 weight 없음. 표2에서 셀별 임계값 확인 필요(0.02도 안되면 더 낮춰야).")
out.append("\n(주의: base 대비 TTT가 +면 회복시키느라 손해. 이상적 weight = 회복하면서 TTTΔ≈0)")

txt = "\n".join(out)
print(txt)
Path("outputs/_diag/VSLW_SWEEP_REPORT.txt").write_text(txt, encoding='utf-8')
print("\n[written: outputs/_diag/VSLW_SWEEP_REPORT.txt]")
