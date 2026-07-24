# far-split 3×3 격자 분석 — (freeway_w, urban_w) → windowed TTT, PFO·P-CENT 대비 (2026-07-24)
# 대각선: (1,1)=pstack4_, (0.25/0.5/0.75 동일)=pstack4fw*_(incident/high만). off-diag=farsplit_(30런).
import os
import pandas as pd, numpy as np
BASE = "C:/Users/alsrj/Desktop/Numerical-Sim-offiter"
PS = "P-STACK-WU-FAITHFUL-ALLPRICE-JOINT"; FF = "WU-FAITHFUL-FOLLOWER"
def load(rel):
    p = os.path.join(BASE, rel); return pd.read_csv(p) if os.path.exists(p) else None
def win(d, warm=5, hi=14400):
    if d is None: return None
    c = pd.to_numeric(d["cumulative_total_ttt"], errors="coerce").to_numpy()
    st = pd.to_numeric(d["step"], errors="coerce").to_numpy()
    t = pd.to_numeric(d["time_sec"], errors="coerce").to_numpy()
    bi = next((i for i, s in enumerate(st) if s == warm - 1), None); end = len(d) - 1
    for i in range(len(t)):
        if t[i] > hi: end = i - 1; break
    return c[end] - (c[bi] if bi is not None else 0)
WT = {"025": 0.25, "05": 0.5, "075": 0.75, "1": 1.0}
TAGS = ["025", "05", "075", "1"]
def cell_grid(cell):
    # (wf_tag, wu_tag) -> TTT
    g = {}
    # off-diagonal 30런
    for wf in ["025", "05", "075"]:
        for wu in ["025", "05", "075"]:
            if wf == wu: continue
            g[(wf, wu)] = win(load(f"outputs/_diag/farsplit_f{wf}u{wu}_{cell}/{PS}/run_log.csv"))
    # diagonal 동일가중: global sweep (incident/high만 존재) + default (1,1)
    for wt in ["025", "05", "075"]:
        g[(wt, wt)] = win(load(f"outputs/_diag/pstack4fw{wt}_{cell}/{PS}/run_log.csv"))
    g[("1", "1")] = win(load(f"outputs/_diag/pstack4_{cell}/{PS}/run_log.csv"))
    return g
CELLS = [("Low", "155"), ("Medium", "170"), ("Skew", "170skew"), ("Incident", "170inc"), ("High", "190")]
PCENT_CELLS = {"170inc", "190", "170"}

for nm, cell in CELLS:
    print("=" * 74)
    pfo = win(load(f"outputs/_diag/pfosplit_{cell}/{FF}/run_log.csv"))
    pc = None
    if cell in PCENT_CELLS:
        pcd = load(f"outputs/_diag/pcent_{cell}/P-CENT/run_log.csv")
        pc = win(pcd)
    ptxt = f"PFO={pfo:.0f}" + (f"  P-CENT={pc:.0f}" if pc is not None else "")
    print(f"### {nm} ({cell})  [{ptxt}]  — 격자: 행=freeway_w, 열=urban_w")
    g = cell_grid(cell)
    print(f"{'fw\\ur':>7}" + "".join(f"{WT[t]:>9}" for t in ["025", "05", "075", "1"]))
    best = (None, 1e18)
    for wf in TAGS:
        cells_s = ""
        for wu in TAGS:
            v = g.get((wf, wu))
            if v is None: cells_s += f"{'-':>9}"
            else:
                cells_s += f"{v:>9.0f}"
                if v < best[1]: best = ((wf, wu), v)
        print(f"{WT[wf]:>7}" + cells_s)
    if best[0]:
        bwf, bwu = best[0]
        vs_pfo = f"{best[1]-pfo:+.0f}" if pfo else "-"
        vs_pc = f"{best[1]-pc:+.0f}" if pc is not None else "-"
        print(f"  → 최적 (fw={WT[bwf]}, ur={WT[bwu]}) = {best[1]:.0f}  | vs PFO {vs_pfo}  vs P-CENT {vs_pc}")
print("=" * 74)
print("freeway_w↓(위로)면 freeway 과보호 완화 기대. 최적이 대각선 밖(fw≠ur)이면 분리가중이 이득.")
print("최적 vs PFO<0 = 그 가중조합서 P-Stack이 PFO 이김.")
