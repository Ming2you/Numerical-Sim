# VSL 마찰 weight 스윕 미리보기 — 완료된 것만 즉시 집계(2026-07-23)
import csv, glob
CT = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"
CELLS = ["155", "170", "170skew", "170inc", "190", "190skew"]
WEIGHTS = [("002", 0.02), ("003", 0.03), ("004", 0.04), ("005", 0.05)]
BASE = {"155": 2989.8, "170": 3809.6, "170skew": 3990.2, "170inc": 5546.3, "190": 5734.8, "190skew": 6378.9}
ALLOFF = {"155": 2949, "170": 4110, "170skew": 3995, "170inc": 5818, "190": 6154, "190skew": 6126}

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
    except: return None, None, None
    segc = [c for c in rows[0] if c.startswith('vsl_FW') and 'seg' in c]
    used=set(); cd=None; prev=None; chg=0
    for r in rows:
        t=float(r['time_sec']); vs=[]
        for c in segc:
            try: v=round(float(r[c])); vs.append(v); used.add(v)
            except: pass
        if abs(t-9000)<90 and vs: cd=vs[0]
        if 900<=t<5220 and vs:
            if prev is not None and vs[0]!=prev: chg+=1
            prev=vs[0]
    return sorted(used), cd, chg

data={}
for c in CELLS:
    for wt,wv in WEIGHTS:
        if done(c,wt):
            ttt=windowed(rl(c,wt)); used,cd,chg=vinfo(ct(c,wt))
            data[(c,wt)]=(ttt,cd,chg)
        else:
            data[(c,wt)]=None

print("=== 미리보기(완료분) — VSL 마찰 weight 스윕 ===")
print("base=0.1(cooldown VSL 100 고착), all-off=0(115 회복)\n")

print("## 1) cooldown VSL @9000s  (115=회복성공 / 100=고착)")
print(f"{'cell':9}{'0(off)':>8}{'0.02':>7}{'0.03':>7}{'0.04':>7}{'0.05':>7}{'0.1':>6}")
for c in CELLS:
    row=f"{c:9}{'115':>8}"
    for wt,wv in WEIGHTS:
        d=data[(c,wt)]
        row+=f"{(d[1] if d and d[1] is not None else '..'):>7}"
    row+=f"{'100':>6}"
    print(row)

print("\n## 2) windowed TTT  (괄호=base대비Δ)")
print(f"{'cell':9}{'0(off)':>12}{'0.02':>12}{'0.03':>12}{'0.04':>12}{'0.05':>12}{'0.1(base)':>11}")
for c in CELLS:
    b=BASE[c]; ao=ALLOFF[c]
    row=f"{c:9}"+f"{ao:4.0f}({ao-b:+.0f})".rjust(12)
    for wt,wv in WEIGHTS:
        d=data[(c,wt)]
        row+=(f"{d[0]:4.0f}({d[0]-b:+.0f})".rjust(12) if d and d[0] else f"{'..':>12}")
    row+=f"{b:6.0f}".rjust(11)
    print(row)

print("\n## 3) peak chatter (seg0 VSL 변화 횟수)")
print(f"{'cell':9}{'0.02':>7}{'0.03':>7}{'0.04':>7}{'0.05':>7}")
for c in CELLS:
    row=f"{c:9}"
    for wt,wv in WEIGHTS:
        d=data[(c,wt)]
        row+=f"{(d[2] if d and d[2] is not None else '..'):>7}"
    print(row)

# 요약
print("\n## 요약 (weight별 회복 셀수 / 평균 TTTΔ)")
for wt,wv in WEIGHTS:
    ds=[data[(c,wt)] for c in CELLS if data[(c,wt)]]
    recov=sum(1 for d in ds if d[1]==115)
    dts=[data[(c,wt)][0]-BASE[c] for c in CELLS if data[(c,wt)] and data[(c,wt)][0]]
    md=sum(dts)/len(dts) if dts else None
    n=len([1 for c in CELLS if data[(c,wt)]])
    print(f"  w={wv}: 회복 {recov}/{n}셀, 평균TTTΔ {md:+.0f}" + (f" ({6-n}셀 미완)" if n<6 else ""))
