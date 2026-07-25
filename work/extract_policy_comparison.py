# P-CENT/PFO/PS4/G 정책·성과 per-step 비교 추출 — 워크플로우 진단용 단일 진실 소스 (2026-07-25)
import os, pandas as pd, numpy as np
BASE="C:/Users/alsrj/Desktop/Numerical-Sim-offiter"
def load(fp,ct):
    p=os.path.join(BASE,f"outputs/_diag/{fp}/{ct}/run_log.csv"); return pd.read_csv(p) if os.path.exists(p) else None
def num(d,k): return np.nan_to_num(pd.to_numeric(d[k],errors="coerce").to_numpy()) if (d is not None and k in d.columns) else None
PS="P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"; FF="WU-FAITHFUL-FOLLOWER"
CTRLS=[("PS4","pstack4",PS),("G-CLF","redesign_G",PS),("PFO","pfosplit",FF),("PCENT","pcent","P-CENT")]

def windowed(d,col,warm=5,hi=14400):
    c=num(d,col); st=num(d,"step"); t=num(d,"time_sec")
    if c is None: return None
    bi=next((i for i,s in enumerate(st) if int(s)==warm-1),0); end=len(d)-1
    for i in range(len(t)):
        if t[i]>hi: end=i-1; break
    return c[end]-c[bi]

for CELL,tag in [("170inc","INCIDENT"),("190","HIGH")]:
    print("="*100); print(f"### {tag} ({CELL}) ###"); print("="*100)
    D={nm:load(f"{fp}_{CELL}",ct) for nm,fp,ct in CTRLS}
    # windowed 요약
    print("windowed TTT (warm5~14400): total / freeway / urban / (urban_share%)")
    for nm in D:
        d=D[nm]
        if d is None: print(f"  {nm:7}: 미완"); continue
        tot=windowed(d,"cumulative_total_ttt"); fw=windowed(d,"cumulative_freeway_ttt"); ur=windowed(d,"cumulative_urban_ttt")
        sh=100*ur/tot if (tot and ur is not None) else float('nan')
        print(f"  {nm:7}: total={tot:7.0f}  fw={fw:7.0f}  urban={ur:7.0f}  ({sh:4.1f}% urban)")
    # per-step (5스텝 간격) freeway/urban 증분·urban축적·boundary큐·metering
    print("\nper-step (Δ=구간증분 veh·h): fw_ttt Δ | urb_ttt Δ | urban_accum | boundary_q | metering_flow")
    ref=D["PS4"]; st=num(ref,"step")
    steps=list(range(0,len(st),5))
    for nm in D:
        d=D[nm]
        if d is None: continue
        cf=num(d,"cumulative_freeway_ttt"); cu=num(d,"cumulative_urban_ttt")
        ua=num(d,"urban_accumulation_veh"); bq=num(d,"boundary_in_load_veh")
        mf=num(d,"total_metering_flow")
        print(f"  --- {nm} ---")
        prev_i=None
        for i in steps:
            if i>=len(d): break
            s=int(num(d,"step")[i])
            dfw=(cf[i]-cf[prev_i]) if (cf is not None and prev_i is not None) else (cf[i] if cf is not None else float('nan'))
            dur=(cu[i]-cu[prev_i]) if (cu is not None and prev_i is not None) else (cu[i] if cu is not None else float('nan'))
            uav=ua[i] if ua is not None else float('nan')
            bqv=bq[i] if bq is not None else float('nan')
            mfv=mf[i] if mf is not None else float('nan')
            gate=""
            print(f"    s{s:>3}: fwΔ={dfw:6.0f} urbΔ={dur:6.0f} | uAcc={uav:5.0f} bndQ={bqv:6.0f} meter={mfv:7.0f}")
            prev_i=i
    print()
