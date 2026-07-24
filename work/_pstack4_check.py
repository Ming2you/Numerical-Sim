import os, pandas as pd, numpy as np
BASE="C:/Users/alsrj/Desktop/Numerical-Sim-offiter"
PS="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"; FF="WU-FAITHFUL-FOLLOWER"
def load(p):
    p=os.path.join(BASE,p); return pd.read_csv(p) if os.path.exists(p) else None
def num(d,k): return pd.to_numeric(d[k],errors="coerce").to_numpy() if (d is not None and k in d.columns) else None
def win(d,warm=5,hi=14400):
    if d is None: return None
    cum=num(d,"cumulative_total_ttt"); st=num(d,"step"); t=num(d,"time_sec")
    bi=next((i for i,s in enumerate(st) if s==warm-1),None)
    end=len(d)-1
    if t is not None:
        for i in range(len(t)):
            if t[i]>hi: end=i-1; break
    return cum[end]-(cum[bi] if bi is not None else 0)
chk=load(f"outputs/_diag/pstack21check/{PS}/run_log.csv")
ref21=load(f"outputs/_diag/camp_s10on_170skew/{PS}/run_log.csv")
print("=== 1) P-Stack(21) F1-edit 안전(bit-identical) 검증 ===")
if chk is not None and ref21 is not None:
    c1=num(chk,"cumulative_total_ttt"); c2=num(ref21,"cumulative_total_ttt")
    n=min(len(c1),len(c2)); dmax=float(np.nanmax(np.abs(c1[:n]-c2[:n])))
    print(f"  겹치는 {n}스텝 max|Δcum_ttt| = {dmax:.6f}  → {'✅ bit-identical' if dmax<1e-6 else '⚠️ 차이'}")
else:
    print(f"  chk={chk is not None} ref21={ref21 is not None}")
print("\n=== 2) windowed TTT 비교 ===")
p4=load(f"outputs/_diag/pstack4_170skew/{PS}/run_log.csv")
rows=[("PFO(2) 7agent", win(load(f"outputs/_diag/pfo_170skew/{FF}/run_log.csv"))),
      ("PFO(4) 9agent", win(load(f"outputs/_diag/pfosplit_170skew/{FF}/run_log.csv"))),
      ("P-Stack(4) 9agent", win(p4)),
      ("P-Stack(21) 21agent", win(ref21))]
for k,v in rows: print(f"  {k:22} = {v:.1f}" if v is not None else f"  {k:22} = 미완")
print("\n=== 3) P-Stack(4) leader 예산 실현 (N_UF) ===")
if p4 is not None:
    for col in p4.columns:
        if "N_UF" in col or "nuf" in col.lower():
            v=num(p4,col)
            if v is not None and np.isfinite(np.nanmean(v)):
                print(f"  {col}: mean={np.nanmean(v):.1f} std={np.nanstd(v):.1f}")
    print(f"  rows={len(p4)}")
