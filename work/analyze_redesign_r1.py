# Round 1a 재설계 분석 — 콤보 A/B/C vs PFO/PS4/P-CENT, "PFO 5셀 전부 이김" 판정 (2026-07-24)
import os
import pandas as pd, numpy as np
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
CELLS = [("Low","155"),("Medium","170"),("Skew","170skew"),("Incident","170inc"),("High","190")]
COLS = [("PFO","pfosplit",FF),("PS4 base","pstack4",PS),("A anchor","redesign_A",PS),
        ("B +green","redesign_B",PS),("C +far","redesign_C",PS),("P-CENT","pcent","P-CENT")]

print("="*104)
print("Round 1a — windowed TTT. 목표: 콤보가 PFO를 5셀 전부 이김(< PFO).")
print(f"{'cell':10}" + "".join(f"{n:>13}" for n,_,_ in COLS))
pfo_by = {}; combo_ttt = {c:{} for c in ["A anchor","B +green","C +far"]}
for nm,cell in CELLS:
    row=""; pfo=None
    for lbl,fp,ct in COLS:
        v = win(load(f"outputs/_diag/{fp}_{cell}/{ct}/run_log.csv"))
        if lbl=="PFO": pfo=v
        if lbl in combo_ttt: combo_ttt[lbl][cell]=(v,pfo)
        row += (f"{v:>13.0f}" if v is not None else f"{'미완':>13}")
    pfo_by[cell]=pfo
    print(f"{nm:10}{row}")
print("-"*104)
# win-all-5 판정
for combo in ["A anchor","B +green","C +far"]:
    wins=0; done=0; detail=[]
    for nm,cell in CELLS:
        v,pfo = combo_ttt[combo].get(cell,(None,None))
        if v is not None and pfo is not None:
            done+=1
            if v < pfo: wins+=1
            detail.append(f"{nm[:3]}{v-pfo:+.0f}")
    verdict = "★★PFO 5셀 전부 이김!" if (wins==5 and done==5) else f"{wins}/{done} 이김"
    print(f"  {combo:10}: {verdict}  [{' '.join(detail)}]")
print("="*104)

# 진단: incident step25 슬램 차단됐나 (base=2400 slam, PFO=5100)
print("\n진단 — Incident step25 리더 N_UF (base 슬램=2400, PFO=5100; 콤보서 5100 근처면 차단 성공):")
def nuf25(fp):
    d=load(f"outputs/_diag/{fp}_170inc/{PS}/run_log.csv")
    if d is None: return None
    sel=num(d,"leader_selected_N_UF_star"); st=num(d,"step")
    idx=np.where(st==25)[0]
    return sel[idx[0]] if len(idx) else None
for lbl,fp in [("base","pstack4"),("A","redesign_A"),("B","redesign_B"),("C","redesign_C")]:
    v=nuf25(fp); print(f"  {lbl:6}: N_UF@25 = {f'{v:.0f}' if v is not None else '미완'}")

# 진단: per-ramp 가격 non-zero 됐나 (base ~0)
print("\n진단 — per-ramp metering 가격 |max| (base ~0.06; 커지면 가격 살아남):")
def pmax(fp):
    d=load(f"outputs/_diag/{fp}_170inc/{PS}/run_log.csv")
    if d is None: return None
    vals=[np.nanmax(np.abs(num(d,f"wu_b3_meter_price_{r}"))) for r in ["R_D_E","R_D_W","R_F_E","R_F_W"] if num(d,f"wu_b3_meter_price_{r}") is not None]
    return max(vals) if vals else None
for lbl,fp in [("base","pstack4"),("C","redesign_C")]:
    v=pmax(fp); print(f"  {lbl:6}: |meter price|max = {f'{v:.3f}' if v is not None else '미완'}")
