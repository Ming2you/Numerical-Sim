# 최적 flagship 탐색표 (box-walk판) — PFO4 / PS4(old,no-bw) / PS4bw / PS4bw+supF / PS4bw+supA / b13 (2026-07-24)
# box-walk 효과 = PS4bw - PS4old. granularity(매칭 감독자·box-walk) = PS4bw+supF - b13.
import os
import numpy as np, pandas as pd
BASE = "C:/Users/alsrj/Desktop/Numerical-Sim-offiter"
PS = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"; FF = "WU-FAITHFUL-FOLLOWER"
CELLS = [("Low", "155"), ("Medium", "170"), ("Med-skew", "170skew"),
         ("Med-incident", "170inc"), ("High", "190")]

def load(rel):
    p = os.path.join(BASE, rel); return pd.read_csv(p) if os.path.exists(p) else None
def num(d, k): return pd.to_numeric(d[k], errors="coerce").to_numpy() if (d is not None and k in d.columns) else None
def win(d, warm=5, hi=14400):
    if d is None: return None
    cum = num(d, "cumulative_total_ttt"); st = num(d, "step"); t = num(d, "time_sec")
    bi = next((i for i, s in enumerate(st) if s == warm - 1), None)
    end = len(d) - 1
    if t is not None:
        for i in range(len(t)):
            if t[i] > hi: end = i - 1; break
    return cum[end] - (cum[bi] if bi is not None else 0)
def costm(d, warm=6):
    ct = num(d, "computation_time_sec"); st = num(d, "step")
    if ct is None: return None
    m = (st >= warm) if st is not None else np.ones(len(ct), bool)
    a = ct[m]; a = a[np.isfinite(a)]
    return float(np.mean(a)) if a.size else None
def walkfire(d, warm=5):  # (meter, vsl, green) 발화 스텝수
    out = []
    st = num(d, "step")
    for col in ["leader_box_walk_meter_active", "leader_box_walk_vsl_active", "leader_box_walk_green_active"]:
        v = num(d, col)
        if v is None: out.append(0); continue
        m = (st >= warm) if st is not None else np.ones(len(v), bool)
        out.append(int(np.sum(np.nan_to_num(v[m]) != 0)))
    return tuple(out)

def paths(c):
    return {
        "PFO4":    f"outputs/_diag/pfosplit_{c}/{FF}/run_log.csv",
        "PS4old":  f"outputs/_diag/pstack4_{c}/{PS}/run_log.csv",
        "PS4bw":   f"outputs/_diag/pstack4bw_{c}/{PS}/run_log.csv",
        "PS4bwF":  f"outputs/_diag/pstack4bwsupF_{c}/{PS}/run_log.csv",
        "PS4bwA":  f"outputs/_diag/pstack4bwsupA_{c}/{PS}/run_log.csv",
        "b13":     f"outputs/_diag/camp_s10on_{c}/{PS}/run_log.csv",
    }
ORDER = ["PFO4", "PS4old", "PS4bw", "PS4bwF", "PS4bwA", "b13"]
LBL = {"PFO4":"PFO(4)", "PS4old":"PS4 no-bw", "PS4bw":"PS4bw", "PS4bwF":"PS4bw+supF", "PS4bwA":"PS4bw+supA", "b13":"b13"}

print("=" * 120)
print("최적 flagship 탐색 (box-walk) — windowed TTT (900-14400). 볼드=셀 최소.")
print(f"{'cell':13}" + "".join(f"{LBL[k]:>13}" for k in ORDER) + f"{'best':>12}")
print("-" * 120)
tally = {k: 0 for k in ORDER}
for nm, c in CELLS:
    P = paths(c); w = {k: win(load(P[k])) for k in ORDER}
    valid = {k: v for k, v in w.items() if v is not None}
    best = min(valid, key=valid.get) if valid else None
    if best: tally[best] += 1
    row = "".join((f"{w[k]:>13.1f}" if w[k] is not None else f"{'미완':>13}") for k in ORDER)
    print(f"{nm:13}{row}{LBL.get(best,'-'):>12}")
print("-" * 120)
print("셀 승수: " + "  ".join(f"{LBL[k]}={tally[k]}" for k in ORDER))
print("=" * 120)

print("\nbox-walk 효과 (PS4bw − PS4old) & granularity@매칭 (PS4bw+supF − b13)")
print(f"{'cell':13}{'PS4bw-PS4old':>15}{'PS4bwF-b13':>13}")
for nm, c in CELLS:
    P = paths(c); bw = win(load(P["PS4bw"])); old = win(load(P["PS4old"]))
    f_ = win(load(P["PS4bwF"])); b = win(load(P["b13"]))
    e1 = f"{bw-old:+.1f}" if (bw is not None and old is not None) else "-"
    e2 = f"{f_-b:+.1f}" if (f_ is not None and b is not None) else "-"
    print(f"{nm:13}{e1:>15}{e2:>13}")
print("  PS4bw-PS4old<0 = box-walk가 개선(Inc/High 회복 기대). PS4bwF-b13<0 = 4-agent가 b13 이김.")

print("\nwalk 발화 (meter/vsl/green 스텝수) — VSL/green이 어디서 켜지나")
print(f"{'cell':13}{'PS4bw':>18}{'PS4bw+supF':>18}")
for nm, c in CELLS:
    P = paths(c)
    a = walkfire(load(P["PS4bw"])); b = walkfire(load(P["PS4bwF"]))
    print(f"{nm:13}{str(a):>18}{str(b):>18}")

print("\ncomputation cost mean s/step")
print(f"{'cell':13}" + "".join(f"{LBL[k]:>13}" for k in ORDER))
for nm, c in CELLS:
    P = paths(c)
    row = "".join((f"{costm(load(P[k])):>13.1f}" if costm(load(P[k])) is not None else f"{'미완':>13}") for k in ORDER)
    print(f"{nm:13}{row}")
