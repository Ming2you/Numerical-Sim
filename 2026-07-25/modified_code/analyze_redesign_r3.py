# Round 3 gated-CLF 분석 — G vs PFO/PS4/P-CENT, 비트동일·진단 (2026-07-25)
import os, pandas as pd, numpy as np
BASE = "C:/Users/alsrj/Desktop/Numerical-Sim-offiter"
PS = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"; FF = "WU-FAITHFUL-FOLLOWER"
def load(rel):
    p = os.path.join(BASE, rel); return pd.read_csv(p) if os.path.exists(p) else None
def num(d, k): return pd.to_numeric(d[k], errors="coerce").to_numpy() if (d is not None and k in d.columns) else None
def win(d, warm=5, hi=14400):
    if d is None: return None
    c = num(d, "cumulative_total_ttt"); st = num(d, "step"); t = num(d, "time_sec")
    bi = next((i for i, s in enumerate(st) if s == warm-1), None); end = len(d)-1
    for i in range(len(t)):
        if t[i] > hi: end = i-1; break
    return c[end] - (c[bi] if bi is not None else 0)
CELLS = [("Low","155"),("Med","170"),("Skew","170skew"),("Inc","170inc"),("High","190")]

print("="*100)
print("Round 3 (gated CLF) — windowed TTT. 목표: G가 PFO를 5셀 전부 이김.")
print(f"{'cell':6}{'PFO':>9}{'PS4base':>9}{'G(CLF)':>9}{'P-CENT':>9} | {'G-PFO':>8} {'G-base':>8}  판정")
wins=0; done=0
for nm,cell in CELLS:
    pfo=win(load(f"outputs/_diag/pfosplit_{cell}/{FF}/run_log.csv"))
    ps4=win(load(f"outputs/_diag/pstack4_{cell}/{PS}/run_log.csv"))
    g  =win(load(f"outputs/_diag/redesign_G_{cell}/{PS}/run_log.csv"))
    pc =win(load(f"outputs/_diag/pcent_{cell}/P-CENT/run_log.csv"))
    def f(v): return f"{v:>9.0f}" if v is not None else f"{'--':>9}"
    gp = f"{g-pfo:+.0f}" if (g is not None and pfo is not None) else "--"
    gb = f"{g-ps4:+.0f}" if (g is not None and ps4 is not None) else "--"
    verdict = ""
    if g is not None and pfo is not None:
        done+=1
        if g < pfo: wins+=1; verdict="✓PFO이김"
        else: verdict="✗PFO패"
        if ps4 is not None and abs(g-ps4)<0.5: verdict+=" [base와 동일]"
    print(f"{nm:6}{f(pfo)}{f(ps4)}{f(g)}{f(pc)} | {gp:>8} {gb:>8}  {verdict}")
print("-"*100)
print(f"  판정: PFO {wins}/{done} 셀 이김" + ("  ★★★전부 이김!" if wins==5 and done==5 else ""))
print("="*100)

# 진단: Inc/High에서 CLF가 실제로 뭘 바꿨나
print("\n진단 — Inc/High: step25 N_UF 슬램·boundary큐peak·per-ramp가격 (base→G)")
def diag(fp, cell):
    d=load(f"outputs/_diag/{fp}_{cell}/{PS}/run_log.csv")
    if d is None: return None
    st=num(d,"step")
    sel=num(d,"leader_selected_N_UF_star"); i25=np.where(st==25)[0]
    nuf25 = sel[i25[0]] if (sel is not None and len(i25)) else None
    bnd=num(d,"leader_boundary_in_queue_veh"); bpk=np.nanmax(bnd) if bnd is not None else None
    prices=[np.nanmax(np.abs(num(d,f"wu_b3_meter_price_{r}"))) for r in ["R_D_E","R_D_W","R_F_E","R_F_W"] if num(d,f"wu_b3_meter_price_{r}") is not None]
    pmx=max(prices) if prices else None
    return nuf25,bpk,pmx
for cell in ["170inc","190"]:
    print(f"  [{cell}]")
    for lbl,fp in [("base","pstack4"),("G(CLF)","redesign_G")]:
        r=diag(fp,cell)
        if r is None: print(f"    {lbl:8}: 미완"); continue
        nuf25,bpk,pmx=r
        s_nuf = f"{nuf25:.0f}" if nuf25 is not None else "--"
        s_bpk = f"{bpk:.0f}" if bpk is not None else "--"
        s_pmx = f"{pmx:.3f}" if pmx is not None else "--"
        print(f"    {lbl:8}: N_UF@25={s_nuf}  boundary_peak={s_bpk}  |meter_price|max={s_pmx}")
